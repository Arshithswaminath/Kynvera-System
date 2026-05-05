"""
Manual smoke-test for workflow email notifications.

Usage:
    python scripts/test_email_notification.py

What it does:
  1. Boots the Flask app with its real config + DB.
  2. Writes a temporary notification config (To / CC) so the test email
     goes to the addresses below — does NOT permanently overwrite the DB row.
  3. Fires every notification function (all stages for both modules).
  4. Prints a clear PASS / FAIL / SKIP (not configured) for each.

Edit TEST_TO / TEST_CC below to change recipients.
"""

import sys
import os
import types
from datetime import date, datetime

# ── recipients ───────────────────────────────────────────────────────────────
TEST_TO = ["arshith@injaaz.ae"]
TEST_CC = ["arshithinjaaz@gmail.com"]
# ─────────────────────────────────────────────────────────────────────────────

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Injaaz import create_app  # noqa: E402
app = create_app()


def _fake_submission(module_type, form_type="hr"):
    """Return a simple namespace that looks like a Submission ORM row."""
    s = types.SimpleNamespace()
    s.id = 9999
    s.submission_id = "TEST-NOTIF-0001"
    s.module_type = module_type
    s.user_id = None              # no DB lookup needed; submitter inclusion handled by None
    s.site_name = "Test Site — Al Barsha"
    s.visit_date = date.today()
    s.form_data = {
        "employee_name": "Test Employee",
        "submitted_by_name": "Test Supervisor",
    }
    return s


def _fake_user(name="Test User", designation="supervisor"):
    u = types.SimpleNamespace()
    u.id = 1
    u.full_name = name
    u.username = "testuser"
    u.email = TEST_TO[0]
    u.designation = designation
    u.role = "user"
    return u


def _patch_config(app):
    """
    Temporarily inject test To/CC into the notification config so the
    notification functions use them without touching the DB.
    We monkey-patch _load_notification_config in the module.
    """
    import common.workflow_notifications as wn

    _orig = wn._load_notification_config

    def _patched():
        return {
            "inspection": {
                "to": list(TEST_TO),
                "cc": list(TEST_CC),
                "include_submitter": False,   # submitter_email is None anyway
            },
            "hr": {
                "to": list(TEST_TO),
                "cc": list(TEST_CC),
                "include_submitter": False,
            },
        }

    wn._load_notification_config = _patched
    return _orig, wn


def _restore_config(wn, orig):
    wn._load_notification_config = orig


def _run(label, fn, *args):
    """Call fn(*args) and print a coloured result line."""
    try:
        ok = fn(*args)
        status = "PASS" if ok else "FAIL (send_email returned False)"
        print(f"  {'[OK]' if ok else '[!!]'}  {label:55s}  {status}")
        return ok
    except Exception as exc:
        print(f"  [XX]  {label:55s}  ERROR: {exc}")
        return False


def main():
    print("\n" + "=" * 70)
    print("  Injaaz Workflow Email Notification — smoke test")
    print(f"  To:  {', '.join(TEST_TO)}")
    print(f"  CC:  {', '.join(TEST_CC)}")
    print("=" * 70)

    with app.app_context():
        # Check email config first
        from common.email_service import is_email_configured
        if not is_email_configured(app):
            print(
                "\n  [SKIP]  Email is NOT configured on this machine.\n"
                "\n  To enable:\n"
                "    Option A (Brevo / Sendinblue — recommended):\n"
                "      Set env vars:  BREVO_API_KEY=<your-key>\n"
                "                     MAIL_DEFAULT_SENDER=noreply@injaaz.com\n"
                "\n    Option B (Gmail SMTP):\n"
                "      Set env vars:  MAIL_SERVER=smtp.gmail.com\n"
                "                     MAIL_PORT=587\n"
                "                     MAIL_USERNAME=you@gmail.com\n"
                "                     MAIL_PASSWORD=<app-password>\n"
                "                     MAIL_DEFAULT_SENDER=you@gmail.com\n"
                "\n  Then re-run this script.\n"
            )
            sys.exit(1)

        import common.workflow_notifications as wn
        orig, wn = _patch_config(app)

        try:
            print("\n── Inspection form notifications ───────────────────────────────────")
            insp = _fake_submission("hvac_mep", "inspection")
            supervisor = _fake_user("Arshith Supervisor", "supervisor")
            om_user    = _fake_user("Arshith OM", "operations_manager")
            bd_user    = _fake_user("Arshith BD", "business_development")
            proc_user  = _fake_user("Arshith Proc", "procurement")
            gm_user    = _fake_user("Arshith GM", "general_manager")

            _run("Stage 0 — New submission",        wn.send_inspection_submitted, insp, supervisor)
            _run("Stage 2 — Supervisor re-signed",  wn.send_team_notification,    insp, supervisor, "Supervisor signed")
            _run("Stage 3 — Operations Manager",    wn.send_team_notification,    insp, om_user,    "Operations Manager signed")
            _run("Stage 4 — Business Development",  wn.send_team_notification,    insp, bd_user,    "Business Development signed")
            _run("Stage 4 — Procurement",           wn.send_team_notification,    insp, proc_user,  "Procurement signed")
            _run("Stage 5 — General Manager (done)",wn.send_team_notification,    insp, gm_user,    "General Manager signed — Form Completed")

            print("\n── HR form notifications ────────────────────────────────────────────")
            hr = _fake_submission("hr_leave_application", "hr")
            emp  = _fake_user("Test Employee", "employee")
            hr_m = _fake_user("Mona HR Manager", "hr_manager")
            gm2  = _fake_user("Taha GM", "general_manager")

            _run("Stage 0 — HR form submitted",     wn.send_hr_submitted,    hr, emp)
            _run("Stage 1 — HR approved (→ GM)",    wn.send_hr_notification, hr, hr_m, "HR Approved — Pending GM Signature")
            _run("Stage 1 — HR rejected",           wn.send_hr_rejected,     hr, hr_m, "Does not meet leave policy requirements")
            _run("Stage 2 — GM final approval",     wn.send_hr_notification, hr, gm2,  "GM Final Approval — Request Completed")
            _run("Stage 2 — GM rejected",           wn.send_hr_rejected,     hr, gm2,  "Insufficient documentation provided")

        finally:
            _restore_config(wn, orig)

    print("\n" + "=" * 70)
    print("  Done.  Check your inbox at:", ", ".join(TEST_TO))
    print("         and CC box at:       ", ", ".join(TEST_CC))
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
