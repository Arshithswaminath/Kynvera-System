"""
Critical: generic HR update / form_data_hr must not wipe or forge approval trails.
"""
from __future__ import annotations

import copy
import uuid
from datetime import timedelta

import pytest

SIG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_filter_form_data_hr_fields_blocks_trail_and_identity():
    from module_hr.hr_management_chain import filter_form_data_hr_fields

    cleaned = filter_form_data_hr_fields(
        {
            "hr_balance_cf": "5",
            "hr_paid": "3",
            "hr_mgmt_chain": {"v": 1, "steps": []},
            "hr_signature": SIG,
            "hr_reviewed_by_id": 999,
            "hr_reviewed_by_name": "Forged",
            "hr_reviewed_at": "2020-01-01T00:00:00Z",
            "hr_comments": "should not overwrite step comments",
            "_routed_signoffs": {"v": 1, "slots": []},
            "gm_signature": SIG,
        }
    )
    assert cleaned == {"hr_balance_cf": "5", "hr_paid": "3"}


def test_enforce_hr_record_fields_restores_routed_and_chain(app):
    from app.models import Submission, User, db
    from app.workflow.routes import _enforce_hr_record_fields_in_form_data
    from common.datetime_utils import utc_now_naive

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        emp = User(
            username=f"trail_emp_{tag}",
            email=f"trail_emp_{tag}@example.com",
            full_name="Trail Emp",
            role="user",
            is_active=True,
            password_changed=True,
        )
        emp.set_password("TestPass123!")
        db.session.add(emp)
        db.session.flush()

        stored = {
            "employee_name": "Trail Emp",
            "leave_type": "annual",
            "_routed_signoffs": {
                "v": 1,
                "slots": [
                    {
                        "key": "replacement",
                        "label": "Replacement",
                        "signature": SIG,
                        "signed_by_id": 42,
                    }
                ],
            },
            "hr_mgmt_chain": {
                "v": 1,
                "current_index": 0,
                "steps": [{"key": "general_manager", "wf": "hr_mgmt_gm", "signature": None}],
            },
            "gm_signature": SIG,
            "replacement_signers": [{"user_id": 7, "signature": SIG}],
        }
        sub = Submission(
            submission_id=f"HR-TRAIL-{tag}",
            user_id=emp.id,
            module_type="hr_leave_application",
            status="submitted",
            workflow_status="hr_mgmt_gm",
            form_data=copy.deepcopy(stored),
            created_at=utc_now_naive(),
        )
        db.session.add(sub)
        db.session.commit()

        payload = {
            "employee_name": "Trail Emp edited",
            "leave_type": "annual",
            "_routed_signoffs": None,
            "hr_mgmt_chain": {"v": 1, "current_index": 0, "steps": []},
            "gm_signature": "",
            "replacement_signers": [],
        }
        out = _enforce_hr_record_fields_in_form_data(emp, sub, payload)

        assert out["employee_name"] == "Trail Emp edited"
        assert out["_routed_signoffs"]["slots"][0]["signature"] == SIG
        assert out["hr_mgmt_chain"]["steps"][0]["key"] == "general_manager"
        assert out["gm_signature"] == SIG
        assert out["replacement_signers"][0]["user_id"] == 7

        db.session.delete(sub)
        db.session.delete(emp)
        db.session.commit()


