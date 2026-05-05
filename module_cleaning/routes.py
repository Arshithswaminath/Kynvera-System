
import os
import json
import logging
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app, send_file, redirect, url_for
from common.utils import (
    random_id, 
    save_uploaded_file,
    save_uploaded_file_cloud,
    upload_base64_to_cloud,
    is_path_safe_for_directory
)
from common.db_utils import (
    create_submission_db,
    create_job_db,
    update_job_progress_db,
    complete_job_db,
    fail_job_db,
    get_job_status_db,
    get_submission_db
)
from common.error_responses import error_response, success_response
from common.datetime_utils import utc_now_naive
from app.models import db, User
from app.middleware import token_required
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.services.cloudinary_service import upload_local_file
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

cleaning_bp = Blueprint('cleaning', __name__, url_prefix='/cleaning', template_folder='templates')

@cleaning_bp.route('/generated/<path:filename>')
def download_generated_cleaning(filename):
    """Serve generated files as download attachments for cleaning module."""
    GENERATED_DIR = current_app.config['GENERATED_DIR']
    safe_path = os.path.join(GENERATED_DIR, filename)
    if not is_path_safe_for_directory(GENERATED_DIR, safe_path):
        logger.warning(f"Path traversal attempt blocked: {filename}")
        return "Forbidden", 403
    if not os.path.exists(safe_path):
        logger.warning(f"File not found: {filename}")
        return "File not found", 404
    # Serve as attachment for download
    return send_file(safe_path, as_attachment=True, download_name=filename)


@cleaning_bp.route("/download/<job_id>/<file_type>", methods=["GET"])
def download_file(job_id, file_type):
    """
    Download proxy route that fetches files from Cloudinary or local storage
    and serves them with proper download headers for auto-download.
    
    Args:
        job_id: Job ID to get file URLs from
        file_type: 'excel' or 'pdf'
    """
    GENERATED_DIR = current_app.config['GENERATED_DIR']
    
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
            filename = results.get('excel_filename') or 'cleaning_report.xlsx'
        elif file_type == 'pdf':
            file_url = results.get('pdf') or results.get('pdf_url')
            filename = results.get('pdf_filename') or 'cleaning_report.pdf'
        else:
            return error_response("Invalid file type", status_code=400, error_code='VALIDATION_ERROR')
        
        if not file_url:
            return error_response(f"{file_type.upper()} file URL not found", status_code=404, error_code='NOT_FOUND')
        
        logger.info(f"Download requested for {file_type}: {file_url}")
        
        # Check if it's a localhost URL (development)
        if file_url.startswith('http://127.0.0.1') or file_url.startswith('http://localhost') or file_url.startswith('http://0.0.0.0'):
            # Local development URL - extract filename and serve from local storage
            from urllib.parse import urlparse, unquote
            
            # Handle URLs with # character in filename
            if '#' in file_url:
                url_parts = file_url.split('#', 1)
                base_url = url_parts[0]
                fragment = url_parts[1] if len(url_parts) > 1 else ''
                parsed = urlparse(base_url)
                full_path = parsed.path
                if fragment:
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
            
            logger.info(f"Local URL detected, serving from filesystem: {local_path}")
            
            if not os.path.exists(local_path):
                logger.error(f"File not found at local path: {local_path}")
                return error_response("File not found locally", status_code=404, error_code='NOT_FOUND')
            
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_type == 'excel' else 'application/pdf'
            return send_file(local_path, as_attachment=True, download_name=filename, mimetype=mimetype)
        
        # Check if it's a Cloudinary URL
        elif 'cloudinary.com' in file_url:
            try:
                clean_url = file_url.split('?')[0]
                response = requests.get(clean_url, timeout=60, stream=True)
                response.raise_for_status()
                
                file_content = response.content
                file_data = BytesIO(file_content)
                file_data.seek(0)
                
                mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_type == 'excel' else 'application/pdf'
                
                if len(file_content) == 0:
                    logger.error(f"Empty file content received from Cloudinary")
                    return error_response("File content is empty", status_code=500, error_code='STORAGE_ERROR')
                
                return send_file(
                    file_data,
                    mimetype=mimetype,
                    as_attachment=True,
                    download_name=filename
                )
            except Exception as e:
                logger.error(f"Error fetching from Cloudinary: {str(e)}")
                logger.error(traceback.format_exc())
                return error_response("Failed to fetch file from Cloudinary", status_code=500, error_code='STORAGE_ERROR')
        else:
            # Relative local URL (starts with /)
            from urllib.parse import unquote
            
            local_filename = unquote(file_url.lstrip('/').replace('generated/', ''))
            local_path = os.path.join(GENERATED_DIR, local_filename)
            
            if not is_path_safe_for_directory(GENERATED_DIR, local_path):
                logger.warning(f"Path traversal attempt blocked: {local_path}")
                return error_response("Invalid file path", status_code=403, error_code='FORBIDDEN')
            
            logger.info(f"Relative URL detected, serving from filesystem: {local_path}")
            
            if not os.path.exists(local_path):
                logger.error(f"File not found at local path: {local_path}")
                return error_response("File not found locally", status_code=404, error_code='NOT_FOUND')
            
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_type == 'excel' else 'application/pdf'
            return send_file(local_path, as_attachment=True, download_name=filename, mimetype=mimetype)
    
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response("Download failed", status_code=500, error_code='INTERNAL_ERROR')

