"""
QHSI Module — Quality, Hospitality, Safety & Inspection
- Staff compliance (uniforms, PPE, company-issued safety kit)
- Training & meeting bookings per project
- Unified QHSA site inspection (HVAC + Civil + Cleaning areas, photos, OM workflow)
"""
import json
import logging
import os
from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models import (
    BDProject,
    QhseComplianceImport,
    QhseStaffComplianceRow,
    QhsiTraining,
    User,
    db,
)
from app.middleware import module_access_required
from common.datetime_utils import utc_now_naive
from common.db_utils import create_job_db, create_submission_db, get_submission_db
from common.error_responses import error_response, success_response
from common.inspection_inapp_notifications import notify_inspection_stage
from common.utils import random_id, upload_base64_to_cloud
from common.workflow_notifications import send_inspection_submitted

from module_qhsi.catalog import build_unified_inspection_catalog, staff_kit_types

logger = logging.getLogger(__name__)

qhsi_bp = Blueprint(
    'qhsi',
    __name__,
    url_prefix='/qhsi',
    template_folder='templates',
)

def _current_user():
    uid = get_jwt_identity()
    if uid is None:
        return None
    return db.session.get(User, int(uid))


def _has_qhsi_access(user):
    if not user:
        return False
    if user.role == 'admin':
        return True
    return bool(getattr(user, 'access_qhsi', False))


def _latest_import_batch(user):
    """Most recent Excel import for this user (admins see latest across all users)."""
    try:
        q = QhseComplianceImport.query.order_by(QhseComplianceImport.created_at.desc())
        if user and user.role != 'admin':
            q = q.filter(QhseComplianceImport.imported_by_id == user.id)
        return q.first()
    except Exception as e:
        logger.warning('QHSE import batch query failed (run restart / db.create_all): %s', e)
        db.session.rollback()
        return None


def _as_stats_dict(raw):
    """Normalize stored import stats (string JSON, nested stats, or alias keys)."""
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    nested = out.get('stats')
    if isinstance(nested, dict):
        for key, value in nested.items():
            out.setdefault(key, value)
    if out.get('employees') is None and out.get('employee_count') is not None:
        out['employees'] = out['employee_count']
    if out.get('kit_lines') is None and out.get('row_count') is not None:
        out['kit_lines'] = out['row_count']
    if out.get('compliant') is None and out.get('ok') is not None:
        out['compliant'] = out['ok']
    if out.get('issues') is None and out.get('issue') is not None:
        out['issues'] = out['issue']
    return out


def _import_stats(user):
    empty = {
        'has_import': False,
        'batch': None,
        'employees': 0,
        'kit_lines': 0,
        'compliant': 0,
        'issues': 0,
        'missing': 0,
        'non_compliant': 0,
        'compliance_rate': 0.0,
    }
    batch = _latest_import_batch(user)
    if not batch:
        return empty

    stats = _as_stats_dict(batch.stats_json)
    required = ('employees', 'kit_lines', 'compliant', 'issues', 'missing', 'compliance_rate')
    if any(stats.get(key) is None for key in required):
        rows = list(batch.rows or [])
        if rows:
            from module_qhsi.excel_import import stats_from_rows
            computed = stats_from_rows([row.to_dict() for row in rows])
            for key, value in computed.items():
                if stats.get(key) is None:
                    stats[key] = value
        stats.setdefault('employees', batch.employee_count or 0)
        stats.setdefault('kit_lines', batch.row_count or 0)
        for key in ('compliant', 'issues', 'missing', 'non_compliant'):
            stats.setdefault(key, 0)
        stats.setdefault('compliance_rate', 0.0)

    stats['has_import'] = True
    stats['batch'] = batch.to_dict()
    return stats


