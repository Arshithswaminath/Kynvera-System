"""
MMR Blueprint – Report Generation (MMR hub).
URL prefix: /admin/mmr
Requires JWT plus admin role or User.access_report_generation.
"""
import os
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import BytesIO

from flask import (Blueprint, request, jsonify, render_template,
                   current_app, send_file)
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import User

logger = logging.getLogger(__name__)

mmr_bp = Blueprint('mmr_bp', __name__, url_prefix='/admin/mmr',
                   template_folder='templates')


def mmr_jwt_and_report_access(fn):
    """JWT + Report Generation module access (admins always allowed)."""
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
                module='Report Generation',
                message='You must be signed in to use Report Generation.',
            ), 403
        if user.role != 'admin' and not getattr(user, 'access_report_generation', False):
            if request.path.startswith('/admin/mmr/api'):
                return jsonify({'error': 'You do not have access to Report Generation.'}), 403
            return render_template(
                'access_denied.html',
                module='Report Generation',
                message='You do not have access to Report Generation. Please contact an administrator.',
            ), 403
        return fn(*args, **kwargs)
    return wrapped


ALLOWED_DOMAIN = 'injaaz.ae'


def _validate_injaaz_emails(raw: str) -> tuple[list[str], str | None]:
    """
    Parse a comma-separated list of emails and enforce @injaaz.ae domain.

    Returns:
        (valid_list, error_message)  – error_message is None when all pass.
    """
    if not raw or not raw.strip():
        return [], None
    emails = [e.strip() for e in raw.split(',') if e.strip()]
    bad = [e for e in emails if not e.lower().endswith(f'@{ALLOWED_DOMAIN}')]
    if bad:
        quoted = ', '.join(bad)
        return [], (
            f"Only @{ALLOWED_DOMAIN} addresses are allowed. "
            f"Invalid: {quoted}"
        )
    return emails, None

_CONFIG_FILE    = 'mmr_email_config.json'
_UPLOAD_FILE    = 'mmr_latest.xlsx'
_CYCLE_LOG_FILE = 'mmr_cycle_log.json'
_ACTIVITY_FILE = 'mmr_automation_activity.json'
_ACTIVITY_MAX_ENTRIES = 100

_DEFAULT_CONFIG = {
    'to': 'dennis@injaaz.ae, shakeel@injaaz.ae, araki@injaaz.ae, abbas@injaaz.ae, a.mohammed@injaaz.ae',
    'cc': 'taha@injaaz.ae, george@injaaz.ae, arshith@injaaz.ae, eslam@injaaz.ae, alaa@injaaz.ae, mona@injaaz.ae, siraj@injaaz.ae, jismon@injaaz.ae, ousman@injaaz.ae',
    'subject': 'Daily Report on Resolved and Pending Complaints for {{REPORT_DATE}}',
    'body': (
        'Dear FM Team,\n\n'
        'Please find below comprehensive Daily Report of ({{REPORT_DATE}}) '
        'generated from our CAFM system / Injaaz Application for all Pending & Resolved work orders.\n\n'
        'Regards,\n'
        'CAFM Team'
    ),
    # daily | monthly — affects default subject/body templates, Excel attachment name, and saved downloads
    'report_format': 'daily',
    'schedule_enabled': False,
    'schedule_hour': 10,
    'schedule_minute': 0,
    'schedule_paused': False,
    # After a successful send while automation is on: true until a new Excel is uploaded.
    'automation_waiting_for_fresh_upload': False,
}

_MONTHLY_SUBJECT_DEFAULT = 'Monthly Report on Resolved and Pending Complaints for {{REPORT_DATE}}'
_MONTHLY_BODY_DEFAULT = (
    'Dear FM Team,\n\n'
    'Please find below comprehensive Monthly Report of ({{REPORT_DATE}}) '
    'generated from our CAFM system / Injaaz Application for all Pending & Resolved work orders.\n\n'
    'Regards,\n'
    'CAFM Team'
)


def _email_presets() -> dict:
    """Canonical Daily vs Monthly subject/body for UI and switching."""
    return {
        'daily': {
            'subject': _DEFAULT_CONFIG['subject'],
            'body': _DEFAULT_CONFIG['body'],
            'to': _DEFAULT_CONFIG['to'],
            'cc': _DEFAULT_CONFIG['cc'],
        },
        'monthly': {
            'subject': _MONTHLY_SUBJECT_DEFAULT,
            'body': _MONTHLY_BODY_DEFAULT,
            'to': _DEFAULT_CONFIG['to'],
            'cc': _DEFAULT_CONFIG['cc'],
        },
    }


def _email_presets_resolved(cfg: dict) -> dict:
    """Daily/monthly presets including saved To/CC per format."""
    out = _email_presets()
    fr = cfg.get('format_recipients')
    if not isinstance(fr, dict):
        fr = {}
    legacy_to = (cfg.get('to') or '').strip()
    legacy_cc = (cfg.get('cc') or '').strip()
    fr_has_data = False
    for fmt in ('daily', 'monthly'):
        block = fr.get(fmt) if isinstance(fr.get(fmt), dict) else {}
        if (block.get('to') or '').strip() or (block.get('cc') or '').strip():
            fr_has_data = True
            break
    for fmt in ('daily', 'monthly'):
        block = fr.get(fmt) if isinstance(fr.get(fmt), dict) else {}
        to_val = (block.get('to') or '').strip()
        cc_val = (block.get('cc') or '').strip()
        if not fr_has_data:
            if legacy_to:
                to_val = legacy_to
            if legacy_cc:
                cc_val = legacy_cc
        out[fmt]['to'] = to_val or out[fmt]['to']
        out[fmt]['cc'] = cc_val or out[fmt]['cc']
    return out


_PRESET_NAME_MAX_LEN = 40


def _normalize_preset_key(name: str) -> str | None:
    """Slug for custom preset storage; None if invalid."""
    raw = (name or '').strip()
    if not raw or len(raw) > _PRESET_NAME_MAX_LEN:
        return None
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _\-]*', raw):
        return None
    return raw.lower().replace(' ', '_')


def _custom_presets_list(config: dict) -> list[dict]:
    """Saved custom To/CC/subject/body presets, sorted by display name."""
    raw = config.get('custom_presets') or {}
    if not isinstance(raw, dict):
        return []
    out = []
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        display = (val.get('name') or key or '').strip()
        if not display:
            continue
        rf = str(val.get('report_format', 'daily')).strip().lower()
        out.append({
            'key': key,
            'name': display,
            'to': val.get('to', '') or '',
            'cc': val.get('cc', '') or '',
            'subject': val.get('subject', '') or '',
            'body': val.get('body', '') or '',
            'report_format': rf if rf in ('daily', 'monthly') else 'daily',
        })
    out.sort(key=lambda p: p['name'].lower())
    return out

_REPORT_DATE_PLACEHOLDER = '{{REPORT_DATE}}'


def _format_report_date(dt: datetime) -> str:
    """Format as '28th of February 2026' (previous day's date for report)."""
    d = dt.day
    suffix = 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
    return f"{d}{suffix} of {dt.strftime('%B %Y')}"


def _format_report_date_range_str(date_range: tuple | None) -> str | None:
    """Format date range for filename: 1 date=single, 2 dates=date1 & date2, 3+=date1 - date2."""
    if not date_range or len(date_range) < 2:
        return None
    min_d, max_d = date_range[0], date_range[1]
    n_unique = date_range[2] if len(date_range) >= 3 else 1
    if not min_d or not max_d:
        return None
    s1, s2 = _format_report_date(min_d), _format_report_date(max_d)
    if n_unique == 1 or min_d.date() == max_d.date():
        return s1
    if n_unique == 2:
        return f"{s1} & {s2}"
    return f"{s1} - {s2}"


