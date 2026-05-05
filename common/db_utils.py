"""
Database utility functions for submission and job management
Provides a clean interface for database operations used by all modules
"""
import logging
from datetime import datetime
from app.models import db, Submission, Job, File, User
from common.utils import random_id
from common.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)


def _notify_supervisor(submission, session):
    """Notify supervisor when technician submits a form"""
    try:
        # Find a supervisor (first available supervisor)
        supervisor = User.query.filter_by(designation='supervisor', is_active=True).first()
        
        if supervisor and hasattr(submission, 'supervisor_id'):
            submission.supervisor_id = supervisor.id
            submission.workflow_status = 'supervisor_notified'
            submission.supervisor_notified_at = utc_now_naive()
            session.commit()
            logger.info(f"✅ Notified supervisor {supervisor.username} about submission {submission.submission_id}")
    except Exception as e:
        logger.warning(f"Could not notify supervisor: {e}")


def _notify_manager(submission, session):
    """Notify manager when supervisor reviews a form"""
    try:
        # Find a manager (first available manager)
        manager = User.query.filter_by(designation='manager', is_active=True).first()
        
        if manager and hasattr(submission, 'manager_id'):
            submission.manager_id = manager.id
            submission.workflow_status = 'manager_notified'
            submission.manager_notified_at = utc_now_naive()
            session.commit()
            logger.info(f"✅ Notified manager {manager.username} about submission {submission.submission_id}")
    except Exception as e:
        logger.warning(f"Could not notify manager: {e}")


def create_submission_db(module_type, form_data, site_name=None, visit_date=None, user_id=None):
    """
    Create a submission in the database
    
    Args:
        module_type: 'civil', 'hvac_mep', or 'cleaning'
        form_data: Dictionary containing all form fields and file URLs
        site_name: Name of the site/project (optional)
        visit_date: Date of visit as string or date object (optional)
        user_id: ID of the user creating submission (optional)
    
    Returns:
        Submission object with submission_id
    """
    try:
        submission_id = random_id("sub")
        
        # Parse visit_date if string
        parsed_date = None
        if visit_date:
            if isinstance(visit_date, str):
                try:
                    parsed_date = datetime.strptime(visit_date, '%Y-%m-%d').date()
                except ValueError:
                    logger.warning(f"Invalid date format: {visit_date}")
            else:
                parsed_date = visit_date
        
        # Set workflow status
        # Check if user is supervisor - if so, set to operations_manager_review immediately
        workflow_status = 'submitted'
        is_supervisor_submission = False
        
        if user_id:
            try:
                from app.models import User
                user = db.session.get(User, user_id)
                if user and user.designation == 'supervisor':
                    is_supervisor_submission = True
                    workflow_status = 'operations_manager_review'  # Supervisor submissions go directly to Operations Manager
            except ImportError:
                pass
        
        submission = Submission(
            submission_id=submission_id,
            user_id=user_id,
            module_type=module_type,
            site_name=site_name or form_data.get('site_name') or form_data.get('project_name'),
            visit_date=parsed_date,
            status='submitted',
            workflow_status=workflow_status if hasattr(Submission, 'workflow_status') else None,
            form_data=form_data
        )
        
        # If the user creating the form is a supervisor, set supervisor_id
        if user_id:
            try:
                from app.models import User
                user = db.session.get(User, user_id)
                if user and user.designation == 'supervisor':
                    submission.supervisor_id = user.id
                    logger.info(f"✅ Set supervisor_id to {user.id} for submission {submission_id}")
                    logger.info(f"✅ Set workflow_status to 'operations_manager_review' for supervisor submission {submission_id}")
            except ImportError:
                pass
        
        db.session.add(submission)
        db.session.commit()
        
        # Trigger workflow notification if user has designation
        if user_id:
            try:
                from app.models import User
            except ImportError:
                pass
            else:
                user = db.session.get(User, user_id)
                if user and user.designation == 'technician':
                    # Find supervisor and notify
                    _notify_supervisor(submission, db.session)
        
        logger.info(f"✅ Created submission {submission_id} for {module_type}")
        return submission
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to create submission: {e}")
        raise


def create_job_db(submission_id_or_obj, job_id=None):
    """
    Create a job in the database for report generation
    
    Args:
        submission_id_or_obj: Submission ID (int) or Submission object
        job_id: Custom job ID (optional, will generate if not provided)
    
    Returns:
        Job object with job_id
    """
    try:
        if not job_id:
            job_id = random_id("job")
        
        # Get submission ID if object passed
        if isinstance(submission_id_or_obj, Submission):
            submission_db_id = submission_id_or_obj.id
        elif isinstance(submission_id_or_obj, int):
            submission_db_id = submission_id_or_obj
        else:
            # Assume it's a submission_id string, need to look up
            submission = Submission.query.filter_by(submission_id=submission_id_or_obj).first()
            if not submission:
                raise ValueError(f"Submission not found: {submission_id_or_obj}")
            submission_db_id = submission.id
        
        job = Job(
            job_id=job_id,
            submission_id=submission_db_id,
            status='pending',
            progress=0,
            started_at=utc_now_naive()
        )
        
        db.session.add(job)
        db.session.commit()
        
        logger.info(f"✅ Created job {job_id} for submission ID {submission_db_id}")
        return job
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to create job: {e}")
        raise