def _submission_stats(user):
    from app.models import Submission

    qhsi_types = ('qhsi_inspection', 'qhsi_staff_compliance')
    base = Submission.query.filter(Submission.module_type.in_(qhsi_types))
    if user and user.role != 'admin':
        base = base.filter(Submission.user_id == user.id)
    total = base.count()
    pending = base.filter(
        Submission.workflow_status.notin_(('completed', 'general_manager_approved', 'rejected'))
    ).count()
    approved = base.filter(
        Submission.workflow_status.in_(('completed', 'general_manager_approved'))
    ).count()
    staff = base.filter(Submission.module_type == 'qhsi_staff_compliance').count()
    inspections = base.filter(Submission.module_type == 'qhsi_inspection').count()
    return {
        'total': total,
        'pending': pending,
        'approved': approved,
        'staff_compliance': staff,
        'inspections': inspections,
    }


def _qhse_sidebar_stats(user):
    """Counts for QHSE sidebar badges (submissions + latest Excel import)."""
    sub = _submission_stats(user)
    imp = _import_stats(user)
    training_upcoming = QhsiTraining.query.filter(
        QhsiTraining.status == 'scheduled',
        QhsiTraining.scheduled_at >= utc_now_naive(),
    ).count()
    if imp.get('has_import'):
        staff_lines = imp.get('kit_lines') or 0
        total_records = (imp.get('employees') or 0) + sub['inspections']
    else:
        staff_lines = sub['staff_compliance']
        total_records = sub['total']
    return {
        'total': total_records,
        'pending': sub['pending'],
        'approved': sub['approved'],
        'staff_compliance': staff_lines,
        'inspections': sub['inspections'],
        'training_upcoming': training_upcoming,
        'import_employees': imp.get('employees') or 0,
        'import_non_compliant': imp.get('non_compliant') or 0,
        'import_compliant': imp.get('compliant') or 0,
        'import_compliance_rate': imp.get('compliance_rate') or 0,
        'has_import': imp.get('has_import'),
    }


def _qhse_page_context(user):
    """Template context for all QHSE pages (sidebar + dashboard)."""
    stats = _qhse_sidebar_stats(user)
    return {
        'user': user,
        'sidebar_stats': stats,
    }


