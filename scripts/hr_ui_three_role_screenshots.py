#!/usr/bin/env python3
"""
Capture HR module UIs with Playwright:

  • Employee: My Requests + every HR submission form (full-page).
  • HR (manager): Dashboard, Pending Review, Approved Forms; optional leave workflow modal flow.
  • GM: GM Approval queue + modal when workflow runs.

Prerequisites:
  - App running: python Injaaz.py (default http://127.0.0.1:5000)
  - pip install playwright && playwright install chromium

Usage:
  python scripts/hr_ui_three_role_screenshots.py
  python scripts/hr_ui_three_role_screenshots.py --no-workflow    # forms + lists only
  python scripts/hr_ui_three_role_screenshots.py --headed
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SIG_PLACEHOLDER = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# User-visible HR GET routes (forms + hub pages). Print/export URLs need submission ids — skipped here.
EMPLOYEE_HR_PATHS: list[tuple[str, str]] = [
    ("employee_my_requests", "/hr/my-requests"),
    ("form_leave_application", "/hr/leave-application-form"),
    ("form_commencement", "/hr/commencement-form"),
    ("form_duty_resumption", "/hr/duty-resumption-form"),
    ("form_contract_renewal", "/hr/contract-renewal-form"),
    ("form_performance_evaluation", "/hr/performance-evaluation-form"),
    ("form_grievance", "/hr/grievance-form"),
    ("form_interview_assessment", "/hr/interview-assessment-form"),
    ("form_passport_release", "/hr/passport-release-form"),
    ("form_staff_appraisal", "/hr/staff-appraisal-form"),
    ("form_station_clearance", "/hr/station-clearance-form"),
    ("form_visa_renewal", "/hr/visa-renewal-form"),
]

HR_MANAGER_PATHS: list[tuple[str, str]] = [
    ("hr_dashboard", "/hr/"),
    ("hr_pending_review", "/hr/pending-review"),
    ("hr_approved_forms", "/hr/approved-forms"),
]

GM_PATHS: list[tuple[str, str]] = [
    ("gm_approval_queue", "/hr/gm-approval"),
]


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name)


def _login(page, base: str, username: str, password: str) -> None:
    page.goto(f"{base}/login", wait_until="domcontentloaded")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#login-btn")
    page.wait_for_url("**/dashboard**", timeout=25000)


def _goto_and_shot(page, base: str, out: Path, fname: str, path: str) -> None:
    page.goto(f"{base}{path}", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(400)
    page.screenshot(path=str(out / f"{_safe_filename(fname)}.png"), full_page=True)


def _wait_list_or_empty(page, timeout_ms: int = 25000) -> None:
    page.wait_for_selector(
        ".review-card, .empty-state, #pendingList .alert-danger",
        timeout=timeout_ms,
    )


def main() -> int:
    p = argparse.ArgumentParser(description="HR module UI screenshots (all forms + optional workflow)")
    p.add_argument("--base-url", default=os.environ.get("HR_UI_BASE", "http://127.0.0.1:5000"))
    p.add_argument("--employee-user", default=os.environ.get("HR_UI_EMPLOYEE", "Arshith"))
    p.add_argument("--hr-user", default=os.environ.get("HR_UI_HR", "hr_manager"))
    p.add_argument("--gm-user", default=os.environ.get("HR_UI_GM", "Taha"))
    p.add_argument("--password", default=os.environ.get("HR_UI_PASSWORD", "TestHrUi@2026"))
    p.add_argument("--out-dir", default="", help="Output folder (default: generated/hr_ui_screenshots_<stamp>)")
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument(
        "--no-workflow",
        action="store_true",
        help="Skip leave submit → HR modal → GM modal end-to-end (only static pages).",
    )
    args = p.parse_args()

    base = args.base_url.rstrip("/")
    out = Path(args.out_dir) if args.out_dir else ROOT / "generated" / f"hr_ui_screenshots_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install playwright: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    captured: list[str] = []
    submission_id = ""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)

        # ── Employee: all HR forms + My Requests ─────────────────
        ctx_e = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx_e.new_page()
        _login(page, base, args.employee_user, args.password)

        for fname, path in EMPLOYEE_HR_PATHS:
            try:
                _goto_and_shot(page, base, out, fname, path)
                captured.append(f"{fname}.png")
            except Exception as ex:
                print(f"WARN employee {path}: {ex}", file=sys.stderr)
                page.screenshot(path=str(out / f"{_safe_filename(fname)}_ERROR.png"), full_page=True)
                captured.append(f"{fname}_ERROR.png")

        if not args.no_workflow:
            page.goto(f"{base}/hr/leave-application-form", wait_until="networkidle")
            page.fill('input[name="employee_name"]', "UI Test — Leave Applicant")
            page.fill('input[name="job_title"]', "Automation Tester")
            page.fill('input[name="department"]', "Quality Assurance")
            page.screenshot(path=str(out / "workflow_leave_step1.png"), full_page=True)
            captured.append("workflow_leave_step1.png")

            page.click(".btn-next")
            page.wait_for_selector("#step2Panel.active")
            start = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            end = (datetime.now() + timedelta(days=11)).strftime("%Y-%m-%d")
            page.click('label.leave-opt:has(input.leave-type-check[value="annual"])')
            page.fill("#firstDay", start)
            page.fill("#lastDay", end)
            page.evaluate("() => document.getElementById('firstDay').dispatchEvent(new Event('change'))")
            page.evaluate("() => document.getElementById('lastDay').dispatchEvent(new Event('change'))")
            page.locator('input[name="salary_advance"][value="no"]').click()
            page.evaluate(
                """(sig) => { document.getElementById('empSigData').value = sig; }""",
                SIG_PLACEHOLDER,
            )
            page.screenshot(path=str(out / "workflow_leave_step2.png"), full_page=True)
            captured.append("workflow_leave_step2.png")

            page.click('#leaveFrm button[type="submit"]')
            page.wait_for_selector("#successModal.show", timeout=30000)
            page.screenshot(path=str(out / "workflow_leave_submit_success.png"), full_page=True)
            captured.append("workflow_leave_submit_success.png")
            submission_id = page.locator("#submissionId").inner_text().strip()

        ctx_e.close()

        # ── HR manager pages ────────────────────────────────────
        ctx_h = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx_h.new_page()
        _login(page, base, args.hr_user, args.password)

        for fname, path in HR_MANAGER_PATHS:
            try:
                page.goto(f"{base}{path}", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(400)
                page.screenshot(path=str(out / f"{_safe_filename(fname)}.png"), full_page=True)
                captured.append(f"{fname}.png")
            except Exception as ex:
                print(f"WARN hr {path}: {ex}", file=sys.stderr)
                page.screenshot(path=str(out / f"{_safe_filename(fname)}_ERROR.png"), full_page=True)

        if not args.no_workflow and submission_id:
            page.goto(f"{base}/hr/pending-review", wait_until="networkidle")
            _wait_list_or_empty(page)
            page.screenshot(path=str(out / "workflow_hr_pending_list.png"), full_page=True)
            captured.append("workflow_hr_pending_list.png")

            card = page.locator(".review-card").filter(has_text=submission_id)
            card.locator(".btn-review-card").click()
            page.wait_for_selector("#reviewModal.show", timeout=15000)
            page.fill("#hrChecked", "YES")
            page.fill("#reviewComments", "HR UI capture — approve.")
            page.locator("#reviewModal .modal-content").screenshot(path=str(out / "workflow_hr_review_modal.png"))
            captured.append("workflow_hr_review_modal.png")

            page.locator("#reviewModal .btn-approve").click()
            page.wait_for_selector("#hrPendingReviewResultBanner", timeout=20000)
            page.screenshot(path=str(out / "workflow_hr_approve_result.png"), full_page=True)
            captured.append("workflow_hr_approve_result.png")
            page.locator("#hrPendingReviewResultBanner button").click()

            page.goto(f"{base}/hr/approved-forms", wait_until="networkidle")
            page.wait_for_timeout(600)
            page.screenshot(path=str(out / "workflow_hr_approved_forms_after_hr.png"), full_page=True)
            captured.append("workflow_hr_approved_forms_after_hr.png")

        ctx_h.close()

        # ── GM ───────────────────────────────────────────────────
        ctx_g = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx_g.new_page()
        _login(page, base, args.gm_user, args.password)

        for fname, path in GM_PATHS:
            try:
                _goto_and_shot(page, base, out, fname, path)
                captured.append(f"{fname}.png")
            except Exception as ex:
                print(f"WARN gm {path}: {ex}", file=sys.stderr)
                page.screenshot(path=str(out / f"{_safe_filename(fname)}_ERROR.png"), full_page=True)

        if not args.no_workflow and submission_id:
            page.goto(f"{base}/hr/gm-approval", wait_until="networkidle")
            _wait_list_or_empty(page)
            page.screenshot(path=str(out / "workflow_gm_pending_list.png"), full_page=True)
            captured.append("workflow_gm_pending_list.png")

            page.locator(".review-card").filter(has_text=submission_id).locator(".btn-review-card").click()
            page.wait_for_selector("#approvalModal.show", timeout=15000)
            page.fill("#gmComments", "GM UI capture — final approve.")
            page.locator("#approvalModal .modal-content").screenshot(path=str(out / "workflow_gm_approval_modal.png"))
            captured.append("workflow_gm_approval_modal.png")

            page.locator("#approvalModal .btn-approve-gm").click()
            page.wait_for_selector("#successModal.show", timeout=20000)
            page.screenshot(path=str(out / "workflow_gm_approve_result.png"), full_page=True)
            captured.append("workflow_gm_approve_result.png")

        ctx_g.close()

        # ── HR Approved Forms after full workflow ───────────────
        if not args.no_workflow and submission_id:
            ctx_h2 = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx_h2.new_page()
            _login(page, base, args.hr_user, args.password)
            page.goto(f"{base}/hr/approved-forms", wait_until="networkidle")
            page.wait_for_timeout(600)
            page.screenshot(path=str(out / "workflow_hr_approved_forms_final.png"), full_page=True)
            captured.append("workflow_hr_approved_forms_final.png")
            ctx_h2.close()

        browser.close()

    index = out / "INDEX.txt"
    index.write_text(
        "HR UI screenshots\n"
        f"base_url={base}\n"
        f"submission_id={submission_id or '(none — workflow skipped)'}\n\n"
        + "\n".join(sorted(set(captured))),
        encoding="utf-8",
    )

    print(f"Done. Output: {out}")
    print(f"Files: {len(set(captured))} screenshots (+ INDEX.txt)")
    if submission_id:
        print(f"Submission ID: {submission_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
