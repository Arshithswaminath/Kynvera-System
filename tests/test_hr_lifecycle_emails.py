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
