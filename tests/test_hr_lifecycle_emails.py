"""HR form lifecycle emails: submitter confirmation and next-signer action."""
from __future__ import annotations

import uuid

import pytest

SIG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def capture_hr_mail(monkeypatch):
    sent = []

    def fake_configured(app=None):
        return True

    def fake_send(recipient, subject, body, html_body=None, **kwargs):
        sent.append(
            {
                "to": recipient,
                "subject": subject,
                "body": body,
                "html": html_body or "",
            }
        )
        return True

    monkeypatch.setattr("module_hr.hr_lifecycle_emails.is_email_configured", fake_configured)
    monkeypatch.setattr("module_hr.hr_lifecycle_emails.send_email", fake_send)
    return sent


def _login_headers(client, username, password="TestPass123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def visa_chain_users(app):
    from app.models import db, User

    created = []

    def _mk(username, designation, *, reporting_manager_id=None, access_hr=False):
        u = User(
            username=username,
            email=f"{username}@example.com",
            full_name=username.replace("_", " ").title(),
            role="user",
            designation=designation,
            is_active=True,
            password_changed=True,
            reporting_manager_id=reporting_manager_id,
            access_hr=access_hr,
        )
        u.set_password("TestPass123")
        db.session.add(u)
        db.session.flush()
        created.append(u.id)
        return u

    with app.app_context():
        tag = uuid.uuid4().hex[:6]
        rm = _mk(f"taha_{tag}", "supervisor")
        gm = _mk(f"gm_{tag}", "general_manager")
        hr = _mk(f"hr_{tag}", "hr_manager", access_hr=True)
        emp = _mk(f"emp_{tag}", "employee", reporting_manager_id=rm.id)
        db.session.commit()
        yield {"emp": emp, "rm": rm, "gm": gm, "hr": hr, "tag": tag}
        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                db.session.delete(obj)
        db.session.commit()


def test_submit_emails_submitter_and_reporting_manager(client, app, visa_chain_users, capture_hr_mail):
    emp = visa_chain_users["emp"]
    rm = visa_chain_users["rm"]
    headers = _login_headers(client, emp.username)
    r = client.post(
        "/hr/api/submit",
        json={
            "form_type": "visa_renewal",
            "employee_name": "Visa Tester",
            "employee_signature": SIG,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body.get("success") is True
    sid = body["submission_id"]
    assert body.get("workflow_status") == "hr_mgmt_reporting_manager"

    tos = [m["to"] for m in capture_hr_mail]
    assert emp.email in tos
    assert rm.email in tos
    confirm = next(m for m in capture_hr_mail if m["to"] == emp.email)
    action = next(m for m in capture_hr_mail if m["to"] == rm.email)
    assert "We received your Visa Renewal" in confirm["subject"]
    assert sid in confirm["subject"]
    assert "Action required" in action["subject"]
    assert "Reporting manager" in action["html"]
    assert f"/hr/mgmt-sign/{sid}" in action["html"]
    assert "Kynvera" in confirm["html"]
    assert "Kynvera</span>" in confirm["html"]
    assert "All operations. One platform." in confirm["html"]
    assert "#ff8e68" in confirm["html"]
    assert "#fff8f5" in action["html"]
    assert "Kynvera</span>" in action["html"]
    assert "All operations. One platform." in action["html"]


def test_rm_sign_emails_submitter_and_gm(client, app, visa_chain_users, capture_hr_mail):
    emp = visa_chain_users["emp"]
    rm = visa_chain_users["rm"]
    gm = visa_chain_users["gm"]
    emp_headers = _login_headers(client, emp.username)
    r = client.post(
        "/hr/api/submit",
        json={
            "form_type": "visa_renewal",
            "employee_name": "Visa Tester",
            "employee_signature": SIG,
        },
        headers=emp_headers,
    )
    assert r.status_code == 200, r.get_json()
    sid = r.get_json()["submission_id"]
    capture_hr_mail.clear()

    rm_headers = _login_headers(client, rm.username)
    sign = client.post(
        f"/hr/api/mgmt-signoff/{sid}/sign",
        json={"signature": SIG},
        headers=rm_headers,
    )
    assert sign.status_code == 200, sign.get_json()
    assert sign.get_json().get("workflow_status") == "hr_mgmt_gm"

    tos = [m["to"] for m in capture_hr_mail]
    assert emp.email in tos
    assert gm.email in tos
    progress = next(m for m in capture_hr_mail if m["to"] == emp.email)
    gm_mail = next(m for m in capture_hr_mail if m["to"] == gm.email)
    assert "now with General manager" in progress["subject"]
    assert "Action required" in gm_mail["subject"]
    assert "General manager" in gm_mail["html"]
    assert f"/hr/mgmt-sign/{sid}" in gm_mail["html"]
    assert "Kynvera</span>" in gm_mail["html"]
    assert "All operations. One platform." in gm_mail["html"]
    assert "#ff8e68" in gm_mail["html"]
    assert "Kynvera</span>" in progress["html"]
    assert "All operations. One platform." in progress["html"]

    with app.app_context():
        from app.models import Notification
        progress_n = Notification.query.filter_by(
            submission_id=sid, notification_type="hr_progress", user_id=emp.id
        ).all()
        assert len(progress_n) == 1
        assert "now with" in (progress_n[0].message or "").lower()


@pytest.fixture()
def leave_office_users(app):
    """Office-staff leave path: employee with no reporting manager → GM → HR."""
    from app.models import db, User

    created = []

    def _mk(username, designation, *, access_hr=False):
        u = User(
            username=username,
            email=f"{username}@example.com",
            full_name=username.replace("_", " ").title(),
            role="user",
            designation=designation,
            is_active=True,
            password_changed=True,
            access_hr=access_hr,
        )
        u.set_password("TestPass123")
        db.session.add(u)
        db.session.flush()
        created.append(u.id)
        return u

    with app.app_context():
        tag = uuid.uuid4().hex[:6]
        gm = _mk(f"gm_{tag}", "general_manager")
        hr = _mk(f"hr_{tag}", "hr_manager", access_hr=True)
        emp = _mk(f"emp_{tag}", "employee")
        db.session.commit()
        yield {"emp": emp, "gm": gm, "hr": hr}
        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                db.session.delete(obj)
        db.session.commit()


def test_leave_goes_to_gm_first_then_hr_after_gm_signs(
    client, app, leave_office_users, capture_hr_mail
):
    """Leave is sequential: GM is notified on submit; HR only after GM signs."""
    from app.models import Notification, Submission

    emp = leave_office_users["emp"]
    gm = leave_office_users["gm"]
    hr = leave_office_users["hr"]
    emp_headers = _login_headers(client, emp.username)

    r = client.post(
        "/hr/api/submit",
        json={
            "form_type": "leave_application",
            "employee_name": "Leave Tester",
            "employee_signature": SIG,
            "need_coverage_signature": "no",
        },
        headers=emp_headers,
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body.get("success") is True
    sid = body["submission_id"]
    assert body.get("workflow_status") == "hr_mgmt_gm"

    submit_tos = [m["to"] for m in capture_hr_mail]
    assert emp.email in submit_tos
    assert gm.email in submit_tos
    assert hr.email not in submit_tos
    confirm = next(m for m in capture_hr_mail if m["to"] == emp.email)
    gm_mail = next(m for m in capture_hr_mail if m["to"] == gm.email)
    assert "We received your Leave Application" in confirm["subject"]
    assert "General manager" in confirm["html"]
    assert "Action required" in gm_mail["subject"]
    assert "General manager" in gm_mail["html"]
    assert "HR (head office)" not in gm_mail["html"]

    with app.app_context():
        signoff = Notification.query.filter_by(
            submission_id=sid, notification_type="hr_mgmt_chain_signoff"
        ).all()
        notified_ids = {n.user_id for n in signoff}
        assert gm.id in notified_ids
        assert emp.id not in notified_ids
        assert hr.id not in notified_ids

    capture_hr_mail.clear()
    gm_headers = _login_headers(client, gm.username)
    sign = client.post(
        f"/hr/api/mgmt-signoff/{sid}/sign",
        json={"signature": SIG},
        headers=gm_headers,
    )
    assert sign.status_code == 200, sign.get_json()
    signed = sign.get_json()
    assert signed.get("workflow_status") == "hr_mgmt_hr_head_office"
    assert signed.get("completed") is False

    after_tos = [m["to"] for m in capture_hr_mail]
    assert hr.email in after_tos
    assert emp.email in after_tos
    hr_mail = next(m for m in capture_hr_mail if m["to"] == hr.email)
    progress = next(m for m in capture_hr_mail if m["to"] == emp.email)
    assert "Action required" in hr_mail["subject"]
    assert "Your role</strong>: HR" in hr_mail["html"] or "as <strong>HR</strong>" in hr_mail["html"]
    assert "now with HR" in progress["subject"]
    assert "head office" not in hr_mail["html"].lower()
    assert "head office" not in progress["subject"].lower()
    gm_action_after = [
        m for m in capture_hr_mail if m["to"] == gm.email and "Action required" in m["subject"]
    ]
    assert gm_action_after == []

    with app.app_context():
        s = Submission.query.filter_by(submission_id=sid).first()
        assert s is not None
        assert s.workflow_status == "hr_mgmt_hr_head_office"
        hr_notices = Notification.query.filter_by(
            submission_id=sid, notification_type="hr_mgmt_chain_signoff", user_id=hr.id
        ).all()
        assert len(hr_notices) == 1
        progress_notices = Notification.query.filter_by(
            submission_id=sid, notification_type="hr_progress", user_id=emp.id
        ).all()
        assert len(progress_notices) == 1
        assert "now with" in (progress_notices[0].message or "").lower()
        assert emp.id not in {
            n.user_id
            for n in Notification.query.filter_by(
                submission_id=sid, notification_type="hr_mgmt_chain_signoff"
            ).all()
        }


def _leave_pdf_text(client, sid, headers, extra_query=""):
    pytest.importorskip("pypdf")
    from io import BytesIO
    from pypdf import PdfReader

    r = client.get(
        f"/hr/download-pdf/{sid}?inline=1{extra_query}",
        headers=headers,
    )
    assert r.status_code == 200, r.data[:400]
    return "".join((page.extract_text() or "") for page in PdfReader(BytesIO(r.data)).pages)


def test_preview_comment_shows_on_pdf_for_current_signer_only(
    client, app, leave_office_users, capture_hr_mail
):
    """Draft Comments (optional) overlay the PDF trail and HR Comments without saving."""
    from app.models import Submission
    from module_hr.hr_management_chain import MGMT_CHAIN_KEY, overlay_preview_comment_on_form_data

    emp = leave_office_users["emp"]
    gm = leave_office_users["gm"]
    hr = leave_office_users["hr"]
    token = "PreviewCommentXYZ123"

    emp_headers = _login_headers(client, emp.username)
    r = client.post(
        "/hr/api/submit",
        json={
            "form_type": "leave_application",
            "employee_name": "Leave Tester",
            "employee_signature": SIG,
            "need_coverage_signature": "no",
        },
        headers=emp_headers,
    )
    assert r.status_code == 200, r.get_json()
    sid = r.get_json()["submission_id"]

    gm_headers = _login_headers(client, gm.username)
    sign = client.post(
        f"/hr/api/mgmt-signoff/{sid}/sign",
        json={"signature": SIG, "comments": "Signed & Verified — Taha."},
        headers=gm_headers,
    )
    assert sign.status_code == 200, sign.get_json()
    assert sign.get_json().get("workflow_status") == "hr_mgmt_hr_head_office"

    with app.app_context():
        s = Submission.query.filter_by(submission_id=sid).first()
        assert s is not None
        overlaid = overlay_preview_comment_on_form_data(s.form_data, hr, s, token)
        assert overlaid.get("hr_comments") == token
        hr_step = next(
            st
            for st in (overlaid.get(MGMT_CHAIN_KEY) or {}).get("steps") or []
            if st.get("key") in ("hr_head_office", "hr_manager")
        )
        assert hr_step.get("comments") == token
        orig_hr = next(
            st
            for st in (s.form_data.get(MGMT_CHAIN_KEY) or {}).get("steps") or []
            if st.get("key") in ("hr_head_office", "hr_manager")
        )
        assert not (orig_hr.get("comments") or "").strip()
        assert not (s.form_data.get("hr_comments") or "").strip()

        emp_overlaid = overlay_preview_comment_on_form_data(s.form_data, emp, s, token)
        emp_hr = next(
            st
            for st in (emp_overlaid.get(MGMT_CHAIN_KEY) or {}).get("steps") or []
            if st.get("key") in ("hr_head_office", "hr_manager")
        )
        assert emp_overlaid.get("hr_comments") != token
        assert (emp_hr.get("comments") or "") != token

    hr_headers = _login_headers(client, hr.username)
    preview_text = _leave_pdf_text(
        client, sid, hr_headers, f"&preview_comment={token}"
    )
    assert token in preview_text

    stored_text = _leave_pdf_text(client, sid, hr_headers)
    assert token not in stored_text

    emp_preview = _leave_pdf_text(
        client, sid, emp_headers, f"&preview_comment={token}"
    )
    assert token not in emp_preview

    persist = client.post(
        f"/hr/api/mgmt-signoff/{sid}/sign",
        json={"signature": SIG, "comments": token},
        headers=hr_headers,
    )
    assert persist.status_code == 200, persist.get_json()
    saved_text = _leave_pdf_text(client, sid, hr_headers)
    assert token in saved_text

