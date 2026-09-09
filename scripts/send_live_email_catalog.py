"""Send every outbound email template to one inbox from the running app.

Designed to run on live (operations.kynvera.net / Render SSH):

    python scripts/send_live_email_catalog.py
    python scripts/send_live_email_catalog.py --to contact@kynvera.net

Does not change users, passwords, MFA, or notification config in the database.
Each subject is prefixed with [LIVE EMAIL TEST] so you can filter the inbox
and Admin → Email logs (related_id starts with live-email-test-).
"""
from __future__ import annotations

import argparse
import os
import sys
import types
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, ROOT)

TO_DEFAULT = "contact@kynvera.net"
SUBJECT_PREFIX = "[LIVE EMAIL TEST]"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _tag(subject: str) -> str:
    if subject.startswith(SUBJECT_PREFIX):
        return subject
    return f"{SUBJECT_PREFIX} {subject}"


def _run(label: str, fn, *args, **kwargs) -> bool:
    try:
        ok = fn(*args, **kwargs)
        ok = bool(ok) if ok is not None else True
        print(f"  {'[OK]' if ok else '[!!]'}  {label:56s}  {'sent' if ok else 'send_email returned False'}")
        return ok
    except Exception as exc:
        print(f"  [XX]  {label:56s}  ERROR: {exc}")
        return False


def _fake_submission(module_type: str, user_id=None):
    s = types.SimpleNamespace()
    s.id = 0
    s.submission_id = f"LIVE-EMAIL-{module_type.upper()}-{_stamp()}"
    s.module_type = module_type
    s.user_id = user_id
    s.site_name = "Ajman Municipality — Live email test"
    s.visit_date = date.today()
    s.workflow_status = "hr_review"
    s.form_data = {
        "employee_name": "Live Email Test Employee",
        "submitted_by_name": "Live Email Test Submitter",
    }
    return s


def _fake_user(email: str, name="Live Email Tester", designation="supervisor"):
    u = types.SimpleNamespace()
    u.id = None
    u.full_name = name
    u.username = "live-email-test"
    u.email = email
    u.designation = designation
    u.role = "user"
    return u


