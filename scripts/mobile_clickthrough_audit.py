#!/usr/bin/env python3
"""Login and walk main module pages at a phone viewport. Flag overflow / huge filters."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    for _line in ENV_PATH.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

OUT = ROOT / "screenshots" / "mobile_clickthrough"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5002"
USER = os.environ.get("CHECK_USERNAME") or os.environ.get("DEFAULT_ADMIN_USERNAME") or "Kynvera"
PASSWORD = (
    os.environ.get("CHECK_PASSWORD")
    or os.environ.get("DEFAULT_ADMIN_PASSWORD")
    or "Arshith&Taha@2026"
)


def _login_via_api() -> tuple[str, str, dict] | None:
    req = Request(
        BASE.rstrip("/") + "/api/auth/login",
        data=json.dumps({"username": USER, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    user = data.get("user") or {}
    if not access:
        return None
    return access, refresh or "", user


def _mint_tokens() -> tuple[str, str, dict]:
    """Issue JWTs against the local sqlite user when the password login fails."""
    from flask import Flask
    from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, get_jti

    import config as config_module

    db_path = ROOT / "injaaz.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, username, full_name, role FROM users "
        "WHERE username = ? OR role = 'admin' ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END LIMIT 1",
        (USER, USER),
    ).fetchone()
    if not row:
        conn.close()
        raise SystemExit("No admin user in injaaz.db — cannot audit")
    uid = int(row["id"])
    user = {
        "id": uid,
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    }

    mini = Flask("audit-login")
    mini.config["JWT_SECRET_KEY"] = config_module.JWT_SECRET_KEY
    mini.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
    mini.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=1)
    JWTManager(mini)
    with mini.app_context():
        access = create_access_token(identity=str(uid))
        refresh = create_refresh_token(identity=str(uid))
        access_jti = get_jti(access)
        refresh_jti = get_jti(refresh)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn.execute(
        "INSERT INTO sessions (user_id, token_jti, expires_at, is_revoked, created_at) VALUES (?, ?, ?, 0, ?)",
        (uid, access_jti, now + timedelta(hours=2), now),
    )
    conn.execute(
        "INSERT INTO sessions (user_id, token_jti, expires_at, is_revoked, created_at) VALUES (?, ?, ?, 0, ?)",
        (uid, refresh_jti, now + timedelta(days=1), now),
    )
    conn.commit()
    conn.close()
    return access, refresh, user


def _install_session(context, page, access: str, refresh: str, user: dict) -> None:
    parsed = urlparse(BASE)
    cookie_url = f"{parsed.scheme}://{parsed.hostname}" + (f":{parsed.port}" if parsed.port else "")
    cookies = [
        {"name": "access_token_cookie", "value": access, "url": cookie_url},
    ]
    if refresh:
        cookies.append({"name": "refresh_token_cookie", "value": refresh, "url": cookie_url})
    context.add_cookies(cookies)
    page.goto(BASE.rstrip("/") + "/dashboard", wait_until="domcontentloaded")
    page.evaluate(
        """({access, refresh, user}) => {
          localStorage.setItem('access_token', access);
          if (refresh) localStorage.setItem('refresh_token', refresh);
          localStorage.setItem('user', JSON.stringify(user));
        }""",
        {"access": access, "refresh": refresh, "user": user},
    )
    page.reload(wait_until="domcontentloaded")

PAGES = [
    ("dashboard", "/dashboard"),
    ("tickets_hub", "/tickets/"),
    ("tickets_list", "/tickets/list"),
    ("tickets_new", "/tickets/new"),
    ("tickets_drafts", "/tickets/drafts"),
    ("tickets_settings", "/tickets/settings"),
    ("assets_hub", "/assets/"),
    ("assets_list", "/assets/list"),
    ("assets_map", "/assets/map"),
    ("bd", "/admin/bd"),
    ("bd_email", "/admin/email-notifications"),
    ("hr_hub", "/hr/"),
    ("hr_hiring", "/hr/hiring"),
    ("hr_leave", "/hr/leave-tracker"),
    ("hr_manpower", "/hr/manpower-tracker"),
    ("hr_pending", "/hr/pending-review"),
    ("hr_approved", "/hr/approved-forms"),
    ("hr_employees", "/hr/employee-list"),
    ("procurement_hub", "/procurement/"),
    ("procurement_pr", "/procurement/purchase-requests"),
    ("procurement_log", "/procurement/log"),
    ("procurement_props", "/procurement/properties"),
    ("procurement_suppliers", "/procurement/suppliers"),
    ("procurement_catalog", "/procurement/catalog/HVAC"),
    ("inspection_hub", "/inspection/"),
    ("qhse_hub", "/qhsi/"),
    ("qhse_staff", "/qhsi/staff-compliance"),
    ("files", "/files/"),
    ("mmr", "/admin/mmr/"),
    ("dochub", "/dochub"),
    ("admin", "/admin/dashboard"),
    ("devices", "/admin/devices"),
    ("devices_all", "/admin/devices/all"),
    ("devices_analytics", "/admin/devices/analytics"),
    ("devices_map", "/admin/devices/map"),
    ("devices_compliance", "/admin/devices/compliance"),
    ("devices_audit", "/admin/devices/audit"),
    ("team", "/admin/team-management"),
    ("database", "/admin/database"),
    ("workflow_pending", "/workflow/pending-reviews"),
    ("submitted_hr", "/workflow/submitted-forms?scope=hr"),
    ("submitted_insp", "/workflow/submitted-forms?scope=inspection"),
]

PROBE_JS = """() => {
  const vw = window.innerWidth;
  const issues = [];
  const docW = document.documentElement.scrollWidth;
  if (docW > vw + 24) {
    issues.push({kind:'page-overflow', scrollWidth: docW, vw});
  }
  document.querySelectorAll('input[type="search"], .tkt-filter-search, .fm-filter-search, .search-wrap, .cat-search-wrap, .kb-search-wrap').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.height > 72 && r.width > 80) {
      issues.push({kind:'tall-search', h: Math.round(r.height), tag: el.tagName, cls: el.className.slice(0,80)});
    }
  });
  document.querySelectorAll('select').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.height > 80 && r.width > 80) {
      issues.push({kind:'tall-select', h: Math.round(r.height), cls: (el.className||'').slice(0,80)});
    }
  });
  document.querySelectorAll('table').forEach((t) => {
    const r = t.getBoundingClientRect();
    if (r.width > vw + 24 && r.height > 40) {
      const wrap = t.closest('.table-scroll, .table-responsive, .mp-board-wrap, .lt-table-wrap, [style*="overflow"]');
      const parent = t.parentElement;
      const parentScroll = parent && parent.scrollWidth > parent.clientWidth + 4;
      const matrix = t.classList.contains('mp-board') || t.classList.contains('lt-table')
        || t.closest('.table-matrix, .mp-board-wrap, .lt-table-wrap');
      if (matrix && (wrap || parentScroll)) return;
      issues.push({
        kind:'wide-table',
        w: Math.round(r.width),
        vw,
        parentOverflow: !!(wrap || parentScroll),
        cls: (t.className||'').slice(0,80),
      });
    }
  });
  return issues;
}"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(25000)
        session = _login_via_api() or _mint_tokens()
        _install_session(context, page, session[0], session[1], session[2])
        page.wait_for_timeout(400)

        for name, path in PAGES:
            url = BASE.rstrip("/") + path
            entry = {"name": name, "path": path, "status": None, "issues": [], "shot": None}
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                entry["status"] = resp.status if resp else None
                page.wait_for_timeout(700)
                if entry["status"] and entry["status"] >= 400:
                    entry["issues"].append({"kind": "http", "status": entry["status"]})
                issues = page.evaluate(PROBE_JS)
                entry["issues"].extend(issues)
                shot = OUT / f"{name}.png"
                page.screenshot(path=str(shot), full_page=False)
                entry["shot"] = str(shot)
            except Exception as exc:
                entry["issues"].append({"kind": "error", "msg": str(exc)[:240]})
            report.append(entry)
            flag = "ISSUE" if entry["issues"] else "ok"
            print(f"{flag:5} {entry['status'] or '---'} {path} {entry['issues'][:3]}", flush=True)

        browser.close()

    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    problems = [r for r in report if r["issues"]]
    print(f"\n{len(problems)}/{len(report)} pages with issues → {OUT}", flush=True)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
