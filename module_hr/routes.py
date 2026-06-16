"""
HR Module Routes
Handles HR forms: Leave, Termination, Long Vacation, Asset Transfer/Register
Workflow: Optional teammate sign-offs → management chain on PDF (Supervisor/RM→OM→GM→HR HO) → completed
"""
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, send_file, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm.attributes import flag_modified
from app.models import db, User, Submission, Notification
from common.form_data_utils import shallow_copy_form_data as _mutable_form_data
from common.datetime_utils import (
    format_naive_utc_in_dubai,
    format_now_in_dubai,
    naive_utc_isoformat_z,
    utc_now_naive,
)

from module_hr.hr_routed_signoffs import (
    collect_routed_signoffs_from_submit,
    email_all_routed_assignees,
    flatten_signers_notify,
    merge_routed_into_form_data_inplace,
    strip_teammate_signatures_from_submitter_payload,
)
from module_hr.replacement_signoff import (
    all_replacements_signed,
    apply_replacement_signature,
    pending_replacement_for_user,
    sync_replacement_display_fields,
)
from module_hr.hr_management_chain import (
    ALL_MGMT_WF_STATUSES,
    MGMT_CHAIN_KEY,
    WF_MGMT_GM,
    WF_MGMT_HR,
    apply_interview_chain_after_interviewer,
    apply_management_signature,
    first_management_workflow_status,
    get_interview_routing_ui_context,
    get_mgmt_chain_ui_context,
    has_management_chain,
    init_management_chain_on_submit,
    interview_routing_deferred_at_submit,
    lane_for_user,
    notify_current_management_signers,
    notify_submitter_management_final,
    pending_management_step_for_user,
    reject_management_submission,
    user_is_mgmt_chain_participant,
    user_mgmt_chain_completed_step,
)

from module_hr.hr_commencement_reporting import (
    dual_role_hint_for_user,
    dual_role_notify_message,
    resolve_commencement_reporting_to,
)

from .print_utils import render_form_for_print
from .docx_service import generate_hr_docx, get_supported_docx_forms
from .pdf_service import generate_hr_pdf, get_supported_pdf_forms

hr_bp = Blueprint('hr', __name__, template_folder='templates')


@hr_bp.context_processor
def _hr_embed_mode():
    """?embed=1 — hide main navbar in HR form pages shown inside modals."""
    v = (request.args.get('embed') or '').strip().lower()
    return {'hr_embed': v in ('1', 'true', 'yes', 'fullscreen', 'full')}


def get_current_user():
    """Get the current authenticated user"""
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


def _exempt_global_rate_limit(f):
    """Notification/read APIs are polled often; skip the app-wide default (e.g. 100/hour)."""
    try:
        limiter = current_app.limiter
        if limiter:
            return limiter.exempt(f)
    except (AttributeError, RuntimeError):
        pass
    return f


def _discard_hr_resume_draft(user: User | None, draft_id: str | None, module_type_full: str) -> None:
    """Drop a saved workflow draft once the same HR form is formally submitted."""
    if not user or not draft_id or not isinstance(draft_id, str) or not str(draft_id).strip():
        return
    did = str(draft_id).strip()
    d = Submission.query.filter_by(submission_id=did).first()
    if not d or getattr(d, "status", None) != "draft":
        return
    if getattr(d, "user_id", None) != user.id:
        return
    want = (module_type_full or "").strip()
    got = (getattr(d, "module_type", None) or "").strip()
    if want and got and got != want:
        return
    db.session.delete(d)


def _role_is_admin(user: User | None) -> bool:
    return bool(user and str(user.role or "").strip().lower() == "admin")


def _user_desig_lc(user: User | None) -> str:
    return ((user.designation or "") if user else "").strip().lower()


_ACTIVITY_APPROVER_DESIGNATIONS = frozenset(
    {"supervisor", "operations_manager", "business_development", "procurement", "general_manager"}
)


def _user_can_view_hr_signoff_activity(user: User | None, submission: Submission | None) -> bool:
    """Match workflow submission detail access for HR modules (submitter, line editors, workflow roles)."""
    if not user or not submission:
        return False
    if not (submission.module_type or "").startswith("hr_"):
        return False
    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    if user_is_mgmt_chain_participant(user, fd):
        return True
    if _role_is_admin(user):
        return True
    if submission.supervisor_id == user.id:
        return True
    if submission.user_id == user.id:
        return True
    if user.designation and user.designation in _ACTIVITY_APPROVER_DESIGNATIONS:
        return True
    des = _user_desig_lc(user)
    if getattr(user, "access_hr", False) or des == "hr_manager":
        return True
    if des == "general_manager":
        return True
    submitter = db.session.get(User, submission.user_id) if submission.user_id else None
    return bool(submitter and submitter.reporting_manager_id == user.id)


def user_is_hr_staff(user: User | None) -> bool:
    """Users who may fill HR-only sections (leave HR review rows, HR signatures).
    HR *module access* (`access_hr`) is not enough — that flag is often used so staff can submit their own HR forms."""
    if not user:
        return False
    if _role_is_admin(user):
        return True
    return _user_desig_lc(user) == "hr_manager"


def user_can_fill_hr_workflow_sidebar_fields(user: User | None) -> bool:
    """Broader gate for HoD / engineer / incharge rows that are not the formal HR-review block."""
    if not user:
        return False
    if _role_is_admin(user):
        return True
    if getattr(user, "access_hr", False):
        return True
    d = _user_desig_lc(user)
    return d in (
        "hr_manager",
        "supervisor",
        "operations_manager",
        "general_manager",
        "business_development",
        "procurement",
    )


