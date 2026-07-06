"""
Ticketing / Work Order module
Handles complaint registration, assignment, progress tracking, cost logging,
closing with signatures, PDF report generation and email notifications.
"""
import os
import uuid
import io
import calendar
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone, date
from decimal import Decimal
from flask import (
    Blueprint, render_template, request, jsonify,
    current_app, send_file, abort
)
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from sqlalchemy.orm import joinedload

from app.models import (
    db, User, Ticket, TicketNote, TicketImage,
    TicketMaterial, TicketManpower, Notification,
    TicketProject, TicketProperty, TicketZone, TicketSubZone,
    TicketBaseUnit, TicketTitleTemplate, TicketSupervisorTeam,
    BDProject,
)

logger = logging.getLogger(__name__)

ticketing_bp = Blueprint('ticketing', __name__, template_folder='templates')


def _tkt_datetime_filter(value, fmt='%d %b %Y, %H:%M'):
    """Format datetime/date for templates; tolerate strings or driver quirks (no .strftime on str)."""
    if value is None:
        return ''
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return ''
        try:
            if 'T' in s or (len(s) >= 10 and s[4:5] == '-' and s[7:8] == '-'):
                iso = s.replace('Z', '+00:00')
                dt = datetime.fromisoformat(iso)
                return dt.strftime(fmt)
        except Exception:
            return s
        return s
    if isinstance(value, datetime):
        try:
            return value.strftime(fmt)
        except Exception:
            return str(value)
    if isinstance(value, date):
        try:
            return value.strftime(fmt)
        except Exception:
            return str(value)
    try:
        return str(value)
    except Exception:
        return ''


_STATUS_LABELS = {
    # v2 canonical
    'open':             'Open',
    'assigned':         'Assigned',
    'site_attended':    'Site Attended',
    'work_started':     'Work Started',
    'work_completed':   'Work Completed',
    'verification':     'Verification',
    'on_hold':          'On Hold',
    'cancelled':        'Cancelled',
    'closed':           'Closed',
    # legacy (v1) — display-only, no new tickets use these
    'pending_supervisor':   'Supervisor Queue',
    'in_progress':          'In Progress',
    'pending_parts':        'Pending Parts',
    'pending_verification': 'Pending Verification',
    'resolved':             'Resolved',
}

ON_HOLD_REASONS = {
    'pending_materials': 'Waiting for Materials',
    'pending_approval':  'Pending Approval',
    'awaiting_client':   'Awaiting Client Response',
    'other':             'Other',
}

CANCEL_REASONS = {
    'duplicate':          'Duplicate ticket',
    'wrong_assignment':   'Wrong assignment',
    'client_request':     'Client request',
    'out_of_scope':       'Out of scope',
    'resolved_elsewhere': 'Resolved elsewhere',
    'no_site_access':     'No site access',
    'other':              'Other',
}

# Statuses that count as "active" (ticket is not done)
_ACTIVE_STATUSES = frozenset({
    'open', 'assigned', 'site_attended', 'work_started', 'work_completed', 'verification', 'on_hold',
    # legacy
    'pending_supervisor', 'in_progress', 'pending_parts', 'pending_verification',
})

_TERMINAL_STATUSES = frozenset({'closed', 'cancelled', 'resolved'})


def _tkt_status_label_filter(status):
    if status is None or status == '':
        return ''
    return _STATUS_LABELS.get(str(status), str(status).replace('_', ' ').strip().title())


@ticketing_bp.record
def _register_ticketing_jinja_filters(state):
    env = state.app.jinja_env
    env.filters['tkt_datetime'] = _tkt_datetime_filter
    env.filters['tkt_status_label'] = _tkt_status_label_filter


def _migrate_ticket_columns(app):
    """Add new supervisor-workflow columns to tickets table if they don't exist yet (SQLite-safe migration)."""
    new_cols = [
        ('supervisor_id',                  'INTEGER'),
        ('technician_id',                  'INTEGER'),
        ('overhead_pct',                   'REAL DEFAULT 10.0'),
        ('markup_pct',                     'REAL'),
        ('actual_price',                   'REAL'),
        ('selling_price',                  'REAL'),
        ('service_report_notes',           'TEXT'),
        ('technician_resolution_notes',    'TEXT'),
        ('supervisor_verification_notes',  'TEXT'),
        # v2 workflow columns
        ('on_hold_reason',                 'TEXT'),
        ('cancelled_reason',               'TEXT'),
        ('cancelled_at',                   'TEXT'),
        ('previous_status',                'TEXT'),
        ('site_attended_at',               'TEXT'),
        ('work_started_at',                'TEXT'),
        ('work_completed_at',              'TEXT'),
    ]
    with app.app_context():
        from app.models import db
        try:
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            from sqlalchemy import inspect as _sa_inspect
            existing = {c['name'] for c in _sa_inspect(db.engine).get_columns('tickets')}
            for col_name, col_type in new_cols:
                if col_name not in existing:
                    try:
                        cursor.execute(f'ALTER TABLE tickets ADD COLUMN {col_name} {col_type}')
                        logger.info('Added column tickets.%s', col_name)
                    except Exception as exc:
                        logger.warning('Could not add column %s: %s', col_name, exc)
            conn.commit()
            conn.close()

            # Create TicketSupervisorTeam table if not exists
            db.create_all()
        except Exception as exc:
            logger.warning('Ticket migration warning: %s', exc)


def _migrate_ticket_project_columns(app):
    """Add ticketing project columns (SQLite-safe PRAGMA + ALTER)."""
    ticket_project_cols = [
        ('supervisor_id', 'INTEGER REFERENCES users(id)'),
        ('bd_project_id', 'INTEGER'),
        ('project_end_date', 'DATE'),
        ('renewal_date', 'DATE'),
        ('project_value', 'REAL'),
    ]
    with app.app_context():
        try:
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            from sqlalchemy import inspect as _sa_inspect
            existing = {c['name'] for c in _sa_inspect(db.engine).get_columns('ticket_projects')}
            for col_name, col_sql in ticket_project_cols:
                if col_name not in existing:
                    try:
                        cursor.execute(f'ALTER TABLE ticket_projects ADD COLUMN {col_name} {col_sql}')
                        logger.info('Added column ticket_projects.%s', col_name)
                    except Exception as exc:
                        logger.warning('Could not add ticket_projects.%s: %s', col_name, exc)
            conn.commit()
            conn.close()
            db.create_all()
        except Exception as exc:
            logger.warning('Ticket project migration warning: %s', exc)


@ticketing_bp.record_once
def _on_register(state):
    """Run column migrations when the blueprint is first registered."""
    _migrate_ticket_columns(state.app)
    _migrate_ticket_project_columns(state.app)


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'heif'}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_user():
    uid = get_jwt_identity()
    if uid is None:
        return None
    try:
        return db.session.get(User, int(uid))
    except (TypeError, ValueError):
        return None



def _has_access(user: User) -> bool:
    if user is None:
        return False
    return bool(user.role == 'admin' or getattr(user, 'access_ticketing', False))


# Designations that may see every ticket (read + list) like admins.
_TICKETING_OVERWATCH_DESIGNATIONS = frozenset({'operations_manager', 'general_manager'})


def _ticketing_sees_all_tickets(user: User) -> bool:
    """Admin, Operations Manager, or General Manager — full visibility across ticketing."""
    if user is None:
        return False
    if user.role == 'admin':
        return True
    des = (getattr(user, 'designation', None) or '').strip().lower()
    return des in _TICKETING_OVERWATCH_DESIGNATIONS


def _user_in_supervisor_pool(user: User) -> bool:
    """Eligible to open and act on tickets in the shared supervisor queue."""
    if user is None:
        return False
    des = (getattr(user, 'designation', None) or '').strip().lower()
    if des == 'supervisor':
        return True
    return TicketSupervisorTeam.query.filter_by(supervisor_id=user.id, is_active=True).first() is not None


def _ticket_visibility_or_clause(user: User):
    """SQL filter: tickets a non-overwatch user may list or count."""
    clauses = [
        Ticket.reporter_id == user.id,
        Ticket.assigned_to_id == user.id,
        Ticket.supervisor_id == user.id,
        Ticket.technician_id == user.id,
    ]
    if _user_in_supervisor_pool(user):
        # Shared supervisor queue: open/pending only when unassigned or assigned to this user
        clauses.append(
            db.and_(
                Ticket.status.in_(('pending_supervisor', 'open')),
                db.or_(Ticket.assigned_to_id.is_(None), Ticket.assigned_to_id == user.id),
            )
        )
    return db.or_(*clauses)


def _visible_tickets_base_query(user: User):
    q = Ticket.query
    if not _ticketing_sees_all_tickets(user):
        q = q.filter(_ticket_visibility_or_clause(user))
    return q


def _can_user_view_ticket(user: User, ticket: Ticket) -> bool:
    if _ticketing_sees_all_tickets(user):
        return True
    if (
        ticket.reporter_id == user.id
        or ticket.assigned_to_id == user.id
        or ticket.supervisor_id == user.id
        or ticket.technician_id == user.id
    ):
        return True
    if ticket.status in ('pending_supervisor', 'open') and _user_in_supervisor_pool(user):
        if ticket.assigned_to_id is None or ticket.assigned_to_id == user.id:
            return True
        return False
    return False


def _api_forbid_unless_ticket_visible(user: User, ticket: Ticket):
    if not _can_user_view_ticket(user, ticket):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return None



def _generate_ticket_id() -> str:
    return 'TKT-' + uuid.uuid4().hex[:8].upper()