def _parse_visit_date(date_str):
    if not date_str:
        return None, None
    try:
        visit = datetime.strptime(str(date_str).strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None, 'Invalid date format. Use YYYY-MM-DD'
    today = utc_now_naive().date()
    if visit > today + timedelta(days=1):
        return None, f'Visit date ({visit}) cannot be more than 1 day in the future'
    return visit, None


def _upload_photo_list(photos, folder, uploads_dir):
    saved = []
    if not isinstance(photos, list):
        return saved
    for idx, raw in enumerate(photos):
        if not raw or not isinstance(raw, str) or not raw.startswith('data:image'):
            continue
        try:
            url, is_cloud = upload_base64_to_cloud(
                raw, folder=folder, prefix=f'photo_{idx}', uploads_dir=uploads_dir
            )
            if url:
                saved.append({'url': url, 'index': idx, 'is_cloud': is_cloud})
        except Exception as e:
            logger.error('QHSI photo upload failed idx=%s: %s', idx, e)
            raise
    return saved


def save_signature_dataurl(dataurl, uploads_dir, prefix='signature'):
    if not dataurl:
        return None, None, None
    url, is_cloud = upload_base64_to_cloud(
        dataurl, folder='signatures', prefix=prefix, uploads_dir=uploads_dir
    )
    if not url:
        raise Exception('Signature upload failed')
    if is_cloud:
        return None, None, url
    filename = url.split('/')[-1]
    from config import GENERATED_DIR
    file_path = os.path.join(GENERATED_DIR, 'uploads', 'signatures', filename)
    return filename, file_path, url


def get_paths():
    from config import GENERATED_DIR, JOBS_DIR, UPLOADS_DIR
    from concurrent.futures import ThreadPoolExecutor
    executor = current_app.config.get('EXECUTOR') if current_app else None
    if not executor:
        executor = ThreadPoolExecutor(max_workers=2)
    return GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, executor


def process_job(sub_id, job_id, config, app):
    from common.module_base import process_report_job
    from module_qhsi.qhsi_generators import create_excel_report, create_pdf_report

    process_report_job(
        sub_id=sub_id,
        job_id=job_id,
        app=app,
        module_name='qhsi_inspection',
        create_excel_report=create_excel_report,
        create_pdf_report=create_pdf_report,
    )


# ─── Pages ───────────────────────────────────────────────────────────────────

@qhsi_bp.route('/')
@jwt_required()
def qhsi_dashboard():
    user = _current_user()
    if not user:
        return redirect('/login')
    if not _has_qhsi_access(user):
        return redirect('/dashboard')
    ctx = _qhse_page_context(user)
    return render_template('qhsi_dashboard.html', **ctx)


@qhsi_bp.route('/staff-compliance')
@jwt_required()
@module_access_required('qhsi')
def staff_compliance_form():
    user = _current_user()
    return render_template(
        'qhsi_staff_compliance.html',
        kit_types=staff_kit_types(),
        **_qhse_page_context(user),
    )


@qhsi_bp.route('/training')
@jwt_required()
@module_access_required('qhsi')
def training_page():
    user = _current_user()
    return render_template('qhsi_training.html', **_qhse_page_context(user))


@qhsi_bp.route('/inspection')
@jwt_required()
@module_access_required('qhsi')
def inspection_form():
    user = _current_user()
    return render_template('qhsi_inspection_form.html', **_qhse_page_context(user))


# ─── APIs: catalog & projects ────────────────────────────────────────────────

@qhsi_bp.route('/api/inspection-catalog')
@jwt_required()
@module_access_required('qhsi')
def api_inspection_catalog():
    return jsonify({'success': True, 'catalog': build_unified_inspection_catalog()})


@qhsi_bp.route('/api/projects')
@jwt_required()
@module_access_required('qhsi')
def api_projects():
    rows = BDProject.query.order_by(BDProject.company.asc(), BDProject.name.asc()).all()
    projects = [{'id': p.id, 'name': p.name, 'company': p.company} for p in rows]
    return jsonify({'success': True, 'projects': projects})


@qhsi_bp.route('/api/stats')
@jwt_required()
@module_access_required('qhsi')
def api_stats():
    user = _current_user()
    sub = _submission_stats(user)
    imp = _import_stats(user)
    training_upcoming = QhsiTraining.query.filter(
        QhsiTraining.status == 'scheduled',
        QhsiTraining.scheduled_at >= utc_now_naive(),
    ).count()
    if imp.get('has_import'):
        forms_submitted = (imp.get('employees') or 0) + sub['inspections']
        records_label = 'employees_tracked'
    else:
        forms_submitted = sub['total']
        records_label = 'forms_submitted'
    return jsonify({
        'success': True,
        'forms_submitted': forms_submitted,
        'pending': sub['pending'],
        'approved': sub['approved'],
        'training_upcoming': training_upcoming,
        'submissions': sub,
        'import': imp,
        'records_label': records_label,
        'staff_kit_compliant': imp.get('compliant') or 0,
        'staff_kit_issues': imp.get('issues') or 0,
        'staff_kit_missing': imp.get('missing') or 0,
        'staff_kit_non_compliant': imp.get('non_compliant') or 0,
        'compliance_rate': imp.get('compliance_rate') or 0,
    })


@qhsi_bp.route('/api/staff-compliance/import-template')
@jwt_required()
@module_access_required('qhsi')
def staff_compliance_import_template():
    from flask import send_file

    from module_qhsi.excel_import import build_import_template_bytes

    data = build_import_template_bytes()
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='QHSE_Staff_Compliance_Import_Template.xlsx',
    )


