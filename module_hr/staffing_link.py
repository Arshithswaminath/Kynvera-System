"""
Staffing link — assign Hiring candidates to Manpower vacancies (vacancy-first).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from flask import redirect, request
from flask_jwt_extended import jwt_required
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import joinedload

from app.models import (
    HIRING_PIPELINE_LABELS,
    HiringCandidate,
    ManpowerVacancy,
    User,
    db,
)
from common.error_responses import error_response, success_response
from common.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)

# Hiring pipeline → Manpower vacancy status
PIPELINE_TO_MANPOWER_STATUS = {
    'on_hold': 'on_hold',
    'interview_completed': 'interviewing',
    'gathering_documents': 'interviewing',
    'preparing_offer_letter': 'selected',
    'offer_letter_prepared': 'selected',
    'offer_letter_signed': 'selected',
    'md_signed_offer_received': 'selected',
    'gathering_documents_for_visa': 'selected',
    'visa_process_started': 'selected',
    'candidate_employee': 'joined',
}

_schema_ensured = False


def ensure_staffing_link_schema() -> None:
    """Add manpower_vacancies.hiring_candidate_id if missing (idempotent)."""
    global _schema_ensured
    if _schema_ensured:
        return
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        if 'manpower_vacancies' not in tables:
            _schema_ensured = True
            return
        cols = {c['name'] for c in inspector.get_columns('manpower_vacancies')}
        if 'hiring_candidate_id' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE manpower_vacancies '
                    'ADD COLUMN hiring_candidate_id INTEGER'
                ))
                # Unique index (SQLite / Postgres compatible enough for our apps)
                try:
                    conn.execute(text(
                        'CREATE UNIQUE INDEX IF NOT EXISTS '
                        'uq_manpower_vacancies_hiring_candidate_id '
                        'ON manpower_vacancies (hiring_candidate_id)'
                    ))
                except Exception:
                    # Some engines reject IF NOT EXISTS; try without
                    try:
                        conn.execute(text(
                            'CREATE UNIQUE INDEX '
                            'uq_manpower_vacancies_hiring_candidate_id '
                            'ON manpower_vacancies (hiring_candidate_id)'
                        ))
                    except Exception:
                        logger.exception(
                            'Could not create unique index on hiring_candidate_id'
                        )
            logger.info('Added hiring_candidate_id to manpower_vacancies')
        _schema_ensured = True
    except Exception:
        logger.exception('Could not ensure staffing link schema')
        try:
            db.session.rollback()
        except Exception:
            pass


def manpower_status_for_pipeline(pipeline_status: str) -> str:
    key = (pipeline_status or '').strip()
    return PIPELINE_TO_MANPOWER_STATUS.get(key, 'interviewing')


def sync_vacancy_from_candidate(candidate: HiringCandidate) -> Optional[ManpowerVacancy]:
    """Push name/contact/status from hiring candidate onto linked vacancy."""
    vac = candidate.assigned_vacancy
    if vac is None:
        return None
    vac.candidate_name = (candidate.full_name or '').strip() or vac.candidate_name
    if candidate.phone:
        vac.contact_number = (candidate.phone or '').strip() or None
    new_status = manpower_status_for_pipeline(candidate.normalized_pipeline_status())
    vac.status = new_status
    if new_status == 'joined' and not vac.date_joined:
        vac.date_joined = date.today()
    vac.updated_at = utc_now_naive()
    return vac


def _clear_vacancy_candidate_slot(vac: ManpowerVacancy, *, clear_identity: bool) -> None:
    """Detach hiring link from a vacancy. Optionally wipe name/contact so the cell looks empty."""
    vac.hiring_candidate_id = None
    if clear_identity:
        vac.candidate_name = None
        vac.contact_number = None
        vac.status = 'open'
        vac.date_joined = None
    vac.updated_at = utc_now_naive()


def assign_candidate_to_vacancy(
    candidate_id: int,
    vacancy_id: int,
    *,
    allow_reassign: bool = False,
) -> tuple[Optional[HiringCandidate], Optional[ManpowerVacancy], Optional[str]]:
    """
    Link candidate ↔ vacancy (1:1).
    Returns (candidate, vacancy, error_message).
    """
    ensure_staffing_link_schema()
    candidate = db.session.get(HiringCandidate, candidate_id)
    if not candidate:
        return None, None, 'Candidate not found'
    vac = (
        ManpowerVacancy.query
        .options(
            joinedload(ManpowerVacancy.trade),
            joinedload(ManpowerVacancy.project),
        )
        .filter_by(id=vacancy_id)
        .first()
    )
    if not vac:
        return None, None, 'Vacancy not found'

    other_vac = ManpowerVacancy.query.filter_by(hiring_candidate_id=candidate.id).first()
    if other_vac and other_vac.id != vac.id:
        if not allow_reassign:
            return None, None, (
                f'Candidate is already assigned to vacancy #{other_vac.id}. '
                'Unassign first.'
            )
        # Switch away: free the previous slot and empty its candidate/contact cells
        _clear_vacancy_candidate_slot(other_vac, clear_identity=True)

    if vac.hiring_candidate_id and vac.hiring_candidate_id != candidate.id:
        return None, None, (
            f'Vacancy #{vac.id} is already linked to another candidate. Unassign first.'
        )

    # Copy replacement onto candidate if empty
    if not (candidate.replacement_name or '').strip() and (vac.replacement_name or '').strip():
        candidate.replacement_name = vac.replacement_name
    if (
        not (candidate.replacement_employee_id or '').strip()
        and (vac.replacement_employee_id or '').strip()
    ):
        candidate.replacement_employee_id = vac.replacement_employee_id

    # Soft-fill role from trade when empty
    if not (candidate.role or '').strip() and vac.trade and vac.trade.name:
        candidate.role = vac.trade.name

    vac.hiring_candidate_id = candidate.id
    vac.candidate_name = (candidate.full_name or '').strip() or vac.candidate_name
    if candidate.phone:
        vac.contact_number = (candidate.phone or '').strip() or None
    vac.status = manpower_status_for_pipeline(candidate.normalized_pipeline_status())
    if vac.status == 'joined' and not vac.date_joined:
        vac.date_joined = date.today()
    vac.updated_at = utc_now_naive()
    candidate.updated_at = utc_now_naive()
    return candidate, vac, None


def unassign_vacancy(vacancy_id: int) -> tuple[Optional[ManpowerVacancy], Optional[str]]:
    ensure_staffing_link_schema()
    vac = db.session.get(ManpowerVacancy, vacancy_id)
    if not vac:
        return None, 'Vacancy not found'
    # Explicit Unlink keeps typed name/contact (board shows them as plain text)
    _clear_vacancy_candidate_slot(vac, clear_identity=False)
    return vac, None


def unassign_candidate(candidate_id: int) -> tuple[Optional[HiringCandidate], Optional[str]]:
    ensure_staffing_link_schema()
    candidate = db.session.get(HiringCandidate, candidate_id)
    if not candidate:
        return None, 'Candidate not found'
    vac = ManpowerVacancy.query.filter_by(hiring_candidate_id=candidate.id).first()
    if vac:
        _clear_vacancy_candidate_slot(vac, clear_identity=False)
    candidate.updated_at = utc_now_naive()
    return candidate, None


def _vacancy_picker_dict(v: ManpowerVacancy) -> dict[str, Any]:
    trade = v.trade
    project = v.project
    req = v.normalized_requirement_type()
    parts = [
        trade.name if trade else None,
        project.name if project else None,
    ]
    label = ' · '.join(p for p in parts if p)
    if req == 'replacement' and (v.replacement_name or '').strip():
        label = f'{label} (replacing {v.replacement_name.strip()})'
    return {
        'id': v.id,
        'trade_id': v.trade_id,
        'trade_name': trade.name if trade else None,
        'project_id': v.project_id,
        'project_name': project.name if project else None,
        'requirement_type': req,
        'replacement_name': v.replacement_name or '',
        'replacement_employee_id': v.replacement_employee_id or '',
        'status': v.normalized_status(),
        'candidate_name': v.candidate_name or '',
        'label': label or f'Vacancy #{v.id}',
    }


def open_vacancies_for_picker(
    *,
    q: str = '',
    trade_hint: str = '',
    include_linked: bool = False,
) -> list[dict[str, Any]]:
    ensure_staffing_link_schema()
    query = (
        ManpowerVacancy.query
        .options(
            joinedload(ManpowerVacancy.trade),
            joinedload(ManpowerVacancy.project),
        )
    )
    if not include_linked:
        query = query.filter(ManpowerVacancy.hiring_candidate_id.is_(None))
        # Prefer slots that are not already filled/joined
        query = query.filter(~ManpowerVacancy.status.in_(('joined', 'filled')))

    vacancies = query.all()
    qn = (q or '').strip().lower()
    hint = (trade_hint or '').strip().lower()

    scored: list[tuple[int, ManpowerVacancy]] = []
    for v in vacancies:
        trade_name = (v.trade.name if v.trade else '') or ''
        project_name = (v.project.name if v.project else '') or ''
        hay = ' '.join([
            trade_name,
            project_name,
            v.replacement_name or '',
            v.replacement_employee_id or '',
            v.candidate_name or '',
            str(v.id),
        ]).lower()
        if qn and qn not in hay:
            continue
        score = 0
        if hint and hint in trade_name.lower():
            score -= 10
        if hint and trade_name.lower() == hint:
            score -= 20
        scored.append((score, v))

    scored.sort(key=lambda item: (
        item[0],
        (item[1].trade.name if item[1].trade else '').lower(),
        (item[1].project.name if item[1].project else '').lower(),
        item[1].id or 0,
    ))
    return [_vacancy_picker_dict(v) for _, v in scored]


def _assigned_vacancy_summary(v: ManpowerVacancy) -> dict[str, Any]:
    trade = v.trade
    project = v.project
    trade_name = trade.name if trade else None
    project_name = project.name if project else None
    parts = [p for p in (trade_name, project_name) if p]
    return {
        'id': v.id,
        'trade_name': trade_name,
        'project_name': project_name,
        'person_label': ' · '.join(parts) if parts else f'Vacancy #{v.id}',
    }


def link_picker_candidates(*, q: str = '') -> list[dict[str, Any]]:
    """
    Hiring candidates for the Manpower Link picker.
    Includes available, already-assigned, and employed people with link_state metadata.
    """
    ensure_staffing_link_schema()
    linked_rows = (
        ManpowerVacancy.query
        .options(
            joinedload(ManpowerVacancy.trade),
            joinedload(ManpowerVacancy.project),
        )
        .filter(ManpowerVacancy.hiring_candidate_id.isnot(None))
        .all()
    )
    assigned_by_candidate: dict[int, ManpowerVacancy] = {
        v.hiring_candidate_id: v
        for v in linked_rows
        if v.hiring_candidate_id
    }

    query = HiringCandidate.query
    qn = (q or '').strip()
    if qn:
        like = f'%{qn}%'
        query = query.filter(or_(
            HiringCandidate.full_name.ilike(like),
            HiringCandidate.role.ilike(like),
            HiringCandidate.department.ilike(like),
            HiringCandidate.phone.ilike(like),
            HiringCandidate.email.ilike(like),
        ))
    rows = query.order_by(HiringCandidate.updated_at.desc()).limit(500).all()

    grouped: dict[str, list[dict[str, Any]]] = {
        'available': [],
        'assigned': [],
        'employee': [],
    }
    for c in rows:
        pipeline = c.normalized_pipeline_status()
        completed, total, _ = c.progress()
        vac = assigned_by_candidate.get(c.id)
        assigned_summary = _assigned_vacancy_summary(vac) if vac else None
        if pipeline == 'candidate_employee':
            link_state = 'employee'
        elif vac is not None:
            link_state = 'assigned'
        else:
            link_state = 'available'
        item = {
            'id': c.id,
            'full_name': c.full_name,
            'role': c.role or '',
            'department': c.department or '',
            'phone': c.phone or '',
            'pipeline_status': pipeline,
            'pipeline_label': HIRING_PIPELINE_LABELS.get(pipeline, pipeline),
            'progress_label': f'{completed}/{total}',
            'initials': c.initials(),
            'url': f'/hr/hiring/candidates/{c.id}',
            'link_state': link_state,
            'assigned_vacancy': assigned_summary,
            'is_selectable': True,
            'updated_at': (
                c.updated_at.isoformat() if getattr(c, 'updated_at', None) else None
            ),
        }
        grouped.setdefault(link_state, []).append(item)

    for key in ('available', 'assigned', 'employee'):
        grouped[key].sort(key=lambda item: item.get('updated_at') or '', reverse=True)
    return grouped['available'] + grouped['assigned'] + grouped['employee']


def unassigned_candidates(*, q: str = '') -> list[dict[str, Any]]:
    """Available-only candidates (Staffing Assignments page)."""
    ensure_staffing_link_schema()
    linked_ids = {
        row[0]
        for row in db.session.query(ManpowerVacancy.hiring_candidate_id)
        .filter(ManpowerVacancy.hiring_candidate_id.isnot(None))
        .all()
        if row[0]
    }
    query = HiringCandidate.query
    if linked_ids:
        query = query.filter(~HiringCandidate.id.in_(linked_ids))
    qn = (q or '').strip()
    if qn:
        like = f'%{qn}%'
        query = query.filter(or_(
            HiringCandidate.full_name.ilike(like),
            HiringCandidate.role.ilike(like),
            HiringCandidate.department.ilike(like),
            HiringCandidate.phone.ilike(like),
            HiringCandidate.email.ilike(like),
        ))
    rows = query.order_by(HiringCandidate.updated_at.desc()).limit(200).all()
    out = []
    for c in rows:
        pipeline = c.normalized_pipeline_status()
        completed, total, _ = c.progress()
        out.append({
            'id': c.id,
            'full_name': c.full_name,
            'role': c.role or '',
            'department': c.department or '',
            'phone': c.phone or '',
            'pipeline_status': pipeline,
            'pipeline_label': HIRING_PIPELINE_LABELS.get(pipeline, pipeline),
            'progress_label': f'{completed}/{total}',
            'initials': c.initials(),
            'url': f'/hr/hiring/candidates/{c.id}',
            'link_state': 'available',
            'assigned_vacancy': None,
            'is_selectable': True,
        })
    return out


def open_unlinked_vacancies(*, q: str = '') -> list[dict[str, Any]]:
    return open_vacancies_for_picker(q=q, include_linked=False)


def linked_assignment_pairs() -> list[dict[str, Any]]:
    ensure_staffing_link_schema()
    vacancies = (
        ManpowerVacancy.query
        .options(
            joinedload(ManpowerVacancy.trade),
            joinedload(ManpowerVacancy.project),
            joinedload(ManpowerVacancy.hiring_candidate),
        )
        .filter(ManpowerVacancy.hiring_candidate_id.isnot(None))
        .order_by(ManpowerVacancy.updated_at.desc())
        .all()
    )
    pairs = []
    for v in vacancies:
        cand = v.hiring_candidate
        if not cand:
            continue
        pipeline = cand.normalized_pipeline_status()
        completed, total, _ = cand.progress()
        vac_d = _vacancy_picker_dict(v)
        pairs.append({
            'vacancy': vac_d,
            'candidate': {
                'id': cand.id,
                'full_name': cand.full_name,
                'role': cand.role or '',
                'phone': cand.phone or '',
                'pipeline_status': pipeline,
                'pipeline_label': HIRING_PIPELINE_LABELS.get(pipeline, pipeline),
                'progress_label': f'{completed}/{total}',
                'url': f'/hr/hiring/candidates/{cand.id}',
            },
        })
    return pairs


def _role_is_admin(user: Optional[User]) -> bool:
    return bool(user and (user.role or '').lower() in ('admin', 'super_admin'))


def _user_desig_lc(user: Optional[User]) -> str:
    return (getattr(user, 'designation', None) or '').strip().lower()


def user_can_manage_staffing(user: Optional[User]) -> bool:
    if not user:
        return False
    if _role_is_admin(user):
        return True
    if getattr(user, 'access_hr', False):
        return True
    if _user_desig_lc(user) == 'hr_manager':
        return True
    return False


def _get_current_user():
    from flask_jwt_extended import get_jwt_identity
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return db.session.get(User, int(user_id))


def _require_staffing_user():
    user = _get_current_user()
    if not user:
        return None, error_response('Authentication required', status_code=401, error_code='UNAUTHORIZED')
    if not user_can_manage_staffing(user):
        return None, error_response('Access denied', status_code=403, error_code='FORBIDDEN')
    ensure_staffing_link_schema()
    return user, None


def register_staffing_link_routes(hr_bp):
    """Register Staffing Assignments page + assign APIs."""

    @hr_bp.route('/staffing-assignments')
    @jwt_required()
    def staffing_assignments_page():
        # Staffing Assignments UI is hidden; linking lives in Manpower / Hiring.
        return redirect('/hr/manpower-tracker')

    @hr_bp.route('/api/staffing/open-vacancies', methods=['GET'])
    @jwt_required()
    def api_staffing_open_vacancies():
        user, err = _require_staffing_user()
        if err:
            return err
        q = (request.args.get('q') or '').strip()
        trade = (request.args.get('trade') or request.args.get('role') or '').strip()
        items = open_vacancies_for_picker(q=q, trade_hint=trade)
        return success_response({'vacancies': items, 'count': len(items)})

    @hr_bp.route('/api/staffing/unassigned-candidates', methods=['GET'])
    @jwt_required()
    def api_staffing_unassigned_candidates():
        user, err = _require_staffing_user()
        if err:
            return err
        q = (request.args.get('q') or '').strip()
        items = link_picker_candidates(q=q)
        return success_response({'candidates': items, 'count': len(items)})

    @hr_bp.route('/api/staffing/assignments', methods=['GET'])
    @jwt_required()
    def api_staffing_assignments():
        user, err = _require_staffing_user()
        if err:
            return err
        q = (request.args.get('q') or '').strip()
        return success_response({
            'open_vacancies': open_unlinked_vacancies(q=q),
            'unassigned_candidates': unassigned_candidates(q=q),
            'linked': linked_assignment_pairs(),
        })

    @hr_bp.route('/api/staffing/assign', methods=['POST'])
    @jwt_required()
    def api_staffing_assign():
        user, err = _require_staffing_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        try:
            candidate_id = int(data.get('candidate_id'))
            vacancy_id = int(data.get('vacancy_id'))
        except (TypeError, ValueError):
            return error_response(
                'candidate_id and vacancy_id are required',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        allow_reassign = bool(data.get('allow_reassign'))
        candidate, vac, msg = assign_candidate_to_vacancy(
            candidate_id, vacancy_id, allow_reassign=allow_reassign,
        )
        if msg:
            code = 404 if 'not found' in msg.lower() else 409
            return error_response(msg, status_code=code, error_code='ASSIGN_ERROR')
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Staffing assign commit failed')
            return error_response('Could not assign', status_code=500)
        db.session.refresh(candidate)
        db.session.refresh(vac)
        return success_response({
            'candidate': candidate.to_dict(include_documents=False),
            'vacancy': vac.to_dict(),
        }, message='Candidate assigned to vacancy')

    @hr_bp.route('/api/staffing/unassign', methods=['POST'])
    @jwt_required()
    def api_staffing_unassign():
        user, err = _require_staffing_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        candidate_id = data.get('candidate_id')
        vacancy_id = data.get('vacancy_id')
        if vacancy_id is not None and vacancy_id != '':
            try:
                vac, msg = unassign_vacancy(int(vacancy_id))
            except (TypeError, ValueError):
                return error_response('Invalid vacancy_id', status_code=400)
            if msg:
                return error_response(msg, status_code=404, error_code='NOT_FOUND')
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                return error_response('Could not unassign', status_code=500)
            return success_response({'vacancy': vac.to_dict()}, message='Vacancy unassigned')

        if candidate_id is not None and candidate_id != '':
            try:
                candidate, msg = unassign_candidate(int(candidate_id))
            except (TypeError, ValueError):
                return error_response('Invalid candidate_id', status_code=400)
            if msg:
                return error_response(msg, status_code=404, error_code='NOT_FOUND')
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                return error_response('Could not unassign', status_code=500)
            return success_response({
                'candidate': candidate.to_dict(include_documents=False),
            }, message='Candidate unassigned')

        return error_response(
            'Provide candidate_id or vacancy_id',
            status_code=400,
            error_code='VALIDATION_ERROR',
        )