def _strip_non_privileged_hr_submit_fields(data: dict, user: User) -> None:
    """Remove HR/GM-only payload keys from non–HR/GM submitters (defence in depth)."""
    if not isinstance(data, dict):
        return
    if user_is_hr_staff(user):
        return
    # Duty resumption: body signatures (employee, RM, GM, HR) captured on one form.
    duty_bundle = data.get("form_type") == "duty_resumption"
    preserve_sigs = {"hr_signature", "gm_signature", "reporting_manager_signature"} if duty_bundle else set()
    for k in list(data.keys()):
        if k.startswith("hr_") and k not in preserve_sigs:
            data.pop(k, None)
    is_gm = _role_is_admin(user) or user.designation == "general_manager"
    if not is_gm and not duty_bundle:
        data.pop("gm_signature", None)


def _hr_form_context(user):
    """Build context for HR form templates (is_hr, is_gm for field enablement)"""
    is_hr = user_is_hr_staff(user)
    is_hr_broad = user_can_fill_hr_workflow_sidebar_fields(user)
    is_gm = _role_is_admin(user) or user.designation == 'general_manager'
    return {
        'is_hr': is_hr,
        'is_hr_broad': is_hr_broad,
        'is_gm': is_gm,
        'mgmt_lane': lane_for_user(user),
    }


def _can_access_hr_submission_export(user, submission):
    """Admin, HR, GM may export any HR submission; submitter may export their own."""
    if not user or not submission:
        return False
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    if _role_is_admin(user) or is_hr or is_gm:
        return True
    if submission.user_id is not None and submission.user_id == user.id:
        return True
    # Designated colleague awaiting a routed (e.g. replacement) signature may preview the PDF on the sign page
    if isinstance(getattr(submission, 'module_type', None), str) and submission.module_type.startswith('hr_'):
        fd = submission.form_data if isinstance(submission.form_data, dict) else {}
        if pending_replacement_for_user(fd, user.id, submission.module_type):
            return True
        if user_is_mgmt_chain_participant(user, fd):
            return True
    return False


def create_notification(user_id, title, message, notification_type='info', submission_id=None):
    """Create a notification for a user"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        submission_id=submission_id
    )
    db.session.add(notification)
    return notification


def get_form_type_display(module_type):
    """Convert module type to display name - Based on HR Documents folder"""
    type_map = {
        'hr_leave_application': 'Leave Application',
        'hr_commencement': 'Commencement Form',
        'hr_duty_resumption': 'Duty Resumption',
        'hr_contract_renewal': 'Contract Renewal Assessment',
        'hr_performance_evaluation': 'Performance Evaluation',
        'hr_grievance': 'Grievance/Disciplinary',
        'hr_interview_assessment': 'Interview Assessment',
        'hr_passport_release': 'Passport Release & Submission',
        'hr_staff_appraisal': 'Staff Appraisal',
        'hr_station_clearance': 'Station Clearance',
        'hr_visa_renewal': 'Visa Renewal',
        'hr_asset_handover': 'Asset Handover & Takeover',
    }
    return type_map.get(module_type, 'HR Form')


def _notify_hr_staff_new_submission(submission_id, module_type_full, employee_name, exclude_user_id=None):
    """Inform HR roster that a submission is ready for HR review."""
    form_type_display = get_form_type_display(module_type_full)
    q = User.query.filter(
        db.or_(
            User.role == 'admin',
            User.access_hr == True,
            User.designation == 'hr_manager'
        ),
        User.is_active == True
    )
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    hr_users = q.all()
    for hr_user in hr_users:
        create_notification(
            user_id=hr_user.id,
            title='New HR Request',
            message=f'{employee_name} submitted {form_type_display} ({submission_id}).',
            notification_type='hr_pending_review',
            submission_id=submission_id
        )


def _advance_hr_after_all_replacements_signed(submission):
    """
    Move replacement_signoff → first management chain step, or legacy hr_review.
    Caller must commit separately.
    """
    if submission.workflow_status != 'replacement_signoff':
        return False
    fd = submission.form_data
    if not isinstance(fd, dict):
        return False
    if not all_replacements_signed(fd, submission.module_type):
        return False

    sync_replacement_display_fields(fd, submission.module_type)
    submission.form_data = fd
    flag_modified(submission, 'form_data')

    form_type_display = get_form_type_display(submission.module_type)
    employee_name = fd.get('employee_name') or fd.get('complainant_name') or fd.get('requester') or 'Employee'

    if has_management_chain(fd):
        ws = first_management_workflow_status(fd)
        submission.workflow_status = ws or 'hr_review'
        notify_current_management_signers(current_app._get_current_object(), submission)
        if submission.user_id:
            create_notification(
                user_id=submission.user_id,
                title='Teammate signatures complete',
                message=(
                    f'{form_type_display} ({submission.submission_id}) — routed to management sign-off '
                    f'(official PDF trail).'
                ),
                notification_type='hr_replacement_complete',
                submission_id=submission.submission_id,
            )
    else:
        submission.workflow_status = 'hr_review'
        exclude_uid = submission.user_id
        _notify_hr_staff_new_submission(
            submission.submission_id, submission.module_type, employee_name, exclude_user_id=exclude_uid
        )
        if submission.user_id:
            create_notification(
                user_id=submission.user_id,
                title='Teammate signatures complete',
                message=f'{form_type_display} ({submission.submission_id}) — all designated colleagues have signed. It is now with HR for review.',
                notification_type='hr_replacement_complete',
                submission_id=submission.submission_id,
            )
    return True


# ============================================
# USER FACING ROUTES (All users can access)
# ============================================

@hr_bp.route('/my-requests')
@jwt_required()
def my_requests():
    """View user's own HR requests - Available to ALL users"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return render_template('hr_my_requests.html', user=user)


@hr_bp.route('/leave-application-form')
@jwt_required()
def leave_application_form():
    """Leave Application Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_leave_application_form.html', user=user, **ctx)


@hr_bp.route('/commencement-form')
@jwt_required()
def commencement_form():
    """Commencement Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_commencement_form.html', user=user, **ctx)