def _allowed_image(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _ticket_images_dir() -> str:
    base = current_app.config.get('UPLOADS_DIR', 'uploads')
    d = os.path.join(base, 'ticket_images')
    os.makedirs(d, exist_ok=True)
    return d


def _recalc_total_cost(ticket: Ticket):
    """Re-compute ticket.total_cost, actual_price, and selling_price from manpower + materials."""
    mp_total  = sum((e.total_cost  or 0) for e in ticket.manpower.all())
    mat_total = sum((m.total_price or 0) for m in ticket.materials.all())
    base_cost = round(mp_total + mat_total, 2)
    ticket.total_cost = base_cost

    overhead = ticket.overhead_pct if ticket.overhead_pct is not None else 10.0
    actual = round(base_cost * (1 + overhead / 100.0), 2)
    ticket.actual_price = actual

    if ticket.markup_pct is not None:
        ticket.selling_price = round(actual * (1 + ticket.markup_pct / 100.0), 2)
    else:
        ticket.selling_price = None


def _is_supervisor_of_ticket(user: User) -> bool:
    """True if this user is designated as a supervisor (has a team or designation)."""
    if user is None:
        return False
    if user.role == 'admin':
        return True
    des = (getattr(user, 'designation', None) or '').strip().lower()
    return (
        des == 'supervisor'
        or TicketSupervisorTeam.query.filter_by(supervisor_id=user.id, is_active=True).first() is not None
    )


def _get_supervisor_team(supervisor_id: int) -> list:
    """Return active team members for the given supervisor."""
    entries = TicketSupervisorTeam.query.filter_by(supervisor_id=supervisor_id, is_active=True).all()
    return entries


def _ticket_roster_fallback_workers():
    rows = []
    for d in _dummy_technicians():
        rows.append({
            'user_id': None,
            'team_entry_id': None,
            'code': d['code'],
            'name': d['name'],
            'speciality': d['speciality'],
            'sidebar_row_id': d['code'],
        })
    return rows


def _ticketing_team_workers_for_sidebar(supervisor_id: int) -> list:
    """Sidebar / assign picker rows from supervisor team Users."""
    rows = []
    for entry in _get_supervisor_team(supervisor_id):
        tu = entry.tech_user
        if tu is None or not getattr(tu, 'is_active', True):
            continue
        speciality = (getattr(tu, 'job_designation', None) or '').strip() or 'Field technician'
        rows.append({
            'user_id': tu.id,
            'team_entry_id': entry.id,
            'code': tu.username or f'USER-{tu.id}',
            'name': tu.full_name or tu.username,
            'speciality': speciality,
            'sidebar_row_id': f'uid-{tu.id}',
        })
    return rows


def _ticketing_worker_pick_list(roster_supervisor_user_id):
    """Prefer DB team for this supervisor account; fallback static demo roster."""
    if roster_supervisor_user_id:
        real = _ticketing_team_workers_for_sidebar(roster_supervisor_user_id)
        if real:
            return real
    return _ticket_roster_fallback_workers()


def _technician_users_available_for_team_add(supervisor_id: int):
    excluded = (
        db.session.query(TicketSupervisorTeam.technician_id)
        .filter(TicketSupervisorTeam.supervisor_id == supervisor_id, TicketSupervisorTeam.is_active == True)  # noqa: E712
        .distinct()
        .all()
    )
    ex = [r[0] for r in excluded]
    q = User.query.filter(User.designation == 'technician', User.is_active == True)  # noqa: E712
    if ex:
        q = q.filter(~User.id.in_(ex))
    return q.order_by(User.full_name).all()


def _is_ticket_assignment_supervisor(u: User) -> bool:
    """True if this account may appear in Assign To (supervisor designation or team lead)."""
    if u is None or not getattr(u, 'is_active', False):
        return False
    if (getattr(u, 'designation', None) or '').strip().lower() == 'supervisor':
        return True
    if TicketSupervisorTeam.query.filter_by(supervisor_id=u.id, is_active=True).first() is not None:
        return True
    return False


def _supervisor_assignees_query():
    """Active users who can be selected as ticket assignees (supervisor accounts only)."""
    team_lead_ids = (
        db.session.query(TicketSupervisorTeam.supervisor_id)
        .filter(TicketSupervisorTeam.is_active == True)  # noqa: E712
        .distinct()
    )
    return (
        User.query.filter(
            User.is_active == True,  # noqa: E712
            db.or_(User.designation == 'supervisor', User.id.in_(team_lead_ids)),
        )
        .order_by(User.full_name)
        .all()
    )


def _supervisor_assignees_for_dropdown(extra_user=None) -> list:
    """
    Ordered list of supervisor accounts for Assign To dropdowns.
    If extra_user is set and not already in the list, append (stale / legacy assignment still visible).
    """
    rows = _supervisor_assignees_query()
    if extra_user and extra_user.is_active and _is_ticket_assignment_supervisor(extra_user) is False:
        ids = {r.id for r in rows}
        if extra_user.id not in ids:
            rows = list(rows) + [extra_user]
            rows.sort(key=lambda u: (u.full_name or '').lower())
    return rows


def _resolve_project_supervisor_id(project_name: str) -> int | None:
    """Return the ticketing supervisor user id for a configured project name, if any."""
    if not project_name:
        return None
    pn = project_name.strip()
    low = pn.lower()
    if low in ('', 'standalone location'):
        return None
    tp = (
        TicketProject.query.filter(
            db.func.lower(TicketProject.name) == low,
            TicketProject.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not tp or not tp.supervisor_id:
        return None
    u = db.session.get(User, tp.supervisor_id)
    if not u or not u.is_active or not _is_ticket_assignment_supervisor(u):
        return None
    return tp.supervisor_id


def _apply_ticket_project_routing(ticket: Ticket) -> int | None:
    """Set assigned_to_id / supervisor_id from project settings. Returns supervisor id or None."""
    sid = _resolve_project_supervisor_id(ticket.project or '')
    if sid:
        ticket.assigned_to_id = sid
        ticket.supervisor_id = sid
    else:
        ticket.assigned_to_id = None
        ticket.supervisor_id = None
    return sid


def _get_sidebar_stats(user: User) -> dict:
    """Return lightweight ticket counts for the sidebar badges."""
    q = _visible_tickets_base_query(user)
    statuses = [t[0] for t in q.with_entities(Ticket.status).all()]
    active_ct = sum(1 for s in statuses if s in _ACTIVE_STATUSES)
    return {
        'total':            len(statuses),
        'active':           active_ct,
        'open':             statuses.count('open'),
        'assigned':         statuses.count('assigned'),
        'site_attended':    statuses.count('site_attended'),
        'work_started':     statuses.count('work_started'),
        'work_completed':   statuses.count('work_completed'),
        'verification':     statuses.count('verification'),
        'on_hold':          statuses.count('on_hold'),
        'cancelled':        statuses.count('cancelled'),
        'closed':           statuses.count('closed'),
        # legacy
        'in_progress':          statuses.count('in_progress'),
        'pending_supervisor':   statuses.count('pending_supervisor'),
        'pending_parts':        statuses.count('pending_parts'),
        'pending_verification': statuses.count('pending_verification'),
        'resolved':             statuses.count('resolved'),
    }


def _dummy_technicians() -> list:
    """Separate demo technician pool (independent from user/team management)."""
    return [
        {'code': 'TECH-001', 'name': 'Arshith Swaminath P', 'speciality': 'HVAC'},
        {'code': 'TECH-002', 'name': 'Fatima Noor', 'speciality': 'Electrical'},
        {'code': 'TECH-003', 'name': 'Mohamed Fawaz', 'speciality': 'Plumbing'},
        {'code': 'TECH-004', 'name': 'Rafiq Ali', 'speciality': 'Civil'},
        {'code': 'TECH-005', 'name': 'Shamnad K', 'speciality': 'Cleaning'},
        {'code': 'TECH-006', 'name': 'Jerin Thomas', 'speciality': 'General Maintenance'},
    ]


def _add_note(ticket: Ticket, user: User, content: str, note_type: str = 'note'):
    note = TicketNote(
        ticket_id=ticket.id,
        user_id=user.id,
        content=content,
        note_type=note_type,
    )
    db.session.add(note)


def _notify_user(user_id: int, title: str, message: str, ntype: str = 'info', ticket_id: str = None):
    n = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=ntype,
        submission_id=ticket_id,
    )
    db.session.add(n)


def _supervisor_queue_broadcast_recipient_ids() -> set[int]:
    """IDs to notify when a ticket enters or re-enters the shared supervisor queue."""
    ids: set[int] = set()
    for u in User.query.filter(User.designation == 'supervisor', User.is_active == True):  # noqa: E712
        ids.add(u.id)
    for row in (
        db.session.query(TicketSupervisorTeam.supervisor_id)
        .filter(TicketSupervisorTeam.is_active == True)  # noqa: E712
        .distinct()
    ):
        ids.add(row[0])
    for u in User.query.filter(User.role == 'admin', User.is_active == True):  # noqa: E712
        ids.add(u.id)
    for des in _TICKETING_OVERWATCH_DESIGNATIONS:
        for u in User.query.filter(User.designation == des, User.is_active == True):  # noqa: E712
            ids.add(u.id)
    return ids


def _notify_supervisor_queue_ticket(ticket: Ticket, body: str):
    title = f'Work Order Queued: {ticket.ticket_id}'
    if ticket.assigned_to_id:
        assignee = db.session.get(User, ticket.assigned_to_id)
        if assignee and assignee.is_active and _is_ticket_assignment_supervisor(assignee):
            _notify_user(ticket.assigned_to_id, title, body, ntype='info', ticket_id=ticket.ticket_id)
            return
    for uid in _supervisor_queue_broadcast_recipient_ids():
        _notify_user(uid, title, body, ntype='info', ticket_id=ticket.ticket_id)


def _send_ticket_email(subject: str, recipients: list, body_html: str):
    """Best-effort email via common email_service."""
    try:
        from common.email_service import send_email
        for recipient in recipients:
            if recipient:
                send_email(to_email=recipient, subject=subject, html_body=body_html)
    except Exception as exc:
        logger.warning("Ticket email send failed: %s", exc)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@ticketing_bp.route('/', methods=['GET'])
@jwt_required()
def dashboard():
    user = _current_user()
    if not _has_access(user):
        abort(403)

    # Stats
    all_tickets = _visible_tickets_base_query(user).order_by(Ticket.created_at.desc())

    tickets_q = all_tickets.all()
    total_ct = len(tickets_q)
    closed_ct = sum(1 for t in tickets_q if t.status == 'closed')
    resolved_ct = sum(1 for t in tickets_q if t.status == 'resolved')
    completed_ct = closed_ct + resolved_ct  # work finished (may still await sign-off)

    stats = {
        'total': total_ct,
        'open': sum(1 for t in tickets_q if t.status == 'open'),
        'pending_supervisor': sum(1 for t in tickets_q if t.status == 'pending_supervisor'),
        'in_progress': sum(1 for t in tickets_q if t.status == 'in_progress'),
        'pending_verification': sum(1 for t in tickets_q if t.status == 'pending_verification'),
        'resolved': resolved_ct,
        'closed': closed_ct,
        'pending_parts': sum(1 for t in tickets_q if t.status == 'pending_parts'),
        'critical': sum(1 for t in tickets_q if t.priority == 'critical'),
        'high': sum(1 for t in tickets_q if t.priority == 'high'),
        # Donut / headline: % fully closed vs all tickets in view
        'closed_pct': int(round(100.0 * closed_ct / total_ct)) if total_ct else 0,
        # Optional: resolved + closed as % of total (work completed, not necessarily signed closed)
        'completed_pct': int(round(100.0 * completed_ct / total_ct)) if total_ct else 0,
    }

    recent = tickets_q[:10]
    all_users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    return render_template(
        'ticket_dashboard.html',
        user=user,
        stats=stats,
        sidebar_stats=stats,
        recent_tickets=recent,
        all_users=all_users,
        active_page='ticketing',
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@ticketing_bp.route('/list', methods=['GET'])
@jwt_required()
def ticket_list():
    user = _current_user()
    if not _has_access(user):
        abort(403)

    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    project_filter = request.args.get('project', '')
    search = request.args.get('q', '').strip()

    q = _visible_tickets_base_query(user)
    if status_filter:
        q = q.filter(Ticket.status == status_filter)
    if priority_filter:
        q = q.filter(Ticket.priority == priority_filter)
    if project_filter:
        q = q.filter(Ticket.project.ilike(f'%{project_filter}%'))
    if search:
        q = q.filter(
            db.or_(
                Ticket.title.ilike(f'%{search}%'),
                Ticket.ticket_id.ilike(f'%{search}%'),
                Ticket.work_description.ilike(f'%{search}%'),
            )
        )

    tickets = q.order_by(Ticket.created_at.desc()).all()
    all_users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    # Unique projects for filter dropdown (within this user's visibility)
    projects = sorted(
        {
            p[0]
            for p in _visible_tickets_base_query(user).with_entities(Ticket.project).distinct()
            if p[0]
        }
    )

    return render_template(
        'ticket_list.html',
        user=user,
        tickets=tickets,
        all_users=all_users,
        projects=projects,
        status_filter=status_filter,
        priority_filter=priority_filter,
        project_filter=project_filter,
        search=search,
        sidebar_stats=_get_sidebar_stats(user),
        active_page='ticketing',
    )


# ---------------------------------------------------------------------------
# New ticket form
# ---------------------------------------------------------------------------

@ticketing_bp.route('/new', methods=['GET'])
@jwt_required()
def new_ticket_form():
    user = _current_user()
    if not _has_access(user):
        abort(403)

    all_users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    # Fetch procurement catalog materials for autocomplete
    procurement_materials = _get_procurement_materials()

    return render_template(
        'ticket_new.html',
        user=user,
        all_users=all_users,
        procurement_materials=procurement_materials,
        sidebar_stats=_get_sidebar_stats(user),
        active_page='ticketing',
    )


# ---------------------------------------------------------------------------
# Create ticket (API)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets', methods=['POST'])
@jwt_required()
def create_ticket():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}

    required = ['title', 'project', 'service_group', 'category', 'fault_type', 'priority', 'work_description']
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({'success': False, 'error': f'Field "{field}" is required'}), 400

    proj_supervisor_id = _resolve_project_supervisor_id(data['project'].strip())

    ticket = Ticket(
        ticket_id=_generate_ticket_id(),
        reporter_id=user.id,
        assigned_to_id=proj_supervisor_id,
        supervisor_id=proj_supervisor_id,
        title=data['title'].strip(),
        project=data['project'].strip(),
        service_group=data['service_group'].strip(),
        category=data['category'].strip(),
        fault_type=data['fault_type'].strip(),
        priority=data['priority'].strip(),
        work_description=data['work_description'].strip(),
        property_name=data.get('property_name', '').strip() or None,
        zone=data.get('zone', '').strip() or None,
        sub_zone=data.get('sub_zone', '').strip() or None,
        base_unit=data.get('base_unit', '').strip() or None,
        is_chargeable=bool(data.get('is_chargeable', False)),
        projected_cost=float(data['projected_cost']) if data.get('projected_cost') else None,
        status='pending_supervisor',
    )
    db.session.add(ticket)
    db.session.flush()  # get ticket.id

    route_sup = db.session.get(User, proj_supervisor_id) if proj_supervisor_id else None
    route_bit = (
        f' Routed to project supervisor {route_sup.full_name}.'
        if route_sup
        else ' Queued in the shared supervisor pool (no project supervisor configured).'
    )
    _add_note(
        ticket,
        user,
        f'Ticket created by {user.full_name}; queued for supervisor routing (no technician yet).{route_bit}',
        note_type='status_change',
    )

    _notify_supervisor_queue_ticket(
        ticket,
        f'Ticket {ticket.ticket_id} — "{ticket.title}" is in the supervisor queue for technician assignment.',
    )

    db.session.commit()
    return jsonify({'success': True, 'ticket_id': ticket.ticket_id, 'id': ticket.id}), 201


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------

@ticketing_bp.route('/<string:ticket_id>', methods=['GET'])
@jwt_required()
def ticket_detail(ticket_id):
    user = _current_user()
    if not _has_access(user):
        abort(403)

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if not _can_user_view_ticket(user, ticket):
        abort(403)

    notes = ticket.notes.order_by(TicketNote.created_at.asc()).all()
    images = ticket.images.all()
    materials = ticket.materials.all()
    manpower_entries = ticket.manpower.all()
    sees_all = _ticketing_sees_all_tickets(user)
    supervisor_assignees = _supervisor_assignees_for_dropdown(ticket.assigned_to) if sees_all else []
    procurement_materials = _get_procurement_materials()

    mat_total = sum(m.total_price or 0 for m in materials)
    mp_total  = sum(e.total_cost or 0 for e in manpower_entries)

    # Supervisor workflow context
    user_is_supervisor = _is_supervisor_of_ticket(user)
    roster_for_picks = ticket.supervisor_id if ticket.supervisor_id else (user.id if user_is_supervisor else None)

    ticket_sidebar_team = _ticketing_team_workers_for_sidebar(user.id) if user_is_supervisor else []
    if user_is_supervisor and not ticket_sidebar_team:
        ticket_sidebar_team = _ticket_roster_fallback_workers()

    worker_pick_list = _ticketing_worker_pick_list(roster_for_picks)
    technician_users_for_team_add = _technician_users_available_for_team_add(user.id) if user_is_supervisor else []

    # Pricing preview
    overhead = ticket.overhead_pct if ticket.overhead_pct is not None else 10.0
    base_cost   = mp_total + mat_total
    actual_price = round(base_cost * (1 + overhead / 100.0), 2)

    return render_template(
        'ticket_detail.html',
        user=user,
        ticket=ticket,
        notes=notes,
        images=images,
        materials=materials,
        manpower_entries=manpower_entries,
        mat_total=mat_total,
        mp_total=mp_total,
        supervisor_assignees=supervisor_assignees,
        ticketing_sees_all=sees_all,
        procurement_materials=procurement_materials,
        user_is_supervisor=user_is_supervisor,
        ticket_sidebar_team=ticket_sidebar_team,
        worker_pick_list=worker_pick_list,
        technician_users_for_team_add=technician_users_for_team_add,
        supervisor_team=[],  # legacy template var (unused)
        base_cost=base_cost,
        actual_price=actual_price,
        sidebar_stats=_get_sidebar_stats(user),
        active_page='ticketing',
    )


# ---------------------------------------------------------------------------
# Update status
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/status', methods=['POST'])
@jwt_required()
def update_status(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if not (_ticketing_sees_all_tickets(user) or _is_supervisor_of_ticket(user)):
        return jsonify({
            'success': False,
            'error': 'Only supervisors or OPS / GM / Admin may set status from this control.',
        }), 403

    data = request.get_json(silent=True) or {}
    new_status = data.get('status', '').strip()

    valid = {
        'open', 'assigned', 'site_attended', 'work_started', 'work_completed',
        'verification', 'on_hold', 'closed', 'cancelled',
        # legacy passthrough
        'in_progress', 'pending_parts', 'pending_supervisor', 'pending_verification', 'resolved',
    }
    if new_status not in valid:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    old_status = ticket.status
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    # Normalize legacy → canonical for storage
    legacy_map = {
        'in_progress': 'work_started',
        'pending_supervisor': 'open',
        'pending_verification': 'verification',
        'pending_parts': 'work_started',
    }
    store_status = legacy_map.get(new_status, new_status)

    if store_status == 'cancelled':
        reason_key = (data.get('cancelled_reason') or data.get('reason') or 'other').strip()
        if reason_key not in CANCEL_REASONS:
            reason_key = 'other'
        ticket.status = 'cancelled'
        ticket.cancelled_reason = reason_key
        ticket.cancelled_at = now_naive.isoformat()
        ticket.on_hold_reason = None
        ticket.previous_status = None
    else:
        ticket.status = store_status

        if old_status == 'on_hold' and store_status != 'on_hold':
            ticket.on_hold_reason = None
            ticket.previous_status = None

        if store_status == 'on_hold' and old_status != 'on_hold':
            ticket.previous_status = old_status
            hold_r = (data.get('on_hold_reason') or 'other').strip()
            if hold_r not in ON_HOLD_REASONS:
                hold_r = 'other'
            ticket.on_hold_reason = hold_r

        if store_status not in ('cancelled', 'closed'):
            ticket.cancelled_reason = None
            ticket.cancelled_at = None

    if new_status == 'resolved' and not ticket.resolved_at:
        ticket.resolved_at = now_naive
    if (store_status == 'closed' or new_status == 'closed') and not ticket.closed_at:
        ticket.closed_at = now_naive
    if store_status == 'closed':
        if not ticket.resolved_at:
            ticket.resolved_at = ticket.closed_at

    _add_note(
        ticket,
        user,
        f'Status changed from "{old_status}" to "{ticket.status}".',
        note_type='status_change',
    )

    comment = (data.get('comment') or '').strip()
    if comment:
        _add_note(ticket, user, comment, note_type='note')

    db.session.commit()
    return jsonify({'success': True, 'status': ticket.status})


@ticketing_bp.route('/api/tickets/<string:ticket_id>/reopen', methods=['POST'])
@jwt_required()
def reopen_ticket(ticket_id):
    """Move a finished ticket back to Open so the workflow can continue."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    if ticket.status not in ('closed', 'resolved', 'cancelled'):
        return jsonify({
            'success': False,
            'error': f'Only closed, resolved, or cancelled tickets can be reopened (current: {ticket.status}).',
        }), 400

    old_status = ticket.status
    ticket.status = 'open'
    ticket.closed_at = None
    ticket.resolved_at = None
    ticket.cancelled_at = None
    ticket.cancelled_reason = None
    ticket.previous_status = None

    data = request.get_json(silent=True) or {}
    comment = (data.get('reason') or data.get('comment') or '').strip()
    _add_note(
        ticket,
        user,
        f'Ticket reopened from "{old_status}" to "open" by {user.full_name}.',
        note_type='status_change',
    )
    if comment:
        _add_note(ticket, user, comment, note_type='note')

    db.session.commit()
    return jsonify({'success': True, 'status': 'open'})


# ---------------------------------------------------------------------------
# Assign ticket
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/assign', methods=['POST'])
@jwt_required()
def assign_ticket(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if not _ticketing_sees_all_tickets(user):
        return jsonify({
            'success': False,
            'error': (
                'Only Admin, Operations Manager, or General Manager may override supervisor routing here. '
                'Supervisors assign technicians from their team via Assign Technician.'
            ),
        }), 403

    data = request.get_json(silent=True) or {}
    assignee_id = data.get('assigned_to_id')

    if assignee_id:
        assignee = db.session.get(User, int(assignee_id))
        if not assignee:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        if not _is_ticket_assignment_supervisor(assignee):
            return jsonify({'success': False, 'error': 'Assignment is limited to supervisor accounts.'}), 400
        ticket.assigned_to_id = assignee.id
        _add_note(ticket, user, f'Assigned to {assignee.full_name}.', note_type='assignment')
        _notify_user(assignee.id, f'Ticket assigned: {ticket.ticket_id}',
                     f'You have been assigned ticket {ticket.ticket_id}: {ticket.title}',
                     ntype='info', ticket_id=ticket.ticket_id)
    else:
        ticket.assigned_to_id = None
        _add_note(ticket, user, 'Ticket unassigned.', note_type='assignment')

    db.session.commit()
    return jsonify({'success': True, 'assigned_to_name': ticket.assigned_to.full_name if ticket.assigned_to else None})


# ---------------------------------------------------------------------------
# Add note
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/notes', methods=['POST'])
@jwt_required()
def add_note(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'error': 'Note cannot be empty'}), 400

    note = TicketNote(
        ticket_id=ticket.id,
        user_id=user.id,
        content=content,
        note_type='note',
    )
    db.session.add(note)
    db.session.commit()

    return jsonify({'success': True, 'note': note.to_dict()})


# ---------------------------------------------------------------------------
# Upload image
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/images', methods=['POST'])
@jwt_required()
def upload_image(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400

    f = request.files['image']
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'Empty file'}), 400
    if not _allowed_image(f.filename):
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400

    ext = f.filename.rsplit('.', 1)[1].lower()
    safe_name = f'{ticket.ticket_id}_{uuid.uuid4().hex[:8]}.{ext}'
    save_dir = _ticket_images_dir()
    save_path = os.path.join(save_dir, safe_name)
    f.save(save_path)

    caption = (request.form.get('caption') or '').strip() or None

    img = TicketImage(
        ticket_id=ticket.id,
        filename=safe_name,
        file_path=save_path,
        cloud_url=None,
        caption=caption,
        uploaded_by=user.id,
    )
    db.session.add(img)
    _add_note(ticket, user, f'Image uploaded: {f.filename}.', note_type='image')
    db.session.commit()

    return jsonify({'success': True, 'image': img.to_dict()})


# ---------------------------------------------------------------------------
# Serve image
# ---------------------------------------------------------------------------

@ticketing_bp.route('/images/<int:image_id>', methods=['GET'])
@jwt_required()
def serve_image(image_id):
    user = _current_user()
    if not _has_access(user):
        abort(403)
    img = db.session.get(TicketImage, image_id)
    if not img:
        abort(404)
    ticket = getattr(img, 'ticket', None)
    if not ticket or not _can_user_view_ticket(user, ticket):
        abort(403)
    if not os.path.exists(img.file_path):
        abort(404)
    return send_file(img.file_path)


# ---------------------------------------------------------------------------
# Add manpower entry
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/manpower', methods=['POST'])
@jwt_required()
def add_manpower(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    data = request.get_json(silent=True) or {}

    worker_name = (data.get('worker_name') or '').strip()
    if not worker_name:
        return jsonify({'success': False, 'error': 'Worker name required'}), 400

    hours_val = data.get('hours')
    try:
        hours = float(hours_val)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid hours value'}), 400

    rate = float(data['rate_per_hour']) if data.get('rate_per_hour') else None
    total = round(hours * rate, 2) if rate else None

    work_date_str = data.get('work_date')
    work_date = None
    if work_date_str:
        try:
            work_date = date.fromisoformat(work_date_str)
        except ValueError:
            pass

    worker_user_id = data.get('worker_user_id')
    if worker_user_id:
        worker_user_id = int(worker_user_id)

    entry = TicketManpower(
        ticket_id=ticket.id,
        worker_name=worker_name,
        worker_user_id=worker_user_id or None,
        hours=hours,
        rate_per_hour=rate,
        total_cost=total,
        work_date=work_date,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(entry)
    _recalc_total_cost(ticket)
    db.session.commit()

    return jsonify({'success': True, 'entry': entry.to_dict(), 'total_cost': ticket.total_cost})


# ---------------------------------------------------------------------------
# Delete manpower entry
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/manpower/<int:entry_id>', methods=['DELETE'])
@jwt_required()
def delete_manpower(ticket_id, entry_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    entry = db.session.get(TicketManpower, entry_id)
    if not entry or entry.ticket_id != ticket.id:
        abort(404)

    db.session.delete(entry)
    _recalc_total_cost(ticket)
    db.session.commit()
    return jsonify({'success': True, 'total_cost': ticket.total_cost})


# ---------------------------------------------------------------------------
# Add material
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/materials', methods=['POST'])
@jwt_required()
def add_material(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    data = request.get_json(silent=True) or {}

    name = (data.get('material_name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Material name required'}), 400

    try:
        qty = float(data.get('quantity', 1))
        unit_price = float(data.get('unit_price', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid quantity or unit price'}), 400

    mat = TicketMaterial(
        ticket_id=ticket.id,
        material_name=name,
        quantity=qty,
        unit=(data.get('unit') or '').strip() or None,
        unit_price=unit_price,
        total_price=round(qty * unit_price, 2),
        from_procurement=bool(data.get('from_procurement', False)),
        procurement_ref=(data.get('procurement_ref') or '').strip() or None,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(mat)
    _recalc_total_cost(ticket)
    db.session.commit()

    return jsonify({'success': True, 'material': mat.to_dict(), 'total_cost': ticket.total_cost})


# ---------------------------------------------------------------------------
# Bulk add materials (from catalog picker)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/materials/bulk', methods=['POST'])
@jwt_required()
def add_materials_bulk(ticket_id):
    """Add multiple catalog materials in one call (from MaterialsPicker selection)."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])

    if not items or not isinstance(items, list):
        return jsonify({'success': False, 'error': 'items array required'}), 400

    added = []
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        try:
            qty = float(item.get('quantity', 1))
            unit_price = float(item.get('unit_price', 0))
        except (TypeError, ValueError):
            qty, unit_price = 1.0, 0.0

        mat = TicketMaterial(
            ticket_id=ticket.id,
            material_name=name,
            quantity=qty,
            unit=(item.get('uom') or item.get('unit') or '').strip() or None,
            unit_price=unit_price,
            total_price=round(qty * unit_price, 2),
            from_procurement=True,
            procurement_ref=(item.get('id') or '').strip() or None,
            notes=(item.get('brand') or '').strip() or None,
        )
        db.session.add(mat)
        added.append(mat)

    _recalc_total_cost(ticket)
    db.session.commit()

    return jsonify({
        'success': True,
        'added': len(added),
        'materials': [m.to_dict() for m in added],
        'total_cost': ticket.total_cost,
        'actual_price': ticket.actual_price,
    })


# ---------------------------------------------------------------------------
# Delete material
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/materials/<int:mat_id>', methods=['DELETE'])
@jwt_required()
def delete_material(ticket_id, mat_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    mat = db.session.get(TicketMaterial, mat_id)
    if not mat or mat.ticket_id != ticket.id:
        abort(404)

    db.session.delete(mat)
    _recalc_total_cost(ticket)
    db.session.commit()
    return jsonify({'success': True, 'total_cost': ticket.total_cost})


# ---------------------------------------------------------------------------
# Close ticket (with signature)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/close', methods=['POST'])
@jwt_required()
def close_ticket(ticket_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    data = request.get_json(silent=True) or {}

    signature = (data.get('signature') or '').strip()
    signed_by = (data.get('signed_by') or '').strip()
    signed_role = (data.get('signed_role') or '').strip()
    close_notes = (data.get('close_notes') or '').strip() or None

    if not signature:
        return jsonify({'success': False, 'error': 'Signature is required to close ticket'}), 400
    if not signed_by:
        return jsonify({'success': False, 'error': 'Signer name is required'}), 400

    ticket.status = 'closed'
    ticket.close_signature = signature
    ticket.close_signed_by = signed_by
    ticket.close_signed_role = signed_role
    ticket.close_notes = close_notes
    ticket.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if not ticket.resolved_at:
        ticket.resolved_at = ticket.closed_at

    _recalc_total_cost(ticket)
    _add_note(ticket, user,
              f'Ticket closed and signed by {signed_by} ({signed_role}).',
              note_type='status_change')

    db.session.commit()

    # Send completion emails
    _send_completion_emails(ticket, user)

    return jsonify({'success': True, 'ticket_id': ticket.ticket_id})


# ---------------------------------------------------------------------------
# Technician self-service: advance status
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/advance', methods=['POST'])
@jwt_required()
def advance_ticket(ticket_id):
    """
    Technician-facing linear progress: assigned → site_attended → work_started → work_completed.
    Supervisor / overwatch can also call this.
    """
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    # Who can advance?
    is_tech = (ticket.technician_id == user.id or ticket.assigned_to_id == user.id)
    if not is_tech and not _ticketing_sees_all_tickets(user) and not _is_supervisor_of_ticket(user):
        return jsonify({'success': False, 'error': 'Only the assigned technician or supervisor may advance this ticket'}), 403

    transitions = {
        'assigned':       'site_attended',
        'site_attended':  'work_started',
        'work_started':   'work_completed',
        # allow from legacy
        'in_progress':    'work_started',
    }
    next_status = transitions.get(ticket.status)
    if not next_status:
        return jsonify({'success': False, 'error': f'Cannot advance from status "{ticket.status}"'}), 400

    data = request.get_json(silent=True) or {}
    now_str = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    old_status = ticket.status
    ticket.status = next_status

    # Record timestamps
    if next_status == 'site_attended':
        ticket.site_attended_at = now_str
    elif next_status == 'work_started':
        ticket.work_started_at = now_str
    elif next_status == 'work_completed':
        ticket.work_completed_at = now_str
        ticket.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        notes_val = (data.get('resolution_notes') or '').strip() or None
        if notes_val:
            ticket.technician_resolution_notes = notes_val

    _add_note(ticket, user,
              f'Status advanced from "{_STATUS_LABELS.get(old_status, old_status)}" to '
              f'"{_STATUS_LABELS.get(next_status, next_status)}" by {user.full_name}.',
              note_type='status_change')

    if next_status == 'work_completed' and ticket.supervisor_id:
        _notify_user(
            ticket.supervisor_id,
            f'Work Completed: {ticket.ticket_id}',
            f'Technician {user.full_name} completed work on "{ticket.title}". Ready for verification.',
            ntype='info', ticket_id=ticket.ticket_id,
        )

    db.session.commit()
    return jsonify({'success': True, 'status': next_status, 'label': _STATUS_LABELS.get(next_status, next_status)})


# ---------------------------------------------------------------------------
# Supervisor begins verification
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/begin-verification', methods=['POST'])
@jwt_required()
def begin_verification(ticket_id):
    """Supervisor moves work_completed → verification so they can review before closing."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if not _is_supervisor_of_ticket(user):
        return jsonify({'success': False, 'error': 'Only supervisors may begin verification'}), 403

    if ticket.status not in ('work_completed', 'pending_verification'):
        return jsonify({'success': False, 'error': f'Cannot begin verification from "{ticket.status}"'}), 400

    ticket.status = 'verification'
    _add_note(ticket, user, f'Verification started by {user.full_name}.', note_type='status_change')
    db.session.commit()
    return jsonify({'success': True, 'status': 'verification'})


# ---------------------------------------------------------------------------
# On hold / resume
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/hold', methods=['POST'])
@jwt_required()
def hold_ticket(ticket_id):
    """Place a ticket on hold with a reason; stores previous status for resume."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if ticket.status in _TERMINAL_STATUSES:
        return jsonify({'success': False, 'error': f'Cannot hold a {ticket.status} ticket'}), 400
    if ticket.status == 'on_hold':
        return jsonify({'success': False, 'error': 'Ticket is already on hold'}), 400

    data = request.get_json(silent=True) or {}
    reason_key = (data.get('reason') or 'other').strip()
    if reason_key not in ON_HOLD_REASONS:
        reason_key = 'other'
    notes = (data.get('notes') or '').strip() or None

    ticket.previous_status = ticket.status
    ticket.on_hold_reason = reason_key
    ticket.status = 'on_hold'

    reason_label = ON_HOLD_REASONS[reason_key]
    msg = f'Ticket placed on hold — {reason_label}.'
    if notes:
        msg += f' Notes: {notes}'
    _add_note(ticket, user, msg, note_type='status_change')
    db.session.commit()
    return jsonify({
        'success': True, 'status': 'on_hold',
        'reason': reason_key, 'reason_label': reason_label,
    })


@ticketing_bp.route('/api/tickets/<string:ticket_id>/resume', methods=['POST'])
@jwt_required()
def resume_ticket(ticket_id):
    """Resume an on-hold ticket back to its previous status."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if ticket.status != 'on_hold':
        return jsonify({'success': False, 'error': 'Ticket is not on hold'}), 400

    resume_to = ticket.previous_status or 'assigned'
    ticket.status = resume_to
    ticket.on_hold_reason = None
    ticket.previous_status = None

    data = request.get_json(silent=True) or {}
    notes = (data.get('notes') or '').strip() or None
    msg = f'Ticket resumed to "{_STATUS_LABELS.get(resume_to, resume_to)}" by {user.full_name}.'
    if notes:
        msg += f' Notes: {notes}'
    _add_note(ticket, user, msg, note_type='status_change')
    db.session.commit()
    return jsonify({'success': True, 'status': resume_to, 'label': _STATUS_LABELS.get(resume_to, resume_to)})


# ---------------------------------------------------------------------------
# Cancel ticket
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_ticket(ticket_id):
    """Cancel a ticket with a mandatory reason."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    if ticket.status in ('closed', 'cancelled'):
        return jsonify({'success': False, 'error': f'Ticket is already {ticket.status}'}), 400

    # Only supervisor/overwatch/reporter can cancel
    can_cancel = (
        _ticketing_sees_all_tickets(user)
        or _is_supervisor_of_ticket(user)
        or ticket.reporter_id == user.id
    )
    if not can_cancel:
        return jsonify({'success': False, 'error': 'Only the reporter, supervisor, or overwatch may cancel this ticket'}), 403

    data = request.get_json(silent=True) or {}
    reason_key = (data.get('reason') or 'other').strip()
    if reason_key not in CANCEL_REASONS:
        reason_key = 'other'
    notes = (data.get('notes') or '').strip() or None

    ticket.status = 'cancelled'
    ticket.cancelled_reason = reason_key
    ticket.cancelled_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    reason_label = CANCEL_REASONS[reason_key]
    msg = f'Ticket cancelled — {reason_label}. By {user.full_name}.'
    if notes:
        msg += f' Notes: {notes}'
    _add_note(ticket, user, msg, note_type='status_change')
    db.session.commit()
    return jsonify({'success': True, 'status': 'cancelled', 'reason': reason_key, 'reason_label': reason_label})


# ---------------------------------------------------------------------------
# Submit to supervisor queue
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/submit-to-supervisor', methods=['POST'])
@jwt_required()
def submit_to_supervisor(ticket_id):
    """Transition ticket to pending_supervisor — routed to the project's supervisor when configured."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    if ticket.status not in ('open', 'pending_supervisor'):
        return jsonify({'success': False, 'error': f'Cannot submit from status "{ticket.status}"'}), 400

    data = request.get_json(silent=True) or {}
    service_report_notes = (data.get('service_report_notes') or '').strip() or None
    ticket.service_report_notes = service_report_notes
    ticket.status = 'pending_supervisor'
    _apply_ticket_project_routing(ticket)

    _add_note(ticket, user,
              'Work order submitted to supervisor queue for technician assignment.',
              note_type='status_change')
    db.session.commit()

    _notify_supervisor_queue_ticket(
        ticket,
        f'Ticket {ticket.ticket_id} — "{ticket.title}" requires a technician assignment.',
    )
    db.session.commit()
    return jsonify({'success': True, 'status': 'pending_supervisor'})


# ---------------------------------------------------------------------------
# Supervisor assigns technician
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/assign-technician', methods=['POST'])
@jwt_required()
def assign_technician(ticket_id):
    """Supervisor picks a technician from their team to work the ticket."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if not _is_supervisor_of_ticket(user):
        return jsonify({'success': False, 'error': 'Only supervisors can assign technicians'}), 403

    data = request.get_json(silent=True) or {}
    tech_id = data.get('technician_id')
    tech_name = (data.get('technician_name') or '').strip()
    tech_code = (data.get('technician_code') or '').strip()

    ticket.supervisor_id = user.id
    ticket.status = 'assigned'

    if tech_id:
        technician = db.session.get(User, int(tech_id))
        if not technician:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        strictly_supervisor_lane = (
            user.role != 'admin'
            and not _ticketing_sees_all_tickets(user)
        )
        if strictly_supervisor_lane:
            in_team = TicketSupervisorTeam.query.filter_by(
                supervisor_id=user.id,
                technician_id=technician.id,
                is_active=True,
            ).first()
            if not in_team:
                return jsonify({
                    'success': False,
                    'error': 'That technician is not on your ticketing team.',
                }), 403

        ticket.technician_id = technician.id
        ticket.assigned_to_id = technician.id
        display_name = technician.full_name

        _add_note(ticket, user,
                  f'Technician {display_name} assigned by supervisor {user.full_name}. Work in progress.',
                  note_type='assignment')
        _notify_user(technician.id, f'Work Order Assigned: {ticket.ticket_id}',
                     f'You have been assigned to work order {ticket.ticket_id}: "{ticket.title}".',
                     ntype='info', ticket_id=ticket.ticket_id)
    elif tech_name:
        # Dummy technician path: keep assignment independent from system users.
        ticket.technician_id = None
        ticket.assigned_to_id = None
        display_name = tech_name
        _add_note(
            ticket,
            user,
            f'Dummy technician {display_name}'
            + (f' ({tech_code})' if tech_code else '')
            + f' assigned by supervisor {user.full_name}. Work in progress.',
            note_type='assignment',
        )
    else:
        return jsonify({'success': False, 'error': 'technician_id or technician_name required'}), 400

    db.session.commit()
    return jsonify({'success': True, 'status': 'in_progress',
                    'technician_name': display_name,
                    'supervisor_name': user.full_name})


# ---------------------------------------------------------------------------
# Technician marks work complete
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/mark-completed', methods=['POST'])
@jwt_required()
def mark_completed(ticket_id):
    """Technician marks work done — ticket goes to supervisor for verification."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    # Assigned technician, overwatch (admin/ops/GM), or owning supervisor (dummy-tech) can mark complete.
    is_assigned_technician = (ticket.technician_id == user.id or ticket.assigned_to_id == user.id)
    is_owning_supervisor = (ticket.supervisor_id == user.id and not ticket.technician_id)
    if (
        not _ticketing_sees_all_tickets(user)
        and not is_assigned_technician
        and not is_owning_supervisor
    ):
        return jsonify({'success': False, 'error': 'Only assigned technician/supervisor can mark this complete'}), 403

    if ticket.status not in ('in_progress', 'work_started', 'site_attended', 'pending_parts'):
        return jsonify({'success': False, 'error': f'Cannot mark complete from status "{ticket.status}"'}), 400

    data = request.get_json(silent=True) or {}
    resolution_notes = (data.get('resolution_notes') or '').strip() or None
    ticket.technician_resolution_notes = resolution_notes
    ticket.status = 'work_completed'
    ticket.work_completed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    ticket.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    _recalc_total_cost(ticket)
    _add_note(ticket, user,
              f'Work completed by {user.full_name}. Awaiting supervisor verification.'
              + (f' Notes: {resolution_notes}' if resolution_notes else ''),
              note_type='status_change')

    # Notify the supervisor
    if ticket.supervisor_id:
        _notify_user(ticket.supervisor_id, f'Work Order Awaiting Verification: {ticket.ticket_id}',
                     f'Technician {user.full_name} has completed work on {ticket.ticket_id}. Please verify and close.',
                     ntype='info', ticket_id=ticket.ticket_id)
    db.session.commit()
    return jsonify({'success': True, 'status': 'pending_verification'})


# ---------------------------------------------------------------------------
# Supervisor verifies and closes with markup
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/supervisor-close', methods=['POST'])
@jwt_required()
def supervisor_close(ticket_id):
    """Supervisor verifies work, sets markup, and closes the ticket."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if not _is_supervisor_of_ticket(user):
        return jsonify({'success': False, 'error': 'Only supervisors can close tickets via this route'}), 403

    if ticket.status not in ('pending_verification', 'verification', 'work_completed'):
        return jsonify({'success': False, 'error': f'Ticket must be in pending_verification to close. Current: {ticket.status}'}), 400

    data = request.get_json(silent=True) or {}

    markup_pct = data.get('markup_pct')
    if markup_pct is not None:
        try:
            markup_pct = float(markup_pct)
            if markup_pct not in (0, 10, 20, 30):
                return jsonify({'success': False, 'error': 'Markup must be 0, 10, 20, or 30'}), 400
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid markup_pct'}), 400

    signature   = (data.get('signature') or '').strip()
    signed_by   = (data.get('signed_by') or '').strip()
    signed_role = (data.get('signed_role') or '').strip()
    ver_notes   = (data.get('verification_notes') or '').strip() or None

    if not signature:
        return jsonify({'success': False, 'error': 'Signature is required to close'}), 400
    if not signed_by:
        return jsonify({'success': False, 'error': 'Signer name is required'}), 400

    ticket.markup_pct = markup_pct
    ticket.supervisor_verification_notes = ver_notes
    ticket.close_signature  = signature
    ticket.close_signed_by  = signed_by
    ticket.close_signed_role = signed_role
    ticket.close_notes = ver_notes
    ticket.status     = 'closed'
    ticket.closed_at  = datetime.now(timezone.utc).replace(tzinfo=None)

    _recalc_total_cost(ticket)

    markup_label = f'{int(markup_pct)}%' if markup_pct else 'No markup'
    _add_note(ticket, user,
              f'Ticket verified and closed by supervisor {user.full_name} ({signed_role}). '
              f'Markup applied: {markup_label}. Selling price: AED {ticket.selling_price or 0:.2f}.',
              note_type='status_change')

    db.session.commit()
    _send_completion_emails(ticket, user)
    return jsonify({
        'success': True,
        'status': 'closed',
        'actual_price': ticket.actual_price,
        'selling_price': ticket.selling_price,
        'markup_pct': ticket.markup_pct,
    })


# ---------------------------------------------------------------------------
# Supervisor team management
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/supervisor/team', methods=['GET'])
@jwt_required()
def get_supervisor_team():
    """List the current supervisor's team members."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    entries = TicketSupervisorTeam.query.filter_by(
        supervisor_id=user.id, is_active=True
    ).all()
    return jsonify({'success': True, 'team': [e.to_dict() for e in entries]})


@ticketing_bp.route('/api/supervisor/team', methods=['POST'])
@jwt_required()
def add_team_member():
    """Supervisor adds a user to their team."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    tech_id = data.get('technician_id')
    if not tech_id:
        return jsonify({'success': False, 'error': 'technician_id required'}), 400

    tech_id = int(tech_id)
    if tech_id == user.id:
        return jsonify({'success': False, 'error': 'Cannot add yourself to your own team'}), 400

    technician = db.session.get(User, tech_id)
    if not technician or not technician.is_active:
        return jsonify({'success': False, 'error': 'User not found or inactive'}), 404

    existing = TicketSupervisorTeam.query.filter_by(
        supervisor_id=user.id, technician_id=tech_id
    ).first()
    if existing:
        existing.is_active = True
        db.session.commit()
        return jsonify({'success': True, 'member': existing.to_dict()})

    entry = TicketSupervisorTeam(supervisor_id=user.id, technician_id=tech_id)
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'member': entry.to_dict()}), 201


@ticketing_bp.route('/api/supervisor/team/<int:entry_id>', methods=['DELETE'])
@jwt_required()
def remove_team_member(entry_id):
    """Supervisor removes a member from their team."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    entry = db.session.get(TicketSupervisorTeam, entry_id)
    if not entry or entry.supervisor_id != user.id:
        abort(404)
    entry.is_active = False
    db.session.commit()
    return jsonify({'success': True})


@ticketing_bp.route('/api/supervisor/all-teams', methods=['GET'])
@jwt_required()
def get_all_teams():
    """Admin / overwatch: all supervisor teams."""
    user = _current_user()
    if not user or not _ticketing_sees_all_tickets(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    entries = TicketSupervisorTeam.query.filter_by(is_active=True).all()
    result = {}
    for e in entries:
        sup_name = e.sup_user.full_name if e.sup_user else f'User {e.supervisor_id}'
        if e.supervisor_id not in result:
            result[e.supervisor_id] = {'supervisor_name': sup_name, 'members': []}
        result[e.supervisor_id]['members'].append(e.to_dict())
    return jsonify({'success': True, 'teams': list(result.values())})


# ---------------------------------------------------------------------------
# Pricing preview API
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/pricing-preview', methods=['GET'])
@jwt_required()
def pricing_preview(ticket_id):
    """Return the calculated actual_price and selling_price for given markup."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    markup_pct = request.args.get('markup_pct', 0)
    try:
        markup_pct = float(markup_pct)
    except (TypeError, ValueError):
        markup_pct = 0.0

    mp_total  = sum((e.total_cost  or 0) for e in ticket.manpower.all())
    mat_total = sum((m.total_price or 0) for m in ticket.materials.all())
    base_cost = mp_total + mat_total
    overhead  = ticket.overhead_pct if ticket.overhead_pct is not None else 10.0
    actual    = round(base_cost * (1 + overhead / 100.0), 2)
    selling   = round(actual * (1 + markup_pct / 100.0), 2)

    return jsonify({
        'success': True,
        'mp_total': mp_total,
        'mat_total': mat_total,
        'base_cost': base_cost,
        'overhead_pct': overhead,
        'overhead_amount': round(base_cost * overhead / 100.0, 2),
        'actual_price': actual,
        'markup_pct': markup_pct,
        'markup_amount': round(actual * markup_pct / 100.0, 2),
        'selling_price': selling,
    })


# ---------------------------------------------------------------------------
# Email on completion
# ---------------------------------------------------------------------------

def _send_completion_emails(ticket: Ticket, closed_by: User):
    """Send email notification to admin, assignee, reporter on ticket close."""
    try:
        admin_emails = [
            u.email for u in User.query.filter_by(role='admin', is_active=True).all()
            if u.email
        ]
        recipients = list(set(filter(None, [
            ticket.reporter.email if ticket.reporter else None,
            ticket.assigned_to.email if ticket.assigned_to else None,
        ] + admin_emails)))

        subject = f'[Injaaz] Work Order Closed — {ticket.ticket_id}'
        body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #1e3a5f;">Work Order Completed</h2>
          <p>Ticket <strong>{ticket.ticket_id}</strong> has been closed.</p>
          <table style="width:100%; border-collapse:collapse; font-size:14px;">
            <tr><td style="padding:6px; font-weight:bold; width:140px;">Title</td><td style="padding:6px;">{ticket.title}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Project</td><td style="padding:6px;">{ticket.project}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Service Group</td><td style="padding:6px;">{ticket.service_group}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Category</td><td style="padding:6px;">{ticket.category}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Priority</td><td style="padding:6px;">{ticket.priority.upper()}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Reported by</td><td style="padding:6px;">{ticket.reporter.full_name if ticket.reporter else 'N/A'}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Assigned to</td><td style="padding:6px;">{ticket.assigned_to.full_name if ticket.assigned_to else 'N/A'}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Location</td><td style="padding:6px;">{' / '.join(filter(None, [ticket.property_name, ticket.zone, ticket.sub_zone, ticket.base_unit]))}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Chargeable</td><td style="padding:6px;">{'Yes' if ticket.is_chargeable else 'No'}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Total Cost</td><td style="padding:6px;">AED {ticket.total_cost or 0:.2f}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Closed by</td><td style="padding:6px;">{ticket.close_signed_by} ({ticket.close_signed_role})</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Closed at</td><td style="padding:6px;">{ticket.closed_at.strftime('%d %b %Y %H:%M') if ticket.closed_at else 'N/A'} (UTC)</td></tr>
          </table>
          {"<p><strong>Closing notes:</strong> " + ticket.close_notes + "</p>" if ticket.close_notes else ""}
          <hr style="margin-top:20px;"/>
          <p style="font-size:12px; color:#888;">This is an automated notification from Injaaz Application.</p>
        </div>
        """
        _send_ticket_email(subject, recipients, body)
    except Exception as exc:
        logger.warning("Failed to send completion emails: %s", exc)


# ---------------------------------------------------------------------------
# PDF Report
# ---------------------------------------------------------------------------

@ticketing_bp.route('/<string:ticket_id>/pdf', methods=['GET'])
@jwt_required()
def download_pdf(ticket_id):
    user = _current_user()
    if not _has_access(user):
        abort(403)

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if not _can_user_view_ticket(user, ticket):
        abort(403)

    notes = ticket.notes.order_by(TicketNote.created_at.asc()).all()
    images = ticket.images.all()
    materials = ticket.materials.all()
    manpower_entries = ticket.manpower.all()

    from module_ticketing.ticket_pdf_builder import build_ticket_pdf
    buf = io.BytesIO()
    build_ticket_pdf(ticket, notes, images, materials, manpower_entries, buf)
    buf.seek(0)

    return send_file(
        buf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{ticket.ticket_id}_report.pdf',
    )


# ---------------------------------------------------------------------------
# Invoice PDF
# ---------------------------------------------------------------------------

@ticketing_bp.route('/<string:ticket_id>/invoice', methods=['GET'])
@jwt_required()
def download_invoice(ticket_id):
    """Generate and return a service invoice PDF for a closed work order."""
    user = _current_user()
    if not _has_access(user):
        abort(403)

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if not _can_user_view_ticket(user, ticket):
        abort(403)

    materials        = ticket.materials.all()
    manpower_entries = ticket.manpower.all()

    # Ensure pricing is computed before generating invoice
    if ticket.selling_price is None:
        _recalc_total_cost(ticket)
        db.session.commit()

    from module_ticketing.ticket_invoice_builder import build_invoice_pdf
    buf = io.BytesIO()
    build_invoice_pdf(ticket, materials, manpower_entries, buf)
    buf.seek(0)

    return send_file(
        buf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{ticket.ticket_id}_invoice.pdf',
    )


# ---------------------------------------------------------------------------
# Procurement materials API (for autocomplete in forms)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/procurement-materials', methods=['GET'])
@jwt_required()
def procurement_materials_api():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return jsonify({'success': True, 'materials': _get_procurement_materials()})


def _procurement_text_field(v, default='') -> str:
    """Normalize form_data values for Jinja ``|tojson`` (must be JSON-serializable)."""
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return ''  # avoid dumping large / non-scalar blobs into autocomplete
    return str(v)


def _procurement_unit_price(v) -> float:
    if v is None or v == '':
        return 0.0
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _get_procurement_materials() -> list:
    """Fetch materials from both procurement_material and catalog_material submissions."""
    try:
        from app.models import Submission
        result = []
        seen_names = set()

        # 1. Procurement department's material list
        rows = Submission.query.filter_by(module_type='procurement_material').all()
        for r in rows:
            fd = r.form_data or {}
            raw_name = fd.get('material_name') or fd.get('name') or ''
            name = _procurement_text_field(raw_name, '')
            if name and name not in seen_names:
                seen_names.add(name)
                result.append({
                    'id': _procurement_text_field(r.submission_id, ''),
                    'name': name,
                    'unit': _procurement_text_field(fd.get('unit', '') or fd.get('uom', '')),
                    'unit_price': _procurement_unit_price(fd.get('unit_price', 0)),
                    'category': _procurement_text_field(fd.get('category', 'General'), 'General'),
                    'brand': _procurement_text_field(fd.get('brand', '') or fd.get('supplier', '')),
                    'source': 'procurement',
                })

        # 2. Catalog materials (HVAC, Cleaning, Electrical, Plumbing departments)
        catalog_rows = Submission.query.filter_by(module_type='catalog_material').all()
        for r in catalog_rows:
            fd = r.form_data or {}
            raw_name = fd.get('material_name') or fd.get('name') or ''
            name = _procurement_text_field(raw_name, '')
            if name and name not in seen_names:
                seen_names.add(name)
                result.append({
                    'id': _procurement_text_field(r.submission_id, ''),
                    'name': name,
                    'unit': _procurement_text_field(fd.get('uom', '') or fd.get('unit', '')),
                    'unit_price': _procurement_unit_price(fd.get('unit_price', 0)),
                    'category': _procurement_text_field(fd.get('department', 'General'), 'General'),
                    'brand': _procurement_text_field(fd.get('brand', '')),
                    'source': 'catalog',
                })

        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Ticket config / options API
# ---------------------------------------------------------------------------

try:
    from module_ticketing import fault_catalog as _tkt_fault_catalog
except ImportError:
    _tkt_fault_catalog = None


def _ticket_dropdown_tail():
    """Shared priority & manpower options."""
    return {
        'priorities': [
            {'value': 'low', 'label': 'Low'},
            {'value': 'medium', 'label': 'Medium'},
            {'value': 'high', 'label': 'High'},
            {'value': 'critical', 'label': 'Critical'},
        ],
        'manpower_hours': [
            {'value': '0.25', 'label': '15 minutes'},
            {'value': '0.5', 'label': '30 minutes'},
            {'value': '0.75', 'label': '45 minutes'},
            {'value': '1', 'label': '1 hour'},
            {'value': '2', 'label': '2 hours'},
            {'value': '3', 'label': '3+ hours'},
            {'value': '4', 'label': '4 hours'},
            {'value': '6', 'label': '6 hours'},
            {'value': '8', 'label': '8 hours (full day)'},
        ],
    }


_LEGACY_CLASSIFICATION_OPTIONS = {
    'service_groups': [
        'HVAC & MEP', 'Civil Works', 'Cleaning Services',
        'Electrical', 'Plumbing', 'IT & Networking',
        'Security Systems', 'Fire & Safety', 'Landscaping', 'General Maintenance',
    ],
    'categories': {
        'HVAC & MEP': ['AC Unit', 'Chiller', 'AHU', 'FCU', 'Ductwork', 'Controls', 'Ventilation', 'Other'],
        'Civil Works': ['Structural', 'Flooring', 'Roofing', 'Walls', 'Ceiling', 'Doors & Windows', 'Other'],
        'Cleaning Services': ['Deep Clean', 'Routine Clean', 'Pest Control', 'Waste Management', 'Other'],
        'Electrical': ['Power Outage', 'Wiring', 'Lighting', 'Panels', 'Generator', 'Other'],
        'Plumbing': ['Leak', 'Blockage', 'Water Pressure', 'Fixtures', 'Drainage', 'Other'],
        'IT & Networking': ['Network', 'Hardware', 'Software', 'CCTV', 'Access Control', 'Other'],
        'Security Systems': ['CCTV', 'Access Control', 'Alarm', 'Intercom', 'Other'],
        'Fire & Safety': ['Fire Alarm', 'Extinguisher', 'Sprinkler', 'Exit Signs', 'Other'],
        'Landscaping': ['Irrigation', 'Lawn', 'Trees', 'Hardscape', 'Other'],
        'General Maintenance': ['Carpentry', 'Painting', 'Locksmith', 'Glass', 'Furniture', 'Other'],
    },
    'fault_types': [
        'Breakdown', 'Preventive Maintenance', 'Corrective Maintenance',
        'Inspection', 'Installation', 'Upgrade', 'Complaint', 'Emergency', 'Other',
    ],
}


@ticketing_bp.route('/api/options', methods=['GET'])
@jwt_required()
def get_options():
    """Return dropdown options for the ticket form."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403

    bundle = (
        _tkt_fault_catalog.load_bundle()
        if _tkt_fault_catalog is not None
        else None
    )

    tail = _ticket_dropdown_tail()
    fault_meta = {'count': 0, 'source_file': None, 'version': None}
    if bundle and bundle.get('fault_catalog'):
        fc_list = bundle['fault_catalog']
        fault_meta = {
            'count': len(fc_list),
            'source_file': bundle.get('catalog_source_file'),
            'version': bundle.get('catalog_version', 1),
        }

    if bundle and bundle.get('fault_catalog'):
        options = {
            'service_groups': bundle['service_groups'],
            'categories': bundle['categories_by_service_group'],
            'fault_types': [],
            'fault_catalog': bundle['fault_catalog'],
            'use_fault_catalog': True,
            'fault_catalog_meta': fault_meta,
            **tail,
        }
    else:
        options = {
            **_LEGACY_CLASSIFICATION_OPTIONS,
            'fault_catalog': [],
            'use_fault_catalog': False,
            'fault_catalog_meta': fault_meta,
            **tail,
        }
    return jsonify({'success': True, 'options': options})


# ===========================================================================
# SETTINGS
# ===========================================================================

def _is_admin(user):
    return user and user.role == 'admin'


@ticketing_bp.route('/settings', methods=['GET'])
@jwt_required()
def settings_page():
    user = _current_user()
    if not _has_access(user):
        abort(403)
    return render_template(
        'ticket_settings.html',
        user=user,
        ticketing_can_manage_fault_catalog=_is_admin(user),
        sidebar_stats=_get_sidebar_stats(user),
        active_page='ticketing',
    )


@ticketing_bp.route('/api/settings/fault-catalog/rebuild', methods=['POST'])
@jwt_required()
def settings_rebuild_fault_catalog():
    """Admin-only: upload Spreadsheet ML .xls and regenerate fault_codes.json."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    if not _is_admin(user):
        return jsonify({'success': False, 'error': 'Admin only'}), 403

    f = request.files.get('file')
    if not f or not getattr(f, 'filename', ''):
        return jsonify({'success': False, 'error': 'file required'}), 400

    safe_name = secure_filename(f.filename)
    lower = safe_name.lower()
    if lower.endswith('.xlsx') or lower.endswith('.csv'):
        return jsonify({'success': False, 'error': 'Upload the XML SpreadsheetML .xls export, not XLSX/CSV'}), 400

    tmp_path: Path | None = None
    try:
        fd, raw_tmp = tempfile.mkstemp(suffix=".xls")
        os.close(fd)
        tmp_path = Path(raw_tmp)
        f.save(tmp_path)

        from module_ticketing import fault_catalog_build

        src_label = safe_name or "uploaded.xls"
        row_count = fault_catalog_build.rebuild_from_path(tmp_path, src_label)
        source_saved = src_label
    except ValueError as e:
        logger.warning('fault catalog rebuild parse failed: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        logger.exception('fault catalog rebuild failed')
        return jsonify({'success': False, 'error': 'Rebuild failed'}), 500
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    return jsonify({
        'success': True,
        'row_count': row_count,
        'source_file': source_saved,
    })


# ── Projects ────────────────────────────────────────────────────────────────

def _parse_ticket_plain_date(raw) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    s = s[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _calendar_month_before(d: date) -> date:
    if d.month == 1:
        y, m = d.year - 1, 12
    else:
        y, m = d.year, d.month - 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _merge_ticket_project_dates(
    existing_end: date | None,
    existing_renewal: date | None,
    data: dict,
) -> tuple[date | None, date | None]:
    end = existing_end
    renewal = existing_renewal
    if 'project_end_date' in data:
        end = _parse_ticket_plain_date(data.get('project_end_date'))
    if 'renewal_date' in data:
        renewal = _parse_ticket_plain_date(data.get('renewal_date'))
    return end, renewal


def _finalize_ticket_project_dates(
    end: date | None,
    renewal: date | None,
) -> tuple[date | None, date | None, str | None]:
    """
    Renewal must be exactly one calendar month before project end when both apply.
    If project end is set and renewal is omitted, default renewal to one month before end.
    """
    if end is None:
        if renewal is not None:
            return None, None, 'Clear renewal date when project end date is removed.'
        return None, None, None
    if renewal is None:
        renewal = _calendar_month_before(end)
    else:
        expected = _calendar_month_before(end)
        if renewal != expected:
            return None, None, (
                'Renewal date must be exactly one calendar month before project end '
                f'(expected {expected.isoformat()}).'
            )
    return end, renewal, None


def _validate_bd_project_link(raw) -> tuple[int | None, str | None]:
    if raw in (None, '', 0, '0'):
        return None, None
    try:
        bid = int(raw)
    except (TypeError, ValueError):
        return None, 'Invalid BD project id'
    bp = db.session.get(BDProject, bid)
    if not bp:
        return None, 'BD project not found'
    return bid, None


def _parse_project_value(raw) -> tuple[float | None, str | None]:
    if raw in (None, ''):
        return None, None
    try:
        v = float(raw)
        if v < 0:
            return None, 'Project value cannot be negative'
        return round(v, 2), None
    except (TypeError, ValueError):
        return None, 'Invalid project value'


def _validate_supervisor_pick(raw) -> tuple[int | None, str | None]:
    """If raw is empty, return (None, None). Else return (user_id, error_message)."""
    if raw is None or raw == '':
        return None, None
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return None, 'Invalid supervisor id'
    u = db.session.get(User, uid)
    if not u or not u.is_active:
        return None, 'User not found'
    if not _is_ticket_assignment_supervisor(u):
        return None, 'Selected user must be a ticketing supervisor'
    return uid, None


@ticketing_bp.route('/api/settings/bd-active-projects', methods=['GET'])
@jwt_required()
def settings_bd_active_projects():
    """BD deals from Business Development for linking to ticketing projects (same source as BD module)."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    rows = (
        BDProject.query.order_by(BDProject.company.asc(), BDProject.name.asc()).all()
    )
    def _iso_date(d):
        return d.isoformat() if d else None

    return jsonify({
        'success': True,
        'projects': [
            {
                'id': r.id,
                'name': r.name,
                'company': r.company,
                'value_amount': float(r.value_amount or 0),
                'expected_close_date': _iso_date(r.expected_close_date),
                'stage': r.stage,
                'status': r.status,
                'priority': r.priority,
                'progress': max(0, min(100, int(r.progress or 0))),
                'owner': r.owner or '',
                'next_action': r.next_action or '',
            }
            for r in rows
        ],
    })


@ticketing_bp.route('/api/settings/supervisor-options', methods=['GET'])
@jwt_required()
def settings_supervisor_options():
    """Users who may be assigned as a project's routing supervisor."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    rows = _supervisor_assignees_query()
    return jsonify({
        'success': True,
        'supervisors': [
            {'id': u.id, 'name': u.full_name or u.username, 'username': u.username}
            for u in rows
        ],
    })


@ticketing_bp.route('/api/settings/projects', methods=['GET'])
@jwt_required()
def settings_list_projects():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    projects = (
        TicketProject.query.options(joinedload(TicketProject.bd_project))
        .filter_by(is_active=True)
        .order_by(TicketProject.sort_order, TicketProject.name)
        .all()
    )
    return jsonify({'success': True, 'projects': [p.to_dict(with_property_count=True) for p in projects]})


@ticketing_bp.route('/api/settings/projects', methods=['POST'])
@jwt_required()
def settings_create_project():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400

    sup_uid, err = _validate_supervisor_pick(data.get('supervisor_id'))
    if err:
        return jsonify({'success': False, 'error': err}), 400

    bid, err = _validate_bd_project_link(data.get('bd_project_id'))
    if err:
        return jsonify({'success': False, 'error': err}), 400

    raw_end = _parse_ticket_plain_date(data.get('project_end_date'))
    raw_renew = _parse_ticket_plain_date(data.get('renewal_date'))
    end_f, renew_f, err = _finalize_ticket_project_dates(raw_end, raw_renew)
    if err:
        return jsonify({'success': False, 'error': err}), 400

    val_f, err = _parse_project_value(data.get('project_value'))
    if err:
        return jsonify({'success': False, 'error': err}), 400

    p = TicketProject(
        name=name,
        client_name=(data.get('client_name') or '').strip() or None,
        description=(data.get('description') or '').strip() or None,
        supervisor_id=sup_uid,
        bd_project_id=bid,
        project_end_date=end_f,
        renewal_date=renew_f,
        project_value=val_f,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'success': True, 'project': p.to_dict(with_property_count=True)}), 201


@ticketing_bp.route('/api/settings/projects/<int:pid>', methods=['PUT'])
@jwt_required()
def settings_update_project(pid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    p = db.session.get(TicketProject, pid)
    if not p:
        abort(404)
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        p.name = data['name'].strip()
    if 'client_name' in data:
        p.client_name = (data['client_name'] or '').strip() or None
    if 'description' in data:
        p.description = (data['description'] or '').strip() or None
    if 'supervisor_id' in data:
        sup_uid, err = _validate_supervisor_pick(data.get('supervisor_id'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        p.supervisor_id = sup_uid
    if 'bd_project_id' in data:
        bid, err = _validate_bd_project_link(data.get('bd_project_id'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        p.bd_project_id = bid
    if 'project_end_date' in data or 'renewal_date' in data:
        merged_end, merged_renew = _merge_ticket_project_dates(
            p.project_end_date, p.renewal_date, data,
        )
        end_f, renew_f, err = _finalize_ticket_project_dates(merged_end, merged_renew)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        p.project_end_date = end_f
        p.renewal_date = renew_f
    if 'project_value' in data:
        val_f, err = _parse_project_value(data.get('project_value'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        p.project_value = val_f
    if 'is_active' in data:
        p.is_active = bool(data['is_active'])
    db.session.commit()
    return jsonify({'success': True, 'project': p.to_dict(with_property_count=True)})


@ticketing_bp.route('/api/settings/projects/<int:pid>', methods=['DELETE'])
@jwt_required()
def settings_delete_project(pid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    p = db.session.get(TicketProject, pid)
    if not p:
        abort(404)
    p.is_active = False
    db.session.commit()
    return jsonify({'success': True})


# ── Location Tree ────────────────────────────────────────────────────────────

@ticketing_bp.route('/api/settings/location-tree', methods=['GET'])
@jwt_required()
def settings_location_tree():
    """Return full hierarchical location tree keyed by project."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403

    projects = TicketProject.query.filter_by(is_active=True).order_by(TicketProject.name).all()
    tree = []
    for proj in projects:
        pd = proj.to_dict()
        pd['properties'] = []
        for prop in proj.properties.filter_by(is_active=True).order_by(TicketProperty.name):
            proD = prop.to_dict()
            proD['zones'] = []
            for zone in prop.zones.filter_by(is_active=True).order_by(TicketZone.name):
                zD = zone.to_dict()
                zD['sub_zones'] = []
                for sz in zone.sub_zones.filter_by(is_active=True).order_by(TicketSubZone.name):
                    szD = sz.to_dict()
                    szD['base_units'] = [u.to_dict() for u in sz.base_units.filter_by(is_active=True).order_by(TicketBaseUnit.name)]
                    zD['sub_zones'].append(szD)
                proD['zones'].append(zD)
            pd['properties'].append(proD)
        tree.append(pd)

    # Also return standalone properties (not linked to any project)
    standalone = TicketProperty.query.filter_by(project_id=None, is_active=True).order_by(TicketProperty.name).all()
    standalone_list = []
    for prop in standalone:
        proD = prop.to_dict()
        proD['zones'] = []
        for zone in prop.zones.filter_by(is_active=True).order_by(TicketZone.name):
            zD = zone.to_dict()
            zD['sub_zones'] = []
            for sz in zone.sub_zones.filter_by(is_active=True).order_by(TicketSubZone.name):
                szD = sz.to_dict()
                szD['base_units'] = [u.to_dict() for u in sz.base_units.filter_by(is_active=True).order_by(TicketBaseUnit.name)]
                zD['sub_zones'].append(szD)
            proD['zones'].append(zD)
        standalone_list.append(proD)

    return jsonify({'success': True, 'tree': tree, 'standalone_properties': standalone_list})


@ticketing_bp.route('/api/settings/properties', methods=['POST'])
@jwt_required()
def settings_create_property():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    p = TicketProperty(
        name=name,
        project_id=int(data['project_id']) if data.get('project_id') else None,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'success': True, 'property': p.to_dict()}), 201


@ticketing_bp.route('/api/settings/properties/<int:pid>', methods=['DELETE'])
@jwt_required()
def settings_delete_property(pid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    p = db.session.get(TicketProperty, pid)
    if not p:
        abort(404)
    p.is_active = False
    db.session.commit()
    return jsonify({'success': True})


@ticketing_bp.route('/api/settings/zones', methods=['POST'])
@jwt_required()
def settings_create_zone():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    property_id = data.get('property_id')
    if not name or not property_id:
        return jsonify({'success': False, 'error': 'Name and property_id required'}), 400
    z = TicketZone(name=name, property_id=int(property_id))
    db.session.add(z)
    db.session.commit()
    return jsonify({'success': True, 'zone': z.to_dict()}), 201


@ticketing_bp.route('/api/settings/zones/<int:zid>', methods=['DELETE'])
@jwt_required()
def settings_delete_zone(zid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    z = db.session.get(TicketZone, zid)
    if not z:
        abort(404)
    z.is_active = False
    db.session.commit()
    return jsonify({'success': True})


@ticketing_bp.route('/api/settings/sub-zones', methods=['POST'])
@jwt_required()
def settings_create_sub_zone():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    zone_id = data.get('zone_id')
    if not name or not zone_id:
        return jsonify({'success': False, 'error': 'Name and zone_id required'}), 400
    sz = TicketSubZone(name=name, zone_id=int(zone_id))
    db.session.add(sz)
    db.session.commit()
    return jsonify({'success': True, 'sub_zone': sz.to_dict()}), 201


@ticketing_bp.route('/api/settings/sub-zones/<int:szid>', methods=['DELETE'])
@jwt_required()
def settings_delete_sub_zone(szid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    sz = db.session.get(TicketSubZone, szid)
    if not sz:
        abort(404)
    sz.is_active = False
    db.session.commit()
    return jsonify({'success': True})


@ticketing_bp.route('/api/settings/base-units', methods=['POST'])
@jwt_required()
def settings_create_base_unit():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    sub_zone_id = data.get('sub_zone_id')
    if not name or not sub_zone_id:
        return jsonify({'success': False, 'error': 'Name and sub_zone_id required'}), 400
    u = TicketBaseUnit(name=name, sub_zone_id=int(sub_zone_id))
    db.session.add(u)
    db.session.commit()
    return jsonify({'success': True, 'base_unit': u.to_dict()}), 201


@ticketing_bp.route('/api/settings/base-units/<int:uid>', methods=['DELETE'])
@jwt_required()
def settings_delete_base_unit(uid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    u = db.session.get(TicketBaseUnit, uid)
    if not u:
        abort(404)
    u.is_active = False
    db.session.commit()
    return jsonify({'success': True})


# ── Title Templates ──────────────────────────────────────────────────────────

@ticketing_bp.route('/api/settings/title-templates', methods=['GET'])
@jwt_required()
def settings_list_title_templates():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    templates = TicketTitleTemplate.query.filter_by(is_active=True).order_by(
        TicketTitleTemplate.service_group, TicketTitleTemplate.sort_order).all()
    return jsonify({'success': True, 'templates': [t.to_dict() for t in templates]})


@ticketing_bp.route('/api/settings/title-templates', methods=['POST'])
@jwt_required()
def settings_create_title_template():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'Title required'}), 400
    t = TicketTitleTemplate(
        service_group=(data.get('service_group') or '').strip() or None,
        category=(data.get('category') or '').strip() or None,
        fault_type=(data.get('fault_type') or '').strip() or None,
        title=title,
        description_template=(data.get('description_template') or '').strip() or None,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({'success': True, 'template': t.to_dict()}), 201


@ticketing_bp.route('/api/settings/title-templates/<int:tid>', methods=['DELETE'])
@jwt_required()
def settings_delete_title_template(tid):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403
    t = db.session.get(TicketTitleTemplate, tid)
    if not t:
        abort(404)
    t.is_active = False
    db.session.commit()
    return jsonify({'success': True})


# ── Smart APIs for the new ticket form ──────────────────────────────────────

@ticketing_bp.route('/api/title-suggestions', methods=['GET'])
@jwt_required()
def title_suggestions():
    """Return title suggestions from templates + recent tickets matching a query."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403

    q = request.args.get('q', '').strip().lower()
    sg = request.args.get('service_group', '').strip()
    cat = request.args.get('category', '').strip()
    ft = request.args.get('fault_type', '').strip()

    suggestions = []

    # From title templates (filtered by service group / category / fault type if provided)
    tq = TicketTitleTemplate.query.filter_by(is_active=True)
    if sg:
        tq = tq.filter(db.or_(TicketTitleTemplate.service_group == sg,
                               TicketTitleTemplate.service_group.is_(None)))
    if cat:
        tq = tq.filter(db.or_(TicketTitleTemplate.category == cat,
                               TicketTitleTemplate.category.is_(None)))
    templates = tq.order_by(TicketTitleTemplate.sort_order).all()
    for t in templates:
        if not q or q in t.title.lower():
            suggestions.append({
                'title': t.title,
                'description_template': t.description_template,
                'source': 'template',
            })

    # From recent ticket titles in the DB
    rq = Ticket.query.with_entities(Ticket.title).distinct()
    if q:
        rq = rq.filter(Ticket.title.ilike(f'%{q}%'))
    if sg:
        rq = rq.filter(Ticket.service_group == sg)
    recent_titles = [row[0] for row in rq.limit(8).all()]
    seen = {s['title'] for s in suggestions}
    for rt in recent_titles:
        if rt not in seen:
            suggestions.append({'title': rt, 'description_template': None, 'source': 'recent'})
            seen.add(rt)

    return jsonify({'success': True, 'suggestions': suggestions[:15]})


@ticketing_bp.route('/api/description-template', methods=['GET'])
@jwt_required()
def description_template():
    """Return auto-generated work description template based on service/category/fault."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False}), 403

    sg = request.args.get('service_group', '').strip()
    cat = request.args.get('category', '').strip()
    ft = request.args.get('fault_type', '').strip()
    title = request.args.get('title', '').strip()

    # Try to find a matching template
    tq = TicketTitleTemplate.query.filter_by(is_active=True)
    if sg:
        tq = tq.filter(db.or_(TicketTitleTemplate.service_group == sg,
                               TicketTitleTemplate.service_group.is_(None)))
    if title:
        tq = tq.filter(TicketTitleTemplate.title == title)
    elif cat:
        tq = tq.filter(db.or_(TicketTitleTemplate.category == cat,
                               TicketTitleTemplate.category.is_(None)))

    tmpl = tq.filter(TicketTitleTemplate.description_template.isnot(None)).first()
    if tmpl and tmpl.description_template:
        text = tmpl.description_template
    else:
        # Auto-generate a sensible template
        parts = []
        if ft:
            parts.append(f'{ft} reported')
        else:
            parts.append('Issue reported')
        if cat:
            parts.append(f'for {cat}')
        if sg:
            parts.append(f'in {sg}')
        parts.append('system.')

        text = ' '.join(parts) + '\n\n'
        text += 'Scope of work:\n- Inspect and diagnose the issue\n'
        if ft in ('Breakdown', 'Emergency'):
            text += '- Immediate corrective action required\n'
        elif ft == 'Preventive Maintenance':
            text += '- Carry out scheduled preventive maintenance tasks\n'
        elif ft == 'Installation':
            text += '- Install and commission new equipment/component\n'
        else:
            text += '- Perform required maintenance/repair work\n'
        text += '- Document findings, materials used, and work completed'

    return jsonify({'success': True, 'description': text})
