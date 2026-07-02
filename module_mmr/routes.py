"""
Email Automation Blueprint.
URL prefix: /admin/mmr  (kept for backward-compatible nav/permission wiring)
Requires JWT plus admin role or User.access_report_generation.

Users create free-form recurring emails (recipients + subject + body + attachments)
that run on a schedule (daily / weekly / monthly / quarterly / every-N interval).
"""
import logging
from functools import wraps

from flask import (Blueprint, request, jsonify, render_template,
                   current_app)
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import (db, User, EmailAutomation, EmailAutomationAttachment,
                        EmailAutomationDefaults)

logger = logging.getLogger(__name__)

mmr_bp = Blueprint('mmr_bp', __name__, url_prefix='/admin/mmr',
                   template_folder='templates')

ALLOWED_DOMAIN = 'injaaz.ae'
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB per file
_VALID_SCHEDULE_TYPES = {'daily', 'weekly', 'monthly', 'quarterly', 'interval'}
_VALID_INTERVAL_UNITS = {'days', 'weeks', 'months'}


def mmr_jwt_and_report_access(fn):
    """JWT + Email Automation access (admins always allowed)."""
    @wraps(fn)
    @jwt_required()
    def wrapped(*args, **kwargs):
        uid = get_jwt_identity()
        try:
            user = User.query.get(int(uid)) if uid is not None else None
        except (TypeError, ValueError):
            user = None
        if not user or not user.is_active:
            if request.path.startswith('/admin/mmr/api'):
                return jsonify({'error': 'Unauthorized'}), 401
            return render_template(
                'access_denied.html',
                module='Email Automation',
                message='You must be signed in to use Email Automation.',
            ), 403
        if user.role != 'admin' and not getattr(user, 'access_report_generation', False):
            if request.path.startswith('/admin/mmr/api'):
                return jsonify({'error': 'You do not have access to Email Automation.'}), 403
            return render_template(
                'access_denied.html',
                module='Email Automation',
                message='You do not have access to Email Automation. Please contact an administrator.',
            ), 403
        return fn(*args, **kwargs)
    return wrapped


def _validate_injaaz_emails(raw: str) -> tuple[list[str], str | None]:
    """Parse a comma-separated email list and enforce the @injaaz.ae domain."""
    if not raw or not raw.strip():
        return [], None
    emails = [e.strip() for e in raw.split(',') if e.strip()]
    bad = [e for e in emails if not e.lower().endswith(f'@{ALLOWED_DOMAIN}')]
    if bad:
        return [], (
            f"Only @{ALLOWED_DOMAIN} addresses are allowed. Invalid: {', '.join(bad)}"
        )
    return emails, None


def _current_scheduler_app():
    """The Flask app object to hand the scheduler (jobs run outside request ctx)."""
    return current_app._get_current_object()


def _sync_job(automation):
    try:
        from .scheduler import sync_automation_job
        sync_automation_job(automation, _current_scheduler_app())
    except Exception:
        logger.exception('Failed to sync scheduler job for automation %s', automation.id)


def _remove_job(automation_id):
    try:
        from .scheduler import remove_automation_job
        remove_automation_job(automation_id, _current_scheduler_app())
    except Exception:
        logger.exception('Failed to remove scheduler job for automation %s', automation_id)


def _with_next_run(automation, include_body=False):
    """to_dict() enriched with the APScheduler next fire time (next_run_at)."""
    d = automation.to_dict(include_body=include_body)
    try:
        from .scheduler import get_next_run_iso
        d['next_run_at'] = get_next_run_iso(automation.id)
    except Exception:
        d['next_run_at'] = None
    return d


# ──────────────────────────────────────────────────────────────────────────────
# Field parsing / validation
# ──────────────────────────────────────────────────────────────────────────────

def _clamp(val, lo, hi, default):
    try:
        return max(lo, min(hi, int(val)))
    except (TypeError, ValueError):
        return default


def _apply_payload(automation, data) -> str | None:
    """Apply a create/update payload to an automation row. Returns an error message or None."""
    name = (data.get('name') or '').strip()
    if not name:
        return 'Name is required.'

    to_list, err = _validate_injaaz_emails(data.get('to_emails') or '')
    if err:
        return err
    if not to_list:
        return 'At least one recipient (To) is required.'
    cc_list, err = _validate_injaaz_emails(data.get('cc_emails') or '')
    if err:
        return err

    st = (data.get('schedule_type') or 'daily').strip().lower()
    if st not in _VALID_SCHEDULE_TYPES:
        return f"schedule_type must be one of {', '.join(sorted(_VALID_SCHEDULE_TYPES))}."

    automation.name = name[:160]
    automation.to_emails = ', '.join(to_list)
    automation.cc_emails = ', '.join(cc_list)
    automation.subject = (data.get('subject') or '').strip()[:300]
    automation.body = data.get('body') or ''
    automation.schedule_type = st
    automation.hour = _clamp(data.get('hour'), 0, 23, 10)
    automation.minute = _clamp(data.get('minute'), 0, 59, 0)
    automation.weekday = _clamp(data.get('weekday'), 0, 6, 0)
    automation.day_of_month = _clamp(data.get('day_of_month'), 1, 28, 1)
    automation.quarter_start_month = _clamp(data.get('quarter_start_month'), 1, 12, 1)

    unit = (data.get('interval_unit') or 'days').strip().lower()
    automation.interval_unit = unit if unit in _VALID_INTERVAL_UNITS else 'days'
    automation.interval_n = _clamp(data.get('interval_n'), 1, 365, 1)

    if 'enabled' in data:
        automation.enabled = bool(data.get('enabled'))
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Page
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/')
@mmr_jwt_and_report_access
def dashboard():
    return render_template('mmr_dashboard.html', active_page='report')


