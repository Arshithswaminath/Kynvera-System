"""Human-readable labels for submissions in admin dashboards and lists."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


MODULE_DISPLAY: dict[str, str] = {
    "hvac_mep": "Fire Systems",
    "procurement_material": "Procurement Request",
    "procurement_property": "Procurement Property",
    "catalog_material": "Material Catalog",
    "mmr": "MMR Report",
}


def get_module_display_name(module_type: str | None) -> str:
    """Return a professional module / form label for a submission."""
    mt = (module_type or "").strip()
    if not mt:
        return "Document"
    if mt.startswith("hr_"):
        try:
            from module_hr.routes import get_form_type_display

            return get_form_type_display(mt)
        except Exception:
            return mt.replace("hr_", "").replace("_", " ").title()
    return MODULE_DISPLAY.get(mt, mt.replace("_", " ").title())


def _resolve_subject(submission: Any) -> str:
    site = (getattr(submission, "site_name", None) or "").strip()
    if site and site not in ("N/A", "Unknown", "HR Form", "—"):
        return site

    form_data = getattr(submission, "form_data", None)
    if isinstance(form_data, dict):
        for key in (
            "employee_name",
            "complainant_name",
            "candidate_name",
            "site_name",
            "project_name",
            "property_name",
        ):
            val = (form_data.get(key) or "").strip()
            if val:
                return val
    return "Untitled record"


def format_visit_date_label(visit_date: date | datetime | str | None) -> str | None:
    if not visit_date:
        return None
    if isinstance(visit_date, datetime):
        d = visit_date.date()
    elif isinstance(visit_date, date):
        d = visit_date
    elif isinstance(visit_date, str):
        try:
            d = datetime.strptime(visit_date[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    else:
        return None
    return d.strftime("%d %b %Y")


INSPECTION_MODULE_TYPES = ("hvac_mep",)

# Document number series — each category gets its own running sequence.
SERIES_PREFIXES = ("HR", "INSP", "PRC", "TKT", "DOC")


def series_for_module_type(module_type: str | None) -> str:
    """Map a submission module_type to its document-number series prefix."""
    mt = (module_type or "").strip().lower()
    if mt.startswith("hr_"):
        return "HR"
    if mt in INSPECTION_MODULE_TYPES:
        return "INSP"
    if mt.startswith("procurement") or mt == "catalog_material":
        return "PRC"
    if mt.startswith("ticket"):
        return "TKT"
    return "DOC"


def format_doc_number(prefix: str, counter: int) -> str:
    return f"{prefix}-{counter:04d}"


def ensure_document_numbers() -> int:
    """
    Assign a permanent per-series document number (HR-0001, INSP-0001, ...) to any
    submission that does not have one yet, in creation order. Existing numbers are
    never changed, so a document keeps its number for life even if others are deleted.

    Returns the count of newly numbered submissions. Safe no-op when all are numbered.
    """
    from app.models import db, Submission

    unnumbered = (
        Submission.query
        .filter(db.or_(Submission.doc_number.is_(None), Submission.doc_number == ""))
        .order_by(Submission.created_at.asc(), Submission.id.asc())
        .all()
    )
    if not unnumbered:
        return 0

    # Current highest counter per series (numbers are zero-padded, max() is safe).
    counters: dict[str, int] = {}
    for prefix in SERIES_PREFIXES:
        last = (
            db.session.query(db.func.max(Submission.doc_number))
            .filter(Submission.doc_number.like(f"{prefix}-%"))
            .scalar()
        )
        n = 0
        if last:
            try:
                n = int(str(last).rsplit("-", 1)[-1])
            except ValueError:
                n = 0
        counters[prefix] = n

    for sub in unnumbered:
        prefix = series_for_module_type(sub.module_type)
        counters[prefix] = counters.get(prefix, 0) + 1
        sub.doc_number = format_doc_number(prefix, counters[prefix])

    db.session.commit()
    return len(unnumbered)


def build_document_ref(submission_id: str | None) -> str:
    """Short admin reference derived from the internal submission id."""
    sid = (submission_id or "").strip()
    if not sid:
        return ""
    if sid.startswith("HR-"):
        parts = sid.split("-")
        if len(parts) >= 3:
            return f"Ref {parts[-1]}"
    if sid.startswith("sub_") and len(sid) > 4:
        return f"Ref {sid[4:10].upper()}"
    if len(sid) > 8:
        return f"Ref {sid[-8:].upper()}"
    return f"Ref {sid.upper()}"


def build_document_labels(submission: Any, module_display: str | None = None) -> dict[str, str]:
    """
    Build display strings for admin document lists.

    Returns:
        document_title — primary label (module / form type, easy to read)
        document_subtitle — subject line (site, employee, or project)
        document_ref — short reference code (tooltip / secondary line)
    """
    mt = getattr(submission, "module_type", None) or ""
    module_label = module_display or get_module_display_name(mt)

    if mt in ("hvac_mep",):
        title = f"{module_label} Inspection"
    else:
        title = module_label

    subject = _resolve_subject(submission)
    ref = build_document_ref(getattr(submission, "submission_id", None))

    return {
        "document_title": title,
        "document_subtitle": subject,
        "document_ref": ref,
    }
