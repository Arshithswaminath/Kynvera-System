import os
import json
import logging
import traceback
from datetime import datetime
from flask import Blueprint, current_app, render_template, request, jsonify, url_for, send_from_directory
from common.utils import random_id, save_uploaded_file_cloud, upload_base64_to_cloud, is_path_safe_for_directory
from common.db_utils import create_submission_db, create_job_db, update_job_progress_db, complete_job_db, fail_job_db, get_job_status_db, get_submission_db
from app.models import db, User
from app.middleware import token_required
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.services.cloudinary_service import upload_local_file
from common.error_responses import error_response, success_response
from common.datetime_utils import utc_now_naive
from common.workflow_notifications import send_inspection_submitted

# Rate limiting helper
def get_limiter():
    """Get rate limiter from current app"""
    try:
        return current_app.limiter
    except (AttributeError, RuntimeError):
        return None

def rate_limit_if_available(limit_str):
    """Decorator to apply rate limiting if limiter is available"""
    def decorator(f):
        limiter = get_limiter()
        if limiter:
            return limiter.limit(limit_str)(f)
        return f
    return decorator

logger = logging.getLogger(__name__)

try:
    from .civil_generators import create_excel_report, create_pdf_report
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Could not import civil_generators: {e}")
    def create_excel_report(data, output_dir):
        basename = f"civil_report_{random_id('')}.xlsx"
        path = os.path.join(output_dir, basename)
        with open(path, "wb") as f:
            f.write(b"Dummy CIVIL EXCEL")
        return basename
    def create_pdf_report(data, output_dir):
        basename = f"civil_report_{random_id('')}.pdf"
        path = os.path.join(output_dir, basename)
        with open(path, "wb") as f:
            f.write(b"Dummy CIVIL PDF")
        return basename

BLUEPRINT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FOLDER = os.path.join(BLUEPRINT_DIR, 'templates')

civil_bp = Blueprint('civil_bp', __name__, template_folder=TEMPLATE_FOLDER, static_folder='static')

def app_paths():
    app = current_app
    return app.config['GENERATED_DIR'], app.config['UPLOADS_DIR'], app.config['JOBS_DIR'], app.config['EXECUTOR']

