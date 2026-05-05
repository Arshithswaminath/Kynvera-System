"""
Integration tests: all HR form types + all inspection modules (HVAC, Civil, Cleaning)
through multi-stage approval with signatures.

Uses in-memory SQLite. Admin performs HR + workflow approvals (routes allow role=admin).

PDF/Excel regeneration runs in background jobs for inspection modules — tests assert API + DB only.
"""
import pytest
from datetime import datetime, timezone

# 1x1 transparent PNG (same as scripts/auto_test_hvac_gm_workflow.py)
SIG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# Every distinct data.form_type from module_hr/templates/hr_*_form.html (15 types)
HR_FORM_TYPES = (
    "leave_application",
    "commencement",
    "duty_resumption",
    "contract_renewal",
    "performance_evaluation",
    "grievance",
    "interview_assessment",
    "passport_release",
    "staff_appraisal",
    "station_clearance",
    "visa_renewal",
    "long_vacation",
    "termination",
    "asset",
    "leave",
)

INSPECTION_MODULES = ("hvac_mep", "civil", "cleaning")


def _delete_submission_by_string_id(app, submission_id_str):
    with app.app_context():
        from app.models import Submission, db

        sub = Submission.query.filter_by(submission_id=submission_id_str).first()
        if sub:
            db.session.delete(sub)
            db.session.commit()


def _inspection_form_data(module_type: str, visit: str, label: str) -> dict:
    site = f"Pytest {label} Site"
    if module_type == "hvac_mep":
        return {"site_name": site, "visit_date": visit, "items": []}
    if module_type == "civil":
        return {"site_name": site, "visit_date": visit, "work_items": []}
    if module_type == "cleaning":
        return {
            "site_name": site,
            "visit_date": visit,
            "project_name": site,
            "date_of_visit": visit,
            "materials_required": [],
        }
    raise ValueError(module_type)


@pytest.mark.parametrize("form_type", HR_FORM_TYPES, ids=HR_FORM_TYPES)
def test_hr_form_full_approval_chain(app, client, auth_headers, admin_auth_headers, form_type):
    """Each HR form_type: submit → HR approve (sign) → GM approve (sign)."""
    body = {
        "form_type": form_type,
        "employee_name": f"Pytest Employee ({form_type})",
        "employee_signature": SIG_DATA_URL,
        "reason": "pytest workflow coverage",
    }
    r0 = client.post(
        "/hr/api/submit",
        json=body,
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.get_data(as_text=True)
    j0 = r0.get_json()
    assert j0.get("success") is True
    sid = j0.get("submission_id")
    assert sid

    expected_module = f"hr_{form_type}"
    try:
        with app.app_context():
            from app.models import Submission

            sub = Submission.query.filter_by(submission_id=sid).first()
            assert sub is not None
            assert sub.workflow_status == "hr_review"
            assert sub.module_type == expected_module

        r1 = client.post(
            f"/hr/api/hr-approve/{sid}",
            json={"comments": f"HR ok ({form_type})", "signature": SIG_DATA_URL},
            headers={**admin_auth_headers, "Content-Type": "application/json"},
        )
        assert r1.status_code == 200, r1.get_data(as_text=True)
        assert r1.get_json().get("success") is True

        with app.app_context():
            from app.models import Submission

            sub = Submission.query.filter_by(submission_id=sid).first()
            assert sub.workflow_status == "gm_review"
            fd = dict(sub.form_data or {})
            assert fd.get("hr_signature")
            assert fd.get("hr_reviewed_at")

        r2 = client.post(
            f"/hr/api/gm-approve/{sid}",
            json={"comments": f"GM final ({form_type})", "signature": SIG_DATA_URL},
            headers={**admin_auth_headers, "Content-Type": "application/json"},
        )
        assert r2.status_code == 200, r2.get_data(as_text=True)
        assert r2.get_json().get("success") is True

        with app.app_context():
            from app.models import Submission

            sub = Submission.query.filter_by(submission_id=sid).first()
            assert sub.workflow_status == "approved"
            assert sub.status == "completed"
            fd = dict(sub.form_data or {})
            assert fd.get("gm_signature")
            assert fd.get("gm_approved_at")
            assert fd.get("hr_signature")
    finally:
        _delete_submission_by_string_id(app, sid)


@pytest.mark.parametrize("module_type", INSPECTION_MODULES, ids=list(INSPECTION_MODULES))
def test_inspection_full_chain_signatures(app, client, supervisor_user, admin_auth_headers, module_type):
    """Supervisor submission → OM → BD → Procurement → GM; form_data keeps signatures."""
    from common.db_utils import create_submission_db

    visit = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    form_data = _inspection_form_data(module_type, visit, module_type)
    site_name = form_data.get("site_name", "Pytest Site")

    with app.app_context():
        sub = create_submission_db(
            module_type,
            form_data,
            site_name=site_name,
            visit_date=visit,
            user_id=supervisor_user.id,
        )
        sid = sub.submission_id
        assert sub.workflow_status == "operations_manager_review"

    try:
        def post_approval(path_suffix, payload):
            return client.post(
                f"/api/workflow/submissions/{sid}/{path_suffix}",
                json=payload,
                headers={**admin_auth_headers, "Content-Type": "application/json"},
            )

        assert post_approval(
            "approve-ops-manager",
            {"comments": f"OM pytest {module_type}", "signature": SIG_DATA_URL},
        ).status_code == 200

        assert post_approval(
            "approve-bd",
            {"comments": f"BD pytest {module_type}", "signature": SIG_DATA_URL},
        ).status_code == 200

        assert post_approval(
            "approve-procurement",
            {"comments": f"Proc pytest {module_type}", "signature": SIG_DATA_URL},
        ).status_code == 200

        with app.app_context():
            from app.models import Submission

            sub = Submission.query.filter_by(submission_id=sid).first()
            assert sub.workflow_status == "general_manager_review"

        assert post_approval(
            "approve-gm",
            {"comments": f"GM pytest {module_type}", "signature": SIG_DATA_URL},
        ).status_code == 200

        with app.app_context():
            from app.models import Submission

            sub = Submission.query.filter_by(submission_id=sid).first()
            assert sub.workflow_status == "completed"
            assert sub.status == "completed"
            fd = dict(sub.form_data or {})
            assert fd.get("operations_manager_comments")
            assert fd.get("operations_manager_signature") or fd.get("opMan_signature")
            assert fd.get("business_dev_signature")
            assert fd.get("procurement_signature")
            assert fd.get("general_manager_signature")
    finally:
        _delete_submission_by_string_id(app, sid)
