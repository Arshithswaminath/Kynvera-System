"""
HR PDF contract tests: generation succeeds and extracted text includes expected branding
and body cues — without changing PDF layout code.

These complement ``test_hr_pdf_all_forms.py`` (strict layout-version check) for teams that
need looser footer assertions or explicit per-form title checks.
"""
from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest

pytest.importorskip("pypdf")
from pypdf import PdfReader  # noqa: E402

BASE = Path(__file__).resolve().parents[1]

_HR_BATCH = None


def _hr_batch():
    global _HR_BATCH
    if _HR_BATCH is None:
        p = BASE / "scripts" / "test_all_hr_forms.py"
        spec = importlib.util.spec_from_file_location("test_all_hr_forms_batch", p)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        _HR_BATCH = mod
    return _HR_BATCH


def _submission(form_type: str):
    hr = _hr_batch()
    return hr._mock_submission(form_type, hr._sample_form_data(form_type))


def _extract_all_text(pdf_bytes: bytes) -> str:
    r = PdfReader(BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def _title_phrases_required(form_type: str) -> tuple[str, ...]:
    """
    Substrings that must appear in extracted text for the form headline area.
    Duty resumption uses on-page title "Resumption Of Duty Form", not the registry nickname.
    """
    from module_hr.hr_pdf_builder import _BUILDERS
    _fn, title = _BUILDERS[form_type]
    headline_overrides: dict[str, tuple[str, ...]] = {
        "duty_resumption": ("Resumption Of Duty",),
    }
    return headline_overrides.get(form_type, (title,))


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_production_path_succeeds(form_type):
    """generate_hr_pdf (same as app download) returns ok for every supported type."""
    from module_hr.pdf_service import generate_hr_pdf

    buf = BytesIO()
    ok, err = generate_hr_pdf(_submission(form_type), buf)
    assert ok and err is None, f"{form_type}: {err}"


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_bytes_are_valid_file(form_type):
    from module_hr.pdf_service import generate_hr_pdf

    buf = BytesIO()
    assert generate_hr_pdf(_submission(form_type), buf)[0]
    raw = buf.getvalue()
    assert raw.startswith(b"%PDF-"), f"{form_type}: not a PDF file signature"
    assert len(raw) >= 512, f"{form_type}: output too small"


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_readable_and_contains_form_title(form_type):
    """Each form’s headline (see registry or overrides) must appear in extractable text."""
    from module_hr.pdf_service import generate_hr_pdf

    buf = BytesIO()
    assert generate_hr_pdf(_submission(form_type), buf)[0]
    text = _extract_all_text(buf.getvalue())
    for phrase in _title_phrases_required(form_type):
        assert phrase in text, f"{form_type}: expected headline phrase {phrase!r} in PDF text"
    r = PdfReader(BytesIO(buf.getvalue()))
    assert len(r.pages) >= 1, f"{form_type}: no pages"


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_contains_branding_and_generated_footer(form_type):
    """
    Header/footer must be present. Uses substring checks only — no layout geometry changes.
    Accepts either 'Kynvera Facility Management' (body) or footer time stamp.
    """
    from module_hr.pdf_service import generate_hr_pdf

    buf = BytesIO()
    assert generate_hr_pdf(_submission(form_type), buf)[0]
    text = _extract_all_text(buf.getvalue())
    assert "Kynvera Facility Management" in text or "INJAAZ" in text, (
        f"{form_type}: missing header branding"
    )
    assert "Generated" in text, f"{form_type}: missing 'Generated' footer"
    assert "Dubai" in text, f"{form_type}: missing Dubai footer"


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_signature_placeholder_or_drawn_slot(form_type):
    """
    Sample data usually has no base64 signature images; the builder emits placeholder
    text ('Sign here' / 'Pending') in signature areas when pypdf can extract them.
    """
    from module_hr.pdf_service import generate_hr_pdf

    buf = BytesIO()
    assert generate_hr_pdf(_submission(form_type), buf)[0]
    text = _extract_all_text(buf.getvalue())
    assert (
        "Sign here" in text
        or "Pending" in text
        or "signature" in text.lower()
    ), (
        f"{form_type}: no signature-related placeholder or label in extractable text"
    )


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_includes_management_approval_trail_like_real_downloads(form_type):
    """
    App exports append hr_mgmt_chain to PDFs (batch sample data includes the same v1 chain).
    Assert the printed section title and table columns appear in extractable text for every form.
    """
    from module_hr.pdf_service import generate_hr_pdf

    buf = BytesIO()
    assert generate_hr_pdf(_submission(form_type), buf)[0]
    text = _extract_all_text(buf.getvalue())
    assert "Management approvals" in text, (
        f"{form_type}: missing management trail (add hr_mgmt_chain to batch sample data)"
    )
    assert "official sign-off trail" in text, form_type
    assert "Role" in text and "Signer" in text, form_type


def test_hr_pdf_management_trail_starts_on_second_page_for_selected_forms():
    """Leave application, interview assessment, and station clearance: sign-off trail starts on page 2."""
    from module_hr.pdf_service import generate_hr_pdf

    marker = "official sign-off trail"
    for form_type in ("leave_application", "interview_assessment", "station_clearance"):
        buf = BytesIO()
        assert generate_hr_pdf(_submission(form_type), buf)[0]
        r = PdfReader(BytesIO(buf.getvalue()))
        assert len(r.pages) >= 2, form_type
        t0 = (r.pages[0].extract_text() or "").lower()
        t1 = (r.pages[1].extract_text() or "").lower()
        assert marker not in t0, f"{form_type}: management trail should not be on page 1"
        assert marker in t1, f"{form_type}: management trail should be on page 2"


def test_commencement_pdf_reporting_manager_named_ousman():
    """
    Scenario: reporting manager is Ousman — name appears in Reporting To and, for the sample chain,
    as the first-step signer in the management approvals table.
    """
    import copy

    from module_hr.pdf_service import generate_hr_pdf

    hr = _hr_batch()
    fd = hr._sample_form_data("commencement")
    fd["reporting_to_name"] = "Ousman"
    mc = copy.deepcopy(fd.get("hr_mgmt_chain") or {})
    if isinstance(mc.get("steps"), list) and mc["steps"]:
        step0 = mc["steps"][0]
        if isinstance(step0, dict):
            step0["signed_by_name"] = "Ousman"
    fd["hr_mgmt_chain"] = mc

    sub = hr._mock_submission("commencement", fd, submission_id="OUSMAN-RM-TEST")

    buf = BytesIO()
    ok, err = generate_hr_pdf(sub, buf)
    assert ok and err is None, err
    text = _extract_all_text(buf.getvalue())
    assert text.count("Ousman") >= 2, "Ousman should appear in Reporting To and management Signer column"
    assert "Commencement Form" in text or "Commencement" in text


def test_supported_pdf_forms_matches_build_registry():
    """pdf_service and hr_pdf_builder stay in sync."""
    from module_hr.hr_pdf_builder import _BUILDERS
    from module_hr.pdf_service import get_supported_pdf_forms

    supported = set(get_supported_pdf_forms())
    builders = set(_BUILDERS.keys())
    assert supported == builders, f"Registry mismatch: pdf {supported^builders}"