@qhsi_bp.route('/api/staff-compliance/import', methods=['POST'])
@jwt_required()
@module_access_required('qhsi')
def staff_compliance_import_excel():
    from module_qhsi.excel_import import parse_staff_compliance_excel, stats_from_rows

    user = _current_user()
    if 'file' not in request.files:
        return error_response('No file uploaded', status_code=400)
    file = request.files['file']
    if not file or not file.filename:
        return error_response('No file selected', status_code=400)

    try:
        parsed = parse_staff_compliance_excel(file)
    except ImportError:
        return error_response(
            'Excel import requires pandas and openpyxl',
            status_code=500,
        )
    except ValueError as e:
        return error_response(str(e), status_code=400)
    except Exception as e:
        logger.exception('QHSE Excel parse failed')
        return error_response(f'Could not parse file: {e}', status_code=400)

    stats = stats_from_rows(parsed['rows'])
    batch = QhseComplianceImport(
        import_id=random_id('qhseimp'),
        filename=file.filename,
        row_count=parsed['row_count'],
        employee_count=stats['employees'],
        stats_json=stats,
        imported_by_id=user.id if user else None,
    )
    db.session.add(batch)
    db.session.flush()

    for row in parsed['rows']:
        db.session.add(QhseStaffComplianceRow(
            import_batch_id=batch.id,
            employee_name=row['employee_name'],
            employee_id=row.get('employee_id') or None,
            project_name=row['project_name'],
            record_date=row.get('record_date'),
            department=row.get('department') or None,
            supervisor_name=row.get('supervisor_name') or None,
            notes=row.get('notes') or None,
            item_type=row.get('item_type'),
            item_label=row.get('item_label'),
            condition=row['condition'],
        ))
    db.session.commit()

    return success_response({
        'import': batch.to_dict(),
        'stats': stats,
        'mode': parsed['mode'],
        'skipped': parsed['skipped'],
        'warnings': parsed.get('errors') or [],
        'message': f'Imported {stats["kit_lines"]} kit lines for {stats["employees"]} employees.',
    })


@qhsi_bp.route('/api/staff-compliance/import/latest')
@jwt_required()
@module_access_required('qhsi')
def staff_compliance_import_latest():
    user = _current_user()
    imp = _import_stats(user)
    return jsonify({'success': True, 'import': imp})


@qhsi_bp.route('/api/staff-compliance/import', methods=['DELETE'])
@jwt_required()
@module_access_required('qhsi')
def staff_compliance_clear_import():
    user = _current_user()
    q = QhseComplianceImport.query
    if user.role != 'admin':
        q = q.filter(QhseComplianceImport.imported_by_id == user.id)
    batches = q.all()
    for b in batches:
        db.session.delete(b)
    db.session.commit()
    return success_response({'message': 'Imported compliance data cleared.'})


# ─── Staff compliance submit ─────────────────────────────────────────────────

@qhsi_bp.route('/api/staff-compliance/submit', methods=['POST'])
@jwt_required()
@module_access_required('qhsi')
def submit_staff_compliance():
    data = request.get_json(force=True) or {}
    required = ['employee_name', 'project_name', 'record_date']
    missing = [f for f in required if not str(data.get(f) or '').strip()]
    if missing:
        return error_response(f'Missing: {", ".join(missing)}', status_code=400)

    _, date_err = _parse_visit_date(data.get('record_date'))
    if date_err:
        return error_response(date_err, status_code=400)

    uploads_dir = current_app.config.get('UPLOADS_DIR')
    kit_items = data.get('kit_items') or []
    for item in kit_items:
        if isinstance(item, dict) and item.get('photos'):
            item['photos'] = _upload_photo_list(
                item['photos'], 'qhsi_staff_photos', uploads_dir
            )

    user = _current_user()
    form_data = {
        'employee_name': data.get('employee_name'),
        'employee_id': data.get('employee_id'),
        'project_name': data.get('project_name'),
        'record_date': data.get('record_date'),
        'department': data.get('department'),
        'supervisor_name': data.get('supervisor_name'),
        'notes': data.get('notes'),
        'kit_items': kit_items,
        'created_at': utc_now_naive().isoformat(),
    }

    submission = create_submission_db(
        module_type='qhsi_staff_compliance',
        form_data=form_data,
        site_name=data.get('project_name'),
        visit_date=data.get('record_date'),
        user_id=user.id if user else None,
    )
    try:
        send_inspection_submitted(submission, user)
    except Exception as e:
        logger.warning('Staff compliance notify failed: %s', e)

    return success_response({
        'submission_id': submission.submission_id,
        'message': 'Staff compliance record submitted to Operations for review.',
    })