@hr_bp.route('/duty-resumption-form')
@jwt_required()
def duty_resumption_form():
    """Duty Resumption Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_duty_resumption_form.html', user=user, **ctx)


@hr_bp.route('/contract-renewal-form')
@jwt_required()
def contract_renewal_form():
    """Contract Renewal Assessment - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_contract_renewal_form.html', user=user, **ctx)


@hr_bp.route('/performance-evaluation-form')
@jwt_required()
def performance_evaluation_form():
    """Performance Evaluation Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_performance_evaluation_form.html', user=user, **ctx)


@hr_bp.route('/grievance-form')
@jwt_required()
def grievance_form():
    """Grievance/Disciplinary Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_grievance_form.html', user=user, **ctx)


@hr_bp.route('/interview-assessment-form')
@jwt_required()
def interview_assessment_form():
    """Interview Assessment Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_interview_assessment_form.html', user=user, **ctx)


@hr_bp.route('/passport-release-form')
@jwt_required()
def passport_release_form():
    """Passport Release & Submission Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_passport_release_form.html', user=user, **ctx)


@hr_bp.route('/staff-appraisal-form')
@jwt_required()
def staff_appraisal_form():
    """Staff Appraisal Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_staff_appraisal_form.html', user=user, **ctx)


@hr_bp.route('/station-clearance-form')
@jwt_required()
def station_clearance_form():
    """Station Clearance Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_station_clearance_form.html', user=user, **ctx)


@hr_bp.route('/visa-renewal-form')
@jwt_required()
def visa_renewal_form():
    """Visa Renewal Form - From HR Documents"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_visa_renewal_form.html', user=user, **ctx)


@hr_bp.route('/asset-handover-form')
@jwt_required()
def asset_handover_form():
    """Asset Handover & Takeover Form - INJ_AHT_001"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    ctx = _hr_form_context(user)
    return render_template('hr_asset_handover_form.html', user=user, **ctx)


# ============================================
# HR MANAGER ROUTES (HR access required)
# ============================================

@hr_bp.route('/')
@jwt_required()
def hr_dashboard():
    """HR Module - HR managers see dashboard; others see My Requests"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # HR dashboard is for HR managers, GM, and admin; others go to My Requests
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    if not _role_is_admin(user) and not is_hr and not is_gm:
        return redirect('/hr/my-requests')
    
    return render_template('hr_dashboard.html', user=user, supported_docx_forms=get_supported_docx_forms(), supported_pdf_forms=get_supported_pdf_forms())


@hr_bp.route('/pending-review')
@hr_bp.route('/pending_review')
@jwt_required()
def pending_review():
    """Pending HR Review - For HR managers"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only HR managers and admin can review
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    if not _role_is_admin(user) and not is_hr:
        return jsonify({'error': 'Access denied'}), 403
    
    return render_template('hr_pending_review.html', user=user, supported_docx_forms=get_supported_docx_forms(), supported_pdf_forms=get_supported_pdf_forms())


@hr_bp.route('/approved-forms')
@jwt_required()
def approved_forms():
    """Approved HR Forms - List page (HR managers, GM, admin)"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    if not _role_is_admin(user) and not is_hr and not is_gm:
        return jsonify({'error': 'Access denied'}), 403
    return render_template('hr_approved_forms.html', user=user, supported_docx_forms=get_supported_docx_forms(), supported_pdf_forms=get_supported_pdf_forms())


@hr_bp.route('/gm-approval')
@jwt_required()
def gm_approval():
    """GM Final Approval - For General Manager"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only GM and admin can access
    if not _role_is_admin(user) and user.designation != 'general_manager':
        return jsonify({'error': 'Access denied'}), 403
    
    return render_template('hr_gm_approval.html', user=user, supported_docx_forms=get_supported_docx_forms(), supported_pdf_forms=get_supported_pdf_forms())


@hr_bp.route('/print/<submission_id>')
@jwt_required()
def hr_print(submission_id):
    """Print view - form in HR Document format (HR, GM, admin, or submitter)"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404
    if not _can_access_hr_submission_export(user, submission):
        return jsonify({'error': 'Access denied'}), 403

    form_data = submission.form_data or {}
    form_title = get_form_type_display(submission.module_type)
    form_html = render_form_for_print(submission.module_type, form_data, submission_id)

    # Document footer (matches HR document reference - HR-FRM-007 for Leave)
    form_type = (submission.module_type or '').replace('hr_', '')
    doc_no = 'HR-FRM-007' if form_type in ('leave_application', 'leave') else None
    doc_date = (
        format_naive_utc_in_dubai(submission.created_at, "%d/%m/%Y")
        if submission.created_at
        else format_now_in_dubai("%d/%m/%Y")
    )
    pdf_available = form_type in get_supported_pdf_forms()

    return render_template(
        'hr_print.html',
        submission_id=submission_id,
        form_title=form_title,
        form_html=form_html,
        doc_no=doc_no,
        doc_date=doc_date,
        pdf_available=pdf_available,
    )


@hr_bp.route('/print-pdf/<submission_id>')
@jwt_required()
def hr_print_pdf_launcher(submission_id):
    """Loads the generated PDF and triggers the system print dialog (preview shows PDF in supporting browsers)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404
    if not _can_access_hr_submission_export(user, submission):
        return jsonify({'error': 'Access denied'}), 403

    form_type = (submission.module_type or '').replace('hr_', '')
    if form_type not in get_supported_pdf_forms():
        return redirect(url_for('hr.hr_print', submission_id=submission_id))

    pdf_url = url_for('hr.hr_download_pdf', submission_id=submission_id, inline=1)
    return render_template('hr_print_pdf_launcher.html', pdf_url=pdf_url)


