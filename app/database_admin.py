"""
Admin-facing database status and backup helpers.

Always describes the database THIS running app is connected to — never a second
live/local URL. Credentials are never returned.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal

from flask import current_app
from sqlalchemy import inspect, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.sql.sqltypes import String, Text


from app.models import DatabaseBackup, db

logger = logging.getLogger(__name__)

MAX_BACKUP_BYTES = 200 * 1024 * 1024  # 200 MB — refuse so the web process cannot hang
BACKUP_TIMEOUT_SEC = 180

NOT_IN_DATABASE = [
    {
        'title': 'MMR Excel workbooks',
        'detail': 'Monthly report spreadsheets live in the generated-files folder (or Cloudinary), not in this database.',
    },
    {
        'title': 'Generated PDFs and uploads',
        'detail': 'Inspection reports, photos, and similar files are stored as files (local disk in development, Cloudinary in production).',
    },
    {
        'title': 'Google Drive files',
        'detail': 'The Files module may sync to Drive. Drive itself is outside this database.',
    },
]

# Human groups for the admin page. Unknown tables fall into Other.
MODULE_GROUPS = [
    (
        'Users & access',
        'People who can log in, sessions, and security logs',
        [
            'users', 'sessions', 'audit_logs', 'notifications', 'push_device_tokens',
            'integration_api_keys', 'outbound_webhooks',
        ],
    ),
    (
        'Workflow & forms',
        'Inspection submissions, jobs, and attached form files',
        ['submissions', 'jobs', 'files'],
    ),
    (
        'HR',
        'Hiring, leave, and manpower trackers',
        [
            'hiring_candidates', 'hiring_documents', 'hiring_offer_letters',
            'leave_employees', 'leave_monthly_usage', 'leave_logs', 'leave_plans',
            'manpower_trades', 'manpower_projects', 'manpower_vacancies',
        ],
    ),
    (
        'Ticketing',
        'Work orders, properties, notes, and related ticket data',
        [
            'ticket_projects', 'ticket_properties', 'ticket_zones', 'ticket_sub_zones',
            'ticket_base_units', 'ticket_title_templates', 'ticket_supervisor_teams',
            'tickets', 'ticket_assets', 'ticket_triage_logs', 'ticket_notes',
            'ticket_images', 'ticket_materials', 'ticket_manpower', 'ticket_email_intakes',
        ],
    ),
    (
        'Assets',
        'Facility assets, floor plans, and forecasts',
        ['fm_assets', 'fm_asset_predictions', 'fm_floor_plans', 'fm_portfolio_forecasts'],
    ),
    (
        'QHSE',
        'Training sessions and staff compliance imports',
        ['qhsi_trainings', 'qhse_compliance_imports', 'qhse_staff_compliance_rows'],
    ),
    (
        'Files',
        'In-app Files folders and Drive connection (not the Drive files themselves)',
        ['files_folders', 'files_items', 'files_drive_connections'],
    ),
    (
        'Admin',
        'Devices, business development, DocHub, knowledge base, and settings',
        [
            'devices', 'technicians',
            'bd_projects', 'bd_followups', 'bd_contacts', 'bd_activities',
            'admin_personal_projects', 'admin_personal_progress_steps',
            'dochub_documents', 'dochub_access', 'knowledge_base_entries',
            'mmr_chargeable_config', 'notification_config', 'email_logs', 'database_backups',
            'assistant_pending_actions',
        ],
    ),
]


class BackupError(Exception):
    """Backup could not be created."""


class BackupTooLarge(BackupError):
    """Database is larger than the in-app download limit."""


def current_environment():
    flask_env = (current_app.config.get('FLASK_ENV') or os.getenv('FLASK_ENV') or 'development').lower()
    return 'live' if flask_env == 'production' else 'local'


def current_engine_kind():
    uri = _database_uri()
    if 'sqlite' in (uri or '').lower():
        return 'sqlite'
    return 'postgresql'


def _database_uri():
    return (
        current_app.config.get('SQLALCHEMY_DATABASE_URI')
        or current_app.config.get('DATABASE_URL')
        or ''
    )


def _make_url():
    uri = _database_uri()
    try:
        return make_url(uri)
    except Exception:
        return None


def _sqlite_path():
    url = _make_url()
    if not url or url.get_backend_name() != 'sqlite':
        return None
    db_name = url.database
    if not db_name or db_name == ':memory:':
        return None
    return os.path.abspath(db_name)


def _quote_ident(name):
    return db.engine.dialect.identifier_preparer.quote(name)


def _format_bytes(size_b):
    size_b = int(size_b or 0)
    if size_b >= 1024 * 1024:
        return f'{size_b / (1024 * 1024):.1f} MB'
    if size_b >= 1024:
        return f'{max(1, int(round(size_b / 1024)))} KB'
    if size_b:
        return f'{size_b} B'
    return '—'


def _probe_health():
    try:
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True, None
    except Exception as exc:
        logger.warning('Database health probe failed: %s', exc)
        return False, str(exc)


def _database_size_bytes():
    engine = current_engine_kind()
    if engine == 'sqlite':
        path = _sqlite_path()
        if path and os.path.isfile(path):
            return os.path.getsize(path)
        return None
    try:
        size = db.session.execute(text('SELECT pg_database_size(current_database())')).scalar()
        return int(size) if size is not None else None
    except Exception as exc:
        logger.info('Could not read Postgres database size: %s', exc)
        return None


def describe_current_database():
    """Plain-language description of the DB this process is using."""
    env = current_environment()
    engine = current_engine_kind()
    healthy, health_error = _probe_health()
    size_bytes = _database_size_bytes()
    url = _make_url()

    if env == 'live':
        env_label = 'Live (production)'
        env_plain = 'This is the live website the client uses. Changes here are real.'
    else:
        env_label = 'Laptop (local)'
        env_plain = 'This is a copy on this computer. It is not the client’s live website.'

    if engine == 'sqlite':
        engine_label = 'SQLite'
        engine_plain = 'A file on this computer (SQLite)'
        db_name = os.path.basename(_sqlite_path() or (url.database if url else '') or 'injaaz.db')
        host_label = 'This computer'
    else:
        engine_label = 'PostgreSQL'
        if env == 'live':
            engine_plain = 'A PostgreSQL server (the real live database)'
        else:
            engine_plain = 'A PostgreSQL database on this computer (same kind as live, still local)'
        db_name = (url.database if url else None) or '—'
        host_label = (url.host if url and url.host else None) or ('this computer' if env == 'local' else '—')

    last = None
    try:
        last = (
            DatabaseBackup.query.filter_by(status='ok')
            .order_by(DatabaseBackup.created_at.desc())
            .first()
        )
    except Exception:
        db.session.rollback()
        last = None

    sqlite_in_production = env == 'live' and engine == 'sqlite'
    oversize = bool(size_bytes and size_bytes > MAX_BACKUP_BYTES)

    return {
        'environment': env,
        'environment_label': env_label,
        'environment_plain': env_plain,
        'engine': engine,
        'engine_label': engine_label,
        'engine_plain': engine_plain,
        'healthy': healthy,
        'health_label': 'Connected' if healthy else 'Not connected',
        'health_error': health_error,
        'host': host_label,
        'database_name': db_name,
        'size_bytes': size_bytes,
        'size_label': _format_bytes(size_bytes) if size_bytes is not None else 'Unknown',
        'backup_limit_bytes': MAX_BACKUP_BYTES,
        'backup_limit_label': _format_bytes(MAX_BACKUP_BYTES),
        'oversize': oversize,
        'sqlite_in_production': sqlite_in_production,
        'last_backup': last.to_dict() if last else None,
        'not_in_database': NOT_IN_DATABASE,
    }


def _table_label(name):
    return name.replace('_', ' ').replace('-', ' ').title()


def module_table_counts():
    """Row counts grouped by product area. Missing tables are skipped."""
    try:
        existing = set(inspect(db.engine).get_table_names())
    except Exception as exc:
        logger.warning('Could not list tables: %s', exc)
        return []

    grouped = []
    seen = set()
    for title, blurb, tables in MODULE_GROUPS:
        items = []
        total = 0
        for table in tables:
            seen.add(table)
            if table not in existing:
                continue
            try:
                count = db.session.execute(text(f'SELECT COUNT(*) FROM {_quote_ident(table)}')).scalar()
                count = int(count or 0)
            except Exception:
                db.session.rollback()
                count = None
            items.append({
                'table': table,
                'label': _table_label(table),
                'rows': count,
            })
            if count:
                total += count
        if items:
            grouped.append({
                'id': title.lower().replace(' ', '-').replace('&', 'and'),
                'title': title,
                'blurb': blurb,
                'tables': items,
                'row_total': total,
                'table_count': len(items),
            })

    leftover = sorted(existing - seen - {'alembic_version', 'sqlite_sequence'})
    other_items = []
    other_total = 0
    for table in leftover:
        try:
            count = db.session.execute(text(f'SELECT COUNT(*) FROM {_quote_ident(table)}')).scalar()
            count = int(count or 0)
        except Exception:
            db.session.rollback()
            count = None
        other_items.append({
            'table': table,
            'label': _table_label(table),
            'rows': count,
        })
        if count:
            other_total += count
    if other_items:
        grouped.append({
            'id': 'other',
            'title': 'Other',
            'blurb': 'Tables that are not grouped into a module yet',
            'tables': other_items,
            'row_total': other_total,
            'table_count': len(other_items),
        })
    return grouped


_TABLE_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_HIDDEN_COLUMNS = {
    'password_hash', 'mfa_secret', 'refresh_token_enc', 'key_hash', 'secret',
    'token_jti',
}
_HIDDEN_SUFFIXES = ('_hash', '_secret', '_enc')
# Still show admin_visible_password — it is the same field Manage profile already shows admins.
_SHOW_EVEN_IF_HIDDEN_NAME = {'admin_visible_password'}

PREFERRED_COLUMNS = {
    'users': [
        'id', 'username', 'email', 'full_name', 'role', 'designation',
        'is_active', 'last_login', 'admin_visible_password', 'phone', 'created_at',
    ],
    'sessions': ['id', 'user_id', 'expires_at', 'is_revoked', 'created_at'],
    'audit_logs': ['id', 'user_id', 'action', 'resource_type', 'resource_id', 'created_at'],
    'submissions': [
        'id', 'submission_id', 'doc_number', 'module_type', 'site_name',
        'status', 'workflow_status', 'user_id', 'created_at',
    ],
    'jobs': ['id', 'job_id', 'submission_id', 'status', 'progress', 'created_at', 'completed_at'],
    'hiring_candidates': ['id', 'full_name', 'email', 'role', 'status', 'created_at'],
    'leave_employees': ['id', 'emp_id', 'full_name', 'role', 'email'],
    'leave_logs': ['id', 'emp_id', 'leave_type', 'start_date', 'end_date', 'status'],
    'manpower_vacancies': ['id', 'trade_id', 'project_id', 'status', 'count'],
    'tickets': ['id', 'ticket_number', 'title', 'status', 'priority', 'created_at'],
    'devices': ['id', 'name', 'device_type', 'status', 'health', 'assigned_user_id'],
    'technicians': ['id', 'employee_id', 'full_name', 'supervisor_user_id'],
    'bd_projects': ['id', 'name', 'company', 'status'],
    'knowledge_base_entries': ['id', 'title', 'category', 'source_type', 'is_active'],
    'mmr_chargeable_config': ['id', 'config_json'],
    'qhse_staff_compliance_rows': ['id', 'employee_name', 'employee_id', 'status'],
    'files_items': ['id', 'name', 'filename', 'source_module', 'sync_status', 'size_bytes'],
}

TABLE_NOTES = {
    'users': 'Login accounts for this website. Password hashes and MFA secrets are hidden. The admin-visible password is the same value shown in Manage profile.',
    'sessions': 'Who is signed in. Session tokens are hidden.',
    'mmr_chargeable_config': 'MMR billing rules only. The monthly Excel workbook itself is not stored in this table.',
    'submissions': 'Inspection and form records. Large form JSON is truncated in the grid — click a row to read it.',
    'files': 'Metadata for files attached to form submissions, not the file bytes.',
    'files_drive_connections': 'Google Drive connection status. Refresh tokens are hidden.',
    'integration_api_keys': 'API key names and prefixes. The secret hash is hidden.',
}

BROWSE_PAGE_MAX = 100
CELL_PREVIEW_CHARS = 140


class UnknownTable(ValueError):
    """Table does not exist or is not allowed to browse."""


def _is_hidden_column(name):
    n = (name or '').lower()
    if n in _SHOW_EVEN_IF_HIDDEN_NAME:
        return False
    if n in _HIDDEN_COLUMNS:
        return True
    return any(n.endswith(sfx) for sfx in _HIDDEN_SUFFIXES)


def _existing_tables():
    names = set(inspect(db.engine).get_table_names())
    names.discard('sqlite_sequence')
    names.discard('alembic_version')
    return names


def _column_is_textish(col):
    t = col.get('type')
    if t is None:
        return False
    try:
        if isinstance(t, (String, Text)):
            return True
    except Exception:
        pass
    type_name = type(t).__name__.lower()
    return any(x in type_name for x in ('char', 'text', 'json', 'clob', 'uuid'))


def _pick_grid_columns(table_name, col_names):
    preferred = [c for c in PREFERRED_COLUMNS.get(table_name, []) if c in col_names and not _is_hidden_column(c)]
    if preferred:
        return preferred
    favorites = [
        'id', 'submission_id', 'doc_number', 'username', 'email', 'full_name', 'name',
        'title', 'status', 'role', 'created_at', 'updated_at',
    ]
    picked = [c for c in favorites if c in col_names and not _is_hidden_column(c)]
    for c in col_names:
        if c not in picked and not _is_hidden_column(c):
            picked.append(c)
        if len(picked) >= 8:
            break
    return picked[:8]


def _cell_preview(value, hidden=False, limit=CELL_PREVIEW_CHARS):
    if hidden:
        return {'text': 'Hidden', 'hidden': True, 'truncated': False}
    if value is None:
        return {'text': '—', 'hidden': False, 'truncated': False}
    if isinstance(value, bool):
        return {'text': 'Yes' if value else 'No', 'hidden': False, 'truncated': False}
    rendered = _jsonable(value)
    if isinstance(rendered, (dict, list)):
        text = json.dumps(rendered, ensure_ascii=False, default=str)
    else:
        text = '' if rendered is None else str(rendered)
    truncated = len(text) > limit
    if truncated:
        text = text[:limit].rstrip() + '…'
    return {'text': text, 'hidden': False, 'truncated': truncated}


def _cell_full(value, hidden=False):
    if hidden:
        return {'text': 'Hidden', 'hidden': True}
    if value is None:
        return {'text': None, 'hidden': False}
    if isinstance(value, bool):
        return {'text': True if value else False, 'hidden': False}
    rendered = _jsonable(value)
    if isinstance(rendered, (dict, list)):
        return {'text': json.dumps(rendered, ensure_ascii=False, indent=2, default=str), 'hidden': False, 'json': True}
    return {'text': rendered, 'hidden': False}


def browse_table(table_name, page=1, per_page=50, q=''):
    """Read-only page of rows. table_name must already exist on this database."""
    if not table_name or not _TABLE_NAME_RE.match(table_name):
        raise UnknownTable('That is not a valid table name.')
    existing = _existing_tables()
    if table_name not in existing:
        raise UnknownTable('This table is not in the current database.')

    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(per_page or 50)
    except (TypeError, ValueError):
        per_page = 50
    per_page = min(max(per_page, 1), BROWSE_PAGE_MAX)
    q = (q or '').strip()
    if len(q) > 80:
        q = q[:80]

    inspector = inspect(db.engine)
    raw_cols = inspector.get_columns(table_name)
    col_names = [c['name'] for c in raw_cols]
    ident = _quote_ident(table_name)

    pk_info = inspector.get_pk_constraint(table_name) or {}
    pk_cols = [c for c in (pk_info.get('constrained_columns') or []) if c in col_names]
    order_col = pk_cols[0] if pk_cols else (col_names[0] if col_names else None)

    where_sql = ''
    params = {}
    if q:
        text_cols = [c['name'] for c in raw_cols if _column_is_textish(c) and not _is_hidden_column(c['name'])]
        if not text_cols:
            text_cols = [c for c in col_names if not _is_hidden_column(c)][:6]
        if text_cols:
            like = '%' + q.replace('\\', '').replace('%', '').replace('_', '') + '%'
            params['q'] = like
            parts = [f"CAST({_quote_ident(c)} AS TEXT) LIKE :q" for c in text_cols]
            where_sql = ' WHERE (' + ' OR '.join(parts) + ')'

    count_sql = f'SELECT COUNT(*) FROM {ident}{where_sql}'
    total = int(db.session.execute(text(count_sql), params).scalar() or 0)

    offset = (page - 1) * per_page
    order_sql = f' ORDER BY {_quote_ident(order_col)} DESC' if order_col else ''
    select_sql = f'SELECT * FROM {ident}{where_sql}{order_sql} LIMIT :lim OFFSET :off'
    bind = dict(params)
    bind['lim'] = per_page
    bind['off'] = offset
    result = db.session.execute(text(select_sql), bind)

    grid_cols = _pick_grid_columns(table_name, col_names)
    rows = []
    for mapping in result.mappings():
        raw = dict(mapping)
        preview = {}
        detail = {}
        for name in col_names:
            hidden = _is_hidden_column(name)
            val = raw.get(name)
            if name in grid_cols:
                preview[name] = _cell_preview(val, hidden=hidden)
            detail[name] = _cell_full(val, hidden=hidden)
        pk = {k: _jsonable(raw.get(k)) for k in pk_cols} if pk_cols else {}
        rows.append({'pk': pk, 'preview': preview, 'detail': detail})

    pages = max(1, (total + per_page - 1) // per_page) if total else 1
    return {
        'table': table_name,
        'label': _table_label(table_name),
        'note': TABLE_NOTES.get(
            table_name,
            'You can view, edit, add, and delete rows here. Changes apply to this website’s database immediately.',
        ),
        'read_only': False,
        'can_edit': bool(pk_cols),
        'pk_columns': pk_cols,
        'columns': [_column_meta(c, raw_cols, pk_cols) for c in col_names],
        'grid_columns': [{
            'name': c,
            'label': _table_label(c),
        } for c in grid_cols],
        'rows': rows,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': pages,
        'q': q,
    }


class BrowseError(ValueError):
    """Invalid edit/delete/insert against a browsed table."""


_LOCK_COLUMNS = {'created_at'}  # keep original create time unless inserting


def _column_kind(col):
    t = col.get('type')
    name = type(t).__name__.lower() if t is not None else ''
    if 'bool' in name:
        return 'bool'
    if 'int' in name:
        return 'number'
    if any(x in name for x in ('numeric', 'float', 'decimal', 'real')):
        return 'number'
    if 'datetime' in name or 'timestamp' in name:
        return 'datetime'
    if name == 'date' or (name.endswith('date') and 'time' not in name):
        return 'date'
    if 'json' in name:
        return 'json'
    return 'text'


def _column_meta(name, raw_cols, pk_cols):
    raw = next((c for c in raw_cols if c['name'] == name), {}) or {}
    hidden = _is_hidden_column(name)
    pk = name in pk_cols
    return {
        'name': name,
        'label': _table_label(name),
        'hidden': hidden,
        'pk': pk,
        'nullable': bool(raw.get('nullable', True)),
        'kind': _column_kind(raw),
        'editable': (not hidden and not pk and name not in _LOCK_COLUMNS),
    }


def _model_for_table(table_name):
    try:
        registry = getattr(db.Model, 'registry', None)
        mappers = registry.mappers if registry is not None else []
        for mapper in mappers:
            cls = mapper.class_
            if getattr(cls, '__tablename__', None) == table_name:
                return cls
    except Exception:
        return None
    return None


def _require_table(table_name):
    if not table_name or not _TABLE_NAME_RE.match(table_name):
        raise UnknownTable('That is not a valid table name.')
    if table_name not in _existing_tables():
        raise UnknownTable('This table is not in the current database.')
    inspector = inspect(db.engine)
    raw_cols = inspector.get_columns(table_name)
    col_names = [c['name'] for c in raw_cols]
    pk_info = inspector.get_pk_constraint(table_name) or {}
    pk_cols = [c for c in (pk_info.get('constrained_columns') or []) if c in col_names]
    if not pk_cols:
        raise BrowseError('This table has no primary key, so rows cannot be edited or deleted safely.')
    return raw_cols, col_names, pk_cols


def _normalize_pk(pk, pk_cols):
    if not isinstance(pk, dict) or not pk:
        raise BrowseError('Missing row id.')
    out = {}
    for col in pk_cols:
        if col not in pk or pk[col] in (None, ''):
            raise BrowseError('Missing row id.')
        out[col] = pk[col]
    return out


def _coerce_value(raw, col_meta):
    kind = col_meta.get('kind') or 'text'
    nullable = col_meta.get('nullable', True)
    if raw is None or raw == '':
        if nullable:
            return None
        raise BrowseError(f'{col_meta["label"]} cannot be empty.')
    if kind == 'bool':
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
    if kind == 'number':
        try:
            if isinstance(raw, bool):
                raise ValueError()
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                return int(raw) if float(raw).is_integer() and kind == 'number' and '.' not in str(raw) else raw
            s = str(raw).strip()
            return int(s) if s.isdigit() or (s.startswith('-') and s[1:].isdigit()) else float(s)
        except (TypeError, ValueError):
            raise BrowseError(f'{col_meta["label"]} must be a number.') from None
    if kind == 'date':
        try:
            if isinstance(raw, date) and not isinstance(raw, datetime):
                return raw
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            raise BrowseError(f'{col_meta["label"]} must be a date (YYYY-MM-DD).') from None
    if kind == 'datetime':
        try:
            if isinstance(raw, datetime):
                return raw.replace(tzinfo=None) if raw.tzinfo else raw
            s = str(raw).replace('Z', '').replace('T', ' ').strip()
            return datetime.fromisoformat(s)
        except ValueError:
            raise BrowseError(f'{col_meta["label"]} must be a date and time.') from None
    if kind == 'json':
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            raise BrowseError(f'{col_meta["label"]} must be valid JSON.') from None
    return raw


def _editable_fields(table_name, col_names, pk_cols, fields, *, creating=False):
    if not isinstance(fields, dict):
        raise BrowseError('No fields were sent.')
    raw_cols = inspect(db.engine).get_columns(table_name)
    metas = {c: _column_meta(c, raw_cols, pk_cols) for c in col_names}
    out = {}
    for name, value in fields.items():
        if name not in col_names:
            continue
        meta = metas[name]
        if meta['hidden']:
            continue
        if meta['pk'] and not creating:
            continue
        if meta['pk'] and creating and (value in (None, '')):
            continue
        if not creating and not meta['editable']:
            continue
        if creating and name in _LOCK_COLUMNS and value in (None, ''):
            continue
        out[name] = _coerce_value(value, meta)
    return out, metas


def _load_row(cls, pk):
    q = cls.query.filter_by(**pk)
    return q.first()


def _guard_users_delete_or_demote(table_name, pk, fields, actor_id, deleting):
    if table_name != 'users':
        return
    uid = pk.get('id')
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return
    if deleting and actor_id is not None and int(actor_id) == uid:
        raise BrowseError('You cannot delete your own login.')
    from app.models import User
    target = db.session.get(User, uid)
    if not target:
        raise BrowseError('That login was not found.')
    new_role = (fields or {}).get('role', target.role)
    new_active = (fields or {}).get('is_active', target.is_active)
    becoming_non_admin = deleting or (str(new_role).lower() != 'admin') or (new_active in (False, 0, 'false'))
    if target.role == 'admin' and becoming_non_admin:
        remaining = User.query.filter(User.role == 'admin', User.is_active.is_(True), User.id != uid).count()
        if remaining < 1:
            raise BrowseError('Keep at least one active admin account.')


def update_row(table_name, pk, fields, actor_id=None):
    raw_cols, col_names, pk_cols = _require_table(table_name)
    pk = _normalize_pk(pk, pk_cols)
    coerced, _metas = _editable_fields(table_name, col_names, pk_cols, fields, creating=False)
    if not coerced:
        raise BrowseError('Nothing to save.')
    _guard_users_delete_or_demote(table_name, pk, coerced, actor_id, deleting=False)
    cls = _model_for_table(table_name)
    if cls is None:
        raise BrowseError('This table cannot be edited from the app.')
    obj = _load_row(cls, pk)
    if obj is None:
        raise BrowseError('That row was not found.')
    if table_name == 'users' and 'admin_visible_password' in coerced:
        pwd = coerced.pop('admin_visible_password')
        if pwd not in (None, ''):
            obj.set_password(str(pwd))
    for name, value in coerced.items():
        setattr(obj, name, value)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Database update failed: %s', exc)
        raise BrowseError('Could not save. Another row may already use that value, or a required field is missing.') from exc
    return True


def delete_row(table_name, pk, actor_id=None):
    _raw_cols, _col_names, pk_cols = _require_table(table_name)
    pk = _normalize_pk(pk, pk_cols)
    _guard_users_delete_or_demote(table_name, pk, None, actor_id, deleting=True)
    cls = _model_for_table(table_name)
    if cls is None:
        raise BrowseError('This table cannot be edited from the app.')
    obj = _load_row(cls, pk)
    if obj is None:
        raise BrowseError('That row was not found.')
    try:
        db.session.delete(obj)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Database delete failed: %s', exc)
        raise BrowseError('Could not delete this row because other records still point to it.') from exc
    return True


def insert_row(table_name, fields, actor_id=None):
    raw_cols, col_names, pk_cols = _require_table(table_name)
    coerced, metas = _editable_fields(table_name, col_names, pk_cols, fields or {}, creating=True)
    cls = _model_for_table(table_name)
    if cls is None:
        raise BrowseError('This table cannot be edited from the app.')
    for name, meta in metas.items():
        if meta['pk'] or meta['hidden'] or name in _LOCK_COLUMNS:
            continue
        if not meta['nullable'] and name not in coerced:
            raise BrowseError(f'{meta["label"]} is required.')
    obj = cls()
    if table_name == 'users' and 'admin_visible_password' in coerced:
        pwd = coerced.pop('admin_visible_password') or 'ChangeMe123'
        if hasattr(obj, 'set_password'):
            obj.set_password(str(pwd))
        if 'password_changed' in col_names and 'password_changed' not in coerced:
            obj.password_changed = True
    for name, value in coerced.items():
        setattr(obj, name, value)
    db.session.add(obj)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Database insert failed: %s', exc)
        raise BrowseError('Could not add this row. A required value may be missing, or it duplicates an existing one.') from exc
    return True


def list_backups(limit=25):
    try:
        from sqlalchemy.orm import joinedload
        rows = (
            DatabaseBackup.query
            .options(joinedload(DatabaseBackup.creator))
            .order_by(DatabaseBackup.created_at.desc())
            .limit(limit)
            .all()
        )
        return [row.to_dict() for row in rows]
    except Exception as exc:
        db.session.rollback()
        logger.warning('Could not list database backups: %s', exc)
        return []


def backups_dir():
    from config import BASE_DIR
    path = os.path.join(BASE_DIR, 'backups')
    os.makedirs(path, exist_ok=True)
    return path


def _stamp_filename(env, engine, ext):
    now = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')
    return f'injaaz-{env}-{now}.{ext}'


def _jsonable(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _write_json_gz_export(out_path):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    payload = {
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'environment': current_environment(),
        'engine': current_engine_kind(),
        'tables': {},
    }
    for table in tables:
        try:
            result = db.session.execute(text(f'SELECT * FROM {_quote_ident(table)}'))
            rows = []
            for mapping in result.mappings():
                rows.append({k: _jsonable(v) for k, v in mapping.items()})
            payload['tables'][table] = rows
        except Exception as exc:
            db.session.rollback()
            logger.warning('Skipping table %s in JSON export: %s', table, exc)
            payload['tables'][table] = {'_error': 'could_not_export'}

    raw = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    if len(raw) > MAX_BACKUP_BYTES * 4:
        # Uncompressed JSON can be larger than the DB; still cap the gzip file below.
        pass
    with gzip.open(out_path, 'wb', compresslevel=6) as gz:
        gz.write(raw)
    size = os.path.getsize(out_path)
    if size > MAX_BACKUP_BYTES:
        raise BackupTooLarge(
            f'This database copy is larger than { _format_bytes(MAX_BACKUP_BYTES) }. '
            'Download from the host instead (for example pg_dump on a trusted machine).'
        )
    return size


def _backup_sqlite(dest_path):
    src = _sqlite_path()
    if not src or not os.path.isfile(src):
        # In-memory or missing file — dump schema+rows via SQLAlchemy JSON.
        _write_json_gz_export(dest_path)
        return
    src_conn = sqlite3.connect(src)
    try:
        dest_conn = sqlite3.connect(dest_path)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()
    size = os.path.getsize(dest_path)
    if size > MAX_BACKUP_BYTES:
        raise BackupTooLarge(
            f'This database file is larger than { _format_bytes(MAX_BACKUP_BYTES) }.'
        )


def _pg_dump_to_gzip(dest_path):
    url = _make_url()
    if not url:
        raise BackupError('Could not read the database connection.')
    pg_dump = shutil.which('pg_dump')
    if not pg_dump:
        raise BackupError('pg_dump is not installed on this server.')
    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password
    sslmode = None
    try:
        sslmode = (url.query or {}).get('sslmode')
    except Exception:
        sslmode = None
    if sslmode:
        env['PGSSLMODE'] = sslmode
    cmd = [
        pg_dump,
        '-h', url.host or 'localhost',
        '-p', str(url.port or 5432),
        '-U', url.username or 'postgres',
        '-d', url.database or 'injaaz',
        '--no-owner',
        '--no-acl',
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    written = 0
    try:
        with gzip.open(dest_path, 'wb', compresslevel=6) as gz:
            while True:
                chunk = proc.stdout.read(1024 * 256)
                if not chunk:
                    break
                gz.write(chunk)
                written += len(chunk)
                if written > MAX_BACKUP_BYTES * 3:
                    proc.kill()
                    raise BackupTooLarge(
                        f'This database dump is larger than { _format_bytes(MAX_BACKUP_BYTES) }.'
                    )
        try:
            stderr = proc.stderr.read() if proc.stderr else b''
            proc.wait(timeout=BACKUP_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise BackupError('Backup timed out. Try again or use pg_dump from a trusted machine.')
        if proc.returncode != 0:
            err = (stderr or b'').decode('utf-8', errors='replace')[:400]
            raise BackupError(err.strip() or 'pg_dump failed.')
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(str(exc)[:400]) from exc
    finally:
        if proc.poll() is None:
            proc.kill()
    size = os.path.getsize(dest_path) if os.path.isfile(dest_path) else 0
    if size <= 0:
        raise BackupError('Backup file was empty.')
    if size > MAX_BACKUP_BYTES:
        raise BackupTooLarge(
            f'This database dump is larger than { _format_bytes(MAX_BACKUP_BYTES) }.'
        )


def _alloc_dest(keep, filename):
    if keep:
        return os.path.join(backups_dir(), filename)
    fd, dest = tempfile.mkstemp(prefix='injaaz-db-', suffix='-' + filename)
    os.close(fd)
    return dest


def create_backup_file():
    """
    Write a backup of the current database to a temp (or local backups/) file.

    Returns dict: path, filename, size_bytes, mimetype, keep (True if stored under backups/).
    """
    env = current_environment()
    engine = current_engine_kind()
    size_now = _database_size_bytes()
    if size_now and size_now > MAX_BACKUP_BYTES:
        raise BackupTooLarge(
            f'This database is { _format_bytes(size_now) }, which is over the '
            f'{ _format_bytes(MAX_BACKUP_BYTES) } in-app download limit. '
            'Use a host backup or pg_dump from a trusted machine instead.'
        )

    keep = env == 'local' and not (engine == 'sqlite' and not _sqlite_path())
    dest = None
    try:
        if engine == 'sqlite' and _sqlite_path():
            filename = _stamp_filename(env, engine, 'db')
            mimetype = 'application/x-sqlite3'
            dest = _alloc_dest(keep, filename)
            _backup_sqlite(dest)
        elif engine == 'postgresql' and shutil.which('pg_dump'):
            filename = _stamp_filename(env, engine, 'sql.gz')
            mimetype = 'application/gzip'
            dest = _alloc_dest(keep, filename)
            _pg_dump_to_gzip(dest)
        else:
            filename = _stamp_filename(env, engine, 'json.gz')
            mimetype = 'application/gzip'
            dest = _alloc_dest(keep, filename)
            _write_json_gz_export(dest)
    except Exception:
        if dest and os.path.isfile(dest) and not keep:
            try:
                os.remove(dest)
            except OSError:
                pass
        raise

    size = os.path.getsize(dest) if dest and os.path.isfile(dest) else 0
    return {
        'path': dest,
        'filename': filename,
        'size_bytes': size,
        'mimetype': mimetype,
        'keep': keep,
    }


_WAL_LISTENER_ATTACHED = False


def enable_sqlite_wal():
    """Enable WAL on SQLite connections (safe no-op for Postgres)."""
    global _WAL_LISTENER_ATTACHED
    try:
        if db.engine.dialect.name != 'sqlite':
            return False
        from sqlalchemy import event

        if not _WAL_LISTENER_ATTACHED:
            @event.listens_for(db.engine, 'connect')
            def _sqlite_on_connect(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute('PRAGMA journal_mode=WAL')
                except Exception:
                    pass
                finally:
                    cursor.close()

            _WAL_LISTENER_ATTACHED = True
        with db.engine.connect() as conn:
            conn.exec_driver_sql('PRAGMA journal_mode=WAL')
            try:
                conn.commit()
            except Exception:
                pass
        logger.info('SQLite WAL mode enabled')
        return True
    except Exception as exc:
        logger.warning('Could not enable SQLite WAL: %s', exc)
        return False
