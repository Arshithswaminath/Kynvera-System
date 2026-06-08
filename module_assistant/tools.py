"""
Server-side data tools for the Injaaz assistant.
All queries are scoped to the authenticated user — never accept user_id from the client.
"""
import json
import re
from datetime import datetime

from sqlalchemy import or_

from app.models import DocHubDocument, Submission

INSPECTION_MODULE_TYPES = (
    'hvac_mep', 'civil', 'cleaning', 'qhsi_inspection', 'qhsi_staff_compliance',
)
HR_LEAVE_MODULE_TYPES = ('hr_leave_application', 'hr_leave')
TERMINAL_WORKFLOW = ('completed', 'closed_by_admin', 'rejected')


def _is_hr_module(module_type: str) -> bool:
    return (module_type or '').startswith('hr_')


def _is_inspection_module(module_type: str) -> bool:
    return (module_type or '') in INSPECTION_MODULE_TYPES


def _parse_form_data(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _parse_date(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()[:10]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _format_date(d) -> str:
    if not d:
        return '—'
    try:
        return d.strftime('%d %b %Y')
    except Exception:
        return str(d)


def _user_can_review(user) -> bool:
    if not user:
        return False
    if getattr(user, 'role', None) == 'admin':
        return True
    reviewer_designations = (
        'supervisor', 'manager', 'operations_manager',
        'business_development', 'procurement', 'general_manager',
    )
    d = (getattr(user, 'designation', None) or '').strip().lower()
    if d in reviewer_designations:
        return True
    if bool(getattr(user, 'access_business_development', False)):
        return True
    return False


def get_pending_summary(user):
    """Pending submissions awaiting this user's review."""
    from app.workflow.routes import get_user_pending_submissions

    can_review = _user_can_review(user)
    if not can_review:
        return {
            'can_review': False,
            'total': 0,
            'hr': 0,
            'inspection': 0,
            'other': 0,
            'items': [],
        }

    if getattr(user, 'role', None) == 'admin':
        subs = Submission.query.filter(
            Submission.workflow_status.notin_(list(TERMINAL_WORKFLOW)),
        ).order_by(Submission.created_at.desc()).all()
    else:
        subs = get_user_pending_submissions(user) or []

    hr = sum(1 for s in subs if _is_hr_module(s.module_type))
    inspection = sum(1 for s in subs if _is_inspection_module(s.module_type))
    other = len(subs) - hr - inspection

    items = []
    for s in subs[:8]:
        items.append({
            'submission_id': s.submission_id,
            'module_type': s.module_type,
            'workflow_status': s.workflow_status,
            'site_name': s.site_name or '',
            'updated_at': (s.updated_at or s.created_at).isoformat() if (s.updated_at or s.created_at) else None,
        })

    return {
        'can_review': True,
        'total': len(subs),
        'hr': hr,
        'inspection': inspection,
        'other': other,
        'items': items,
    }


def get_my_submissions_summary(user):
    """Summary of forms submitted by the current user."""
    uid = user.id
    q = Submission.query.filter(Submission.user_id == uid)
    all_rows = q.all()
    total = len(all_rows)
    drafts = sum(1 for s in all_rows if (s.status or '') == 'draft')
    in_progress = sum(
        1 for s in all_rows
        if (s.workflow_status or '') not in TERMINAL_WORKFLOW and (s.status or '') != 'draft'
    )
    completed = sum(1 for s in all_rows if (s.workflow_status or '') in ('completed',))
    rejected = sum(1 for s in all_rows if (s.workflow_status or '') == 'rejected')

    recent = (
        q.order_by(Submission.updated_at.desc(), Submission.created_at.desc())
        .limit(5)
        .all()
    )
    recent_items = []
    for s in recent:
        recent_items.append({
            'submission_id': s.submission_id,
            'module_type': s.module_type,
            'workflow_status': s.workflow_status,
            'status': s.status,
            'updated_at': (s.updated_at or s.created_at).isoformat() if (s.updated_at or s.created_at) else None,
        })

    return {
        'total': total,
        'drafts': drafts,
        'in_progress': in_progress,
        'completed': completed,
        'rejected': rejected,
        'recent': recent_items,
    }


LEAVE_TYPE_LABELS = {
    'annual': 'Annual Leave',
    'sick': 'Sick Leave',
    'ot_compensatory': 'OT Compensatory Off',
    'examination': 'Examination Leave',
    'study': 'Study Leave',
    'compassionate': 'Compassionate Leave',
    'unpaid': 'Unpaid Leave',
    'hajj': 'Hajj Leave',
    'other': 'Other',
}


def get_my_leave_history(user, limit=5, leave_type_filter=None):
    """Leave applications submitted by the current user."""
    q = Submission.query.filter(
        Submission.user_id == user.id,
        Submission.module_type.in_(HR_LEAVE_MODULE_TYPES),
        Submission.status != 'draft',
    )
    rows = q.all()

    entries = []
    for s in rows:
        fd = _parse_form_data(s.form_data)
        start = _parse_date(fd.get('first_day_of_leave') or fd.get('start_date'))
        end = _parse_date(fd.get('last_day_of_leave') or fd.get('end_date'))
        sort_date = end or start
        lt_raw = (fd.get('leave_type') or '').strip().lower()
        if leave_type_filter and lt_raw != leave_type_filter:
            continue
        lt_label = (
            fd.get('leave_type_display')
            or LEAVE_TYPE_LABELS.get(lt_raw, lt_raw.replace('_', ' ').title() if lt_raw else 'Leave')
        )
        entries.append({
            'submission_id': s.submission_id,
            'leave_type': lt_raw,
            'leave_type_label': lt_label,
            'start_date': _format_date(start),
            'end_date': _format_date(end),
            'sort_date': sort_date,
            'workflow_status': s.workflow_status or s.status or 'submitted',
            'total_days': fd.get('total_days_requested') or fd.get('total_days') or '',
        })

    entries.sort(key=lambda e: e['sort_date'] or datetime.min.date(), reverse=True)
    for e in entries:
        e.pop('sort_date', None)
    entries = entries[:limit]

    return {
        'count': len(entries),
        'entries': entries,
        'has_leave': len(entries) > 0,
    }


def _has_dochub_access(user):
    from app.docs.routes import _has_dochub_access as check
    return check(user)


def _score_document(doc, query: str) -> float:
    q = (query or '').lower().strip()
    if not q:
        return 0.0
    title = (doc.title or '').lower()
    category = (doc.category or '').lower()
    content = re.sub(r'<[^>]+>', ' ', (doc.content or '')).lower()
    score = 0.0
    if q in title:
        score += 10.0
    if q in category:
        score += 3.0
    tokens = [t for t in re.findall(r'[a-z0-9]+', q) if len(t) > 2]
    for tok in tokens:
        if tok in title:
            score += 4.0
        if tok in category:
            score += 1.5
        if tok in content:
            score += 0.5
    return score


def _profile_data_for(target_user) -> dict:
    """Build the profile data dict for a given user object."""
    from datetime import date

    start = getattr(target_user, 'employment_start_date', None)
    tenure_str = None
    if start:
        today = date.today()
        delta = today - start
        years = delta.days // 365
        months = (delta.days % 365) // 30
        if years and months:
            tenure_str = f"{years} year{'s' if years != 1 else ''} and {months} month{'s' if months != 1 else ''}"
        elif years:
            tenure_str = f"{years} year{'s' if years != 1 else ''}"
        else:
            tenure_str = f"{months} month{'s' if months != 1 else ''}"

    manager = None
    try:
        mgr = getattr(target_user, 'reporting_manager', None)
        if mgr:
            manager = mgr.full_name or mgr.username
    except Exception:
        pass

    return {
        'full_name': getattr(target_user, 'full_name', None) or getattr(target_user, 'username', ''),
        'email': getattr(target_user, 'email', None) or '',
        'job_designation': getattr(target_user, 'job_designation', None) or '',
        'designation': getattr(target_user, 'designation', None) or '',
        'employment_start_date': start.strftime('%d %b %Y') if start else None,
        'tenure': tenure_str,
        'annual_leave_days': getattr(target_user, 'annual_leave_days', None),
        'other_leave_days': getattr(target_user, 'other_leave_days', None),
        'manager': manager,
        'assigned_project': getattr(target_user, 'assigned_project', None) or '',
        'phone': getattr(target_user, 'phone', None) or '',
    }


def get_my_profile(user, person_name: str = None):
    """Return profile data. Admins can look up any user by name; others get their own."""
    from app.models import User as UserModel

    target = user

    if person_name and getattr(user, 'role', None) == 'admin':
        name_lower = person_name.strip().lower()
        match = UserModel.query.filter(
            UserModel.full_name.ilike(f'%{person_name}%')
        ).first()
        if not match:
            match = UserModel.query.filter(
                UserModel.username.ilike(f'%{person_name}%')
            ).first()
        if match:
            target = match

    data = _profile_data_for(target)
    data['is_self'] = (target.id == user.id)
    return data


def get_procurement_summary(user):
    """Materials and properties submitted by this user in the Procurement module."""
    uid = user.id
    PROC_MODULE_TYPES = ('procurement_material', 'procurement_property', 'catalog_material')
    rows = Submission.query.filter(
        Submission.user_id == uid,
        Submission.module_type.in_(PROC_MODULE_TYPES),
    ).order_by(Submission.created_at.desc()).all()

    materials = [r for r in rows if r.module_type in ('procurement_material', 'catalog_material')]
    properties = [r for r in rows if r.module_type == 'procurement_property']

    recent_materials = []
    for s in materials[:5]:
        fd = _parse_form_data(s.form_data)
        name = (
            fd.get('material_name') or fd.get('name') or fd.get('item_name')
            or s.site_name or s.submission_id
        )
        recent_materials.append({
            'name': name,
            'property': fd.get('property_name') or fd.get('property') or '',
            'status': s.workflow_status or s.status or 'submitted',
        })

    return {
        'materials_count': len(materials),
        'properties_count': len(properties),
        'total': len(rows),
        'recent_materials': recent_materials,
        'has_data': len(rows) > 0,
    }


def get_ticket_summary(user):
    """Tickets raised by or assigned to the current user."""
    if not getattr(user, 'access_ticketing', False) and getattr(user, 'role', None) != 'admin':
        return {
            'allowed': False,
            'open': 0, 'in_progress': 0, 'closed': 0,
            'total': 0, 'recent': [],
        }

    try:
        from app.models import Ticket
        from sqlalchemy import or_
        q = Ticket.query.filter(
            or_(Ticket.reporter_id == user.id, Ticket.assigned_to_id == user.id,
                Ticket.technician_id == user.id)
        )
        tickets = q.order_by(Ticket.created_at.desc()).all()
    except Exception:
        return {'allowed': True, 'open': 0, 'in_progress': 0, 'closed': 0, 'total': 0, 'recent': []}

    OPEN_STATUSES = {'open', 'pending_supervisor'}
    IN_PROGRESS_STATUSES = {'in_progress', 'pending_parts', 'pending_verification'}
    CLOSED_STATUSES = {'closed', 'closed_by_admin'}

    open_count = sum(1 for t in tickets if t.status in OPEN_STATUSES)
    in_progress_count = sum(1 for t in tickets if t.status in IN_PROGRESS_STATUSES)
    closed_count = sum(1 for t in tickets if t.status in CLOSED_STATUSES)

    recent = []
    for t in tickets[:5]:
        recent.append({
            'ticket_id': t.ticket_id,
            'title': t.title,
            'status': t.status,
            'category': t.category,
            'created_at': _format_date(t.created_at.date() if t.created_at else None),
        })

    return {
        'allowed': True,
        'open': open_count,
        'in_progress': in_progress_count,
        'closed': closed_count,
        'total': len(tickets),
        'recent': recent,
    }


def get_my_inspections_summary(user):
    """Inspection form submissions by the current user (HVAC, Civil, Cleaning)."""
    INSPECTION_TYPES = ('hvac_mep', 'civil', 'cleaning')
    rows = Submission.query.filter(
        Submission.user_id == user.id,
        Submission.module_type.in_(INSPECTION_TYPES),
    ).order_by(Submission.created_at.desc()).all()

    by_type = {'hvac_mep': 0, 'civil': 0, 'cleaning': 0}
    for r in rows:
        mt = r.module_type
        if mt in by_type:
            by_type[mt] += 1

    recent = []
    for s in rows[:5]:
        recent.append({
            'module_type': s.module_type,
            'site_name': s.site_name or '',
            'status': s.workflow_status or s.status or 'submitted',
            'created_at': _format_date(s.created_at.date() if s.created_at else None),
        })

    return {
        'total': len(rows),
        'hvac': by_type['hvac_mep'],
        'civil': by_type['civil'],
        'cleaning': by_type['cleaning'],
        'recent': recent,
        'has_data': len(rows) > 0,
    }


def search_documents(user, query: str, limit=5):
    """Search published DocHub documents the user can access."""
    if not _has_dochub_access(user):
        return {
            'allowed': False,
            'documents': [],
            'query': query,
        }

    docs = (
        DocHubDocument.query.filter(
            DocHubDocument.status == 'published',
            or_(DocHubDocument.inline_asset.is_(False), DocHubDocument.inline_asset.is_(None)),
        )
        .order_by(DocHubDocument.updated_at.desc())
        .all()
    )

    scored = []
    for doc in docs:
        sc = _score_document(doc, query)
        if sc > 0:
            scored.append((sc, doc))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored and query:
        for doc in docs:
            scored.append((0.1, doc))
        scored = scored[:limit]

    results = []
    for sc, doc in scored[:limit]:
        updated = doc.updated_at.strftime('%d %b %Y') if doc.updated_at else ''
        results.append({
            'id': doc.id,
            'title': doc.title,
            'category': doc.category or 'Internal',
            'updated_at': updated,
            'preview_url': f'/api/docs/{doc.id}/preview',
            'download_url': f'/api/docs/{doc.id}/download',
            'score': sc,
        })

    return {
        'allowed': True,
        'documents': results,
        'query': query,
    }
