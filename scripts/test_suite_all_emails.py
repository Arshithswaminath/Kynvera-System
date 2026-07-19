#!/usr/bin/env python3
"""
Suite 3 — Fire every product email trigger to Arshith's inbox.

Recipients default to:
  To: arshith@injaaz.ae
  CC: arshithinjaaz@gmail.com

Override with env:
  EMAIL_TEST_TO=you@example.com
  EMAIL_TEST_CC=other@example.com

Covers:
  • Inspection workflow stages
  • HR workflow stages (submit / approve / reject)
  • HR management-chain + routed-signoff action emails
  • Account emails (welcome, password reset, username change, OTP ×2)
  • Ticketing work-order created / closed
  • Civil Defense inspection scheduled
  • Cheque status change
  • Finance monthly report

Usage (from project root):
  python scripts/test_suite_all_emails.py
"""
from __future__ import annotations

import os
import sys
import types
from datetime import date, datetime, timedelta

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from test_suite_common import SuiteResult, ensure_root_on_path, fake_ticket, fake_user  # noqa: E402

# ── recipients ───────────────────────────────────────────────────────────────
TEST_TO = [
    e.strip()
    for e in os.environ.get("EMAIL_TEST_TO", "arshith@injaaz.ae").split(",")
    if e.strip()
]
TEST_CC = [
    e.strip()
    for e in os.environ.get("EMAIL_TEST_CC", "arshithinjaaz@gmail.com").split(",")
    if e.strip()
]
# ─────────────────────────────────────────────────────────────────────────────


def _fake_submission(module_type: str):
    s = types.SimpleNamespace()
    s.id = 9999
    s.submission_id = "TEST-EMAIL-SUITE-0001"
    s.module_type = module_type
    s.user_id = None
    s.site_name = "Test Site — Al Barsha"
    s.visit_date = date.today()
    s.form_data = {
        "employee_name": "Test Employee",
        "submitted_by_name": "Arshith Supervisor",
    }
    return s


def _run(result: SuiteResult, label: str, fn, *args, **kwargs):
    try:
        ok = fn(*args, **kwargs)
        # Some helpers return None on success (mgmt chain / slot assignment)
        if ok is None:
            result.pass_(label)
            return True
        if ok:
            result.pass_(label)
            return True
        result.fail(label, "send returned False")
        return False
    except Exception as exc:
        result.fail(label, str(exc))
        return False


def _patch_workflow_config():
    import common.workflow_notifications as wn

    orig = wn._load_notification_config

    def patched():
        return {
            "inspection": {
                "to": list(TEST_TO),
                "cc": list(TEST_CC),
                "include_submitter": False,
            },
            "hr": {
                "to": list(TEST_TO),
                "cc": list(TEST_CC),
                "include_submitter": False,
            },
        }

    wn._load_notification_config = patched
    return orig, wn