# ──────────────────────────────────────────────────────────────────────────────
# Default email settings (global, single row)
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/defaults', methods=['GET'])
@mmr_jwt_and_report_access
def get_defaults():
    row = EmailAutomationDefaults.query.first()
    defaults = row.to_dict() if row else {'to_emails': '', 'cc_emails': ''}
    return jsonify({'defaults': defaults})


@mmr_bp.route('/api/defaults', methods=['PUT'])
@mmr_jwt_and_report_access
def save_defaults():
    data = request.get_json(silent=True) or {}
    to_list, err = _validate_injaaz_emails(data.get('to_emails') or '')
    if err:
        return jsonify({'error': err}), 400
    cc_list, err = _validate_injaaz_emails(data.get('cc_emails') or '')
    if err:
        return jsonify({'error': err}), 400

    row = EmailAutomationDefaults.query.first()
    if not row:
        row = EmailAutomationDefaults()
        db.session.add(row)
    row.to_emails = ', '.join(to_list)
    row.cc_emails = ', '.join(cc_list)
    db.session.commit()
    return jsonify({'defaults': row.to_dict()})


# ──────────────────────────────────────────────────────────────────────────────
# Automation CRUD
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/automations', methods=['GET'])
@mmr_jwt_and_report_access
def list_automations():
    rows = EmailAutomation.query.order_by(EmailAutomation.created_at.desc()).all()
    return jsonify({'automations': [_with_next_run(r) for r in rows]})


@mmr_bp.route('/api/automations', methods=['POST'])
@mmr_jwt_and_report_access
def create_automation():
    data = request.get_json(silent=True) or {}
    automation = EmailAutomation()
    err = _apply_payload(automation, data)
    if err:
        return jsonify({'error': err}), 400
    try:
        automation.created_by = int(get_jwt_identity())
    except (TypeError, ValueError):
        automation.created_by = None
    db.session.add(automation)
    db.session.commit()
    _sync_job(automation)
    return jsonify({'automation': _with_next_run(automation, include_body=True)}), 201


@mmr_bp.route('/api/automations/<int:aid>', methods=['GET'])
@mmr_jwt_and_report_access
def get_automation(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    return jsonify({'automation': _with_next_run(automation, include_body=True)})


@mmr_bp.route('/api/automations/<int:aid>', methods=['PUT'])
@mmr_jwt_and_report_access
def update_automation(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    data = request.get_json(silent=True) or {}
    err = _apply_payload(automation, data)
    if err:
        return jsonify({'error': err}), 400
    db.session.commit()
    _sync_job(automation)
    return jsonify({'automation': _with_next_run(automation, include_body=True)})


@mmr_bp.route('/api/automations/<int:aid>', methods=['DELETE'])
@mmr_jwt_and_report_access
def delete_automation(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    db.session.delete(automation)
    db.session.commit()
    _remove_job(aid)
    return jsonify({'ok': True})


@mmr_bp.route('/api/automations/<int:aid>/toggle', methods=['POST'])
@mmr_jwt_and_report_access
def toggle_automation(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    automation.enabled = not automation.enabled
    db.session.commit()
    _sync_job(automation)
    return jsonify({'automation': _with_next_run(automation)})


@mmr_bp.route('/api/automations/<int:aid>/run-now', methods=['POST'])
@mmr_jwt_and_report_access
def run_automation_now(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    try:
        from .scheduler import run_automation_now as _run
        _run(aid, _current_scheduler_app())
    except Exception as exc:
        logger.exception('Manual run failed for automation %s', aid)
        return jsonify({'error': f'Run failed: {exc}'}), 500
    db.session.refresh(automation)
    return jsonify({'automation': _with_next_run(automation)})


@mmr_bp.route('/api/automations/<int:aid>/logs', methods=['GET'])
@mmr_jwt_and_report_access
def list_automation_logs(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    limit = _clamp(request.args.get('limit'), 1, 100, 50)
    offset = _clamp(request.args.get('offset'), 0, 10000, 0)
    logs = automation.run_logs.offset(offset).limit(limit).all()
    return jsonify({
        'logs': [l.to_dict() for l in logs],
        'total': automation.run_logs.count(),
    })


# ──────────────────────────────────────────────────────────────────────────────
# Attachments
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/automations/<int:aid>/attachments', methods=['POST'])
@mmr_jwt_and_report_access
def add_attachment(aid):
    automation = EmailAutomation.query.get(aid)
    if not automation:
        return jsonify({'error': 'Automation not found'}), 404
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    data = f.read()
    if len(data) > _MAX_ATTACHMENT_BYTES:
        return jsonify({'error': 'File too large (max 10 MB)'}), 400
    att = EmailAutomationAttachment(
        automation_id=automation.id,
        filename=(f.filename or 'attachment')[:255],
        mime_type=(f.mimetype or 'application/octet-stream')[:120],
        content=data,
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({
        'attachment': {'id': att.id, 'filename': att.filename, 'mime_type': att.mime_type}
    }), 201


@mmr_bp.route('/api/automations/<int:aid>/attachments/<int:att_id>', methods=['DELETE'])
@mmr_jwt_and_report_access
def delete_attachment(aid, att_id):
    att = EmailAutomationAttachment.query.filter_by(id=att_id, automation_id=aid).first()
    if not att:
        return jsonify({'error': 'Attachment not found'}), 404
    db.session.delete(att)
    db.session.commit()
    return jsonify({'ok': True})
