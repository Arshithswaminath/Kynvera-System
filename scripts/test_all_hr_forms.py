#!/usr/bin/env python3
"""
Auto-test all HR document forms - fill all fields and generate DOCX/PDF.

Generates sample-filled documents for every HR form type to verify:
- Template placeholders are correctly populated
- No unresolved {{ placeholder }} tokens remain
- Document structure is preserved

Usage:
  python scripts/test_all_hr_forms.py
  python scripts/test_all_hr_forms.py --pdf
  python scripts/test_all_hr_forms.py --check   # Run fidelity check after generation
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def _mock_submission(module_type: str, form_data: dict, submission_id: str | None = None):
    """Create a mock Submission-like object for docx/pdf generation."""
    sid = submission_id or str(uuid.uuid4())[:8].upper()
    return type("Submission", (), {
        "module_type": f"hr_{module_type}",
        "form_data": form_data,
        "submission_id": f"HR-{module_type.upper().replace('_', '-')}-{sid}",
        "created_at": datetime.now(),
    })()


def _sample_form_data(form_type: str) -> dict:
    """Return fully populated sample form data for each HR form type."""
    today = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    next_month = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    common = {
        "employee_name": "Ahmed Hassan Al-Rashid",
        "employee_id": "EMP-2024-0042",
        "job_title": "Senior Project Engineer",
        "position": "Senior Project Engineer",
        "designation": "Senior Project Engineer",
        "department": "Engineering",
        "organization": "INJAAZ",
        "company": "INJAAZ",
        "mobile_no": "+971 50 123 4567",
        "contact_number": "+971 50 123 4567",
    }

    samples = {
        "commencement": {
            **common,
            "position": "Senior Project Engineer",
            "contacts": "+971 50 123 4567",
            "department": "Engineering",
            "organization": "INJAAZ",
            "date_of_joining": today,
            "bank_name": "Emirates NBD",
            "bank_branch": "Dubai Mall Branch",
            "account_number": "AE12 3456 7890 1234 5678 901",
            "employee_sign_date": today,
            "reporting_to_name": "Mohammed Khalid",
            "reporting_to_designation": "Engineering Manager",
            "reporting_to_contact": "+971 50 987 6543",
            "reporting_sign_date": today,
        },
        "leave_application": {
            **common,
            "today_date": today,
            "date_of_joining": "2022-03-15",
            "last_leave_date": "2024-01-10",
            "leave_type": "annual",
            "first_day_of_leave": next_week,
            "last_day_of_leave": next_month,
            "start_date": next_week,
            "end_date": next_month,
            "total_days_requested": "14",
            "total_days": "14",
            "date_returning_to_work": (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d"),
            "telephone_reachable": "+971 50 123 4567",
            "salary_advance": "no",
            "replacement_name": "Sara Mohammed",
            "hr_checked": "Verified",
            "hr_comments": "Leave balance confirmed. Approved.",
            "hr_balance_cf": "21",
            "hr_contract_year": "2024-2025",
            "hr_paid": "14",
            "hr_unpaid": "0",
            "hr_date": today,
        },
        "leave": {
            **common,
            "today_date": today,
            "date_of_joining": "2022-03-15",
            "last_leave_date": "2024-01-10",
            "leave_type": "sick",
            "first_day_of_leave": last_week,
            "last_day_of_leave": last_week,
            "total_days_requested": "1",
            "date_returning_to_work": (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d"),
            "telephone_reachable": "+971 50 123 4567",
            "salary_advance": "no",
            "replacement_name": "Omar Ali",
            "hr_checked": "Verified",
            "hr_comments": "Medical certificate received.",
            "hr_balance_cf": "20",
            "hr_contract_year": "2024-2025",
            "hr_paid": "1",
            "hr_unpaid": "0",
            "hr_date": today,
        },
        "duty_resumption": {
            **common,
            "requester": "Ahmed Hassan Al-Rashid",
            "leave_started": "2024-02-01",
            "leave_ended": "2024-02-15",
            "planned_resumption_date": "2024-02-16",
            "actual_resumption_date": "2024-02-16",
            "note": "Resumed duty as scheduled. All handover completed.",
            "line_manager_remarks": "Welcome back. Handover reviewed.",
            "sign_date": today,
        },
        "passport_release": {
            **common,
            "requester": "Ahmed Hassan Al-Rashid",
            "project": "Dubai Marina Tower",
            "form_date": today,
            "purpose_of_release": "Visa renewal at Amer center",
            "release_date": today,
        },
        "grievance": {
            "complainant_name": "Ahmed Hassan Al-Rashid",
            "complainant_id": "EMP-2024-0042",
            "complainant_designation": "Senior Project Engineer",
            "date_of_incident": last_week,
            "shift_time": "Day shift, 08:00-17:00",
            "complainant_contact": "+971 50 123 4567",
            "second_party_name": "Omar Khalil",
            "second_party_id": "EMP-2023-0015",
            "second_party_department": "Operations",
            "place_of_incident": "Site office - Building A",
            "second_party_contact": "+971 50 555 1234",
            "complaint_description": "Unprofessional behavior during project meeting. Raised voice and made inappropriate comments.",
            "complaint": "Unprofessional behavior during project meeting.",
            "witnesses": "Sara Mohammed, Ali Hassan",
            "who_informed": "Line Manager - Mohammed Khalid",
            "attachment": "Meeting notes attached",
            "hr_remarks": "Investigation initiated. Both parties interviewed.",
            "gm_remarks": "Follow up in 2 weeks.",
        },
        "performance_evaluation": {
            **common,
            "date_of_evaluation": today,
            "date_of_joining": "2022-03-15",
            "evaluation_done_by": "Mohammed Khalid",
            "score_01": "4",
            "score_02": "4.5",
            "score_03": "4",
            "score_04": "5",
            "score_05": "4",
            "score_06": "4.5",
            "score_07": "4",
            "score_08": "4",
            "score_09": "4.5",
            "score_10": "4",
            "overall_score": "4.25",
            "evaluator_name": "Mohammed Khalid",
            "evaluator_designation": "Engineering Manager",
            "evaluator_observation": "Consistent performer. Strong technical skills. Good team player.",
            "area_of_concern": "Time management during peak project phases.",
            "training_required": "Advanced project management certification.",
            "employee_comments": "Thank you for the feedback. Will work on time management.",
            "employee_sign_date": today,
            "evaluator_sign_date": today,
            "concern_incharge_name": "Mohammed Khalid",
            "incharge_comments": "Agreed. Training scheduled for Q2.",
            "gm_remarks": "Approved. Good performance.",
            "hr_remarks": "Evaluation complete. On file.",
        },
        "interview_assessment": {
            "candidate_name": "Fatima Abdullah",
            "position_title": "Junior Engineer",
            "position_applied": "Junior Engineer",
            "academic_qualification": "B.E. Civil Engineering, UAE University",
            "age": "24",
            "marital_status": "Single",
            "dependents": "0",
            "nationality": "UAE",
            "gender": "Female",
            "current_job_title": "Graduate Trainee",
            "years_experience": "1",
            "current_salary": "8,000 AED",
            "expected_salary": "10,000 AED",
            "interview_date": today,
            "interview_by": "Mohammed Khalid, Sara Ahmed",
            "rating_turnout": "v_good",
            "rating_confidence": "good",
            "rating_mental_alertness": "v_good",
            "rating_maturity": "good",
            "rating_communication": "v_good",
            "rating_technical": "good",
            "rating_training": "good",
            "rating_experience": "fair",
            "rating_overall": "good",
            "overall_assessment": "Suitable candidate. Recommend for second round.",
            "eligibility": "Eligible",
            "hr_comments": "References checked. Clear.",
            "gm_comments": "Proceed with offer.",
        },
        "staff_appraisal": {
            **common,
            "appraisal_period": "Jan 2024 - Dec 2024",
            "review_period": "Jan 2024 - Dec 2024",
            "reviewer": "Mohammed Khalid",
            "rating_punctuality": "4",
            "comments_punctuality": "Consistently on time.",
            "rating_job_knowledge": "4.5",
            "comments_job_knowledge": "Strong technical knowledge.",
            "rating_quality": "4",
            "comments_quality": "High quality deliverables.",
            "rating_productivity": "4",
            "comments_productivity": "Meets deadlines.",
            "rating_communication": "4",
            "comments_communication": "Clear and professional.",
            "rating_teamwork": "4.5",
            "comments_teamwork": "Excellent collaborator.",
            "rating_problem_solving": "4",
            "comments_problem_solving": "Analytical approach.",
            "rating_adaptability": "4",
            "comments_adaptability": "Adapts well to changes.",
            "rating_leadership": "3.5",
            "comments_leadership": "Developing leadership skills.",
            "total_score": "41",
            "employee_strengths": "Technical expertise, teamwork, reliability.",
            "hr_comments": "Appraisal complete.",
            "gm_comments": "Approved.",
        },
        "station_clearance": {
            **common,
            "employment_date": "2022-03-15",
            "date_of_joining": "2022-03-15",
            "section": "Civil Engineering",
            "type_of_departure": "resignation",
            "departure_reason": "resignation",
            "last_working_date": today,
            "last_working_day": today,
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
            "remarks": "All clearance completed. No pending items.",
        },
        "visa_renewal": {
            **common,
            "form_date": today,
            "employer": "INJAAZ",
            "years_completed": "2",
            "decision": "continue",
            "hr_comments": "Visa renewal initiated.",
            "gm_comments": "Approved.",
        },
        "contract_renewal": {
            **common,
            "date_of_evaluation": today,
            "date_of_joining": "2022-03-15",
            "contract_end_date": "2025-03-14",
            "current_contract_end": "2025-03-14",
            "evaluation_by": "Mohammed Khalid",
            "evaluator_name": "Mohammed Khalid",
            "rating_01a": "4",
            "rating_01b": "4",
            "rating_01c": "4.5",
            "rating_01d": "4",
            "rating_01e": "4",
            "rating_02a": "4",
            "rating_02b": "4.5",
            "rating_02c": "4",
            "rating_02d": "4",
            "rating_02e": "4",
            "rating_03a": "4",
            "rating_03b": "4.5",
            "rating_03c": "4",
            "rating_03d": "4",
            "rating_03e": "4",
            "rating_04a": "4.5",
            "rating_04b": "4",
            "rating_04c": "4",
            "comments_01": "Strong performance in task completion.",
            "comments_02": "Good attitude and professionalism.",
            "comments_03": "Effective communicator.",
            "comments_04": "Reliable attendance.",
            "strength": "Technical expertise, teamwork, meeting deadlines.",
            "areas_for_improvement": "Time management during peak periods.",
            "overall_score": "4.1",
            "recommendation": "renew",
            "evaluator_date": today,
        },
    }

    return samples.get(form_type, common)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-test all HR document forms.")
    parser.add_argument("--pdf", action="store_true", help="Also generate PDF for each form")
    parser.add_argument("--check", action="store_true", help="Run fidelity check after generation")
    parser.add_argument("--out", type=str, default="", help="Output directory (default: test_output/hr_forms_<timestamp>)")
    args = parser.parse_args()

    from module_hr.docx_service import generate_hr_docx, get_supported_docx_forms

    form_types = get_supported_docx_forms()
    if not form_types:
        print("ERROR: No supported DOCX forms found.")
        return 1

    out_dir = Path(args.out) if args.out else BASE / "test_output" / f"hr_forms_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")
    print(f"Forms to generate: {len(form_types)}")
    print()

    ok = 0
    fail = 0
    for form_type in form_types:
        form_data = _sample_form_data(form_type)
        submission = _mock_submission(form_type, form_data)

        docx_path = out_dir / f"{form_type}_{submission.submission_id}.docx"
        try:
            with open(docx_path, "wb") as f:
                result = generate_hr_docx(submission, f)
            if isinstance(result, tuple):
                generated, _ = result
            else:
                generated = result
            if generated:
                print(f"  [OK] {form_type} -> {docx_path.name}")
                ok += 1

                if args.pdf:
                    try:
                        from module_hr.pdf_service import generate_hr_pdf
                        pdf_path = out_dir / f"{form_type}_{submission.submission_id}.pdf"
                        with open(pdf_path, "wb") as pf:
                            gen_ok, err = generate_hr_pdf(submission, pf)
                        if gen_ok:
                            print(f"       PDF -> {pdf_path.name}")
                        else:
                            print(f"       PDF failed: {err}")
                    except Exception as e:
                        print(f"       PDF failed: {e}")
            else:
                print(f"  [SKIP] {form_type} (not supported)")
        except FileNotFoundError as e:
            print(f"  [FAIL] {form_type}: {e}")
            fail += 1
        except Exception as e:
            print(f"  [FAIL] {form_type}: {e}")
            fail += 1

    print()
    print(f"Summary: OK={ok} FAIL={fail}")

    if args.check and ok > 0:
        print()
        print("Running fidelity check...")
        check_script = BASE / "scripts" / "check_hr_docx_fidelity.py"
        if check_script.exists():
            import subprocess
            r = subprocess.run([sys.executable, str(check_script), "--generated-dir", str(out_dir)], cwd=str(BASE))
            if r.returncode != 0:
                return r.returncode

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
