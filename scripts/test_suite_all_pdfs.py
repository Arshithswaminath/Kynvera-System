#!/usr/bin/env python3
"""
Suite 1 — Generate every product PDF with test data.

Covers:
  • All HR form PDFs
  • Fire Systems inspection (basic + signed workflow)
  • Ticketing work-order / invoice / service-report PDFs
  • Ticketing analytics report PDFs (all REPORT_SPECS keys)
  • Operations cheque + trading invoice + quotation PDFs
  • Finance monthly report PDF
  • Legacy site-visit PDF

Usage (from project root):
  python scripts/test_suite_all_pdfs.py

Output:
  test_output/pdf_suite_YYYYMMDD_HHMMSS/
"""
from __future__ import annotations

import os
import sys
from io import BytesIO

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from test_suite_common import (  # noqa: E402
    SuiteResult,
    ensure_root_on_path,
    fake_cheque,
    fake_manpower,
    fake_materials,
    fake_quotation,
    fake_ticket,
    fake_trading_invoice,
    inspection_sample_data,
    is_pdf_bytes,
    load_script,
    make_outdir,
    sample_asset_handover_data,
    sample_finance_payload,
    sample_ticketing_report_rows,
    pdf_page_count,
    write_stream,
)


def _save_pdf(path: str, stream_or_bytes) -> None:
    size = write_stream(path, stream_or_bytes)
    with open(path, "rb") as f:
        head = f.read(4)
    if head != b"%PDF":
        raise RuntimeError(f"not a PDF (got {head!r}, {size} bytes)")
    if size < 200:
        raise RuntimeError(f"PDF too small ({size} bytes)")


def _gen_hr(out_dir: str, result: SuiteResult) -> None:
    hr_dir = os.path.join(out_dir, "hr")
    os.makedirs(hr_dir, exist_ok=True)

    hr_forms = load_script("auto_test_hr_forms", "auto_test_hr_forms.py")
    from module_hr.pdf_service import generate_hr_pdf, get_supported_pdf_forms

    sample = hr_forms._sample_form_data()
    seen = set()
    for form_type in get_supported_pdf_forms():
        if form_type in seen or form_type == "leave":
            continue
        seen.add(form_type)
        if form_type == "asset_handover":
            form_data = sample_asset_handover_data()
        elif form_type == "leave":
            form_data = sample.get("leave_application")
        else:
            form_data = sample.get(form_type)
        label = f"hr/{form_type}"
        if not form_data:
            result.skip(label, "no sample data")
            continue
        try:
            submission = hr_forms._mock_submission(form_type, form_data)
            path = os.path.join(hr_dir, f"hr_{form_type}.pdf")
            buf = BytesIO()
            ok, err = generate_hr_pdf(submission, buf)
            if not ok:
                raise RuntimeError(err or "generate_hr_pdf failed")
            _save_pdf(path, buf)
            result.pass_(label)
        except Exception as exc:
            result.fail(label, str(exc))


