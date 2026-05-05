"""
HR form workflow: submit → HR review/sign → GM final approval.
Also sanity-checks PDF output includes approval signatures in form_data.
"""
import uuid
from io import BytesIO

import pytest

SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def _login_headers(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _make_users(app, suffix):
    from app.models import db, User

    def u(username, **kw):
        user = User(
            username=f"{username}_{suffix}",
            email=f"{username}_{suffix}@test.example",
            full_name=username.replace("_", " ").title(),
            role=kw.pop("role", "user"),
            is_active=True,
            password_changed=True,
            **kw,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        return user

    with app.app_context():
        employee = u("emp")
        hr = u("hruser", access_hr=True)
        gm = u("gmuser", designation="general_manager")
        db.session.commit()
        eid, hid, gid = employee.id, hr.id, gm.id
    return eid, hid, gid, employee.username, hr.username, gm.username


@pytest.fixture
def hr_three_users(app):
    suffix = uuid.uuid4().hex[:8]
    return _make_users(app, suffix)


def test_hr_workflow_submit_hr_approve_gm_approve(client, app, hr_three_users):
    eid, hid, gid, emp_u, hr_u, gm_u = hr_three_users

    leave_payload = {
        "form_type": "leave_application",
        "employee_name": "Workflow Tester",
        "job_title": "Analyst",
        "today_date": "2026-04-09",
        "employee_id": "INJ-9999",
        "department": "QA",
        "date_of_joining": "2025-01-01",
        "mobile_no": "+971500000000",
        "last_leave_date": "2025-06-01",
        "leave_type": "annual",
        "total_days_requested": "3",
        "first_day_of_leave": "2026-04-15",
        "last_day_of_leave": "2026-04-17",
        "date_returning_to_work": "2026-04-18",
        "salary_advance": "no",
        "telephone_reachable": "+971500000000",
        "replacement_name": "Cover Person",
        "employee_signature": SIG,
        "replacement_signature": SIG,
    }

    h_emp = _login_headers(client, emp_u, "TestPass123!")
    h_hr = _login_headers(client, hr_u, "TestPass123!")
    h_gm = _login_headers(client, gm_u, "TestPass123!")

    sub_r = client.post("/hr/api/submit", json=leave_payload, headers=h_emp)
    assert sub_r.status_code == 200, sub_r.get_json()
    submission_id = sub_r.get_json()["submission_id"]

    from app.models import db, Submission

    with app.app_context():
        s = Submission.query.filter_by(submission_id=submission_id).first()
        assert s is not None
        assert s.workflow_status == "hr_review"
        assert s.user_id == eid

    bad_gm = client.post(
        f"/hr/api/gm-approve/{submission_id}",
        json={"signature": SIG, "comments": "too early"},
        headers=h_gm,
    )
    assert bad_gm.status_code == 400

    hr_r = client.post(
        f"/hr/api/hr-approve/{submission_id}",
        json={
            "signature": SIG,
            "comments": "HR ok",
            "form_data_hr": {
                "hr_checked": "yes",
                "hr_balance_cf": "10",
                "hr_contract_year": "2026",
                "hr_paid": "3",
                "hr_unpaid": "0",
                "hr_date": "2026-04-09",
            },
        },
        headers=h_hr,
    )
    assert hr_r.status_code == 200, hr_r.get_json()

    with app.app_context():
        s = Submission.query.filter_by(submission_id=submission_id).first()
        assert s.workflow_status == "gm_review"
        fd = s.form_data or {}
        assert fd.get("hr_signature") == SIG
        assert fd.get("hr_comments") == "HR ok"
        assert fd.get("hr_reviewed_by_id") == hid
        assert fd.get("hr_balance_cf") == "10"

    bad_hr_again = client.post(
        f"/hr/api/hr-approve/{submission_id}",
        json={"signature": SIG, "comments": "again"},
        headers=h_hr,
    )
    assert bad_hr_again.status_code == 400

    gm_r = client.post(
        f"/hr/api/gm-approve/{submission_id}",
        json={"signature": SIG, "comments": "GM approved"},
        headers=h_gm,
    )
    assert gm_r.status_code == 200, gm_r.get_json()

    with app.app_context():
        s = Submission.query.filter_by(submission_id=submission_id).first()
        assert s.workflow_status == "approved"
        assert s.status == "completed"
        fd = s.form_data or {}
        assert fd.get("gm_signature") == SIG
        assert fd.get("gm_comments") == "GM approved"
        assert fd.get("gm_approved_by_id") == gid

    buf = BytesIO()
    with app.app_context():
        s = Submission.query.filter_by(submission_id=submission_id).first()
        from module_hr.pdf_service import generate_hr_pdf

        ok, err = generate_hr_pdf(s, buf)
        assert ok, err
        assert len(buf.getvalue()) > 2000


def test_hr_permissions_endpoints(client, app, hr_three_users):
    _, _, _, emp_u, hr_u, gm_u = hr_three_users
    h_emp = _login_headers(client, emp_u, "TestPass123!")
    h_hr = _login_headers(client, hr_u, "TestPass123!")
    h_gm = _login_headers(client, gm_u, "TestPass123!")

    assert client.get("/hr/api/pending-hr-review", headers=h_emp).status_code == 403
    assert client.get("/hr/api/pending-hr-review", headers=h_hr).status_code == 200
    assert client.get("/hr/api/pending-gm-approval", headers=h_hr).status_code == 403
    assert client.get("/hr/api/pending-gm-approval", headers=h_gm).status_code == 200

    perms = client.get("/hr/api/user-permissions", headers=h_hr).get_json()
    assert perms["permissions"]["can_review_hr"] is True
    assert perms["permissions"]["can_approve_gm"] is False

    perms_gm = client.get("/hr/api/user-permissions", headers=h_gm).get_json()
    assert perms_gm["permissions"]["can_approve_gm"] is True