def _report_filename(report_date: datetime | None = None, report_date_range: tuple | None = None,
                     upload_path: str | None = None, report_format: str | None = None) -> str:
    """Excel filename based on report date(s).
    1 date: single date | 2 dates: date1 & date2 | 3+ dates: date1 - date2"""
    kind = (report_format or 'daily').strip().lower()
    if kind == 'monthly':
        prefix = 'Monthly Report on Resolved and Pending Complaints for'
    else:
        prefix = 'Daily Report on Resolved and Pending Complaints for'
    date_str = _format_report_date_range_str(report_date_range) if report_date_range else None
    if date_str is None:
        dt = report_date
        if dt is None and upload_path and os.path.exists(upload_path):
            from .mmr_service import get_report_date_from_excel
            dt = get_report_date_from_excel(upload_path)
        if dt is None:
            dt = datetime.now() - timedelta(days=1)
        date_str = _format_report_date(dt)
    return f"{prefix} {date_str}.xlsx"


def _resolve_report_format(explicit: str | None) -> str:
    """Prefer explicit daily|monthly from query/body; else saved mmr_email_config.json."""
    if explicit is not None and str(explicit).strip() != '':
        v = str(explicit).strip().lower()
        if v in ('daily', 'monthly'):
            return v
    v = str(_load_config().get('report_format', 'daily')).strip().lower()
    return v if v in ('daily', 'monthly') else 'daily'


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers (stored in GENERATED_DIR as a JSON file)
# ──────────────────────────────────────────────────────────────────────────────

def _config_path():
    return os.path.join(current_app.config['GENERATED_DIR'], _CONFIG_FILE)

def _upload_path():
    return os.path.join(current_app.config['GENERATED_DIR'], _UPLOAD_FILE)


def _safe_report_folder_path(filename: str | None) -> str | None:
    """Return absolute path for a basename in the reports folder, or None if invalid."""
    fn = (filename or '').strip()
    if not fn or '..' in fn or '/' in fn or '\\' in fn:
        return None
    path = os.path.join(_reports_folder(), fn)
    if os.path.exists(path) and os.path.isfile(path):
        return path
    return None


def _dashboard_payload_from_path(path: str) -> tuple[dict, list]:
    """Parse a saved CAFM upload into dashboard aggregates and row dicts (same shaping as POST upload)."""
    from .mmr_service import (
        parse_excel,
        compute_dashboard,
        df_to_rows,
        _resolve_chargeable,
        get_mmr_chargeable_config,
        _project_blob_from_row_dict,
        _complaint_from_row_dict,
    )
    df = parse_excel(path)
    dashboard_data = compute_dashboard(df)
    rows = df_to_rows(df)
    cfg = get_mmr_chargeable_config()
    for r in rows:
        r['Space'] = _resolve_chargeable(
            r.get('Space', ''), r.get('BaseUnit', ''), r.get('Client', ''),
            r.get('Service Group', ''), r.get('Contract', ''),
            r.get('Work Description', ''), r.get('Specific Area', ''),
            cfg,
            _project_blob_from_row_dict(r),
            '',
            _complaint_from_row_dict(r),
        )
    return dashboard_data, rows


def _reports_folder():
    """Folder for saved reports (sent via email or Save to Folder)."""
    folder = os.path.join(current_app.config['GENERATED_DIR'], 'mmr_reports')
    os.makedirs(folder, exist_ok=True)
    return folder


# TrueNAS: web UI (TrueNAS ID / management URL). Override with TRUENAS_UI_URL.
_TRUENAS_UI_URL = (os.environ.get('TRUENAS_UI_URL') or 'http://172.25.70.143/').rstrip('/') + '/'
# SMB host for Save to Drive (same appliance as UI). Override full paths via TRUENAS_CAFM_PATH etc., or TRUENAS_HOST only.
_TRUENAS_HOST = os.environ.get('TRUENAS_HOST', '172.25.70.143')
_TRUENAS_CAFM_PATH = os.environ.get('TRUENAS_CAFM_PATH') or rf'\\{_TRUENAS_HOST}\Injaaz\CAFM\Daily Generated Report'
_SAVE_TO_DRIVE_GENERAL_PATH = os.environ.get('MMR_SAVE_DRIVE_GENERAL_PATH') or rf'\\{_TRUENAS_HOST}\Injaaz\General\CAFM\Daily Generated Report'
# Email report save location (set MMR_EMAIL_SAVE_PATH in .env to override)
_EMAIL_REPORT_SAVE_PATH = os.environ.get('MMR_EMAIL_SAVE_PATH') or rf'\\{_TRUENAS_HOST}\Injaaz\General\CAFM'


def _save_report_to_folder(report_bytes: bytes, base_filename: str, suffix: str = '',
                          filters: dict | None = None) -> str | None:
    """Save report to folder. Filename uses only reported date(s), no save timestamp.
    Optionally save filter state to restore dashboard. Returns saved filename or None."""
    try:
        folder = _reports_folder()
        base = base_filename.replace('.xlsx', '') if base_filename.endswith('.xlsx') else base_filename
        name = base + '.xlsx'
        path = os.path.join(folder, name)
        n = 1
        while os.path.exists(path):
            n += 1
            name = f"{base} ({n}).xlsx"
            path = os.path.join(folder, name)
        with open(path, 'wb') as f:
            f.write(report_bytes)
        # Save filter state for restoring dashboard when opening report
        if filters is not None:
            filters_path = path.replace('.xlsx', '_filters.json')
            with open(filters_path, 'w') as f:
                json.dump(filters, f, indent=2)
        return name
    except Exception as e:
        logger.warning(f'MMR save to folder failed: {e}')
        return None


def _save_email_report_to_network(report_bytes: bytes, base_filename: str) -> None:
    """Save email report to General CAFM path on TrueNAS (see _EMAIL_REPORT_SAVE_PATH). Best-effort, logs on failure.
    Filename uses only reported date(s), no save timestamp."""
    try:
        name = base_filename if base_filename.endswith('.xlsx') else base_filename + '.xlsx'
        path, err, saved_locally = _save_report_to_drive(report_bytes, name, save_path=_EMAIL_REPORT_SAVE_PATH)
        if path and not saved_locally:
            logger.info(f'MMR email report saved to network: {path}')
        elif path and saved_locally:
            logger.warning(f'MMR email report: network unavailable, saved locally: {path}')
        elif err:
            logger.warning(f'MMR email report save to {_EMAIL_REPORT_SAVE_PATH} failed: {err}')
    except Exception as e:
        logger.warning(f'MMR save email report to network failed: {e}')


def _save_report_to_drive(report_bytes: bytes, filename: str, save_path: str | None = None) -> tuple[str | None, str | None, bool]:
    """Save report to given path or default TrueNAS path. Returns (full_path, None) on success or (None, error_message) on failure."""
    base = (save_path or '').strip() or _TRUENAS_CAFM_PATH
    # Normalize path for Windows UNC (avoid double backslashes)
    base = os.path.normpath(base)
    try:
        # Create target directory if it doesn't exist
        if not os.path.exists(base):
            try:
                os.makedirs(base, exist_ok=True)
            except OSError as e:
                return None, f'Cannot create folder {base}. {e}'
        path = os.path.join(base, filename)
        with open(path, 'wb') as f:
            f.write(report_bytes)
        logger.info(f'MMR report saved to network: {path}')
        return path, None, False
    except PermissionError as e:
        logger.warning(f'MMR save to drive permission error ({base}): {e}')
        return None, 'Permission denied. Check TrueNAS share permissions.', False
    except OSError as e:
        logger.warning(f'MMR save to drive failed: {e}')
        err = str(e)
        # Fallback: save to local report folder if network drive fails
        try:
            local_name = _save_report_to_folder(report_bytes, filename, 'drive_fallback')
            if local_name:
                local_path = os.path.join(_reports_folder(), local_name)
                logger.warning(f'MMR save to drive failed ({base}): {err}. Fallback: saved locally to {local_path}')
                return local_path, None, True  # Success, saved locally
        except Exception:
            pass
        if 'cannot find' in err.lower() or 'no such file' in err.lower() or 'network' in err.lower():
            return None, f'Cannot reach TrueNAS ({_TRUENAS_UI_URL}). Ensure {base} is accessible. ({err})', False
        return None, err, False
    except Exception as e:
        logger.warning(f'MMR save to drive failed ({base}): {e}')
        # Fallback to local
        try:
            local_name = _save_report_to_folder(report_bytes, filename, 'drive_fallback')
            if local_name:
                local_path = os.path.join(_reports_folder(), local_name)
                logger.warning(f'MMR drive fallback: saved locally to {local_path}')
                return local_path, None, True
        except Exception:
            pass
        return None, str(e), False