@hr_bp.route('/download-docx/<submission_id>')
@jwt_required()
def hr_download_docx(submission_id):
    """Download filled HR document (DOCX) - matches shared HR Documents templates"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404
    if not _can_access_hr_submission_export(user, submission):
        return jsonify({'error': 'Access denied'}), 403

    try:
        from io import BytesIO
        buf = BytesIO()
        result = generate_hr_docx(submission, buf)
        if isinstance(result, tuple):
            generated, filled = result
        else:
            generated, filled = result, False
        if not generated:
            return jsonify({'error': 'DOCX download not available for this form type'}), 404
        buf.seek(0)
        form_title = get_form_type_display(submission.module_type).replace(' ', '_')
        filename = f"{form_title}_{submission_id}.docx"
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', as_attachment=True, download_name=filename)
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        current_app.logger.exception('DOCX generation failed')
        return jsonify({'error': f'Failed to generate document: {str(e)}'}), 500


@hr_bp.route('/download-pdf/<submission_id>')
@jwt_required()
def hr_download_pdf(submission_id):
    """Download professional branded PDF - bold layout, INJAAZ design"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404
    if not _can_access_hr_submission_export(user, submission):
        return jsonify({'error': 'Access denied'}), 403

    try:
        from io import BytesIO
        buf = BytesIO()
        ok, err = generate_hr_pdf(submission, buf)
        if not ok:
            return jsonify({'error': err or 'PDF not available for this form type'}), 404
        buf.seek(0)
        form_title = get_form_type_display(submission.module_type).replace(' ', '_')
        filename = f"{form_title}_{submission_id}.pdf"
        inline_q = (request.args.get('inline') or '').lower()
        as_inline = inline_q in ('1', 'true', 'yes')
        resp = send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=not as_inline,
            download_name=filename,
        )
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        return resp
    except Exception as e:
        current_app.logger.exception('PDF generation failed')
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500


# ============================================
# API ROUTES
# ============================================

@hr_bp.route('/api/submit', methods=['POST'])
@jwt_required()
def submit_hr_form():
    """Submit any HR form - Available to ALL users"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid payload'}), 400
    
    resume_draft_id = data.pop('resume_draft_id', None) or data.pop('clear_draft_id', None)
    
    form_type = data.get('form_type')  # 'leave', 'termination', 'long_vacation', 'asset'
    
    if not form_type:
        return jsonify({'error': 'Form type is required'}), 400
    
    is_gm = _role_is_admin(user) or user.designation == 'general_manager'
    if form_type == 'duty_resumption' and not is_gm:
        data.pop('line_manager_remarks', None)
    
    # Generate submission ID
    submission_id = f"HR-{form_type.upper()}-{uuid.uuid4().hex[:8].upper()}"

    # Add submitter info to form data
    data['submitted_by_id'] = user.id
    data['submitted_by_name'] = user.full_name or user.username
    data['submitted_at'] = naive_utc_isoformat_z(utc_now_naive())

    module_type_full = f'hr_{form_type}'
    data.pop('hr_mgmt_chain', None)
    data.pop(MGMT_CHAIN_KEY, None)
    strip_teammate_signatures_from_submitter_payload(data, module_type_full)
    routed_block, strip_keys, routed_err = collect_routed_signoffs_from_submit(
        data, user.id, module_type_full
    )
    if routed_err:
        return jsonify({'error': routed_err}), 400
    for k in strip_keys:
        data.pop(k, None)

    _strip_non_privileged_hr_submit_fields(data, user)

    if form_type == 'interview_assessment':
        data['interview_routing'] = interview_routing_deferred_at_submit()
    else:
        mgmt_err = init_management_chain_on_submit(data, user)
        if mgmt_err:
            return jsonify({'error': mgmt_err}), 400

    commencement_dual_meta = None
    if form_type == 'commencement':
        rt_block, rt_err, rt_meta = resolve_commencement_reporting_to(data, user)
        if rt_err:
            return jsonify({'error': rt_err}), 400
        if rt_block:
            if routed_block and isinstance(routed_block.get('slots'), list):
                routed_block['slots'].extend(rt_block['slots'])
            else:
                routed_block = rt_block
        commencement_dual_meta = (
            rt_meta if isinstance(rt_meta, dict) and rt_meta.get('mode') == 'dual_role' else None
        )

    workflow_status = first_management_workflow_status(data)
    if routed_block:
        merge_routed_into_form_data_inplace(data, routed_block, module_type_full)
        workflow_status = 'replacement_signoff'
    elif workflow_status is None:
        workflow_status = 'hr_review'

    submission = Submission(
        submission_id=submission_id,
        user_id=user.id,
        module_type=module_type_full,
        site_name=data.get('employee_name', user.full_name or 'HR Form'),
        visit_date=datetime.now().date(),
        status='submitted',
        workflow_status=workflow_status,
        supervisor_id=user.id,
        form_data=data
    )

    db.session.add(submission)
    db.session.commit()
    _discard_hr_resume_draft(user, resume_draft_id, module_type_full)
    db.session.commit()

    form_type_display = get_form_type_display(f'hr_{form_type}')
    employee_name = (
        data.get('employee_name')
        or data.get('complainant_name')
        or data.get('candidate_name')
        or user.full_name
        or 'Employee'
    )

    if routed_block:
        routed_rows = flatten_signers_notify(routed_block)
        for row in routed_rows:
            uid = row.get('user_id')
            if not uid:
                continue
            lbl = row.get('_slot_label') or 'Signatory'
            create_notification(
                user_id=int(uid),
                title='HR form needs your signature',
                message=(
                    f'{employee_name} listed you ({lbl}) on '
                    f'{form_type_display} ({submission_id}). Sign in Injaaz to continue.'
                ),
                notification_type='hr_replacement_signoff',
                submission_id=submission_id
            )
        email_all_routed_assignees(current_app._get_current_object(), submission, form_type_display)
        db.session.commit()
        return jsonify({
            'success': True,
            'submission_id': submission_id,
            'workflow_status': workflow_status,
            'message': (
                f'Submitted. {len(routed_rows)} colleague(s) must sign digitally first; '
                'then the management approval chain begins for the PDF trail.'
            ),
        })

    if has_management_chain(data):
        notify_current_management_signers(current_app._get_current_object(), submission)
        if commencement_dual_meta:
            uid = commencement_dual_meta.get('user_id')
            if uid:
                create_notification(
                    user_id=int(uid),
                    title='Reporting To + management sign-off',
                    message=dual_role_notify_message(
                        commencement_dual_meta, employee_name, submission_id
                    ),
                    notification_type='hr_commencement_dual_role',
                    submission_id=submission_id,
                )
        done_msg = (
            'Form submitted. Management approvers were notified in order '
            '(supervisor / reporting manager → operations manager → general manager → HR).'
        )
        if commencement_dual_meta:
            done_msg = (
                'Form submitted. Your Reporting To manager is also in the management chain — '
                'they were notified that their signature will appear in both the Reporting To '
                'block and their management step. Other approvers were notified in order.'
            )
    else:
        _notify_hr_staff_new_submission(
            submission_id,
            module_type_full,
            employee_name,
            exclude_user_id=user.id,
        )
        done_msg = (
            'Form submitted. This request was sent to the HR review queue '
            '(no management chain on this submission).'
        )
    db.session.commit()

    return jsonify({
        'success': True,
        'submission_id': submission_id,
        'workflow_status': workflow_status,
        'message': done_msg,
    })


@hr_bp.route('/api/my-submissions')
@jwt_required()
def get_my_submissions():
    """Get current user's own HR submissions"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get user's own HR submissions
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.user_id == user.id
    ).order_by(Submission.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'submissions': [s.to_dict() for s in submissions]
    })


