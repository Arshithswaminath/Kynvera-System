"""Per-form HR signature requirement catalog (counts + extras)."""
from module_hr.hr_signature_requirements import (
    FORM_REQUIREMENTS,
    form_type_from_path,
    summarize_required_signatures,
)


def test_form_type_from_path():
    assert form_type_from_path("/hr/duty-resumption-form") == "duty_resumption"
    assert form_type_from_path("/hr/leave-application-form?edit=x") == "leave_application"
    assert form_type_from_path("/hr/unknown") == ""


def test_summarize_office_staff_chain_counts():
    chain = [
        {"role_label": "Reporting manager"},
        {"role_label": "HR"},
    ]
    duty = summarize_required_signatures("duty_resumption", chain)
    assert duty["you_now_count"] == 1
    assert duty["min_total"] == 3
    assert duty["chain_count"] == 2

    leave = summarize_required_signatures("leave_application", chain)
    assert leave["you_now_count"] == 1
    assert leave["extra_optional_count"] == 1
    assert leave["min_total"] == 3

    contract = summarize_required_signatures("contract_renewal", chain)
    assert contract["you_now_count"] == 0
    assert contract["extra_required_count"] == 1
    assert contract["min_total"] == 3

    interview = summarize_required_signatures("interview_assessment", [])
    assert interview["you_now_count"] == 0
    assert interview["extra_required_count"] == 1
    assert interview["min_total"] == 1

    commencement = summarize_required_signatures("commencement", chain)
    assert commencement["you_now_count"] == 1
    assert commencement["extra_required_count"] == 1
    assert commencement["min_total"] == 4


def test_catalog_covers_live_hr_forms():
    expected = {
        "leave_application",
        "duty_resumption",
        "visa_renewal",
        "commencement",
        "grievance",
        "passport_release",
        "performance_evaluation",
        "station_clearance",
        "asset_handover",
        "staff_appraisal",
        "contract_renewal",
        "interview_assessment",
        "termination",
        "long_vacation",
        "leave",
        "asset",
    }
    assert expected <= set(FORM_REQUIREMENTS)


def test_signature_status_sidebar_reads_live_chain_and_reporting_manager():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static/js/hr_signature_status_sidebar.js").read_text(
        encoding="utf-8"
    )
    assert "reporting_manager:" in js
    assert "liveStepHasSignature" in js
    assert "setHrMgmtChainLiveSteps" in js
    assert "isSignatureSrc" in js
    assert "u.indexOf('/') === 0" not in js


def test_mgmt_chain_sidebar_marks_live_signed_steps():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static/js/hr_mgmt_chain_submit.js").read_text(
        encoding="utf-8"
    )
    assert "hr-mgmt-chain-step--signed" in js
    assert "hr-mgmt-chain-live" in js


def test_leave_form_hydrates_manager_sig_from_reporting_manager_chain():
    from pathlib import Path

    html = (
        Path(__file__).resolve().parents[1]
        / "module_hr/templates/hr_leave_application_form.html"
    ).read_text(encoding="utf-8")
    assert "managerSignatureFromLeaveFd" in html
    assert "setHrMgmtChainLiveSteps" in html