def main() -> int:
    ensure_root_on_path()
    from Injaaz import create_app

    app = create_app()
    result = SuiteResult("Email suite")

    print(f"\n{'=' * 70}")
    print("  Suite 3 — All email triggers → Arshith")
    print(f"  To:  {', '.join(TEST_TO)}")
    print(f"  CC:  {', '.join(TEST_CC)}")
    print(f"{'=' * 70}")

    with app.app_context():
        from common.email_service import (
            is_email_configured,
            send_email,
            send_otp_email,
            send_password_reset_email,
            send_username_changed_email,
            send_welcome_email,
        )

        if not is_email_configured(app):
            print(
                "\n  [SKIP] Email is NOT configured on this machine.\n"
                "\n  Enable with Brevo:\n"
                "    BREVO_API_KEY=...  MAIL_DEFAULT_SENDER=noreply@injaaz.com\n"
                "\n  Or Gmail SMTP:\n"
                "    MAIL_SERVER=smtp.gmail.com MAIL_PORT=587\n"
                "    MAIL_USERNAME=... MAIL_PASSWORD=... MAIL_DEFAULT_SENDER=...\n"
            )
            return 1

        to_primary = TEST_TO[0]
        orig, wn = _patch_workflow_config()

        try:
            # ── Inspection workflow ──────────────────────────────────────────
            print("\n── Inspection workflow ────────────────────────────────────────────")
            insp = _fake_submission("hvac_mep")
            roles = [
                ("New submission", "supervisor", None),
                ("Supervisor signed", "supervisor", "Supervisor signed"),
                ("Operations Manager signed", "operations_manager", "Operations Manager signed"),
                ("Business Development signed", "business_development", "Business Development signed"),
                ("Procurement signed", "procurement", "Procurement signed"),
                ("GM signed — completed", "general_manager", "General Manager signed — Form Completed"),
            ]
            for label, desig, action in roles:
                user = fake_user(f"Arshith ({desig})", to_primary, desig)
                if action is None:
                    _run(result, f"inspection/{label}", wn.send_inspection_submitted, insp, user)
                else:
                    _run(result, f"inspection/{label}", wn.send_team_notification, insp, user, action)

            # ── HR workflow ──────────────────────────────────────────────────
            print("\n── HR workflow ───────────────────────────────────────────────────")
            hr = _fake_submission("hr_leave_application")
            emp = fake_user("Test Employee", to_primary, "employee")
            hr_m = fake_user("Arshith HR", to_primary, "hr_manager")
            gm = fake_user("Arshith GM", to_primary, "general_manager")
            _run(result, "hr/submitted", wn.send_hr_submitted, hr, emp)
            _run(result, "hr/approved", wn.send_hr_notification, hr, hr_m,
                 "HR Approved — Pending GM Signature")
            _run(result, "hr/rejected_by_hr", wn.send_hr_rejected, hr, hr_m,
                 "Does not meet leave policy requirements")
            _run(result, "hr/gm_approved", wn.send_hr_notification, hr, gm,
                 "GM Final Approval — Request Completed")
            _run(result, "hr/gm_rejected", wn.send_hr_rejected, hr, gm,
                 "Insufficient documentation provided")

            # ── HR management chain + routed signoff ─────────────────────────
            print("\n── HR sign-request emails ─────────────────────────────────────────")
            recipient = fake_user("Arshith Approver", to_primary, "hr_manager")
            try:
                from module_hr.hr_management_chain import _email_mgmt_sign_request
                _run(
                    result,
                    "hr/mgmt_sign_request",
                    lambda: _email_mgmt_sign_request(
                        app, recipient, hr,
                        employee_name="Test Employee",
                        form_type_display="Leave Application",
                        step_label="HR (head office)",
                    ) or True,
                )
            except Exception as exc:
                result.fail("hr/mgmt_sign_request", str(exc))

            try:
                from module_hr.hr_routed_signoffs import send_slot_assignment_email
                _run(
                    result,
                    "hr/routed_signoff",
                    lambda: send_slot_assignment_email(
                        app, recipient, hr,
                        submitter_name="Test Employee",
                        form_label="Leave Application",
                        slot_label="Replacement employee",
                    ) or True,
                )
            except Exception as exc:
                result.fail("hr/routed_signoff", str(exc))

            # ── Account / auth emails ────────────────────────────────────────
            print("\n── Account emails ─────────────────────────────────────────────────")
            _run(result, "account/welcome", send_welcome_email,
                 to_primary, "arshith", "TempPass123!", "Arshith Swaminath P")
            _run(result, "account/password_reset", send_password_reset_email,
                 to_primary, "arshith", "TempPass123!")
            _run(result, "account/username_changed", send_username_changed_email,
                 to_primary, "old_arshith", "arshith", "Arshith Swaminath P")
            _run(result, "account/otp_password_reset", send_otp_email,
                 to_primary, "arshith", "123456", "Password reset", 10)
            _run(result, "account/otp_admin_protect", send_otp_email,
                 to_primary, "arshith", "654321", "Admin protect PIN", 10)

            # ── Ticketing ────────────────────────────────────────────────────
            print("\n── Ticketing ──────────────────────────────────────────────────────")
            ticket = fake_ticket()
            creator = fake_user("Arshith Creator", to_primary, "supervisor")
            supervisor = fake_user("Arshith Supervisor", to_primary, "supervisor")
            try:
                from module_ticketing.routes import (
                    _send_completion_emails,
                    _send_work_order_created_email,
                )
                _run(
                    result,
                    "ticketing/work_order_created",
                    lambda: (_send_work_order_created_email(ticket, creator, supervisor), True)[1],
                )
                _run(
                    result,
                    "ticketing/work_order_closed",
                    lambda: (
                        _send_completion_emails(
                            ticket, creator,
                            custom_to=list(TEST_TO),
                            custom_cc=list(TEST_CC),
                        ),
                        True,
                    )[1],
                )
            except Exception as exc:
                result.fail("ticketing/*", str(exc))

            # ── Civil Defense inspection scheduled ───────────────────────────
            print("\n── Inspection (Civil Defense) ─────────────────────────────────────")
            try:
                from module_inspection.routes import _send_inspection_email

                notif = types.SimpleNamespace(
                    notif_id="CD-TEST-0001",
                    site_name="Ajman Tower",
                    inspection_type="Civil Defense Annual",
                    civil_defense_ref="CD-REF-99",
                    notification_date=date.today(),
                    inspection_date=date.today() + timedelta(days=14),
                    notes="Suite sample — please prepare technicians.",
                    ops_notified_at=None,
                    days_notice=lambda: 14,
                    days_remaining=lambda: 14,
                )

                # Avoid DB commit on fake object
                class _NoCommit:
                    def commit(self):
                        return None

                import module_inspection.routes as insp_routes
                from app.models import db as _db
                _orig_commit = _db.session.commit
                _db.session.commit = lambda: None
                try:
                    _run(
                        result,
                        "inspection/cd_scheduled",
                        lambda: (
                            _send_inspection_email(
                                notif,
                                custom_to=list(TEST_TO),
                                custom_cc=list(TEST_CC),
                            ),
                            True,
                        )[1],
                    )
                finally:
                    _db.session.commit = _orig_commit
            except Exception as exc:
                result.fail("inspection/cd_scheduled", str(exc))

            # ── Cheque status ────────────────────────────────────────────────
            print("\n── Operations (cheque) ────────────────────────────────────────────")
            try:
                from module_operations.routes import _send_cheque_status_email

                cheque = types.SimpleNamespace(
                    reference_no="CHQ-TEST-0001",
                    department="Operations",
                    total_amount=2500.0,
                    status="pending_verification",
                    office="Head Office",
                    requested_date=date.today(),
                    requested_by_name="Arshith Swaminath P",
                    verified_by_name=None,
                    approved_by_name=None,
                    items=[
                        types.SimpleNamespace(
                            sn=1, supplier="Emirates Supplies LLC",
                            amount=2500.0, cheque_date=date.today(),
                            remarks="Suite sample",
                        )
                    ],
                )

                # Patch ChequeNotificationConfig lookup
                import module_operations.routes as ops_routes
                fake_cfg = types.SimpleNamespace(
                    status="pending_verification",
                    to_emails=",".join(TEST_TO),
                    cc_emails=",".join(TEST_CC),
                )
                _orig_q = ops_routes.ChequeNotificationConfig.query

                class _Q:
                    @staticmethod
                    def filter_by(**kwargs):
                        return types.SimpleNamespace(first=lambda: fake_cfg)

                ops_routes.ChequeNotificationConfig.query = _Q()
                try:
                    _run(
                        result,
                        "operations/cheque_status",
                        _send_cheque_status_email,
                        cheque, "draft", "pending_verification",
                        "Arshith Swaminath P", "Suite sample status change",
                    )
                finally:
                    ops_routes.ChequeNotificationConfig.query = _orig_q
            except Exception as exc:
                result.fail("operations/cheque_status", str(exc))

            # ── Finance monthly report ───────────────────────────────────────
            print("\n── Finance ────────────────────────────────────────────────────────")
            try:
                html = (
                    "<html><body style='font-family:sans-serif'>"
                    "<h2 style='color:#a8121e'>Monthly Finance Report — Test</h2>"
                    "<p>Period: Suite sample · Jobs: 1 · Value: AED 450.00</p>"
                    "<p>This is an automated test email from the Amaan email suite.</p>"
                    "</body></html>"
                )
                plain = "Monthly Finance Report (suite): 1 jobs, AED 450.00"
                subject = f"[Amaan Finance] Monthly Report — Suite Test {date.today():%b %Y}"

                def _send_finance():
                    ok_any = False
                    for r in TEST_TO:
                        if send_email(
                            recipient=r,
                            subject=subject,
                            body=plain,
                            html_body=html,
                            cc=TEST_CC or None,
                        ):
                            ok_any = True
                    return ok_any

                _run(result, "finance/monthly_report", _send_finance)
            except Exception as exc:
                result.fail("finance/monthly_report", str(exc))

            # ── Generic smoke (attachments-free) ─────────────────────────────
            print("\n── Generic ────────────────────────────────────────────────────────")
            _run(
                result,
                "generic/ping",
                send_email,
                TEST_TO,
                "[Amaan] Email suite complete — ping",
                "All email triggers in the suite have been fired. Check inbox for the full set.",
                html_body=(
                    "<p>All email triggers in the <strong>Amaan email suite</strong> "
                    "have been fired.</p><p>Check your inbox for the full set.</p>"
                ),
                cc=TEST_CC or None,
            )

        finally:
            wn._load_notification_config = orig

    print(f"\nCheck inbox: {', '.join(TEST_TO)}")
    if TEST_CC:
        print(f"Check CC:    {', '.join(TEST_CC)}")
    return result.summary()


if __name__ == "__main__":
    sys.exit(main())
