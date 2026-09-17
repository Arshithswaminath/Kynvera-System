"""
Employee from hiring — promote Candidate employed people onto the staff roster.
"""
from __future__ import annotations

import logging

from flask import render_template, request
from flask_jwt_extended import jwt_required
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import joinedload

from app.models import HIRING_PIPELINE_STEPS, HiringCandidate, LeaveEmployee, db
from common.datetime_utils import naive_utc_isoformat_z, utc_now_naive
from common.error_responses import error_response, success_response

logger = logging.getLogger(__name__)

_schema_ensured = False

_MISSING_PLACEHOLDERS = frozenset({'', '—', '-', '–', 'n/a', 'na', 'none'})


def ensure_employee_from_hiring_schema() -> None:
    """Add hiring_candidates columns used by Hiring Docs + Employee from hiring."""
    global _schema_ensured
    if _schema_ensured:
        return
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        if 'hiring_candidates' not in tables:
            _schema_ensured = True
            return
        cols = {c['name'] for c in inspector.get_columns('hiring_candidates')}
        if 'hr_ref' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE hiring_candidates ADD COLUMN hr_ref VARCHAR(80)'
                ))
            logger.info('Added hr_ref to hiring_candidates')
            cols.add('hr_ref')
        if 'leave_employee_id' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE hiring_candidates '
                    'ADD COLUMN leave_employee_id INTEGER'
                ))
                try:
                    conn.execute(text(
                        'CREATE UNIQUE INDEX IF NOT EXISTS '
                        'ix_hiring_candidates_leave_employee_id '
                        'ON hiring_candidates (leave_employee_id)'
                    ))
                except Exception:
                    try:
                        conn.execute(text(
                            'CREATE UNIQUE INDEX '
                            'ix_hiring_candidates_leave_employee_id '
                            'ON hiring_candidates (leave_employee_id)'
                        ))
                    except Exception:
                        logger.exception(
                            'Could not create unique index on leave_employee_id'
                        )
            logger.info('Added leave_employee_id to hiring_candidates')
            cols.add('leave_employee_id')
        if 'employee_list_dismissed_at' not in cols:
            # DATETIME is invalid on Postgres (live) and left this column missing,
            # which 500s Hiring Docs list + Excel import preview.
            dialect = db.engine.dialect.name
            ts_sql = 'TIMESTAMP' if dialect == 'postgresql' else 'DATETIME'
            with db.engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE hiring_candidates '
                    f'ADD COLUMN employee_list_dismissed_at {ts_sql}'
                ))
            logger.info('Added employee_list_dismissed_at to hiring_candidates')
        _schema_ensured = True
    except Exception:
        logger.exception('Could not ensure employee-from-hiring schema')
        try:
            db.session.rollback()
        except Exception:
            pass


def field_is_missing(value) -> bool:
    text = str(value or '').strip()
    return not text or text.lower() in _MISSING_PLACEHOLDERS


def required_reasons(*, emp_id=None, full_name=None, pending_hire=False) -> list[str]:
    reasons: list[str] = []
    if pending_hire or field_is_missing(emp_id):
        reasons.append('emp_id')
    if field_is_missing(full_name):
        reasons.append('full_name')
    return reasons


def _normalize_name(name) -> str:
    return ' '.join(str(name or '').strip().lower().split())


def _name_tokens(name) -> set[str]:
    return {part for part in _normalize_name(name).split() if part}


_NAME_TOKEN_FOLDS = {
    'mohamed': 'mohammad',
    'mohammed': 'mohammad',
    'mohamad': 'mohammad',
    'muhammad': 'mohammad',
    'muhamed': 'mohammad',
    'muhammed': 'mohammad',
    'mohd': 'mohammad',
}


def _fold_name_token(token: str) -> str:
    return _NAME_TOKEN_FOLDS.get(token, token)


def _folded_name_tokens(name) -> set[str]:
    return {_fold_name_token(part) for part in _name_tokens(name)}


