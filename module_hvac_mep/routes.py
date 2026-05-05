# module_hvac_mep/routes.py
import os
import json
import time
import base64
import re
import traceback
import logging
from datetime import datetime
from flask import Blueprint, current_app, render_template, request, jsonify, url_for, send_from_directory, send_file, Response
import requests
from io import BytesIO

# CRITICAL FIX: Define logger FIRST before using it
logger = logging.getLogger(__name__)

# common utilities (ensure common/utils.py exists)
from common.utils import (
    random_id,
    save_uploaded_file,
    save_uploaded_file_cloud,
    upload_base64_to_cloud,
    is_path_safe_for_directory,
)
from common.error_responses import error_response, success_response
from common.datetime_utils import utc_now_naive
from common.db_utils import (
    create_submission_db,
    create_job_db,
    update_job_progress_db,
    complete_job_db,
    fail_job_db,
    get_job_status_db,
    get_submission_db
)
from app.models import db, User
from app.middleware import token_required, module_access_required
from app.services.cloudinary_service import upload_local_file
from flask_jwt_extended import get_jwt_identity, jwt_required
from common.workflow_notifications import send_inspection_submitted

# Rate limiting helper (import from auth routes)
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

# Import BOTH report generators
try:
    from .hvac_generators import create_excel_report, create_pdf_report
    logger.info("✅ Successfully imported hvac_generators")
except Exception as e:
    logger.error(f"❌ Failed to import generators: {e}")
    def create_excel_report(data, output_dir):
        raise NotImplementedError("Excel generator not available")
    def create_pdf_report(data, output_dir):
        raise NotImplementedError("PDF generator not available")

# import the external generator worker you added
try:
    from . import generator as hvac_generator
except Exception:
    hvac_generator = None  # we'll still allow fallback behavior if needed

try:
    from .generator import process_submission
except ImportError:
    # Fallback if generator.py doesn't exist
    def process_submission(submission_data, job_id, config):
        from common.db_utils import fail_job_db
        fail_job_db(job_id, "Generator not implemented")

BLUEPRINT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BLUEPRINT_DIR)

# sensible defaults; prefer app config at runtime via get_paths()
DEFAULT_GENERATED_DIR = os.path.join(BASE_DIR, "generated")
DEFAULT_UPLOADS_DIR = os.path.join(DEFAULT_GENERATED_DIR, "uploads")
DEFAULT_JOBS_DIR = os.path.join(DEFAULT_GENERATED_DIR, "jobs")

# fallback executor for background tasks (used if app doesn't provide one)
from concurrent.futures import ThreadPoolExecutor

_FALLBACK_EXECUTOR = ThreadPoolExecutor(max_workers=2)

hvac_mep_bp = Blueprint(
    "hvac_mep_bp", __name__, template_folder="templates", static_folder="static"
)


def get_paths():
    """
    Return (GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR) using current_app config or defaults.
    Safe to call during request handling.
    """
    gen = (
        current_app.config.get("GENERATED_DIR", DEFAULT_GENERATED_DIR)
        if current_app
        else DEFAULT_GENERATED_DIR
    )
    uploads = (
        current_app.config.get("UPLOADS_DIR", DEFAULT_UPLOADS_DIR)
        if current_app
        else DEFAULT_UPLOADS_DIR
    )
    jobs = (
        current_app.config.get("JOBS_DIR", DEFAULT_JOBS_DIR)
        if current_app
        else DEFAULT_JOBS_DIR
    )
    executor = (
        current_app.config.get("EXECUTOR")
        if (current_app and current_app.config.get("EXECUTOR"))
        else _FALLBACK_EXECUTOR
    )
    return gen, uploads, jobs, executor


