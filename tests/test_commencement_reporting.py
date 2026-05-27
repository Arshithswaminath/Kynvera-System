"""Tests for commencement Reporting To signature routing."""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture()
def commencement_users(app):
    from app.models import db, User

    created: list[int] = []

    def _mk(username, designation, *, reporting_manager_id=None):
        u = User(
            username=username,
            email=f"{username}@example.com",
            full_name=username.replace("_", " ").title(),
            role="user",
            designation=designation,
            is_active=True,
            password_changed=True,
            reporting_manager_id=reporting_manager_id,
        )
        u.set_password("TestPass123")
        db.session.add(u)
        db.session.flush()
        created.append(u.id)
        return u

    with app.app_context():
        tag = uuid.uuid4().hex[:6]
        sup = _mk(f"csup_{tag}", "supervisor")
        gm = _mk(f"cgm_{tag}", "general_manager")
        emp = _mk(f"cemp_{tag}", "employee")
        outsider = _mk(f"cout_{tag}", "supervisor")
        db.session.commit()
        yield {"sup": sup, "gm": gm, "emp": emp, "outsider": outsider}
        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                db.session.delete(obj)
        db.session.commit()


def _base_commencement_payload(rt_user_id: int) -> dict:
    return {
        "form_type": "commencement",
        "employee_name": "Test Employee",
        "position": "Clerk",
        "contacts": "0500000000",
        "department": "Admin",
        "organization": "INJAAZ",
        "date_of_joining": "2026-05-01",
        "bank_name": "Test Bank",
        "account_number": "123456",
        "reporting_to_signer_id": rt_user_id,
        "reporting_to_name": "Manager",
        "reporting_to_designation": "GM",
        "reporting_to_contact": "0501111111",
        "employee_signature": "data:image/png;base64,iVBORw0KGgo=",
        "employee_sign_date": "2026-05-27",
    }


def test_reporting_to_dual_role_when_gm_in_chain(app, commencement_users):
    from module_hr.hr_commencement_reporting import REPORTING_TO_SIGNOFF_KEY, resolve_commencement_reporting_to
    from module_hr.hr_management_chain import init_management_chain_on_submit

    with app.app_context():
        emp = commencement_users["emp"]
        gm = commencement_users["gm"]
        data = _base_commencement_payload(gm.id)
        assert init_management_chain_on_submit(data, emp) is None

        block, err, meta = resolve_commencement_reporting_to(data, emp)
        assert err is None
        assert block is None
        assert meta["mode"] == "dual_role"
        assert meta["user_id"] == gm.id
        assert data[REPORTING_TO_SIGNOFF_KEY]["chain_step_key"] == "general_manager"


def test_reporting_to_pre_chain_when_outside_chain(app, commencement_users):
    from module_hr.hr_commencement_reporting import REPORTING_TO_SIGNOFF_KEY, resolve_commencement_reporting_to
    from module_hr.hr_management_chain import init_management_chain_on_submit

    with app.app_context():
        emp = commencement_users["emp"]
        outsider = commencement_users["outsider"]
        data = _base_commencement_payload(outsider.id)
        assert init_management_chain_on_submit(data, emp) is None

        block, err, meta = resolve_commencement_reporting_to(data, emp)
        assert err is None
        assert meta["mode"] == "pre_chain"
        assert block is not None
        assert block["slots"][0]["key"] == "reporting_to"
        assert block["slots"][0]["signers"][0]["user_id"] == outsider.id
        assert data[REPORTING_TO_SIGNOFF_KEY]["mode"] == "pre_chain"


def test_dual_role_mirror_on_mgmt_sign(app, commencement_users):
    from module_hr.hr_commencement_reporting import (
        REPORTING_TO_SIGNOFF_KEY,
        apply_dual_role_reporting_to_mirror,
    )

    with app.app_context():
        gm = commencement_users["gm"]
        fd = {
            REPORTING_TO_SIGNOFF_KEY: {
                "mode": "dual_role",
                "user_id": gm.id,
                "chain_step_key": "general_manager",
            }
        }
        step = {
            "key": "general_manager",
            "signature": "data:image/png;base64,abc",
            "signed_at": "2026-05-27T10:00:00Z",
        }
        apply_dual_role_reporting_to_mirror(fd, gm, step)
        assert fd["reporting_to_signature"] == step["signature"]
        assert fd["reporting_sign_date"] == "2026-05-27"