def _name_is_richer(source, target) -> bool:
    source_name = _normalize_name(source)
    target_name = _normalize_name(target)
    if not source_name or source_name == target_name:
        return False
    source_parts = source_name.split()
    target_parts = target_name.split()
    if len(source_parts) != len(target_parts):
        return len(source_parts) > len(target_parts)
    return len(source_name) > len(target_name)


def _names_are_related(left, right) -> bool:
    left_tokens = _folded_name_tokens(left)
    right_tokens = _folded_name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    smaller, larger = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    if smaller <= larger:
        if len(smaller) < 2 and len(next(iter(smaller))) < 5:
            return False
        return True
    return len(left_tokens & right_tokens) >= 2


def _active_roster() -> list[LeaveEmployee]:
    return LeaveEmployee.query.filter_by(active=True).all()


def _find_active_by_emp_id(emp_id) -> LeaveEmployee | None:
    emp_id = str(emp_id or '').strip()
    if not emp_id:
        return None
    return LeaveEmployee.query.filter(
        db.func.lower(LeaveEmployee.emp_id) == emp_id.lower(),
        LeaveEmployee.active.is_(True),
    ).first()


def _pick_unique_employee(hits, candidate: HiringCandidate):
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    role = _normalize_name(candidate.role)
    if not role:
        return None
    role_hits = [
        emp for emp in hits
        if _normalize_name(emp.designation) == role
    ]
    if len(role_hits) == 1:
        return role_hits[0]
    return None


def _match_roster_employee(candidate: HiringCandidate, roster=None):
    hire_name = _normalize_name(candidate.full_name)
    if not hire_name:
        return None
    employees = list(roster) if roster is not None else _active_roster()
    exact = [emp for emp in employees if _normalize_name(emp.full_name) == hire_name]
    picked = _pick_unique_employee(exact, candidate)
    if picked is not None:
        return picked
    if len(exact) > 1:
        return exact[0]

    related = [
        emp for emp in employees
        if _names_are_related(hire_name, emp.full_name)
    ]
    return _pick_unique_employee(related, candidate)


def _matched_employee_payload(matched, hire_name) -> dict | None:
    if matched is None:
        return None
    related = _names_are_related(hire_name, matched.full_name)
    return {
        'id': matched.id,
        'emp_id': matched.emp_id,
        'full_name': matched.full_name,
        'company': matched.company or '',
        'name_can_update': bool(related and _name_is_richer(hire_name, matched.full_name)),
    }


def hiring_linked_employee_ids(emp_ids) -> set[int]:
    ids = [int(i) for i in (emp_ids or []) if i]
    if not ids:
        return set()
    rows = (
        HiringCandidate.query
        .filter(HiringCandidate.leave_employee_id.in_(ids))
        .with_entities(HiringCandidate.leave_employee_id)
        .all()
    )
    return {row[0] for row in rows if row[0]}


def _linked_employee_active(candidate: HiringCandidate) -> bool:
    emp = getattr(candidate, 'leave_employee', None)
    return bool(candidate.leave_employee_id and emp and emp.active)


def revoke_employee_conversion(candidate: HiringCandidate) -> None:
    """Undo a hiring→employee conversion (e.g. a mistaken duplicate add).

    Unlinks the Employee List row and reopens the candidate's hiring file at
    the stage just before "Candidate employed", so a corrected Emp ID can be
    issued later without losing the document progress already recorded.
    """
    candidate.leave_employee_id = None
    candidate.employee_list_dismissed_at = None
    if candidate.normalized_pipeline_status() == 'candidate_employee':
        idx = HIRING_PIPELINE_STEPS.index('candidate_employee')
        candidate.pipeline_status = HIRING_PIPELINE_STEPS[idx - 1]
    candidate.updated_at = utc_now_naive()
    try:
        from module_hr.staffing_link import sync_vacancy_from_candidate
        sync_vacancy_from_candidate(candidate)
    except Exception:
        logger.exception('Could not sync vacancy after revoking employee conversion')