@hr_bp.route('/api/user-permissions')
@jwt_required()
def get_user_permissions():
    """Get current user's HR module permissions"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    is_admin = _role_is_admin(user)
    
    return jsonify({
        'success': True,
        'permissions': {
            'can_review_hr': is_admin or is_hr,
            'can_approve_gm': is_admin or is_gm,
            'is_admin': is_admin,
            'full_access': is_admin,
        }
    })


@hr_bp.route('/replacement-sign/<submission_id>')
@jwt_required()
def replacement_sign_page(submission_id):
    """Minimal page for designated replacement colleagues to capture a signature."""
    user = get_current_user()
    if not user:
        return redirect('/login')
    return render_template(
        'hr_replacement_sign.html',
        user=user,
        submission_id=submission_id,
    )


@hr_bp.route('/api/mgmt-chain-context')
@jwt_required()
def mgmt_chain_context():
    """Reporting manager + lane info for HR form UI (profile-driven)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    form_type = (request.args.get('form_type') or '').strip().lower()
    if form_type == 'interview_assessment':
        return jsonify(get_interview_routing_ui_context())
    return jsonify(get_mgmt_chain_ui_context(user))


def _interview_interviewer_pending(submission, user):
    """True when user is the pending interviewer slot on an interview assessment."""
    if submission.module_type != 'hr_interview_assessment':
        return None
    fd = submission.form_data or {}
    pend = pending_replacement_for_user(fd, user.id, submission.module_type)
    if pend and pend.get('_slot_key') == 'interviewer':
        return pend
    return None


@hr_bp.route('/api/active-users-for-picker')
@jwt_required()
def active_users_for_picker():
    """Lightweight colleague list for replacement signatory selection (authenticated users only)."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    q = (
        User.query.filter(User.is_active == True)
        .filter(User.id != user.id)
        .order_by(db.func.lower(db.func.coalesce(User.full_name, User.username)))
    )

    picker = [
        {
            'id': u.id,
            'full_name': u.full_name or u.username,
            'username': u.username,
            'designation': (u.designation or '') or '',
        }
        for u in q.limit(600).all()
    ]
    return jsonify({'success': True, 'users': picker})


@hr_bp.route('/api/my-replacement-signoffs')
@jwt_required()
def my_replacement_signoffs():
    """Submissions awaiting the current user's replacement signature."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.workflow_status == 'replacement_signoff',
    ).order_by(Submission.created_at.desc()).limit(120).all()

    out = []
    for s in submissions:
        slot = pending_replacement_for_user(s.form_data or {}, user.id, s.module_type)
        if not slot:
            continue
        d = s.to_dict()
        submitter = db.session.get(User, s.user_id)
        if submitter:
            d['submitter_display'] = submitter.full_name or submitter.username
        d['pending_slot_label'] = slot.get('_slot_label')
        out.append(d)

    return jsonify({'success': True, 'submissions': out})


@hr_bp.route('/api/signoff-activity/<submission_id>')
@jwt_required()
def hr_signoff_activity_poll(submission_id):
    """
    Lightweight timeline for HR ?edit= pages: colleague + management sign-offs.
    Used for live polling without re-downloading full form_data / images.
    """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404

    if not _user_can_view_hr_signoff_activity(user, submission):
        return jsonify({'error': 'Access denied'}), 403

    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    activities, fingerprint = compute_hr_signoff_activity(
        fd, submission.workflow_status, submission.status
    )

    return jsonify(
        {
            'success': True,
            'fingerprint': fingerprint,
            'workflow_status': submission.workflow_status,
            'workflow_status_label': hr_workflow_status_label(
                submission.workflow_status, submission.status
            ),
            'activities': activities,
        }
    )