@civil_bp.route('/form', methods=['GET'])
@jwt_required()
def index():
    """Civil form - requires authentication and module access. Supports editing existing submissions."""
    from flask import redirect, url_for, request
    from flask_jwt_extended import get_jwt_identity
    from app.models import Submission
    
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id)) if user_id is not None else None
        
        if not user or not user.is_active:
            return render_template('access_denied.html',
                                 module='Civil Works',
                                 message='Your account is inactive. Please contact an administrator.'), 403
        
        # Initialize variables
        submission_data = None
        is_edit_mode = False
        
        # Allow admins, supervisors, and managers to edit submissions even if they don't have module access
        edit_submission_id = request.args.get('edit')
        
        if edit_submission_id:
            # Check if user can edit (admin, or supervisor/manager of this submission)
            submission = Submission.query.filter_by(submission_id=edit_submission_id).first()
            if not submission:
                return render_template('access_denied.html',
                                     module='Civil Works',
                                     message='Submission not found.'), 404
            
            # Allow editing/reviewing based on role and workflow status
            can_edit = False
            can_view = False
            user_designation = user.designation if hasattr(user, 'designation') else None
            workflow_status = submission.workflow_status if hasattr(submission, 'workflow_status') else None
            
            # Admin - always can edit/view
            if user.role == 'admin':
                can_edit = True
                can_view = True
            # Supervisor - can edit ONLY if form is still at their stage, otherwise read-only
            elif user_designation == 'supervisor' and hasattr(submission, 'supervisor_id') and submission.supervisor_id == user.id:
                # Supervisor can edit if form is still at operations_manager_review (pending OM approval)
                # Once OM approves (status changes to bd_procurement_review or beyond), supervisor can only view
                if workflow_status == 'operations_manager_review':
                    # Form submitted but OM hasn't approved yet - supervisor can still edit/resubmit
                    can_edit = True
                    can_view = True
                elif workflow_status in ['bd_procurement_review', 'general_manager_review', 'completed']:
                    # Form has moved past OM - supervisor can only view (read-only)
                    can_view = True
                else:
                    # Draft or initial state - supervisor can edit
                    can_edit = True
                    can_view = True
            # Operations Manager - can review/edit while form is at their stage, 
            # AND can still edit if form moved to bd_procurement_review but BD/Procurement haven't approved yet
            elif user_designation == 'operations_manager':
                if workflow_status == 'operations_manager_review':
                    can_edit = True
                    can_view = True
                elif workflow_status == 'bd_procurement_review':
                    # OM can still edit their review if BD and Procurement haven't started approving yet
                    bd_started = hasattr(submission, 'business_dev_approved_at') and submission.business_dev_approved_at
                    proc_started = hasattr(submission, 'procurement_approved_at') and submission.procurement_approved_at
                    if not bd_started and not proc_started:
                        can_edit = True
                        can_view = True
                    else:
                        # BD or Procurement has started reviewing - OM can only view
                        can_view = True
                elif hasattr(submission, 'operations_manager_id') and submission.operations_manager_id == user.id:
                    # Can view forms they've already reviewed (for history/document access)
                    can_view = True
            # Business Development - can edit while form is at bd_procurement_review stage
            # Can re-sign even after signing, and also at general_manager_review if GM hasn't started yet
            elif user_designation == 'business_development':
                if workflow_status == 'bd_procurement_review':
                    # BD can edit while form is at this stage (even after they've signed)
                    can_edit = True
                    can_view = True
                elif workflow_status == 'general_manager_review':
                    # BD can still edit if GM hasn't started reviewing yet
                    gm_started = hasattr(submission, 'general_manager_approved_at') and submission.general_manager_approved_at
                    if not gm_started:
                        can_edit = True
                        can_view = True
                    else:
                        can_view = True
                elif workflow_status == 'completed':
                    # Form is completed - BD can only view
                    can_view = True
                elif hasattr(submission, 'business_dev_id') and submission.business_dev_id == user.id:
                    can_view = True
            # Procurement - can edit while form is at bd_procurement_review stage
            # Can re-sign even after signing, and also at general_manager_review if GM hasn't started yet
            elif user_designation == 'procurement':
                if workflow_status == 'bd_procurement_review':
                    # Procurement can edit while form is at this stage (even after they've signed)
                    can_edit = True
                    can_view = True
                elif workflow_status == 'general_manager_review':
                    # Procurement can still edit if GM hasn't started reviewing yet
                    gm_started = hasattr(submission, 'general_manager_approved_at') and submission.general_manager_approved_at
                    if not gm_started:
                        can_edit = True
                        can_view = True
                    else:
                        can_view = True
                elif workflow_status == 'completed':
                    # Form is completed - Procurement can only view
                    can_view = True
                elif hasattr(submission, 'procurement_id') and submission.procurement_id == user.id:
                    can_view = True
            # General Manager - can edit while form is at general_manager_review stage
            # Can also re-sign even after form is completed (they're the final approver)
            elif user_designation == 'general_manager':
                if workflow_status == 'general_manager_review':
                    # GM can edit while form is at this stage (even after they've signed)
                    can_edit = True
                    can_view = True
                elif workflow_status == 'completed':
                    # GM can still edit their review even after form is completed
                    # (as the final approver, they should be able to modify their decision)
                    can_edit = True
                    can_view = True
                elif hasattr(submission, 'general_manager_id') and submission.general_manager_id == user.id:
                    can_view = True

            # Admin-closed submissions are read-only for all users
            if workflow_status == 'closed_by_admin':
                can_edit = False
                if user.role == 'admin':
                    can_view = True
                elif (
                    (hasattr(submission, 'supervisor_id') and submission.supervisor_id == user.id) or
                    (hasattr(submission, 'operations_manager_id') and submission.operations_manager_id == user.id) or
                    (hasattr(submission, 'business_dev_id') and submission.business_dev_id == user.id) or
                    (hasattr(submission, 'procurement_id') and submission.procurement_id == user.id) or
                    (hasattr(submission, 'general_manager_id') and submission.general_manager_id == user.id)
                ):
                    can_view = True
            
            if not can_view:
                return render_template('access_denied.html',
                                     module='Civil Works',
                                     message=f'You do not have permission to review this submission. Current status: {workflow_status}, Your role: {user_designation}'), 403
            
            # Load submission data for editing
            submission_dict = submission.to_dict()
            # Parse form_data if it's a string
            form_data = submission_dict.get('form_data', {})
            if isinstance(form_data, str):
                try:
                    form_data = json.loads(form_data)
                except:
                    form_data = {}
            
            # Merge Supervisor data from nested form_data.data if not already present
            # This ensures OM and other reviewers can see supervisor signature/comments
            if not form_data.get('supervisor_signature') and not form_data.get('supervisor_signature_url'):
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data and (nested_data.get('supervisor_signature') or nested_data.get('supervisor_signature_url')):
                        form_data['supervisor_signature'] = nested_data.get('supervisor_signature') or nested_data.get('supervisor_signature_url')
                        logger.info(f"✅ Found Supervisor signature in nested form_data.data structure")
            if not form_data.get('supervisor_comments') and isinstance(submission.form_data, dict):
                nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                if nested_data and nested_data.get('supervisor_comments'):
                    form_data['supervisor_comments'] = nested_data.get('supervisor_comments')
                    logger.info(f"✅ Found Supervisor comments in nested form_data.data structure")
            
            # Merge Operations Manager comments from model field into form_data if not already present
            # This ensures BD and other reviewers can see OM comments even if not in form_data
            if hasattr(submission, 'operations_manager_comments') and submission.operations_manager_comments:
                if not form_data.get('operations_manager_comments'):
                    form_data['operations_manager_comments'] = submission.operations_manager_comments
                    logger.info(f"✅ Added Operations Manager comments from model field to form_data for display")
            
            # Operations Manager signature: check form_data first, then model field, then nested
            if not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
                # First check top-level form_data directly from submission
                fd = submission.form_data if isinstance(submission.form_data, dict) else {}
                if isinstance(fd, str):
                    try:
                        fd = json.loads(fd)
                    except:
                        fd = {}
                sig = fd.get('operations_manager_signature') or fd.get('opMan_signature')
                if sig:
                    form_data['operations_manager_signature'] = sig
                    logger.info(f"✅ Found Operations Manager signature in form_data for display")
                elif fd.get('data') and isinstance(fd['data'], dict):
                    nested = fd['data']
                    sig = nested.get('operations_manager_signature') or nested.get('opMan_signature')
                    if sig:
                        form_data['operations_manager_signature'] = sig
                        logger.info(f"✅ Found Operations Manager signature in nested form_data.data for display")
                else:
                    # If still not found, log for debugging
                    logger.warning(f"⚠️ Operations Manager signature not found in form_data for submission {submission.submission_id}")
                    logger.warning(f"  - form_data keys: {list(form_data.keys()) if isinstance(form_data, dict) else 'not a dict'}")
                    logger.warning(f"  - submission.form_data type: {type(submission.form_data)}")
                    if isinstance(submission.form_data, dict):
                        logger.warning(f"  - submission.form_data keys: {list(submission.form_data.keys())[:20]}")
            
            # Merge Business Development comments from model field into form_data if not already present
            # CRITICAL: Only use actual BD comments, never fall back to supervisor comments
            existing_bd_comments = form_data.get('business_dev_comments')
            supervisor_comments = form_data.get('supervisor_comments')
            
            # Check if BD comments are incorrectly set to supervisor comments
            if existing_bd_comments and supervisor_comments and existing_bd_comments == supervisor_comments:
                logger.warning(f"⚠️ WARNING: BD comments appear to be incorrectly set to supervisor comments for submission {submission.submission_id}!")
                form_data['business_dev_comments'] = None
                existing_bd_comments = None
            
            if hasattr(submission, 'business_dev_comments') and submission.business_dev_comments:
                if not existing_bd_comments or existing_bd_comments == supervisor_comments:
                    form_data['business_dev_comments'] = submission.business_dev_comments
                    logger.info(f"✅ Added Business Development comments from model field to form_data for display")
            
            if not form_data.get('business_dev_signature') and not form_data.get('businessDevSignature'):
                fd = submission.form_data if isinstance(submission.form_data, dict) else {}
                sig = fd.get('business_dev_signature') or fd.get('businessDevSignature')
                if sig:
                    form_data['business_dev_signature'] = sig
                    logger.info(f"✅ Found Business Development signature in form_data for display")
                elif fd.get('data') and isinstance(fd['data'], dict):
                    sig = (fd['data'].get('business_dev_signature') or fd['data'].get('businessDevSignature'))
                    if sig:
                        form_data['business_dev_signature'] = sig
            
            # CRITICAL: Only use actual Procurement comments, never fall back to supervisor/BD comments
            existing_proc_comments = form_data.get('procurement_comments')
            
            # Check if Procurement comments are incorrectly set to supervisor or BD comments
            if existing_proc_comments and supervisor_comments and existing_proc_comments == supervisor_comments:
                logger.warning(f"⚠️ WARNING: Procurement comments appear to be incorrectly set to supervisor comments for submission {submission.submission_id}!")
                form_data['procurement_comments'] = None
                existing_proc_comments = None
            
            if hasattr(submission, 'procurement_comments') and submission.procurement_comments:
                if not existing_proc_comments:
                    form_data['procurement_comments'] = submission.procurement_comments
                    logger.info(f"✅ Added Procurement comments from model field to form_data for display")
            
            if not form_data.get('procurement_signature') and not form_data.get('procurementSignature'):
                fd = submission.form_data if isinstance(submission.form_data, dict) else {}
                sig = fd.get('procurement_signature') or fd.get('procurementSignature')
                if sig:
                    form_data['procurement_signature'] = sig
                    logger.info(f"✅ Found Procurement signature in form_data for display")
                elif fd.get('data') and isinstance(fd['data'], dict):
                    sig = (fd['data'].get('procurement_signature') or fd['data'].get('procurementSignature'))
                    if sig:
                        form_data['procurement_signature'] = sig
            
            # CRITICAL: Only use actual GM comments, never fall back to supervisor/BD/Proc comments
            existing_gm_comments = form_data.get('general_manager_comments')
            
            # Check if GM comments are incorrectly set to supervisor comments
            if existing_gm_comments and supervisor_comments and existing_gm_comments == supervisor_comments:
                logger.warning(f"⚠️ WARNING: GM comments appear to be incorrectly set to supervisor comments for submission {submission.submission_id}!")
                form_data['general_manager_comments'] = None
                existing_gm_comments = None
            
            if hasattr(submission, 'general_manager_comments') and submission.general_manager_comments:
                if not existing_gm_comments:
                    form_data['general_manager_comments'] = submission.general_manager_comments
                    logger.info(f"✅ Added General Manager comments from model field to form_data for display")
            
            if not form_data.get('general_manager_signature') and not form_data.get('generalManagerSignature'):
                fd = submission.form_data if isinstance(submission.form_data, dict) else {}
                sig = fd.get('general_manager_signature') or fd.get('generalManagerSignature')
                if sig:
                    form_data['general_manager_signature'] = sig
                elif fd.get('data') and isinstance(fd['data'], dict):
                    sig = (fd['data'].get('general_manager_signature') or fd['data'].get('generalManagerSignature'))
                    if sig:
                        form_data['general_manager_signature'] = sig
            
            submission_data = {
                'submission_id': submission.submission_id,
                'site_name': submission.site_name or '',
                'visit_date': submission.visit_date.isoformat() if submission.visit_date else '',
                'form_data': form_data,
                'is_edit_mode': True,
                'workflow_status': submission.workflow_status if hasattr(submission, 'workflow_status') else None,
                'supervisor_id': submission.supervisor_id if hasattr(submission, 'supervisor_id') else None,
                'can_edit': can_edit,  # Pass can_edit to JavaScript so it can show editable vs read-only UI
                'operations_manager_approved_at': submission.operations_manager_approved_at.isoformat() if hasattr(submission, 'operations_manager_approved_at') and submission.operations_manager_approved_at else None,
                'business_dev_approved_at': submission.business_dev_approved_at.isoformat() if hasattr(submission, 'business_dev_approved_at') and submission.business_dev_approved_at else None,
                'procurement_approved_at': submission.procurement_approved_at.isoformat() if hasattr(submission, 'procurement_approved_at') and submission.procurement_approved_at else None,
                'general_manager_approved_at': submission.general_manager_approved_at.isoformat() if hasattr(submission, 'general_manager_approved_at') and submission.general_manager_approved_at else None,
                'operations_manager_comments': form_data.get('operations_manager_comments') or (submission.operations_manager_comments if hasattr(submission, 'operations_manager_comments') else None),
                'operations_manager_signature': form_data.get('operations_manager_signature') or form_data.get('opMan_signature'),
                'business_dev_comments': form_data.get('business_dev_comments') or (submission.business_dev_comments if hasattr(submission, 'business_dev_comments') else None),
                'business_dev_signature': form_data.get('business_dev_signature') or form_data.get('businessDevSignature'),
                'procurement_comments': form_data.get('procurement_comments') or (submission.procurement_comments if hasattr(submission, 'procurement_comments') else None),
                'procurement_signature': form_data.get('procurement_signature') or form_data.get('procurementSignature'),
                'general_manager_comments': form_data.get('general_manager_comments') or (submission.general_manager_comments if hasattr(submission, 'general_manager_comments') else None),
                'general_manager_signature': form_data.get('general_manager_signature') or form_data.get('generalManagerSignature'),
            }
            is_edit_mode = True
        else:
            # Normal form access - check module access
            if not user.has_module_access('civil'):
                return render_template('access_denied.html',
                                     module='Civil Works',
                                     message='You do not have access to this module. Please contact an administrator to grant access.'), 403
        
        # Pass designation info so the template can adjust signature visibility
        user_designation = user.designation if hasattr(user, 'designation') else None
        
        # Only supervisors (and admins acting as supervisors) should use the supervisor edit path
        # Operations Manager, BD, Procurement, GM use their own workflow-specific paths
        is_supervisor_edit = is_edit_mode and (user_designation == 'supervisor' or (user.role == 'admin' and request.args.get('review') != 'true'))
        
        # Pass can_edit to template so it knows if user can modify the form
        can_edit_form = False
        if edit_submission_id and 'can_edit' in locals():
            can_edit_form = can_edit
        elif not edit_submission_id:
            # New form - supervisor can always create
            can_edit_form = True
        
        return render_template(
            'civil_form.html',
            submission_data=submission_data,
            is_edit_mode=is_edit_mode,
            user_designation=user_designation,
            is_supervisor_edit=is_supervisor_edit,
            can_edit=can_edit_form,
            user=user
        )
    except Exception as e:
        logger.error(f"Error checking module access: {str(e)}")
        # If JWT check fails, redirect to login
        return redirect(url_for('login_page'))