def pending_from_hiring_query():
    ensure_employee_from_hiring_schema()
    return (
        HiringCandidate.query
        .outerjoin(LeaveEmployee, HiringCandidate.leave_employee_id == LeaveEmployee.id)
        .options(joinedload(HiringCandidate.leave_employee))
        .filter(HiringCandidate.pipeline_status == 'candidate_employee')
        .filter(HiringCandidate.employee_list_dismissed_at.is_(None))
        .filter(or_(
            HiringCandidate.leave_employee_id.is_(None),
            LeaveEmployee.id.is_(None),
            LeaveEmployee.active.is_(False),
        ))
        .order_by(HiringCandidate.updated_at.desc(), HiringCandidate.full_name.asc())
    )


def pending_from_hiring_count() -> int:
    try:
        return pending_from_hiring_query().count()
    except Exception:
        logger.exception('Could not count pending employees from hiring')
        try:
            db.session.rollback()
        except Exception:
            pass
        return 0


def pending_candidate_to_dict(candidate: HiringCandidate, roster_index=None) -> dict:
    name = (candidate.full_name or '').strip()
    role = (candidate.role or '').strip()
    reasons = required_reasons(emp_id='', full_name=name, pending_hire=True)
    company = ''
    vac = getattr(candidate, 'assigned_vacancy', None)
    if vac is not None and getattr(vac, 'project', None) is not None:
        company = (vac.project.name or '').strip()
    matched = None
    if roster_index is not None:
        matched = _match_roster_employee(candidate, roster_index)
    matched_payload = _matched_employee_payload(matched, name)
    return {
        'source': 'hiring',
        'hiring_candidate_id': candidate.id,
        'full_name': name,
        'designation': role,
        'role': role,
        'emp_id': (matched.emp_id if matched else ''),
        'company': company or ((matched.company if matched else '') or 'Kynvera'),
        'department': (candidate.department or '').strip(),
        'required_reasons': reasons,
        'on_employee_list': False,
        'already_on_list': bool(matched),
        'matched_employee': matched_payload,
        'updated_at': naive_utc_isoformat_z(candidate.updated_at) if candidate.updated_at else None,
    }


def _parse_entitlement(raw):
    if raw is None or raw == '':
        return None, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, error_response('Invalid annual_entitlement', status_code=400)


