#!/usr/bin/env python3
"""
HR Module Auto-Test: Fill all HR forms, submit, and download Word + PDF.

Run with the Flask app already running (python Injaaz.py). Uses admin credentials
to submit forms and download DOCX/PDF. Output saved to test_output/hr_forms_<timestamp>/.

Usage:
    python tests/hr_auto_test.py
    python tests/hr_auto_test.py --base-url http://127.0.0.1:5000
    python tests/hr_auto_test.py --user admin --password Admin@123
"""
import os
import sys
import argparse
import base64
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

# Minimal valid 1x1 transparent PNG (signature placeholder)
SIG_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
SIGNATURE_DATA_URL = f"data:image/png;base64,{SIG_PNG_B64}"

# All HR form types that support DOCX/PDF
HR_FORM_TYPES = [
    "leave_application",
    "commencement",
    "duty_resumption",
    "passport_release",
    "grievance",
    "visa_renewal",
    "interview_assessment",
    "staff_appraisal",
    "station_clearance",
    "performance_evaluation",
    "contract_renewal",
]

# Common sample fields
COMMON = {
    "employee_name": "Auto Test Employee",
    "employee_id": "INJ-TEST-001",
    "job_title": "Test Engineer",
    "department": "IT",
    "today_date": datetime.now().strftime("%Y-%m-%d"),
    "employee_signature": SIGNATURE_DATA_URL,
    "employee_sign_date": datetime.now().strftime("%Y-%m-%d"),
    "form_date": datetime.now().strftime("%Y-%m-%d"),
    "sign_date": datetime.now().strftime("%Y-%m-%d"),
}


