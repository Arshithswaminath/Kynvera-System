"""
Amaan Service Report helpers.

Manages the `service_report_data` JSON blob stored on Ticket and provides
auto-fill logic that maps existing ticket/materials data to the paper template.
"""
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Job-type mapping ──────────────────────────────────────────────────────────

_PPM_TYPES = {
    'Preventive Maintenance (PPM)',
    'Corrective Maintenance',
}
_INSPECTION_TYPES = {
    'Annual Inspection',
    'Testing & Certification',
    'Compliance Audit',
}
_OTHERS_TYPES = {
    'False Alarm Investigation',
    'Emergency Response',
    'Other',
    'Breakdown / Fault',
    'Installation',
    'Commissioning',
    'Upgrade / Modification',
}

# Accepted job_type values on the service report (PDF + UI)
VALID_JOB_TYPES = {'ppm', 'inspection', 'rectification', 'others'}
# Older saved reports used maintenance/installation
_JOB_TYPE_ALIASES = {
    'maintenance': 'ppm',
    'installation': 'inspection',
}


def normalize_job_type(value: str) -> str:
    """Map legacy or raw job_type values to ppm|inspection|rectification|others."""
    v = (value or '').strip().lower()
    v = _JOB_TYPE_ALIASES.get(v, v)
    return v if v in VALID_JOB_TYPES else 'others'


def map_job_type(ticket) -> str:
    """Return one of ppm|inspection|rectification|others from ticket data."""
    if ticket.source_inspection_notif_id:
        return 'rectification'
    ft = (ticket.fault_type or '').strip()
    if ft in _PPM_TYPES or 'PPM' in ft.upper():
        return 'ppm'
    if ft in _INSPECTION_TYPES or 'inspection' in ft.lower():
        return 'inspection'
    if ft in _OTHERS_TYPES:
        return 'others'
    return 'others'


# ── Time helpers ──────────────────────────────────────────────────────────────

def _parse_iso(val):
    """Parse an ISO datetime string stored as TEXT in SQLite. Returns datetime or None."""
    if not val:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(val[:26], fmt)
        except ValueError:
            continue
    return None


def _dt_to_hm(dt) -> dict:
    if dt is None:
        return {'h': None, 'm': None}
    return {'h': dt.hour, 'm': dt.minute}