@hr_bp.route('/api/replacement-signoff-detail/<submission_id>')
@jwt_required()
def replacement_signoff_detail(submission_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404

    fd = submission.form_data or {}
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'

    pend = pending_replacement_for_user(fd, user.id, submission.module_type)
    is_owner = submission.user_id == user.id
    allowed = pend is not None or is_owner or _role_is_admin(user) or is_hr

    if not allowed:
        return jsonify({'error': 'Access denied'}), 403

    pending_for_me = pend is not None
    pending_slot_label = pend.get('_slot_label') if pend else None
    requires_next_approver = bool(
        pending_for_me
        and submission.module_type == 'hr_interview_assessment'
        and pend.get('_slot_key') == 'interviewer'
    )
    payload = submission.to_dict()
    return jsonify({
        'success': True,
        'submission': payload,
        'can_sign': bool(pending_for_me),
        'pending_slot_label': pending_slot_label,
        'requires_next_approver': requires_next_approver,
        'form_type_display': get_form_type_display(submission.module_type),
    })


@hr_bp.route('/api/replacement-signoff/<submission_id>/sign', methods=['POST'])
@jwt_required()
def replacement_signoff_submit(submission_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404

    body = request.get_json() or {}
    signature = (body.get('signature') or '').strip()
    comments = body.get('comments')
    next_approver_raw = body.get('next_approver_signer_id')

    if not signature or not signature.startswith('data:image'):
        return jsonify({'error': 'A captured signature image is required'}), 400

    iv_pending = _interview_interviewer_pending(submission, user)
    if iv_pending:
        if next_approver_raw is None or next_approver_raw == '':
            return jsonify({'error': 'Select a colleague to forward this form to for approval.'}), 400
        try:
            next_approver_id = int(next_approver_raw)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid next approver.'}), 400

    ok, err = apply_replacement_signature(submission, user, signature, comments)
    if not ok:
        return jsonify({'error': err}), 400

    if iv_pending:
        fd = submission.form_data if isinstance(submission.form_data, dict) else {}
        chain_err = apply_interview_chain_after_interviewer(
            fd,
            next_approver_id,
            submitter_id=submission.user_id,
            interviewer_id=user.id,
        )
        if chain_err:
            db.session.rollback()
            return jsonify({'error': chain_err}), 400
        submission.form_data = fd
        flag_modified(submission, 'form_data')

    advanced = _advance_hr_after_all_replacements_signed(submission)
    db.session.commit()

    if advanced:
        fd = submission.form_data if isinstance(submission.form_data, dict) else {}
        msg = (
            'Thank you — management sign-off begins next (official PDF trail).'
            if has_management_chain(fd)
            else 'Thank you — all colleague signatures received. This request is now with HR for review.'
        )
    else:
        msg = 'Signature saved. Waiting for remaining replacement signatories.'
    return jsonify({'success': True, 'advanced_to_hr_review': advanced, 'message': msg})


@hr_bp.route('/mgmt-sign/<submission_id>')
@jwt_required()
def mgmt_sign_page(submission_id):
    user = get_current_user()
    if not user:
        return redirect('/login')
    return render_template(
        'hr_mgmt_sign.html',
        user=user,
        submission_id=submission_id,
    )


@hr_bp.route('/api/mgmt-signoff-detail/<submission_id>')
@jwt_required()
def mgmt_signoff_detail(submission_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404

    fd = submission.form_data or {}
    pend = pending_management_step_for_user(fd, submission.workflow_status, user)
    completed = user_mgmt_chain_completed_step(user, fd)
    is_owner = submission.user_id == user.id
    is_hr_viewer = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    allowed = (
        user_is_mgmt_chain_participant(user, fd)
        or is_owner
        or _role_is_admin(user)
        or is_hr_viewer
    )

    if not allowed:
        return jsonify({'error': 'Access denied'}), 403

    if pend:
        viewer_state = 'can_sign'
    elif completed:
        viewer_state = 'already_signed'
    elif user_is_mgmt_chain_participant(user, fd):
        viewer_state = 'not_your_turn'
    else:
        viewer_state = 'view_only'

    signed_step = None
    if completed:
        signed_step = {
            'step_key': completed.get('key'),
            'step_label': completed.get('pdf_label'),
            'signed_at': completed.get('signed_at'),
            'signed_by_name': completed.get('signed_by_name'),
            'comments': completed.get('comments'),
            'signature': completed.get('signature'),
        }

    return jsonify({
        'success': True,
        'submission': submission.to_dict(),
        'can_sign': bool(pend),
        'already_signed': viewer_state == 'already_signed',
        'viewer_state': viewer_state,
        'signed_step': signed_step,
        'current_user_id': user.id,
        'step_label': pend.get('pdf_label') if pend else None,
        'form_type_display': get_form_type_display(submission.module_type),
        'workflow_status': submission.workflow_status,
        'reporting_to_dual_role_hint': dual_role_hint_for_user(fd, user.id),
    })


@hr_bp.route('/api/mgmt-signoff/<submission_id>/sign', methods=['POST'])
@jwt_required()
def mgmt_signoff_sign(submission_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404

    body = request.get_json() or {}
    signature = (body.get('signature') or '').strip()
    comments = body.get('comments')
    form_payload_hr = body.get('form_data_hr')
    form_data_hr = form_payload_hr if isinstance(form_payload_hr, dict) else None

    ok, err = apply_management_signature(submission, user, signature, comments, form_data_hr)
    if not ok:
        return jsonify({'error': err or 'Unable to save signature'}), 400

    app = current_app._get_current_object()
    finished = submission.workflow_status == 'approved'
    if finished:
        notify_submitter_management_final(app, submission, completed=True)
    else:
        notify_current_management_signers(app, submission)

    db.session.commit()

    msg = (
        'All management signatures are complete — request approved.'
        if finished else 'Saved — routed to the next approver.'
    )
    return jsonify({
        'success': True,
        'completed': finished,
        'workflow_status': submission.workflow_status,
        'message': msg,
    })


@hr_bp.route('/api/mgmt-signoff/<submission_id>/reject', methods=['POST'])
@jwt_required()
def mgmt_signoff_reject(submission_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission or not submission.module_type.startswith('hr_'):
        return jsonify({'error': 'Submission not found'}), 404

    reason = (request.get_json() or {}).get('reason', '')
    ok, err = reject_management_submission(submission, user, reason)
    if not ok:
        return jsonify({'error': err or 'Reject failed'}), 400

    notify_submitter_management_final(
        current_app._get_current_object(),
        submission,
        completed=False,
        rejected=True,
        reason=reason,
    )
    db.session.commit()
    return jsonify({'success': True, 'message': 'Request rejected'})


@hr_bp.route('/api/my-mgmt-signoffs')
@jwt_required()
def my_mgmt_signoffs():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    submissions = (
        Submission.query.filter(
            Submission.module_type.like('hr_%'),
            Submission.workflow_status.in_(ALL_MGMT_WF_STATUSES),
        )
        .order_by(Submission.created_at.desc())
        .limit(160)
        .all()
    )
    out = []
    for s in submissions:
        fd = s.form_data or {}
        pend = pending_management_step_for_user(fd, s.workflow_status, user)
        if not pend:
            continue
        d = s.to_dict()
        submitter = db.session.get(User, s.user_id)
        if submitter:
            d['submitter_display'] = submitter.full_name or submitter.username
        d['pending_step_label'] = pend.get('pdf_label')
        out.append(d)

    return jsonify({'success': True, 'submissions': out})


@hr_bp.route('/api/pending-hr-review')
@jwt_required()
def get_pending_hr_review():
    """Get submissions pending HR review"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only HR managers and admin can access
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    if not _role_is_admin(user) and not is_hr:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get submissions pending HR review (legacy inbox + final HR step of management chain)
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.workflow_status.in_(['hr_review', WF_MGMT_HR]),
    ).order_by(Submission.created_at.desc()).all()
    
    # Add submitter info
    result = []
    for s in submissions:
        data = s.to_dict()
        submitter = db.session.get(User, s.user_id)
        if submitter:
            data['submitter_name'] = submitter.full_name or submitter.username
            data['submitter_email'] = submitter.email
        result.append(data)
    
    return jsonify({
        'success': True,
        'submissions': result
    })


@hr_bp.route('/api/pending-gm-approval')
@jwt_required()
def get_pending_gm_approval():
    """Get submissions pending GM approval"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only GM and admin can access
    if not _role_is_admin(user) and user.designation != 'general_manager':
        return jsonify({'error': 'Access denied'}), 403
    
    # Get submissions pending GM approval (legacy + management chain GM gate)
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.workflow_status.in_(['gm_review', WF_MGMT_GM]),
    ).order_by(Submission.created_at.desc()).all()
    
    # Add submitter and HR reviewer info
    result = []
    for s in submissions:
        data = s.to_dict()
        submitter = db.session.get(User, s.user_id)
        if submitter:
            data['submitter_name'] = submitter.full_name or submitter.username
        result.append(data)
    
    return jsonify({
        'success': True,
        'submissions': result
    })


@hr_bp.route('/api/approved-hr-submissions')
@jwt_required()
def get_approved_hr_submissions():
    """Get HR submissions that have been fully approved (workflow_status=approved)"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # HR and GM can see approved submissions
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    if not _role_is_admin(user) and not is_hr and not is_gm:
        return jsonify({'error': 'Access denied'}), 403
    
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.workflow_status == 'approved'
    ).order_by(Submission.updated_at.desc()).limit(100).all()
    
    result = []
    for s in submissions:
        data = s.to_dict()
        submitter = db.session.get(User, s.user_id)
        if submitter:
            data['submitter_name'] = submitter.full_name or submitter.username
        result.append(data)
    
    return jsonify({
        'success': True,
        'submissions': result
    })


@hr_bp.route('/api/hr-approve/<submission_id>', methods=['POST'])
@jwt_required()
def hr_approve(submission_id):
    """HR approves and forwards to GM"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only HR managers and admin can approve
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    if not _role_is_admin(user) and not is_hr:
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    if submission.workflow_status != 'hr_review':
        return jsonify({'error': 'Submission is not pending HR review'}), 400
    
    data = request.get_json() or {}
    
    # Update submission
    form_data = _mutable_form_data(submission)
    form_data['hr_reviewed_by_id'] = user.id
    form_data['hr_reviewed_by_name'] = user.full_name or user.username
    form_data['hr_reviewed_at'] = naive_utc_isoformat_z(utc_now_naive())
    form_data['hr_comments'] = data.get('comments', '')
    form_data['hr_signature'] = data.get('signature', '')
    # Merge form-specific HR fields (e.g. leave_application: hr_checked, hr_balance_cf, etc.)
    for k, v in (data.get('form_data_hr') or {}).items():
        form_data[k] = v
    
    submission.form_data = form_data
    submission.workflow_status = 'gm_review'  # Forward to GM
    submission.status = 'submitted'
    submission.operations_manager_id = user.id
    submission.operations_manager_approved_at = utc_now_naive()
    submission.operations_manager_comments = data.get('comments', '')
    
    db.session.commit()
    
    # Notify GM users about new request pending their approval
    form_type_display = get_form_type_display(submission.module_type)
    employee_name = form_data.get('employee_name') or form_data.get('complainant_name') or form_data.get('requester') or 'Employee'
    gm_users = User.query.filter(
        db.or_(
            User.role == 'admin',
            User.designation == 'general_manager'
        ),
        User.is_active == True
    ).all()
    for gm_user in gm_users:
        create_notification(
            user_id=gm_user.id,
            title='HR Request Pending Your Approval',
            message=f'{form_type_display} for {employee_name} ({submission_id}) – approved by HR, awaiting your final approval.',
            notification_type='gm_approval_pending',
            submission_id=submission_id
        )
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Approved and forwarded to General Manager for final approval'
    })


@hr_bp.route('/api/hr-reject/<submission_id>', methods=['POST'])
@jwt_required()
def hr_reject(submission_id):
    """HR rejects the submission"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    if not _role_is_admin(user) and not is_hr:
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    data = request.get_json() or {}
    
    # Update submission
    form_data = _mutable_form_data(submission)
    form_data['hr_rejected_by_id'] = user.id
    form_data['hr_rejected_by_name'] = user.full_name or user.username
    form_data['hr_rejected_at'] = naive_utc_isoformat_z(utc_now_naive())
    form_data['hr_rejection_reason'] = data.get('reason', '')
    
    submission.form_data = form_data
    submission.workflow_status = 'rejected'
    submission.status = 'rejected'
    submission.rejection_reason = data.get('reason', '')
    submission.rejected_at = utc_now_naive()
    submission.rejected_by_id = user.id
    
    # Get form type for display
    form_type_display = get_form_type_display(submission.module_type)
    rejection_reason = data.get('reason', 'No reason provided')
    
    # Send notification to the original submitter
    if submission.user_id:
        create_notification(
            user_id=submission.user_id,
            title='HR Request Rejected',
            message=f'Your {form_type_display} ({submission_id}) has been rejected by HR. Reason: {rejection_reason}',
            notification_type='hr_rejected',
            submission_id=submission_id
        )
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Request rejected'
    })


@hr_bp.route('/api/gm-approve/<submission_id>', methods=['POST'])
@jwt_required()
def gm_approve(submission_id):
    """GM gives final approval"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if not _role_is_admin(user) and user.designation != 'general_manager':
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    if submission.workflow_status != 'gm_review':
        return jsonify({'error': 'Submission is not pending GM approval'}), 400
    
    data = request.get_json() or {}
    
    # Update submission
    form_data = _mutable_form_data(submission)
    form_data['gm_approved_by_id'] = user.id
    form_data['gm_approved_by_name'] = user.full_name or user.username
    form_data['gm_approved_at'] = naive_utc_isoformat_z(utc_now_naive())
    form_data['gm_comments'] = data.get('comments', '')
    form_data['gm_signature'] = data.get('signature', '')
    
    submission.form_data = form_data
    submission.workflow_status = 'approved'
    submission.status = 'completed'
    submission.general_manager_id = user.id
    submission.general_manager_approved_at = utc_now_naive()
    submission.general_manager_comments = data.get('comments', '')
    
    # Get form type for display
    form_type_display = get_form_type_display(submission.module_type)
    employee_name = form_data.get('employee_name', 'Employee')
    
    # Send notification to the original submitter
    if submission.user_id:
        create_notification(
            user_id=submission.user_id,
            title='HR Request Approved',
            message=f'Your {form_type_display} ({submission_id}) has been approved by the General Manager.',
            notification_type='hr_approved',
            submission_id=submission_id
        )
    
    # Send notification to HR who reviewed it
    hr_reviewer_id = form_data.get('hr_reviewed_by_id')
    if hr_reviewer_id and hr_reviewer_id != submission.user_id:
        create_notification(
            user_id=hr_reviewer_id,
            title='HR Request Final Approval',
            message=f'{form_type_display} for {employee_name} ({submission_id}) has been approved by GM.',
            notification_type='hr_approved',
            submission_id=submission_id
        )
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Request approved successfully'
    })