def register_employee_from_hiring_routes(hr_bp):
    """Attach Employee from hiring routes to the HR blueprint."""
    from module_hr.leave_tracker import (
        _get_current_user,
        _require_leave_user,
        user_can_manage_leave_tracker,
        upsert_leave_employee,
    )

    hr_bp.add_app_template_global(
        pending_from_hiring_count,
        name='employee_from_hiring_pending_count',
    )

    @hr_bp.route('/employee-from-hiring')
    @jwt_required()
    def employee_from_hiring_dashboard():
        user = _get_current_user()
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        if not user_can_manage_leave_tracker(user):
            return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
        ensure_employee_from_hiring_schema()
        return render_template(
            'hr_employee_from_hiring.html',
            user=user,
            hiring_active='employee_from_hiring',
        )

    @hr_bp.route('/api/employee-from-hiring', methods=['GET'])
    @jwt_required()
    def api_employee_from_hiring_list():
        user, err = _require_leave_user()
        if err:
            return err
        ensure_employee_from_hiring_schema()
        rows = pending_from_hiring_query().all()
        roster = _active_roster()
        pending = [pending_candidate_to_dict(c, roster) for c in rows]
        return success_response({
            'pending': pending,
            'count': len(pending),
        })

    @hr_bp.route('/api/employee-from-hiring/count', methods=['GET'])
    @jwt_required()
    def api_employee_from_hiring_count():
        user, err = _require_leave_user()
        if err:
            return err
        return success_response({'count': pending_from_hiring_count()})

    @hr_bp.route('/api/employee-from-hiring/<int:candidate_id>/promote', methods=['POST'])
    @jwt_required()
    def api_employee_from_hiring_promote(candidate_id):
        user, err = _require_leave_user()
        if err:
            return err
        ensure_employee_from_hiring_schema()
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')
        if candidate.normalized_pipeline_status() != 'candidate_employee':
            return error_response(
                'Only candidate-employed people can be moved to the Employee List',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        if _linked_employee_active(candidate):
            return error_response(
                'This person is already on the Employee List',
                status_code=409,
                error_code='CONFLICT',
            )

        data = request.get_json(silent=True) or {}
        emp_id = str(data.get('emp_id') or '').strip()
        if 'full_name' in data:
            full_name = str(data.get('full_name') or '').strip()
        else:
            full_name = str(candidate.full_name or '').strip()
        if not emp_id or not full_name:
            return error_response(
                'Emp ID and full name are required to move someone to the Employee List',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        existing = _find_active_by_emp_id(emp_id)
        if existing:
            payload = _matched_employee_payload(existing, full_name)
            return error_response(
                'This Emp ID is already on the Employee List. Merge into one record?',
                status_code=409,
                error_code='NEEDS_MERGE',
                details={
                    'needs_merge': True,
                    'matched_employee': payload,
                },
            )
        entitlement, ent_err = _parse_entitlement(data.get('annual_entitlement'))
        if ent_err:
            return ent_err
        designation = str(
            data.get('designation') or data.get('role') or candidate.role or ''
        ).strip()
        result, upsert_err = upsert_leave_employee(
            emp_id=emp_id,
            full_name=full_name,
            designation=designation,
            company=data.get('company'),
            annual_entitlement=entitlement,
        )
        if upsert_err:
            return upsert_err
        emp = result['employee']
        candidate.leave_employee_id = emp.id
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({
            'employee': emp.to_dict(),
            'candidate': candidate.to_dict(include_documents=False),
            'restored': result['restored'],
        }, message='Added to Employee List')

    @hr_bp.route('/api/employee-from-hiring/<int:candidate_id>/dismiss', methods=['POST'])
    @jwt_required()
    def api_employee_from_hiring_dismiss(candidate_id):
        user, err = _require_leave_user()
        if err:
            return err
        ensure_employee_from_hiring_schema()
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')
        if candidate.normalized_pipeline_status() != 'candidate_employee':
            return error_response(
                'Only candidate-employed people can be removed from this queue',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        if candidate.employee_list_dismissed_at:
            return error_response(
                'This person is already removed from the hiring queue',
                status_code=409,
                error_code='CONFLICT',
            )
        data = request.get_json(silent=True) or {}
        emp_id = str(data.get('emp_id') or '').strip()
        matched = _find_active_by_emp_id(emp_id) if emp_id else None
        if not matched:
            matched = _match_roster_employee(candidate)
        if not matched:
            return error_response(
                'This person was not found on the Employee List',
                status_code=409,
                error_code='CONFLICT',
            )
        hire_name = str(candidate.full_name or '').strip()
        hire_role = str(candidate.role or '').strip()
        name_updated = False
        if (
            _names_are_related(hire_name, matched.full_name)
            and _name_is_richer(hire_name, matched.full_name)
        ):
            matched.full_name = hire_name
            name_updated = True
        if hire_role and field_is_missing(matched.designation):
            matched.designation = hire_role
        taken = (
            HiringCandidate.query
            .filter(HiringCandidate.leave_employee_id == matched.id)
            .filter(HiringCandidate.id != candidate.id)
            .first()
        )
        if not taken:
            candidate.leave_employee_id = matched.id
        matched.updated_at = utc_now_naive()
        candidate.employee_list_dismissed_at = utc_now_naive()
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        emp_payload = matched.to_dict()
        emp_payload['from_hiring'] = True
        return success_response({
            'candidate_id': candidate.id,
            'name_updated': name_updated,
            'employee': emp_payload,
            'matched_employee': {
                'id': matched.id,
                'emp_id': matched.emp_id,
                'full_name': matched.full_name,
            },
        }, message='Merged with Employee List')
