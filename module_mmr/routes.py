"""
MMR Blueprint – Report Generation (available to all authenticated users).
URL prefix: /admin/mmr
Administrative module (user management, access control) stays admin-only.
"""
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO

from flask import (Blueprint, request, jsonify, render_template,
                   current_app, send_file)
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import User

logger = logging.getLogger(__name__)

mmr_bp = Blueprint('mmr_bp', __name__, url_prefix='/admin/mmr',
                   template_folder='templates')

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
        },
        'monthly': {
            'subject': _MONTHLY_SUBJECT_DEFAULT,
            'body': _MONTHLY_BODY_DEFAULT,
        },
    }

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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
def get_email_config():
    cfg = _load_config()
    out = {**cfg, 'presets': _email_presets()}
    return jsonify(out)


@mmr_bp.route('/api/automation-status', methods=['GET'])
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
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
@jwt_required()
def get_cycles():
    """Return full cycle log (current cycle + history)."""
    return jsonify(_load_cycle_log())


@mmr_bp.route('/api/cycle/<int:cycle_id>/detail', methods=['GET'])
@jwt_required()
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
@jwt_required()
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
@jwt_required()
def save_email_config():
    data = request.get_json() or {}

    # Domain validation before persisting
    for field in ('to', 'cc'):
        if field in data and data[field]:
            _, err = _validate_injaaz_emails(data[field])
            if err:
                return jsonify({'error': err}), 400

    config = _load_config()
    prev_schedule_on = bool(config.get('schedule_enabled'))
    allowed = ['to', 'cc', 'subject', 'body',
                'schedule_enabled', 'schedule_hour', 'schedule_minute', 'schedule_paused']
    for k in allowed:
        if k in data:
            config[k] = data[k]
    if 'report_format' in data:
        rf = str(data['report_format']).strip().lower()
        if rf not in ('daily', 'monthly'):
            return jsonify({'error': 'report_format must be "daily" or "monthly"'}), 400
        config['report_format'] = rf
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


# ──────────────────────────────────────────────────────────────────────────────
# Send email
# ──────────────────────────────────────────────────────────────────────────────

@mmr_bp.route('/api/send-email', methods=['POST'])
@jwt_required()
def send_email_now():
    data = request.get_json() or {}
    path = _upload_path()

    if not os.path.exists(path):
        return jsonify({'error': 'No MMR file uploaded yet. Please upload an Excel file first.'}), 400

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

    # Generate report
    try:
        from .mmr_service import parse_excel, generate_report_excel, get_report_date_range_from_df, format_chargeable_summary_for_email, format_per_tower_chargeable_html_for_email
        df = parse_excel(path)
        report_bytes = generate_report_excel(df)
        date_range = get_report_date_range_from_df(df)
        filename = _report_filename(report_date_range=date_range, upload_path=path, report_format=rf)
        # Build report_date string for subject/body (same format as filename date part)
        report_date = _format_report_date_range_str(date_range)
        if report_date is None:
            from .mmr_service import get_report_date_from_excel
            report_dt = get_report_date_from_excel(path) or (datetime.now() - timedelta(days=1))
            report_date = _format_report_date(report_dt)
        subject = subject.replace(_REPORT_DATE_PLACEHOLDER, report_date)
        body = body.replace(_REPORT_DATE_PLACEHOLDER, report_date)

        # Intro for HTML (full body before chargeable summary)
        intro_for_html = body.rstrip()

        # Plain text body (fallback)
        chargeable_summary = format_chargeable_summary_for_email(df)
        if chargeable_summary:
            body = (body.rstrip() + '\n\n' + chargeable_summary).rstrip()
        body = (body.rstrip() + '\n\nFor full information, please refer to the attached Excel file.').rstrip()

        # HTML body with per-tower tables (Askaan, Orient, Garden, C1)
        html_tables = format_per_tower_chargeable_html_for_email(df)
        html_body = None
        if html_tables:
            intro_escaped = intro_for_html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            html_body = f'''<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="font-family:Arial,sans-serif;font-size:12px;color:#333">
<p style="margin:0 0 12px 0;line-height:1.5">{intro_escaped}</p>
{html_tables}
<p style="margin:12px 0 8px 0;font-size:10px;color:#666;font-style:italic">* This is computer generated, please cross check at least once.</p>
<p style="margin:0">For full information, please refer to the attached Excel file.</p>
</body></html>'''
    except Exception as e:
        return jsonify({'error': f'Report generation failed: {str(e)}'}), 500

    # Guard: SMTP or Brevo HTTP API (Render free tier blocks outbound SMTP ports)
    from flask import current_app as _app
    from common.email_service import is_email_configured
    if not is_email_configured(_app):
        return jsonify({
            'error': (
                'Email is not configured. Set MAIL_* for SMTP, or '
                'BREVO_API_KEY + MAIL_DEFAULT_SENDER for Brevo (HTTPS, recommended on Render free tier).'
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
