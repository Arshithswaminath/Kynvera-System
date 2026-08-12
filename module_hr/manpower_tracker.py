"""
Manpower Tracker — project vacancy fill board.
Routes registered on hr_bp via register_manpower_tracker_routes().
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from io import BytesIO
from typing import Optional

from flask import render_template, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models import (
    MANPOWER_IN_PROGRESS_STATUSES,
    MANPOWER_REQUIREMENT_TYPE_DEFAULT,
    MANPOWER_REQUIREMENT_TYPE_LABELS,
    MANPOWER_REQUIREMENT_TYPES,
    MANPOWER_STATUS_DEFAULT,
    MANPOWER_STATUS_LABELS,
    MANPOWER_STATUSES,
    ManpowerProject,
    ManpowerTrade,
    ManpowerVacancy,
    User,
    db,
)
from common.datetime_utils import utc_now_naive
from common.error_responses import error_response, success_response
from module_hr.staffing_link import ensure_staffing_link_schema

logger = logging.getLogger(__name__)


def _role_is_admin(user: Optional[User]) -> bool:
    return bool(user and getattr(user, 'role', None) == 'admin')


def _user_desig_lc(user: Optional[User]) -> str:
    return (getattr(user, 'designation', None) or '').strip().lower()


def user_can_manage_manpower(user: Optional[User]) -> bool:
    """Same access gate as Hiring Document Tracker / Leave Tracker."""
    if not user:
        return False
    if _role_is_admin(user):
        return True
    if getattr(user, 'access_hr', False):
        return True
    return _user_desig_lc(user) == 'hr_manager'


def _get_current_user():
    from module_hr.routes import get_current_user
    return get_current_user()


def _require_manpower_user():
    user = _get_current_user()
    if not user:
        return None, error_response('User not found', status_code=404, error_code='NOT_FOUND')
    if not user_can_manage_manpower(user):
        return None, error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    ensure_staffing_link_schema()
    return user, None


def _parse_date(raw) -> Optional[date]:
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return False  # sentinel invalid


def _normalize_status(raw) -> Optional[str]:
    if raw is None or raw == '':
        return None
    s = str(raw).strip().lower().replace(' ', '_')
    aliases = {
        'open': 'open',
        'interviewing': 'interviewing',
        'selected': 'selected',
        'filled': 'filled',
        'joined': 'joined',
        'on_hold': 'on_hold',
        'onhold': 'on_hold',
    }
    if s in aliases:
        return aliases[s]
    for key, label in MANPOWER_STATUS_LABELS.items():
        if label.lower() == str(raw).strip().lower():
            return key
    return False  # invalid


def _normalize_req_type(raw) -> Optional[str]:
    if raw is None or raw == '':
        return None
    s = str(raw).strip().lower()
    if s in MANPOWER_REQUIREMENT_TYPES:
        return s
    for key, label in MANPOWER_REQUIREMENT_TYPE_LABELS.items():
        if label.lower() == s:
            return key
    if 'replac' in s:
        return 'replacement'
    if s == 'new':
        return 'new'
    return False


def _person_counts(vacancies: list[ManpowerVacancy]) -> dict[tuple[int, int], list[ManpowerVacancy]]:
    """Group vacancies by (trade_id, project_id) preserving order."""
    groups: dict[tuple[int, int], list[ManpowerVacancy]] = {}
    for v in vacancies:
        key = (v.trade_id, v.project_id)
        groups.setdefault(key, []).append(v)
    return groups


def _annotate_person_labels(vacancies: list[ManpowerVacancy]) -> list[dict]:
    """Attach N of M within each trade×project group (by sort_order then id)."""
    groups = _person_counts(vacancies)
    # Sort each group
    for key in groups:
        groups[key] = sorted(
            groups[key],
            key=lambda x: (x.sort_order or 0, x.id or 0),
        )
    # Build index maps
    index_map: dict[int, tuple[int, int]] = {}
    for key, items in groups.items():
        total = len(items)
        for i, v in enumerate(items, start=1):
            index_map[v.id] = (i, total)

    out = []
    for v in vacancies:
        of, total = index_map.get(v.id, (1, 1))
        out.append(v.to_dict(person_of=of, person_total=total))
    return out


def _vacancy_sort_key(v: ManpowerVacancy):
    trade = v.trade
    project = v.project
    return (
        (trade.sort_order if trade else 0),
        (trade.name or '') if trade else '',
        (project.sort_order if project else 0),
        (project.name or '') if project else '',
        v.sort_order or 0,
        v.id or 0,
    )


def _vacancy_is_empty(v: ManpowerVacancy) -> bool:
    if v.hiring_candidate_id:
        return False
    return not any([
        (v.candidate_name or '').strip(),
        (v.contact_number or '').strip(),
        (v.replacement_name or '').strip(),
        (v.replacement_employee_id or '').strip(),
        (v.remarks or '').strip(),
        v.date_joined,
    ])


def _vacancy_removal_rank(v: ManpowerVacancy) -> tuple:
    """Lower rank is safer to auto-delete when shrinking a matrix cell."""
    status = v.normalized_status()
    status_rank = {
        'open': 0,
        'on_hold': 1,
        'interviewing': 2,
        'selected': 3,
        'filled': 4,
        'joined': 5,
    }.get(status, 3)
    empty_rank = 0 if _vacancy_is_empty(v) else 1
    return (empty_rank, status_rank, -(v.id or 0))


def _set_matrix_cell_count(
    *,
    trade: ManpowerTrade,
    project: ManpowerProject,
    target: int,
    user: Optional[User],
) -> dict:
    """Create/delete vacancies so trade×project headcount matches target."""
    existing = (
        ManpowerVacancy.query
        .filter_by(trade_id=trade.id, project_id=project.id)
        .all()
    )
    current = len(existing)
    locked_n = sum(
        1 for v in existing if v.normalized_status() in ('joined', 'filled')
    )
    if target < locked_n:
        raise ValueError(
            f'Cannot set below {locked_n} filled/joined '
            f'{"vacancy" if locked_n == 1 else "vacancies"} for this trade × project. '
            'Change those rows in the main table first.'
        )

    created = 0
    deleted = 0

    if target > current:
        max_sort = (
            db.session.query(db.func.coalesce(db.func.max(ManpowerVacancy.sort_order), 0))
            .filter_by(trade_id=trade.id, project_id=project.id)
            .scalar()
        ) or 0
        for i in range(target - current):
            db.session.add(ManpowerVacancy(
                trade_id=trade.id,
                project_id=project.id,
                requirement_type=MANPOWER_REQUIREMENT_TYPE_DEFAULT,
                status=MANPOWER_STATUS_DEFAULT,
                sort_order=max_sort + i + 1,
                created_by=user.id if user else None,
            ))
            created += 1
    elif target < current:
        removable = sorted(existing, key=_vacancy_removal_rank)
        to_remove = removable[: current - target]
        if any(v.normalized_status() in ('joined', 'filled') for v in to_remove):
            raise ValueError(
                'Cannot remove filled/joined vacancies from the matrix. '
                'Update those rows in the main table first.'
            )
        for v in to_remove:
            db.session.delete(v)
            deleted += 1

    db.session.commit()
    return {
        'trade_id': trade.id,
        'project_id': project.id,
        'count': target,
        'previous_count': current,
        'created': created,
        'deleted': deleted,
        'joined': sum(1 for v in existing if v.normalized_status() == 'joined'),
    }


def _build_summary(vacancies: list[ManpowerVacancy], trades: list[ManpowerTrade], projects: list[ManpowerProject]) -> dict:
    total = len(vacancies)
    joined = sum(1 for v in vacancies if v.normalized_status() == 'joined')
    open_n = sum(1 for v in vacancies if v.normalized_status() == 'open')
    in_progress = sum(
        1 for v in vacancies if v.normalized_status() in MANPOWER_IN_PROGRESS_STATUSES
    )

    # Matrix: trade rows × project cols → count
    matrix_cells: dict[str, int] = {}  # f"{trade_id}:{project_id}"
    trade_totals: dict[int, dict] = {}
    project_progress: dict[int, dict] = {}

    for p in projects:
        project_progress[p.id] = {
            'project_id': p.id,
            'project_name': p.name,
            'required': 0,
            'joined': 0,
            'in_progress': 0,
            'open': 0,
        }

    for t in trades:
        trade_totals[t.id] = {
            'trade_id': t.id,
            'trade_name': t.name,
            'required': 0,
            'joined': 0,
            'open': 0,
        }

    for v in vacancies:
        tid, pid = v.trade_id, v.project_id
        key = f'{tid}:{pid}'
        matrix_cells[key] = matrix_cells.get(key, 0) + 1
        status = v.normalized_status()

        if tid in trade_totals:
            trade_totals[tid]['required'] += 1
            if status == 'joined':
                trade_totals[tid]['joined'] += 1
            if status == 'open':
                trade_totals[tid]['open'] += 1

        if pid in project_progress:
            project_progress[pid]['required'] += 1
            if status == 'joined':
                project_progress[pid]['joined'] += 1
            elif status == 'open':
                project_progress[pid]['open'] += 1
            elif status in MANPOWER_IN_PROGRESS_STATUSES:
                project_progress[pid]['in_progress'] += 1

    # Active trades/projects stay editable in the matrix; keep inactive ones that still have rows
    trade_ids_with_data = {v.trade_id for v in vacancies}
    project_ids_with_data = {v.project_id for v in vacancies}
    matrix_trades = [
        {'id': t.id, 'name': t.name}
        for t in trades
        if getattr(t, 'active', True) or t.id in trade_ids_with_data
    ]
    matrix_projects = [
        {'id': p.id, 'name': p.name}
        for p in projects
        if getattr(p, 'active', True) or p.id in project_ids_with_data
    ]

    matrix = []
    for t in matrix_trades:
        totals = trade_totals.get(t['id']) or {
            'required': 0, 'joined': 0, 'open': 0,
        }
        row = {
            'trade_id': t['id'],
            'trade_name': t['name'],
            'cells': {},
            'required': totals['required'],
            'joined': totals['joined'],
            'open': totals['open'],
        }
        for p in matrix_projects:
            row['cells'][str(p['id'])] = matrix_cells.get(f"{t['id']}:{p['id']}", 0)
        matrix.append(row)

    return {
        'total_required': total,
        'joined': joined,
        'in_progress': in_progress,
        'still_open': open_n,
        'matrix_trades': matrix_trades,
        'matrix_projects': matrix_projects,
        'matrix': matrix,
        'by_project': [
            project_progress[p.id]
            for p in projects
            if project_progress[p.id]['required'] > 0
        ],
    }


def register_manpower_tracker_routes(hr_bp):
    """Attach manpower tracker routes to the HR blueprint."""

    @hr_bp.route('/manpower-tracker')
    @jwt_required()
    def manpower_tracker_dashboard():
        user = _get_current_user()
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        if not user_can_manage_manpower(user):
            return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
        ensure_staffing_link_schema()
        return render_template(
            'hr_manpower_tracker.html',
            user=user,
            hiring_active='manpower',
        )

    @hr_bp.route('/api/manpower/meta', methods=['GET'])
    @jwt_required()
    def api_manpower_meta():
        user, err = _require_manpower_user()
        if err:
            return err
        trades = (
            ManpowerTrade.query
            .order_by(ManpowerTrade.sort_order, ManpowerTrade.name)
            .all()
        )
        projects = (
            ManpowerProject.query
            .order_by(ManpowerProject.sort_order, ManpowerProject.name)
            .all()
        )
        trade_counts = dict(
            db.session.query(ManpowerVacancy.trade_id, db.func.count(ManpowerVacancy.id))
            .group_by(ManpowerVacancy.trade_id)
            .all()
        )
        project_counts = dict(
            db.session.query(ManpowerVacancy.project_id, db.func.count(ManpowerVacancy.id))
            .group_by(ManpowerVacancy.project_id)
            .all()
        )

        def trade_dict(t):
            d = t.to_dict()
            d['vacancy_count'] = int(trade_counts.get(t.id, 0) or 0)
            return d

        def project_dict(p):
            d = p.to_dict()
            d['vacancy_count'] = int(project_counts.get(p.id, 0) or 0)
            return d

        return success_response({
            'trades': [trade_dict(t) for t in trades],
            'projects': [project_dict(p) for p in projects],
            'statuses': [
                {'key': k, 'label': MANPOWER_STATUS_LABELS[k]}
                for k in MANPOWER_STATUSES
            ],
            'requirement_types': [
                {'key': k, 'label': MANPOWER_REQUIREMENT_TYPE_LABELS[k]}
                for k in MANPOWER_REQUIREMENT_TYPES
            ],
        })

    @hr_bp.route('/api/manpower/summary', methods=['GET'])
    @jwt_required()
    def api_manpower_summary():
        user, err = _require_manpower_user()
        if err:
            return err
        vacancies = (
            ManpowerVacancy.query
            .options(
                joinedload(ManpowerVacancy.trade),
                joinedload(ManpowerVacancy.project),
            )
            .all()
        )
        trades = (
            ManpowerTrade.query
            .order_by(ManpowerTrade.sort_order, ManpowerTrade.name)
            .all()
        )
        projects = (
            ManpowerProject.query
            .order_by(ManpowerProject.sort_order, ManpowerProject.name)
            .all()
        )
        return success_response(_build_summary(vacancies, trades, projects))

    @hr_bp.route('/api/manpower/matrix/cell', methods=['PUT'])
    @jwt_required()
    def api_set_manpower_matrix_cell():
        """Set required headcount for a trade × project cell (creates/deletes vacancy rows)."""
        user, err = _require_manpower_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        trade_id = data.get('trade_id')
        project_id = data.get('project_id')
        raw_count = data.get('count')

        if trade_id is None or project_id is None:
            return error_response(
                'trade_id and project_id are required',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        try:
            trade_id = int(trade_id)
            project_id = int(project_id)
            count = int(raw_count)
        except (TypeError, ValueError):
            return error_response(
                'trade_id, project_id, and count must be integers',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        if count < 0:
            return error_response('count cannot be negative', status_code=400, error_code='VALIDATION_ERROR')
        if count > 200:
            return error_response(
                'count cannot exceed 200 for one trade × project cell',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        trade = db.session.get(ManpowerTrade, trade_id)
        project = db.session.get(ManpowerProject, project_id)
        if not trade:
            return error_response('Trade not found', status_code=404, error_code='NOT_FOUND')
        if not project:
            return error_response('Project not found', status_code=404, error_code='NOT_FOUND')

        try:
            result = _set_matrix_cell_count(
                trade=trade,
                project=project,
                target=count,
                user=user,
            )
        except ValueError as e:
            return error_response(str(e), status_code=400, error_code='VALIDATION_ERROR')

        vacancies = (
            ManpowerVacancy.query
            .options(
                joinedload(ManpowerVacancy.trade),
                joinedload(ManpowerVacancy.project),
            )
            .all()
        )
        trades = (
            ManpowerTrade.query
            .order_by(ManpowerTrade.sort_order, ManpowerTrade.name)
            .all()
        )
        projects = (
            ManpowerProject.query
            .order_by(ManpowerProject.sort_order, ManpowerProject.name)
            .all()
        )
        return success_response({
            'cell': result,
            'summary': _build_summary(vacancies, trades, projects),
        })

    @hr_bp.route('/api/manpower/vacancies', methods=['GET'])
    @jwt_required()
    def api_list_manpower_vacancies():
        user, err = _require_manpower_user()
        if err:
            return err

        q = (request.args.get('q') or '').strip()
        trade_id = request.args.get('trade_id')
        project_id = request.args.get('project_id')
        status = (request.args.get('status') or 'all').strip().lower()
        req_type = (request.args.get('requirement_type') or 'all').strip().lower()

        query = (
            ManpowerVacancy.query
            .options(
                joinedload(ManpowerVacancy.trade),
                joinedload(ManpowerVacancy.project),
                joinedload(ManpowerVacancy.hiring_candidate),
            )
        )
        if trade_id and str(trade_id).isdigit():
            query = query.filter(ManpowerVacancy.trade_id == int(trade_id))
        if project_id and str(project_id).isdigit():
            query = query.filter(ManpowerVacancy.project_id == int(project_id))
        if status and status != 'all':
            norm = _normalize_status(status)
            if norm and norm is not False:
                query = query.filter(ManpowerVacancy.status == norm)
        if req_type and req_type != 'all':
            rnorm = _normalize_req_type(req_type)
            if rnorm and rnorm is not False:
                query = query.filter(ManpowerVacancy.requirement_type == rnorm)
        linked = (request.args.get('linked') or 'all').strip().lower()
        if linked == 'linked':
            query = query.filter(ManpowerVacancy.hiring_candidate_id.isnot(None))
        elif linked in ('unlinked', 'open'):
            query = query.filter(ManpowerVacancy.hiring_candidate_id.is_(None))
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                ManpowerVacancy.candidate_name.ilike(like),
                ManpowerVacancy.replacement_name.ilike(like),
                ManpowerVacancy.replacement_employee_id.ilike(like),
                ManpowerVacancy.contact_number.ilike(like),
                ManpowerVacancy.remarks.ilike(like),
            ))

        vacancies = query.all()
        # Sort for board grouping
        vacancies.sort(key=_vacancy_sort_key)
        # Person N of M must consider full trade×project set (not filtered subset for totals)
        # Recompute within the filtered list so labels match visible rows
        items = _annotate_person_labels(vacancies)
        return success_response({'vacancies': items, 'count': len(items)})

    @hr_bp.route('/api/manpower/vacancies', methods=['POST'])
    @jwt_required()
    def api_create_manpower_vacancy():
        user, err = _require_manpower_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}

        trade_id = data.get('trade_id')
        project_id = data.get('project_id')
        if not trade_id:
            return error_response('trade_id is required', status_code=400, error_code='VALIDATION_ERROR')
        if not project_id:
            return error_response('project_id is required', status_code=400, error_code='VALIDATION_ERROR')

        trade = db.session.get(ManpowerTrade, int(trade_id))
        project = db.session.get(ManpowerProject, int(project_id))
        if not trade:
            return error_response('Trade not found', status_code=404, error_code='NOT_FOUND')
        if not project:
            return error_response('Project not found', status_code=404, error_code='NOT_FOUND')

        req = _normalize_req_type(data.get('requirement_type') or MANPOWER_REQUIREMENT_TYPE_DEFAULT)
        if req is False:
            return error_response('Invalid requirement_type', status_code=400, error_code='VALIDATION_ERROR')
        status = _normalize_status(data.get('status') or MANPOWER_STATUS_DEFAULT)
        if status is False:
            return error_response('Invalid status', status_code=400, error_code='VALIDATION_ERROR')

        dj = _parse_date(data.get('date_joined'))
        if dj is False:
            return error_response('Invalid date_joined', status_code=400, error_code='VALIDATION_ERROR')

        max_sort = (
            db.session.query(db.func.coalesce(db.func.max(ManpowerVacancy.sort_order), 0))
            .filter_by(trade_id=trade.id, project_id=project.id)
            .scalar()
        ) or 0

        vac = ManpowerVacancy(
            trade_id=trade.id,
            project_id=project.id,
            requirement_type=req or MANPOWER_REQUIREMENT_TYPE_DEFAULT,
            replacement_name=(data.get('replacement_name') or '').strip() or None,
            replacement_employee_id=(data.get('replacement_employee_id') or '').strip() or None,
            candidate_name=(data.get('candidate_name') or '').strip() or None,
            contact_number=(data.get('contact_number') or '').strip() or None,
            status=status or MANPOWER_STATUS_DEFAULT,
            date_joined=dj,
            remarks=(data.get('remarks') or '').strip() or None,
            sort_order=max_sort + 1,
            created_by=user.id if user else None,
        )
        db.session.add(vac)
        db.session.commit()
        db.session.refresh(vac)
        return success_response({'vacancy': vac.to_dict(person_of=1, person_total=1)}, status_code=201)

    @hr_bp.route('/api/manpower/vacancies/<int:vacancy_id>', methods=['PATCH'])
    @jwt_required()
    def api_update_manpower_vacancy(vacancy_id):
        user, err = _require_manpower_user()
        if err:
            return err
        vac = db.session.get(ManpowerVacancy, vacancy_id)
        if not vac:
            return error_response('Vacancy not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(silent=True) or {}

        if 'trade_id' in data:
            tid = data.get('trade_id')
            if not tid:
                return error_response('trade_id cannot be empty', status_code=400)
            trade = db.session.get(ManpowerTrade, int(tid))
            if not trade:
                return error_response('Trade not found', status_code=404)
            vac.trade_id = trade.id

        if 'project_id' in data:
            pid = data.get('project_id')
            if not pid:
                return error_response('project_id cannot be empty', status_code=400)
            project = db.session.get(ManpowerProject, int(pid))
            if not project:
                return error_response('Project not found', status_code=404)
            vac.project_id = project.id

        if 'requirement_type' in data:
            req = _normalize_req_type(data.get('requirement_type'))
            if req is False or req is None:
                return error_response('Invalid requirement_type', status_code=400)
            vac.requirement_type = req

        if 'status' in data:
            status = _normalize_status(data.get('status'))
            if status is False or status is None:
                return error_response('Invalid status', status_code=400)
            vac.status = status

        if 'replacement_name' in data:
            vac.replacement_name = (data.get('replacement_name') or '').strip() or None
        if 'replacement_employee_id' in data:
            vac.replacement_employee_id = (data.get('replacement_employee_id') or '').strip() or None
        # Linked vacancies: candidate name/contact come from Hiring — ignore free-text overwrites
        if not vac.hiring_candidate_id:
            if 'candidate_name' in data:
                vac.candidate_name = (data.get('candidate_name') or '').strip() or None
            if 'contact_number' in data:
                vac.contact_number = (data.get('contact_number') or '').strip() or None
        if 'remarks' in data:
            vac.remarks = (data.get('remarks') or '').strip() or None
        if 'date_joined' in data:
            dj = _parse_date(data.get('date_joined'))
            if dj is False:
                return error_response('Invalid date_joined', status_code=400)
            vac.date_joined = dj
        if 'sort_order' in data and data.get('sort_order') is not None:
            try:
                vac.sort_order = int(data.get('sort_order'))
            except (TypeError, ValueError):
                return error_response('Invalid sort_order', status_code=400)

        vac.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(vac)
        return success_response({'vacancy': vac.to_dict()})

    @hr_bp.route('/api/manpower/vacancies/<int:vacancy_id>', methods=['DELETE'])
    @jwt_required()
    def api_delete_manpower_vacancy(vacancy_id):
        user, err = _require_manpower_user()
        if err:
            return err
        vac = db.session.get(ManpowerVacancy, vacancy_id)
        if not vac:
            return error_response('Vacancy not found', status_code=404, error_code='NOT_FOUND')
        db.session.delete(vac)
        db.session.commit()
        return success_response(message='Vacancy deleted')

    @hr_bp.route('/api/manpower/vacancies/<int:vacancy_id>/duplicate', methods=['POST'])
    @jwt_required()
    def api_duplicate_manpower_vacancy(vacancy_id):
        user, err = _require_manpower_user()
        if err:
            return err
        vac = db.session.get(ManpowerVacancy, vacancy_id)
        if not vac:
            return error_response('Vacancy not found', status_code=404, error_code='NOT_FOUND')

        max_sort = (
            db.session.query(db.func.coalesce(db.func.max(ManpowerVacancy.sort_order), 0))
            .filter_by(trade_id=vac.trade_id, project_id=vac.project_id)
            .scalar()
        ) or 0

        clone = ManpowerVacancy(
            trade_id=vac.trade_id,
            project_id=vac.project_id,
            requirement_type=vac.requirement_type,
            replacement_name=vac.replacement_name,
            replacement_employee_id=vac.replacement_employee_id,
            candidate_name=None,
            contact_number=None,
            status=MANPOWER_STATUS_DEFAULT,
            date_joined=None,
            remarks=None,
            sort_order=max_sort + 1,
            created_by=user.id if user else None,
        )
        db.session.add(clone)
        db.session.commit()
        db.session.refresh(clone)
        return success_response({'vacancy': clone.to_dict()}, status_code=201)

    # ── Trades / Projects management ──────────────────────────────────────

    @hr_bp.route('/api/manpower/trades', methods=['POST'])
    @jwt_required()
    def api_create_manpower_trade():
        user, err = _require_manpower_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return error_response('Trade name is required', status_code=400)
        existing = ManpowerTrade.query.filter(
            db.func.lower(ManpowerTrade.name) == name.lower()
        ).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.updated_at = utc_now_naive()
                db.session.commit()
                return success_response({'trade': existing.to_dict()})
            return error_response('Trade already exists', status_code=400)
        max_sort = db.session.query(
            db.func.coalesce(db.func.max(ManpowerTrade.sort_order), 0)
        ).scalar() or 0
        row = ManpowerTrade(name=name, sort_order=max_sort + 10, active=True)
        db.session.add(row)
        db.session.commit()
        return success_response({'trade': row.to_dict()}, status_code=201)

    @hr_bp.route('/api/manpower/trades/<int:trade_id>', methods=['PATCH'])
    @jwt_required()
    def api_update_manpower_trade(trade_id):
        user, err = _require_manpower_user()
        if err:
            return err
        row = db.session.get(ManpowerTrade, trade_id)
        if not row:
            return error_response('Trade not found', status_code=404)
        data = request.get_json(silent=True) or {}
        if 'name' in data:
            name = (data.get('name') or '').strip()
            if not name:
                return error_response('Trade name cannot be empty', status_code=400)
            clash = ManpowerTrade.query.filter(
                db.func.lower(ManpowerTrade.name) == name.lower(),
                ManpowerTrade.id != trade_id,
            ).first()
            if clash:
                return error_response('Trade name already used', status_code=400)
            row.name = name
        if 'active' in data:
            row.active = bool(data.get('active'))
        if 'sort_order' in data and data.get('sort_order') is not None:
            row.sort_order = int(data.get('sort_order'))
        row.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'trade': row.to_dict()})

    @hr_bp.route('/api/manpower/projects', methods=['POST'])
    @jwt_required()
    def api_create_manpower_project():
        user, err = _require_manpower_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return error_response('Project name is required', status_code=400)
        existing = ManpowerProject.query.filter(
            db.func.lower(ManpowerProject.name) == name.lower()
        ).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.updated_at = utc_now_naive()
                db.session.commit()
                return success_response({'project': existing.to_dict()})
            return error_response('Project already exists', status_code=400)
        max_sort = db.session.query(
            db.func.coalesce(db.func.max(ManpowerProject.sort_order), 0)
        ).scalar() or 0
        row = ManpowerProject(name=name, sort_order=max_sort + 10, active=True)
        db.session.add(row)
        db.session.commit()
        return success_response({'project': row.to_dict()}, status_code=201)

    @hr_bp.route('/api/manpower/projects/<int:project_id>', methods=['PATCH'])
    @jwt_required()
    def api_update_manpower_project(project_id):
        user, err = _require_manpower_user()
        if err:
            return err
        row = db.session.get(ManpowerProject, project_id)
        if not row:
            return error_response('Project not found', status_code=404)
        data = request.get_json(silent=True) or {}
        if 'name' in data:
            name = (data.get('name') or '').strip()
            if not name:
                return error_response('Project name cannot be empty', status_code=400)
            clash = ManpowerProject.query.filter(
                db.func.lower(ManpowerProject.name) == name.lower(),
                ManpowerProject.id != project_id,
            ).first()
            if clash:
                return error_response('Project name already used', status_code=400)
            row.name = name
        if 'active' in data:
            row.active = bool(data.get('active'))
        if 'sort_order' in data and data.get('sort_order') is not None:
            row.sort_order = int(data.get('sort_order'))
        row.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'project': row.to_dict()})

    # ── Excel ─────────────────────────────────────────────────────────────

    @hr_bp.route('/api/manpower/template', methods=['GET'])
    @jwt_required()
    def api_manpower_template():
        user, err = _require_manpower_user()
        if err:
            return err
        from module_hr.manpower_excel import build_manpower_template_bytes
        data = build_manpower_template_bytes()
        return send_file(
            BytesIO(data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='Manpower_Tracker_Template.xlsx',
        )

    @hr_bp.route('/api/manpower/export', methods=['GET'])
    @jwt_required()
    def api_manpower_export():
        user, err = _require_manpower_user()
        if err:
            return err
        from module_hr.manpower_excel import build_manpower_export_bytes
        data = build_manpower_export_bytes()
        return send_file(
            BytesIO(data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='Manpower_Tracker_Export.xlsx',
        )

    @hr_bp.route('/api/manpower/import', methods=['POST'])
    @jwt_required()
    def api_manpower_import():
        user, err = _require_manpower_user()
        if err:
            return err
        if 'file' not in request.files:
            return error_response('No file uploaded', status_code=400, error_code='VALIDATION_ERROR')
        file = request.files['file']
        if not file or not file.filename:
            return error_response('No file selected', status_code=400, error_code='VALIDATION_ERROR')

        replace = (request.form.get('replace') or request.args.get('replace') or '').strip().lower() in (
            '1', 'true', 'yes',
        )

        from module_hr.manpower_excel import apply_manpower_import
        try:
            result = apply_manpower_import(
                file,
                replace=replace,
                created_by=user.id if user else None,
            )
        except ImportError:
            return error_response(
                'openpyxl is required for Excel import',
                status_code=500,
                error_code='DEPENDENCY_ERROR',
            )
        except Exception as e:
            logger.exception('Manpower Excel import failed')
            return error_response(f'Import failed: {e}', status_code=400)

        return success_response(result, message='Import complete')