def _env_schedule_override() -> dict:
    """Schedule fields from env (Render/PaaS: survives redeploys when JSON on ephemeral disk is wiped)."""
    out = {}
    raw = os.environ.get('MMR_SCHEDULE_ENABLED')
    if raw is not None and str(raw).strip() != '':
        out['schedule_enabled'] = str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
    h = os.environ.get('MMR_SCHEDULE_HOUR', '').strip()
    if h.isdigit():
        out['schedule_hour'] = max(0, min(23, int(h)))
    m = os.environ.get('MMR_SCHEDULE_MINUTE', '').strip()
    if m.isdigit():
        out['schedule_minute'] = max(0, min(59, int(m)))
    return out


def _load_config() -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    try:
        p = _config_path()
        if os.path.exists(p):
            with open(p) as f:
                cfg = {**cfg, **json.load(f)}
    except Exception:
        pass
    # Env wins for schedule keys when set (ops can pin automation on cloud without persistent disk)
    cfg.update(_env_schedule_override())
    return cfg

def _save_config(config: dict):
    with open(_config_path(), 'w') as f:
        json.dump(config, f, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Cycle log helpers  (stored as mmr_cycle_log.json next to the config)
# ──────────────────────────────────────────────────────────────────────────────

def _cycle_log_path():
    return os.path.join(current_app.config['GENERATED_DIR'], _CYCLE_LOG_FILE)


def _activity_log_path():
    return os.path.join(current_app.config['GENERATED_DIR'], _ACTIVITY_FILE)


def _load_activity_log() -> dict:
    empty = {'next_id': 1, 'entries': []}
    try:
        p = _activity_log_path()
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data.get('entries'), list):
                return {'next_id': max(1, int(data.get('next_id', 1))), 'entries': data['entries']}
    except Exception:
        pass
    return dict(empty)


def append_automation_activity(
    event_type: str,
    message: str,
    detail: str | None = None,
    *,
    meta: dict | None = None,
) -> None:
    """Append one timeline row for the MMR automation UI (best-effort, never raises)."""
    try:
        log = _load_activity_log()
        eid = int(log.get('next_id', 1))
        entry = {
            'id': eid,
            'ts': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'type': event_type,
            'message': (message or '')[:500],
            'detail': (detail[:1000] if detail else None),
            'meta': meta if isinstance(meta, dict) else {},
        }
        log['next_id'] = eid + 1
        entries = log.get('entries', [])
        entries.insert(0, entry)
        log['entries'] = entries[:_ACTIVITY_MAX_ENTRIES]
        with open(_activity_log_path(), 'w', encoding='utf-8') as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        logger.warning('MMR automation activity log failed: %s', e)


def _get_caller_identity() -> str:
    """Safely extract a username string from the current JWT identity."""
    try:
        identity = get_jwt_identity()
        if isinstance(identity, str):
            return identity
        if isinstance(identity, dict):
            return identity.get('username') or identity.get('sub') or 'admin'
        return str(identity) or 'admin'
    except Exception:
        return 'admin'


def _load_cycle_log() -> dict:
    default = {'current': None, 'history': [], 'next_cycle_id': 1}
    try:
        p = _cycle_log_path()
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return dict(default)
            # Legacy: older builds left current=cycle with status sent — archive to history
            cur = data.get('current')
            if isinstance(cur, dict) and cur.get('status') == 'sent':
                hist = data.get('history', [])
                if not isinstance(hist, list):
                    hist = []
                hist.insert(0, cur)
                data['history'] = hist[:50]
                data['current'] = None
                try:
                    with open(p, 'w', encoding='utf-8') as wf:
                        json.dump(data, wf, indent=2)
                except Exception:
                    pass
            return data
    except Exception:
        pass
    return dict(default)


def _save_cycle_log(log: dict):
    try:
        with open(_cycle_log_path(), 'w') as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        logger.warning(f'MMR cycle log save failed: {e}')


def _start_new_cycle(uploaded_by: str = 'admin') -> dict:
    """Begin a fresh dispatch cycle. Pushes any existing current cycle to history."""
    log = _load_cycle_log()
    current = log.get('current')
    if current and current.get('upload_at'):
        history = log.get('history', [])
        history.insert(0, current)
        log['history'] = history[:50]
    cycle_id = int(log.get('next_cycle_id', 1))
    log['next_cycle_id'] = cycle_id + 1
    log['current'] = {
        'cycle_id': cycle_id,
        'upload_at': datetime.now().isoformat(),
        'upload_by': uploaded_by,
        'approved_at': None,
        'approved_by': None,
        'sent_at': None,
        'sent_by': None,
        'recipient_count': 0,
        'subject': '',
        'report_filename': '',
        'status': 'uploaded',
    }
    _save_cycle_log(log)
    return log['current']


# How long an uploaded-but-unapproved cycle is allowed to sit before the
# automation auto-stops and a fresh upload is required. 30 minutes per spec.
_CYCLE_APPROVAL_TIMEOUT_SECONDS = 30 * 60


def _current_cycle_status() -> dict | None:
    """Return the current (in-flight) cycle dict, or None."""
    try:
        return (_load_cycle_log() or {}).get('current')
    except Exception:
        return None


def _is_current_cycle_approved() -> bool:
    """True only when the in-flight cycle has been reviewed/approved."""
    cur = _current_cycle_status()
    return bool(cur and cur.get('status') == 'approved' and cur.get('approved_at'))