def _gen_inspection(out_dir: str, result: SuiteResult) -> None:
    """Fire Systems only — this product does not ship Civil / Cleaning forms."""
    insp_dir = os.path.join(out_dir, "inspection")
    os.makedirs(insp_dir, exist_ok=True)
    samples = inspection_sample_data()

    # Basic Fire Systems PDF (legacy generator module: module_hvac_mep)
    label = "inspection/fire_systems_basic"
    try:
        from module_hvac_mep.hvac_generators import create_pdf_report
        path = create_pdf_report(samples["hvac"], insp_dir)
        full = path if os.path.isabs(path) else os.path.join(insp_dir, path)
        if not os.path.isfile(full):
            raise RuntimeError(f"missing file: {full}")
        with open(full, "rb") as f:
            if not is_pdf_bytes(f.read(4)):
                raise RuntimeError("not a PDF")
        # Stable suite filename
        final = os.path.join(insp_dir, "fire_systems_basic.pdf")
        if os.path.abspath(full) != os.path.abspath(final):
            if os.path.isfile(final):
                os.remove(final)
            os.replace(full, final)
        pages = pdf_page_count(final)
        if pages < 2:
            raise RuntimeError(f"expected ≥2 pages (SR + attachments), got {pages}")
        result.pass_(f"{label} ({pages} pages)")
    except Exception as exc:
        result.fail(label, str(exc))

    # Full signed workflow Fire Systems PDF
    label = "inspection/fire_systems_workflow_signed"
    try:
        from module_hvac_mep.hvac_generators import create_pdf_report
        gm = load_script("auto_test_hvac_gm_workflow", "auto_test_hvac_gm_workflow.py")
        data = gm.sample_hvac_gm_data()
        data["submission_id"] = "FS-TEST-GM-0001"
        data["technician_name"] = "Arshith Technician"
        data["tech_signature"] = data.get("supervisor_signature") or samples["hvac"].get("tech_signature")
        data["job_name"] = "Fire Systems Inspection"
        p = create_pdf_report(data, insp_dir)
        src = p if os.path.isabs(p) else os.path.join(insp_dir, p)
        if not os.path.isfile(src):
            raise RuntimeError(f"generator returned missing path: {p!r}")
        final = os.path.join(insp_dir, "fire_systems_workflow_signed.pdf")
        if os.path.abspath(src) != os.path.abspath(final):
            if os.path.isfile(final):
                os.remove(final)
            os.replace(src, final)
        with open(final, "rb") as f:
            if not is_pdf_bytes(f.read(4)):
                raise RuntimeError("not a PDF")
        pages = pdf_page_count(final)
        if pages < 2:
            raise RuntimeError(f"expected ≥2 pages (SR + attachments), got {pages}")
        result.pass_(f"{label} ({pages} pages)")
    except Exception as exc:
        result.fail(label, str(exc))


def _gen_ticketing(out_dir: str, result: SuiteResult) -> None:
    tkt_dir = os.path.join(out_dir, "ticketing")
    os.makedirs(tkt_dir, exist_ok=True)

    ticket = fake_ticket()
    materials = fake_materials()
    manpower = fake_manpower()

    # Work order PDF
    label = "ticketing/work_order"
    try:
        from module_ticketing.ticket_pdf_builder import build_ticket_pdf
        buf = BytesIO()
        build_ticket_pdf(ticket, notes=[], images=[], materials=materials,
                         manpower_entries=manpower, output_stream=buf)
        path = os.path.join(tkt_dir, "work_order_TKT-TEST-001.pdf")
        _save_pdf(path, buf)
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))

    # Service invoice PDF
    label = "ticketing/invoice"
    try:
        from module_ticketing.ticket_invoice_builder import build_invoice_pdf
        buf = BytesIO()
        build_invoice_pdf(ticket, materials, manpower, buf)
        path = os.path.join(tkt_dir, "invoice_TKT-TEST-001.pdf")
        _save_pdf(path, buf)
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))

    # Service report PDF (single page — shared page-1 template)
    label = "ticketing/service_report"
    try:
        from module_ticketing.service_report import build_service_report_defaults
        from module_ticketing.service_report_pdf_builder import build_service_report_pdf
        sr = build_service_report_defaults(ticket, materials)
        sr["parts_used"] = [
            {"part": m.material_name, "specification": m.notes or "", "qty": m.quantity}
            for m in materials
        ]
        buf = BytesIO()
        build_service_report_pdf(ticket, sr, materials, buf)
        path = os.path.join(tkt_dir, "service_report_TKT-TEST-001.pdf")
        _save_pdf(path, buf)
        pages = pdf_page_count(path)
        if pages != 1:
            raise RuntimeError(f"ticket Service Report should be 1 page, got {pages}")
        result.pass_(f"{label} ({pages} page)")
    except Exception as exc:
        result.fail(label, str(exc))

    # Analytics report PDFs
    try:
        from module_ticketing.report_builders import REPORT_SPECS, build_report_pdf
    except Exception as exc:
        result.fail("ticketing/reports", f"import failed: {exc}")
        return

    for key, spec in REPORT_SPECS.items():
        label = f"ticketing/report_{key}"
        try:
            rows, summary = sample_ticketing_report_rows(key)
            buf = BytesIO()
            build_report_pdf(spec, rows, summary, "Test suite filters", buf)
            path = os.path.join(tkt_dir, f"report_{key}.pdf")
            _save_pdf(path, buf)
            result.pass_(label)
        except Exception as exc:
            result.fail(label, str(exc))


