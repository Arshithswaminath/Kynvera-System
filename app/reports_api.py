"""
On-Demand Report Regeneration API
Allows regenerating reports from database without storing them permanently
"""
import os
import logging
from flask import Blueprint, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Submission, User
from common.db_utils import get_submission_db

logger = logging.getLogger(__name__)

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')


def _user_can_access_submission(user, submission):
    """Check if user is allowed to access this submission (for report regeneration)."""
    if not user or not submission:
        return False
    if user.role == 'admin':
        return True
    if submission.user_id and submission.user_id == user.id:
        return True
    # Workflow participants can access
    if submission.supervisor_id == user.id or submission.operations_manager_id == user.id:
        return True
    if submission.business_dev_id == user.id or submission.procurement_id == user.id:
        return True
    if submission.general_manager_id == user.id or submission.manager_id == user.id:
        return True
    return False


@reports_bp.route('/regenerate/<submission_id>/excel', methods=['GET'])
@jwt_required()
def regenerate_excel(submission_id):
    """
    Regenerate Excel report from submission data on-demand
    No permanent storage - report is generated fresh each time
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id) if user_id else None
        if not user or not user.is_active:
            return jsonify({'error': 'Authentication required'}), 401

        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return jsonify({'error': 'Submission not found'}), 404

        if not _user_can_access_submission(user, submission):
            return jsonify({'error': 'Access denied to this submission'}), 403

        submission_data = get_submission_db(submission_id)
        if not submission_data:
            return jsonify({'error': 'Submission not found'}), 404

        module_type = submission_data.get('module_type')
        form_data_wrapper = submission_data.get('form_data', {})
        # Extract inner data if nested (matches module_base.process_report_job)
        form_data = form_data_wrapper.get('data', form_data_wrapper) if isinstance(form_data_wrapper, dict) else form_data_wrapper
        
        # Generate report based on module type
        if module_type == 'civil':
            from module_civil.civil_generators import create_excel_report
        elif module_type == 'hvac_mep':
            from module_hvac_mep.hvac_generators import create_excel_report
        elif module_type == 'cleaning':
            from module_cleaning.cleaning_generators import create_excel_report
        else:
            return jsonify({'error': f'Unknown module type: {module_type}'}), 400
        
        # Generate report in temporary location
        temp_dir = current_app.config.get('GENERATED_DIR')
        report_path = create_excel_report(form_data, temp_dir)
        
        # Send file and delete after sending
        return send_file(
            report_path,
            as_attachment=True,
            download_name=os.path.basename(report_path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Failed to regenerate Excel: {e}")
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/regenerate/<submission_id>/pdf', methods=['GET'])
@jwt_required()
def regenerate_pdf(submission_id):
    """
    Regenerate PDF report from submission data on-demand
    No permanent storage - report is generated fresh each time
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id) if user_id else None
        if not user or not user.is_active:
            return jsonify({'error': 'Authentication required'}), 401

        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return jsonify({'error': 'Submission not found'}), 404

        if not _user_can_access_submission(user, submission):
            return jsonify({'error': 'Access denied to this submission'}), 403

        submission_data = get_submission_db(submission_id)
        if not submission_data:
            return jsonify({'error': 'Submission not found'}), 404

        module_type = submission_data.get('module_type')
        form_data_wrapper = submission_data.get('form_data', {})
        # Extract inner data if nested (matches module_base.process_report_job)
        form_data = form_data_wrapper.get('data', form_data_wrapper) if isinstance(form_data_wrapper, dict) else form_data_wrapper
        
        # Generate report based on module type
        if module_type == 'civil':
            from module_civil.civil_generators import create_pdf_report
        elif module_type == 'hvac_mep':
            from module_hvac_mep.hvac_generators import create_pdf_report
        elif module_type == 'cleaning':
            from module_cleaning.cleaning_generators import create_pdf_report
        else:
            return jsonify({'error': f'Unknown module type: {module_type}'}), 400
        
        # Generate report in temporary location
        temp_dir = current_app.config.get('GENERATED_DIR')
        report_path = create_pdf_report(form_data, temp_dir)
        
        # Send file and delete after sending
        return send_file(
            report_path,
            as_attachment=True,
            download_name=os.path.basename(report_path),
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Failed to regenerate PDF: {e}")
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/list/<module_type>', methods=['GET'])
@jwt_required()
def list_reports(module_type):
    """
    List all submissions for a module (authenticated users only).
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id) if user_id else None
        if not user or not user.is_active:
            return jsonify({'error': 'Authentication required'}), 401

        submissions = Submission.query.filter_by(module_type=module_type).order_by(Submission.created_at.desc()).limit(100).all()
        
        return jsonify({
            'module': module_type,
            'count': len(submissions),
            'submissions': [s.to_dict() for s in submissions]
        })
        
    except Exception as e:
        logger.error(f"Failed to list submissions: {e}")
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/submission/<submission_id>', methods=['GET'])
@jwt_required()
def get_submission_details(submission_id):
    """
    Get submission details with regeneration links (authenticated + authorized).
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id) if user_id else None
        if not user or not user.is_active:
            return jsonify({'error': 'Authentication required'}), 401

        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return jsonify({'error': 'Submission not found'}), 404

        if not _user_can_access_submission(user, submission):
            return jsonify({'error': 'Access denied to this submission'}), 403

        submission_data = get_submission_db(submission_id)
        if not submission_data:
            return jsonify({'error': 'Submission not found'}), 404

        # Add regeneration URLs
        submission_data['reports'] = {
            'excel_url': f"/api/reports/regenerate/{submission_id}/excel",
            'pdf_url': f"/api/reports/regenerate/{submission_id}/pdf"
        }
        
        return jsonify(submission_data)
        
    except Exception as e:
        logger.error(f"Failed to get submission: {e}")
        return jsonify({'error': str(e)}), 500