@hr_bp.route('/api/gm-reject/<submission_id>', methods=['POST'])
@jwt_required()
def gm_reject(submission_id):
    """GM rejects the submission"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if not _role_is_admin(user) and user.designation != 'general_manager':
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    data = request.get_json() or {}
    
    # Update submission
    form_data = _mutable_form_data(submission)
    form_data['gm_rejected_by_id'] = user.id
    form_data['gm_rejected_by_name'] = user.full_name or user.username
    form_data['gm_rejected_at'] = naive_utc_isoformat_z(utc_now_naive())
    form_data['gm_rejection_reason'] = data.get('reason', '')
    
    submission.form_data = form_data
    submission.workflow_status = 'rejected'
    submission.status = 'rejected'
    submission.rejection_reason = data.get('reason', '')
    submission.rejected_at = utc_now_naive()
    submission.rejected_by_id = user.id
    
    # Get form type for display
    form_type_display = get_form_type_display(submission.module_type)
    employee_name = form_data.get('employee_name', 'Employee')
    rejection_reason = data.get('reason', 'No reason provided')
    
    # Send notification to the original submitter
    if submission.user_id:
        create_notification(
            user_id=submission.user_id,
            title='HR Request Rejected',
            message=f'Your {form_type_display} ({submission_id}) has been rejected by the General Manager. Reason: {rejection_reason}',
            notification_type='hr_rejected',
            submission_id=submission_id
        )
    
    # Send notification to HR who reviewed it
    hr_reviewer_id = form_data.get('hr_reviewed_by_id')
    if hr_reviewer_id and hr_reviewer_id != submission.user_id:
        create_notification(
            user_id=hr_reviewer_id,
            title='HR Request Rejected by GM',
            message=f'{form_type_display} for {employee_name} ({submission_id}) has been rejected by GM. Reason: {rejection_reason}',
            notification_type='hr_rejected',
            submission_id=submission_id
        )
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Request rejected'
    })


@hr_bp.route('/api/submissions')
@jwt_required()
def get_hr_submissions():
    """Get all HR submissions - For HR dashboard"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    if not _role_is_admin(user) and not is_hr and not is_gm:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get all HR submissions
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%')
    ).order_by(Submission.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'submissions': [s.to_dict() for s in submissions]
    })


# ============================================
# NOTIFICATION API ROUTES
# ============================================

@hr_bp.route('/api/notifications')
@jwt_required()
@_exempt_global_rate_limit
def get_notifications():
    """Get current user's notifications"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get user's notifications, most recent first
    notifications = Notification.query.filter_by(user_id=user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    
    # Count unread
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    
    return jsonify({
        'success': True,
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count
    })


@hr_bp.route('/api/notifications/unread-count')
@jwt_required()
@_exempt_global_rate_limit
def get_unread_count():
    """Get count of unread notifications"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    
    return jsonify({
        'success': True,
        'unread_count': unread_count
    })


@hr_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@jwt_required()
@_exempt_global_rate_limit
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    notification = Notification.query.filter_by(id=notification_id, user_id=user.id).first()
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'success': True})


@hr_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@jwt_required()
@_exempt_global_rate_limit
def mark_all_notifications_read():
    """Mark all notifications as read"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    return jsonify({'success': True})