@civil_bp.route('/dropdowns', methods=['GET'])
def dropdowns():
    local = os.path.join(BLUEPRINT_DIR, 'dropdown_data.json')
    if os.path.exists(local):
        with open(local, 'r') as f:
            return jsonify(json.load(f))
    central = os.path.join(current_app.config.get('BASE_DIR', ''), 'data', 'dropdown_data.json')
    if os.path.exists(central):
        with open(central, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({})

@civil_bp.route('/save-draft', methods=['POST'])
def save_draft():
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = app_paths()
    payload = request.get_json(force=True)
    draft_id = random_id("draft")
    drafts_dir = os.path.join(GENERATED_DIR, "drafts")
    os.makedirs(drafts_dir, exist_ok=True)
    with open(os.path.join(drafts_dir, f"{draft_id}.json"), 'w') as f:
        json.dump(payload, f)
    return jsonify({"status": "ok", "draft_id": draft_id})

@civil_bp.route('/submit', methods=['POST'])
@rate_limit_if_available('10 per minute')  # Limit form submissions
def submit():
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = app_paths()
    
    # Validate required fields
    fields = dict(request.form)
    required_fields = ['project_name', 'location', 'date']
    missing = [f for f in required_fields if not fields.get(f) or not fields.get(f).strip()]
    if missing:
        logger.warning(f"Missing required fields: {missing}")
        return error_response(f"Missing required fields: {', '.join(missing)}", status_code=400, error_code='VALIDATION_ERROR')
    
    # Validate date format
    try:
        from datetime import datetime, timedelta
        visit_date = datetime.strptime(fields.get('date'), '%Y-%m-%d').date()
        # Only reject dates that are clearly in the future (more than 1 day ahead)
        # This accounts for timezone differences while still catching obvious errors
        today_utc = utc_now_naive().date()
        # Allow today and tomorrow to account for timezone differences (GST is UTC+4)
        max_allowed_date = today_utc + timedelta(days=1)
        logger.info(f"Date validation (/submit): visit_date={visit_date}, today_utc={today_utc}, max_allowed={max_allowed_date}")
        if visit_date > max_allowed_date:
            logger.warning(f"Rejected future date: {visit_date} > {max_allowed_date}")
            return error_response(f"Visit date ({visit_date}) cannot be more than 1 day in the future", status_code=400, error_code='VALIDATION_ERROR')
    except ValueError as e:
        logger.error(f"Invalid date format: {fields.get('date')}, error: {e}")
        return error_response("Invalid date format. Use YYYY-MM-DD", status_code=400, error_code='VALIDATION_ERROR')
    
    saved_files = []
    for key in request.files:
        f = request.files.get(key)
        if f and f.filename:
            try:
                result = save_uploaded_file_cloud(f, UPLOADS_DIR, folder="civil_photos")
                saved_files.append({
                    "field": key,
                    "saved": None,
                    "url": result["url"],
                    "is_cloud": True
                })
            except (IOError, OSError) as e:
                logger.error(f"File system error uploading file: {e}")
                return error_response("File storage error", status_code=500, error_code='STORAGE_ERROR')
            except ValueError as e:
                logger.error(f"Invalid file data: {e}")
                return error_response("Invalid file data", status_code=400, error_code='VALIDATION_ERROR')
            except Exception as e:
                logger.error(f"Unexpected error uploading file: {e}")
                return error_response("Cloud storage error", status_code=500, error_code='STORAGE_ERROR')
    # Create submission in database
    submission_data = {
        "fields": fields,
        "files": saved_files,
        "base_url": request.host_url.rstrip('/')
    }
    
    # Get user_id from JWT token if available
    user_id = None
    try:
        from flask_jwt_extended import verify_jwt_in_request
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                logger.info(f"✅ Submission will be associated with user_id: {user_id}")
        except Exception:
            pass  # No token or invalid token - submission will be anonymous
    except Exception:
        pass  # JWT not available
    
    submission = create_submission_db(
        module_type='civil',
        form_data=submission_data,
        site_name=fields.get('project_name'),
        visit_date=fields.get('date'),
        user_id=user_id
    )
    sub_id = submission.submission_id

    # Trigger real-time inspection submission email.
    try:
        submitter_user = db.session.get(User, int(user_id)) if user_id else None
        send_inspection_submitted(submission, submitter_user)
    except Exception as notify_err:
        logger.warning(f"Submission email notification failed for {sub_id}: {notify_err}")

    # Create job in database
    job = create_job_db(submission)
    job_id = job.job_id

    def task_generate_reports(job_id_local, sub_id_local, base_url, app):
        logger.debug(f"task_generate_reports called for {job_id_local}")
        with app.app_context():
            try:
                update_job_progress_db(job_id_local, 10, status='processing')
                
                # Get submission data from database
                data = get_submission_db(sub_id_local)
                if not data:
                    fail_job_db(job_id_local, "Submission not found")
                    return

                # Generate Excel
                logger.info("📊 Generating Excel report...")
                excel_path = create_excel_report(data, output_dir=GENERATED_DIR)
                excel_filename = os.path.basename(excel_path)
                logger.info(f"✅ Excel created: {excel_filename}")
                excel_url = f"{base_url}/generated/{excel_filename}"
                update_job_progress_db(job_id_local, 40)

                # Generate PDF
                logger.info("📄 Generating PDF report...")
                pdf_path = create_pdf_report(data, output_dir=GENERATED_DIR)
                pdf_filename = os.path.basename(pdf_path)
                logger.info(f"✅ PDF created: {pdf_filename}")
                pdf_url = f"{base_url}/generated/{pdf_filename}"
                update_job_progress_db(job_id_local, 60)

                # Set results
                results = {
                    "excel": excel_url,
                    "excel_filename": excel_filename,
                    "pdf": pdf_url,
                    "pdf_filename": pdf_filename
                }

                complete_job_db(job_id_local, results)
            except Exception as e:
                logger.exception(f"Report generation failed: {e}")
                fail_job_db(job_id_local, str(e))

    EXECUTOR.submit(task_generate_reports, job_id, sub_id, request.host_url.rstrip('/'), current_app._get_current_object())
    return jsonify({"status": "queued", "job_id": job_id, "submission_id": sub_id, "files": saved_files})

@civil_bp.route('/status/<job_id>', methods=['GET'])
def status(job_id):
    try:
        job_data = get_job_status_db(job_id)
        if not job_data:
            return error_response("Job not found", 404, "JOB_NOT_FOUND")
        return jsonify(job_data)
    except Exception as e:
        logger.error(f"Status check failed for {job_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return error_response("Status check failed", 500, "INTERNAL_ERROR", str(e))


@civil_bp.route("/generated/<path:filename>", methods=["GET"])
def download_generated(filename):
    """Download generated files (Excel/PDF reports)"""
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = app_paths()
    # allow nested paths like uploads/<name>
    return send_from_directory(GENERATED_DIR, filename, as_attachment=True)


@civil_bp.route("/download/<job_id>/<file_type>", methods=["GET"])
def download_file(job_id, file_type):
    """
    Download proxy route that fetches files from Cloudinary or local storage
    and serves them with proper download headers for auto-download.
    
    Args:
        job_id: Job ID to get file URLs from
        file_type: 'excel' or 'pdf'
    """
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = app_paths()
    
    try:
        import requests
        from io import BytesIO
        
        # Get job data from database
        job_data = get_job_status_db(job_id)
        if not job_data:
            logger.error(f"Job not found: {job_id}")
            return error_response("Job not found", 404, "JOB_NOT_FOUND")
        
        # Extract results
        results = {}
        if isinstance(job_data, dict):
            results = job_data.get('results', {}) or job_data.get('result_data', {}) or job_data.get('results_data', {})
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    logger.warning(f"Failed to parse results as JSON")
                    results = {}
        
        if not results:
            logger.error(f"Job results not found for {job_id}")
            return error_response("Job results not found", status_code=404, error_code='NOT_FOUND')
        
        # Get file URL and filename based on file_type
        if file_type == 'excel':
            file_url = results.get('excel') or results.get('excel_url')
            filename = results.get('excel_filename') or 'civil_report.xlsx'
        elif file_type == 'pdf':
            file_url = results.get('pdf') or results.get('pdf_url')
            filename = results.get('pdf_filename') or 'civil_report.pdf'
        else:
            return error_response("Invalid file type", status_code=400, error_code='VALIDATION_ERROR')
        
        if not file_url:
            return error_response(f"{file_type.upper()} file URL not found", status_code=404, error_code='NOT_FOUND')
        
        # Check if it's a localhost/local development URL
        if file_url.startswith('http://127.0.0.1') or file_url.startswith('http://localhost') or file_url.startswith('http://0.0.0.0'):
            # Local development URL - extract filename and serve from local storage
            # URL might contain # which breaks URL parsing, so we need to handle it carefully
            from urllib.parse import urlparse, unquote
            # Reconstruct the full path including fragment (everything after #)
            # Split by # to get path and fragment separately
            if '#' in file_url:
                url_parts = file_url.split('#', 1)
                base_url = url_parts[0]
                fragment = url_parts[1] if len(url_parts) > 1 else ''
                parsed = urlparse(base_url)
                # Reconstruct full filename: path + fragment
                full_path = parsed.path
                if fragment:
                    # If fragment exists, it's part of the filename (not a URL fragment)
                    full_path = full_path + '#' + fragment
            else:
                parsed = urlparse(file_url)
                full_path = parsed.path
            
            # Extract filename from path
            local_filename = unquote(full_path.lstrip('/').replace('generated/', ''))
            local_path = os.path.join(GENERATED_DIR, local_filename)
            
            if not is_path_safe_for_directory(GENERATED_DIR, local_path):
                logger.warning(f"Path traversal attempt blocked: {local_path}")
                return error_response("Invalid file path", status_code=403, error_code='FORBIDDEN')
            
            logger.debug(f"Local URL detected, serving from filesystem: {local_path}")
            
            if not os.path.exists(local_path):
                logger.error(f"File not found at local path: {local_path}")
                return error_response("File not found locally", status_code=404, error_code='NOT_FOUND')
            
            from flask import send_file
            return send_file(local_path, as_attachment=True, download_name=filename)
        elif file_url.startswith('http://') or file_url.startswith('https://'):
            # Cloudinary URL or other HTTP URL - fetch and serve
            try:
                logger.debug(f"Fetching {file_type.upper()} file from URL: {file_url}")
                # Remove ?attachment=true if present
                clean_url = file_url.split('?')[0]
                logger.debug(f"Clean URL (removed query params): {clean_url}")
                
                response = requests.get(clean_url, timeout=60, stream=True)
                response.raise_for_status()
                logger.debug(f"Successfully fetched {file_type.upper()} file, status: {response.status_code}, content-length: {response.headers.get('Content-Length', 'unknown')}")
                
                file_content = response.content
                file_data = BytesIO(file_content)
                file_data.seek(0)
                
                mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_type == 'excel' else 'application/pdf'
                
                if len(file_content) == 0:
                    logger.error(f"Empty file content received")
                    return error_response("File content is empty", status_code=500, error_code='STORAGE_ERROR')
                
                from flask import send_file
                return send_file(
                    file_data,
                    mimetype=mimetype,
                    as_attachment=True,
                    download_name=filename
                )
            except Exception as e:
                logger.error(f"Error fetching file: {str(e)}")
                logger.error(traceback.format_exc())
                return error_response("Failed to fetch file", status_code=500, error_code='STORAGE_ERROR')
        else:
            # Local URL
            local_filename = file_url.lstrip('/').replace('generated/', '')
            local_path = os.path.join(GENERATED_DIR, local_filename)
            
            if not is_path_safe_for_directory(GENERATED_DIR, local_path):
                logger.warning(f"Path traversal attempt blocked: {local_path}")
                return error_response("Invalid file path", status_code=403, error_code='FORBIDDEN')
            
            if not os.path.exists(local_path):
                return error_response("File not found locally", status_code=404, error_code='NOT_FOUND')
            
            from flask import send_file
            return send_file(local_path, as_attachment=True, download_name=filename)
    
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response("Download failed", status_code=500, error_code='INTERNAL_ERROR')


# ---------- Progressive Upload Endpoints ----------

@civil_bp.route("/upload-photo", methods=["POST"])
def upload_photo():
    """Upload a single photo immediately to cloud storage."""
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = app_paths()
    
    try:
        if 'photo' not in request.files:
            return jsonify({"success": False, "error": "No photo file provided"}), 400
        
        photo_file = request.files['photo']
        if photo_file.filename == '':
            return jsonify({"success": False, "error": "Empty filename"}), 400
        
        logger.info(f"Uploading photo: {photo_file.filename}")
        
        # Upload directly to cloud storage with proper error handling
        try:
            result = save_uploaded_file_cloud(photo_file, UPLOADS_DIR, folder="civil_photos")
            
            if not result or not result.get("url"):
                logger.error("Upload returned no URL")
                return error_response("Upload failed - no URL returned", status_code=500, error_code='STORAGE_ERROR')
            
            logger.info(f"✅ Photo uploaded successfully: {result['url']}")
            
            return jsonify({
                "success": True,
                "url": result["url"],
                "is_cloud": result.get("is_cloud", False),
                "filename": photo_file.filename
            })
            
        except Exception as upload_error:
            logger.error(f"Upload error: {str(upload_error)}")
            logger.error(traceback.format_exc())
            return jsonify({"success": False, "error": f"Upload failed: {str(upload_error)}"}), 500
        
    except Exception as e:
        logger.error(f"❌ Civil photo upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def save_signature_dataurl(dataurl, uploads_dir, prefix="signature"):
    """
    Upload signature to cloud storage with local fallback.
    Returns (saved_filename_or_none, file_path_or_none, public_url) tuple.
    """
    if not dataurl:
        return None, None, None
    
    try:
        # Try cloud upload first, with local fallback
        url, is_cloud = upload_base64_to_cloud(dataurl, folder="signatures", prefix=prefix, uploads_dir=uploads_dir)
        
        if url:
            if is_cloud:
                logger.info(f"✅ Signature uploaded to cloud: {url}")
                return None, None, url  # No local file for cloud uploads
            else:
                # Local storage - extract filename from URL
                # URL format: /generated/uploads/signatures/filename.png
                filename = url.split('/')[-1]
                # Get the full path
                from config import GENERATED_DIR
                file_path = os.path.join(GENERATED_DIR, "uploads", "signatures", filename)
                logger.info(f"✅ Signature saved locally: {url}")
                return filename, file_path, url
        
        raise Exception("Upload succeeded but no URL returned")
        
    except Exception as e:
        logger.error(f"❌ Signature upload failed: {e}")
        raise Exception(f"Signature upload failed: {str(e)}")


@civil_bp.route("/submit-with-urls", methods=["POST"])
def submit_with_urls():
    """Submit form data where photos are already uploaded to cloud."""
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = app_paths()
    
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(JOBS_DIR, exist_ok=True)
    
    try:
        payload = request.get_json(force=True)
        
        # Validate required fields
        project_name = payload.get("project_name", "").strip()
        location = payload.get("location", "").strip()
        visit_date = payload.get("visit_date", "").strip()
        
        if not project_name:
            return error_response("Project name is required", 400, "VALIDATION_ERROR")
        if not location:
            return error_response("Location is required", 400, "VALIDATION_ERROR")
        
        # Validate date format
        if visit_date:
            try:
                parsed_date = datetime.strptime(visit_date, '%Y-%m-%d').date()
                # Only reject dates that are clearly in the future (more than 1 day ahead)
                # This accounts for timezone differences while still catching obvious errors
                from datetime import timedelta
                today_utc = utc_now_naive().date()
                # Allow today and tomorrow to account for timezone differences (GST is UTC+4)
                max_allowed_date = today_utc + timedelta(days=1)
                logger.info(f"Date validation: parsed_date={parsed_date}, today_utc={today_utc}, max_allowed={max_allowed_date}")
                if parsed_date > max_allowed_date:
                    logger.warning(f"Rejected future date: {parsed_date} > {max_allowed_date}")
                    return error_response(f"Visit date ({parsed_date}) cannot be more than 1 day in the future", 400, "VALIDATION_ERROR")
            except ValueError as e:
                logger.error(f"Invalid date format: {visit_date}, error: {e}")
                return error_response("Invalid date format. Use YYYY-MM-DD", 400, "VALIDATION_ERROR")
        
        # Process signatures (data URLs)
        inspector_sig_dataurl = payload.get("inspector_signature", "")
        manager_sig_dataurl = payload.get("manager_signature", "")
        
        inspector_sig_file = None
        manager_sig_file = None
        
        if inspector_sig_dataurl:
            fname, fpath, url = save_signature_dataurl(inspector_sig_dataurl, UPLOADS_DIR, prefix="inspector_sig")
            if url:
                inspector_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
        
        if manager_sig_dataurl:
            fname, fpath, url = save_signature_dataurl(manager_sig_dataurl, UPLOADS_DIR, prefix="manager_sig")
            if url:
                manager_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
        
        # Extract work items with photo URLs
        work_items = payload.get("work_items", [])
        logger.info(f"📋 Received {len(work_items)} work items")
        processed_items = []
        
        total_photos = 0
        for idx, item_data in enumerate(work_items):
            photo_urls = item_data.get("photo_urls", [])
            logger.info(f"  Work item {idx + 1}: {len(photo_urls)} photo URLs")
            photos_saved = []
            
            for url_idx, url in enumerate(photo_urls):
                logger.info(f"    Photo {url_idx + 1}: {url[:80] if url else 'NO URL'}...")
                photos_saved.append({
                    "saved": None,
                    "path": None,
                    "url": url,
                    "is_cloud": True
                })
            
            total_photos += len(photos_saved)
            processed_items.append({
                "item_number": item_data.get("item_number", ""),
                "description": item_data.get("description", ""),
                "quantity": item_data.get("quantity", ""),
                "material": item_data.get("material", ""),
                "material_qty": item_data.get("material_qty", ""),
                "specification": item_data.get("specification", ""),
                "unit_price": item_data.get("unit_price", ""),
                "price": item_data.get("price", ""),
                "labour": item_data.get("labour", ""),
                "comments": item_data.get("comments", ""),
                "photos": photos_saved
            })
        
        logger.info(f"📸 Total photos processed: {total_photos}")
        
        # Process supervisor signature if present
        supervisor_sig_dataurl = payload.get("supervisor_signature", "")
        supervisor_comments = payload.get("supervisor_comments", "")
        supervisor_sig_file = None
        
        if supervisor_sig_dataurl:
            fname, fpath, url = save_signature_dataurl(supervisor_sig_dataurl, UPLOADS_DIR, prefix="supervisor_sig")
            if url:
                supervisor_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
        
        # Create submission in database
        submission_data = {
            "project_name": project_name,
            "location": location,
            "visit_date": visit_date,
            "inspector_name": payload.get("inspector_name", ""),
            "inspector_signature": inspector_sig_file,
            "supervisor_signature": supervisor_sig_file,
            "supervisor_comments": supervisor_comments,
            "description_of_work": payload.get("description_of_work", ""),
            "area": payload.get("area", ""),
            "area_other": payload.get("area_other", ""),
            "work_items": processed_items,
            "base_url": request.host_url.rstrip('/'),
            "created_at": utc_now_naive().isoformat()
        }
        
        # Get user_id from JWT token if available
        user_id = None
        try:
            from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id:
                    logger.info(f"✅ Submission will be associated with user_id: {user_id}")
            except Exception as jwt_error:
                logger.debug(f"JWT token not available or invalid: {jwt_error}")
        except Exception as e:
            logger.debug(f"JWT verification error: {e}")
            pass  # JWT not available
        
        submission = create_submission_db(
            module_type='civil',
            form_data=submission_data,
            site_name=project_name,
            visit_date=visit_date,
            user_id=user_id
        )
        sub_id = submission.submission_id

        # Trigger real-time inspection submission email.
        try:
            submitter_user = db.session.get(User, int(user_id)) if user_id else None
            send_inspection_submitted(submission, submitter_user)
        except Exception as notify_err:
            logger.warning(f"Submission email notification failed for {sub_id}: {notify_err}")
        
        logger.info(f"✅ Civil submission {sub_id} saved with {len(processed_items)} work items")
        
        # Create job in database
        job = create_job_db(submission)
        job_id = job.job_id
        
        logger.info(f"Starting background task for job {job_id}")
        
        # Submit to executor using process_job pattern like HVAC
        if EXECUTOR:
            future = EXECUTOR.submit(
                process_job,
                sub_id,
                job_id,
                current_app.config,
                current_app._get_current_object()
            )
            
            # Add error callback to catch silent failures
            def log_exception(fut):
                try:
                    fut.result()
                except Exception as e:
                    logger.error(f"❌ FATAL: Background job {job_id} crashed: {e}")
                    logger.error(traceback.format_exc())
            
            future.add_done_callback(log_exception)
            logger.info(f"✅ Background job {job_id} submitted to executor")
        else:
            logger.error("ThreadPoolExecutor not found in app config")
            return jsonify({'error': 'Background processing not available'}), 500
        
        logger.info(f"🚀 Civil job {job_id} queued for submission {sub_id}")
        
        return jsonify({
            "status": "ok",
            "submission_id": sub_id,
            "job_id": job_id,
            "job_status_url": url_for("civil_bp.status", job_id=job_id, _external=False)
        })
        
    except Exception as e:
        logger.error(f"❌ Civil submit with URLs failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "error": str(e)}), 500


def process_job(sub_id, job_id, config, app):
    """Background worker: Generate BOTH Excel AND PDF reports"""
    logger.debug(f"process_job called with sub_id={sub_id}, job_id={job_id}")
    from common.module_base import process_report_job
    from .civil_generators import create_excel_report, create_pdf_report
    
    process_report_job(
        sub_id=sub_id,
        job_id=job_id,
        app=app,
        module_name='civil',
        create_excel_report=create_excel_report,
        create_pdf_report=create_pdf_report
    )