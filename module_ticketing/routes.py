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
    BDProject, InspectionNotification,
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
    'open':                 'Open',
    'assigned':             'Assigned',
    'site_attended':        'Site Attended',
    'work_started':         'Work In Progress',
    'work_completed':       'Work Completed',
    'verification':         'Supervisor Review',
    'pending_gm_approval':  'Pending GM Approval',
    'pending_finance':      'Pending Finance',
    'on_hold':              'On Hold',
    'cancelled':            'Cancelled',
    'closed':               'Closed',
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
    'open', 'assigned', 'site_attended', 'work_started', 'work_completed',
    'verification', 'pending_gm_approval', 'pending_finance', 'on_hold',
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
        # client sign-off
        ('client_signature',               'TEXT'),
        ('client_signed_by',               'TEXT'),
        ('client_signed_at',               'TEXT'),
        ('client_mobile',                  'TEXT'),
        # technician ID for service report
        ('technician_id_no',               'TEXT'),
        # Amaan Service Report template
        ('service_report_no',              'INTEGER'),
        ('service_report_data',            'TEXT'),
        # finance approval gate
        ('gm_approval_required',           'INTEGER DEFAULT 0'),
        ('gm_approved_at',                 'TEXT'),
        ('gm_approved_by_id',              'INTEGER'),
        ('gm_approval_notes',              'TEXT'),
        ('gm_rejected_at',                 'TEXT'),
        ('gm_rejection_notes',             'TEXT'),
        ('finance_confirmed_at',           'TEXT'),
        ('finance_confirmed_by_id',        'INTEGER'),
        ('finance_invoice_ref',            'TEXT'),
        ('finance_contract_id',            'INTEGER'),
    ]
    with app.app_context():
        from app.models import db
        try:
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tickets)")
            existing = {row[1] for row in cursor.fetchall()}
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
            cursor.execute('PRAGMA table_info(ticket_projects)')
            existing = {row[1] for row in cursor.fetchall()}
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


def _is_finance_user(user: User) -> bool:
    """Finance team (or admin) — needs the service report + team's invoice to raise the ERP invoice."""
    if user is None:
        return False
    return bool(user.role == 'admin' or (getattr(user, 'designation', None) or '').strip().lower() == 'finance')


