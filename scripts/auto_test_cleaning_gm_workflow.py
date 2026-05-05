#!/usr/bin/env python3
"""
Auto Test: Generate Cleaning Assessment PDF including full workflow
up to and including General Manager approval.

Run from project root:
  python scripts/auto_test_cleaning_gm_workflow.py

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


def sample_cleaning_gm_data():
    """Sample Cleaning form data including full reviewer chain up to GM."""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "project_name": "Cleaning GM Workflow Test Site",
        "date_of_visit": today,
        "technician_name": "Test Cleaning Supervisor",
        # Facility counts
        "facility_floor": "15",
        "facility_ground_parking": "2",
        "facility_basement": "1",
        "facility_podium": "1",
        "facility_gym_room": "1",
        "facility_swimming_pool": "1",
        "facility_washroom_male": "8",
        "facility_washroom_female": "6",
        "facility_changing_room": "2",
        "facility_play_kids_place": "1",
        "facility_garbage_room": "2",
        "facility_floor_chute_room": "15",
        "facility_staircase": "4",
        "facility_floor_service_room": "10",
        "facility_cleaner_count": "18",
        # Scope
        "scope_offices": "True",
        "scope_toilets": "True",
        "scope_hallways": "True",
        "scope_kitchen": "True",
        "scope_exterior": "True",
        "scope_special_care": "False",
        # Deep cleaning, waste, special considerations, safety
        "deep_clean_required": "Yes",
        "deep_clean_areas": "All washrooms and garbage rooms.",
        "waste_disposal_required": "Yes",
        "waste_disposal_method": "Municipality-approved contractor.",
        "restricted_access": "Server rooms and data centers.",
        "pest_control": "Required for garbage rooms and basement.",
        "working_hours": "24/7 coverage with staggered shifts.",
        "required_team_size": "22",
        "site_access_requirements": "Security ID badges and safety induction.",
        "general_comments": "Overall site in acceptable condition; improvements planned for high-traffic zones.",
        # Photos (simple placeholders, enough to exercise photo grid)
        "photos": [
            {"url": SIG_PLACEHOLDER},
            {"url": SIG_PLACEHOLDER},
        ],
        # Supervisor
        "supervisor_comments": "Assessment completed. Extra focus needed on podium and garbage rooms.",
        "supervisor_signature": SIG_PLACEHOLDER,
        # Operations Manager
        "operations_manager_comments": "Approve additional manpower for peak hours.",
        "operations_manager_signature": SIG_PLACEHOLDER,
        # Business Development
        "business_dev_comments": "Client is open to extended contract if KPIs improve.",
        "business_dev_signature": SIG_PLACEHOLDER,
        # Procurement
        "procurement_comments": "Order advanced floor scrubber and eco-friendly chemicals.",
        "procurement_signature": SIG_PLACEHOLDER,
        # General Manager (final approval)
        "general_manager_comments": "Approved. Proceed with enhanced cleaning plan and equipment purchase.",
        "general_manager_signature": SIG_PLACEHOLDER,
    }


def main():
    _ensure_project_root()

    from module_cleaning.cleaning_generators import create_pdf_report

    out_dir = os.path.join(PROJECT_ROOT, "test_output", "inspection_forms_test")
    os.makedirs(out_dir, exist_ok=True)

    data = sample_cleaning_gm_data()

    print(f"Output directory: {out_dir}")
    print("Sample Cleaning + GM data:")
    print(f"  Project: {data['project_name']}")
    print(f"  Visit date: {data['date_of_visit']}")
    print(f"  Photos: {len(data['photos'])}")
    print("  Includes reviewer comments/signatures for:")
    print("    - Supervisor")
    print("    - Operations Manager")
    print("    - Business Development")
    print("    - Procurement")
    print("    - General Manager (final approval)")

    print("\nGenerating Cleaning PDF (full workflow up to GM)...")
    pdf_path = create_pdf_report(data, out_dir)
    print(f"  Created: {os.path.basename(pdf_path)}")
    print("\nCleaning GM workflow PDF test completed successfully.")
    print(f"File saved to: {pdf_path}")


if __name__ == "__main__":
    main()