def _hm_diff(arrive: datetime, left: datetime) -> dict:
    if arrive is None or left is None:
        return {'h': None, 'm': None}
    delta = left - arrive
    if delta.total_seconds() < 0:
        return {'h': None, 'm': None}
    total_mins = int(delta.total_seconds() // 60)
    return {'h': total_mins // 60, 'm': total_mins % 60}


# ── Auto-fill builder ─────────────────────────────────────────────────────────

def build_service_report_defaults(ticket, materials) -> dict:
    """
    Build the default service_report_data dict from ticket fields.
    Called when a ticket has no saved service_report_data yet, or to
    fill-in keys that the user has never touched.
    """
    # Client name: prefer project's client_name if available via backref
    client_name = ''
    try:
        proj_obj = ticket.ticket_project  # TicketProject relationship if present
        if proj_obj and proj_obj.client_name:
            client_name = proj_obj.client_name
    except Exception:
        pass
    if not client_name:
        client_name = ticket.project or ''

    # Service date: prefer first manpower work_date, then site_attended_at
    service_date = ''
    if materials:
        from app.models import TicketManpower
    try:
        mp_entries = ticket.manpower.all() if hasattr(ticket, 'manpower') else []
        dates = [e.work_date for e in mp_entries if e.work_date]
        if dates:
            service_date = min(dates).isoformat()
    except Exception:
        pass
    if not service_date:
        arrive_raw = getattr(ticket, 'site_attended_at', None)
        dt_arrive = _parse_iso(arrive_raw)
        if dt_arrive:
            service_date = dt_arrive.date().isoformat()
    if not service_date and ticket.created_at:
        service_date = ticket.created_at.date().isoformat()

    # Time arrive / left
    arrive_dt = _parse_iso(getattr(ticket, 'site_attended_at', None))
    left_dt   = _parse_iso(getattr(ticket, 'work_completed_at', None))

    # Location / site / technician (auto, but editable)
    site_name = ticket.property_name or ''
    location  = ' / '.join(filter(None, [ticket.zone, ticket.sub_zone, ticket.base_unit]))
    technician_name = ''
    if getattr(ticket, 'technician', None):
        technician_name = ticket.technician.full_name
    elif getattr(ticket, 'assigned_to', None):
        technician_name = ticket.assigned_to.full_name

    # Comments: merge resolution notes
    comments_parts = []
    if ticket.technician_resolution_notes:
        comments_parts.append(ticket.technician_resolution_notes.strip())
    if ticket.service_report_notes:
        comments_parts.append(ticket.service_report_notes.strip())
    comments = '\n\n'.join(comments_parts)

    # Parts used → specification via material.notes
    parts_used = []
    for m in (materials or []):
        parts_used.append({
            'part': m.material_name or '',
            'specification': m.notes or '',
            'qty': m.quantity,
        })

    return {
        '_auto': True,                          # flag so UI knows this is auto-generated
        'client_name': client_name,
        'job_no': ticket.ticket_id,
        'site_name': site_name,
        'location': location,
        'technician_name': technician_name,
        'service_date': service_date,
        'time_arrive': _dt_to_hm(arrive_dt),
        'time_left': _dt_to_hm(left_dt),
        'travel_time': {'h': None, 'm': None},
        'total_time': _hm_diff(arrive_dt, left_dt),
        'fire_alarm': {'qty': '', 'type': '', 'make': '', 'zones_loops': ''},
        'fire_fighting': {
            'fire_extinguisher': False,
            'gas_suppression': False,
            'hose_reel': False,
            'kitchen_hood': False,
            'sprinkler': False,
            'wet_dry_riser': False,
            'fire_pump_set': False,
            'others': False,
            'others_text': '',
        },
        'job_type': map_job_type(ticket),
        'job_type_other': '',
        'job_name': (ticket.title or '').strip(),
        'comments': comments,
        'parts_required': [],
        'customer_remarks': '',
        'client_mobile': ticket.client_mobile or '',
        'technician_id_no': ticket.technician_id_no or '',
    }


def merge_service_report_data(ticket, materials) -> dict:
    """
    Return the effective service_report_data dict.
    Saved user edits take precedence; auto-fill only populates keys the
    user has never set (i.e. absent from saved JSON or still null/empty).
    """
    defaults = build_service_report_defaults(ticket, materials)

    saved_raw = ticket.service_report_data
    if not saved_raw:
        return defaults

    try:
        saved = json.loads(saved_raw) if isinstance(saved_raw, str) else saved_raw
    except (json.JSONDecodeError, TypeError):
        return defaults

    # Merge: saved wins on non-empty scalar values; nested dicts merged shallowly
    merged = dict(defaults)
    for key, saved_val in saved.items():
        if key == '_auto':
            continue
        if key == 'job_name':
            # Always prefer live ticket title (not a user-editable SR field)
            continue
        if key in ('fire_alarm', 'fire_fighting', 'time_arrive', 'time_left',
                   'travel_time', 'total_time'):
            # Nested dict: merge key-by-key so auto-fills still apply to untouched sub-keys
            if isinstance(saved_val, dict):
                sub = dict(merged.get(key, {}))
                sub.update({k: v for k, v in saved_val.items() if v not in (None, '')})
                merged[key] = sub
        elif key == 'parts_required':
            merged[key] = saved_val  # user-managed list, keep as-is
        elif saved_val not in (None, ''):
            merged[key] = saved_val

    # Keep job_name in sync with the ticket title
    merged['job_name'] = (ticket.title or '').strip() or merged.get('job_name', '')

    return merged


def get_or_assign_service_report_no(ticket) -> int:
    """
    Assign and persist a sequential SRN if the ticket doesn't have one yet.

    Format: YYNNN where YY is the 2-digit year and NNN is a sequence
    starting at 001 (e.g. 2026 → 26001, 26002, …).
    """
    if ticket.service_report_no:
        return ticket.service_report_no

    from app.models import db, Ticket as TicketModel

    yy = datetime.now().year % 100
    year_floor = yy * 1000          # 2026 → 26000
    year_start = year_floor + 1     # first SRN of the year → 26001
    year_ceil = year_floor + 1000   # exclusive upper bound → 27000

    max_in_year = (
        db.session.query(db.func.max(TicketModel.service_report_no))
        .filter(
            TicketModel.service_report_no >= year_floor,
            TicketModel.service_report_no < year_ceil,
        )
        .scalar()
    )
    next_no = (max_in_year + 1) if max_in_year else year_start
    ticket.service_report_no = next_no
    db.session.commit()
    return next_no
