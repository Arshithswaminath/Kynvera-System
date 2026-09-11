"""
Unit tests for the fixed three-lane HR management approval chain.

Covers:

* Technician lane: supervisor (fixed) -> OM gate -> GM gate -> HR gate
* Supervisor lane: OM gate -> GM gate -> HR gate
* Office staff lane: GM gate -> HR gate (plus reporting manager when assigned)
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
        ids = {
            "tech": tech.id,
            "sup": sup.id,
            "om": om.id,
            "gm": gm.id,
            "hr": hr.id,
            "emp": emp.id,
        }

        yield {key: db.session.get(User, uid) for key, uid in ids.items()}

        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                obj.reporting_manager_id = None
        db.session.commit()
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
        assert steps[1]["pdf_label"] == "HR"


def test_mgmt_step_display_label_uses_hr_not_head_office():
    from module_hr.hr_management_chain import mgmt_step_display_label

    assert mgmt_step_display_label({"key": "hr_head_office", "pdf_label": "HR (head office)"}) == "HR"
    assert mgmt_step_display_label({"pdf_label": "HR head office"}) == "HR"
    assert mgmt_step_display_label({"pdf_label": "General manager"}) == "General manager"


def test_gm_without_reporting_manager_skips_self_and_lists_admin_as_hr(app, chain_users):
    """A GM with no reporting manager must not sign their own form; HR falls back to admin."""
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        _supervisor_for,
        get_mgmt_chain_ui_context,
        lane_for_user,
    )

    with app.app_context():
        gm = chain_users["gm"]
        assert lane_for_user(gm) == "office_staff"
        assert _supervisor_for(gm) is None

        steps, err = _build_chain_for_submitter(gm)
        assert err is None
        assert _chain_keys(steps) == ["hr_head_office"]

        ctx = get_mgmt_chain_ui_context(gm)
        assert [c["key"] for c in ctx["chain"]] == ["hr_head_office"]
        hr_row = ctx["chain"][0]
        assert hr_row["who_label"]
        assert hr_row["key"] == "hr_head_office"
        assert hr_row["role_label"] == "HR"


def test_canonical_hr_falls_back_to_admin_when_no_hr_manager(app, chain_users):
    from app.models import db, User
    from module_hr.hr_management_chain import _canonical_hr_user

    with app.app_context():
        hr = db.session.get(User, chain_users["hr"].id)
        previous = hr.designation
        hr.designation = "employee"
        db.session.commit()
        try:
            canonical = _canonical_hr_user()
            assert canonical is not None
            assert canonical.role == "admin"
        finally:
            hr.designation = previous
            db.session.commit()


def test_office_staff_with_reporting_manager_lists_them_separately(app, chain_users):
    """Reporting manager is its own step; they are not also listed under GM."""
    from app.models import db, User
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        get_mgmt_chain_ui_context,
        user_allowed_to_sign_step,
    )

    with app.app_context():
        emp = db.session.get(User, chain_users["emp"].id)
        gm = chain_users["gm"]
        emp.reporting_manager_id = gm.id
        db.session.commit()

        steps, err = _build_chain_for_submitter(emp)
        assert err is None
        assert _chain_keys(steps) == ["reporting_manager", "hr_head_office"]
        assert steps[0]["signer_id"] == gm.id

        ctx = get_mgmt_chain_ui_context(emp)
        assert [c["key"] for c in ctx["chain"]] == ["reporting_manager", "hr_head_office"]
        assert ctx["chain"][0]["who_label"] == (gm.full_name or gm.username)
        assert ctx["lane_flow"].startswith("Reporting manager")


def test_office_staff_reporting_manager_excluded_from_gm_pool(app, chain_users):
    from app.models import db, User
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        get_mgmt_chain_ui_context,
        user_allowed_to_sign_step,
    )

    with app.app_context():
        tag = uuid.uuid4().hex[:6]
        other_gm = User(
            username=f"gm2_{tag}",
            email=f"gm2_{tag}@example.com",
            full_name="Other GM",
            role="user",
            designation="general_manager",
            is_active=True,
            password_changed=True,
        )
        other_gm.set_password("TestPass123")
        db.session.add(other_gm)
        db.session.flush()

        emp = db.session.get(User, chain_users["emp"].id)
        rm = chain_users["gm"]
        emp.reporting_manager_id = rm.id
        db.session.commit()

        steps, err = _build_chain_for_submitter(emp)
        assert err is None
        assert _chain_keys(steps) == [
            "reporting_manager",
            "general_manager",
            "hr_head_office",
        ]
        gm_step = steps[1]
        assert rm.id in (gm_step.get("exclude_signer_ids") or [])
        assert user_allowed_to_sign_step(rm, gm_step) is False
        assert user_allowed_to_sign_step(other_gm, gm_step) is True

        ctx = get_mgmt_chain_ui_context(emp)
        gm_row = next(c for c in ctx["chain"] if c["key"] == "general_manager")
        assert "Other GM" in gm_row["who_label"]
        assert (rm.full_name or rm.username) not in gm_row["who_label"]
        assert "Either may sign" not in (gm_row.get("who_detail") or "")

        db.session.delete(other_gm)
        db.session.commit()


def test_other_designations_use_office_staff_lane(app, chain_users):
    """OM/HR submitting still go through the GM pool; a GM cannot sign their own form."""
    from module_hr.hr_management_chain import (
        _build_chain_for_submitter,
        lane_for_user,
    )

    with app.app_context():
        for actor in (chain_users["om"], chain_users["gm"], chain_users["hr"]):
            assert lane_for_user(actor) == "office_staff"
            steps, err = _build_chain_for_submitter(actor)
            assert err is None
            if actor.id == chain_users["gm"].id:
                assert _chain_keys(steps) == ["hr_head_office"]
            else:
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
        from app.models import db, User

        tech = db.session.get(User, chain_users["tech"].id)
        ctx = get_mgmt_chain_ui_context(tech)
        assert ctx["success"] is True
        assert ctx["lane"] == "technician"
        assert ctx["setup_error"] is None
        assert ctx["lane_flow"].startswith("Immediate supervisor")

        roles = [c["role_label"] for c in ctx["chain"]]
        assert roles == [
            "Immediate supervisor",
            "Operations manager",
            "General manager",
            "HR",
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


def test_access_hr_user_cannot_sign_hr_mgmt_step(app, chain_users):
    """Module access is not HR signing authority."""
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
            "HR",
            signer_mode="designation",
            designation_gate="hr_head_office",
        )
        assert user_allowed_to_sign_step(chain_users["hr"], step) is True
        assert user_allowed_to_sign_step(hr_staff, step) is False
        assert user_allowed_to_sign_step(chain_users["tech"], step) is False

        db.session.delete(hr_staff)
        db.session.commit()


def test_submitter_cannot_sign_own_hr_mgmt_step(app, chain_users):
    from module_hr.hr_management_chain import user_allowed_to_sign_step, _step, WF_MGMT_HR

    with app.app_context():
        hr = chain_users["hr"]
        step = _step(
            "hr_head_office",
            WF_MGMT_HR,
            "HR",
            signer_mode="designation",
            designation_gate="hr_head_office",
        )
        assert user_allowed_to_sign_step(hr, step) is True
        assert user_allowed_to_sign_step(hr, step, submitter_id=hr.id) is False
        assert user_allowed_to_sign_step(hr, step, submitter_id=chain_users["emp"].id) is True


def test_admin_cannot_sign_own_hr_mgmt_step(app, chain_users):
    from app.models import db, User
    from module_hr.hr_management_chain import user_allowed_to_sign_step, _step, WF_MGMT_HR

    with app.app_context():
        admin = User(
            username=f"adm_{uuid.uuid4().hex[:6]}",
            email="adm-own@example.com",
            full_name="Admin Submitter",
            role="admin",
            is_active=True,
            password_changed=True,
        )
        admin.set_password("TestPass123")
        db.session.add(admin)
        db.session.flush()
        step = _step(
            "hr_head_office",
            WF_MGMT_HR,
            "HR",
            signer_mode="designation",
            designation_gate="hr_head_office",
        )
        assert user_allowed_to_sign_step(admin, step) is True
        assert user_allowed_to_sign_step(admin, step, submitter_id=admin.id) is False
        assert user_allowed_to_sign_step(admin, step, submitter_id=chain_users["emp"].id) is True
        db.session.delete(admin)
        db.session.commit()


def test_gm_cannot_sign_hr_mgmt_step(app, chain_users):
    from module_hr.hr_management_chain import user_allowed_to_sign_step, _step, WF_MGMT_HR

    with app.app_context():
        step = _step(
            "hr_head_office",
            WF_MGMT_HR,
            "HR",
            signer_mode="designation",
            designation_gate="hr_head_office",
        )
        assert user_allowed_to_sign_step(chain_users["gm"], step) is False
        assert user_allowed_to_sign_step(chain_users["hr"], step) is True


def test_prior_signer_cannot_sign_later_hr_step(app, chain_users):
    from module_hr.hr_management_chain import (
        MGMT_CHAIN_KEY,
        WF_MGMT_HR,
        init_management_chain_on_submit,
        pending_management_step_for_user,
    )

    with app.app_context():
        emp = chain_users["emp"]
        gm = chain_users["gm"]
        hr = chain_users["hr"]
        payload = {"employee_name": "Emp", "submitted_by_id": emp.id}
        assert init_management_chain_on_submit(payload, emp) is None
        block = payload[MGMT_CHAIN_KEY]
        gm_step = block["steps"][0]
        assert gm_step["key"] == "general_manager"
        gm_step["signature"] = "data:image/png;base64,x"
        gm_step["signed_by_id"] = gm.id
        block["current_index"] = 1
        assert pending_management_step_for_user(
            payload, WF_MGMT_HR, gm, submitter_id=emp.id
        ) is None
        assert pending_management_step_for_user(
            payload, WF_MGMT_HR, hr, submitter_id=emp.id
        ) is not None


def test_apply_management_signature_refuses_submitter(app, chain_users):
    from app.models import db, Submission
    from module_hr.hr_management_chain import (
        MGMT_CHAIN_KEY,
        WF_MGMT_HR,
        apply_management_signature,
        init_management_chain_on_submit,
    )

    sig = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    with app.app_context():
        hr = chain_users["hr"]
        payload = {"employee_name": "HR Self", "submitted_by_id": hr.id}
        assert init_management_chain_on_submit(payload, hr) is None
        block = payload[MGMT_CHAIN_KEY]
        steps = block["steps"]
        hr_idx = next(i for i, s in enumerate(steps) if s["key"] == "hr_head_office")
        block["current_index"] = hr_idx
        sub = Submission(
            submission_id=f"HR-VISA_RENEWAL-{uuid.uuid4().hex[:8].upper()}",
            user_id=hr.id,
            module_type="hr_visa_renewal",
            site_name="HR Self",
            status="submitted",
            workflow_status=WF_MGMT_HR,
            form_data=payload,
        )
        db.session.add(sub)
        db.session.flush()
        ok, err = apply_management_signature(sub, hr, sig, "self")
        assert ok is False
        assert err
        ok_other, err_other = apply_management_signature(
            sub, chain_users["emp"], sig, "nope"
        )
        assert ok_other is False
        db.session.rollback()


def test_hr_signer_pool_excludes_submitter(app, chain_users):
    from app.models import Submission
    from module_hr.hr_management_chain import (
        MGMT_CHAIN_KEY,
        WF_MGMT_HR,
        current_management_signer_users,
        init_management_chain_on_submit,
    )

    with app.app_context():
        emp = chain_users["emp"]
        hr = chain_users["hr"]
        payload = {"employee_name": "Emp", "submitted_by_id": emp.id}
        assert init_management_chain_on_submit(payload, emp) is None
        block = payload[MGMT_CHAIN_KEY]
        hr_idx = next(i for i, s in enumerate(block["steps"]) if s["key"] == "hr_head_office")
        block["current_index"] = hr_idx
        sub = Submission(
            submission_id=f"HR-VISA_RENEWAL-{uuid.uuid4().hex[:8].upper()}",
            user_id=emp.id,
            module_type="hr_visa_renewal",
            site_name="Emp",
            status="submitted",
            workflow_status=WF_MGMT_HR,
            form_data=payload,
        )
        recipients, role = current_management_signer_users(sub)
        ids = {u.id for u in recipients}
        assert emp.id not in ids
        assert hr.id in ids
        assert role == "HR"


def test_submitter_mgmt_signoff_detail_cannot_sign_hr_step(client, app, chain_users):
    """Employee who started the visa form must not see the HR signature pad."""
    from app.models import db, Submission
    from module_hr.hr_management_chain import (
        MGMT_CHAIN_KEY,
        WF_MGMT_HR,
        init_management_chain_on_submit,
    )

    with app.app_context():
        emp = chain_users["emp"]
        emp.access_hr = True
        db.session.commit()
        payload = {
            "employee_name": "Arshith",
            "submitted_by_id": emp.id,
            "submitted_by_name": "Arshith",
        }
        assert init_management_chain_on_submit(payload, emp) is None
        block = payload[MGMT_CHAIN_KEY]
        hr_idx = next(i for i, s in enumerate(block["steps"]) if s["key"] == "hr_head_office")
        block["current_index"] = hr_idx
        sub = Submission(
            submission_id=f"HR-VISA_RENEWAL-{uuid.uuid4().hex[:8].upper()}",
            user_id=emp.id,
            module_type="hr_visa_renewal",
            site_name="Arshith",
            status="submitted",
            workflow_status=WF_MGMT_HR,
            form_data=payload,
        )
        db.session.add(sub)
        db.session.commit()
        sid = sub.submission_id
        emp_name = emp.username
        hr_name = chain_users["hr"].username

    emp_h = _login_headers(client, emp_name)
    detail = client.get(f"/hr/api/mgmt-signoff-detail/{sid}", headers=emp_h).get_json()
    assert detail["success"] is True
    assert detail["is_owner"] is True
    assert detail["can_sign"] is False
    assert detail["viewer_state"] == "submitter"
    assert not detail.get("step_label")

    mine = client.get("/hr/api/my-mgmt-signoffs", headers=emp_h).get_json()["submissions"]
    assert sid not in {row["submission_id"] for row in mine}

    hr_h = _login_headers(client, hr_name)
    hr_detail = client.get(f"/hr/api/mgmt-signoff-detail/{sid}", headers=hr_h).get_json()
    assert hr_detail["can_sign"] is True
    assert hr_detail["is_owner"] is False
    assert hr_detail["step_label"] == "HR"


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


def _login_headers(client, username, password="TestPass123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def test_pending_review_sends_submitter_to_submitted_and_signer_to_archive(client, admin_auth_headers):
    r = client.get("/hr/pending-review", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Open in Submitted Forms" in body
    assert "/hr/api/my-in-flight-hr" in body
    assert "Status" in body
    assert "hrOwnerSubmittedFormsLink" in body
    assert "Open in Completed Forms" not in body
    assert "Open in GM Approved Forms" not in body
    assert "/hr/gm-approval?submission=" not in body


def test_mgmt_sign_page_stays_put_with_pending_forms_link(client, admin_auth_headers):
    r = client.get("/hr/mgmt-sign/HR-LEAVE_APPLICATION-TEST", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "You have already signed this form" in body
    assert "Back to Pending Forms" in body
    assert 'id="rspDonePrimaryLink"' in body
    assert "/hr/pending-review" in body
    assert "openHrCenterNotice" not in body
    assert "redirectGmAlreadySigned" not in body
    assert "Open in GM Approved Forms" not in body
    assert "Open in Completed Forms" not in body
    assert "Open Completed Forms" not in body


def test_gm_approval_waiting_overlay_does_not_show_fake_hr_or_completed_cta(client, admin_auth_headers):
    r = client.get("/hr/gm-approval", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "You have already signed" in body
    assert "gm-signed-status" in body
    assert "Back to list" in body
    assert "Open Completed Forms" not in body
    assert "function hrHasSigned" in body
    assert "function nextUnsignedStepLabel" in body
    assert "hr_reviewed_by_name || 'HR Manager'" not in body
    assert "You signed this request. Remaining signatures are still outstanding." not in body


def test_workflow_cards_split_pending_gm_approved_and_completed(client, app, chain_users):
    """Pending = needs this user or the submitter's own in-flight status; GM Approved = GM signed in-flight; Completed = all signatures."""
    from app.models import db, Submission
    from module_hr.hr_management_chain import (
        WF_MGMT_HR,
        apply_management_signature,
        first_management_workflow_status,
        init_management_chain_on_submit,
    )

    sig = "data:image/png;base64,abc"
    with app.app_context():
        emp = chain_users["emp"]
        gm = chain_users["gm"]
        emp.reporting_manager_id = gm.id
        db.session.commit()

        payload: dict = {"employee_name": "Office Emp"}
        assert init_management_chain_on_submit(payload, emp) is None
        wf0 = first_management_workflow_status(payload)
        sub = Submission(
            submission_id=f"HR-VISA_RENEWAL-{uuid.uuid4().hex[:8].upper()}",
            user_id=emp.id,
            module_type="hr_visa_renewal",
            site_name="Office Emp",
            status="submitted",
            workflow_status=wf0,
            form_data=payload,
        )
        db.session.add(sub)
        db.session.commit()
        sid = sub.submission_id
        gm_name = gm.username
        emp_name = emp.username

    gm_h = _login_headers(client, gm_name)
    emp_h = _login_headers(client, emp_name)
    assert client.get("/hr/pending-review", headers=gm_h).status_code == 200
    assert client.get("/hr/pending-review", headers=emp_h).status_code == 200

    pending = client.get("/hr/api/my-mgmt-signoffs", headers=gm_h).get_json()["submissions"]
    assert sid in {s["submission_id"] for s in pending}

    own_inflight = client.get("/hr/api/my-in-flight-hr", headers=emp_h).get_json()["submissions"]
    assert sid in {s["submission_id"] for s in own_inflight}
    own_row = next(s for s in own_inflight if s["submission_id"] == sid)
    assert own_row["viewer_state"] == "submitter"
    assert own_row["can_sign"] is False
    assert sid not in {
        s["submission_id"]
        for s in client.get("/hr/api/my-mgmt-signoffs", headers=emp_h).get_json()["submissions"]
    }

    gm_approved = client.get("/hr/api/pending-gm-approval", headers=gm_h).get_json()["submissions"]
    assert sid not in {s["submission_id"] for s in gm_approved}

    with app.app_context():
        sub = Submission.query.filter_by(submission_id=sid).first()
        gm = chain_users["gm"]
        ok, err = apply_management_signature(sub, gm, sig, "ok")
        assert ok, err
        db.session.commit()
        assert sub.workflow_status == WF_MGMT_HR

    pending_after = client.get("/hr/api/my-mgmt-signoffs", headers=gm_h).get_json()["submissions"]
    assert sid not in {s["submission_id"] for s in pending_after}

    gm_approved_after = client.get("/hr/api/pending-gm-approval", headers=gm_h).get_json()["submissions"]
    assert sid in {s["submission_id"] for s in gm_approved_after}

    detail = client.get(f"/hr/api/mgmt-signoff-detail/{sid}", headers=gm_h).get_json()
    assert detail["already_signed"] is True
    assert detail["can_sign"] is False
    assert detail["viewer_state"] == "already_signed"
    label = (detail.get("step_label") or "").lower()
    assert "hr" not in label
    assert "reporting" in label or "manager" in label

    completed = client.get("/hr/api/approved-hr-submissions", headers=gm_h).get_json()["submissions"]
    assert sid not in {s["submission_id"] for s in completed}

    with app.app_context():
        sub = Submission.query.filter_by(submission_id=sid).first()
        sub.workflow_status = "approved"
        db.session.commit()

    gm_approved_done = client.get("/hr/api/pending-gm-approval", headers=gm_h).get_json()["submissions"]
    assert sid not in {s["submission_id"] for s in gm_approved_done}

    completed_done = client.get("/hr/api/approved-hr-submissions", headers=gm_h).get_json()["submissions"]
    assert sid in {s["submission_id"] for s in completed_done}

    own_done = client.get("/hr/api/my-in-flight-hr", headers=emp_h).get_json()["submissions"]
    assert sid not in {s["submission_id"] for s in own_done}


