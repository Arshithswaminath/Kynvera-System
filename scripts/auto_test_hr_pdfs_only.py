#!/usr/bin/env python3
"""
Auto Test: Fill all HR module form fields with sample data and generate **PDF only**.

Run from project root:
  python scripts/auto_test_hr_pdfs_only.py

Output:
  test_output/hr_forms_pdfs_YYYYMMDD_HHMMSS/
"""

import os
import sys
from datetime import datetime

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# Reuse sample data and helpers from the main HR auto-test script
from scripts.auto_test_hr_forms import _sample_form_data, _mock_submission  # type: ignore


def main():
    from module_hr.pdf_service import generate_hr_pdf, get_supported_pdf_forms

    out_dir = os.path.join(
        PROJECT_ROOT,
        "test_output",
        f"hr_forms_pdfs_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(out_dir, exist_ok=True)
    print(f"Output directory: {out_dir}")

    sample_data = _sample_form_data()
    pdf_forms = get_supported_pdf_forms()

    results = []

    for form_type in pdf_forms:
        # `leave` is an alias mapped to leave_application sample data
        form_data = (
            sample_data.get("leave_application")
            if form_type == "leave"
            else sample_data.get(form_type)
        )
        if not form_data:
            print(f"  [SKIP] {form_type}: no sample data")
            continue

        submission = _mock_submission(form_type, form_data)
        slug = form_type.replace("_", " ").replace(" ", "_").lower()

        try:
            pdf_path = os.path.join(out_dir, f"{slug}_{submission.submission_id}.pdf")
            with open(pdf_path, "wb") as f:
                ok, err = generate_hr_pdf(submission, f)
                if not ok:
                    raise RuntimeError(err or "PDF generation failed")
            results.append(pdf_path)
            print(f"  [OK] PDF: {form_type}")
        except Exception as e:
            print(f"  [FAIL] PDF {form_type}: {e}")

    print(f"\nDone. Generated {len(results)} HR PDFs in {out_dir}")


if __name__ == "__main__":
    main()

