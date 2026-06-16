"""Interview assessment: deferred routing until interviewer signs."""
from __future__ import annotations

import uuid

import pytest

SIG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def interview_routing_users(app):
    from app.models import User, db

    tag = uuid.uuid4().hex[:6]
    created: list[int] = []

    def _add(**kwargs):
        u = User(is_active=True, password_changed=True, **kwargs)
        u.set_password("TestPass123")
        db.session.add(u)
        db.session.flush()
        created.append(u.id)
        return u

    with app.app_context():
        submitter = _add(
            username=f"iv_sub_{tag}",
            email=f"iv_sub_{tag}@example.com",
            full_name="Interview Submitter",
            role="user",
            designation="employee",
        )
        interviewer = _add(
            username=f"iv_int_{tag}",
            email=f"iv_int_{tag}@example.com",
            full_name="Interview Conductor",
            role="user",
            designation="employee",
        )
        next_approver = _add(
            username=f"iv_next_{tag}",
            email=f"iv_next_{tag}@example.com",
            full_name="Next Approver Colleague",
            role="user",
            designation="employee",
        )
        db.session.commit()

        users = {
            "submitter": submitter,
            "interviewer": interviewer,
            "next_approver": next_approver,
        }
        yield users

        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                db.session.delete(obj)
        db.session.commit()


def _auth_headers(client, username: str, password: str = "TestPass123") -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    token = r.get_json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _submit_interview(client, headers, interviewer_id: int) -> str:
    body = {
        "form_type": "interview_assessment",
        "candidate_name": "Candidate One",
        "position_title": "Coordinator",
        "interview_date": "2026-06-16",
        "interview_by": "HR Team",
        "rating_overall": "good",
        "eligibility": "yes",
        "interviewer_signer_ids": [interviewer_id],
    }
    r = client.post("/hr/api/submit", json=body, headers=headers)
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j.get("success") is True
    sid = j.get("submission_id")
    assert sid
    assert j.get("workflow_status") == "replacement_signoff"
    return sid


def test_interview_submit_defers_mgmt_chain(app, client, interview_routing_users):
    users = interview_routing_users
    headers = _auth_headers(client, users["submitter"].username)
    sid = _submit_interview(client, headers, users["interviewer"].id)

    with app.app_context():
        from app.models import Submission

        sub = Submission.query.filter_by(submission_id=sid).first()
        assert sub is not None
        fd = sub.form_data or {}
        assert "hr_mgmt_chain" not in fd
        assert fd.get("interview_routing", {}).get("deferred") is True
        assert sub.workflow_status == "replacement_signoff"


def test_interview_sign_requires_next_approver(app, client, interview_routing_users):
    users = interview_routing_users
    sub_headers = _auth_headers(client, users["submitter"].username)
    sid = _submit_interview(client, sub_headers, users["interviewer"].id)

    int_headers = _auth_headers(client, users["interviewer"].username)
    r = client.post(
        f"/hr/api/replacement-signoff/{sid}/sign",
        json={"signature": SIG_DATA_URL},
        headers=int_headers,
    )
    assert r.status_code == 400
    assert "forward" in (r.get_json().get("error") or "").lower()


def test_interview_sign_builds_chain_and_advances(app, client, interview_routing_users):
    users = interview_routing_users
    sub_headers = _auth_headers(client, users["submitter"].username)
    sid = _submit_interview(client, sub_headers, users["interviewer"].id)

    int_headers = _auth_headers(client, users["interviewer"].username)
    r = client.post(
        f"/hr/api/replacement-signoff/{sid}/sign",
        json={
            "signature": SIG_DATA_URL,
            "next_approver_signer_id": users["next_approver"].id,
        },
        headers=int_headers,
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j.get("success") is True
    assert j.get("advanced_to_hr_review") is True

    with app.app_context():
        from app.models import Submission
        from module_hr.hr_management_chain import WF_MGMT_GM, WF_MGMT_HR, WF_MGMT_ROUTING

        sub = Submission.query.filter_by(submission_id=sid).first()
        fd = sub.form_data or {}
        assert fd.get("interviewer_signature", "").startswith("data:image")
        assert fd.get("next_approver_signer_id") == users["next_approver"].id
        chain = fd.get("hr_mgmt_chain") or {}
        steps = chain.get("steps") or []
        assert len(steps) == 3
        assert steps[0]["key"] == "routing_approver"
        assert steps[0]["wf"] == WF_MGMT_ROUTING
        assert steps[0]["signer_id"] == users["next_approver"].id
        assert steps[1]["wf"] == WF_MGMT_GM
        assert steps[2]["wf"] == WF_MGMT_HR
        assert sub.workflow_status == WF_MGMT_ROUTING
        assert fd.get("interview_routing", {}).get("deferred") is False


def test_interview_cannot_forward_to_self_or_submitter(app, client, interview_routing_users):
    users = interview_routing_users
    sub_headers = _auth_headers(client, users["submitter"].username)
    sid = _submit_interview(client, sub_headers, users["interviewer"].id)
    int_headers = _auth_headers(client, users["interviewer"].username)

    r_self = client.post(
        f"/hr/api/replacement-signoff/{sid}/sign",
        json={"signature": SIG_DATA_URL, "next_approver_signer_id": users["interviewer"].id},
        headers=int_headers,
    )
    assert r_self.status_code == 400

    r_sub = client.post(
        f"/hr/api/replacement-signoff/{sid}/sign",
        json={"signature": SIG_DATA_URL, "next_approver_signer_id": users["submitter"].id},
        headers=int_headers,
    )
    assert r_sub.status_code == 400
