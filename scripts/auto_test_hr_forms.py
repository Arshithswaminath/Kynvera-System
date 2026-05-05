#!/usr/bin/env python3
"""
Auto Test: Fill all HR module form fields with sample data and download DOCX + PDF.
Run from project root: python scripts/auto_test_hr_forms.py
Output: test_output/hr_forms_YYYYMMDD_HHMMSS/
"""
import os
import sys
import uuid
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# Minimal 1x1 transparent PNG as base64 (for signature placeholders)
SIG_PLACEHOLDER = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def _date(days_offset=0):
    d = datetime.now()
    if days_offset:
        from datetime import timedelta
        d = d + timedelta(days=days_offset)
    return d.strftime("%Y-%m-%d")


def _mock_submission(module_type, form_data, submission_id=None):
    """Create a minimal mock Submission-like object for docx/pdf generation."""
    sid = submission_id or f"HR-{module_type.upper().replace('HR_', '')}-{uuid.uuid4().hex[:8].upper()}"
    return type("MockSubmission", (), {
        "module_type": f"hr_{module_type}" if not module_type.startswith("hr_") else module_type,
        "form_data": form_data,
        "submission_id": sid,
    })()


def _sample_form_data():
    """Sample form data for all HR forms - fills every field."""
    base = _date()
    base_d = _date(-30)
    base_f = _date(14)

    return {
        "leave": None,  # alias - uses leave_application data
        "leave_application": {
            "employee_name": "Ahmed Hassan",
            "job_title": "Facility Supervisor",
            "today_date": base,
            "employee_id": "INJ-0042",
            "department": "Operations",
            "date_of_joining": base_d,
            "mobile_no": "+971 50 123 4567",
            "last_leave_date": _date(-90),
            "leave_type": "annual",
            "total_days_requested": "5",
            "first_day_of_leave": base_f,
            "last_day_of_leave": _date(18),
            "date_returning_to_work": _date(19),
            "salary_advance": "no",
            "telephone_reachable": "+971 50 123 4567",
            "replacement_name": "Mohammed Ali",
            "employee_signature": SIG_PLACEHOLDER,
            "replacement_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
        },
        "commencement": {
            "employee_name": "Sara Mohammed",
            "position": "Administrative Assistant",
            "contacts": "+971 55 987 6543",
            "department": "Operations",
            "organization": "INJAAZ",
            "date_of_joining": base,
            "bank_name": "Emirates NBD",
            "bank_branch": "Dubai Mall Branch",
            "account_number": "AE123456789012345678901",
            "employee_sign_date": base,
            "reporting_to_name": "John Smith",
            "reporting_to_designation": "Operations Manager",
            "reporting_to_contact": "+971 50 111 2222",
            "reporting_sign_date": base,
            "employee_signature": SIG_PLACEHOLDER,
            "reporting_to_signature": SIG_PLACEHOLDER,
        },
        "duty_resumption": {
            "requester": "HR Department",
            "employee_name": "Ahmed Hassan",
            "employee_id": "INJ-0042",
            "job_title": "Facility Supervisor",
            "company": "INJAAZ LLC",
            "leave_started": _date(-30),
            "leave_ended": _date(-1),
            "planned_resumption_date": base,
            "actual_resumption_date": base,
            "note": "Resumed as scheduled",
            "line_manager_remarks": "Employee resumed duties on time. No issues noted.",
            "employee_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
        },
        "passport_release": {
            "requester": "HR Department",
            "employee_name": "Ahmed Hassan",
            "employee_id": "INJ-0042",
            "job_title": "Facility Supervisor",
            "project": "Main Site",
            "form_date": base,
            "passport_form_type": "release",
            "purpose_of_release": "Personal travel - visa renewal",
            "release_date": base,
            "employee_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
        },
        "grievance": {
            "complainant_name": "Ali Hassan",
            "complainant_id": "INJ-0033",
            "complainant_designation": "Technician",
            "date_of_incident": _date(-5),
            "shift_time": "Day Shift",
            "complainant_contact": "+971 50 444 5555",
            "issue_location": "site",
            "second_party_name": "Omar Khalid",
            "second_party_id": "INJ-0021",
            "second_party_department": "Maintenance",
            "place_of_incident": "Building A - Floor 2",
            "complaint_description": "Dispute over work assignment. Both parties were informed. Witness: Security guard.",
            "witnesses": "Security guard - Ahmed",
            "who_informed": "Site Supervisor",
            "attachment": "None",
            "statement_2nd_party": "yes",
            "hr_statement_verified": "Both parties",
            "hr_first_recurring": "1st",
            "hr_remarks": "Meeting scheduled for resolution.",
            "gm_remarks": "Approved for HR follow-up.",
            "complainant_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
        },
        "visa_renewal": {
            "employee_name": "Ahmed Hassan",
            "employee_id": "INJ-0042",
            "designation": "Facility Supervisor",
            "position": "Facility Supervisor",
            "department": "Operations",
            "employer": "INJAAZ LLC",
            "years_completed": "3",
            "date_of_joining": base_d,
            "passport_number": "A12345678",
            "nationality": "Egyptian",
            "current_visa_expiry": _date(60),
            "decision": "continue",
            "decision_display": "1. Continue my employment with the company for the next 2 years",
            "employee_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
        },
        "interview_assessment": {
            "candidate_name": "Fatima Al-Rashid",
            "position_applied": "Administrative Officer",
            "position_title": "Administrative Officer",
            "interview_date": base,
            "interviewer_name": "John Smith",
            "current_job_title": "Office Administrator",
            "nationality": "Jordanian",
            "years_experience": "5 years",
            "academic_qualification": "Bachelor's in Business Admin",
            "rating_turnout": "V. Good",
            "rating_confidence": "Good",
            "rating_mental_alertness": "Outstanding",
            "rating_maturity": "V. Good",
            "rating_communication": "Good",
            "rating_technical": "V. Good",
            "rating_training": "Good",
            "rating_experience": "V. Good",
            "rating_overall": "V. Good",
            "overall_assessment": "Strong communication skills and relevant UAE experience.",
            "eligibility": "Eligible - Recommended for hire.",
            "strengths": "Strong communication skills, relevant experience.",
            "weaknesses": "Limited UAE market knowledge.",
            "interviewer_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
        },
        "staff_appraisal": {
            "employee_name": "Ahmed Hassan",
            "employee_id": "INJ-0042",
            "department": "Operations",
            "designation": "Facility Supervisor",
            "position": "Facility Supervisor",
            "review_period": "Jan 2025 - Dec 2025",
            "appraisal_period": "Jan 2025 - Dec 2025",
            "review_date": base,
            "evaluator_name": "John Smith",
            "reviewer": "John Smith",
            "rating_punctuality": "4", "comments_punctuality": "Always on time.",
            "rating_job_knowledge": "5", "comments_job_knowledge": "Excellent knowledge.",
            "rating_quality": "4", "comments_quality": "High-quality output.",
            "rating_productivity": "4", "comments_productivity": "Consistent output.",
            "rating_communication": "3", "comments_communication": "Clear and concise.",
            "rating_teamwork": "5", "comments_teamwork": "Great team player.",
            "rating_problem_solving": "4", "comments_problem_solving": "Handles issues well.",
            "rating_adaptability": "4", "comments_adaptability": "Adapts quickly.",
            "rating_leadership": "3", "comments_leadership": "Shows initiative.",
            "total_score": "40",
            "employee_strengths": "Reliable, good team player.",
            "areas_for_improvement": "Time management for reports.",
            "employee_signature": SIG_PLACEHOLDER,
            "evaluator_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
        },
        "station_clearance": {
            "employee_name": "Omar Khalid",
            "employee_id": "INJ-0021",
            "designation": "Technician",
            "position": "Technician",
            "department": "Maintenance",
            "date_of_joining": _date(-365),
            "last_working_day": base,
            "last_working_date": base,
            "departure_reason": "resignation",
            "type_of_departure": "resignation",
            "tasks_handed_over": "on",
            "documents_handed_over": "on",
            "files_handed_over": "on",
            "keys_returned": "on",
            "toolbox_returned": "on",
            "access_card_returned": "on",
            "email_cancelled": "on",
            "software_hardware_returned": "on",
            "laptop_returned": "on",
            "file_shifted": "on",
            "dues_paid": "on",
            "medical_card_returned": "on",
            "eos_transfer": "on",
            "employee_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
        },
        "performance_evaluation": {
            "employee_name": "Ahmed Hassan",
            "employee_id": "INJ-0042",
            "department": "Operations",
            "designation": "Facility Supervisor",
            "date_of_evaluation": base,
            "date_of_joining": base_d,
            "evaluation_done_by": "John Smith",
            "score_01": "4",
            "score_02": "5",
            "score_03": "4",
            "score_04": "4",
            "score_05": "5",
            "score_06": "4",
            "score_07": "4",
            "score_08": "5",
            "score_09": "4",
            "score_10": "4",
            "overall_score": "4.3",
            "evaluator_name": "John Smith",
            "evaluator_designation": "Operations Manager",
            "evaluator_observation": "Consistent performer, good attitude.",
            "area_of_concern": "None",
            "training_required": "Advanced Excel",
            "employee_comments": "Thank you for the feedback.",
            "employee_sign_date": base,
            "evaluator_sign_date": base,
            "concern_incharge_name": "N/A",
            "incharge_comments": "N/A",
            "gm_remarks": "Approved.",
            "hr_remarks": "Noted.",
            "employee_signature": SIG_PLACEHOLDER,
            "evaluator_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
        },
        "contract_renewal": {
            "employee_name": "Ahmed Hassan",
            "employee_id": "INJ-0042",
            "department": "Operations",
            "designation": "Facility Supervisor",
            "date_of_joining": base_d,
            "current_contract_end": _date(30),
            "contract_end_date": _date(30),
            "date_of_evaluation": base,
            "evaluation_by": "John Smith",
            "evaluator_name": "John Smith",
            "evaluator_date": base,
            "rating_01a": "4",
            "rating_01b": "5",
            "rating_01c": "4",
            "rating_01d": "4",
            "rating_01e": "4",
            "rating_02a": "4",
            "rating_02b": "4",
            "rating_02c": "4",
            "rating_02d": "5",
            "rating_02e": "4",
            "rating_03a": "5",
            "rating_03b": "4",
            "rating_03c": "4",
            "rating_03d": "4",
            "rating_03e": "5",
            "rating_04a": "4",
            "rating_04b": "4",
            "rating_04c": "4",
            "areas_for_improvement": "Report submission timeliness.",
            "strength": "Reliable team player with strong technical skills.",
            "recommendation": "Recommend renewal for 2 years.",
            "comments_01": "Good performance.",
            "comments_02": "Team collaboration excellent.",
            "comments_03": "Technical skills adequate.",
            "comments_04": "Recommend renewal.",
            "evaluator_signature": SIG_PLACEHOLDER,
            "hr_signature": SIG_PLACEHOLDER,
            "gm_signature": SIG_PLACEHOLDER,
        },
    }


