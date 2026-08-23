"""Automations hub: daily HR Excel backup and future module jobs."""
from __future__ import annotations

import logging

from flask import Blueprint, render_template, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.automations.jobs import (
    ensure_seed_jobs,
    get_catalog_entry,
    JOB_CATALOG,
    resolve_recipients,
)
from app.automations.runner import run_job
from app.models import AutomationJob, AutomationRun, User, db
from common.error_responses import error_response, success_response

logger = logging.getLogger(__name__)

automations_bp = Blueprint('automations', __name__, template_folder='../../templates')


def _current_user() -> User | None:
    uid = get_jwt_identity()
    if uid is None:
        return None
    try:
        return db.session.get(User, int(uid))
    except (TypeError, ValueError):
        return None


def user_can_use_automations(user: User | None) -> bool:
    if not user:
        return False
    if user.role == 'admin':
        return True
    if getattr(user, 'access_hr', False):
        return True
    return False


def _require_user():
    user = _current_user()
    if not user:
        return None, error_response('User not found', status_code=404)
    if not user_can_use_automations(user):
        return None, error_response('Access denied to Automations', status_code=403)
    return user, None


def _job_payload(job: AutomationJob | None, spec: dict) -> dict:
    data = spec.copy()
    data['implemented'] = bool(spec.get('implemented'))
    if job:
        data.update(job.to_dict())
        data['resolved_recipients'] = resolve_recipients(job)
    else:
        data.update({
            'id': None,
            'enabled': False,
            'schedule_hour': int(spec.get('default_hour') or 20),
            'schedule_minute': int(spec.get('default_minute') or 0),
            'timezone': 'Asia/Dubai',
            'to_emails': '',
            'save_to_files': True,
            'send_email': True,
            'sync_drive': True,
            'last_run_at': None,
            'last_success_at': None,
            'last_error': '',
            'resolved_recipients': [],
        })
    return data


@automations_bp.route('/')
@jwt_required()
def automations_home():
    user, err = _require_user()
    if err:
        return err
    ensure_seed_jobs()
    return render_template('automations.html', user=user, active_page='automations')


@automations_bp.route('/api/jobs', methods=['GET'])
@jwt_required()
def api_list_jobs():
    user, err = _require_user()
    if err:
        return err
    ensure_seed_jobs()
    rows = {j.slug: j for j in AutomationJob.query.all()}
    jobs = [_job_payload(rows.get(spec['slug']), spec) for spec in JOB_CATALOG]
    recent = (
        AutomationRun.query.order_by(AutomationRun.started_at.desc())
        .limit(12)
        .all()
    )
    return success_response({
        'jobs': jobs,
        'runs': [r.to_dict() for r in recent],
    })


@automations_bp.route('/api/jobs/<slug>', methods=['PATCH'])
@jwt_required()
def api_patch_job(slug):
    user, err = _require_user()
    if err:
        return err
    spec = get_catalog_entry(slug)
    if not spec:
        return error_response('Unknown job', status_code=404)
    if not spec.get('implemented'):
        return error_response('This job is not available yet', status_code=400)
    ensure_seed_jobs()
    job = AutomationJob.query.filter_by(slug=slug).first()
    if not job:
        return error_response('Job not found', status_code=404)

    data = request.get_json(silent=True) or {}
    if 'enabled' in data:
        job.enabled = bool(data.get('enabled'))
    if 'save_to_files' in data:
        job.save_to_files = bool(data.get('save_to_files'))
    if 'send_email' in data:
        job.send_email = bool(data.get('send_email'))
    if 'sync_drive' in data:
        job.sync_drive = bool(data.get('sync_drive'))
    if 'to_emails' in data:
        job.to_emails = (data.get('to_emails') or '').strip() or None
    if 'schedule_hour' in data:
        try:
            hour = int(data.get('schedule_hour'))
        except (TypeError, ValueError):
            return error_response('Invalid schedule_hour', status_code=400)
        if hour < 0 or hour > 23:
            return error_response('schedule_hour must be 0–23', status_code=400)
        job.schedule_hour = hour
    if 'schedule_minute' in data:
        try:
            minute = int(data.get('schedule_minute'))
        except (TypeError, ValueError):
            return error_response('Invalid schedule_minute', status_code=400)
        if minute < 0 or minute > 59:
            return error_response('schedule_minute must be 0–59', status_code=400)
        job.schedule_minute = minute
    db.session.commit()

    try:
        from flask import current_app
        from app.automations.scheduler import refresh_cron_jobs
        refresh_cron_jobs(current_app._get_current_object())
    except Exception:
        logger.warning('Could not refresh Automations cron after patch', exc_info=True)

    return success_response({'job': _job_payload(job, spec)})


@automations_bp.route('/api/jobs/<slug>/run', methods=['POST'])
@jwt_required()
def api_run_job(slug):
    user, err = _require_user()
    if err:
        return err
    spec = get_catalog_entry(slug)
    if not spec:
        return error_response('Unknown job', status_code=404)
    if not spec.get('implemented'):
        return error_response('This job is not available yet', status_code=400)
    try:
        result = run_job(slug, trigger='manual', user_id=user.id)
    except ValueError as exc:
        return error_response(str(exc), status_code=400)
    except Exception:
        logger.exception('Manual automations run failed for %s', slug)
        return error_response('Backup failed', status_code=500)
    return success_response(result, message=result.get('message') or 'Run finished')
