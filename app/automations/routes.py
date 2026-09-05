"""Automations hub: daily Excel backups and linked Report Generation status."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.automations.jobs import (
    MMR_DAILY_EXCEL,
    allowed_module_ids,
    ensure_seed_jobs,
    get_catalog_entry,
    JOB_CATALOG,
    module_choices_for_spec,
    parse_module_list,
    resolve_recipients,
    selected_modules,
    serialize_modules,
)
from app.automations.run_record import (
    lookup_email_log,
    normalize_run_view,
    related_id_for_run,
)
from app.automations.runner import run_job
from app.models import AutomationJob, AutomationRun, User, db
from common.error_responses import error_response, success_response

logger = logging.getLogger(__name__)

automations_bp = Blueprint('automations', __name__, template_folder='../../templates')

RECENT_RUN_LIMIT = 12


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
    data['linked'] = bool(spec.get('linked'))
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
            'export_modules': '',
            'last_run_at': None,
            'last_success_at': None,
            'last_error': '',
            'resolved_recipients': [],
        })
    data['export_modules'] = selected_modules(data.get('export_modules'), spec)
    data['module_choices'] = module_choices_for_spec(spec)
    return data


def _run_payload(run: AutomationRun, *, with_email_log: bool = False) -> dict:
    log = None
    if with_email_log:
        email = ((run.detail or {}).get('email') or {})
        related_id = (email.get('related_id') or '').strip() or related_id_for_run(run.id)
        log = lookup_email_log(related_id)
    return normalize_run_view(run, email_log=log)


def _sent_at_iso(raw) -> str:
    text = str(raw or '').strip()
    if not text:
        return ''
    try:
        stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return text
    if stamp.tzinfo is None:
        from zoneinfo import ZoneInfo
        stamp = stamp.replace(tzinfo=ZoneInfo('Asia/Dubai'))
    return stamp.isoformat()


def _cycle_trigger(cycle: dict) -> str:
    sent_by = (cycle.get('sent_by') or '').strip().lower()
    return 'scheduler' if sent_by == 'scheduler' else 'manual'


def _linked_run_from_cycle(cycle: dict, spec: dict) -> dict:
    sent_at = _sent_at_iso(cycle.get('sent_at'))
    filename = (cycle.get('report_filename') or '').strip()
    cycle_id = cycle.get('cycle_id')
    trigger = _cycle_trigger(cycle)
    title = spec.get('title') or 'Report generated'
    slug = spec.get('slug') or MMR_DAILY_EXCEL
    return {
        'id': f'mmr-cycle-{cycle_id}',
        'job_id': None,
        'slug': slug,
        'trigger': trigger,
        'status': 'ok',
        'detail': {},
        'error_message': '',
        'started_at': sent_at,
        'finished_at': sent_at,
        'external': True,
        'view': {
            'job_title': title,
            'dubai_date': '',
            'files': (
                [{
                    'module': 'mmr',
                    'label': 'Report',
                    'item_id': None,
                    'filename': filename,
                    'folder': 'Report Generation',
                    'size_bytes': None,
                    'attached_to_email': True,
                    'drive': {},
                    'download_url': None,
                }]
                if filename else []
            ),
            'email': {
                'outcome': 'sent',
                'reason': None,
                'reason_label': '',
                'recipients': [],
                'subject': cycle.get('subject') or '',
                'attachment_names': [filename] if filename else [],
                'email_log_id': None,
                'related_id': filename,
                'sent': True,
                'skipped': False,
                'line': 'Sent from Report Generation',
                'note': '',
            },
            'warnings': [],
            'email_log': None,
        },
    }


def _parse_run_time(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value or '').strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def _recent_mmr_cycles(limit: int = RECENT_RUN_LIMIT) -> list[dict]:
    try:
        from module_mmr.routes import recent_sent_cycles
        return list(recent_sent_cycles(limit=limit) or [])
    except Exception:
        logger.warning('Could not load Report Generation cycles for Automations', exc_info=True)
        return []


def _unavailable_message(spec: dict) -> str:
    if spec.get('linked'):
        return 'This job is managed in Report Generation'
    return 'This job is not available yet'


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
    cycles = _recent_mmr_cycles(RECENT_RUN_LIMIT)
    mmr_spec = get_catalog_entry(MMR_DAILY_EXCEL) or {}
    jobs = []
    for spec in JOB_CATALOG:
        payload = _job_payload(rows.get(spec['slug']), spec)
        if spec.get('linked'):
            payload['linked'] = True
            payload['linked_url'] = spec.get('linked_url') or '/admin/mmr/'
            last = cycles[0] if cycles else None
            payload['linked_last_send'] = None
            if last:
                payload['linked_last_send'] = {
                    'sent_at': _sent_at_iso(last.get('sent_at')),
                    'filename': (last.get('report_filename') or '').strip(),
                    'trigger': _cycle_trigger(last),
                }
        jobs.append(payload)
    recent = (
        AutomationRun.query.order_by(AutomationRun.started_at.desc())
        .limit(RECENT_RUN_LIMIT)
        .all()
    )
    hub_runs = [_run_payload(r) for r in recent]
    linked_runs = [_linked_run_from_cycle(cycle, mmr_spec) for cycle in cycles]
    merged = sorted(
        hub_runs + linked_runs,
        key=lambda row: _parse_run_time(row.get('started_at')),
        reverse=True,
    )[:RECENT_RUN_LIMIT]
    return success_response({
        'jobs': jobs,
        'runs': merged,
    })


@automations_bp.route('/api/runs/<int:run_id>', methods=['GET'])
@jwt_required()
def api_get_run(run_id):
    user, err = _require_user()
    if err:
        return err
    run = db.session.get(AutomationRun, run_id)
    if not run:
        return error_response('Run not found', status_code=404)
    return success_response({'run': _run_payload(run, with_email_log=True)})


@automations_bp.route('/api/jobs/<slug>', methods=['PATCH'])
@jwt_required()
def api_patch_job(slug):
    user, err = _require_user()
    if err:
        return err
    spec = get_catalog_entry(slug)
    if not spec:
        return error_response('Unknown job', status_code=404)
    if spec.get('linked') or not spec.get('implemented'):
        return error_response(_unavailable_message(spec), status_code=400)
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
    if 'export_modules' in data:
        choices = module_choices_for_spec(spec)
        if len(choices) >= 2:
            allowed = set(allowed_module_ids(spec))
            picked = [mid for mid in parse_module_list(data.get('export_modules')) if mid in allowed]
            if not picked:
                return error_response('Pick at least one module', status_code=400)
            if set(picked) == set(row['id'] for row in choices):
                job.export_modules = None
            else:
                job.export_modules = serialize_modules(picked)
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
    if spec.get('linked') or not spec.get('implemented'):
        return error_response(_unavailable_message(spec), status_code=400)
    try:
        result = run_job(slug, trigger='manual', user_id=user.id)
    except ValueError as exc:
        return error_response(str(exc), status_code=400)
    except Exception:
        logger.exception('Manual automations run failed for %s', slug)
        return error_response('Backup failed', status_code=500)
    return success_response(result, message=result.get('message') or 'Run finished')
