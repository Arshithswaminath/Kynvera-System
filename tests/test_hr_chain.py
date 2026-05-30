"""
Unit tests for the fixed three-lane HR management approval chain.

Covers:

* Technician lane: supervisor (fixed) -> OM gate -> GM gate -> HR gate
* Supervisor lane: OM gate -> GM gate -> HR gate
* Office staff lane: GM gate -> HR gate
* Technician with no supervisor on profile -> setup_error
* UI context shape (Box 2 chain descriptor)
"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture()
def chain_users(app):
    """Create one user per role used by the chain. Cleaned up at the end."""
    from app.models import db, User

    created: list[int] = []

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
        sup = _mk(f"sup_{tag}", "supervisor")
        om = _mk(f"om_{tag}", "operations_manager")
        gm = _mk(f"gm_{tag}", "general_manager")
        hr = _mk(f"hr_{tag}", "hr_manager")
        tech = _mk(f"tech_{tag}", "technician", reporting_manager_id=sup.id)
        emp = _mk(f"emp_{tag}", "employee")
        db.session.commit()

        yield {
            "tech": tech,
            "sup": sup,
            "om": om,
            "gm": gm,
            "hr": hr,
            "emp": emp,
        }

        # Cleanup
        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                db.session.delete(obj)
        db.session.commit()


def _chain_keys(steps):
    return [s["key"] for s in steps]


def _chain_modes(steps):
    return [s["signer_mode"] for s in steps]


# ---------------------------------------------------------------------------
# Chain construction
# ---------------------------------------------------------------------------


def test_technician_lane_builds_full_chain(app, chain_users):
    """Technician -> supervisor (fixed) -> OM -> GM -> HR."""
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        lane_for_user,
    )

    with app.app_context():
        tech = chain_users["tech"]
        assert lane_for_user(tech) == "technician"

        steps, err = _build_chain_for_submitter(tech)
        assert err is None
        assert _chain_keys(steps) == [
            "supervisor",
            "operations_manager",
            "general_manager",
            "hr_head_office",
        ]
        assert _chain_modes(steps) == [
            "fixed_user",
            "designation",
            "designation",
            "designation",
        ]
        assert steps[0]["signer_id"] == chain_users["sup"].id
        assert steps[1]["designation_gate"] == "operations_manager"
        assert steps[2]["designation_gate"] == "general_manager"
        assert steps[3]["designation_gate"] == "hr_head_office"


def test_supervisor_lane_skips_supervisor_step(app, chain_users):
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        lane_for_user,
    )

    with app.app_context():
        sup = chain_users["sup"]
        assert lane_for_user(sup) == "supervisor"

        steps, err = _build_chain_for_submitter(sup)
        assert err is None
        assert _chain_keys(steps) == [
            "operations_manager",
            "general_manager",
            "hr_head_office",
        ]
        assert [s["signer_mode"] for s in steps] == [
            "designation",
            "designation",
            "designation",
        ]


def test_office_staff_lane_is_gm_then_hr(app, chain_users):
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        lane_for_user,
    )

    with app.app_context():
        emp = chain_users["emp"]
        assert lane_for_user(emp) == "office_staff"

        steps, err = _build_chain_for_submitter(emp)
        assert err is None
        assert _chain_keys(steps) == ["general_manager", "hr_head_office"]
        assert [s["signer_mode"] for s in steps] == ["designation", "designation"]


def test_other_designations_use_office_staff_lane(app, chain_users):
    """An OM/GM submitting their own form goes through GM -> HR (any other GM signs)."""
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        lane_for_user,
    )

    with app.app_context():
        for actor in (chain_users["om"], chain_users["gm"], chain_users["hr"]):
            assert lane_for_user(actor) == "office_staff"
            steps, err = _build_chain_for_submitter(actor)
            assert err is None
            assert _chain_keys(steps) == ["general_manager", "hr_head_office"]


def test_technician_missing_supervisor_returns_setup_error(app, chain_users):
    from app.models import db, User
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        init_management_chain_on_submit,
    )

    with app.app_context():
        tech = chain_users["tech"]
        # Clear the supervisor on this technician's profile.
        live = db.session.get(User, tech.id)
        live.reporting_manager_id = None
        db.session.commit()

        steps, err = _build_chain_for_submitter(live)
        assert steps == []
        assert err and "supervisor" in err.lower()

        # init_management_chain_on_submit surfaces the same error to callers.
        payload: dict = {}
        msg = init_management_chain_on_submit(payload, live)
        assert msg == err
        assert "hr_mgmt_chain" not in payload


def test_technician_with_non_supervisor_rm_is_rejected(app, chain_users):
    """If the assigned RM is not a Supervisor, technicians cannot submit."""
    from app.models import db, User
    from module_hr.hr_management_chain import _build_chain_for_submitter

    with app.app_context():
        tech = chain_users["tech"]
        live = db.session.get(User, tech.id)
        # Point the technician at an employee instead of a supervisor.
        live.reporting_manager_id = chain_users["emp"].id
        db.session.commit()

        steps, err = _build_chain_for_submitter(live)
        assert steps == []
        assert err and "supervisor" in err.lower()


# ---------------------------------------------------------------------------
# UI context (Box 2 chain descriptor)
# ---------------------------------------------------------------------------


def test_ui_context_technician_descriptor(app, chain_users):
    from module_hr.hr_management_chain import get_mgmt_chain_ui_context

    with app.app_context():
        ctx = get_mgmt_chain_ui_context(chain_users["tech"])
        assert ctx["success"] is True
        assert ctx["lane"] == "technician"
        assert ctx["setup_error"] is None
        assert ctx["lane_flow"].startswith("Immediate supervisor")

        roles = [c["role_label"] for c in ctx["chain"]]
        assert roles == [
            "Immediate supervisor",
            "Operations manager",
            "General manager",
            "HR (head office)",
        ]

        sup_row = ctx["chain"][0]
        assert sup_row["signer_mode"] == "fixed_user"
        assert sup_row["signer_id"] == chain_users["sup"].id
        assert sup_row["who_label"] == (
            chain_users["sup"].full_name or chain_users["sup"].username
        )
        assert sup_row["missing"] is False

        hr_row = ctx["chain"][3]
        assert hr_row["signer_mode"] == "designation"
        assert hr_row["missing"] is False


def test_ui_context_office_staff_descriptor(app, chain_users):
    from module_hr.hr_management_chain import get_mgmt_chain_ui_context

    with app.app_context():
        ctx = get_mgmt_chain_ui_context(chain_users["emp"])
        assert ctx["lane"] == "office_staff"
        assert [c["key"] for c in ctx["chain"]] == ["general_manager", "hr_head_office"]
        # GM pool is populated by the fixture's gm user — should not be flagged missing.
        gm_row = ctx["chain"][0]
        assert gm_row["missing"] is False


def test_ui_context_flags_setup_error_for_technician_without_supervisor(app, chain_users):
    from app.models import db, User
    from module_hr.hr_management_chain import get_mgmt_chain_ui_context

    with app.app_context():
        live = db.session.get(User, chain_users["tech"].id)
        live.reporting_manager_id = None
        db.session.commit()

        ctx = get_mgmt_chain_ui_context(live)
        assert ctx["success"] is True
        assert ctx["lane"] == "technician"
        assert ctx["setup_error"]
        assert ctx["chain"] == []
        assert ctx["supervisor"] is not None
        assert ctx["supervisor"]["assigned"] is False


def test_access_hr_user_can_sign_hr_mgmt_step(app, chain_users):
    from app.models import db, User
    from module_hr.hr_management_chain import user_allowed_to_sign_step, _step, WF_MGMT_HR

    with app.app_context():
        tag = chain_users["tech"].username.split("_")[-1]
        hr_staff = User(
            username=f"hrstaff_{tag}",
            email=f"hrstaff_{tag}@example.com",
            full_name="HR Staff",
            role="user",
            designation="employee",
            is_active=True,
            password_changed=True,
            access_hr=True,
        )
        hr_staff.set_password("TestPass123")
        db.session.add(hr_staff)
        db.session.commit()

        step = _step(
            "hr_head_office",
            WF_MGMT_HR,
            "HR (head office)",
            signer_mode="designation",
            designation_gate="hr_head_office",
        )
        assert user_allowed_to_sign_step(chain_users["hr"], step) is True
        assert user_allowed_to_sign_step(hr_staff, step) is True
        assert user_allowed_to_sign_step(chain_users["tech"], step) is False

        db.session.delete(hr_staff)
        db.session.commit()


def test_canonical_hr_prefers_named_account_over_seed_login(app, chain_users):
    """Mona (real HR manager) wins over the legacy ``hr_manager`` bootstrap user."""
    from app.models import db, User
    from module_hr.hr_management_chain import _canonical_hr_user

    with app.app_context():
        tag = chain_users["hr"].username.split("_")[-1]
        seed = chain_users["hr"]
        mona = User(
            username=f"Mona_{tag}",
            email=f"mona_{tag}@example.com",
            full_name="Mona",
            role="user",
            designation="hr_manager",
            is_active=True,
            password_changed=True,
            access_hr=True,
        )
        mona.set_password("TestPass123")
        db.session.add(mona)
        db.session.commit()

        canonical = _canonical_hr_user()
        assert canonical is not None
        assert canonical.id == mona.id
        assert canonical.full_name == "Mona"

        db.session.delete(mona)
        db.session.commit()
        assert _canonical_hr_user().id == seed.id


def test_mgmt_chain_participant_includes_assigned_supervisor_and_past_signers(app, chain_users):
    from module_hr.hr_management_chain import (
        MGMT_CHAIN_KEY,
        init_management_chain_on_submit,
        user_is_mgmt_chain_participant,
    )

    with app.app_context():
        tech = chain_users["tech"]
        sup = chain_users["sup"]
        om = chain_users["om"]
        payload: dict = {"employee_name": "Tech User"}
        assert init_management_chain_on_submit(payload, tech) is None
        chain = payload[MGMT_CHAIN_KEY]
        chain["steps"][0]["signature"] = "data:image/png;base64,abc"
        chain["steps"][0]["signed_by_id"] = sup.id
        chain["current_index"] = 1

        assert user_is_mgmt_chain_participant(sup, payload) is True
        assert user_is_mgmt_chain_participant(om, payload) is True
        assert user_is_mgmt_chain_participant(tech, payload) is False


def test_user_mgmt_chain_completed_step(app, chain_users):
    from module_hr.hr_management_chain import (
        MGMT_CHAIN_KEY,
        init_management_chain_on_submit,
        user_mgmt_chain_completed_step,
    )

    with app.app_context():
        tech = chain_users["tech"]
        sup = chain_users["sup"]
        payload: dict = {"employee_name": "Tech User"}
        assert init_management_chain_on_submit(payload, tech) is None
        step = payload[MGMT_CHAIN_KEY]["steps"][0]
        step["signature"] = "data:image/png;base64,abc"
        step["signed_at"] = "2026-05-27T12:00:00Z"
        step["signed_by_id"] = sup.id
        step["signed_by_name"] = sup.full_name

        found = user_mgmt_chain_completed_step(sup, payload)
        assert found is not None
        assert found.get("pdf_label") == "Immediate supervisor"
        assert user_mgmt_chain_completed_step(chain_users["om"], payload) is None


def test_can_access_hr_submission_export_for_mgmt_chain_supervisor(app, chain_users):
    from app.models import Submission
    from module_hr.routes import _can_access_hr_submission_export
    from module_hr.hr_management_chain import init_management_chain_on_submit, WF_MGMT_SUP

    with app.app_context():
        tech = chain_users["tech"]
        sup = chain_users["sup"]
        payload: dict = {"employee_name": "Tech User"}
        assert init_management_chain_on_submit(payload, tech) is None
        submission = Submission(
            submission_id=f"HR-COMMENCEMENT-{uuid.uuid4().hex[:8].upper()}",
            user_id=tech.id,
            module_type="hr_commencement",
            site_name="Tech User",
            status="submitted",
            workflow_status=WF_MGMT_SUP,
            form_data=payload,
        )
        assert _can_access_hr_submission_export(sup, submission) is True
        assert _can_access_hr_submission_export(chain_users["emp"], submission) is False
