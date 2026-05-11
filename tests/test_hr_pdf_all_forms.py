"""Regression: every HR PDF form type generates valid PDF bytes (full sample data)."""
from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest

pytest.importorskip("pypdf")
from pypdf import PdfReader  # noqa: E402

from module_hr.hr_pdf_builder import HR_PDF_LAYOUT_VERSION

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


@pytest.fixture(scope="module")
def sample_and_mock():
    hr_batch = _hr_batch()

    def mock_and_data(form_type: str):
        fd = hr_batch._sample_form_data(form_type)
        sub = hr_batch._mock_submission(form_type, fd)
        return sub

    return mock_and_data


@pytest.mark.parametrize(
    "form_type",
    __import__("module_hr.pdf_service", fromlist=["get_supported_pdf_forms"]).get_supported_pdf_forms(),
)
def test_hr_pdf_generates_valid_pdf(form_type, sample_and_mock):
    from module_hr.pdf_service import generate_hr_pdf

    submission = sample_and_mock(form_type)
    buf = BytesIO()
    ok, err = generate_hr_pdf(submission, buf)
    assert ok, f"{form_type}: {err}"
    raw = buf.getvalue()
    assert len(raw) > 500, f"{form_type}: PDF unexpectedly small"
    assert raw.startswith(b"%PDF"), f"{form_type}: not a PDF"
    text = "\n".join(
        (p.extract_text() or "") for p in PdfReader(BytesIO(raw)).pages
    )
    assert HR_PDF_LAYOUT_VERSION in text, (
        f"{form_type}: footer must include PDF layout stamp {HR_PDF_LAYOUT_VERSION!r} "
        "(regenerate or fix hr_pdf_builder)."
    )