# ─── Unified QHSA inspection submit ──────────────────────────────────────────

@qhsi_bp.route('/api/inspection/submit', methods=['POST'])
@jwt_required()
@module_access_required('qhsi')
def submit_inspection():
    data = request.get_json(force=True) or {}
    required = ['project_name', 'visit_date', 'department']
    missing = [f for f in required if not str(data.get(f) or '').strip()]
    if missing:
        return error_response(f'Missing: {", ".join(missing)}', status_code=400)

    dept = str(data.get('department')).strip().lower()
    if dept not in ('hvac', 'civil', 'cleaning'):
        return error_response('Invalid department', status_code=400)

    _, date_err = _parse_visit_date(data.get('visit_date'))
    if date_err:
        return error_response(date_err, status_code=400)

    uploads_dir = current_app.config.get('UPLOADS_DIR')
    items_in = data.get('items') or []
    if not items_in:
        return error_response('Add at least one inspection area with photos', status_code=400)

    items_out = []
    for row in items_in:
        if not isinstance(row, dict):
            continue
        photos = _upload_photo_list(row.get('photos') or [], 'qhsi_inspection_photos', uploads_dir)
        if not photos:
            continue
        items_out.append({
            'department': row.get('department') or dept,
            'trade': row.get('trade'),
            'system': row.get('system'),
            'equipment': row.get('equipment'),
            'area': row.get('area'),
            'zone': row.get('zone'),
            'description': (row.get('description') or '').strip(),
            'severity': row.get('severity') or 'observation',
            'photos': photos,
        })

    if not items_out:
        return error_response('Each item needs at least one photo', status_code=400)

    tech_sig = data.get('tech_signature') or ''
    tech_sig_file = None
    if tech_sig and str(tech_sig).startswith('data:image'):
        _, _, tech_sig_file = save_signature_dataurl(tech_sig, uploads_dir, 'tech_sig')

    user = _current_user()
    form_data = {
        'project_name': data.get('project_name'),
        'visit_date': data.get('visit_date'),
        'location': data.get('location'),
        'department': dept,
        'inspector_name': data.get('inspector_name') or (user.full_name if user else ''),
        'summary': data.get('summary'),
        'items': items_out,
        'tech_signature': tech_sig_file,
        'base_url': request.host_url.rstrip('/'),
        'created_at': utc_now_naive().isoformat(),
    }

    submission = create_submission_db(
        module_type='qhsi_inspection',
        form_data=form_data,
        site_name=data.get('project_name'),
        visit_date=data.get('visit_date'),
        user_id=user.id if user else None,
    )
    sub_id = submission.submission_id

    try:
        send_inspection_submitted(submission, user)
        notify_inspection_stage(submission, 'submitted')
    except Exception as e:
        logger.warning('QHSA inspection notify failed: %s', e)

    job = create_job_db(submission)
    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths()
    EXECUTOR.submit(process_job, sub_id, job.job_id, {}, current_app._get_current_object())

    return success_response({
        'submission_id': sub_id,
        'job_id': job.job_id,
        'message': 'QHSA inspection submitted — forwarded to Operations Manager.',
    })


# ─── Training CRUD ───────────────────────────────────────────────────────────