try:
    from .cleaning_generators import create_excel_report, create_pdf_report
    logger.info("✅ Successfully imported cleaning_generators")
except Exception as e:
    logger.error(f"❌ Failed to import generators: {e}")
    def create_excel_report(data, output_dir):
        logger.error("Placeholder: Excel generator not implemented")
        raise NotImplementedError("Excel generator not available")
    
    def create_pdf_report(data, output_dir):
        logger.error("Placeholder: PDF generator not implemented")
        raise NotImplementedError("PDF generator not available")


@cleaning_bp.route('/')
def index():
    """Cleaning module index page"""
    return redirect(url_for('cleaning.form'))


@cleaning_bp.route('/form', methods=['GET'])
@jwt_required()
def form():
    """Cleaning form - requires authentication and module access. Supports editing existing submissions."""
    from flask import redirect, url_for
    from flask_jwt_extended import get_jwt_identity
    from app.models import Submission
    
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id)) if user_id is not None else None
        
        if not user or not user.is_active:
            return render_template('access_denied.html',
                                 module='Cleaning',
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
                                     module='Cleaning',
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
                                     module='Cleaning',
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
            
            # Merge Operations Manager comments from model field into form_data if not already present
            # This ensures BD and other reviewers can see OM comments even if not in form_data
            if hasattr(submission, 'operations_manager_comments') and submission.operations_manager_comments:
                if not form_data.get('operations_manager_comments'):
                    form_data['operations_manager_comments'] = submission.operations_manager_comments
                    logger.info(f"✅ Added Operations Manager comments from model field to form_data for display")
            
            # Operations Manager signature is stored in form_data, but ensure it's there
            if not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data:
                        if nested_data.get('operations_manager_signature'):
                            form_data['operations_manager_signature'] = nested_data.get('operations_manager_signature')
                            logger.info(f"✅ Found Operations Manager signature in nested form_data.data structure")
                        elif nested_data.get('opMan_signature'):
                            form_data['operations_manager_signature'] = nested_data.get('opMan_signature')
                            logger.info(f"✅ Found Operations Manager signature (opMan_signature) in nested form_data.data structure")
            
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
            
            # Business Development signature is stored in form_data, but ensure it's there
            if not form_data.get('business_dev_signature'):
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data:
                        if nested_data.get('business_dev_signature'):
                            form_data['business_dev_signature'] = nested_data.get('business_dev_signature')
                            logger.info(f"✅ Found Business Development signature in nested form_data.data structure")
            
            # Merge Procurement comments from model field into form_data if not already present
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
            
            # Procurement signature is stored in form_data, but ensure it's there
            if not form_data.get('procurement_signature'):
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data:
                        if nested_data.get('procurement_signature'):
                            form_data['procurement_signature'] = nested_data.get('procurement_signature')
                            logger.info(f"✅ Found Procurement signature in nested form_data.data structure")
            
            # Merge General Manager comments from model field into form_data if not already present
            existing_gm_comments = form_data.get('general_manager_comments')
            
            if hasattr(submission, 'general_manager_comments') and submission.general_manager_comments:
                if not existing_gm_comments:
                    form_data['general_manager_comments'] = submission.general_manager_comments
                    logger.info(f"✅ Added General Manager comments from model field to form_data for display")
            
            # General Manager signature - ensure it's in form_data
            if not form_data.get('general_manager_signature'):
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data:
                        if nested_data.get('general_manager_signature'):
                            form_data['general_manager_signature'] = nested_data.get('general_manager_signature')
                            logger.info(f"✅ Found General Manager signature in nested form_data.data structure")
                # Also check model field for GM signature
                if hasattr(submission, 'general_manager_signature') and submission.general_manager_signature:
                    form_data['general_manager_signature'] = submission.general_manager_signature
                    logger.info(f"✅ Added General Manager signature from model field to form_data for display")
            
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
                # Reviewer comments and signatures at top level for easy template access
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
            if not user.has_module_access('cleaning'):
                return render_template('access_denied.html',
                                     module='Cleaning',
                                     message='You do not have access to this module. Please contact an administrator to grant access.'), 403
        
        # Pass designation details so the template can adapt workflow UI
        user_designation = user.designation if hasattr(user, 'designation') else None
        
        # Only treat as "supervisor edit" if actually a supervisor (or admin NOT in review mode)
        # This ensures OM/BD/Procurement/GM in review mode don't get supervisor UI
        review_param = request.args.get('review') == 'true'
        is_supervisor_edit = is_edit_mode and (user_designation == 'supervisor' or (user.role == 'admin' and not review_param))
        
        # Pass can_edit to template so it knows if user can modify the form
        can_edit_form = False
        if edit_submission_id and 'can_edit' in locals():
            can_edit_form = can_edit
        elif not edit_submission_id:
            # New form - supervisor can always create
            can_edit_form = True
        
        return render_template(
            'cleaning_form.html',
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


@cleaning_bp.route('/submit', methods=['POST'])
@rate_limit_if_available('10 per minute')  # Limit form submissions
def submit():
    """Handle form submission and start background job."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response('No data received', status_code=400, error_code='VALIDATION_ERROR')
        
        # Validate required fields
        required_fields = ['project_name', 'date_of_visit']
        missing = [f for f in required_fields if not data.get(f) or not str(data.get(f)).strip()]
        if missing:
            logger.warning(f"Missing required fields: {missing}")
            return error_response(f"Missing required fields: {', '.join(missing)}", status_code=400, error_code='VALIDATION_ERROR')
        
        # Validate date - allow past dates and today, reject future dates (>1 day)
        date_str = data.get('date_of_visit', '')
        if date_str:
            try:
                from datetime import timedelta
                visit_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                # Use UTC date and add 1 day buffer to account for timezone differences
                today_utc = utc_now_naive().date()
                max_allowed_date = today_utc + timedelta(days=1)
                logger.info(f"Date validation (Cleaning): parsed_date={visit_date}, today_utc={today_utc}, max_allowed={max_allowed_date}")
                if visit_date > max_allowed_date:
                    logger.warning(f"Rejected future date: {visit_date} > {max_allowed_date}")
                    return error_response(f'Visit date ({visit_date}) cannot be more than 1 day in the future', status_code=400, error_code='VALIDATION_ERROR')
            except ValueError as e:
                logger.error(f"Invalid date format: {date_str}, error: {e}")
                return error_response('Invalid date format. Use YYYY-MM-DD', status_code=400, error_code='VALIDATION_ERROR')
        
        GENERATED_DIR = current_app.config['GENERATED_DIR']
        UPLOADS_DIR = current_app.config['UPLOADS_DIR']
        JOBS_DIR = current_app.config['JOBS_DIR']
        
        # Ensure directories exist
        os.makedirs(GENERATED_DIR, exist_ok=True)
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        os.makedirs(JOBS_DIR, exist_ok=True)
        
        # Generate unique IDs
        submission_id = random_id('sub')
        job_id = random_id('job')
        
        # Save uploaded photos (assuming base64 data from frontend)
        photos = data.get('photos', [])
        saved_photos = []
        
        for idx, photo_base64 in enumerate(photos):
            if photo_base64 and photo_base64.startswith('data:image'):
                try:
                    # Cloud upload with local fallback
                    cloud_url, is_cloud = upload_base64_to_cloud(
                        photo_base64, 
                        folder="cleaning_photos", 
                        prefix=f"photo_{idx}",
                        uploads_dir=UPLOADS_DIR
                    )
                    
                    saved_photos.append({
                        'saved': None,
                        'path': None,
                        'url': cloud_url,
                        'index': idx,
                        'is_cloud': is_cloud
                    })
                except Exception as e:
                    logger.error(f"Failed to upload photo {idx}: {e}")
                    return jsonify({'error': f'Storage error for photo {idx}: {str(e)}'}), 500
        
        data['photos'] = saved_photos
        
        # Save signatures (base64 data) with local fallback
        tech_signature = data.get('tech_signature', '')
        supervisor_signature = data.get('supervisor_signature', '')
        supervisor_comments = data.get('supervisor_comments', '')
        
        if tech_signature and tech_signature.startswith('data:image'):
            try:
                # Cloud upload with local fallback
                cloud_url, is_cloud = upload_base64_to_cloud(
                    tech_signature, 
                    folder="signatures", 
                    prefix="tech_sig",
                    uploads_dir=UPLOADS_DIR
                )
                
                data['tech_signature'] = {
                    'saved': None,
                    'path': None,
                    'url': cloud_url,
                    'is_cloud': is_cloud
                }
            except Exception as e:
                logger.error(f"Failed to upload tech signature: {e}")
                return error_response('Storage error for tech signature', status_code=500, error_code='STORAGE_ERROR')
        
        if supervisor_signature and supervisor_signature.startswith('data:image'):
            try:
                # Cloud upload with local fallback
                cloud_url, is_cloud = upload_base64_to_cloud(
                    supervisor_signature, 
                    folder="signatures", 
                    prefix="supervisor_sig",
                    uploads_dir=UPLOADS_DIR
                )
                
                data['supervisor_signature'] = {
                    'saved': None,
                    'path': None,
                    'url': cloud_url,
                    'is_cloud': is_cloud
                }
                data['supervisor_comments'] = supervisor_comments
            except Exception as e:
                logger.error(f"Failed to upload supervisor signature: {e}")
                return error_response('Storage error for supervisor signature', status_code=500, error_code='STORAGE_ERROR')
        
        # Save base URL for report generation
        data['base_url'] = request.host_url.rstrip('/')
        data['created_at'] = utc_now_naive().isoformat()
        
        # Get user_id from JWT token if available
        user_id = None
        try:
            from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id:
                    logger.info(f"✅ Submission will be associated with user_id: {user_id}")
            except Exception:
                pass  # No token or invalid token - submission will be anonymous
        except Exception:
            pass  # JWT not available
        
        # Create submission in database
        submission = create_submission_db(
            module_type='cleaning',
            form_data=data,
            site_name=data.get('project_name'),
            visit_date=data.get('date_of_visit'),
            user_id=user_id
        )
        submission_id = submission.submission_id

        # Trigger real-time inspection submission email.
        try:
            submitter_user = db.session.get(User, int(user_id)) if user_id else None
            send_inspection_submitted(submission, submitter_user)
        except Exception as notify_err:
            logger.warning(f"Submission email notification failed for {submission_id}: {notify_err}")
        
        # Add IDs to data for background task
        data['submission_id'] = submission_id
        
        logger.info(f"Submission saved to database: {submission_id}")
        
        # Create job in database
        job = create_job_db(submission)
        job_id = job.job_id
        data['job_id'] = job_id
        
        # Submit background job with submission_id
        executor = current_app.config.get('EXECUTOR')
        if executor:
            executor.submit(
                process_job, 
                submission_id, 
                job_id, 
                current_app.config,
                current_app._get_current_object()
            )
            logger.info(f"Job {job_id} submitted to executor")
        else:
            logger.error("ThreadPoolExecutor not found in app config")
            return error_response('Background task executor not available', status_code=500, error_code='SERVICE_UNAVAILABLE')
        
        return jsonify({
            'status': 'queued',
            'job_id': job_id,
            'submission_id': submission_id
        }), 202
        
    except Exception as e:
        logger.error(f"Submission error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@cleaning_bp.route('/status/<job_id>', methods=['GET'])
def job_status(job_id):
    """Check the status of a background job."""
    try:
        job_data = get_job_status_db(job_id)
        
        if not job_data:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify(job_data)
        
    except Exception as e:
        logger.error(f"Job status error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def process_job(sub_id, job_id, config, app):
    """Background worker: Generate BOTH Excel AND PDF reports"""
    logger.debug(f"process_job called with sub_id={sub_id}, job_id={job_id}")
    from common.module_base import process_report_job
    from .cleaning_generators import create_excel_report, create_pdf_report
    
    process_report_job(
        sub_id=sub_id,
        job_id=job_id,
        app=app,
        module_name='cleaning',
        create_excel_report=create_excel_report,
        create_pdf_report=create_pdf_report
    )


# ---------- Progressive Upload Endpoints ----------

@cleaning_bp.route("/upload-photo", methods=["POST"])
def upload_photo():
    """Upload a single photo immediately to cloud storage."""
    try:
        UPLOADS_DIR = current_app.config['UPLOADS_DIR']
        
        if 'photo' not in request.files:
            return jsonify({"success": False, "error": "No photo file provided"}), 400
        
        photo_file = request.files['photo']
        if photo_file.filename == '':
            return jsonify({"success": False, "error": "Empty filename"}), 400
        
        result = save_uploaded_file_cloud(photo_file, UPLOADS_DIR, folder="cleaning_photos")
        
        if not result.get("url"):
            return jsonify({"success": False, "error": "Cloud upload failed"}), 500
        
        logger.info(f"✅ Cleaning photo uploaded to cloud: {result['url']}")
        
        return jsonify({
            "success": True,
            "url": result["url"],
            "filename": result.get("filename"),
            "is_cloud": result.get("is_cloud", True)
        })
        
    except Exception as e:
        logger.error(f"❌ Cleaning photo upload failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@cleaning_bp.route("/submit-with-urls", methods=["POST"])
@jwt_required()
def submit_with_urls():
    """Submit form data where photos are already uploaded to cloud."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # Validate required fields
        required_fields = ['project_name', 'date_of_visit']
        missing = [f for f in required_fields if not data.get(f) or not str(data.get(f)).strip()]
        if missing:
            logger.warning(f"Missing required fields: {missing}")
            return jsonify({'error': f"Missing required fields: {', '.join(missing)}"}), 400
        
        # Validate date - allow past dates and today, reject future dates (>1 day)
        date_str = data.get('date_of_visit', '')
        if date_str:
            try:
                from datetime import timedelta
                visit_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                # Use UTC date and add 1 day buffer to account for timezone differences
                today_utc = utc_now_naive().date()
                max_allowed_date = today_utc + timedelta(days=1)
                logger.info(f"Date validation (submit-with-urls): parsed_date={visit_date}, today_utc={today_utc}, max_allowed={max_allowed_date}")
                if visit_date > max_allowed_date:
                    logger.warning(f"Rejected future date: {visit_date} > {max_allowed_date}")
                    return jsonify({'error': f'Visit date ({visit_date}) cannot be more than 1 day in the future'}), 400
            except ValueError as e:
                logger.error(f"Invalid date format: {date_str}, error: {e}")
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        GENERATED_DIR = current_app.config['GENERATED_DIR']
        UPLOADS_DIR = current_app.config['UPLOADS_DIR']
        JOBS_DIR = current_app.config['JOBS_DIR']
        
        os.makedirs(GENERATED_DIR, exist_ok=True)
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        os.makedirs(JOBS_DIR, exist_ok=True)
        
        submission_id = random_id('sub')
        job_id = random_id('job')
        
        # Process photos - convert URLs to expected format
        photo_urls = data.get('photo_urls', [])
        saved_photos = []
        
        logger.info(f"📸 Received {len(photo_urls)} photo URLs")
        
        for idx, url in enumerate(photo_urls):
            if url:
                logger.info(f"  Photo {idx + 1}: {url[:80]}...")
                saved_photos.append({
                    'saved': None,
                    'path': None,
                    'url': url,
                    'index': idx,
                    'is_cloud': True
                })
        
        data['photos'] = saved_photos
        logger.info(f"📸 Total photos processed: {len(saved_photos)}")
        
        # Save signatures (base64 data) to cloud with local fallback
        tech_signature = data.get('tech_signature', '')
        supervisor_signature = data.get('supervisor_signature', '')
        supervisor_comments = data.get('supervisor_comments', '')
        
        if tech_signature and tech_signature.startswith('data:image'):
            try:
                cloud_url, is_cloud = upload_base64_to_cloud(tech_signature, folder="signatures", prefix="tech_sig", uploads_dir=UPLOADS_DIR)
                data['tech_signature'] = {
                    'saved': None,
                    'path': None,
                    'url': cloud_url,
                    'is_cloud': is_cloud
                }
            except Exception as e:
                logger.error(f"Failed to upload tech signature: {e}")
        
        if supervisor_signature and supervisor_signature.startswith('data:image'):
            try:
                cloud_url, is_cloud = upload_base64_to_cloud(supervisor_signature, folder="signatures", prefix="supervisor_sig", uploads_dir=UPLOADS_DIR)
                data['supervisor_signature'] = {
                    'saved': None,
                    'path': None,
                    'url': cloud_url,
                    'is_cloud': is_cloud
                }
                data['supervisor_comments'] = supervisor_comments
                logger.info(f"✅ Saved supervisor signature and comments for submission")
            except Exception as e:
                logger.error(f"Failed to upload supervisor signature: {e}")
        
        # Add base_url and timestamp directly to data
        data['base_url'] = request.host_url.rstrip('/')
        data['created_at'] = utc_now_naive().isoformat()
        
        # Get user_id from JWT token
        user_id = None
        try:
            user_id = get_jwt_identity()
            if user_id:
                logger.info(f"✅ Submission will be associated with user_id: {user_id}")
        except Exception:
            pass  # No token or invalid token - submission will be anonymous
        
        # Save submission to database - pass data directly as form_data (matches Civil/HVAC structure)
        submission_db = create_submission_db(
            module_type='cleaning',
            form_data=data,
            site_name=data.get('project_name', 'Cleaning Assessment'),
            visit_date=data.get('date_of_visit', utc_now_naive().strftime('%Y-%m-%d')),
            user_id=user_id
        )
        submission_id = submission_db.submission_id

        # Trigger real-time inspection submission email.
        try:
            submitter_user = db.session.get(User, int(user_id)) if user_id else None
            send_inspection_submitted(submission_db, submitter_user)
        except Exception as notify_err:
            logger.warning(f"Submission email notification failed for {submission_id}: {notify_err}")
        
        logger.info(f"✅ Cleaning submission {submission_id} saved to database with {len(saved_photos)} photos")
        
        # Create job in database
        job = create_job_db(submission_db)
        job_id = job.job_id
        
        # Submit background task
        executor = current_app.config.get('EXECUTOR')
        if executor:
            future = executor.submit(
                process_job,
                submission_id,
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
        
        logger.info(f"🚀 Cleaning job {job_id} queued for submission {submission_id}")
        
        return jsonify({
            'status': 'queued',
            'job_id': job_id,
            'submission_id': submission_id,
            'job_status_url': url_for('cleaning.job_status', job_id=job_id, _external=False)
        })
        
    except Exception as e:
        logger.error(f"❌ Cleaning submit with URLs failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500