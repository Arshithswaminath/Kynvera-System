#!/usr/bin/env python3
"""
Generate a single folder of sample PDFs: all supported HR types plus multiple
inspection PDFs (HVAC item-rich + full signed workflow for HVAC/Civil/Cleaning).

Run from project root:
  python scripts/generate_all_sample_pdfs.py

Output:
  test_output/all_sample_pdfs_YYYYMMDD_HHMMSS/
    hr/                     — one PDF per HR type that supports PDF
    inspection/             — HVAC (2), Civil (1), Cleaning (1)
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_script_module(name: str, filename: str):
    root = _project_root()
    path = os.path.join(root, "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    root = _project_root()
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = os.path.join(root, "test_output", f"all_sample_pdfs_{stamp}")
    hr_dir = os.path.join(out_root, "hr")
    insp_dir = os.path.join(out_root, "inspection")
    os.makedirs(hr_dir, exist_ok=True)
    os.makedirs(insp_dir, exist_ok=True)

    print(f"Output: {out_root}\n")

    counts = {"hr": 0, "inspection": 0, "failed": []}

    # --- HR PDFs (all types in hr_pdf_builder._BUILDERS via get_supported_pdf_forms) ---
    hr_forms_mod = _load_script_module("auto_test_hr_forms", "auto_test_hr_forms.py")
    from module_hr.pdf_service import generate_hr_pdf, get_supported_pdf_forms

    sample_data = hr_forms_mod._sample_form_data()
    pdf_forms = get_supported_pdf_forms()
    seen = set()
    for form_type in pdf_forms:
        if form_type in seen:
            continue
        # Same ReportLab builder as leave_application — one file is enough
        if form_type == "leave":
            continue
        seen.add(form_type)
        form_data = (
            sample_data.get("leave_application")
            if form_type == "leave"
            else sample_data.get(form_type)
        )
        if not form_data:
            print(f"  [SKIP HR] {form_type}: no sample data")
            continue
        submission = hr_forms_mod._mock_submission(form_type, form_data)
        slug = form_type.replace("_", "-")
        pdf_path = os.path.join(hr_dir, f"hr_{slug}.pdf")
        try:
            with open(pdf_path, "wb") as f:
                ok, err = generate_hr_pdf(submission, f)
                if not ok:
                    raise RuntimeError(err or "PDF failed")
            counts["hr"] += 1
            print(f"  [OK] HR PDF  {form_type} -> {os.path.basename(pdf_path)}")
        except Exception as e:
            counts["failed"].append(("hr", form_type, str(e)))
            print(f"  [FAIL] HR PDF {form_type}: {e}")

    # --- Inspection: HVAC with multiple items (photos) ---
    hvac_insp = _load_script_module("auto_test_hvac_inspection", "auto_test_hvac_inspection.py")
    try:
        from module_hvac_mep.hvac_generators import create_pdf_report as hvac_pdf

        hvac_items_data = hvac_insp.sample_hvac_data()
        p = hvac_pdf(hvac_items_data, insp_dir)
        base = os.path.basename(p)
        if base != "hvac_inspection_items.pdf":
            target = os.path.join(insp_dir, "hvac_inspection_items.pdf")
            if os.path.abspath(p) != os.path.abspath(target) and os.path.isfile(p):
                os.replace(p, target)
                p = target
        counts["inspection"] += 1
        print(f"  [OK] Inspection  HVAC (items + photos) -> {os.path.basename(p)}")
    except Exception as e:
        counts["failed"].append(("inspection", "hvac_items", str(e)))
        print(f"  [FAIL] HVAC items PDF: {e}")

    # --- Inspection: full signed workflow PDFs (HVAC / Civil / Cleaning) ---
    hvac_gm = _load_script_module("auto_test_hvac_gm_workflow", "auto_test_hvac_gm_workflow.py")
    civil_gm = _load_script_module("auto_test_civil_gm_workflow", "auto_test_civil_gm_workflow.py")
    clean_gm = _load_script_module("auto_test_cleaning_gm_workflow", "auto_test_cleaning_gm_workflow.py")

    _pairs = [
        ("hvac_workflow_signed.pdf", hvac_gm.sample_hvac_gm_data, "module_hvac_mep.hvac_generators", "create_pdf_report"),
        ("civil_workflow_signed.pdf", civil_gm.sample_civil_gm_data, "module_civil.civil_generators", "create_pdf_report"),
        ("cleaning_workflow_signed.pdf", clean_gm.sample_cleaning_gm_data, "module_cleaning.cleaning_generators", "create_pdf_report"),
    ]
    for out_name, sample_fn, mod_path, fn_name in _pairs:
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            create_pdf = getattr(mod, fn_name)
            data = sample_fn()
            p = create_pdf(data, insp_dir)
            final_path = os.path.join(insp_dir, out_name)
            if os.path.abspath(p) != os.path.abspath(final_path) and os.path.isfile(p):
                if os.path.isfile(final_path):
                    os.remove(final_path)
                os.replace(p, final_path)
                p = final_path
            counts["inspection"] += 1
            print(f"  [OK] Inspection  {out_name}")
        except Exception as e:
            counts["failed"].append(("inspection", out_name, str(e)))
            print(f"  [FAIL] {out_name}: {e}")

    print(
        f"\nSummary: {counts['hr']} HR PDFs, {counts['inspection']} inspection PDFs "
        f"in {out_root}"
    )
    if counts["failed"]:
        print(f"Failures ({len(counts['failed'])}):")
        for bucket, name, msg in counts["failed"]:
            print(f"  - {bucket}/{name}: {msg}")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
