"""Reporting manager pre-fill coverage across HR forms."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "module_hr" / "templates"

# Only commencement has the employee-facing Reporting To name/designation block.
FORMS_WITH_REPORTING_TO_BLOCK = {"hr_commencement_form.html"}

# Every submit form should use profile-driven management chain in the sidebar.
HR_SUBMIT_FORMS = sorted(TEMPLATES_DIR.glob("hr_*_form.html"))


@pytest.fixture()
def technician_with_manager(app):
    from app.models import User, db

    created: list[int] = []
    with app.app_context():
        tag = uuid.uuid4().hex[:6]
        sup = User(
            username=f"rt_sup_{tag}",
            email=f"rt_sup_{tag}@example.com",
            full_name="Reporting Supervisor",
            role="user",
            designation="supervisor",
            is_active=True,
            password_changed=True,
        )
        sup.set_password("TestPass123")
        db.session.add(sup)
        db.session.flush()
        created.append(sup.id)

        tech = User(
            username=f"rt_tech_{tag}",
            email=f"rt_tech_{tag}@example.com",
            full_name="Reporting Technician",
            role="user",
            designation="technician",
            is_active=True,
            password_changed=True,
            reporting_manager_id=sup.id,
        )
        tech.set_password("TestPass123")
        db.session.add(tech)
        db.session.flush()
        created.append(tech.id)
        db.session.commit()

        yield {"tech": tech, "sup": sup}

        for uid in created:
            obj = db.session.get(User, uid)
            if obj is not None:
                db.session.delete(obj)
        db.session.commit()


def test_only_commencement_has_reporting_to_picker_block():
    """Reporting To picker + name fields exist on commencement only."""
    found = set()
    for path in HR_SUBMIT_FORMS:
        text = path.read_text(encoding="utf-8")
        if "reportingToUserSelect" in text or 'name="reporting_to_name"' in text:
            found.add(path.name)
    assert found == FORMS_WITH_REPORTING_TO_BLOCK


def test_all_hr_submit_forms_include_mgmt_chain_sidebar():
    """Management approvals sidebar (profile-driven routing) on every HR submit form."""
    missing = []
    for path in HR_SUBMIT_FORMS:
        text = path.read_text(encoding="utf-8")
        if "hr_form_approvals_sidebar.html" not in text:
            missing.append(path.name)
    assert missing == []


def test_commencement_form_uses_shared_reporting_to_prefill_js():
    text = (TEMPLATES_DIR / "hr_commencement_form.html").read_text(encoding="utf-8")
    assert "hr_reporting_to_prefill.js" in text
    assert "HrReportingToPrefill.init" in text


def test_ui_context_default_reporting_to_technician(app, technician_with_manager):
    from module_hr.hr_management_chain import get_mgmt_chain_ui_context

    with app.app_context():
        tech = technician_with_manager["tech"]
        sup = technician_with_manager["sup"]
        ctx = get_mgmt_chain_ui_context(tech)
        prefill = ctx.get("default_reporting_to")
        assert prefill is not None
        assert prefill["id"] == sup.id
        assert prefill["full_name"] == (sup.full_name or sup.username)


def test_ui_context_default_reporting_to_none_without_manager(app, standard_user):
    from module_hr.hr_management_chain import get_mgmt_chain_ui_context

    with app.app_context():
        ctx = get_mgmt_chain_ui_context(standard_user)
        assert ctx.get("default_reporting_to") is None