def get_sample_form_data(form_type: str) -> dict:
    """Sample form data per form type to fill and sign."""
    base = {**COMMON}
    base["form_type"] = form_type

    if form_type == "leave_application":
        base.update({
            "leave_type": "annual",
            "total_days_requested": "5",
            "first_day_of_leave": "2026-03-15",
            "last_day_of_leave": "2026-03-19",
            "date_returning_to_work": "2026-03-22",
            "salary_advance": "no",
            "replacement_name": "John Replacement",
            "replacement_signature": SIGNATURE_DATA_URL,
            "last_leave_date": "2025-12-01",
            "date_of_joining": "2024-01-15",
            "mobile_no": "+971 50 123 4567",
            "telephone_reachable": "+971 50 123 4567",
        })
    elif form_type == "commencement":
        base.update({
            "position": "Test Engineer",
            "organization": "INJAAZ",
            "contacts": "+971 50 123 4567",
            "date_of_joining": "2026-03-01",
            "bank_name": "Test Bank",
            "bank_branch": "Dubai Main",
            "account_number": "1234567890",
            "reporting_to_name": "Jane Manager",
            "reporting_to_designation": "Team Lead",
            "reporting_to_contact": "+971 50 999 8888",
            "reporting_to_signature": SIGNATURE_DATA_URL,
            "reporting_sign_date": datetime.now().strftime("%Y-%m-%d"),
        })
    elif form_type == "duty_resumption":
        base.update({
            "requester": "Auto Test",
            "company": "INJAAZ LLC",
            "leave_started": "2026-02-01",
            "leave_ended": "2026-02-28",
            "planned_resumption_date": "2026-03-01",
            "actual_resumption_date": "2026-03-01",
            "note": "Auto-test resumption",
        })
    elif form_type == "passport_release":
        base.update({
            "passport_form_type": "release",
            "requester": "Auto Test",
            "project": "Test Project",
            "release_date": "2026-03-15",
            "purpose_of_release": "Auto-test purpose",
        })
    elif form_type == "grievance":
        base.update({
            "complainant_name": "Auto Test",
            "complainant_id": "INJ-TEST-001",
            "complainant_designation": "Engineer",
            "complainant_contact": "+971 50 123 4567",
            "date_of_incident": "2026-03-01",
            "description": "Auto-test grievance description.",
            "complaint_description": "Auto-test grievance description.",
            "complainant_signature": SIGNATURE_DATA_URL,
        })
    elif form_type == "visa_renewal":
        base.update({
            "designation": "Engineer",
            "position": "Test Engineer",
            "nationality": "UAE",
            "passport_number": "A12345678",
            "current_expiry": "2026-06-30",
            "years_completed": "2",
            "decision": "continue",
        })
    elif form_type == "interview_assessment":
        base.update({
            "candidate_name": "Test Candidate",
            "position_applied": "Engineer",
            "position_title": "Engineer",
            "academic_qualification": "B.Sc. Computer Science",
            "age": "28",
            "gender": "Male",
            "marital_status": "Single",
            "dependents": "0",
            "nationality": "UAE",
            "current_job_title": "Junior Engineer",
            "years_experience": "3",
            "current_salary": "8000",
            "expected_salary": "10000",
            "interview_date": datetime.now().strftime("%Y-%m-%d"),
            "interview_by": "HR Manager",
            "rating_turnout": "good",
            "rating_confidence": "v_good",
            "rating_mental_alertness": "good",
            "rating_maturity": "good",
            "rating_communication": "v_good",
            "rating_technical": "good",
            "rating_training": "good",
            "rating_experience": "good",
            "rating_overall": "good",
            "overall_assessment": "Suitable candidate for the position.",
            "recommendation": "Recommended",
            "interviewer_name": "Interviewer Name",
            "interviewer_designation": "HR Manager",
            "interviewer_signature": SIGNATURE_DATA_URL,
        })
    elif form_type == "staff_appraisal":
        base.update({
            "designation": "Engineer",
            "position": "Test Engineer",
            "review_period": "Jan 2026 - Mar 2026",
            "evaluator_name": "Evaluator Name",
            "evaluator_designation": "Manager",
            "evaluator_signature": SIGNATURE_DATA_URL,
            "evaluator_date": datetime.now().strftime("%Y-%m-%d"),
            "rating_punctuality": "4",
            "rating_job_knowledge": "5",
            "rating_quality": "4",
            "rating_productivity": "4",
            "rating_communication": "5",
            "rating_teamwork": "4",
            "rating_problem_solving": "4",
            "rating_adaptability": "5",
            "rating_leadership": "4",
            "total_score": "4.3",
            "employee_strengths": "Consistent performer, good team player.",
        })
    elif form_type == "station_clearance":
        base.update({
            "position": "Test Engineer",
            "employment_date": "2024-01-15",
            "last_working_date": "2026-03-31",
            "section": "IT Operations",
            "type_of_departure": "resignation",
            "tasks_handed_over": "on",
            "documents_handed_over": "on",
            "files_handed_over": "on",
            "keys_returned": "on",
            "toolbox_returned": "on",
            "access_card_returned": "on",
            "dept_date_1": "2026-03-30",
            "dept_date_2": "2026-03-30",
            "email_cancelled": "on",
            "software_hardware_returned": "on",
            "laptop_returned": "on",
            "file_shifted": "on",
            "dues_paid": "on",
            "medical_card_returned": "on",
            "eos_transfer": "on",
            "remarks": "All clearances completed successfully.",
        })
    elif form_type == "performance_evaluation":
        base.update({
            "designation": "Engineer",
            "review_period": "2026 Q1",
            "evaluation_done_by": "Jane Manager",
            "evaluator_name": "Evaluator Name",
            "evaluator_designation": "Manager",
            "evaluator_signature": SIGNATURE_DATA_URL,
            "evaluator_date": datetime.now().strftime("%Y-%m-%d"),
            "date_of_evaluation": datetime.now().strftime("%Y-%m-%d"),
            "score_01": "8",
            "score_02": "9",
            "score_03": "8",
            "score_04": "7",
            "score_05": "9",
            "score_06": "8",
            "score_07": "8",
            "score_08": "9",
            "score_09": "7",
            "score_10": "8",
            "overall_score": "81",
            "evaluator_observation": "Strong performance during the review period.",
            "area_of_concern": "None.",
            "training_required": "Advanced certification recommended.",
        })
    elif form_type == "contract_renewal":
        base.update({
            "designation": "Engineer",
            "date_of_joining": "2024-01-15",
            "contract_end_date": "2026-06-30",
            "date_of_evaluation": datetime.now().strftime("%Y-%m-%d"),
            "evaluation_by": "Jane Manager",
            "evaluator_signature": SIGNATURE_DATA_URL,
            "evaluator_date": datetime.now().strftime("%Y-%m-%d"),
            "recommendation": "renew",
            "overall_score": "4.2",
            "strength": "Reliable, meets deadlines, good technical skills.",
            "areas_for_improvement": "Leadership development.",
            "rating_01a": "4",
            "rating_01b": "5",
            "rating_01c": "4",
            "rating_01d": "4",
            "rating_01e": "4",
            "rating_02a": "5",
            "rating_02b": "4",
            "rating_02c": "4",
            "rating_02d": "4",
            "rating_02e": "4",
            "rating_03a": "4",
            "rating_03b": "5",
            "rating_03c": "4",
            "rating_03d": "4",
            "rating_03e": "4",
            "rating_04a": "5",
            "rating_04b": "4",
            "rating_04c": "4",
        })

    return base