def _can_access_ticket_docs(user: User, ticket: Ticket) -> bool:
    """Who may pull the Service Report / Team's Invoice for a ticket.
    Finance + management always; involved users always; and once the ticket reaches the
    finance pipeline (GM-approved/closed) any user with ticketing access can download it.
    """
    if user is None:
        return False
    if _is_finance_user(user) or _ticketing_sees_all_tickets(user):
        return True
    if _can_user_view_ticket(user, ticket):
        return True
    if ticket.status in ('pending_gm_approval', 'pending_finance', 'closed') and _has_access(user):
        return True
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
    """All active technician accounts — used when no supervisor team is configured."""
    users = (
        User.query
        .filter(User.designation == 'technician', User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
        .all()
    )
    return [
        {
            'user_id': u.id,
            'team_entry_id': None,
            'code': u.username or f'USER-{u.id}',
            'name': u.full_name or u.username,
            'speciality': (getattr(u, 'job_designation', None) or '').strip() or 'Field technician',
            'sidebar_row_id': f'uid-{u.id}',
        }
        for u in users
    ]


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


def _ticketing_worker_pick_list(roster_supervisor_user_id, current_user_id=None):
    """Prefer DB team for this supervisor account; try current user's team; fallback static demo roster."""
    if roster_supervisor_user_id:
        real = _ticketing_team_workers_for_sidebar(roster_supervisor_user_id)
        if real:
            return real
    if current_user_id and current_user_id != roster_supervisor_user_id:
        real = _ticketing_team_workers_for_sidebar(current_user_id)
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
        'total':                len(statuses),
        'active':               active_ct,
        'open':                 statuses.count('open'),
        'assigned':             statuses.count('assigned'),
        'site_attended':        statuses.count('site_attended'),
        'work_started':         statuses.count('work_started'),
        'work_completed':       statuses.count('work_completed'),
        'verification':         statuses.count('verification'),
        'pending_gm_approval':  statuses.count('pending_gm_approval'),
        'pending_finance':      statuses.count('pending_finance'),
        'on_hold':              statuses.count('on_hold'),
        'cancelled':            statuses.count('cancelled'),
        'closed':               statuses.count('closed'),
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
        plain = 'Please view this message in an HTML-capable email client.'
        for recipient in recipients:
            if recipient:
                send_email(
                    recipient=recipient,
                    subject=subject,
                    body=plain,
                    html_body=body_html,
                )
    except Exception as exc:
        logger.warning("Ticket email send failed: %s", exc)


def _send_work_order_created_email(ticket: Ticket, creator: 'User', supervisor: 'User | None'):
    """Send work order creation confirmation to the creator and assigned supervisor."""
    priority_colour = {'low': '#16a34a', 'medium': '#d97706', 'high': '#dc2626', 'critical': '#7c3aed'}.get(
        (ticket.priority or '').lower(), '#6b7280'
    )
    location_parts = [ticket.property_name, ticket.zone, ticket.sub_zone, ticket.base_unit]
    location_str = ' / '.join(p for p in location_parts if p) or '—'
    html = f"""
<html><body style="font-family:sans-serif;color:#1a1a1a;">
<div style="max-width:620px;margin:0 auto;padding:24px;">
  <div style="background:#d21725;padding:20px 24px;border-radius:10px 10px 0 0;">
    <h2 style="color:#fff;margin:0;">Work Order Created</h2>
    <p style="color:rgba(255,255,255,.85);margin:6px 0 0;">{ticket.ticket_id}</p>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 10px 10px;">
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:8px 0;font-weight:600;width:160px;">Title</td><td style="padding:8px 0;"><strong>{ticket.title}</strong></td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Project</td><td style="padding:8px 4px;">{ticket.project}</td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Location</td><td style="padding:8px 0;">{location_str}</td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Service Group</td><td style="padding:8px 4px;">{ticket.service_group}</td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Category</td><td style="padding:8px 0;">{ticket.category}</td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Fault Type</td><td style="padding:8px 4px;">{ticket.fault_type}</td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Priority</td><td style="padding:8px 0;"><strong style="color:{priority_colour};">{ticket.priority.upper() if ticket.priority else '—'}</strong></td></tr>
      <tr style="background:#f9fafb;"><td style="padding:8px 4px;font-weight:600;">Created by</td><td style="padding:8px 4px;">{creator.full_name or creator.username}</td></tr>
      <tr><td style="padding:8px 0;font-weight:600;">Assigned to</td><td style="padding:8px 0;">{supervisor.full_name or supervisor.username if supervisor else 'Supervisor pool'}</td></tr>
    </table>
    {'<p style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-top:16px;">' + ticket.work_description + '</p>' if ticket.work_description else ''}
    <p style="margin-top:24px;">Log in to the Amaan platform to view and manage this work order.</p>
    <p style="color:#6b7280;font-size:.85rem;margin-top:16px;">This is an automated notification from Amaan Application.</p>
  </div>
</div>
</body></html>"""
    recipients = list({u.email for u in [creator, supervisor] if u and u.email})
    _send_ticket_email(
        subject=f"[Amaan] Work Order Created — {ticket.ticket_id}: {ticket.title}",
        recipients=recipients,
        body_html=html,
    )


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

    pending_gm_ct = sum(1 for t in tickets_q if t.status == 'pending_gm_approval')
    pending_finance_ct = sum(1 for t in tickets_q if t.status == 'pending_finance')
    work_active_ct = sum(1 for t in tickets_q if t.status in ('work_started', 'site_attended', 'assigned'))
    verification_ct = sum(1 for t in tickets_q if t.status in ('verification', 'work_completed'))

    stats = {
        'total': total_ct,
        'open': sum(1 for t in tickets_q if t.status == 'open'),
        'assigned': sum(1 for t in tickets_q if t.status == 'assigned'),
        'work_started': sum(1 for t in tickets_q if t.status in ('work_started', 'site_attended')),
        'work_completed': sum(1 for t in tickets_q if t.status == 'work_completed'),
        'verification': verification_ct,
        'pending_gm_approval': pending_gm_ct,
        'pending_finance': pending_finance_ct,
        'on_hold': sum(1 for t in tickets_q if t.status == 'on_hold'),
        # legacy
        'pending_supervisor': sum(1 for t in tickets_q if t.status == 'pending_supervisor'),
        'in_progress': sum(1 for t in tickets_q if t.status == 'in_progress'),
        'pending_verification': sum(1 for t in tickets_q if t.status == 'pending_verification'),
        'resolved': resolved_ct,
        'closed': closed_ct,
        'pending_parts': sum(1 for t in tickets_q if t.status == 'pending_parts'),
        'critical': sum(1 for t in tickets_q if t.priority == 'critical'),
        'high': sum(1 for t in tickets_q if t.priority == 'high'),
        'active': work_active_ct,
        # Donut / headline: % fully closed vs all tickets in view
        'closed_pct': int(round(100.0 * closed_ct / total_ct)) if total_ct else 0,
        'completed_pct': int(round(100.0 * completed_ct / total_ct)) if total_ct else 0,
    }

    recent = tickets_q[:20]
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
# Civil Defense (CD) notification feed — surfaces inspection notifications
# registered by Sales so ops can convert them into service tickets.
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/cd-notifications', methods=['GET'])
@jwt_required()
def cd_notifications_feed():
    """JSON feed of Civil Defense inspection notifications for the ticketing hero popup.

    Each row carries the source narrative plus a `converted` flag (and the list of
    ticket ids it has already spawned) so the popup can show a 'Converted ✓' badge
    while still allowing another conversion.
    """
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    today = date.today()
    notifs = (InspectionNotification.query
              .order_by(InspectionNotification.inspection_date.asc())
              .all())

    # Refresh overdue status in passing (mirrors the inspection module behaviour).
    changed = False
    for n in notifs:
        if n.status == 'pending' and n.inspection_date and n.inspection_date < today:
            n.status = 'overdue'
            changed = True
    if changed:
        db.session.commit()

    rows = []
    open_ct = 0
    overdue_ct = 0
    for n in notifs:
        converted_tickets = [
            {'ticket_id': t.ticket_id, 'status': t.status}
            for t in n.converted_tickets.order_by(Ticket.created_at.asc()).all()
        ]
        data = n.to_dict()
        data['converted'] = bool(converted_tickets)
        data['converted_tickets'] = converted_tickets
        rows.append(data)
        if n.status not in ('completed', 'closed', 'cancelled'):
            open_ct += 1
        if n.status == 'overdue' or (n.inspection_date and n.inspection_date < today
                                     and n.status not in ('completed', 'closed', 'cancelled')):
            overdue_ct += 1

    return jsonify({
        'success': True,
        'notifications': rows,
        'summary': {'open': open_ct, 'overdue': overdue_ct, 'total': len(rows)},
    })


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
    if priority_filter == 'normal':
        # Dashboard "Normal" pill = everything that is not critical/high
        q = q.filter(Ticket.priority.in_(['low', 'medium']))
    elif priority_filter:
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

    # Optional pre-fill when converting a Civil Defense (CD) inspection notification.
    cd_prefill = _build_cd_prefill(request.args.get('from_cd'))

    return render_template(
        'ticket_new.html',
        user=user,
        all_users=all_users,
        procurement_materials=procurement_materials,
        sidebar_stats=_get_sidebar_stats(user),
        active_page='ticketing',
        cd_prefill=cd_prefill,
    )


def _build_cd_prefill(from_cd):
    """Return a {title, work_description, source_inspection_notif_id} dict for the
    new-ticket form when arriving from a CD notification, else None.

    Only the narrative (title + description) is pre-filled — classification,
    project and priority are left for the user to choose.
    """
    if not from_cd:
        return None
    try:
        notif = InspectionNotification.query.get(int(from_cd))
    except (TypeError, ValueError):
        return None
    if not notif:
        return None

    cd_ref = notif.civil_defense_ref or notif.notif_id
    title = f"Civil Defense — {notif.site_name} ({cd_ref})"

    lines = [f"Civil Defense inspection notification {cd_ref}."]
    if notif.inspection_type:
        lines.append(f"Type: {notif.inspection_type}.")
    if notif.notification_date:
        lines.append(f"Notified: {notif.notification_date.strftime('%d %b %Y')}.")
    if notif.inspection_date:
        lines.append(f"Inspection due: {notif.inspection_date.strftime('%d %b %Y')}.")
    if notif.notes:
        lines.append("")
        lines.append(notif.notes)

    return {
        'source_inspection_notif_id': notif.id,
        'cd_ref': cd_ref,
        'site_name': notif.site_name,
        'title': title,
        'work_description': "\n".join(lines),
    }


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

    # Optional link back to the Civil Defense notification this ticket was converted from.
    # Conversion is gated: only a failed inspection that Amaan must rectify may spawn an ST.
    source_cd_id = None
    raw_cd = data.get('source_inspection_notif_id')
    if raw_cd:
        try:
            cd_notif = InspectionNotification.query.get(int(raw_cd))
        except (TypeError, ValueError):
            cd_notif = None
        if cd_notif:
            if not cd_notif.can_convert:
                return jsonify({
                    'success': False,
                    'error': 'This Civil Defense notification cannot be converted: a service '
                             'ticket is only allowed for a failed inspection that Amaan must rectify.',
                }), 400
            source_cd_id = cd_notif.id

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
        source_inspection_notif_id=source_cd_id,
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
    _send_work_order_created_email(ticket, user, route_sup)
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

    worker_pick_list = _ticketing_worker_pick_list(roster_for_picks, current_user_id=user.id)
    ticket_sidebar_team = (
        (_ticketing_team_workers_for_sidebar(user.id) or _ticket_roster_fallback_workers())
        if user_is_supervisor else []
    )
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
        'verification', 'pending_gm_approval', 'pending_finance', 'on_hold', 'closed', 'cancelled',
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
        ticket.supervisor_id = assignee.id
        _add_note(ticket, user, f'Supervisor re-routed to {assignee.full_name}.', note_type='assignment')
        _notify_user(assignee.id, f'Ticket assigned: {ticket.ticket_id}',
                     f'You have been assigned ticket {ticket.ticket_id}: {ticket.title}',
                     ntype='info', ticket_id=ticket.ticket_id)
    else:
        ticket.assigned_to_id = None
        ticket.supervisor_id = None
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
    """Supervisor completes verification, sets markup, and submits to GM for final approval."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny
    if not _is_supervisor_of_ticket(user):
        return jsonify({'success': False, 'error': 'Only supervisors can submit tickets for GM approval'}), 403

    if ticket.status not in ('pending_verification', 'verification', 'work_completed'):
        return jsonify({'success': False, 'error': f'Ticket must be in Supervisor Review to submit for GM approval. Current: {ticket.status}'}), 400

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
        return jsonify({'success': False, 'error': 'Supervisor signature is required'}), 400
    if not signed_by:
        return jsonify({'success': False, 'error': 'Signer name is required'}), 400

    ticket.markup_pct = markup_pct
    ticket.supervisor_verification_notes = ver_notes
    ticket.close_signature   = signature
    ticket.close_signed_by   = signed_by
    ticket.close_signed_role = signed_role
    ticket.close_notes = ver_notes
    ticket.status = 'pending_gm_approval'
    ticket.gm_approval_required = True
    # Clear any previous rejection so GM sees a fresh request
    ticket.gm_rejected_at = None
    ticket.gm_rejection_notes = None

    _recalc_total_cost(ticket)

    markup_label = f'{int(markup_pct)}%' if markup_pct else 'No markup'
    _add_note(ticket, user,
              f'Supervisor {user.full_name} completed review and submitted ticket for GM approval. '
              f'Markup: {markup_label}. Selling price: AED {ticket.selling_price or 0:.2f}.',
              note_type='status_change')

    # Notify all GM / admin users
    gm_users = User.query.filter(
        User.is_active == True,  # noqa: E712
        db.or_(User.role == 'admin', User.designation == 'general_manager'),
    ).all()
    for gm in gm_users:
        _notify_user(gm.id,
                     f'GM Approval Required — {ticket.ticket_id}',
                     f'Ticket "{ticket.title}" from project {ticket.project} is awaiting your approval. '
                     f'Selling price: AED {ticket.selling_price or 0:.2f}.',
                     ntype='warning',
                     ticket_id=ticket.ticket_id)

    # Notify Finance in parallel — they may start the ERP invoice without waiting for GM
    _gm_ids = {gm.id for gm in gm_users}
    finance_users = [
        fu for fu in User.query.filter(
            User.is_active == True,  # noqa: E712
            User.designation == 'finance',
        ).all()
        if fu.id not in _gm_ids
    ]
    for fu in finance_users:
        _notify_user(fu.id,
                     f'Ready for Invoicing — {ticket.ticket_id}',
                     f'Supervisor has verified ticket "{ticket.title}" (Project: {ticket.project}). '
                     f'Selling price: AED {ticket.selling_price or 0:.2f}. '
                     f'You may log the ERP invoice now; GM approval is running in parallel.',
                     ntype='info',
                     ticket_id=ticket.ticket_id)

    db.session.commit()
    return jsonify({
        'success': True,
        'status': 'pending_gm_approval',
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

def _send_completion_emails(ticket: Ticket, closed_by: User,
                            custom_to=None, custom_cc=None, custom_body=None):
    """Send email notification to admin, assignee, reporter on ticket close."""
    try:
        if custom_to:
            recipients = custom_to
        else:
            admin_emails = [
                u.email for u in User.query.filter_by(role='admin', is_active=True).all()
                if u.email
            ]
            recipients = list(set(filter(None, [
                ticket.reporter.email if ticket.reporter else None,
                ticket.assigned_to.email if ticket.assigned_to else None,
            ] + admin_emails)))

        subject = f'[Amaan] Work Order Closed — {ticket.ticket_id}'
        body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #a8121e;">Work Order Completed</h2>
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
          <p style="font-size:12px; color:#888;">This is an automated notification from Amaan Application.</p>
        </div>
        """
        final_body = custom_body or body
        plain = (
            f'Work order {ticket.ticket_id} has been closed. '
            f'Title: {ticket.title}. View details in Amaan.'
        )
        from common.email_service import send_email
        cc_list = custom_cc or None
        for r in recipients:
            if not r:
                continue
            send_email(
                recipient=r,
                subject=subject,
                body=plain,
                html_body=final_body,
                cc=cc_list,
            )
    except Exception as exc:
        logger.warning("Failed to send completion emails: %s", exc)


# ---------------------------------------------------------------------------
# PDF Report
# ---------------------------------------------------------------------------

@ticketing_bp.route('/<string:ticket_id>/pdf', methods=['GET'])
@jwt_required()
def download_pdf(ticket_id):
    user = _current_user()
    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if not _can_access_ticket_docs(user, ticket):
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
    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if not _can_access_ticket_docs(user, ticket):
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
        'Fire Alarm & Detection',
        'Fire Suppression',
        'Fire Safety Equipment',
        'Emergency & Evacuation',
    ],
    'categories': {
        'Fire Alarm & Detection': [
            'Fire Control Panel',
            'Smoke Detectors',
            'Heat Detectors',
            'Manual Call Points',
            'Alarm Sounders & Strobes',
            'Addressable Devices',
            'Fire Alarm Cabling',
            'Beam Detectors',
            'Gas Detectors',
            'Other',
        ],
        'Fire Suppression': [
            'Sprinkler System',
            'FM200 Gas Suppression',
            'CO2 Suppression System',
            'Foam System',
            'Deluge System',
            'Water Mist System',
            'Suppression Control Panel',
            'Suppression Cylinders & Valves',
            'Pipework & Fittings',
            'Other',
        ],
        'Fire Safety Equipment': [
            'Portable Fire Extinguishers',
            'Hose Reels',
            'Fire Blankets',
            'Dry Risers',
            'Fire Hydrants',
            'Fire Cabinets',
            'Sand Buckets',
            'Firefighting Pumps',
            'Other',
        ],
        'Emergency & Evacuation': [
            'Emergency Lighting',
            'Exit Signs & Wayfinding',
            'Public Address System',
            'Evacuation Alarm',
            'Fire Escape Routes',
            'Fire Doors & Barriers',
            'Assembly Point Signage',
            'Other',
        ],
    },
    'fault_types': [
        'Breakdown / Fault',
        'Preventive Maintenance (PPM)',
        'Corrective Maintenance',
        'Annual Inspection',
        'False Alarm Investigation',
        'Installation',
        'Commissioning',
        'Testing & Certification',
        'Upgrade / Modification',
        'Emergency Response',
        'Compliance Audit',
        'Other',
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


# ---------------------------------------------------------------------------
# Service Report: digital form page
# ---------------------------------------------------------------------------

@ticketing_bp.route('/<string:ticket_id>/service-report', methods=['GET'])
@jwt_required()
def service_report_page(ticket_id):
    """Render the digital service report form for a completed work order."""
    user = _current_user()
    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    if not _can_access_ticket_docs(user, ticket):
        abort(403)
    notes = ticket.notes.order_by(TicketNote.created_at.asc()).all()
    images = ticket.images.all()
    materials = ticket.materials.all()
    manpower_entries = ticket.manpower.all()
    return render_template(
        'ticket_service_report.html',
        ticket=ticket,
        notes=notes,
        images=images,
        materials=materials,
        manpower_entries=manpower_entries,
        user=user,
    )


# ---------------------------------------------------------------------------
# Client sign-off
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/client-sign', methods=['POST'])
@jwt_required()
def client_sign_ticket(ticket_id):
    """Record the client's digital signature on a completed service report."""
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

    if not signature:
        return jsonify({'success': False, 'error': 'Client signature is required'}), 400
    if not signed_by:
        return jsonify({'success': False, 'error': 'Client name is required'}), 400

    ticket.client_signature = signature
    ticket.client_signed_by = signed_by
    ticket.client_signed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    mobile = (data.get('client_mobile') or '').strip()
    if mobile:
        ticket.client_mobile = mobile

    _add_note(ticket, user,
              f'Service report signed by client: {signed_by}.',
              note_type='status_change')
    db.session.commit()
    return jsonify({'success': True, 'client_signed_by': signed_by})


# ---------------------------------------------------------------------------
# Amaan Service Report data (GET / PATCH)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/service-report-data', methods=['GET'])
@jwt_required()
def get_service_report_data(ticket_id):
    """Return merged auto-fill + saved service report JSON."""
    user = _current_user()
    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    if not _can_access_ticket_docs(user, ticket):
        abort(403)
    from module_ticketing.service_report import merge_service_report_data, get_or_assign_service_report_no
    materials = ticket.materials.all()
    srn = get_or_assign_service_report_no(ticket)
    data = merge_service_report_data(ticket, materials)
    data['service_report_no'] = srn
    # Include read-only parts_used from TicketMaterial
    data['parts_used'] = [
        {'part': m.material_name, 'specification': m.notes or '', 'qty': m.quantity}
        for m in materials
    ]
    return jsonify({'success': True, 'data': data, 'srn': srn})


@ticketing_bp.route('/api/tickets/<string:ticket_id>/service-report-data', methods=['PATCH'])
@jwt_required()
def save_service_report_data(ticket_id):
    """Persist editable service report fields."""
    import json as _json
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    deny = _api_forbid_unless_ticket_visible(user, ticket)
    if deny:
        return deny

    payload = request.get_json(silent=True) or {}

    # Load existing saved data and merge
    try:
        existing = _json.loads(ticket.service_report_data) if ticket.service_report_data else {}
    except Exception:
        existing = {}

    # SRN is editable (the paper form's "Need to change" note). Validate + guard uniqueness.
    new_srn = payload.pop('service_report_no', None)
    payload.pop('_auto', None)
    payload.pop('parts_used', None)

    if new_srn not in (None, ''):
        try:
            new_srn_int = int(new_srn)
            if new_srn_int <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'SRN must be a positive number'}), 400
        if new_srn_int != ticket.service_report_no:
            clash = Ticket.query.filter(
                Ticket.service_report_no == new_srn_int,
                Ticket.id != ticket.id,
            ).first()
            if clash:
                return jsonify({'success': False,
                                'error': f'SRN {new_srn_int} is already in use by {clash.ticket_id}'}), 400
            ticket.service_report_no = new_srn_int

    existing.update(payload)
    # Remove _auto flag so we know user has edited this
    existing.pop('_auto', None)

    # Validate job_type (accept legacy maintenance/installation aliases)
    from module_ticketing.service_report import VALID_JOB_TYPES, normalize_job_type
    if 'job_type' in existing:
        existing['job_type'] = normalize_job_type(existing['job_type'])
        if existing['job_type'] not in VALID_JOB_TYPES:
            return jsonify({'success': False, 'error': 'Invalid job_type'}), 400

    # Strip empty parts_required rows
    if 'parts_required' in existing:
        existing['parts_required'] = [
            r for r in existing['parts_required']
            if (r.get('part') or '').strip()
        ]

    # Persist top-level convenience fields
    if 'client_mobile' in payload and payload['client_mobile']:
        ticket.client_mobile = payload['client_mobile'].strip()
    if 'technician_id_no' in payload and payload['technician_id_no']:
        ticket.technician_id_no = payload['technician_id_no'].strip()

    ticket.service_report_data = _json.dumps(existing)
    db.session.commit()
    return jsonify({'success': True})


