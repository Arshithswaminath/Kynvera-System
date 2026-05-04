"""
HR Module Routes
Handles HR forms: Leave, Termination, Long Vacation, Asset Transfer/Register
Workflow: User submits → HR reviews/signs → GM final approval
"""
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app, redirect, send_file, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Submission, Notification
from common.form_data_utils import shallow_copy_form_data as _mutable_form_data

from .print_utils import render_form_for_print
from .docx_service import generate_hr_docx, get_supported_docx_forms
from .pdf_service import generate_hr_pdf, get_supported_pdf_forms

hr_bp = Blueprint('hr', __name__, template_folder='templates')


def get_current_user():
    """Get the current authenticated user"""
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


def _hr_form_context(user):
    """Build context for HR form templates (is_hr, is_gm for field enablement)"""
    is_hr = user.role == 'admin' or getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.role == 'admin' or user.designation == 'general_manager'
    return {'is_hr': is_hr, 'is_gm': is_gm}


def _can_access_hr_submission_export(user, submission):
    """Admin, HR, GM may export any HR submission; submitter may export their own."""
    if not user or not submission:
        return False
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    is_gm = user.designation == 'general_manager'
    if user.role == 'admin' or is_hr or is_gm:
        return True
    return submission.user_id is not None and submission.user_id == user.id


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
    }
    return type_map.get(module_type, 'HR Form')


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
    if user.role != 'admin' and not is_hr and not is_gm:
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
    if user.role != 'admin' and not is_hr:
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
    if user.role != 'admin' and not is_hr and not is_gm:
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
    if user.role != 'admin' and user.designation != 'general_manager':
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
    doc_date = submission.created_at.strftime('%d/%m/%Y') if submission.created_at else datetime.now().strftime('%d/%m/%Y')
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
    form_type = data.get('form_type')  # 'leave', 'termination', 'long_vacation', 'asset'
    
    if not form_type:
        return jsonify({'error': 'Form type is required'}), 400
    
    # Generate submission ID
    submission_id = f"HR-{form_type.upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    # Add submitter info to form data
    data['submitted_by_id'] = user.id
    data['submitted_by_name'] = user.full_name or user.username
    data['submitted_at'] = datetime.now().isoformat()
    
    # Create submission with workflow status
    submission = Submission(
        submission_id=submission_id,
        user_id=user.id,
        module_type=f'hr_{form_type}',
        site_name=data.get('employee_name', user.full_name or 'HR Form'),
        visit_date=datetime.now().date(),
        status='submitted',
        workflow_status='hr_review',  # Goes to HR first
        supervisor_id=user.id,
        form_data=data
    )
    
    db.session.add(submission)
    db.session.commit()
    
    # Notify HR users about new submission
    form_type_display = get_form_type_display(f'hr_{form_type}')
    employee_name = data.get('employee_name') or data.get('complainant_name') or data.get('candidate_name') or user.full_name or 'Employee'
    hr_users = User.query.filter(
        db.or_(
            User.role == 'admin',
            User.access_hr == True,
            User.designation == 'hr_manager'
        ),
        User.id != user.id,
        User.is_active == True
    ).all()
    for hr_user in hr_users:
        create_notification(
            user_id=hr_user.id,
            title='New HR Request',
            message=f'{employee_name} submitted {form_type_display} ({submission_id})',
            notification_type='info',
            submission_id=submission_id
        )
    db.session.commit()
    
    return jsonify({
        'success': True,
        'submission_id': submission_id,
        'message': f'{form_type.replace("_", " ").title()} form submitted successfully. Pending HR review.'
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
    is_admin = user.role == 'admin'
    
    return jsonify({
        'success': True,
        'permissions': {
            'can_review_hr': is_admin or is_hr,
            'can_approve_gm': is_admin or is_gm,
            'is_admin': is_admin
        }
    })


@hr_bp.route('/api/pending-hr-review')
@jwt_required()
def get_pending_hr_review():
    """Get submissions pending HR review"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Only HR managers and admin can access
    is_hr = getattr(user, 'access_hr', False) or user.designation == 'hr_manager'
    if user.role != 'admin' and not is_hr:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get submissions pending HR review
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.workflow_status == 'hr_review'
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
    if user.role != 'admin' and user.designation != 'general_manager':
        return jsonify({'error': 'Access denied'}), 403
    
    # Get submissions pending GM approval
    submissions = Submission.query.filter(
        Submission.module_type.like('hr_%'),
        Submission.workflow_status == 'gm_review'
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
    if user.role != 'admin' and not is_hr and not is_gm:
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
    if user.role != 'admin' and not is_hr:
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
    form_data['hr_reviewed_at'] = datetime.now().isoformat()
    form_data['hr_comments'] = data.get('comments', '')
    form_data['hr_signature'] = data.get('signature', '')
    # Merge form-specific HR fields (e.g. leave_application: hr_checked, hr_balance_cf, etc.)
    for k, v in (data.get('form_data_hr') or {}).items():
        form_data[k] = v
    
    submission.form_data = form_data
    submission.workflow_status = 'gm_review'  # Forward to GM
    submission.status = 'submitted'
    submission.operations_manager_id = user.id
    submission.operations_manager_approved_at = datetime.now()
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
    if user.role != 'admin' and not is_hr:
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    data = request.get_json() or {}
    
    # Update submission
    form_data = _mutable_form_data(submission)
    form_data['hr_rejected_by_id'] = user.id
    form_data['hr_rejected_by_name'] = user.full_name or user.username
    form_data['hr_rejected_at'] = datetime.now().isoformat()
    form_data['hr_rejection_reason'] = data.get('reason', '')
    
    submission.form_data = form_data
    submission.workflow_status = 'rejected'
    submission.status = 'rejected'
    submission.rejection_reason = data.get('reason', '')
    submission.rejected_at = datetime.now()
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
    
    if user.role != 'admin' and user.designation != 'general_manager':
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
    form_data['gm_approved_at'] = datetime.now().isoformat()
    form_data['gm_comments'] = data.get('comments', '')
    form_data['gm_signature'] = data.get('signature', '')
    
    submission.form_data = form_data
    submission.workflow_status = 'approved'
    submission.status = 'completed'
    submission.general_manager_id = user.id
    submission.general_manager_approved_at = datetime.now()
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
    
    if user.role != 'admin' and user.designation != 'general_manager':
        return jsonify({'error': 'Access denied'}), 403
    
    submission = Submission.query.filter_by(submission_id=submission_id).first()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    data = request.get_json() or {}
    
    # Update submission
    form_data = _mutable_form_data(submission)
    form_data['gm_rejected_by_id'] = user.id
    form_data['gm_rejected_by_name'] = user.full_name or user.username
    form_data['gm_rejected_at'] = datetime.now().isoformat()
    form_data['gm_rejection_reason'] = data.get('reason', '')
    
    submission.form_data = form_data
    submission.workflow_status = 'rejected'
    submission.status = 'rejected'
    submission.rejection_reason = data.get('reason', '')
    submission.rejected_at = datetime.now()
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
    if user.role != 'admin' and not is_hr and not is_gm:
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
def mark_all_notifications_read():
    """Mark all notifications as read"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    return jsonify({'success': True})
