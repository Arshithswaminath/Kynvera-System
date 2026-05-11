"""
Layout / template regression for Leave Application PDF.

Uses `tests/fixtures/hr/leave_application_reference.pdf` (export from the app) as the
baseline document, and asserts generated PDFs contain the same structural sections and
headings (branding, body table, HR-only block, signature placeholders, management trail).
"""
from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest

from module_hr.hr_pdf_builder import HR_PDF_LAYOUT_VERSION

BASE = Path(__file__).resolve().parents[1]
FIXTURE_PDF = BASE / "tests" / "fixtures" / "hr" / "leave_application_reference.pdf"

pytest.importorskip("pypdf")
from pypdf import PdfReader  # noqa: E402


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    r = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in r.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _hr_batch():
    p = BASE / "scripts" / "test_all_hr_forms.py"
    spec = importlib.util.spec_from_file_location("test_all_hr_forms_batch", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _leave_application_form_data_with_mgmt_chain():
    """Deterministic payload matching the shipped Leave layout (incl. page-2 management trail)."""
    hr = _hr_batch()
    fd = hr._sample_form_data("leave_application")
    fd["hr_mgmt_chain"] = {
        "v": 1,
        "lane": "employee",
        "steps": [
            {
                "key": "reporting_manager",
                "wf": "mgmt_reporting",
                "pdf_label": "Reporting manager",
                "signer_mode": "fixed_user",
                "signer_id": 1,
                "signed_by_name": "Taha",
                "comments": "Approved",
                "signature": None,
                "signed_at": "2026-05-06T10:00:00+00:00",
            },
            {
                "key": "hr_head_office",
                "wf": "mgmt_hr",
                "pdf_label": "HR (head office)",
                "signer_mode": "designation",
                "designation_gate": "hr_head_office",
                "signed_by_name": None,
                "comments": "—",
                "signature": None,
                "signed_at": None,
            },
        ],
        "pdf_hints": [
            "Your reporting manager is the General Manager — one signature covers both steps on this form.",
        ],
    }
    return fd


# Strings taken from a real export (`leave_application_reference.pdf`) — section headers and trail.
LEAVE_APPLICATION_LAYOUT_MARKERS = [
    "Injaaz Facility Management",
    "Leave Application Form",
    "DETAILS OF LEAVE",
    "Type of Leave",
    "For Human Resources Only",
    "HR Signature",
    "Management approvals",
    "official sign-off trail",
    "Signatures captured in approval order",
    "Role",
    "Signer",
    "Comments",
    "Signature",
    "Date",
    "Reporting manager",
    "HR (head office)",
    "(HR pool)",
    "Generated",
    "Dubai",
    f"PDF layout {HR_PDF_LAYOUT_VERSION}",
]


def test_fixture_reference_pdf_contains_layout_markers():
    assert FIXTURE_PDF.is_file(), (
        f"Missing {FIXTURE_PDF}. Copy an exported Leave Application PDF from the app into this path."
    )
    text = _extract_pdf_text(FIXTURE_PDF.read_bytes())
    missing = [m for m in LEAVE_APPLICATION_LAYOUT_MARKERS if m not in text]
    assert not missing, f"Fixture PDF missing markers: {missing[:8]}"


def test_generated_leave_application_pdf_matches_layout_markers():
    from module_hr.pdf_service import generate_hr_pdf

    hr = _hr_batch()
    fd = _leave_application_form_data_with_mgmt_chain()
    sub = hr._mock_submission("leave_application", fd, submission_id="TEMPLATE-TEST-LEAVE-APP")

    buf = BytesIO()
    ok, err = generate_hr_pdf(sub, buf)
    assert ok, err

    text = _extract_pdf_text(buf.getvalue())
    missing = [m for m in LEAVE_APPLICATION_LAYOUT_MARKERS if m not in text]
    assert not missing, f"Generated PDF missing markers: {missing[:12]}"

    r = PdfReader(BytesIO(buf.getvalue()))
    assert len(r.pages) >= 2, "Leave Application with management chain should span at least two pages"
    # Italic “Sign here” in ReportLab tables is often omitted by pypdf; require signature labels + mgmt pending.
    assert "Pending" in text or "Sign here" in text, (
        "expected empty-signature placeholders (Pending or Sign here) in extracted text"
    )


def test_generated_leave_application_includes_checkbox_and_leave_type_row():
    """Ensures the detailed leave grid (not a minimal stub) is present."""
    from module_hr.pdf_service import generate_hr_pdf

    hr = _hr_batch()
    fd = _leave_application_form_data_with_mgmt_chain()
    sub = hr._mock_submission("leave_application", fd)

    buf = BytesIO()
    assert generate_hr_pdf(sub, buf)[0]
    text = _extract_pdf_text(buf.getvalue())
    assert "Annual Leave" in text
    assert "Total No. of Days Requested" in text