@qhsi_bp.route('/api/trainings', methods=['GET'])
@jwt_required()
@module_access_required('qhsi')
def list_trainings():
    status = (request.args.get('status') or '').strip()
    q = QhsiTraining.query.order_by(QhsiTraining.scheduled_at.asc())
    if status:
        q = q.filter_by(status=status)
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    if from_date:
        try:
            q = q.filter(QhsiTraining.scheduled_at >= datetime.strptime(from_date, '%Y-%m-%d'))
        except ValueError:
            pass
    if to_date:
        try:
            end = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)
            q = q.filter(QhsiTraining.scheduled_at < end)
        except ValueError:
            pass
    rows = q.limit(200).all()
    return jsonify({'success': True, 'trainings': [t.to_dict() for t in rows]})


@qhsi_bp.route('/api/trainings', methods=['POST'])
@jwt_required()
@module_access_required('qhsi')
def create_training():
    data = request.get_json(force=True) or {}
    required = ['project_name', 'title', 'scheduled_at']
    missing = [f for f in required if not str(data.get(f) or '').strip()]
    if missing:
        return error_response(f'Missing: {", ".join(missing)}', status_code=400)

    try:
        scheduled = datetime.fromisoformat(str(data['scheduled_at']).replace('Z', '+00:00'))
        if scheduled.tzinfo:
            scheduled = scheduled.replace(tzinfo=None)
    except ValueError:
        return error_response('Invalid scheduled_at datetime', status_code=400)

    user = _current_user()
    row = QhsiTraining(
        training_id=random_id('qtr'),
        project_name=str(data['project_name']).strip(),
        bd_project_id=data.get('bd_project_id') or None,
        title=str(data['title']).strip(),
        training_type=(data.get('training_type') or 'training').strip()[:30],
        scheduled_at=scheduled,
        duration_minutes=int(data.get('duration_minutes') or 60),
        location=(data.get('location') or '').strip() or None,
        facilitator_name=(data.get('facilitator_name') or '').strip() or None,
        facilitator_id=data.get('facilitator_id'),
        attendees=data.get('attendees') or [],
        status='scheduled',
        notes=(data.get('notes') or '').strip() or None,
        created_by_id=user.id if user else None,
    )
    db.session.add(row)
    db.session.commit()
    return success_response({'training': row.to_dict()}, status_code=201)


@qhsi_bp.route('/api/trainings/<training_id>', methods=['PATCH'])
@jwt_required()
@module_access_required('qhsi')
def update_training(training_id):
    row = QhsiTraining.query.filter_by(training_id=training_id).first()
    if not row:
        return error_response('Training not found', status_code=404)
    data = request.get_json(force=True) or {}
    for field in ('title', 'project_name', 'location', 'facilitator_name', 'notes', 'status', 'training_type'):
        if field in data:
            setattr(row, field, data[field])
    if 'scheduled_at' in data and data['scheduled_at']:
        try:
            scheduled = datetime.fromisoformat(str(data['scheduled_at']).replace('Z', '+00:00'))
            if scheduled.tzinfo:
                scheduled = scheduled.replace(tzinfo=None)
            row.scheduled_at = scheduled
        except ValueError:
            return error_response('Invalid scheduled_at', status_code=400)
    if 'duration_minutes' in data:
        row.duration_minutes = int(data['duration_minutes'] or 60)
    if 'attendees' in data:
        row.attendees = data['attendees']
    db.session.commit()
    return success_response({'training': row.to_dict()})


@qhsi_bp.route('/api/trainings/<training_id>', methods=['DELETE'])
@jwt_required()
@module_access_required('qhsi')
def delete_training(training_id):
    row = QhsiTraining.query.filter_by(training_id=training_id).first()
    if not row:
        return error_response('Training not found', status_code=404)
    db.session.delete(row)
    db.session.commit()
    return success_response({'deleted': training_id})