@hvac_mep_bp.route("/form", methods=["GET"])
@jwt_required()
def index():
    """HVAC&MEP form - requires authentication and module access. Supports editing existing submissions."""
    from flask import redirect, url_for, request
    from flask_jwt_extended import get_jwt_identity
    from app.models import Submission
    
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return redirect(url_for('login_page'))
        
        user = db.session.get(User, int(user_id)) if user_id is not None else None
        
        if not user or not user.is_active:
            return render_template('access_denied.html', 
                                 module='HVAC & MEP',
                                 message='Your account is inactive. Please contact an administrator.'), 403
        
        # Allow admins, supervisors, and managers to edit submissions even if they don't have module access
        edit_submission_id = request.args.get('edit')
        submission_data = None
        is_edit_mode = False
        
        if edit_submission_id:
            # Check if user can edit (admin, or supervisor/manager of this submission)
            submission = Submission.query.filter_by(submission_id=edit_submission_id).first()
            if not submission:
                return render_template('access_denied.html',
                                     module='HVAC & MEP',
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
                                     module='HVAC & MEP',
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
            
            # Log Operations Manager data for debugging
            logger.info(f"🔍 Operations Manager data check for submission {edit_submission_id}:")
            logger.info(f"  - form_data.operations_manager_comments: {bool(form_data.get('operations_manager_comments'))}")
            logger.info(f"  - form_data.operations_manager_signature: {bool(form_data.get('operations_manager_signature'))}")
            logger.info(f"  - form_data.opMan_signature: {bool(form_data.get('opMan_signature'))}")
            logger.info(f"  - Model field operations_manager_comments: {bool(hasattr(submission, 'operations_manager_comments') and submission.operations_manager_comments)}")
            
            # Operations Manager signature is stored in form_data, but ensure it's there
            # Check if it exists in form_data, if not, try to extract from nested structures
            if not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
                # Try to find signature in nested structures
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data:
                        if nested_data.get('operations_manager_signature'):
                            form_data['operations_manager_signature'] = nested_data.get('operations_manager_signature')
                            logger.info(f"✅ Found Operations Manager signature in nested form_data.data structure")
                        elif nested_data.get('opMan_signature'):
                            form_data['operations_manager_signature'] = nested_data.get('opMan_signature')
                            logger.info(f"✅ Found Operations Manager signature (opMan_signature) in nested form_data.data structure")
                
                # If still not found, log warning
                if not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
                    logger.warning(f"⚠️ Operations Manager signature not found in form_data for submission {edit_submission_id}")
                    logger.warning(f"  - Available form_data keys: {list(form_data.keys())[:30]}")
                    # Check if OM has approved (might have signature but not in form_data yet)
                    if hasattr(submission, 'operations_manager_approved_at') and submission.operations_manager_approved_at:
                        logger.warning(f"  - ⚠️ OM has approved but signature not in form_data - this may indicate a data saving issue")
            
            # Merge Business Development comments from model field into form_data if not already present
            # This ensures Procurement and other reviewers can see BD comments even if not in form_data
            # CRITICAL: Only use actual BD comments, never fall back to supervisor comments
            existing_bd_comments = form_data.get('business_dev_comments')
            supervisor_comments = form_data.get('supervisor_comments')
            
            # Check if BD comments are incorrectly set to supervisor comments
            if existing_bd_comments and supervisor_comments and existing_bd_comments == supervisor_comments:
                logger.warning(f"⚠️ WARNING: BD comments appear to be incorrectly set to supervisor comments!")
                logger.warning(f"  - BD comments value: {existing_bd_comments[:50] if existing_bd_comments else 'None'}...")
                logger.warning(f"  - Supervisor comments value: {supervisor_comments[:50] if supervisor_comments else 'None'}...")
                # Clear the incorrect BD comments - we'll set it properly below
                form_data['business_dev_comments'] = None
                existing_bd_comments = None
            
            if hasattr(submission, 'business_dev_comments') and submission.business_dev_comments:
                # Only set if not already present OR if it was incorrectly set to supervisor comments
                if not existing_bd_comments or existing_bd_comments == supervisor_comments:
                    form_data['business_dev_comments'] = submission.business_dev_comments
                    logger.info(f"✅ Added Business Development comments from model field to form_data for display")
                    logger.info(f"  - BD comments value: {submission.business_dev_comments[:50] if submission.business_dev_comments else 'None'}...")
            elif existing_bd_comments and existing_bd_comments != supervisor_comments:
                # Keep existing BD comments if they're valid (not supervisor comments)
                logger.info(f"✅ Using existing Business Development comments from form_data")
                logger.info(f"  - BD comments value: {existing_bd_comments[:50] if existing_bd_comments else 'None'}...")
            else:
                # No BD comments found - ensure it's not set to supervisor comments
                if form_data.get('business_dev_comments') == supervisor_comments:
                    form_data['business_dev_comments'] = None
                    logger.warning(f"⚠️ Cleared BD comments that were incorrectly set to supervisor comments")
            
            # Business Development signature is stored in form_data, but ensure it's there
            # Check if it exists in form_data, if not, try to extract from nested structures
            if not form_data.get('business_dev_signature'):
                # Try to find signature in nested structures
                if isinstance(submission.form_data, dict):
                    nested_data = submission.form_data.get('data') if isinstance(submission.form_data.get('data'), dict) else {}
                    if nested_data:
                        if nested_data.get('business_dev_signature'):
                            form_data['business_dev_signature'] = nested_data.get('business_dev_signature')
                            logger.info(f"✅ Found Business Development signature in nested form_data.data structure")
                
                # If still not found, log warning
                if not form_data.get('business_dev_signature'):
                    logger.warning(f"⚠️ Business Development signature not found in form_data for submission {edit_submission_id}")
                    # Check if BD has approved (might have signature but not in form_data yet)
                    if hasattr(submission, 'business_dev_approved_at') and submission.business_dev_approved_at:
                        logger.warning(f"  - ⚠️ BD has approved but signature not in form_data - this may indicate a data saving issue")
            
            # Log Business Development data for debugging
            logger.info(f"🔍 Business Development data check for submission {edit_submission_id}:")
            logger.info(f"  - form_data.business_dev_comments: {bool(form_data.get('business_dev_comments'))}")
            if form_data.get('business_dev_comments'):
                bd_comments_val = form_data.get('business_dev_comments')
                logger.info(f"  - BD comments value (first 50 chars): {bd_comments_val[:50] if isinstance(bd_comments_val, str) else str(bd_comments_val)[:50]}...")
            logger.info(f"  - form_data.business_dev_signature: {bool(form_data.get('business_dev_signature'))}")
            logger.info(f"  - Model field business_dev_comments: {bool(hasattr(submission, 'business_dev_comments') and submission.business_dev_comments)}")
            if hasattr(submission, 'business_dev_comments') and submission.business_dev_comments:
                logger.info(f"  - Model BD comments value (first 50 chars): {submission.business_dev_comments[:50]}...")
            logger.info(f"  - BD approved at: {submission.business_dev_approved_at if hasattr(submission, 'business_dev_approved_at') else 'N/A'}")
            logger.info(f"  - Supervisor comments (for comparison): {bool(supervisor_comments)}")
            if supervisor_comments:
                logger.info(f"  - Supervisor comments value (first 50 chars): {supervisor_comments[:50]}...")
            
            # Use values from form_data if available (what technician submitted), otherwise fall back to DB columns
            site_name = form_data.get('site_name') or submission.site_name or ''
            visit_date = form_data.get('visit_date') or (submission.visit_date.isoformat() if submission.visit_date else '')
            
            submission_data = {
                'submission_id': submission.submission_id,
                'site_name': site_name,
                'visit_date': visit_date,
                'form_data': form_data,
                'is_edit_mode': True,
                'workflow_status': submission.workflow_status if hasattr(submission, 'workflow_status') else None,
                'supervisor_id': submission.supervisor_id if hasattr(submission, 'supervisor_id') else None,
                'can_edit': can_edit,  # Pass can_edit to JavaScript so it can show editable vs read-only UI
                'operations_manager_approved_at': submission.operations_manager_approved_at.isoformat() if hasattr(submission, 'operations_manager_approved_at') and submission.operations_manager_approved_at else None,
                'business_dev_approved_at': submission.business_dev_approved_at.isoformat() if hasattr(submission, 'business_dev_approved_at') and submission.business_dev_approved_at else None,
                'procurement_approved_at': submission.procurement_approved_at.isoformat() if hasattr(submission, 'procurement_approved_at') and submission.procurement_approved_at else None,
                'general_manager_approved_at': submission.general_manager_approved_at.isoformat() if hasattr(submission, 'general_manager_approved_at') and submission.general_manager_approved_at else None,
            }
            is_edit_mode = True
            
            logger.info(f"Submission data prepared - site_name: {site_name}, visit_date: {visit_date}")
            logger.info(f"Items in form_data: {len(form_data.get('items', [])) if isinstance(form_data.get('items'), list) else 'not a list'}")
        else:
            # Normal form access - check module access
            if not user.has_module_access('hvac_mep'):
                return render_template('access_denied.html',
                                     module='HVAC & MEP',
                                     message='You do not have access to this module. Please contact an administrator to grant access.'), 403
        
        # Pass user designation and role to template for signature field visibility
        user_designation = user.designation if hasattr(user, 'designation') else None
        
        # Consider admins, supervisors, managers, and all reviewer roles as "supervisor edit" for review purposes
        # This allows reviewers to see the same editable view and add their comments/signatures
        review_param = request.args.get('review') == 'true'
        reviewer_designations = ['supervisor', 'manager', 'operations_manager', 'business_development', 'procurement', 'general_manager']
        is_supervisor_edit = is_edit_mode and (user_designation in reviewer_designations or user.role == 'admin' or review_param)
        
        # Log for debugging
        if is_edit_mode:
            logger.info(f"Loading submission {edit_submission_id} for user {user_id} (role: {user.role}, designation: {user_designation}, is_supervisor_edit: {is_supervisor_edit})")
            if submission_data and submission_data.get('form_data'):
                logger.info(f"Form data keys: {list(submission_data['form_data'].keys())}")
                logger.info(f"Site name from form_data: {submission_data['form_data'].get('site_name')}")
                logger.info(f"Visit date from form_data: {submission_data['form_data'].get('visit_date')}")
                logger.info(f"Site name in submission_data: {submission_data.get('site_name')}")
                logger.info(f"Visit date in submission_data: {submission_data.get('visit_date')}")
                if 'items' in submission_data['form_data']:
                    items_list = submission_data['form_data']['items']
                    if isinstance(items_list, list):
                        logger.info(f"Items count: {len(items_list)}")
                        if len(items_list) > 0:
                            logger.info(f"First item keys: {list(items_list[0].keys()) if isinstance(items_list[0], dict) else 'not a dict'}")
                    else:
                        logger.warning(f"Items is not a list: {type(items_list)}")
                if 'tech_signature' in submission_data['form_data']:
                    tech_sig = submission_data['form_data']['tech_signature']
                    if isinstance(tech_sig, dict):
                        logger.info(f"Tech signature URL: {tech_sig.get('url', 'no url')}")
                    else:
                        logger.info(f"Tech signature type: {type(tech_sig)}")
        
        # Pass can_edit to template so it knows if user can modify the form
        can_edit_form = False
        if edit_submission_id and 'can_edit' in locals():
            can_edit_form = can_edit
        elif not edit_submission_id:
            # New form - supervisor can always create
            can_edit_form = True
        
        return render_template("hvac_mep_form.html", 
                             submission_data=submission_data, 
                             is_edit_mode=is_edit_mode,
                             user_designation=user_designation,
                             is_supervisor_edit=is_supervisor_edit,
                             can_edit=can_edit_form,
                             current_user_id=user_id,
                             user=user)
    except Exception as e:
        logger.error(f"Error checking module access: {str(e)}")
        logger.error(traceback.format_exc())
        # If JWT check fails, redirect to login
        return redirect(url_for('login_page'))


@hvac_mep_bp.route("/dropdowns", methods=["GET"])
def dropdowns():
    # prefer module-level dropdown_data.json (BLUEPRINT_DIR/dropdown_data.json)
    local = os.path.join(BLUEPRINT_DIR, "dropdown_data.json")
    if os.path.exists(local):
        with open(local, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    # fallback to empty object
    return jsonify({})


@hvac_mep_bp.route("/save-draft", methods=["POST"])
def save_draft():
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
    payload = request.get_json(force=True)
    draft_id = random_id("draft")
    drafts_dir = os.path.join(GENERATED_DIR, "drafts")
    os.makedirs(drafts_dir, exist_ok=True)
    with open(os.path.join(drafts_dir, f"{draft_id}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return jsonify({"status": "ok", "draft_id": draft_id})


# ---------- Helpers for signatures ----------
_DATAURL_RE = re.compile(r"data:(?P<mime>[^;]+);base64,(?P<data>.+)")


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


# ---------- Submit route (handles multi-item + per-item photos + signatures) ----------
@hvac_mep_bp.route("/submit", methods=["POST"])
@rate_limit_if_available('10 per minute')  # Limit form submissions
def submit():
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()

    # Ensure directories exist
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(JOBS_DIR, exist_ok=True)

    try:
        # Check if this is an edit/update request
        edit_submission_id = request.args.get('edit') or request.form.get('edit_submission_id')
        
        # If the client used the multi-item UI, it will post items_count and item_* fields.
        # We'll handle both cases: multi-item (items_count present) and legacy single-file uploads.

        # Basic form fields
        site_name = request.form.get("site_name", "")
        visit_date = request.form.get("visit_date", "")
        
        # Validate required fields
        if not site_name or not site_name.strip():
            return error_response("Site name is required", status_code=400, error_code='VALIDATION_ERROR')
        
        # Validate date - allow past dates and today, reject future dates (>1 day)
        if visit_date:
            try:
                from datetime import timedelta
                parsed_date = datetime.strptime(visit_date, '%Y-%m-%d').date()
                # Use UTC date and add 1 day buffer to account for timezone differences
                today_utc = utc_now_naive().date()
                max_allowed_date = today_utc + timedelta(days=1)
                logger.info(f"Date validation (HVAC): parsed_date={parsed_date}, today_utc={today_utc}, max_allowed={max_allowed_date}")
                if parsed_date > max_allowed_date:
                    logger.warning(f"Rejected future date: {parsed_date} > {max_allowed_date}")
                    return error_response(f"Visit date ({parsed_date}) cannot be more than 1 day in the future", status_code=400, error_code='VALIDATION_ERROR')
            except ValueError as e:
                logger.error(f"Invalid date format: {visit_date}, error: {e}")
                return error_response("Invalid date format. Use YYYY-MM-DD", status_code=400, error_code='VALIDATION_ERROR')

        # Signatures (data URLs). We'll persist them to files.
        tech_sig_dataurl = request.form.get("tech_signature") or request.form.get("tech_signature_data") or ""
        opman_sig_dataurl = request.form.get("opMan_signature") or request.form.get("opManSignatureData") or ""

        tech_sig_file = None
        opman_sig_file = None
        
        # If editing, preserve existing signatures if no new signature provided
        if edit_submission_id:
            from common.db_utils import get_submission_db
            existing_submission = get_submission_db(edit_submission_id)
            if existing_submission and existing_submission.get('form_data'):
                existing_form_data = existing_submission['form_data']
                
                # Preserve tech signature if not provided
                if not tech_sig_dataurl and existing_form_data.get('tech_signature'):
                    tech_sig_file = existing_form_data['tech_signature']
                    logger.info(f"✅ Preserving existing tech signature from submission")
                
                # Preserve opman signature if not provided
                if not opman_sig_dataurl and existing_form_data.get('opman_signature'):
                    opman_sig_file = existing_form_data['opman_signature']
                    logger.info(f"✅ Preserving existing opman signature from submission")
        
        # Upload new signatures if provided
        if tech_sig_dataurl and not tech_sig_file:
            # Upload to cloud and get URL
            fname, fpath, url = save_signature_dataurl(tech_sig_dataurl, UPLOADS_DIR, prefix="tech_sig")
            if url:  # Check for URL, not fname (cloud upload returns None for fname)
                tech_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
        if opman_sig_dataurl and not opman_sig_file:
            fname, fpath, url = save_signature_dataurl(opman_sig_dataurl, UPLOADS_DIR, prefix="opman_sig")
            if url:  # Check for URL, not fname (cloud upload returns None for fname)
                opman_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}

        # Determine items_count
        try:
            items_count = int(request.form.get("items_count", "0") or 0)
        except Exception:
            items_count = 0

        items = []

        if items_count and items_count > 0:
            # Parse each item and its files
            for i in range(items_count):
                asset = request.form.get(f"item_{i}_asset", "")
                system = request.form.get(f"item_{i}_system", "")
                description = request.form.get(f"item_{i}_description", "")
                quantity = request.form.get(f"item_{i}_quantity", "1")
                brand = request.form.get(f"item_{i}_brand", "")
                specification = request.form.get(f"item_{i}_specification", "")
                comments = request.form.get(f"item_{i}_comments", "")

                photos_saved = []
                # Files for this item are expected with field name item_{i}_photo (can appear multiple times)
                file_field = f"item_{i}_photo"
                uploaded_files = request.files.getlist(file_field) or []
                for f in uploaded_files:
                    if f and getattr(f, "filename", None):
                        try:
                            # Upload to cloud (required)
                            result = save_uploaded_file_cloud(f, UPLOADS_DIR, folder="hvac_photos")
                            photos_saved.append({
                                "field": file_field,
                                "saved": None,
                                "path": None,
                                "url": result["url"],
                                "is_cloud": True
                            })
                        except Exception as e:
                            logger.error(f"Failed to upload photo: {e}")
                            return error_response(f"Cloud storage error: {str(e)}", 500, "STORAGE_ERROR")

                items.append(
                    {
                        "asset": asset,
                        "system": system,
                        "description": description,
                        "quantity": quantity,
                        "brand": brand,
                        "specification": specification,
                        "comments": comments,
                        "photos": photos_saved,
                    }
                )
        else:
            # Legacy/fallback: collect any file fields in request.files and attach them as top-level files
            # Also attempt to parse a single item from form fields if present
            # Collect files
            saved_files = []
            for key in request.files:
                # Ignore any item_x_photo style keys if they existed but items_count was 0
                f = request.files.get(key)
                if f and getattr(f, "filename", None):
                    try:
                        result = save_uploaded_file_cloud(f, UPLOADS_DIR, folder="hvac_photos")
                        saved_files.append({
                            "field": key,
                            "saved": None,
                            "path": None,
                            "url": result["url"],
                            "is_cloud": True
                        })
                    except Exception as e:
                        logger.error(f"Failed to upload file: {e}")
                        return error_response(f"Cloud storage error: {str(e)}", 500, "STORAGE_ERROR")

            # If there are explicit item fields (single item), capture them
            asset = request.form.get("asset") or request.form.get("item_0_asset") or ""
            system = request.form.get("system") or request.form.get("item_0_system") or ""
            description = request.form.get("description") or request.form.get("item_0_description") or ""

            if asset or system or description or saved_files:
                items.append(
                    {
                        "asset": asset,
                        "system": system,
                        "description": description,
                        "photos": saved_files,
                    }
                )

        # Create submission in database
        submission_record = {
            "site_name": site_name,
            "visit_date": visit_date,
            "tech_signature": tech_sig_file,
            "opman_signature": opman_sig_file,
            "items": items,
            "base_url": request.host_url.rstrip('/'),
            "created_at": utc_now_naive().isoformat(),
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
                else:
                    logger.warning("⚠️ JWT token verified but no user_id found")
            except Exception as jwt_error:
                logger.debug(f"JWT token not available or invalid: {jwt_error}")
                # No token or invalid token - submission will be anonymous
        except Exception as e:
            logger.debug(f"JWT verification error: {e}")
            pass  # JWT not available
        
        submission = create_submission_db(
            module_type='hvac_mep',
            form_data=submission_record,
            site_name=site_name,
            visit_date=visit_date,
            user_id=user_id
        )
        sub_id = submission.submission_id

        # Trigger inspection email notification for real-time supervisor submission.
        try:
            submitter_user = db.session.get(User, int(user_id)) if user_id else None
            send_inspection_submitted(submission, submitter_user)
        except Exception as notify_err:
            logger.warning(f"Submission email notification failed for {sub_id}: {notify_err}")

        # Create job in database
        job = create_job_db(submission)
        job_id = job.job_id

        logger.info(f"Starting background task for job {job_id}")
        logger.debug(f"Executor object: {EXECUTOR}")
        
        # Submit to executor with submission_id instead of record
        if EXECUTOR:
            # Add callback to catch any errors
            future = EXECUTOR.submit(
                process_job,
                sub_id,
                job_id,
                current_app.config,
                current_app._get_current_object()
            )
            
            # Add error callback
            def log_exception(fut):
                try:
                    fut.result()  # This will raise if the worker had an exception
                except Exception as e:
                    logger.error(f"❌ FATAL: Background job {job_id} crashed: {e}")
                    logger.error(traceback.format_exc())
            
            future.add_done_callback(log_exception)
            logger.info(f"✅ Background job {job_id} submitted to executor")
        else:
            logger.error("ThreadPoolExecutor not found in app config")
            return jsonify({'error': 'Background processing not available'}), 500

        return jsonify({"status": "queued", "job_id": job_id, "submission_id": sub_id, "items": len(items)})
    
    except Exception as e:
        logger.error(f"Submission failed: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response('Submission failed', status_code=500, error_code='INTERNAL_ERROR')


@hvac_mep_bp.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    try:
        job_data = get_job_status_db(job_id)
        if not job_data:
            return error_response("Job not found", status_code=404, error_code='NOT_FOUND')
        return jsonify(job_data)
    except Exception as e:
        logger.error(f"Status check failed for {job_id}: {e}")
        logger.error(traceback.format_exc())
        return error_response("Status check failed", status_code=500, error_code='INTERNAL_ERROR')


@hvac_mep_bp.route("/generated/<path:filename>", methods=["GET"])
def download_generated(filename):
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
    # allow nested paths like uploads/<name>
    return send_from_directory(GENERATED_DIR, filename, as_attachment=True)


@hvac_mep_bp.route("/download/<job_id>/<file_type>", methods=["GET"])
def download_file(job_id, file_type):
    """
    Download proxy route that fetches files from Cloudinary or local storage
    and serves them with proper download headers for auto-download.
    
    Args:
        job_id: Job ID to get file URLs from
        file_type: 'excel' or 'pdf'
    """
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
    
    try:
        # Get job data from database
        job_data = get_job_status_db(job_id)
        if not job_data:
            logger.error(f"Job not found: {job_id}")
            return error_response("Job not found", 404, "JOB_NOT_FOUND")
        
        # Log the job_data structure (debug level only)
        logger.debug(f"Job data for {job_id}: {type(job_data)}")
        logger.debug(f"Job data keys: {list(job_data.keys()) if isinstance(job_data, dict) else 'Not a dict'}")
        
        # Extract results - try multiple possible keys
        results = {}
        if isinstance(job_data, dict):
            results = job_data.get('results', {}) or job_data.get('result_data', {}) or job_data.get('results_data', {})
            # If results is a string (JSON), parse it
            if isinstance(results, str):
                try:
                    import json
                    results = json.loads(results)
                except:
                    logger.warning(f"Failed to parse results as JSON")
                    results = {}
        
        if not results:
            logger.error(f"Job results not found for {job_id}")
            return error_response("Job results not found", status_code=404, error_code='NOT_FOUND')
        
        logger.debug(f"Results for {job_id}: {list(results.keys()) if isinstance(results, dict) else type(results)}")
        
        # Get file URL and filename based on file_type
        if file_type == 'excel':
            file_url = results.get('excel') or results.get('excel_url')
            filename = results.get('excel_filename', 'hvac_report.xlsx')
        elif file_type == 'pdf':
            file_url = results.get('pdf') or results.get('pdf_url')
            filename = results.get('pdf_filename', 'hvac_report.pdf')
        else:
            return error_response("Invalid file type. Use 'excel' or 'pdf'", status_code=400, error_code='VALIDATION_ERROR')
        
        if not file_url:
            return error_response(f"{file_type.upper()} file URL not found", status_code=404, error_code='NOT_FOUND')
        
        # Check if it's a Cloudinary URL or local URL
        # If it's a localhost URL, treat it as a local file path instead
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
            
            return send_file(local_path, as_attachment=True, download_name=filename)
        elif file_url.startswith('http://') or file_url.startswith('https://'):
            # Cloudinary URL - fetch and serve
            try:
                logger.debug(f"Fetching {file_type.upper()} file from Cloudinary: {file_url}")
                # Remove ?attachment=true if present
                clean_url = file_url.split('?')[0]
                logger.debug(f"Clean URL (removed query params): {clean_url}")
                
                # Use the original URL directly - Cloudinary URLs work fine as-is
                response = requests.get(clean_url, timeout=60, stream=True)
                response.raise_for_status()
                logger.debug(f"Successfully fetched {file_type.upper()} file, status: {response.status_code}, content-length: {response.headers.get('Content-Length', 'unknown')}")
                
                # Read file content into BytesIO
                file_content = response.content
                file_data = BytesIO(file_content)
                file_data.seek(0)  # Reset to beginning
                
                # Determine content type
                if file_type == 'excel':
                    mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                else:  # pdf
                    mimetype = 'application/pdf'
                
                # Verify file content is not empty
                if len(file_content) == 0:
                    logger.error(f"Empty file content received from Cloudinary: {file_url}")
                    return error_response("File content is empty", 500, "EMPTY_FILE")
                
                logger.debug(f"Serving file: {filename}, size: {len(file_content)} bytes, type: {mimetype}")
                
                # Serve with download headers
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
            # Local URL - extract filename and serve from local storage
            # Remove leading slash and 'generated/' if present
            local_filename = file_url.lstrip('/').replace('generated/', '')
            local_path = os.path.join(GENERATED_DIR, local_filename)
            
            if not is_path_safe_for_directory(GENERATED_DIR, local_path):
                logger.warning(f"Path traversal attempt blocked: {local_path}")
                return error_response("Invalid file path", status_code=403, error_code='FORBIDDEN')
            
            if not os.path.exists(local_path):
                return error_response("File not found locally", status_code=404, error_code='NOT_FOUND')
            
            return send_file(local_path, as_attachment=True, download_name=filename)
    
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response("Download failed", status_code=500, error_code='INTERNAL_ERROR')

def process_job(sub_id, job_id, config, app):
    """Background worker: Generate BOTH Excel AND PDF reports"""
    logger.debug(f"process_job called with sub_id={sub_id}, job_id={job_id}")
    from common.module_base import process_report_job
    from .hvac_generators import create_excel_report, create_pdf_report
    
    process_report_job(
        sub_id=sub_id,
        job_id=job_id,
        app=app,
        module_name='hvac',
        create_excel_report=create_excel_report,
        create_pdf_report=create_pdf_report
    )


# ---------- Progressive Upload Endpoints ----------

@hvac_mep_bp.route("/upload-photo", methods=["POST"])
@rate_limit_if_available('20 per minute')  # Allow multiple photos per submission
def upload_photo():
    """
    Upload a single photo immediately to cloud storage.
    Used by progressive upload to upload photos when adding each item.
    Returns: {"success": true, "url": "cloudinary_url"}
    """
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
    
    try:
        # Expect a single file with field name 'photo'
        if 'photo' not in request.files:
            logger.error("No photo file in request")
            return error_response("No photo file provided", status_code=400, error_code='VALIDATION_ERROR')
        
        photo_file = request.files['photo']
        if photo_file.filename == '':
            logger.error("Empty filename provided")
            return error_response("Empty filename", status_code=400, error_code='VALIDATION_ERROR')
        
        logger.info(f"Uploading photo: {photo_file.filename}")
        
        # Upload directly to cloud storage with proper error handling
        try:
            result = save_uploaded_file_cloud(photo_file, UPLOADS_DIR)
            
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
            
            # Try to save locally as fallback
            try:
                logger.info("Attempting local fallback save...")
                local_filename = save_uploaded_file(photo_file, UPLOADS_DIR)
                local_url = url_for('download_generated', filename=f"uploads/{local_filename}", _external=False)
                
                logger.info(f"✅ Saved locally as fallback: {local_url}")
                return jsonify({
                    "success": True,
                    "url": local_url,
                    "is_cloud": False,
                    "filename": local_filename,
                    "warning": "Saved locally (cloud upload failed)"
                })
            except Exception as local_error:
                logger.error(f"Local fallback also failed: {str(local_error)}")
                return error_response("Both cloud and local upload failed", status_code=500, error_code='STORAGE_ERROR')
        
    except Exception as e:
        logger.error(f"❌ Photo upload failed completely: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response("Photo upload failed", status_code=500, error_code='INTERNAL_ERROR')


@hvac_mep_bp.route("/submit-with-urls", methods=["POST"])
@rate_limit_if_available('10 per minute')  # Limit form submissions
def submit_with_urls():
    """
    Submit form data where photos are already uploaded to cloud.
    Expects JSON payload with:
    {
        "site_name": "...",
        "visit_date": "...",
        "tech_signature": "data:image/png;base64,...",
        "opMan_signature": "data:image/png;base64,...",
        "items": [
            {
                "asset": "...",
                "system": "...",
                "description": "...",
                "photo_urls": ["cloudinary_url1", "cloudinary_url2", ...]
            }
        ]
    }
    """
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
    
    # Ensure directories exist
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(JOBS_DIR, exist_ok=True)
    
    try:
        # Parse JSON payload
        payload = request.get_json(force=True)
        
        site_name = payload.get("site_name", "")
        visit_date = payload.get("visit_date", "")
        edit_submission_id = payload.get("edit_submission_id") or payload.get("submission_id")
        
        # Check if this is an update/edit request
        is_edit_mode = bool(edit_submission_id)
        
        # Process signatures
        tech_sig_dataurl = payload.get("tech_signature", "")
        opman_sig_dataurl = payload.get("opMan_signature", "")
        supervisor_sig_dataurl = payload.get("supervisor_signature", "")
        supervisor_comments = payload.get("supervisor_comments", "")
        
        tech_sig_file = None
        opman_sig_file = None
        supervisor_sig_file = None
        
        # If editing, preserve existing signatures and comments if no new ones provided
        if is_edit_mode:
            from common.db_utils import get_submission_db
            existing_submission = get_submission_db(edit_submission_id)
            if existing_submission and existing_submission.get('form_data'):
                existing_form_data = existing_submission['form_data']
                
                # Preserve tech signature if not provided
                if not tech_sig_dataurl:
                    tech_sig_file = existing_form_data.get('tech_signature')
                    if tech_sig_file:
                        logger.info(f"✅ Preserving existing tech signature from submission")
                
                # Preserve opman signature if not provided
                if not opman_sig_dataurl:
                    opman_sig_file = existing_form_data.get('opMan_signature')
                    if opman_sig_file:
                        logger.info(f"✅ Preserving existing opman signature from submission")
                
                # Preserve supervisor signature if not provided
                if not supervisor_sig_dataurl:
                    supervisor_sig_file = existing_form_data.get('supervisor_signature')
                    if supervisor_sig_file:
                        logger.info(f"✅ Preserving existing supervisor signature from submission")
                
                # Preserve supervisor comments if not provided (or if empty string provided but existing has value)
                if not supervisor_comments or supervisor_comments.strip() == '':
                    existing_comments = existing_form_data.get('supervisor_comments')
                    if existing_comments and existing_comments.strip():
                        supervisor_comments = existing_comments
                        logger.info(f"✅ Preserving existing supervisor comments from submission")
        
        # Upload new signatures if provided
        if tech_sig_dataurl and not tech_sig_file:
            fname, fpath, url = save_signature_dataurl(tech_sig_dataurl, UPLOADS_DIR, prefix="tech_sig")
            if url:  # Check for URL, not fname (cloud upload returns None for fname)
                tech_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
        
        if opman_sig_dataurl and not opman_sig_file:
            fname, fpath, url = save_signature_dataurl(opman_sig_dataurl, UPLOADS_DIR, prefix="opman_sig")
            if url:  # Check for URL, not fname (cloud upload returns None for fname)
                opman_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
        
        if supervisor_sig_dataurl and not supervisor_sig_file:
            # Only process if signature data is not empty
            if supervisor_sig_dataurl.strip() and supervisor_sig_dataurl.strip() != '':
                fname, fpath, url = save_signature_dataurl(supervisor_sig_dataurl, UPLOADS_DIR, prefix="supervisor_sig")
                if url:
                    supervisor_sig_file = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
                    logger.info(f"✅ Supervisor signature saved successfully (URL: {url[:80]}...)")
                else:
                    logger.warning(f"⚠️ Supervisor signature upload failed - no URL returned")
            else:
                logger.warning(f"⚠️ Supervisor signature data is empty, skipping upload")
        
        # Process items with photo URLs
        items_data = payload.get("items", [])
        items = []
        
        for item_data in items_data:
            asset = item_data.get("asset", "")
            system = item_data.get("system", "")
            description = item_data.get("description", "")
            quantity = item_data.get("quantity", "1")
            brand = item_data.get("brand", "")
            specification = item_data.get("specification", "")
            comments = item_data.get("comments", "")
            photo_urls = item_data.get("photo_urls", [])
            
            # Convert photo URLs to the format expected by generators
            photos_saved = []
            for url in photo_urls:
                photos_saved.append({
                    "saved": None,    # No local filename since already in cloud
                    "path": None,     # No local path
                    "url": url,       # Cloud URL
                    "is_cloud": True  # Flag for PDF generator to fetch from cloud
                })
            
            items.append({
                "asset": asset,
                "system": system,
                "description": description,
                "quantity": quantity,
                "brand": brand,
                "specification": specification,
                "comments": comments,
                "photos": photos_saved
            })
        
        # Create or update submission
        # Only include supervisor_signature if it has a value (don't set to None)
        submission_data = {
            "site_name": site_name,
            "visit_date": visit_date,
            "tech_signature": tech_sig_file,
            "opMan_signature": opman_sig_file,
            "items": items,
            "timestamp": datetime.now().isoformat(),
            "base_url": request.host_url.rstrip('/')
        }
        
        # Always include supervisor fields in submission_data
        # Include signature if we have one (new or preserved)
        if supervisor_sig_file:
            submission_data["supervisor_signature"] = supervisor_sig_file
            logger.info(f"✅ Including supervisor signature in submission data (URL: {supervisor_sig_file.get('url', 'N/A')[:80] if isinstance(supervisor_sig_file, dict) else 'N/A'})")
        elif is_edit_mode:
            # When editing, check if we preserved an existing signature earlier
            # (This should have been set in the preservation logic above)
            if supervisor_sig_file is None:
                # Double-check existing submission for signature
                from common.db_utils import get_submission_db
                existing_submission = get_submission_db(edit_submission_id)
                if existing_submission and existing_submission.get('form_data'):
                    existing_sig = existing_submission['form_data'].get('supervisor_signature')
                    if existing_sig:
                        submission_data["supervisor_signature"] = existing_sig
                        logger.info(f"✅ Preserving existing supervisor signature in submission data from database")
                    else:
                        logger.warning(f"⚠️ No existing supervisor signature found in database for submission {edit_submission_id}")
            else:
                # supervisor_sig_file was set during preservation, include it
                submission_data["supervisor_signature"] = supervisor_sig_file
                logger.info(f"✅ Including preserved supervisor signature in submission data")
        
        # Always include supervisor_comments (even if empty, so field is preserved)
        submission_data["supervisor_comments"] = supervisor_comments or ''
        if supervisor_comments:
            logger.info(f"✅ Supervisor comments: {len(supervisor_comments)} characters")
        else:
            logger.info(f"ℹ️ Supervisor comments: empty (field preserved)")
        
        # Get user_id from JWT token if available
        user_id = None
        try:
            from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id:
                    logger.info(f"✅ Submission will be associated with user_id: {user_id}")
                else:
                    logger.warning("⚠️ JWT token verified but no user_id found")
            except Exception as jwt_error:
                logger.debug(f"JWT token not available or invalid: {jwt_error}")
                # No token or invalid token - submission will be anonymous
        except Exception as e:
            logger.debug(f"JWT verification error: {e}")
            pass  # JWT not available
        
        # Handle edit vs new submission
        if is_edit_mode:
            from common.db_utils import update_submission_db
            
            # Add submission_id to the data for consistency
            submission_data["submission_id"] = edit_submission_id
            
            # Update existing submission
            submission_db = update_submission_db(
                submission_id=edit_submission_id,
                form_data=submission_data,
                site_name=site_name,
                visit_date=visit_date,
                preserve_signatures=True  # Keep existing signatures if not replaced
            )
            
            if not submission_db:
                return jsonify({"status": "error", "error": "Submission not found"}), 404
            
            sub_id = submission_db.submission_id
            logger.info(f"✅ Updated submission {sub_id} with {len(items)} items")
        else:
            # Create new submission
            sub_id = random_id("sub")
            submission_data["submission_id"] = sub_id
            
            submission_db = create_submission_db(
                module_type='hvac_mep',
                form_data=submission_data,
                site_name=site_name,
                visit_date=visit_date,
                user_id=user_id
            )
            sub_id = submission_db.submission_id
            logger.info(f"✅ Created submission {sub_id} with {len(items)} items")

            # Trigger inspection email notification on real HVAC submission.
            try:
                submitter_user = db.session.get(User, int(user_id)) if user_id else None
                send_inspection_submitted(submission_db, submitter_user)
            except Exception as notify_err:
                logger.warning(f"Submission email notification failed for {sub_id}: {notify_err}")
        
        # Create job in database
        job = create_job_db(submission_db)
        job_id = job.job_id
        
        logger.info(f"Starting background task for job {job_id}")
        
        # Submit to executor
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
                    import traceback
                    logger.error(traceback.format_exc())
            
            future.add_done_callback(log_exception)
            logger.info(f"✅ Background job {job_id} submitted to executor")
        else:
            logger.error("ThreadPoolExecutor not found in app config")
            return jsonify({'error': 'Background processing not available'}), 500
        
        logger.info(f"🚀 Job {job_id} queued for submission {sub_id}")
        
        return jsonify({
            "status": "ok",
            "submission_id": sub_id,
            "job_id": job_id,
            "job_status_url": url_for("hvac_mep_bp.status", job_id=job_id, _external=False)
        })
        
    except Exception as e:
        logger.error(f"❌ Submit with URLs failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "error": str(e)}), 500


@hvac_mep_bp.route("/add-photos-to-item", methods=["POST"])
def add_photos_to_item():
    """
    Add additional photos to an existing item in a submission.
    
    Expected JSON payload:
    {
        "submission_id": "sub_abc123",
        "item_index": 0,
        "photo_urls": ["https://cloudinary.../photo1.jpg", "https://cloudinary.../photo2.jpg"]
    }
    
    Or multipart/form-data with:
    - submission_id
    - item_index
    - photo files as file uploads
    """
    try:
        GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
        
        # Check if request has files (multipart) or JSON
        if request.files:
            # Multipart form data with file uploads
            submission_id = request.form.get("submission_id")
            item_index = request.form.get("item_index")
            
            if not submission_id or item_index is None:
                return error_response("submission_id and item_index are required", 400, "VALIDATION_ERROR")
            
            try:
                item_index = int(item_index)
            except ValueError:
                return error_response("item_index must be a number", 400, "VALIDATION_ERROR")
            
            # Get the submission from database
            from common.db_utils import get_submission_db
            submission = get_submission_db(submission_id)
            
            if not submission:
                return error_response("Submission not found", 404, "NOT_FOUND")
            
            # Parse form_data JSON (submission is a dict, not an object)
            form_data = submission.get('form_data', {})
            items = form_data.get("items", [])
            
            if item_index < 0 or item_index >= len(items):
                return error_response(f"Item index {item_index} out of range (0-{len(items)-1})", 400, "VALIDATION_ERROR")
            
            # Upload new photos
            new_photos = []
            photo_files = request.files.getlist("photos")
            
            for photo_file in photo_files:
                if photo_file and getattr(photo_file, "filename", None):
                    try:
                        # Upload to cloud storage
                        result = save_uploaded_file_cloud(photo_file, UPLOADS_DIR, folder="hvac_photos")
                        new_photos.append({
                            "saved": result.get("filename"),
                            "path": None,
                            "url": result["url"],
                            "is_cloud": result.get("is_cloud", True)
                        })
                        logger.info(f"✅ Uploaded photo: {result['url']}")
                    except Exception as e:
                        logger.error(f"Failed to upload photo: {e}")
                        return error_response(f"Photo upload failed: {str(e)}", 500, "UPLOAD_ERROR")
            
            if not new_photos:
                return error_response("No valid photos provided", 400, "VALIDATION_ERROR")
            
            # Add photos to the item
            if "photos" not in items[item_index]:
                items[item_index]["photos"] = []
            
            items[item_index]["photos"].extend(new_photos)
            
            # Update the submission in database
            from common.db_utils import update_submission_db
            updated_submission = update_submission_db(
                submission_id=submission_id,
                form_data=form_data,
                site_name=submission.get('site_name'),
                visit_date=submission.get('visit_date'),
                preserve_signatures=True
            )
            
            if not updated_submission:
                return error_response("Failed to update submission", 500, "UPDATE_ERROR")
            
            logger.info(f"✅ Added {len(new_photos)} photos to item {item_index} in submission {submission_id}")
            
            return jsonify({
                "status": "success",
                "message": f"Added {len(new_photos)} photo(s) to item",
                "photos": new_photos,
                "total_photos": len(items[item_index]["photos"])
            })
            
        else:
            # JSON payload with pre-uploaded photo URLs
            data = request.get_json()
            
            if not data:
                return error_response("No data provided", 400, "VALIDATION_ERROR")
            
            submission_id = data.get("submission_id")
            item_index = data.get("item_index")
            photo_urls = data.get("photo_urls", [])
            
            if not submission_id or item_index is None:
                return error_response("submission_id and item_index are required", 400, "VALIDATION_ERROR")
            
            if not photo_urls or not isinstance(photo_urls, list):
                return error_response("photo_urls must be a non-empty array", 400, "VALIDATION_ERROR")
            
            try:
                item_index = int(item_index)
            except ValueError:
                return error_response("item_index must be a number", 400, "VALIDATION_ERROR")
            
            # Get the submission from database
            from common.db_utils import get_submission_db
            submission = get_submission_db(submission_id)
            
            if not submission:
                return error_response("Submission not found", 404, "NOT_FOUND")
            
            # Parse form_data JSON (submission is a dict, not an object)
            form_data = submission.get('form_data', {})
            items = form_data.get("items", [])
            
            if item_index < 0 or item_index >= len(items):
                return error_response(f"Item index {item_index} out of range (0-{len(items)-1})", 400, "VALIDATION_ERROR")
            
            # Add photo URLs to the item
            new_photos = []
            for url in photo_urls:
                new_photos.append({
                    "saved": None,
                    "path": None,
                    "url": url,
                    "is_cloud": True
                })
            
            if "photos" not in items[item_index]:
                items[item_index]["photos"] = []
            
            items[item_index]["photos"].extend(new_photos)
            
            # Update the submission in database
            from common.db_utils import update_submission_db
            updated_submission = update_submission_db(
                submission_id=submission_id,
                form_data=form_data,
                site_name=submission.get('site_name'),
                visit_date=submission.get('visit_date'),
                preserve_signatures=True
            )
            
            if not updated_submission:
                return error_response("Failed to update submission", 500, "UPDATE_ERROR")
            
            logger.info(f"✅ Added {len(new_photos)} photo URLs to item {item_index} in submission {submission_id}")
            
            return jsonify({
                "status": "success",
                "message": f"Added {len(new_photos)} photo(s) to item",
                "photos": new_photos,
                "total_photos": len(items[item_index]["photos"])
            })
            
    except Exception as e:
        logger.error(f"❌ Add photos to item failed: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response(str(e), 500, "INTERNAL_ERROR")