def run_test(base_url: str, username: str, password: str, output_dir: Path) -> bool:
    """Run full HR auto-test: login, submit all forms, download DOCX and PDF."""
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    # 1. Login
    print("Logging in...")
    r = session.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
    )
    if not r.ok:
        print(f"Login failed: {r.status_code} {r.text}")
        return False
    data = r.json()
    token = data.get("access_token")
    if not token:
        print("Login response missing access_token")
        return False
    session.headers["Authorization"] = f"Bearer {token}"
    print("Login OK\n")

    submissions = []

    # 2. Submit each form
    for ft in HR_FORM_TYPES:
        print(f"Submitting {ft}...")
        payload = get_sample_form_data(ft)
        r = session.post(f"{base_url}/hr/api/submit", json=payload)
        if not r.ok:
            print(f"  FAIL: {r.status_code} {r.text[:200]}")
            continue
        sub = r.json()
        sub_id = sub.get("submission_id")
        if sub_id:
            submissions.append((ft, sub_id))
            print(f"  OK -> {sub_id}")
        else:
            print(f"  FAIL: no submission_id in response")

    if not submissions:
        print("\nNo submissions created. Cannot download.")
        return False

    # 3. Download DOCX and PDF for each submission
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading to {output_dir}...")

    for ft, sub_id in submissions:
        # DOCX
        r = session.get(f"{base_url}/hr/download-docx/{sub_id}")
        if r.ok:
            path = output_dir / f"{ft}_{sub_id}.docx"
            path.write_bytes(r.content)
            print(f"  {ft}: DOCX saved -> {path.name}")
        else:
            print(f"  {ft}: DOCX failed {r.status_code}")

        # PDF
        r = session.get(f"{base_url}/hr/download-pdf/{sub_id}")
        if r.ok:
            path = output_dir / f"{ft}_{sub_id}.pdf"
            path.write_bytes(r.content)
            print(f"  {ft}: PDF saved -> {path.name}")
        else:
            print(f"  {ft}: PDF failed {r.status_code}")

    print(f"\nDone. Files in: {output_dir.absolute()}")
    return True


def main():
    parser = argparse.ArgumentParser(description="HR module auto-test: fill forms, submit, download Word + PDF")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Flask app base URL")
    parser.add_argument("--user", default=os.environ.get("HR_TEST_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("HR_TEST_PASSWORD", "Admin@123"))
    parser.add_argument("--output", default=None, help="Output folder (default: test_output/hr_forms_<timestamp>)")
    args = parser.parse_args()

    out = Path(args.output) if args.output else Path("test_output") / f"hr_forms_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("HR Module Auto-Test")
    print("=" * 50)
    print(f"Base URL: {args.base_url}")
    print(f"User: {args.user}")
    print(f"Output: {out}")
    print()

    ok = run_test(args.base_url, args.user, args.password, out)
    if ok and sys.platform == "win32":
        os.startfile(out)
    elif ok:
        print("Open folder to view downloaded files.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
