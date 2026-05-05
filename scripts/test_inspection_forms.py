"""Auto-test HVAC, Civil, and Cleaning inspection form PDF/Excel generation."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Placeholder signature and photo (valid PNG - small gray square)
SIG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
# Placeholder photo (valid 1x1 gray PNG)
PHOTO = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQz0AEABJAAvPvMGoAAAAASUVORK5CYII="
)

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "test_output", "inspection_forms_test")
os.makedirs(OUTDIR, exist_ok=True)

# HVAC sample data
HVAC_DATA = {
    "site_name": "Test Site - Ajman Tower",
    "visit_date": "2026-03-12",
    "items": [
        {
            "asset": "Chiller Unit A",
            "system": "HVAC",
            "description": "Main chiller for building cooling",
            "quantity": "1",
            "brand": "Carrier",
            "specification": "500 TR",
            "comments": "In good condition",
            "photos": [PHOTO, PHOTO],
        },
        {
            "asset": "AHU-01",
            "system": "HVAC",
            "description": "Air handling unit Floor 1",
            "quantity": "1",
            "brand": "Trane",
            "specification": "10,000 CFM",
            "comments": "Filter replacement recommended",
            "photos": [PHOTO],
        },
    ],
    "supervisor_signature": SIG,
    "supervisor_comments": "Inspection completed. Minor maintenance required.",
}

# Civil sample data
CIVIL_DATA = {
    "project_name": "Test Civil Project",
    "location": "Dubai Marina",
    "visit_date": "2026-03-12",
    "inspector_name": "Ahmed Al-Rashid",
    "description_of_work": "Structural inspection and assessment",
    "work_items": [
        {
            "description": "Foundation inspection",
            "quantity": "1",
            "material": "Concrete",
            "material_qty": "N/A",
            "price": "N/A",
            "labour": "N/A",
            "photos": [PHOTO],
        },
        {
            "description": "Wall crack assessment",
            "quantity": "3",
            "material": "N/A",
            "material_qty": "N/A",
            "price": "N/A",
            "labour": "N/A",
            "photos": [PHOTO, PHOTO],
        },
    ],
    "supervisor_signature": SIG,
    "supervisor_comments": "Civil works inspection completed.",
}

# Cleaning sample data
CLEANING_DATA = {
    "project_name": "Test Cleaning Site",
    "date_of_visit": "2026-03-12",
    "technician_name": "Fatima Hassan",
    "facility_floor": "5",
    "facility_ground_parking": "2",
    "facility_basement": "1",
    "facility_podium": "1",
    "facility_gym_room": "1",
    "facility_swimming_pool": "1",
    "facility_washroom_male": "4",
    "facility_washroom_female": "4",
    "facility_changing_room": "2",
    "facility_play_kids_place": "0",
    "facility_garbage_room": "1",
    "facility_floor_chute_room": "1",
    "facility_staircase": "2",
    "facility_floor_service_room": "1",
    "facility_cleaner_count": "8",
    "scope_offices": "True",
    "scope_toilets": "True",
    "scope_hallways": "True",
    "scope_kitchen": "True",
    "scope_exterior": "False",
    "scope_special_care": "True",
    "deep_clean_required": "Yes",
    "deep_clean_areas": "Washrooms, Kitchen",
    "waste_disposal_required": "Yes",
    "waste_disposal_method": "Central collection",
    "restricted_access": "Server room",
    "pest_control": "Monthly",
    "working_hours": "06:00 - 22:00",
    "required_team_size": "8",
    "site_access_requirements": "ID card required",
    "general_comments": "Site assessment completed. Standard cleaning scope.",
    "photos": [PHOTO, PHOTO, PHOTO],
    "supervisor_signature": SIG,
    "supervisor_comments": "Cleaning assessment approved.",
}


def run():
    from module_hvac_mep.hvac_generators import create_excel_report as hvac_excel, create_pdf_report as hvac_pdf
    from module_civil.civil_generators import create_excel_report as civil_excel, create_pdf_report as civil_pdf
    from module_cleaning.cleaning_generators import create_excel_report as cleaning_excel, create_pdf_report as cleaning_pdf

    results = []
    tests = [
        ("hvac_mep", HVAC_DATA, hvac_excel, hvac_pdf),
        ("civil", CIVIL_DATA, civil_excel, civil_pdf),
        ("cleaning", CLEANING_DATA, cleaning_excel, cleaning_pdf),
    ]
    for module_name, data, create_excel, create_pdf in tests:
        ok_excel = ok_pdf = False
        try:
            excel_path = create_excel(data, OUTDIR)
            ok_excel = excel_path and os.path.exists(excel_path)
        except Exception as e:
            print(f"  FAIL {module_name} Excel: {e}")
        try:
            pdf_path = create_pdf(data, OUTDIR)
            # Some generators return full path, others return basename
            full_pdf = pdf_path if pdf_path and os.path.isabs(pdf_path) else os.path.join(OUTDIR, pdf_path or "")
            ok_pdf = pdf_path and os.path.exists(full_pdf)
        except Exception as e:
            print(f"  FAIL {module_name} PDF: {e}")
        status = "OK" if (ok_excel and ok_pdf) else "FAIL"
        results.append((module_name, status, ok_excel, ok_pdf))
        print(f"  {status}  : {module_name} (Excel: {'OK' if ok_excel else 'FAIL'}, PDF: {'OK' if ok_pdf else 'FAIL'})")

    n_ok = sum(1 for _, s, _, _ in results if s == "OK")
    n_fail = len(results) - n_ok
    print(f"\nResults: {n_ok} OK, {n_fail} FAIL")
    print(f"Output: {os.path.abspath(OUTDIR)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