def _gen_operations(out_dir: str, result: SuiteResult) -> None:
    ops_dir = os.path.join(out_dir, "operations")
    os.makedirs(ops_dir, exist_ok=True)

    label = "operations/cheque"
    try:
        from module_operations.cheque_pdf_builder import build_cheque_pdf
        buf = BytesIO()
        build_cheque_pdf(fake_cheque(), buf)
        path = os.path.join(ops_dir, "cheque_CHQ-TEST-0001.pdf")
        _save_pdf(path, buf)
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))

    label = "operations/trading_invoice"
    try:
        from module_operations.trading_invoice_builder import build_trading_invoice_pdf
        invoice, client, items = fake_trading_invoice()
        buf = BytesIO()
        build_trading_invoice_pdf(invoice, client, items, buf)
        path = os.path.join(ops_dir, "trading_invoice_TRD-INV-TEST-001.pdf")
        _save_pdf(path, buf)
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))

    label = "operations/quotation"
    try:
        from module_operations.quotation_builder import build_quotation_pdf
        path = os.path.join(ops_dir, "quotation_ASQ-2026-TEST-001.pdf")
        build_quotation_pdf(fake_quotation(), path)
        with open(path, "rb") as f:
            if not is_pdf_bytes(f.read(4)):
                raise RuntimeError("not a PDF")
        if os.path.getsize(path) < 200:
            raise RuntimeError(f"PDF too small ({os.path.getsize(path)} bytes)")
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))


def _gen_finance(out_dir: str, result: SuiteResult) -> None:
    fin_dir = os.path.join(out_dir, "finance")
    os.makedirs(fin_dir, exist_ok=True)
    label = "finance/monthly_report"
    try:
        from module_finance.finance_report_builder import build_pdf
        buf = build_pdf(sample_finance_payload())
        path = os.path.join(fin_dir, "finance_monthly_report.pdf")
        _save_pdf(path, buf)
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))


def _gen_site_visit(out_dir: str, result: SuiteResult) -> None:
    sv_dir = os.path.join(out_dir, "site_visit")
    os.makedirs(sv_dir, exist_ok=True)
    label = "site_visit/legacy"
    try:
        from app.services.pdf_service import generate_visit_pdf
        visit_info = {
            "building_name": "Test Site — Ajman Tower",
            "email": "arshith@injaaz.ae",
            "visit_date": "2026-07-19",
            "supervisor": "Arshith Supervisor",
        }
        items = [{
            "description": "Chiller inspection — test data",
            "image_urls": [],
        }]
        pdf_path, _ = generate_visit_pdf(visit_info, items, sv_dir, report_id="SUITE-TEST")
        if not pdf_path or not os.path.isfile(pdf_path):
            raise RuntimeError(f"missing file: {pdf_path}")
        with open(pdf_path, "rb") as f:
            if not is_pdf_bytes(f.read(4)):
                raise RuntimeError("not a PDF")
        result.pass_(label)
    except Exception as exc:
        result.fail(label, str(exc))


def main() -> int:
    ensure_root_on_path()
    out_dir = make_outdir("pdf_suite")
    result = SuiteResult("PDF suite")
    print(f"\n{'=' * 70}")
    print("  Suite 1 — All PDFs with test data")
    print(f"  Output: {out_dir}")
    print(f"{'=' * 70}\n")

    print("── HR ──────────────────────────────────────────────────────────────")
    _gen_hr(out_dir, result)
    print("\n── Inspection ──────────────────────────────────────────────────────")
    _gen_inspection(out_dir, result)
    print("\n── Ticketing ───────────────────────────────────────────────────────")
    _gen_ticketing(out_dir, result)
    print("\n── Operations ──────────────────────────────────────────────────────")
    _gen_operations(out_dir, result)
    print("\n── Finance ─────────────────────────────────────────────────────────")
    _gen_finance(out_dir, result)
    print("\n── Site visit ──────────────────────────────────────────────────────")
    _gen_site_visit(out_dir, result)

    print(f"\nOutput folder: {out_dir}")
    return result.summary()


if __name__ == "__main__":
    sys.exit(main())