def test_approved_forms_signer_sees_only_forms_they_signed(client, app, chain_users):
    """Completed Forms: own requests plus forms this user signed; not everyone else's."""
    from app.models import db, Submission
    from module_hr.hr_management_chain import MGMT_CHAIN_KEY, init_management_chain_on_submit

    with app.app_context():
        tech = chain_users["tech"]
        sup = chain_users["sup"]
        emp = chain_users["emp"]
        gm = chain_users["gm"]

        signed_payload: dict = {"employee_name": "Tech User"}
        assert init_management_chain_on_submit(signed_payload, tech) is None
        step = signed_payload[MGMT_CHAIN_KEY]["steps"][0]
        step["signature"] = "data:image/png;base64,abc"
        step["signed_by_id"] = sup.id
        signed = Submission(
            submission_id=f"HR-COMMENCEMENT-{uuid.uuid4().hex[:8].upper()}",
            user_id=tech.id,
            module_type="hr_commencement",
            site_name="Tech User",
            status="submitted",
            workflow_status="approved",
            form_data=signed_payload,
        )

        other_payload: dict = {"employee_name": "Other"}
        assert init_management_chain_on_submit(other_payload, emp) is None
        other = Submission(
            submission_id=f"HR-VISA_RENEWAL-{uuid.uuid4().hex[:8].upper()}",
            user_id=emp.id,
            module_type="hr_visa_renewal",
            site_name="Other",
            status="submitted",
            workflow_status="approved",
            form_data=other_payload,
        )
        db.session.add_all([signed, other])
        db.session.commit()
        signed_id = signed.submission_id
        other_id = other.submission_id
        names = {
            "sup": sup.username,
            "emp": emp.username,
            "gm": gm.username,
        }

    sup_h = _login_headers(client, names["sup"])
    assert client.get("/hr/approved-forms", headers=sup_h).status_code == 200
    sup_ids = {
        s["submission_id"]
        for s in client.get("/hr/api/approved-hr-submissions", headers=sup_h).get_json()["submissions"]
    }
    assert signed_id in sup_ids
    assert other_id not in sup_ids

    emp_h = _login_headers(client, names["emp"])
    assert client.get("/hr/approved-forms", headers=emp_h).status_code == 200
    emp_ids = {
        s["submission_id"]
        for s in client.get("/hr/api/approved-hr-submissions", headers=emp_h).get_json()["submissions"]
    }
    assert signed_id not in emp_ids
    assert other_id in emp_ids

    gm_h = _login_headers(client, names["gm"])
    gm_ids = {
        s["submission_id"]
        for s in client.get("/hr/api/approved-hr-submissions", headers=gm_h).get_json()["submissions"]
    }
    assert signed_id in gm_ids
    assert other_id in gm_ids