def update_job_progress_db(job_id, progress, status=None, error_message=None):
    """
    Update job progress in database
    
    Args:
        job_id: Job ID string
        progress: Progress percentage (0-100)
        status: Optional status update ('pending', 'processing', 'completed', 'failed')
        error_message: Optional error message if failed
    """
    try:
        job = Job.query.filter_by(job_id=job_id).first()
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job.progress = progress
        
        if status:
            job.status = status
        
        if progress > 0 and not job.started_at:
            job.started_at = utc_now_naive()
        
        if error_message:
            job.error_message = error_message
            job.status = 'failed'
        
        db.session.commit()
        logger.debug(f"Updated job {job_id}: progress={progress}, status={status}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to update job progress: {e}")


def complete_job_db(job_id, result_urls):
    """
    Mark job as completed with result URLs
    
    Args:
        job_id: Job ID string
        result_urls: Dictionary with report URLs (e.g., {"excel": "url", "pdf": "url"})
    """
    try:
        job = Job.query.filter_by(job_id=job_id).first()
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job.status = 'completed'
        job.progress = 100
        job.completed_at = utc_now_naive()
        job.result_data = result_urls
        
        db.session.commit()
        logger.info(f"✅ Job {job_id} completed successfully")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to complete job: {e}")


def fail_job_db(job_id, error_message):
    """
    Mark job as failed with error message
    
    Args:
        job_id: Job ID string
        error_message: Error description
    """
    try:
        job = Job.query.filter_by(job_id=job_id).first()
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return
        
        job.status = 'failed'
        job.progress = 0
        job.completed_at = utc_now_naive()
        job.error_message = error_message
        
        db.session.commit()
        logger.error(f"❌ Job {job_id} failed: {error_message}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to mark job as failed: {e}")


def get_job_status_db(job_id):
    """
    Get job status from database
    
    Args:
        job_id: Job ID string
    
    Returns:
        Dictionary with job status, or None if not found
    """
    try:
        from flask import has_app_context, current_app
        
        # Ensure we're in app context
        if not has_app_context():
            logger.error(f"❌ get_job_status_db called outside app context for {job_id}")
            return None
        
        job = Job.query.filter_by(job_id=job_id).first()
        if not job:
            logger.warning(f"Job not found in database: {job_id}")
            return None
        
        return job.to_dict()
        
    except Exception as e:
        logger.error(f"❌ Failed to get job status for {job_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_submission_db(submission_id, eager_load=None, return_object=False):
    """
    Get submission from database by submission_id
    
    Args:
        submission_id: Submission ID string (e.g., 'sub_abc123')
        eager_load: Optional list of relationships to eager load (e.g., ['user', 'jobs'])
        return_object: If True, return the Submission object instead of dict
    
    Returns:
        Dictionary with submission data (or Submission object if return_object=True), or None if not found
    """
    try:
        query = Submission.query
        
        # Apply eager loading if specified
        if eager_load:
            from sqlalchemy.orm import joinedload
            for rel in eager_load:
                if hasattr(Submission, rel):
                    query = query.options(joinedload(getattr(Submission, rel)))
        
        submission = query.filter_by(submission_id=submission_id).first()
        if not submission:
            return None
        
        if return_object:
            return submission
        
        return submission.to_dict()
        
    except Exception as e:
        logger.error(f"❌ Failed to get submission: {e}")
        return None


def update_submission_db(submission_id, form_data=None, site_name=None, visit_date=None, preserve_signatures=True):
    """
    Update an existing submission in the database
    
    Args:
        submission_id: Submission ID string (e.g., 'sub_abc123')
        form_data: Updated form data dictionary (optional)
        site_name: Updated site name (optional)
        visit_date: Updated visit date (optional)
        preserve_signatures: If True, keep existing signatures if not provided in form_data (default: True)
    
    Returns:
        Updated Submission object, or None if not found
    """
    try:
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            logger.warning(f"Submission not found: {submission_id}")
            return None
        
        # Update basic fields
        if site_name is not None:
            submission.site_name = site_name
        
        if visit_date is not None:
            if isinstance(visit_date, str):
                try:
                    submission.visit_date = datetime.strptime(visit_date, '%Y-%m-%d').date()
                except ValueError:
                    logger.warning(f"Invalid date format: {visit_date}")
            else:
                submission.visit_date = visit_date
        
        # Update form_data while preserving signatures if requested
        if form_data is not None:
            # Get existing form_data
            existing_form_data = submission.form_data or {}
            
            if preserve_signatures:
                # Preserve existing signatures if not provided in new form_data
                signature_fields = ['tech_signature', 'opMan_signature', 'supervisor_signature']
                for sig_field in signature_fields:
                    # If new form_data doesn't have signature, use existing one
                    if sig_field not in form_data or not form_data[sig_field]:
                        if sig_field in existing_form_data and existing_form_data[sig_field]:
                            form_data[sig_field] = existing_form_data[sig_field]
                            logger.info(f"✅ Preserved existing {sig_field} from database")
                
                # Also preserve supervisor_comments if not provided
                if 'supervisor_comments' not in form_data or not form_data.get('supervisor_comments'):
                    if 'supervisor_comments' in existing_form_data and existing_form_data.get('supervisor_comments'):
                        form_data['supervisor_comments'] = existing_form_data['supervisor_comments']
                        logger.info(f"✅ Preserved existing supervisor_comments from database")
            
            # Merge form_data to preserve any fields not in the update
            # This ensures all existing data is preserved, not just signatures
            merged_form_data = existing_form_data.copy()
            merged_form_data.update(form_data)
            submission.form_data = merged_form_data
        
        submission.updated_at = utc_now_naive()
        
        db.session.commit()
        logger.info(f"✅ Updated submission {submission_id}")
        
        return submission
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to update submission: {e}")
        raise
