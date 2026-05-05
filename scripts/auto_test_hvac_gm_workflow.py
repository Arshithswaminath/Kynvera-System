#!/usr/bin/env python3
"""
Auto Test: Generate HVAC inspection form PDF including full workflow
up to and including General Manager approval.

Run from project root:
  python scripts/auto_test_hvac_gm_workflow.py

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


def sample_hvac_gm_data():
    """Sample HVAC form data including full reviewer chain up to GM."""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "site_name": "GM Workflow Test Tower",
        "site_address": "Dubai Investment Park",
        "visit_date": today,
        "items": [
            {
                "asset": "Chiller Unit 2",
                "system": "HVAC",
                "description": "Chiller with partial load test",
                "quantity": "1",
                "brand": "Carrier",
                "specification": "Model 30XA-400",
                "comments": "Minor vibration observed, recommended monitoring.",
                "photos": [{"url": SIG_PLACEHOLDER}],
            },
            {
                "asset": "AHU-05",
                "system": "HVAC",
                "description": "Air Handling Unit - Level 5",
                "quantity": "1",
                "brand": "Trane",
                "specification": "12,000 CFM",
                "comments": "Filters replaced, differential pressure within limits.",
                "photos": [{"url": SIG_PLACEHOLDER}],
            },
        ],
        # Supervisor
        "supervisor_comments": "Inspection completed. Minor issues noted, safe to operate.",
        "supervisor_signature": SIG_PLACEHOLDER,
        # Operations Manager
        "operations_manager_comments": "Agree with supervisor assessment. Schedule follow-up in 30 days.",
        "operations_manager_signature": SIG_PLACEHOLDER,
        # Business Development
        "business_dev_comments": "No commercial impact foreseen at this stage.",
        "business_dev_signature": SIG_PLACEHOLDER,
        # Procurement
        "procurement_comments": "Spare parts quotation to be requested only if vibration worsens.",
        "procurement_signature": SIG_PLACEHOLDER,
        # General Manager (final approval)
        "general_manager_comments": "Approved. Proceed as per Operations Manager plan.",
        "general_manager_signature": SIG_PLACEHOLDER,
    }


def main():
    _ensure_project_root()

    from module_hvac_mep.hvac_generators import create_pdf_report

    out_dir = os.path.join(PROJECT_ROOT, "test_output", "inspection_forms_test")
    os.makedirs(out_dir, exist_ok=True)

    data = sample_hvac_gm_data()

    print(f"Output directory: {out_dir}")
    print("Sample HVAC + GM data:")
    print(f"  Site: {data['site_name']}")
    print(f"  Visit date: {data['visit_date']}")
    print(f"  Items: {len(data['items'])}")
    print("  Includes reviewer comments/signatures for:")
    print("    - Supervisor")
    print("    - Operations Manager")
    print("    - Business Development")
    print("    - Procurement")
    print("    - General Manager (final approval)")

    print("\nGenerating HVAC/MEP PDF (full workflow up to GM)...")
    pdf_path = create_pdf_report(data, out_dir)
    print(f"  Created: {os.path.basename(pdf_path)}")
    print("\nHVAC GM workflow PDF test completed successfully.")
    print(f"File saved to: {pdf_path}")


if __name__ == "__main__":
    main()