# Service report PDF download
@ticketing_bp.route('/<string:ticket_id>/service-report/pdf', methods=['GET'])
@jwt_required()
def download_service_report_pdf(ticket_id):
    """Generate and stream the Amaan Service Report PDF."""
    user = _current_user()
    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()
    if not _can_access_ticket_docs(user, ticket):
        abort(403)
    from module_ticketing.service_report import merge_service_report_data, get_or_assign_service_report_no
    from module_ticketing.service_report_pdf_builder import build_service_report_pdf
    materials = ticket.materials.all()
    srn = get_or_assign_service_report_no(ticket)
    sr_data = merge_service_report_data(ticket, materials)
    sr_data['service_report_no'] = srn
    buf = io.BytesIO()
    build_service_report_pdf(ticket, sr_data, materials, buf)
    buf.seek(0)
    filename = f'ServiceReport_{ticket.ticket_id}.pdf'
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# GM approval / rejection + Finance confirmation (mandatory closing gates)
# ---------------------------------------------------------------------------

@ticketing_bp.route('/api/tickets/<string:ticket_id>/gm-approve', methods=['POST'])
@jwt_required()
def gm_approve_ticket(ticket_id):
    """GM approves a ticket in pending_gm_approval → moves it to pending_finance and auto-generates invoice."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if user.role != 'admin' and getattr(user, 'designation', None) != 'general_manager':
        return jsonify({'success': False, 'error': 'Only General Manager or Admin may approve tickets'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if ticket.status != 'pending_gm_approval':
        return jsonify({'success': False, 'error': f'Ticket is not awaiting GM approval. Current status: {ticket.status}'}), 400

    data = request.get_json(silent=True) or {}
    notes = (data.get('notes') or '').strip() or None

    ticket.gm_approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket.gm_approved_by_id = user.id
    ticket.gm_approval_notes = notes
    ticket.gm_rejected_at = None
    ticket.gm_rejection_notes = None

    if ticket.finance_confirmed_at:
        # Finance already logged the ERP invoice — GM approval was the last gate.
        ticket.status = 'closed'
        ticket.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        _add_note(ticket, user,
                  f'GM approval granted by {user.full_name}. Finance had already logged the invoice'
                  f'{(" (ref: " + ticket.finance_invoice_ref + ")") if ticket.finance_invoice_ref else ""}, '
                  f'so the ticket is now fully closed. '
                  f'{("Notes: " + notes) if notes else ""}',
                  note_type='status_change')

        for uid in filter(None, {ticket.supervisor_id, ticket.reporter_id}):
            _notify_user(uid,
                         f'Ticket Closed — {ticket.ticket_id}',
                         f'Ticket "{ticket.title}" has been approved by the GM and fully closed. '
                         f'Invoice was processed by Finance.',
                         ntype='success',
                         ticket_id=ticket.ticket_id)

        db.session.commit()
        _send_completion_emails(ticket, user)
        return jsonify({'success': True, 'status': 'closed', 'approved_by': user.full_name})

    ticket.status = 'pending_finance'

    _add_note(ticket, user,
              f'GM approval granted by {user.full_name}. Ticket approved and sent to Finance for invoicing. '
              f'{("Notes: " + notes) if notes else ""}',
              note_type='status_change')

    # Notify Finance team (users with designation='finance' or role='admin')
    finance_users = User.query.filter(
        User.is_active == True,  # noqa: E712
        db.or_(User.designation == 'finance', User.role == 'admin'),
    ).all()
    for fu in finance_users:
        _notify_user(fu.id,
                     f'Invoice Required — {ticket.ticket_id}',
                     f'GM has approved ticket "{ticket.title}" (Project: {ticket.project}). '
                     f'Selling price: AED {ticket.selling_price or 0:.2f}. Please create the invoice.',
                     ntype='info',
                     ticket_id=ticket.ticket_id)

    # Also notify the supervisor
    if ticket.supervisor_id:
        _notify_user(ticket.supervisor_id,
                     f'GM Approved — {ticket.ticket_id}',
                     f'Your ticket "{ticket.title}" has been approved by the GM and sent to Finance.',
                     ntype='success',
                     ticket_id=ticket.ticket_id)

    db.session.commit()
    return jsonify({'success': True, 'status': 'pending_finance', 'approved_by': user.full_name})


@ticketing_bp.route('/api/tickets/<string:ticket_id>/gm-reject', methods=['POST'])
@jwt_required()
def gm_reject_ticket(ticket_id):
    """GM rejects a ticket in pending_gm_approval → sends it back to Supervisor Review."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if user.role != 'admin' and getattr(user, 'designation', None) != 'general_manager':
        return jsonify({'success': False, 'error': 'Only General Manager or Admin may reject tickets'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if ticket.status != 'pending_gm_approval':
        return jsonify({'success': False, 'error': f'Ticket is not awaiting GM approval. Current status: {ticket.status}'}), 400

    data = request.get_json(silent=True) or {}
    rejection_notes = (data.get('notes') or '').strip()
    if not rejection_notes:
        return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400

    ticket.gm_rejected_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket.gm_rejection_notes = rejection_notes
    ticket.status = 'verification'

    # If Finance already logged the invoice in parallel, reset their confirmation —
    # pricing may change after rework. Keep finance_invoice_ref for reference.
    finance_had_confirmed = bool(ticket.finance_confirmed_at)
    if finance_had_confirmed:
        ticket.finance_confirmed_at = None
        ticket.finance_confirmed_by_id = None

    _add_note(ticket, user,
              f'GM rejected by {user.full_name}. Ticket returned to Supervisor Review. '
              f'Reason: {rejection_notes}'
              f'{" Finance invoice confirmation has been reset and may need revision." if finance_had_confirmed else ""}',
              note_type='status_change')

    # Notify supervisor
    if ticket.supervisor_id:
        _notify_user(ticket.supervisor_id,
                     f'GM Rejected — {ticket.ticket_id}',
                     f'Your ticket "{ticket.title}" was rejected by the GM. '
                     f'Reason: {rejection_notes}. Please review and resubmit.',
                     ntype='error',
                     ticket_id=ticket.ticket_id)

    # Notify finance if their parallel invoice work was invalidated
    if finance_had_confirmed:
        finance_users = User.query.filter(
            User.is_active == True,  # noqa: E712
            db.or_(User.designation == 'finance', User.role == 'admin'),
        ).all()
        for fu in finance_users:
            _notify_user(fu.id,
                         f'GM Rejected — {ticket.ticket_id}',
                         f'Ticket "{ticket.title}" was rejected by the GM and returned to the supervisor. '
                         f'The ERP invoice{(" (ref: " + ticket.finance_invoice_ref + ")") if ticket.finance_invoice_ref else ""} '
                         f'may need revision once the ticket is resubmitted.',
                         ntype='warning',
                         ticket_id=ticket.ticket_id)

    db.session.commit()
    return jsonify({'success': True, 'status': 'verification', 'rejected_by': user.full_name})


@ticketing_bp.route('/api/tickets/<string:ticket_id>/finance-confirm', methods=['POST'])
@jwt_required()
def finance_confirm_ticket(ticket_id):
    """Finance team confirms invoice created → ticket is fully closed."""
    user = _current_user()
    # Mirror the Finance dashboard's access (admin / GM / Ops Manager / finance / ticketing access).
    _desig = (getattr(user, 'designation', None) or '').strip().lower()
    _may_confirm = bool(user and (
        user.role == 'admin'
        or _desig in ('finance', 'general_manager', 'operations_manager')
        or getattr(user, 'access_ticketing', False)
    ))
    if not _may_confirm:
        return jsonify({'success': False, 'error': 'You do not have permission to confirm invoices'}), 403

    ticket = Ticket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if ticket.status not in ('pending_finance', 'pending_gm_approval'):
        return jsonify({'success': False, 'error': f'Ticket is not pending finance confirmation. Current status: {ticket.status}'}), 400

    data = request.get_json(silent=True) or {}
    invoice_ref  = (data.get('invoice_ref') or '').strip() or None
    custom_to    = [e.strip() for e in (data.get('email_to') or '').split(',') if e.strip()] or None
    custom_cc    = [e.strip() for e in (data.get('email_cc') or '').split(',') if e.strip()] or None
    custom_body  = (data.get('email_body') or '').strip() or None

    # Apply Finance Settings: ERP ref requirement + shared notification defaults
    try:
        from module_finance.routes import _get_finance_settings
        fin_cfg = _get_finance_settings()
    except Exception:
        fin_cfg = {}
    if fin_cfg.get('require_erp_ref') and not invoice_ref:
        prefix = fin_cfg.get('erp_ref_prefix') or 'INV'
        return jsonify({
            'success': False,
            'error': f'ERP invoice reference is required (e.g. {prefix}-2026-00001). Configure this in Finance Settings.',
        }), 400
    if not custom_to and fin_cfg.get('invoice_email_to'):
        custom_to = [e.strip() for e in fin_cfg['invoice_email_to'].split(',') if e.strip()] or None
    if not custom_cc and fin_cfg.get('invoice_email_cc'):
        custom_cc = [e.strip() for e in fin_cfg['invoice_email_cc'].split(',') if e.strip()] or None

    ticket.finance_confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket.finance_confirmed_by_id = user.id
    ticket.finance_invoice_ref = invoice_ref

    if ticket.status == 'pending_gm_approval':
        # Finance finished first — GM approval is the final gate, so don't close yet.
        _add_note(ticket, user,
                  f'Invoice logged by Finance ({user.full_name}). '
                  f'{("Invoice ref: " + invoice_ref + ". ") if invoice_ref else ""}'
                  f'Awaiting GM approval to close the ticket.',
                  note_type='status_change')

        gm_users = User.query.filter(
            User.is_active == True,  # noqa: E712
            db.or_(User.role == 'admin', User.designation == 'general_manager'),
        ).all()
        for gm in gm_users:
            _notify_user(gm.id,
                         f'Finance Done — {ticket.ticket_id}',
                         f'Finance has logged the ERP invoice for ticket "{ticket.title}"'
                         f'{(" (ref: " + invoice_ref + ")") if invoice_ref else ""}. '
                         f'Only your approval is pending to close the ticket.',
                         ntype='info',
                         ticket_id=ticket.ticket_id)

        db.session.commit()
        return jsonify({'success': True, 'status': 'pending_gm_approval', 'invoice_ref': invoice_ref})

    # GM already approved (pending_finance) — finance confirmation fully closes the ticket.
    ticket.status = 'closed'
    ticket.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    _add_note(ticket, user,
              f'Invoice confirmed by Finance ({user.full_name}). '
              f'{("Invoice ref: " + invoice_ref + ". ") if invoice_ref else ""}'
              f'Ticket is now fully closed.',
              note_type='status_change')

    for uid in filter(None, {ticket.supervisor_id, ticket.reporter_id}):
        _notify_user(uid,
                     f'Ticket Closed — {ticket.ticket_id}',
                     f'Ticket "{ticket.title}" has been fully closed. Invoice processed by Finance.',
                     ntype='success',
                     ticket_id=ticket.ticket_id)

    db.session.commit()
    _send_completion_emails(ticket, user, custom_to=custom_to, custom_cc=custom_cc, custom_body=custom_body)
    return jsonify({'success': True, 'status': 'closed', 'invoice_ref': invoice_ref})


# ---------------------------------------------------------------------------
# Reports — spec-driven PDF / Excel downloads
# ---------------------------------------------------------------------------

_FINANCE_TIER_REPORTS = {'financial', 'projects'}


def _can_use_finance_reports(user: User) -> bool:
    return _ticketing_sees_all_tickets(user) or _is_finance_user(user)


def _report_filtered_tickets(user: User, args):
    """Visible tickets narrowed by the shared report filters (date range, project, status)."""
    q = _visible_tickets_base_query(user)

    date_from = (args.get('date_from') or '').strip()
    date_to = (args.get('date_to') or '').strip()
    project = (args.get('project') or '').strip()
    status = (args.get('status') or '').strip()

    label_parts = []
    if date_from:
        try:
            q = q.filter(Ticket.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
            label_parts.append(f'from {date_from}')
        except ValueError:
            pass
    if date_to:
        try:
            # inclusive end-of-day
            q = q.filter(Ticket.created_at < datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            label_parts.append(f'to {date_to}')
        except ValueError:
            pass
    if project:
        q = q.filter(Ticket.project == project)
        label_parts.append(f'project: {project}')
    if status:
        q = q.filter(Ticket.status == status)
        label_parts.append(f'status: {_STATUS_LABELS.get(status, status)}')

    return q.order_by(Ticket.created_at.desc()).all(), ', '.join(label_parts)


def _fmt_dt(value):
    if not value:
        return ''
    try:
        return value.strftime('%d %b %Y')
    except AttributeError:
        return str(value)


def _report_rows(report_key: str, user: User, args):
    """Build (rows, summary) for a report key. Rows are dicts keyed by column spec keys."""
    tickets, filters_label = _report_filtered_tickets(user, args)

    if report_key == 'work_orders':
        rows = [{
            'ticket_id': t.ticket_id,
            'title': t.title,
            'project': t.project,
            'service_group': t.service_group,
            'priority': (t.priority or '').capitalize(),
            'status': _STATUS_LABELS.get(t.status, t.status),
            'supervisor': t.supervisor.full_name if t.supervisor else '',
            'technician': t.technician.full_name if t.technician else '',
            'created': _fmt_dt(t.created_at),
            'closed': _fmt_dt(t.closed_at),
        } for t in tickets]
        statuses = [t.status for t in tickets]
        summary = [
            ('Total', len(tickets)),
            ('Open', statuses.count('open')),
            ('In Progress', sum(1 for s in statuses if s in ('assigned', 'site_attended', 'work_started', 'in_progress'))),
            ('Completed', sum(1 for s in statuses if s in ('work_completed', 'verification', 'pending_gm_approval', 'pending_finance'))),
            ('Closed', statuses.count('closed')),
            ('Cancelled', statuses.count('cancelled')),
        ]
        return rows, summary, filters_label

    if report_key == 'financial':
        fin_tickets = [t for t in tickets if t.is_chargeable or t.selling_price or t.total_cost]
        rows = []
        for t in fin_tickets:
            margin = (t.selling_price or 0) - (t.total_cost or 0)
            rows.append({
                'ticket_id': t.ticket_id,
                'project': t.project,
                'title': t.title,
                'total_cost': t.total_cost or 0,
                'actual_price': t.actual_price or 0,
                'markup_pct': t.markup_pct or 0,
                'selling_price': t.selling_price or 0,
                'margin': margin,
                'invoice_ref': t.finance_invoice_ref or '',
                'closed': _fmt_dt(t.closed_at),
            })
        total_rev = sum(r['selling_price'] for r in rows)
        total_cost = sum(r['total_cost'] for r in rows)
        summary = [
            ('Work Orders', len(rows)),
            ('Revenue (AED)', f'{total_rev:,.2f}'),
            ('Cost (AED)', f'{total_cost:,.2f}'),
            ('Margin (AED)', f'{total_rev - total_cost:,.2f}'),
            ('Invoiced', sum(1 for r in rows if r['invoice_ref'])),
        ]
        return rows, summary, filters_label

    if report_key == 'projects':
        by_project = {}
        for t in tickets:
            by_project.setdefault(t.project or '—', []).append(t)
        rows = []
        for project, ts in sorted(by_project.items()):
            closed = [t for t in ts if t.status == 'closed']
            close_days = [
                (t.closed_at - t.created_at).days
                for t in closed if t.closed_at and t.created_at
            ]
            revenue = sum(t.selling_price or 0 for t in ts)
            cost = sum(t.total_cost or 0 for t in ts)
            rows.append({
                'project': project,
                'total': len(ts),
                'open': sum(1 for t in ts if t.status not in ('closed', 'cancelled')),
                'closed': len(closed),
                'revenue': revenue,
                'cost': cost,
                'margin': revenue - cost,
                'avg_close_days': f'{sum(close_days) / len(close_days):.1f}' if close_days else '—',
            })
        summary = [
            ('Projects', len(rows)),
            ('Work Orders', sum(r['total'] for r in rows)),
            ('Revenue (AED)', f"{sum(r['revenue'] for r in rows):,.2f}"),
            ('Margin (AED)', f"{sum(r['margin'] for r in rows):,.2f}"),
        ]
        return rows, summary, filters_label

    if report_key == 'team':
        people = {}

        def _bucket(u, role):
            if not u:
                return None
            key = (u.id, role)
            if key not in people:
                people[key] = {'name': u.full_name or u.username, 'role': role,
                               'assigned': 0, 'completed': 0, 'hours': 0.0, 'labour_cost': 0.0}
            return people[key]

        for t in tickets:
            tech = _bucket(t.technician, 'Technician')
            if tech:
                tech['assigned'] += 1
                if t.status in ('work_completed', 'verification', 'pending_gm_approval', 'pending_finance', 'closed'):
                    tech['completed'] += 1
            sup = _bucket(t.supervisor, 'Supervisor')
            if sup:
                sup['assigned'] += 1
                if t.status == 'closed':
                    sup['completed'] += 1
            for mp in t.manpower.all():
                worker = None
                if mp.worker_user_id:
                    wu = User.query.get(mp.worker_user_id)
                    worker = _bucket(wu, 'Technician') if wu else None
                if worker is None and mp.worker_name:
                    key = (mp.worker_name, 'Technician')
                    if key not in people:
                        people[key] = {'name': mp.worker_name, 'role': 'Technician',
                                       'assigned': 0, 'completed': 0, 'hours': 0.0, 'labour_cost': 0.0}
                    worker = people[key]
                if worker:
                    worker['hours'] += mp.hours or 0
                    worker['labour_cost'] += mp.total_cost or 0

        rows = sorted(people.values(), key=lambda r: (-r['assigned'], r['name']))
        for r in rows:
            r['hours'] = f"{r['hours']:.2f}".rstrip('0').rstrip('.')
        summary = [
            ('Team Members', len(rows)),
            ('Orders Covered', len(tickets)),
            ('Labour Cost (AED)', f"{sum(r['labour_cost'] for r in rows):,.2f}"),
        ]
        return rows, summary, filters_label

    if report_key == 'materials':
        agg = {}
        for t in tickets:
            for m in t.materials.all():
                key = ((m.material_name or '').strip().lower(), (m.unit or '').strip().lower())
                entry = agg.setdefault(key, {
                    'material': (m.material_name or '').strip() or '—',
                    'unit': (m.unit or '').strip(),
                    'quantity': 0.0, 'spend': 0.0, '_prices': [], '_tickets': set(),
                })
                entry['quantity'] += m.quantity or 0
                entry['spend'] += m.total_price or 0
                if m.unit_price:
                    entry['_prices'].append(m.unit_price)
                entry['_tickets'].add(t.ticket_id)

        rows = []
        for entry in sorted(agg.values(), key=lambda e: -e['spend']):
            rows.append({
                'material': entry['material'],
                'unit': entry['unit'],
                'quantity': f"{entry['quantity']:.2f}".rstrip('0').rstrip('.'),
                'avg_price': (sum(entry['_prices']) / len(entry['_prices'])) if entry['_prices'] else 0,
                'spend': entry['spend'],
                'tickets': len(entry['_tickets']),
            })
        summary = [
            ('Distinct Materials', len(rows)),
            ('Total Spend (AED)', f"{sum(r['spend'] for r in rows):,.2f}"),
            ('Orders With Materials', len({tid for e in agg.values() for tid in e['_tickets']})),
        ]
        return rows, summary, filters_label

    return None, None, filters_label


@ticketing_bp.route('/reports', methods=['GET'])
@jwt_required()
def reports_page():
    """Reports hub — download work-order, financial and operational reports."""
    user = _current_user()
    if not _has_access(user):
        abort(403)

    from module_ticketing.report_builders import REPORT_SPECS
    can_finance = _can_use_finance_reports(user)

    projects = sorted({
        p[0] for p in _visible_tickets_base_query(user)
        .with_entities(Ticket.project).distinct() if p[0]
    })

    return render_template(
        'ticket_reports.html',
        user=user,
        report_specs=REPORT_SPECS,
        can_finance=can_finance,
        projects=projects,
        status_labels=_STATUS_LABELS,
        sidebar_stats=_get_sidebar_stats(user),
    )


# ---------------------------------------------------------------------------
# Analytics — resolution speed, SLA breach-risk, stage bottlenecks, team & faults
# ---------------------------------------------------------------------------

def _build_ticket_analytics(user) -> dict:
    """Crunch every analytics view from the user's visible tickets.

    Routes scope + fetch; module_ticketing.analytics does the maths. Cost/margin
    figures are only included for finance-tier users.
    """
    from module_ticketing import analytics as A

    tickets = _visible_tickets_base_query(user).all()
    ticket_ids = [t.id for t in tickets]
    can_finance = _can_use_finance_reports(user)

    status_notes, manpower = [], []
    if ticket_ids:
        status_notes = (
            TicketNote.query
            .filter(TicketNote.ticket_id.in_(ticket_ids),
                    TicketNote.note_type == 'status_change')
            .all()
        )
        manpower = TicketManpower.query.filter(TicketManpower.ticket_id.in_(ticket_ids)).all()

    # On-hold tickets have a paused clock, so they're excluded from breach risk.
    open_for_breach = [
        t for t in tickets if t.status in _ACTIVE_STATUSES and t.status != 'on_hold'
    ]
    users = {u.id: u for u in User.query.all()}

    return {
        'resolution': A.compute_resolution_stats(tickets),
        'stages': A.compute_stage_durations(tickets, status_notes),
        'breach': A.compute_breach_risk(open_for_breach, tickets),
        'team': A.compute_team_perf(tickets, manpower, users),
        'faults': A.compute_fault_pareto(tickets, include_cost=can_finance),
        'meta': {
            'total': len(tickets),
            'open': len(open_for_breach),
            'can_finance': can_finance,
            'sla_targets': A.SLA_TARGET_HOURS,
            'status_labels': _STATUS_LABELS,
        },
    }


@ticketing_bp.route('/analytics', methods=['GET'])
@jwt_required()
def analytics_page():
    """Analytics hub — speed, SLA breach-risk, stage bottlenecks, team & fault insights."""
    user = _current_user()
    if not _has_access(user):
        abort(403)
    return render_template(
        'ticket_analytics.html',
        user=user,
        can_finance=_can_use_finance_reports(user),
        sidebar_stats=_get_sidebar_stats(user),
        active_page='ticketing',
    )


@ticketing_bp.route('/api/analytics/data', methods=['GET'])
@jwt_required()
def analytics_data():
    """JSON payload feeding the analytics page charts/tables."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return jsonify({'success': True, 'data': _build_ticket_analytics(user)})


@ticketing_bp.route('/api/reports/<string:report_key>/download', methods=['GET'])
@jwt_required()
def download_report(report_key):
    """Build the requested report and stream it as PDF or Excel."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    from module_ticketing.report_builders import (
        REPORT_SPECS, build_report_pdf, build_report_excel,
    )

    spec = REPORT_SPECS.get(report_key)
    if not spec:
        return jsonify({'success': False, 'error': 'Unknown report'}), 404

    if report_key in _FINANCE_TIER_REPORTS and not _can_use_finance_reports(user):
        return jsonify({'success': False, 'error': 'This report is restricted to management and finance'}), 403

    fmt = (request.args.get('format') or 'pdf').lower()
    if fmt not in ('pdf', 'excel'):
        return jsonify({'success': False, 'error': 'format must be pdf or excel'}), 400

    rows, summary, filters_label = _report_rows(report_key, user, request.args)
    if rows is None:
        return jsonify({'success': False, 'error': 'Unknown report'}), 404

    buf = io.BytesIO()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d')
    if fmt == 'pdf':
        build_report_pdf(spec, rows, summary, filters_label, buf)
        mimetype = 'application/pdf'
        filename = f'AMAAN_{report_key}_{stamp}.pdf'
    else:
        build_report_excel(spec, rows, summary, filters_label, buf)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = f'AMAAN_{report_key}_{stamp}.xlsx'
    buf.seek(0)

    return send_file(buf, mimetype=mimetype, as_attachment=True, download_name=filename)
