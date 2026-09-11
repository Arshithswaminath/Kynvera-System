#!/usr/bin/env python3
"""Screenshot every HR fill form, form-wise.

Two-step forms get section_1.png + section_2.png.
Single-page forms get form.png.

Usage (app must already be running):
  ./venv/bin/python scripts/capture_hr_form_ui.py --base-url http://127.0.0.1:5002
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# slug, title, path, has_two_sections
HR_FORMS: list[tuple[str, str, str, bool]] = [
    ("leave_application", "Leave Application", "/hr/leave-application-form", True),
    ("commencement", "Commencement of Employment", "/hr/commencement-form", True),
    ("duty_resumption", "Duty Resumption", "/hr/duty-resumption-form", True),
    ("contract_renewal", "Contract Renewal", "/hr/contract-renewal-form", True),
    ("performance_evaluation", "Performance Evaluation", "/hr/performance-evaluation-form", True),
    ("grievance", "Grievance", "/hr/grievance-form", True),
    ("interview_assessment", "Interview Assessment", "/hr/interview-assessment-form", False),
    ("passport_release", "Passport Release", "/hr/passport-release-form", True),
    ("staff_appraisal", "Staff Appraisal", "/hr/staff-appraisal-form", True),
    ("station_clearance", "Station Clearance", "/hr/station-clearance-form", True),
    ("visa_renewal", "Visa Renewal", "/hr/visa-renewal-form", True),
    ("asset_handover", "Asset Handover", "/hr/asset-handover-form", True),
]


def _shot(page, dest: Path) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(250)
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(dest), full_page=True)


def _goto_step2(page) -> bool:
    page.once("dialog", lambda d: d.dismiss())
    moved = page.evaluate(
        """() => {
          if (typeof goToStep2 === 'function') { goToStep2(); return true; }
          if (typeof showStep2 === 'function') { showStep2(); return true; }
          const p2 = document.getElementById('step2Panel');
          const p1 = document.getElementById('step1Panel');
          if (!p2) return false;
          if (p1) p1.classList.remove('active');
          p2.classList.add('active');
          return true;
        }"""
    )
    if not moved:
        return False
    page.wait_for_timeout(400)
    return page.evaluate(
        """() => {
          const p2 = document.getElementById('step2Panel');
          return !!(p2 && p2.classList.contains('active'));
        }"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Capture HR form UIs, form-wise")
    p.add_argument("--base-url", default="http://127.0.0.1:5002")
    p.add_argument("--user", default="Arshith")
    p.add_argument("--password", default=os.environ.get("CHECK_PASSWORD") or os.environ.get("DEFAULT_ADMIN_PASSWORD") or "")
    p.add_argument("--out-dir", default="")
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(args.out_dir) if args.out_dir else ROOT / "generated" / f"hr_form_ui_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    captured: list[str] = []
    errors: list[str] = []

    from dotenv import load_dotenv
    from flask_jwt_extended import create_access_token, create_refresh_token

    load_dotenv(ROOT / ".env")
    from Injaaz import create_app
    from app.models import User

    flask_app = create_app()
    with flask_app.app_context():
        user = User.query.filter(
            (User.username == args.user) | (User.email == args.user)
        ).first()
        if not user:
            print(f"User not found: {args.user}", file=sys.stderr)
            return 1
        access = create_access_token(identity=str(user.id))
        refresh = create_refresh_token(identity=str(user.id))
        user_payload = user.to_client_dict()

    parsed = urlparse(base)
    cookie_url = f"{parsed.scheme}://{parsed.hostname}" + (
        f":{parsed.port}" if parsed.port else ""
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies(
            [
                {"name": "access_token_cookie", "value": access, "url": cookie_url},
                {"name": "refresh_token_cookie", "value": refresh, "url": cookie_url},
            ]
        )
        page = ctx.new_page()
        page.goto(f"{base}/dashboard", wait_until="domcontentloaded", timeout=30000)
        page.evaluate(
            """({access, refresh, user}) => {
              localStorage.setItem('access_token', access);
              localStorage.setItem('refresh_token', refresh);
              localStorage.setItem('user', JSON.stringify(user));
            }""",
            {"access": access, "refresh": refresh, "user": user_payload},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(600)

        for slug, title, path, two in HR_FORMS:
            folder = out / slug
            folder.mkdir(parents=True, exist_ok=True)
            try:
                page.goto(f"{base}{path}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(700)
                if two:
                    _shot(page, folder / "section_1.png")
                    captured.append(f"{slug}/section_1.png")
                    if _goto_step2(page):
                        _shot(page, folder / "section_2.png")
                        captured.append(f"{slug}/section_2.png")
                    else:
                        errors.append(f"{slug}: step 2 not shown")
                else:
                    _shot(page, folder / "form.png")
                    captured.append(f"{slug}/form.png")
                (folder / "README.txt").write_text(
                    f"{title}\n{path}\nsections={'2' if two else '1'}\n",
                    encoding="utf-8",
                )
                print(f"OK  {title}  ({'2 sections' if two else '1 page'})")
            except Exception as ex:
                print(f"ERR {title}: {ex}", file=sys.stderr)
                errors.append(f"{slug}: {ex}")
                try:
                    _shot(page, folder / "ERROR.png")
                except Exception:
                    pass

        browser.close()

    index = out / "INDEX.txt"
    index.write_text(
        "HR form UI screenshots (form-wise)\n"
        f"base_url={base}\n"
        f"user={args.user}\n\n"
        + "\n".join(captured)
        + ("\n\nERRORS\n" + "\n".join(errors) if errors else ""),
        encoding="utf-8",
    )
    print(f"\nDone. {len(captured)} files → {out}")
    if errors:
        print("Errors:\n  " + "\n  ".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
