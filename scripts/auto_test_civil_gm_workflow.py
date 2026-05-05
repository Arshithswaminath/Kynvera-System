#!/usr/bin/env python3
"""
Auto Test: Generate Civil inspection form PDF including full workflow
up to and including General Manager approval.

Run from project root:
  python scripts/auto_test_civil_gm_workflow.py

Output:
  test_output/inspection_forms_test/
"""

import os
from datetime import datetime

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_project_root():
    """Ensure cwd is project root and import paths are correct."""
    import sys

    if os.getcwd() != PROJECT_ROOT:
        os.chdir(PROJECT_ROOT)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


# Minimal 1x1 transparent PNG as base64 (for signatures/photos)
SIG_PLACEHOLDER = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def sample_civil_gm_data():
    """Sample Civil form data including full reviewer chain up to GM."""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "project_name": "Civil GM Workflow Test Project",
        "location": "Ajman Industrial Area",
        "visit_date": today,
        "inspector_name": "Test Civil Inspector",
        "description_of_work": "Concrete repair and waterproofing inspection.",
        "work_items": [
            {
                "description": "Repair cracks in slab near column C3",
                "quantity": "25 m",
                "material": "Polymer-modified repair mortar",
                "material_qty": "5 bags",
                "price": "1500 AED",
                "labour": "2 masons, 1 helper",
                "photos": [{"url": SIG_PLACEHOLDER}],
            },
            {
                "description": "Apply waterproofing membrane on roof area",
                "quantity": "120 m²",
                "material": "Torch-applied bituminous membrane",
                "material_qty": "Rolls as per coverage",
                "price": "6500 AED",
                "labour": "4 workers",
                "photos": [{"url": SIG_PLACEHOLDER}],
            },
        ],
        # Supervisor
        "supervisor_comments": "Site inspected. Repair methodology and access confirmed.",
        "supervisor_signature": SIG_PLACEHOLDER,
        # Operations Manager
        "operations_manager_comments": "Scope and resources approved. Monitor weather for waterproofing works.",
        "operations_manager_signature": SIG_PLACEHOLDER,
        # Business Development
        "business_dev_comments": "Client communication in progress. No pricing changes required.",
        "business_dev_signature": SIG_PLACEHOLDER,
        # Procurement
        "procurement_comments": "Materials available in stock. Replenish after this job.",
        "procurement_signature": SIG_PLACEHOLDER,
        # General Manager (final approval)
        "general_manager_comments": "Approved. Proceed as per submitted plan.",
        "general_manager_signature": SIG_PLACEHOLDER,
    }


def main():
    _ensure_project_root()

    from module_civil.civil_generators import create_pdf_report

    out_dir = os.path.join(PROJECT_ROOT, "test_output", "inspection_forms_test")
    os.makedirs(out_dir, exist_ok=True)

    data = sample_civil_gm_data()

    print(f"Output directory: {out_dir}")
    print("Sample Civil + GM data:")
    print(f"  Project: {data['project_name']}")
    print(f"  Visit date: {data['visit_date']}")
    print(f"  Work items: {len(data['work_items'])}")
    print("  Includes reviewer comments/signatures for:")
    print("    - Supervisor")
    print("    - Operations Manager")
    print("    - Business Development")
    print("    - Procurement")
    print("    - General Manager (final approval)")

    print("\nGenerating Civil PDF (full workflow up to GM)...")
    pdf_basename = create_pdf_report(data, out_dir)
    pdf_path = os.path.join(out_dir, pdf_basename)
    print(f"  Created: {pdf_basename}")
    print("\nCivil GM workflow PDF test completed successfully.")
    print(f"File saved to: {pdf_path}")


if __name__ == "__main__":
    main()