def main():
    from io import BytesIO
    from module_hr.docx_service import generate_hr_docx, get_supported_docx_forms
    from module_hr.pdf_service import generate_hr_pdf, get_supported_pdf_forms

    out_dir = os.path.join(PROJECT_ROOT, "test_output", f"hr_forms_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"Output directory: {out_dir}")

    sample_data = _sample_form_data()
    docx_forms = get_supported_docx_forms()
    pdf_forms = get_supported_pdf_forms()

    results = {"docx": [], "pdf": []}

    for form_type in docx_forms:
        form_data = sample_data.get(form_type) if form_type != "leave" else sample_data.get("leave_application")
        if not form_data:
            print(f"  [SKIP] {form_type}: no sample data")
            continue

        submission = _mock_submission(form_type, form_data)
        slug = form_type.replace("_", " ").replace(" ", "_").lower()

        # DOCX
        try:
            docx_path = os.path.join(out_dir, f"{slug}_{submission.submission_id}.docx")
            with open(docx_path, "wb") as f:
                generate_hr_docx(submission, f)
            results["docx"].append(docx_path)
            print(f"  [OK] DOCX: {form_type}")
        except Exception as e:
            print(f"  [FAIL] DOCX {form_type}: {e}")

        # PDF
        if form_type in pdf_forms:
            try:
                pdf_path = os.path.join(out_dir, f"{slug}_{submission.submission_id}.pdf")
                with open(pdf_path, "wb") as f:
                    ok, err = generate_hr_pdf(submission, f)
                    if not ok:
                        raise RuntimeError(err or "PDF generation failed")
                results["pdf"].append(pdf_path)
                print(f"  [OK] PDF: {form_type}")
            except Exception as e:
                print(f"  [FAIL] PDF {form_type}: {e}")

    print(f"\nDone. Generated {len(results['docx'])} DOCX, {len(results['pdf'])} PDF in {out_dir}")


if __name__ == "__main__":
    main()