def auto_stop_stale_cycle(reason_extra: str = '') -> bool:
    """If the current cycle is uploaded but not approved within the timeout,
    stop the automation (disable schedule) and require a fresh upload.

    Returns True when a stop was performed.
    """
    cur = _current_cycle_status()
    if not cur or cur.get('status') != 'uploaded':
        return False
    upload_at_raw = cur.get('upload_at')
    if not upload_at_raw:
        return False
    try:
        upload_at = datetime.fromisoformat(upload_at_raw)
    except (TypeError, ValueError):
        return False
    age = (datetime.now() - upload_at).total_seconds()
    if age < _CYCLE_APPROVAL_TIMEOUT_SECONDS:
        return False

    config = _load_config()
    config['schedule_enabled'] = False
    config['schedule_paused'] = True
    config['automation_waiting_for_fresh_upload'] = True
    _save_config(config)
    try:
        from .scheduler import update_schedule
        update_schedule(config, current_app._get_current_object())
    except Exception:
        pass

    cid = cur.get('cycle_id')
    meta: dict = {'reason': 'approval_timeout', 'timeout_minutes': _CYCLE_APPROVAL_TIMEOUT_SECONDS // 60}
    try:
        if cid is not None:
            meta['cycle_id'] = int(cid)
    except (TypeError, ValueError):
        pass
    detail = (
        f'Cycle was uploaded but not approved within {_CYCLE_APPROVAL_TIMEOUT_SECONDS // 60} minutes. '
        f'Automation has been stopped — upload a new Excel and re-enable the schedule to send again.'
    )
    if reason_extra:
        detail = f'{detail} ({reason_extra})'
    append_automation_activity(
        'auto_stopped',
        'Automation auto-stopped — approval timeout',
        detail,
        meta=meta,
    )
    return True


def _approve_current_cycle(approved_by: str = 'admin') -> bool:
    """Mark current cycle as reviewed. Returns False if nothing to approve."""
    log = _load_cycle_log()
    current = log.get('current')
    if not current or current.get('status') != 'uploaded':
        return False
    current['approved_at'] = datetime.now().isoformat()
    current['approved_by'] = approved_by
    current['status'] = 'approved'
    log['current'] = current
    _save_cycle_log(log)
    return True


def _complete_current_cycle(sent_by: str, subject: str,
                             recipient_count: int, report_filename: str) -> int | None:
    """Mark current cycle sent, move it to history, clear current (await next Excel). Returns cycle_id."""
    try:
        log = _load_cycle_log()
        current = log.get('current')
        if not current:
            cycle_id = int(log.get('next_cycle_id', 1))
            log['next_cycle_id'] = cycle_id + 1
            current = {
                'cycle_id': cycle_id,
                'upload_at': datetime.now().isoformat(),
                'upload_by': 'system',
                'approved_at': None,
                'approved_by': None,
                'status': 'uploaded',
            }
        current['sent_at'] = datetime.now().isoformat()
        current['sent_by'] = sent_by
        current['recipient_count'] = recipient_count
        current['subject'] = subject
        current['report_filename'] = report_filename
        current['status'] = 'sent'
        cid = int(current.get('cycle_id', 0))
        history = log.get('history', [])
        history.insert(0, current)
        log['history'] = history[:50]
        log['current'] = None
        _save_cycle_log(log)
        append_automation_activity(
            'cycle_completed',
            f'Cycle #{cid} completed — saved to history; upload a new Excel for the next run',
            (subject or '')[:200] or None,
            meta={'cycle_id': cid},
        )
        return cid
    except Exception as e:
        logger.warning(f'MMR complete cycle failed: {e}')
    return None


def _cycle_timeline_from_record(c: dict) -> list[dict]:
    """Ordered milestone rows for cycle detail UI."""
    rows: list[dict] = []
    if c.get('upload_at'):
        rows.append({
            'key': 'upload',
            'at': c['upload_at'],
            'title': 'Excel uploaded',
            'detail': f"By {c.get('upload_by') or '—'}",
        })
    if c.get('approved_at'):
        rows.append({
            'key': 'approved',
            'at': c['approved_at'],
            'title': 'Reviewed & approved',
            'detail': f"By {c.get('approved_by') or '—'}",
        })
    if c.get('sent_at'):
        subj = (c.get('subject') or '').strip()
        rows.append({
            'key': 'sent',
            'at': c['sent_at'],
            'title': 'Report email sent',
            'detail': (
                f"{c.get('recipient_count', 0)} recipients · sent by {c.get('sent_by') or '—'}"
                + (f' · {subj}' if subj else '')
            ),
        })
    fn = (c.get('report_filename') or '').strip()
    if fn:
        rows.append({
            'key': 'attachment',
            'at': c.get('sent_at') or c.get('upload_at'),
            'title': 'Excel attachment filename',
            'detail': fn,
        })
    rows.sort(key=lambda r: (r.get('at') or ''))
    return rows


def _activities_for_cycle_id(cycle_id: int, limit: int = 80) -> list[dict]:
    """Automation activity log rows tagged with this cycle_id (chronological)."""
    matches: list[dict] = []
    for e in _load_activity_log().get('entries', []):
        mid = e.get('meta') or {}
        try:
            if int(mid.get('cycle_id', -1)) == int(cycle_id):
                matches.append(e)
        except (TypeError, ValueError):
            continue
    matches.sort(key=lambda x: int(x.get('id', 0)))
    return matches[-limit:]


def _save_last_run(
    status: str,
    to_list: list,
    cc_list: list | None,
    subject: str,
    recipient_count: int,
    *,
    activity_source: str | None = None,
    cycle_id: int | None = None,
):
    """Persist last run for status display. On success with automation enabled, pause until a new Excel upload."""
    config = _load_config()
    config['last_run_at'] = datetime.now().isoformat()
    config['last_run_status'] = status
    config['last_run_to'] = ', '.join(to_list) if to_list else ''
    config['last_run_cc'] = ', '.join(cc_list) if cc_list else ''
    config['last_run_subject'] = subject or ''
    config['last_run_recipient_count'] = recipient_count
    if status == 'success' and config.get('schedule_enabled'):
        config['schedule_paused'] = True
        config['automation_waiting_for_fresh_upload'] = True
        up = _upload_path()
        if os.path.exists(up):
            config['last_sent_source_mtime'] = os.path.getmtime(up)
    _save_config(config)

    if status == 'success' and activity_source:
        src = 'Scheduled automation' if activity_source == 'scheduler' else 'Manual send'
        em: dict = {'recipients': recipient_count, 'source': activity_source}
        if cycle_id is not None:
            em['cycle_id'] = int(cycle_id)
        append_automation_activity(
            'email_sent',
            f'{src}: report email sent',
            subject or None,
            meta=em,
        )
    elif status == 'failed' and activity_source == 'scheduler':
        fm: dict = {'source': 'scheduler'}
        if cycle_id is not None:
            fm['cycle_id'] = int(cycle_id)
        append_automation_activity(
            'email_failed',
            'Scheduled automation: send failed',
            None,
            meta=fm,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Page render
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/', methods=['GET'])
@mmr_jwt_and_report_access
def dashboard():
    is_admin = False
    try:
        uid = get_jwt_identity()
        user = User.query.get(int(uid))
        if user and user.role == 'admin':
            is_admin = True
    except (TypeError, ValueError):
        pass
    return render_template('mmr_dashboard.html', is_admin=is_admin)


# ──────────────────────────────────────────────────────────────────────────────
# Upload
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/upload', methods=['POST'])
@mmr_jwt_and_report_access
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file format – upload .xlsx or .xls'}), 400

    dest = _upload_path()
    file.save(dest)

    try:
        dashboard_data, rows = _dashboard_payload_from_path(dest)
        # Start a new dispatch cycle for this upload
        new_cycle = None
        try:
            new_cycle = _start_new_cycle(_get_caller_identity())
        except Exception:
            pass

        # Auto-resume automation when new file uploaded (each run needs fresh Excel)
        config = _load_config()
        resumed_auto = False
        if config.get('schedule_enabled') and config.get('schedule_paused'):
            config['schedule_paused'] = False
            config['automation_waiting_for_fresh_upload'] = False
            _save_config(config)
            resumed_auto = True
            try:
                from .scheduler import update_schedule
                update_schedule(config, current_app._get_current_object())
            except Exception:
                pass
        who = _get_caller_identity()
        fn = (file.filename or 'workbook')[:120]
        emeta: dict = {'by': who, 'resumed_automation': resumed_auto}
        try:
            if new_cycle and new_cycle.get('cycle_id') is not None:
                emeta['cycle_id'] = int(new_cycle['cycle_id'])
        except (TypeError, ValueError):
            pass
        append_automation_activity(
            'excel_uploaded',
            f'New Excel uploaded by {who}' + (' — automation resumed for the next run.' if resumed_auto else ''),
            fn,
            meta=emeta,
        )
        return jsonify({'success': True, 'dashboard': dashboard_data, 'rows': rows,
                        'total': len(rows)})
    except Exception as e:
        logger.error(f'MMR upload parse error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@mmr_bp.route('/api/current-upload', methods=['GET'])
@mmr_jwt_and_report_access
def current_upload():
    """Return dashboard JSON for the last uploaded Excel (mmr_latest.xlsx) so the page can restore after refresh."""
    path = _upload_path()
    if not os.path.exists(path):
        return jsonify({'success': True, 'has_file': False})

    try:
        dashboard_data, rows = _dashboard_payload_from_path(path)
        return jsonify({
            'success': True,
            'has_file': True,
            'dashboard': dashboard_data,
            'rows': rows,
            'total': len(rows),
        })
    except Exception as e:
        logger.error(f'MMR current-upload parse error: {e}', exc_info=True)
        return jsonify({'success': False, 'has_file': True, 'error': str(e)}), 500


@mmr_bp.route('/api/clear-upload', methods=['POST'])
@mmr_jwt_and_report_access
def clear_upload():
    """Remove mmr_latest.xlsx so the dashboard can start fresh (new report cycle upload)."""
    path = _upload_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.warning(f'MMR clear-upload failed: {e}')
            return jsonify({'success': False, 'error': str(e)}), 500
    _who = _get_caller_identity()
    append_automation_activity(
        'excel_cleared',
        f'Report cleared from server by {_who}',
        'Workbook removed — upload a new Excel when ready.',
        meta={'by': _who},
    )
    return jsonify({'success': True})


# ──────────────────────────────────────────────────────────────────────────────
# Download report
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/download-report', methods=['GET'])
@mmr_jwt_and_report_access
def download_report():
    path = _upload_path()
    if not os.path.exists(path):
        return jsonify({'error': 'No file uploaded yet. Please upload an Excel file first.'}), 404

    try:
        from .mmr_service import parse_excel, generate_report_excel, get_report_date_range_from_df
        df = parse_excel(path)
        report_bytes = generate_report_excel(df)
        date_range = get_report_date_range_from_df(df)
        rf = _resolve_report_format(request.args.get('report_format'))
        filename = _report_filename(report_date_range=date_range, upload_path=path, report_format=rf)
        from flask import make_response
        resp = make_response(send_file(
            BytesIO(report_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ))
        resp.headers['Content-Length'] = len(report_bytes)
        return resp
    except Exception as e:
        logger.error(f'MMR report generation error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@mmr_bp.route('/api/download-report-monthly', methods=['GET'])
@mmr_jwt_and_report_access
def download_report_monthly():
    """Generate one Excel per calendar month and stream them as a single ZIP."""
    path = _upload_path()
    if not os.path.exists(path):
        return jsonify({'error': 'No file uploaded yet. Please upload an Excel file first.'}), 404

    try:
        from .mmr_service import parse_excel, generate_monthly_zip, get_report_date_range_from_df
        df = parse_excel(path)
        rf = _resolve_report_format(request.args.get('report_format'))
        zip_bytes, filenames = generate_monthly_zip(df, report_format=rf)

        date_range = get_report_date_range_from_df(df)
        if date_range:
            min_d, max_d = date_range[0], date_range[1]
            min_m = min_d.strftime('%b %Y')
            max_m = max_d.strftime('%b %Y')
            zip_name = (f'Reports {min_m}.zip' if min_m == max_m
                        else f'Reports {min_m} – {max_m}.zip')
        else:
            zip_name = 'Reports.zip'

        logger.info(f'MMR monthly ZIP: {len(filenames)} file(s) → {zip_name}')
        from flask import make_response
        resp = make_response(send_file(
            BytesIO(zip_bytes),
            as_attachment=True,
            download_name=zip_name,
            mimetype='application/zip'
        ))
        resp.headers['Content-Length'] = len(zip_bytes)
        return resp
    except Exception as e:
        logger.error(f'MMR monthly report generation error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Save to folder & Report folder
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/save-to-folder', methods=['POST'])
@mmr_jwt_and_report_access
def save_to_folder():
    """Save current (optionally filtered) report to the report folder."""
    path = _upload_path()
    if not os.path.exists(path):
        return jsonify({'error': 'No file uploaded yet. Please upload an Excel file first.'}), 400

    data = request.get_json() or {}
    rows = data.get('rows')
    filters = data.get('filters')  # { client, contract, serviceGroup, space, status, priority }

    try:
        from .mmr_service import parse_excel, generate_report_excel, rows_to_df, get_report_date_range_from_df
        if rows:
            df = rows_to_df(rows)
            if df.empty:
                return jsonify({'error': 'No rows to save. Apply filters or upload data.'}), 400
        else:
            df = parse_excel(path)
        report_bytes = generate_report_excel(df)
        date_range = get_report_date_range_from_df(df)
        rf = _resolve_report_format(data.get('report_format'))
        filename = _report_filename(report_date_range=date_range, upload_path=path, report_format=rf)
        saved = _save_report_to_folder(report_bytes, filename, 'saved', filters=filters)
        if saved:
            return jsonify({'success': True, 'filename': saved})
        return jsonify({'error': 'Failed to save to folder'}), 500
    except Exception as e:
        logger.error(f'MMR save to folder error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@mmr_bp.route('/api/save-to-drive', methods=['POST'])
@mmr_jwt_and_report_access
def save_to_drive():
    """Save current (optionally filtered) report to TrueNAS CAFM drive (see _TRUENAS_CAFM_PATH)."""
    path = _upload_path()
    if not os.path.exists(path):
        return jsonify({'error': 'No file uploaded yet. Please upload an Excel file first.'}), 400

    data = request.get_json() or {}
    rows = data.get('rows')
    filters = data.get('filters')
    save_path = data.get('save_path')

    try:
        from .mmr_service import parse_excel, generate_report_excel, rows_to_df, get_report_date_range_from_df
        if rows:
            df = rows_to_df(rows)
            if df.empty:
                return jsonify({'error': 'No rows to save. Apply filters or upload data.'}), 400
        else:
            df = parse_excel(path)
        report_bytes = generate_report_excel(df)
        date_range = get_report_date_range_from_df(df)
        rf = _resolve_report_format(data.get('report_format'))
        filename = _report_filename(report_date_range=date_range, upload_path=path, report_format=rf)

        if save_path:
            # Custom path: save only there
            saved_path, err, saved_locally = _save_report_to_drive(report_bytes, filename, save_path=save_path)
            if saved_path:
                return jsonify({
                    'success': True, 'path': saved_path, 'filename': filename,
                    'saved_locally': saved_locally
                })
        else:
            # Default Save to Drive: save to both locations
            path1, err1, loc1 = _save_report_to_drive(report_bytes, filename, save_path=_TRUENAS_CAFM_PATH)
            path2, err2, loc2 = _save_report_to_drive(report_bytes, filename, save_path=_SAVE_TO_DRIVE_GENERAL_PATH)
            if path1 or path2:
                if err1 and not loc1:
                    logger.warning(f'MMR Save to Drive: CAFM path failed: {err1}')
                if err2 and not loc2:
                    logger.warning(f'MMR Save to Drive: General CAFM path failed: {err2}')
                if path1 and path2 and not (loc1 or loc2):
                    logger.info(f'MMR Save to Drive: saved to both network locations')
                return jsonify({
                    'success': True,
                    'path': path1 or path2,
                    'filename': filename,
                    'saved_locally': loc1 or loc2,
                    'saved_to_both': bool(path1 and path2 and not (loc1 or loc2)),
                    'local_folder': _reports_folder() if (loc1 or loc2) else None
                })
            msg = err1 or err2 or 'Failed to save to drive. Check network access.'
            logger.error(f'MMR Save to Drive: both paths failed. CAFM: {err1}; General: {err2}')
            return jsonify({'error': msg}), 500

        msg = err or 'Failed to save to drive. Check network access to TrueNAS.'
        return jsonify({'error': msg}), 500
    except Exception as e:
        logger.error(f'MMR save to drive error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@mmr_bp.route('/api/report-folder', methods=['GET'])
@mmr_jwt_and_report_access
def list_report_folder():
    """List all saved reports in the report folder. Includes filter state for restoring dashboard."""
    folder = _reports_folder()
    files = []
    for name in os.listdir(folder):
        if name.lower().endswith('.xlsx'):
            path = os.path.join(folder, name)
            try:
                stat = os.stat(path)
                entry = {
                    'name': name,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
                # Load saved filter state if present
                filters_path = path.replace('.xlsx', '_filters.json')
                if os.path.exists(filters_path):
                    try:
                        with open(filters_path) as f:
                            entry['filters'] = json.load(f)
                    except Exception:
                        entry['filters'] = {}
                else:
                    entry['filters'] = {}
                files.append(entry)
            except OSError:
                pass
    # Always sort by actual saved/modified time (newest first)
    files.sort(key=lambda x: x.get('modified') or '', reverse=True)
    return jsonify({'files': files})


@mmr_bp.route('/api/report-folder/download/<path:filename>', methods=['GET'])
@mmr_jwt_and_report_access
def download_report_folder_file(filename):
    """Download a saved report from the report folder."""
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    folder = _reports_folder()
    path = os.path.join(folder, filename)
    if not os.path.exists(path) or not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@mmr_bp.route('/api/report-folder/open/<path:filename>', methods=['GET'])
@mmr_jwt_and_report_access
def open_report_from_folder(filename):
    """Load a saved report's data for display in the dashboard."""
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    folder = _reports_folder()
    path = os.path.join(folder, filename)
    if not os.path.exists(path) or not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404

    try:
        from .mmr_service import (
            parse_saved_report_excel,
            compute_dashboard,
            df_to_rows,
            _resolve_chargeable,
            get_mmr_chargeable_config,
            _project_blob_from_row_dict,
            _complaint_from_row_dict,
        )
        df = parse_saved_report_excel(path)
        if df.empty:
            return jsonify({'error': 'Could not parse report. The file may be in a different format.'}), 400
        dashboard_data = compute_dashboard(df)
        rows = df_to_rows(df)
        cfg = get_mmr_chargeable_config()
        for r in rows:
            r['Space'] = _resolve_chargeable(
                r.get('Space', ''), r.get('BaseUnit', ''), r.get('Client', ''),
                r.get('Service Group', ''), r.get('Contract', ''),
                r.get('Work Description', ''), r.get('Specific Area', ''),
                cfg,
                _project_blob_from_row_dict(r),
                '',
                _complaint_from_row_dict(r),
            )
        return jsonify({
            'success': True,
            'dashboard': dashboard_data,
            'rows': rows,
            'total': len(rows),
        })
    except Exception as e:
        logger.error(f'MMR open report error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Email config
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/email-config', methods=['GET'])
@mmr_jwt_and_report_access
def get_email_config():
    cfg = _load_config()
    out = {**cfg, 'presets': _email_presets_resolved(cfg), 'custom_presets': _custom_presets_list(cfg)}
    return jsonify(out)


def _collect_mmr_email_suggestions() -> list[dict]:
    """Unique @injaaz.ae addresses for To/CC autocomplete."""
    seen: set[str] = set()
    out: list[dict] = []

    def add(email: str, name: str = '') -> None:
        e = (email or '').strip()
        if not e.lower().endswith(f'@{ALLOWED_DOMAIN}'):
            return
        key = e.lower()
        if key in seen:
            return
        seen.add(key)
        out.append({'email': e, 'name': (name or '').strip()})

    for field in ('to', 'cc'):
        for part in (_DEFAULT_CONFIG.get(field, '') or '').split(','):
            add(part.strip())

    cfg = _load_config()
    for field in ('to', 'cc'):
        for part in (cfg.get(field) or '').split(','):
            add(part.strip())
    fr = cfg.get('format_recipients')
    if isinstance(fr, dict):
        for fmt in ('daily', 'monthly'):
            block = fr.get(fmt)
            if isinstance(block, dict):
                for part in (block.get('to') or '').split(','):
                    add(part.strip())
                for part in (block.get('cc') or '').split(','):
                    add(part.strip())
    for preset in _custom_presets_list(cfg):
        for part in (preset.get('to') or '').split(','):
            add(part.strip())
        for part in (preset.get('cc') or '').split(','):
            add(part.strip())

    try:
        rows = (
            User.query.filter(
                User.is_active.is_(True),
                User.email.ilike(f'%@{ALLOWED_DOMAIN}'),
            )
            .order_by(User.full_name.asc().nullslast(), User.email.asc())
            .all()
        )
        for u in rows:
            add(u.email, u.full_name or u.username or '')
    except Exception as e:
        logger.warning(f'MMR email suggestions user lookup skipped: {e}')

    out.sort(key=lambda x: ((x.get('name') or x['email']).lower(), x['email'].lower()))
    return out


@mmr_bp.route('/api/email-suggestions', methods=['GET'])
@mmr_jwt_and_report_access
def get_email_suggestions():
    q = (request.args.get('q') or '').strip().lower()
    items = _collect_mmr_email_suggestions()
    if q:
        filtered = []
        for item in items:
            email = item['email'].lower()
            name = (item.get('name') or '').lower()
            local = email.split('@')[0]
            if q in email or q in name or local.startswith(q):
                filtered.append(item)
        items = filtered
    return jsonify({'suggestions': items[:15]})


@mmr_bp.route('/api/automation-status', methods=['GET'])
@mmr_jwt_and_report_access
def get_automation_status():
    """Return schedule state and last run info for the automation button."""
    config = _load_config()
    schedule_enabled = bool(config.get('schedule_enabled'))
    schedule_hour = int(config.get('schedule_hour', 10))
    schedule_minute = int(config.get('schedule_minute', 0))
    schedule_paused = bool(config.get('schedule_paused'))
    excel_uploaded = os.path.exists(_upload_path())

    last_run = None
    if config.get('last_run_at'):
        try:
            at = datetime.fromisoformat(config['last_run_at'])
            today = datetime.now().date()
            last_run = {
                'at': config['last_run_at'],
                'at_formatted': at.strftime('%Y-%m-%d %H:%M'),
                'date': at.date().isoformat(),
                'is_today': at.date() == today,
                'status': config.get('last_run_status', 'unknown'),
                'to': config.get('last_run_to', ''),
                'cc': config.get('last_run_cc', ''),
                'subject': config.get('last_run_subject', ''),
                'recipient_count': int(config.get('last_run_recipient_count', 0)),
            }
        except (ValueError, TypeError):
            pass

    # automation_status: "completed" | "pending" | "paused" | "disabled"
    automation_status = 'disabled'
    if schedule_enabled:
        if schedule_paused:
            automation_status = 'paused'
        elif last_run and last_run['is_today'] and last_run['status'] == 'success':
            automation_status = 'completed'
        else:
            automation_status = 'pending'

    next_run = None
    next_run_tomorrow = False
    if schedule_enabled:
        now = datetime.now()
        next_today = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
        if now >= next_today:
            from datetime import timedelta
            next_today += timedelta(days=1)
            next_run_tomorrow = True
        next_run = next_today.strftime('%H:%M')

    excel_required_for_next_run = (
        schedule_enabled and schedule_paused and
        last_run and last_run['is_today'] and last_run['status'] == 'success'
    )
    waiting_fresh = bool(config.get('automation_waiting_for_fresh_upload'))

    return jsonify({
        'schedule_enabled': schedule_enabled,
        'schedule_hour': schedule_hour,
        'schedule_minute': schedule_minute,
        'schedule_paused': schedule_paused,
        'next_run_at': next_run,
        'next_run_tomorrow': next_run_tomorrow,
        'excel_uploaded': excel_uploaded,
        'excel_required_for_next_run': excel_required_for_next_run,
        'automation_waiting_for_fresh_upload': waiting_fresh,
        'last_run': last_run,
        'automation_status': automation_status,
    })


def _activity_entry_cycle_id(entry: dict) -> int | None:
    mid = entry.get('meta') or {}
    raw = mid.get('cycle_id')
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@mmr_bp.route('/api/automation-activities', methods=['GET'])
@mmr_jwt_and_report_access
def get_automation_activities():
    """Automation timeline (newest first).
    mode=live: rows for the active cycle only; if there is no current cycle, returns an empty list
    (idle top feed — full logs stay on each cycle under Cycle History).
    Or for_cycle=N / only_untagged=1 when mode is not live.
    """
    try:
        limit = min(_ACTIVITY_MAX_ENTRIES, max(1, int(request.args.get('limit', 40))))
    except (TypeError, ValueError):
        limit = 40
    after_id = request.args.get('after_id', type=int)
    mode = (request.args.get('mode') or '').strip().lower()
    live_context: dict | None = None
    only_untagged = False

    if mode == 'live':
        cl = _load_cycle_log()
        cur = cl.get('current')
        for_cycle = None
        if isinstance(cur, dict) and cur.get('cycle_id') is not None:
            try:
                for_cycle = int(cur['cycle_id'])
            except (TypeError, ValueError):
                for_cycle = None
        live_context = {'active_cycle_id': for_cycle}
    else:
        for_cycle = request.args.get('for_cycle', type=int)
        only_untagged = str(request.args.get('only_untagged', '')).strip().lower() in ('1', 'true', 'yes', 'on')

    log = _load_activity_log()
    pool = list(log.get('entries', []))
    if mode == 'live':
        if for_cycle is not None:
            pool = [e for e in pool if _activity_entry_cycle_id(e) == for_cycle]
        else:
            pool = []
    elif for_cycle is not None:
        pool = [e for e in pool if _activity_entry_cycle_id(e) == for_cycle]
    elif only_untagged:
        pool = [e for e in pool if _activity_entry_cycle_id(e) is None]

    if after_id is not None:
        entries = [e for e in pool if int(e.get('id', 0)) > after_id]
    else:
        entries = pool[:limit]

    ids = [int(e.get('id', 0)) for e in log.get('entries', [])]
    max_id = max(ids) if ids else 0

    out = {
        'activities': entries,
        'max_id': max_id,
        'server_time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    if live_context is not None:
        out['live_context'] = live_context
    return jsonify(out)


@mmr_bp.route('/api/automation-pause', methods=['POST'])
@mmr_jwt_and_report_access
def pause_automation():
    """Pause the automation. Next run will not execute until resumed."""
    config = _load_config()
    config['schedule_paused'] = True
    config['automation_waiting_for_fresh_upload'] = False
    _save_config(config)
    try:
        from .scheduler import update_schedule
        update_schedule(config, current_app._get_current_object())
    except Exception:
        pass
    append_automation_activity(
        'paused',
        f'Automation paused by {_get_caller_identity()}',
        'Scheduled sends are on hold until you resume.',
        meta={'by': _get_caller_identity()},
    )
    return jsonify({'success': True, 'paused': True})


@mmr_bp.route('/api/automation-resume', methods=['POST'])
@mmr_jwt_and_report_access
def resume_automation():
    """Resume the automation. Requires Excel file to be uploaded."""
    path = _upload_path()
    if not os.path.exists(path):
        return jsonify({'error': 'Upload an Excel file first to resume automation.'}), 400
    config = _load_config()
    if config.get('automation_waiting_for_fresh_upload'):
        try:
            last_mt = float(config.get('last_sent_source_mtime', 0))
        except (TypeError, ValueError):
            last_mt = 0.0
        if os.path.getmtime(path) <= last_mt + 0.001:
            append_automation_activity(
                'resume_blocked',
                f'Resume blocked for {_get_caller_identity()}',
                'A new Excel upload is required after the last send before automation can run again.',
                meta={'by': _get_caller_identity()},
            )
            return jsonify({
                'error': (
                    'Automation needs a new Excel upload after the last send. '
                    'Upload a fresh CAFM file, then resume (or it will resume automatically on upload).'
                )
            }), 400
    config['schedule_paused'] = False
    config['automation_waiting_for_fresh_upload'] = False
    _save_config(config)
    try:
        from .scheduler import update_schedule
        update_schedule(config, current_app._get_current_object())
    except Exception:
        pass
    append_automation_activity(
        'resumed',
        f'Automation resumed by {_get_caller_identity()}',
        'Next send will run at the scheduled time.',
        meta={'by': _get_caller_identity()},
    )
    return jsonify({'success': True, 'paused': False})


# ──────────────────────────────────────────────────────────────────────────────
# Cycle endpoints
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/cycles', methods=['GET'])
@mmr_jwt_and_report_access
def get_cycles():
    """Return full cycle log (current cycle + history)."""
    return jsonify(_load_cycle_log())


@mmr_bp.route('/api/cycle/<int:cycle_id>/detail', methods=['GET'])
@mmr_jwt_and_report_access
def get_cycle_detail(cycle_id: int):
    """Milestones + automation activity rows for one cycle (newest first, then back to start)."""
    log = _load_cycle_log()
    history = log.get('history', [])
    found = next((c for c in history if int(c.get('cycle_id', -1)) == int(cycle_id)), None)
    if found is None:
        cur = log.get('current')
        if cur and int(cur.get('cycle_id', -1)) == int(cycle_id):
            found = cur
    if found is None:
        return jsonify({'error': 'Cycle not found'}), 404
    timeline = list(reversed(_cycle_timeline_from_record(found)))
    activities = list(reversed(_activities_for_cycle_id(cycle_id)))
    return jsonify({
        'cycle': found,
        'timeline': timeline,
        'activities': activities,
    })


@mmr_bp.route('/api/approve', methods=['POST'])
@mmr_jwt_and_report_access
def approve_cycle():
    """Mark the current cycle as reviewed/approved."""
    user = _get_caller_identity()
    if _approve_current_cycle(user):
        log_ok = _load_cycle_log()
        cur = log_ok.get('current') or {}
        cid = cur.get('cycle_id')
        ameta: dict = {'by': user}
        try:
            if cid is not None:
                ameta['cycle_id'] = int(cid)
        except (TypeError, ValueError):
            pass
        append_automation_activity(
            'cycle_approved',
            f'Cycle marked reviewed by {user}',
            'Ready for email send or scheduled automation.',
            meta=ameta,
        )
        return jsonify({'success': True})
    log = _load_cycle_log()
    current = log.get('current')
    if not current:
        return jsonify({'error': 'No active cycle. Upload an Excel file first.'}), 400
    if current.get('status') == 'approved':
        return jsonify({'error': 'Already approved', 'already_approved': True}), 400
    if current.get('status') == 'sent':
        return jsonify({'error': 'Cycle already completed. Upload a new file to start the next cycle.'}), 400
    return jsonify({'error': 'Cannot approve in the current cycle state'}), 400


@mmr_bp.route('/api/email-config', methods=['POST'])
@mmr_jwt_and_report_access
def save_email_config():
    data = request.get_json() or {}

    # Domain validation before persisting
    for field in ('to', 'cc'):
        if field in data and data[field]:
            _, err = _validate_injaaz_emails(data[field])
            if err:
                return jsonify({'error': err}), 400
    fr_in = data.get('format_recipients')
    if isinstance(fr_in, dict):
        for fmt in ('daily', 'monthly'):
            block = fr_in.get(fmt)
            if not isinstance(block, dict):
                continue
            for field in ('to', 'cc'):
                if block.get(field):
                    _, err = _validate_injaaz_emails(block[field])
                    if err:
                        return jsonify({'error': err}), 400

    config = _load_config()
    prev_schedule_on = bool(config.get('schedule_enabled'))
    allowed = ['to', 'cc', 'subject', 'body',
                'schedule_enabled', 'schedule_hour', 'schedule_minute', 'schedule_paused',
                'active_custom_preset']
    for k in allowed:
        if k in data:
            config[k] = data[k]
    if 'report_format' in data:
        rf = str(data['report_format']).strip().lower()
        if rf not in ('daily', 'monthly', 'custom'):
            return jsonify({'error': 'report_format must be "daily", "monthly", or "custom"'}), 400
        config['report_format'] = rf
    if 'active_custom_preset' in data:
        key = str(data['active_custom_preset'] or '').strip().lower().replace(' ', '_')
        config['active_custom_preset'] = key
    # Per-format To/CC (Daily vs Monthly)
    rf_save = str(config.get('report_format', 'daily')).strip().lower()
    if rf_save in ('daily', 'monthly') and ('to' in data or 'cc' in data):
        fr = config.get('format_recipients')
        if not isinstance(fr, dict):
            fr = {}
        block = fr.get(rf_save) if isinstance(fr.get(rf_save), dict) else {}
        fr[rf_save] = {
            'to': data.get('to', block.get('to', config.get('to', ''))),
            'cc': data.get('cc', block.get('cc', config.get('cc', ''))),
        }
        config['format_recipients'] = fr
    if 'format_recipients' in data and isinstance(data['format_recipients'], dict):
        fr_in = data['format_recipients']
        fr = config.get('format_recipients')
        if not isinstance(fr, dict):
            fr = {}
        for fmt in ('daily', 'monthly'):
            block = fr_in.get(fmt)
            if not isinstance(block, dict):
                continue
            fr[fmt] = {
                'to': block.get('to', fr.get(fmt, {}).get('to', '') if isinstance(fr.get(fmt), dict) else ''),
                'cc': block.get('cc', fr.get(fmt, {}).get('cc', '') if isinstance(fr.get(fmt), dict) else ''),
            }
        config['format_recipients'] = fr
    # Env schedule vars (Render) override form so MMR_SCHEDULE_* survives accidental UI toggles
    config.update(_env_schedule_override())
    _save_config(config)

    now_on = bool(config.get('schedule_enabled'))
    if prev_schedule_on != now_on:
        h = int(config.get('schedule_hour', 10))
        m = int(config.get('schedule_minute', 0))
        if now_on:
            append_automation_activity(
                'schedule_on',
                'Daily email automation enabled',
                f'Schedule: {h:02d}:{m:02d} (automation timezone).',
                meta={'hour': h, 'minute': m},
            )
        else:
            append_automation_activity(
                'schedule_off',
                'Daily email automation stopped',
                'No further scheduled sends until re-enabled.',
                meta={},
            )

    # Refresh scheduler
    try:
        from .scheduler import update_schedule
        update_schedule(config, current_app._get_current_object())
    except Exception as e:
        logger.warning(f'MMR scheduler update skipped: {e}')

    return jsonify({'success': True})


@mmr_bp.route('/api/email-presets', methods=['POST'])
@mmr_jwt_and_report_access
def save_email_preset():
    """Save current-style To/CC/subject/body under a user-chosen name."""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    key = _normalize_preset_key(name)
    if not key:
        return jsonify({
            'error': (
                f'Preset name is required (letters, numbers, spaces, dash; '
                f'max {_PRESET_NAME_MAX_LEN} characters).'
            ),
        }), 400

    to_raw = (data.get('to') or '').strip()
    if not to_raw:
        return jsonify({'error': 'To is required when saving a preset'}), 400

    for field in ('to', 'cc'):
        if field in data and data[field]:
            _, err = _validate_injaaz_emails(data[field])
            if err:
                return jsonify({'error': err}), 400

    rf = str(data.get('report_format', 'daily')).strip().lower()
    if rf not in ('daily', 'monthly', 'custom'):
        rf = 'daily'

    config = _load_config()
    presets = config.get('custom_presets')
    if not isinstance(presets, dict):
        presets = {}
    presets[key] = {
        'name': name,
        'to': data.get('to', '') or '',
        'cc': data.get('cc', '') or '',
        'subject': (data.get('subject') or '').strip(),
        'body': (data.get('body') or '').strip(),
        'report_format': rf,
    }
    config['custom_presets'] = presets
    _save_config(config)
    return jsonify({'success': True, 'custom_presets': _custom_presets_list(config)})


@mmr_bp.route('/api/email-presets/<path:preset_key>', methods=['DELETE'])
@mmr_jwt_and_report_access
def delete_email_preset(preset_key: str):
    key = _normalize_preset_key(preset_key) or preset_key.strip().lower().replace(' ', '_')
    config = _load_config()
    presets = config.get('custom_presets')
    if not isinstance(presets, dict) or key not in presets:
        return jsonify({'error': 'Preset not found'}), 404
    del presets[key]
    config['custom_presets'] = presets
    _save_config(config)
    return jsonify({'success': True, 'custom_presets': _custom_presets_list(config)})


# ──────────────────────────────────────────────────────────────────────────────
# Send email
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/send-email', methods=['POST'])
@mmr_jwt_and_report_access
def send_email_now():
    """Send report email immediately (manual). Does not require cycle approval."""
    data = request.get_json() or {}
    upload_path = _upload_path()
    folder_path = _safe_report_folder_path(data.get('folder_filename'))
    use_folder = bool(folder_path and not os.path.exists(upload_path))
    path = folder_path if use_folder else upload_path

    if not os.path.exists(path):
        return jsonify({
            'error': (
                'No report available. Upload a CAFM Excel file or open a saved report '
                'from the Report folder first.'
            ),
        }), 400

    to_raw = data.get('to', '').strip()
    cc_raw = data.get('cc', '').strip()
    subject = data.get('subject', _DEFAULT_CONFIG['subject'])
    body    = data.get('body', '')
    cfg_send = _load_config()
    rf = (data.get('report_format') or cfg_send.get('report_format') or 'daily')
    rf = str(rf).strip().lower()
    if rf not in ('daily', 'monthly'):
        rf = 'daily'

    if not to_raw:
        return jsonify({'error': 'Recipient (To) email is required'}), 400

    to_list, to_err = _validate_injaaz_emails(to_raw)
    if to_err:
        return jsonify({'error': to_err}), 400

    cc_list, cc_err = _validate_injaaz_emails(cc_raw)
    if cc_err:
        return jsonify({'error': cc_err}), 400
    cc_list = cc_list or None

    # Generate report (or attach saved report from folder)
    try:
        from .mmr_service import (
            parse_excel,
            parse_saved_report_excel,
            generate_report_excel,
            get_report_date_range_from_df,
            build_mmr_email_bodies,
        )
        if use_folder:
            with open(path, 'rb') as report_file:
                report_bytes = report_file.read()
            df = parse_saved_report_excel(path)
            filename = os.path.basename(path)
        else:
            df = parse_excel(path)
            report_bytes = generate_report_excel(df)
            date_range = get_report_date_range_from_df(df)
            filename = _report_filename(report_date_range=date_range, upload_path=path, report_format=rf)
        date_range = get_report_date_range_from_df(df)
        # Build report_date string for subject/body (same format as filename date part)
        report_date = _format_report_date_range_str(date_range)
        if report_date is None:
            from .mmr_service import get_report_date_from_excel
            report_dt = get_report_date_from_excel(path) or (datetime.now() - timedelta(days=1))
            report_date = _format_report_date(report_dt)
        subject = subject.replace(_REPORT_DATE_PLACEHOLDER, report_date)
        body = body.replace(_REPORT_DATE_PLACEHOLDER, report_date)

        body, html_body = build_mmr_email_bodies(body, df)
    except Exception as e:
        return jsonify({'error': f'Report generation failed: {str(e)}'}), 500

    # Guard: SMTP or Mailjet HTTPS API (Render free tier blocks outbound SMTP ports)
    from flask import current_app as _app
    from common.email_service import is_email_configured
    if not is_email_configured(_app):
        return jsonify({
            'error': (
                'Email is not configured. Set MAIL_* for SMTP, or '
                'MAILJET_API_KEY + MAILJET_SECRET_KEY + MAIL_DEFAULT_SENDER for Mailjet '
                '(HTTPS, recommended on Render free tier).'
            )
        }), 503

    # Send
    try:
        from common.email_service import send_email
        ok = send_email(
            recipient=to_list,
            subject=subject,
            body=body,
            html_body=html_body if html_body else None,
            cc=cc_list,
            attachments=[{
                'content': report_bytes,
                'filename': filename,
                'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }]
        )
        if ok:
            _save_report_to_folder(report_bytes, filename, 'email')
            _save_email_report_to_network(report_bytes, filename)
            rc = len(to_list) + (len(cc_list) if cc_list else 0)
            cid = None
            try:
                cid = _complete_current_cycle(_get_caller_identity(), subject, rc, filename)
            except Exception:
                pass
            try:
                _save_last_run(
                    'success', to_list, cc_list, subject, rc,
                    activity_source='manual', cycle_id=cid,
                )
            except Exception:
                pass
            return jsonify({
                'success': True,
                'message': "Email sent successfully. If you don't see it, check spam/junk and Promotions (Gmail)."
            })
        return jsonify({'error': 'Email was rejected by the mail server. Check credentials and try again.'}), 502
    except Exception as e:
        logger.error(f'MMR send email error: {e}', exc_info=True)
        return jsonify({'error': f'Email error: {str(e)}'}), 502
