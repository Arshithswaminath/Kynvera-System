"""Project-scoped Resource Management helpers (supervisors, team, vendors)."""

from __future__ import annotations

import logging

from app.models import (
    db, User, TicketProject, TicketProjectSupervisor, TicketProjectTeamMember,
    TicketVendor, TicketVendorTechnician, TicketProjectVendor,
    TicketSupervisorTeam,
)

logger = logging.getLogger(__name__)

SAMPLE_VENDORS = [
    {
        'name': 'Kynvera',
        'technicians': [
            {'code': 'TECH-001', 'name': 'Arshith Swaminath P', 'speciality': 'HVAC'},
            {'code': 'TECH-002', 'name': 'Fatima Noor', 'speciality': 'Electrical'},
        ],
    },
    {
        'name': 'NAFCO Technical Services',
        'technicians': [
            {'code': 'NAF-101', 'name': 'Omar Al Suwaidi', 'speciality': 'Plumbing'},
            {'code': 'NAF-102', 'name': 'Priya Menon', 'speciality': 'Civil'},
        ],
    },
]


def find_project_by_name(project_name: str) -> TicketProject | None:
    if not project_name:
        return None
    pn = project_name.strip()
    low = pn.lower()
    if low in ('', 'standalone location'):
        return None
    return (
        TicketProject.query.filter(
            db.func.lower(TicketProject.name) == low,
            TicketProject.is_active == True,  # noqa: E712
        )
        .first()
    )


def sync_primary_supervisor(project: TicketProject) -> None:
    """Keep TicketProject.supervisor_id as the sole roster member, else None."""
    links = (
        TicketProjectSupervisor.query.filter_by(project_id=project.id)
        .order_by(TicketProjectSupervisor.id)
        .all()
    )
    if len(links) == 1:
        project.supervisor_id = links[0].user_id
    else:
        project.supervisor_id = None


def seed_supervisor_roster_from_legacy() -> None:
    """Copy TicketProject.supervisor_id into the roster table when the roster is empty."""
    try:
        projects = TicketProject.query.filter(TicketProject.supervisor_id.isnot(None)).all()
        for p in projects:
            if TicketProjectSupervisor.query.filter_by(project_id=p.id).first():
                continue
            db.session.add(TicketProjectSupervisor(project_id=p.id, user_id=p.supervisor_id))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Supervisor roster seed skipped: %s', exc)


def seed_sample_vendors_if_empty() -> None:
    try:
        if TicketVendor.query.count() > 0:
            return
        for spec in SAMPLE_VENDORS:
            v = TicketVendor(name=spec['name'], is_active=True)
            db.session.add(v)
            db.session.flush()
            for t in spec.get('technicians') or []:
                db.session.add(TicketVendorTechnician(
                    vendor_id=v.id,
                    name=t['name'],
                    speciality=t.get('speciality'),
                    code=t.get('code'),
                ))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Sample vendor seed skipped: %s', exc)


def project_supervisor_user_ids(project: TicketProject) -> list[int]:
    return [
        r.user_id for r in
        TicketProjectSupervisor.query.filter_by(project_id=project.id).order_by(TicketProjectSupervisor.id).all()
    ]


def rostered_project_names_lower() -> set[str]:
    rows = (
        db.session.query(TicketProject.name)
        .join(TicketProjectSupervisor, TicketProjectSupervisor.project_id == TicketProject.id)
        .filter(TicketProject.is_active == True)  # noqa: E712
        .distinct()
        .all()
    )
    return {(n or '').strip().lower() for (n,) in rows if n}


def user_supervised_project_names_lower(user: User) -> set[str]:
    if user is None:
        return set()
    rows = (
        db.session.query(TicketProject.name)
        .join(TicketProjectSupervisor, TicketProjectSupervisor.project_id == TicketProject.id)
        .filter(
            TicketProjectSupervisor.user_id == user.id,
            TicketProject.is_active == True,  # noqa: E712
        )
        .all()
    )
    return {(n or '').strip().lower() for (n,) in rows if n}


def user_on_project_supervisor_roster(user: User, project_name: str) -> bool:
    tp = find_project_by_name(project_name or '')
    if not tp or user is None:
        return False
    return (
        TicketProjectSupervisor.query.filter_by(project_id=tp.id, user_id=user.id).first()
        is not None
    )


def resolve_single_project_supervisor_id(project_name: str) -> int | None:
    """Return the user id only when the project has exactly one active supervisor."""
    tp = find_project_by_name(project_name or '')
    if not tp:
        return None
    ids = []
    for uid in project_supervisor_user_ids(tp):
        u = db.session.get(User, uid)
        if u and u.is_active:
            ids.append(uid)
    if len(ids) == 1:
        return ids[0]
    return None


def project_team_workers(project_name: str) -> list[dict]:
    tp = find_project_by_name(project_name or '')
    if not tp:
        return []
    rows = []
    for link in TicketProjectTeamMember.query.filter_by(project_id=tp.id).all():
        tu = link.user
        if tu is None or not getattr(tu, 'is_active', True):
            continue
        speciality = (getattr(tu, 'job_designation', None) or '').strip() or 'Field technician'
        rows.append({
            'user_id': tu.id,
            'team_entry_id': link.id,
            'code': tu.username or f'USER-{tu.id}',
            'name': tu.full_name or tu.username,
            'speciality': speciality,
            'sidebar_row_id': f'uid-{tu.id}',
        })
    return rows


def vendors_for_project_name(project_name: str) -> list[dict]:
    tp = find_project_by_name(project_name or '')
    if not tp:
        return []
    out = []
    for link in TicketProjectVendor.query.filter_by(project_id=tp.id).all():
        v = link.vendor
        if v is None or not v.is_active:
            continue
        out.append(v.to_assign_dict())
    return out


def resources_payload(project: TicketProject) -> dict:
    supervisors = [
        link.to_dict()
        for link in TicketProjectSupervisor.query.filter_by(project_id=project.id)
        .order_by(TicketProjectSupervisor.id).all()
    ]
    team = [
        link.to_dict()
        for link in TicketProjectTeamMember.query.filter_by(project_id=project.id)
        .order_by(TicketProjectTeamMember.id).all()
    ]
    vendors = []
    for link in TicketProjectVendor.query.filter_by(project_id=project.id).order_by(TicketProjectVendor.id).all():
        v = link.vendor
        if v:
            d = v.to_dict()
            d['link_id'] = link.id
            vendors.append(d)
    return {
        'project_id': project.id,
        'project_name': project.name,
        'supervisors': supervisors,
        'team': team,
        'vendors': vendors,
    }


def eligible_team_users(project_id: int) -> list[User]:
    taken = {
        r[0] for r in
        db.session.query(TicketProjectTeamMember.user_id).filter_by(project_id=project_id).all()
    }
    q = User.query.filter(User.is_active == True)  # noqa: E712
    q = q.filter(db.or_(
        User.designation == 'technician',
        User.id.in_(
            db.session.query(TicketSupervisorTeam.technician_id)
            .filter(TicketSupervisorTeam.is_active == True)  # noqa: E712
        ),
    ))
    if taken:
        q = q.filter(~User.id.in_(taken))
    return q.order_by(User.full_name).all()