def _tiny_txt():
    body = (
        b"Kynvera live email catalog test attachment.\n"
        b"This is not an operational report.\n"
    )
    return {
        "content": body,
        "filename": "LIVE_EMAIL_TEST.txt",
        "mime_type": "text/plain",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send every Kynvera email template to one inbox.")
    parser.add_argument("--to", default=os.environ.get("LIVE_EMAIL_TEST_TO", TO_DEFAULT))
    args, _ = parser.parse_known_args()
    to_addr = (args.to or TO_DEFAULT).strip()
    run_id = f"live-email-test-{_stamp()}"

    from Injaaz import create_app

    app = create_app()
    print("\n" + "=" * 72)
    print("  Kynvera live email catalog")
    print(f"  To:         {to_addr}")
    print(f"  related_id: {run_id}")
    print("=" * 72)

    passed = 0
    failed = 0

    with app.app_context():
        from common.email_service import (
            branded_kynvera_html,
            is_email_configured,
            send_account_created_email,
            send_account_status_email,
            send_admin_edit_otp_email,
            send_email,
            send_forgot_password_email,
            send_login_details_email,
            send_mfa_disabled_email,
            send_mfa_enabled_email,
            send_password_reset_email,
            send_password_updated_email,
        )
        from common.email_service import send_email as _raw_send

        if not is_email_configured(app):
            print("\n  Email is not configured on this host. Aborting.\n")
            return 1

        host = (app.config.get("APP_BASE_URL") or "").rstrip("/")
        sender = app.config.get("MAIL_DEFAULT_SENDER") or ""
        print(f"  APP_BASE_URL:         {host or '(unset)'}")
        print(f"  MAIL_DEFAULT_SENDER:  {sender or '(unset)'}")
        print(f"  RENDER:               {os.environ.get('RENDER') or 'no'}")

        def send(recipient, subject, body, **kwargs):
            kwargs.setdefault("related_id", run_id)
            return _raw_send(recipient, _tag(subject), body, **kwargs)

        # Prefix auth helpers without editing their source subjects after send.
        def wrap_auth(fn):
            def _inner(*a, **k):
                orig = _raw_send

                def prefixed(recipient, subject, body, *rest, **kw):
                    kw.setdefault("related_id", run_id)
                    return orig(recipient, _tag(subject), body, *rest, **kw)

                import common.email_service as es

                es.send_email = prefixed
                try:
                    return fn(*a, **k)
                finally:
                    es.send_email = orig

            return _inner

        print("\n── Auth ──────────────────────────────────────────────────────────")
        dummy_pw = "TEST-NOT-A-REAL-PASSWORD"
        checks = [
            (
                "Account created",
                wrap_auth(send_account_created_email),
                (to_addr, "live-email-test", "Live Email Tester", dummy_pw),
            ),
            (
                "Password updated (user)",
                wrap_auth(lambda: send_password_updated_email(
                    to_addr, "live-email-test", by_admin=False, full_name="Live Email Tester"
                )),
                (),
            ),
            (
                "Password updated (admin)",
                wrap_auth(lambda: send_password_updated_email(
                    to_addr, "live-email-test", by_admin=True, full_name="Live Email Tester"
                )),
                (),
            ),
            (
                "Account activated",
                wrap_auth(lambda: send_account_status_email(
                    to_addr, "live-email-test", is_active=True, full_name="Live Email Tester"
                )),
                (),
            ),
            (
                "Account deactivated",
                wrap_auth(lambda: send_account_status_email(
                    to_addr, "live-email-test", is_active=False, full_name="Live Email Tester"
                )),
                (),
            ),
            (
                "Admin password reset",
                wrap_auth(send_password_reset_email),
                (to_addr, "live-email-test", dummy_pw),
            ),
            (
                "Login details",
                wrap_auth(send_login_details_email),
                (to_addr, "live-email-test", dummy_pw, "Live Email Tester"),
            ),
            (
                "MFA enabled",
                wrap_auth(send_mfa_enabled_email),
                (to_addr, "live-email-test", "Live Email Tester"),
            ),
            (
                "MFA disabled (user)",
                wrap_auth(lambda: send_mfa_disabled_email(
                    to_addr, "live-email-test", by_admin=False, full_name="Live Email Tester"
                )),
                (),
            ),
            (
                "MFA reset (admin)",
                wrap_auth(lambda: send_mfa_disabled_email(
                    to_addr, "live-email-test", by_admin=True, full_name="Live Email Tester"
                )),
                (),
            ),
            (
                "Admin edit OTP",
                wrap_auth(send_admin_edit_otp_email),
                (to_addr, "000000", "Live Email Tester"),
            ),
        ]
        for label, fn, fn_args in checks:
            ok = _run(label, fn, *fn_args)
            passed += int(ok)
            failed += int(not ok)

        forgot_user = _fake_user(to_addr, "Live Email Tester")
        ok = _run(
            "Forgot password",
            wrap_auth(send_forgot_password_email),
            forgot_user,
            "LIVE-EMAIL-TEST-TOKEN-INVALID",
        )
        passed += int(ok)
        failed += int(not ok)

        print("\n── Inspection + HR workflow (legacy notifications) ───────────────")
        import common.workflow_notifications as wn

        orig_cfg = wn._load_notification_config

        def _test_cfg():
            return {
                "inspection": {"to": [to_addr], "cc": [], "include_submitter": False},
                "hr": {"to": [to_addr], "cc": [], "include_submitter": False},
            }

        wn._load_notification_config = _test_cfg
        orig_wn_send = wn.send_email

        def _wn_send(recipient, subject, body, **kw):
            kw.setdefault("related_id", run_id)
            return orig_wn_send(recipient, _tag(subject), body, **kw)

        wn.send_email = _wn_send
        try:
            insp = _fake_submission("hvac_mep")
            supervisor = _fake_user(to_addr, "Arshith Supervisor", "supervisor")
            workflow = [
                ("Inspection submitted", wn.send_inspection_submitted, (insp, supervisor)),
                ("Inspection supervisor signed", wn.send_team_notification, (insp, supervisor, "Supervisor signed")),
                (
                    "Inspection OM signed",
                    wn.send_team_notification,
                    (_fake_submission("hvac_mep"), _fake_user(to_addr, "OM", "operations_manager"), "Operations Manager signed"),
                ),
                (
                    "Inspection BD signed",
                    wn.send_team_notification,
                    (_fake_submission("hvac_mep"), _fake_user(to_addr, "BD", "business_development"), "Business Development signed"),
                ),
                (
                    "Inspection procurement signed",
                    wn.send_team_notification,
                    (_fake_submission("hvac_mep"), _fake_user(to_addr, "Proc", "procurement"), "Procurement signed"),
                ),
                (
                    "Inspection GM completed",
                    wn.send_team_notification,
                    (_fake_submission("hvac_mep"), _fake_user(to_addr, "GM", "general_manager"), "General Manager signed — Form Completed"),
                ),
            ]
            hr = _fake_submission("hr_leave_application")
            emp = _fake_user(to_addr, "Test Employee", "employee")
            hr_m = _fake_user(to_addr, "HR Manager", "hr_manager")
            gm = _fake_user(to_addr, "GM", "general_manager")
            workflow += [
                ("HR form submitted", wn.send_hr_submitted, (hr, emp)),
                ("HR approved", wn.send_hr_notification, (hr, hr_m, "HR Approved — Pending GM Signature")),
                ("HR rejected", wn.send_hr_rejected, (hr, hr_m, "Live email catalog — not a real rejection")),
                ("HR GM approved", wn.send_hr_notification, (hr, gm, "GM Final Approval — Request Completed")),
                ("HR GM rejected", wn.send_hr_rejected, (hr, gm, "Live email catalog — not a real rejection")),
            ]
            for label, fn, fn_args in workflow:
                ok = _run(label, fn, *fn_args)
                passed += int(ok)
                failed += int(not ok)
        finally:
            wn._load_notification_config = orig_cfg
            wn.send_email = orig_wn_send

        print("\n── HR lifecycle ──────────────────────────────────────────────────")
        from module_hr import hr_lifecycle_emails as hle

        orig_hle_send = hle.send_email

        def _hle_send(recipient, subject, body, **kw):
            kw.setdefault("related_id", run_id)
            return orig_hle_send(recipient, _tag(subject), body, **kw)

        hle.send_email = _hle_send
        try:
            recipient = _fake_user(to_addr, "Live Email Tester", "employee")
            leave = _fake_submission("hr_leave_application", user_id=None)
            ok = _run(
                "HR received confirmation",
                lambda: hle.send_submitter_confirmation(app, leave, recipient) or True,
            )
            passed += int(ok)
            failed += int(not ok)
            ok = _run(
                "HR action required",
                lambda: hle.send_action_required(
                    app, leave, recipient, role_label="HR Manager"
                ) or True,
            )
            passed += int(ok)
            failed += int(not ok)

            # progress/outcome look up User by submission.user_id — use a stub session get.
            orig_get = hle.db.session.get

            def _get(model, ident, **kw):
                try:
                    from app.models import User as UserModel
                    if model is UserModel:
                        return recipient
                except Exception:
                    pass
                return orig_get(model, ident, **kw)

            hle.db.session.get = _get
            leave.user_id = 1
            try:
                ok = _run(
                    "HR progress",
                    lambda: hle.send_submitter_progress(
                        app, leave, signed_by_name="HR Manager", signed_role="HR"
                    ) or True,
                )
                passed += int(ok)
                failed += int(not ok)
                ok = _run(
                    "HR approved outcome",
                    lambda: hle.send_submitter_outcome(app, leave, approved=True) or True,
                )
                passed += int(ok)
                failed += int(not ok)
                ok = _run(
                    "HR not-approved outcome",
                    lambda: hle.send_submitter_outcome(
                        app, leave, approved=False, reason="Live email catalog — not a real rejection"
                    ) or True,
                )
                passed += int(ok)
                failed += int(not ok)
            finally:
                hle.db.session.get = orig_get
        finally:
            hle.send_email = orig_hle_send

        print("\n── Ticketing ─────────────────────────────────────────────────────")
        ticket_html = """
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
          <h2 style="color:#1e3a5f;">Work Order Completed</h2>
          <p>Ticket <strong>WO-LIVE-TEST</strong> has been closed (catalog test — not a real close).</p>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <tr><td style="padding:6px;font-weight:bold;width:140px;">Title</td><td style="padding:6px;">Live email catalog</td></tr>
            <tr><td style="padding:6px;font-weight:bold;">Project</td><td style="padding:6px;">Ajman Municipality</td></tr>
            <tr><td style="padding:6px;font-weight:bold;">Priority</td><td style="padding:6px;">MEDIUM</td></tr>
          </table>
          <p style="font-size:12px;color:#888;">Automated notification from Kynvera.</p>
        </div>
        """
        invoice_html = """
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
          <h2 style="color:#1e3a5f;">Work Order Invoice</h2>
          <p>Catalog test invoice for completed work order <strong>WO-LIVE-TEST</strong>.</p>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <tr><td style="padding:6px;font-weight:bold;width:160px;">Invoice Total</td><td style="padding:6px;">AED 0.00</td></tr>
          </table>
          <p style="font-size:12px;color:#888;">Automated notification from Kynvera.</p>
        </div>
        """
        ok = _run(
            "Ticket closed",
            send,
            to_addr,
            "[Injaaz] Work Order Closed — WO-LIVE-TEST",
            "Work order closed (live email catalog).",
            html_body=ticket_html,
            source="ticketing",
        )
        passed += int(ok)
        failed += int(not ok)
        ok = _run(
            "Ticket invoice",
            send,
            to_addr,
            "[Injaaz] Invoice — Work Order WO-LIVE-TEST",
            "Work order invoice (live email catalog).",
            html_body=invoice_html,
            attachments=[_tiny_txt()],
            source="ticketing",
        )
        passed += int(ok)
        failed += int(not ok)

        print("\n── Procurement ───────────────────────────────────────────────────")
        from module_procurement.pr_docs import EMAIL_DEFAULTS, _fill

        ctx = {
            "pr_id": "PR-LIVE-TEST",
            "property": "Ajman Municipality",
            "total": "AED 1,000.00",
            "status": "gm review",
            "approve_url": f"{host}/procurement/doc-approve/LIVE-EMAIL-TEST",
            "supplier": "Live Test Supplier",
        }
        for key, defaults in EMAIL_DEFAULTS.items():
            subject = _fill(defaults["subject"], ctx)
            body = _fill(defaults["body"], ctx).rstrip() + "\n\n—\nKynvera Procurement"
            html = (
                '<pre style="font-family:inherit;white-space:pre-wrap;">'
                + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                + "</pre>"
            )
            ok = _run(
                f"PR {key}",
                send,
                to_addr,
                subject,
                body,
                html_body=html,
                source="procurement_pr",
            )
            passed += int(ok)
            failed += int(not ok)

        print("\n── MMR / BD / Automations ────────────────────────────────────────")
        mmr_html = branded_kynvera_html(
            greeting="Daily CAFM report",
            paragraphs=[
                "This is a live catalog test of the MMR report email. No operational workbook is attached.",
            ],
            cta_url=f"{host}/admin/mmr" if host else "",
            cta_label="Open Report Generation",
        )
        ok = _run(
            "MMR report",
            send,
            to_addr,
            "MMR Daily Report — live email catalog",
            "MMR daily report catalog test. No operational workbook is attached.",
            html_body=mmr_html,
            attachments=[_tiny_txt()],
            source="mmr",
        )
        passed += int(ok)
        failed += int(not ok)

        from app.bd.email_automation import _html_body, _text_body

        bd_msg = (
            "This is a live catalog test of the BD email module from operations.kynvera.net.\n"
            "No client documents are attached."
        )
        bd_user = _fake_user(to_addr, "Kynvera Operations")
        ok = _run(
            "BD compose",
            send,
            to_addr,
            "BD update — live email catalog",
            _text_body(bd_msg, bd_user),
            html_body=_html_body(bd_msg, bd_user),
            source="bd_email",
        )
        passed += int(ok)
        failed += int(not ok)

        from app.automations.jobs import JOB_CATALOG
        from app.automations.runner import _email_copy

        now_local = datetime.now()
        for spec in JOB_CATALOG:
            if not spec.get("implemented"):
                continue
            names = "LIVE_EMAIL_TEST.txt"
            labels = [spec.get("title") or spec.get("slug")]
            subject, body, html_body, source = _email_copy(
                spec,
                now_local,
                names,
                module_labels_list=labels,
                files=[{"filename": names, "label": spec.get("title") or "", "folder": "Files"}],
            )
            ok = _run(
                f"Automation {spec.get('slug')}",
                send,
                to_addr,
                subject,
                body,
                html_body=html_body,
                attachments=[_tiny_txt()],
                source=source,
            )
            passed += int(ok)
            failed += int(not ok)
            # One representative automation email is enough for the attachment path;
            # still send each implemented job so the inbox shows every subject line.

        print("\n── Pipeline ping ─────────────────────────────────────────────────")
        ping_html = branded_kynvera_html(
            greeting="Live mailer check",
            paragraphs=[
                "If you received this, operations.kynvera.net can deliver to this inbox.",
                f"Catalog run id: {run_id}",
            ],
            cta_url=f"{host}/login" if host else "",
            cta_label="Open Kynvera",
        )
        ok = _run(
            "Pipeline ping",
            send,
            to_addr,
            "Kynvera mailer is working",
            f"Live mailer check from operations.kynvera.net. Run id: {run_id}",
            html_body=ping_html,
            source="other",
        )
        passed += int(ok)
        failed += int(not ok)

    print("\n" + "=" * 72)
    print(f"  Done.  sent={passed}  failed={failed}")
    print(f"  Inbox: {to_addr}")
    print(f"  Filter subject: {SUBJECT_PREFIX}")
    print("=" * 72 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