def test_update_submission_cannot_wipe_routed_signoffs(client, app):
    from app.models import Submission, User, db
    from common.datetime_utils import utc_now_naive

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        emp = User(
            username=f"upd_emp_{tag}",
            email=f"upd_emp_{tag}@example.com",
            full_name="Update Emp",
            role="user",
            designation="employee",
            is_active=True,
            password_changed=True,
        )
        emp.set_password("TestPass123!")
        db.session.add(emp)
        db.session.flush()

        sub = Submission(
            submission_id=f"HR-UPD-{tag}",
            user_id=emp.id,
            module_type="hr_leave_application",
            status="submitted",
            workflow_status="hr_mgmt_gm",
            form_data={
                "employee_name": "Update Emp",
                "_routed_signoffs": {
                    "v": 1,
                    "slots": [{"key": "replacement", "signature": SIG, "signed_by_name": "Cover"}],
                },
                "hr_mgmt_chain": {
                    "v": 1,
                    "current_index": 0,
                    "steps": [{"key": "general_manager", "wf": "hr_mgmt_gm"}],
                },
            },
            created_at=utc_now_naive() - timedelta(minutes=5),
        )
        db.session.add(sub)
        db.session.commit()
        sid = sub.submission_id
        emp_name = emp.username

    login = client.post(
        "/api/auth/login", json={"username": emp_name, "password": "TestPass123!"}
    )
    assert login.status_code == 200, login.get_json()
    token = login.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.put(
        f"/api/workflow/submissions/{sid}/update",
        json={
            "form_data_updates": {
                "employee_name": "Still Update Emp",
                "_routed_signoffs": {"v": 1, "slots": []},
                "hr_mgmt_chain": {"hacked": True},
            }
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        row = Submission.query.filter_by(submission_id=sid).first()
        assert row is not None
        fd = row.form_data
        assert fd["employee_name"] == "Still Update Emp"
        assert fd["_routed_signoffs"]["slots"][0]["signature"] == SIG
        assert fd["hr_mgmt_chain"]["steps"][0]["key"] == "general_manager"
        db.session.delete(row)
        emp_row = User.query.filter_by(username=emp_name).first()
        if emp_row:
            db.session.delete(emp_row)
        db.session.commit()


def test_reject_management_requires_workflow_step_match(app):
    from app.models import Submission, User, db
    from module_hr.hr_management_chain import reject_management_submission

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        gm = User(
            username=f"rej_gm_{tag}",
            email=f"rej_gm_{tag}@example.com",
            full_name="Reject GM",
            role="user",
            designation="general_manager",
            is_active=True,
            password_changed=True,
        )
        gm.set_password("TestPass123!")
        db.session.add(gm)
        db.session.flush()

        sub = Submission(
            submission_id=f"HR-REJ-{tag}",
            user_id=gm.id,
            module_type="hr_leave_application",
            status="submitted",
            # Status says GM step, but current_index points at a different step.wf
            workflow_status="hr_mgmt_gm",
            form_data={
                "hr_mgmt_chain": {
                    "v": 1,
                    "current_index": 0,
                    "steps": [
                        {
                            "key": "hr_head_office",
                            "wf": "hr_mgmt_hr_head_office",
                            "signer_mode": "pool",
                            "pool_designation": "hr_manager",
                            "signature": None,
                        }
                    ],
                }
            },
        )
        db.session.add(sub)
        db.session.commit()

        ok, err = reject_management_submission(sub, gm, "nope")
        assert ok is False
        assert "mismatch" in (err or "").lower()

        db.session.delete(sub)
        db.session.delete(gm)
        db.session.commit()


def test_apply_management_signature_form_data_hr_cannot_wipe_chain(app):
    from app.models import Submission, User, db
    from module_hr.hr_management_chain import apply_management_signature

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        hr = User(
            username=f"hr_final_{tag}",
            email=f"hr_final_{tag}@example.com",
            full_name="HR Final",
            role="user",
            designation="hr_manager",
            is_active=True,
            password_changed=True,
        )
        hr.set_password("TestPass123!")
        db.session.add(hr)
        db.session.flush()

        chain = {
            "v": 1,
            "current_index": 0,
            "steps": [
                {
                    "key": "hr_head_office",
                    "wf": "hr_mgmt_hr_head_office",
                    "signer_mode": "pool",
                    "designation_gate": "hr_head_office",
                    "pdf_label": "HR",
                    "signature": None,
                }
            ],
        }
        sub = Submission(
            submission_id=f"HR-FDHR-{tag}",
            user_id=hr.id,
            module_type="hr_leave_application",
            status="submitted",
            workflow_status="hr_mgmt_hr_head_office",
            form_data={
                "hr_mgmt_chain": copy.deepcopy(chain),
                "_routed_signoffs": {"v": 1, "slots": [{"signature": SIG}]},
            },
        )
        db.session.add(sub)
        db.session.commit()

        ok, err = apply_management_signature(
            sub,
            hr,
            SIG,
            "ok",
            form_data_hr={
                "hr_balance_cf": "2",
                "hr_mgmt_chain": {"v": 1, "steps": []},
                "_routed_signoffs": None,
                "hr_reviewed_by_id": 1,
            },
        )
        assert ok is True, err
        fd = sub.form_data
        assert fd["hr_balance_cf"] == "2"
        assert fd["hr_mgmt_chain"]["steps"][0]["signature"] == SIG
        assert fd["_routed_signoffs"]["slots"][0]["signature"] == SIG
        assert fd["hr_reviewed_by_id"] == hr.id

        db.session.delete(sub)
        db.session.delete(hr)
        db.session.commit()
