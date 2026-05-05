"""
Professional PDF generation for HR forms.
Native ReportLab builder — top-notch professional output, no DOCX conversion.
"""
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def generate_hr_pdf(submission, output_stream):
    """
    Generate a top-notch professional PDF from HR submission.
    Uses native ReportLab (hr_pdf_builder) — crisp typography, bold branding.
    Returns (True, None) on success, (False, error_msg) on failure.
    """
    from module_hr.hr_pdf_builder import build_hr_pdf, supports_pdf
    from module_hr.docx_service import _normalize_form_data_for_docx

    form_type = (submission.module_type or "").replace("hr_", "")
    form_data = _normalize_form_data_for_docx(submission.form_data or {}, form_type)

    if not supports_pdf(form_type):
        return False, "PDF not available for this form type"

    try:
        ok = build_hr_pdf(
            form_type,
            form_data,
            output_stream,
            submission_id=getattr(submission, "submission_id", None),
        )
        if ok:
            return True, None
        return False, "PDF generation failed"
    except Exception as e:
        logger.exception("HR PDF generation failed for %s: %s", form_type, e)
        return False, str(e)


def get_supported_pdf_forms():
    """Return list of form types that support PDF download."""
    from module_hr.hr_pdf_builder import _BUILDERS
    return list(_BUILDERS.keys())