def test_mgmt_chain_context_uses_submitter_path_when_viewing_a_form(client, app, chain_users):
    """GM viewing an employee's leave must see that employee's RM → HR path, not the GM's own."""
    from app.models import db, Submission
    from module_hr.hr_management_chain import init_management_chain_on_submit

    with app.app_context():
        emp = chain_users["emp"]
        gm = chain_users["gm"]
        emp.reporting_manager_id = gm.id
        db.session.commit()
        payload: dict = {"employee_name": "Office Emp"}
        assert init_management_chain_on_submit(payload, emp) is None
        sub = Submission(
            submission_id=f"HR-LEAVE_APPLICATION-{uuid.uuid4().hex[:8].upper()}",
            user_id=emp.id,
            module_type="hr_leave_application",
            site_name="Office Emp",
            status="submitted",
            workflow_status="approved",
            form_data=payload,
        )
        db.session.add(sub)
        db.session.commit()
        sid = sub.submission_id
        gm_name = gm.username

    gm_h = _login_headers(client, gm_name)
    own = client.get("/hr/api/mgmt-chain-context", headers=gm_h).get_json()
    own_keys = [c.get("key") for c in (own.get("chain") or [])]
    assert "reporting_manager" not in own_keys

    recorded = client.get(
        f"/hr/api/mgmt-chain-context?submission_id={sid}",
        headers=gm_h,
    ).get_json()
    rec_keys = [c.get("key") for c in (recorded.get("chain") or [])]
    assert rec_keys[0] == "reporting_manager"
    assert rec_keys[-1] == "hr_head_office"
    assert "Reporting manager" in (recorded.get("lane_flow") or "")
    assert recorded.get("recorded_path") is True
