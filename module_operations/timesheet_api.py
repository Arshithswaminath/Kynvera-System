"""Duty / Timesheet API — registered on operations_bp."""
from __future__ import annotations

import uuid
from datetime import datetime, date

from flask import render_template, redirect, request
from flask_jwt_extended import jwt_required

from app.models import db, DutyTimesheetEntry
from common.error_responses import success_response, error_response


def _gen_id():
    return 'DUTY-' + uuid.uuid4().hex[:8].upper()


def _parse_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_hhmm(value):
    s = str(value or '').strip()
    if not s:
        return None
    parts = s.split(':')
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f'{h:02d}:{m:02d}'


def _hours_between(start_hhmm, end_hhmm):
    sh, sm = map(int, start_hhmm.split(':'))
    eh, em = map(int, end_hhmm.split(':'))
    start_m = sh * 60 + sm
    end_m = eh * 60 + em
    if end_m <= start_m:
        end_m += 24 * 60
    return round((end_m - start_m) / 60.0, 2)


def _can_see_rates(user):
    if not user:
        return False
    if user.role == 'admin':
        return True
    if bool(getattr(user, 'access_finance', False)):
        return True
    desig = str(getattr(user, 'designation', '') or '').strip().lower()
    return desig in ('general_manager', 'finance', 'finance_manager')


def register_timesheet_routes(bp, *, current_user_fn, has_ops_sub_access_fn, rate_for_date_fn, day_type_for_date_fn):
    @bp.route('/timesheet')
    @jwt_required()
    def timesheet_page():
        user = current_user_fn()
        if not has_ops_sub_access_fn(user, 'timesheet'):
            return redirect('/dashboard')
        return render_template(
            'timesheet.html',
            user=user,
            can_see_rates=_can_see_rates(user),
        )

    @bp.route('/api/timesheet', methods=['GET'])
    @jwt_required()
    def api_list_timesheet():
        user = current_user_fn()
        if not has_ops_sub_access_fn(user, 'timesheet'):
            return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
        q = DutyTimesheetEntry.query.order_by(
            DutyTimesheetEntry.work_date.desc(), DutyTimesheetEntry.id.desc()
        )
        project = (request.args.get('project') or '').strip()
        if project:
            q = q.filter(DutyTimesheetEntry.project_name.ilike(f'%{project}%'))
        rows = q.limit(500).all()
        include_rates = _can_see_rates(user)
        total_hours = round(sum(float(r.hours or 0) for r in rows), 2)
        return success_response({
            'entries': [r.to_dict(include_rates=include_rates) for r in rows],
            'total_hours': total_hours,
            'can_see_rates': include_rates,
        })

    @bp.route('/api/timesheet', methods=['POST'])
    @jwt_required()
    def api_create_timesheet():
        user = current_user_fn()
        if not has_ops_sub_access_fn(user, 'timesheet'):
            return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
        data = request.get_json(silent=True) or {}
        staff = (data.get('staff_name') or '').strip()
        project = (data.get('project_name') or '').strip()
        work_date = _parse_date(data.get('work_date') or data.get('date'))
        start_time = _parse_hhmm(data.get('start_time'))
        end_time = _parse_hhmm(data.get('end_time'))
        if not staff or not project or not work_date or not start_time or not end_time:
            return error_response(
                'staff_name, project_name, work_date, start_time, and end_time are required',
                status_code=400, error_code='VALIDATION',
            )
        hours = _hours_between(start_time, end_time)
        day_type = day_type_for_date_fn(work_date)
        rate = rate_for_date_fn(work_date)
        total = round(hours * float(rate), 2) if rate is not None else None
        row = DutyTimesheetEntry(
            entry_id=_gen_id(),
            staff_name=staff,
            employee_id=(data.get('employee_id') or '').strip() or None,
            project_name=project,
            project_code=(data.get('project_code') or '').strip() or None,
            work_date=work_date,
            start_time=start_time,
            end_time=end_time,
            hours=hours,
            day_type=day_type,
            rate_per_hour=rate,
            total_amount=total,
            remarks=(data.get('remarks') or '').strip() or None,
            status='submitted',
            created_by_id=user.id if user else None,
        )
        db.session.add(row)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return error_response(f'Database error: {e}', status_code=500, error_code='DATABASE_ERROR')
        return success_response(
            {'entry': row.to_dict(include_rates=_can_see_rates(user))},
            message='Timesheet entry saved.',
        )

    @bp.route('/api/timesheet/<entry_id>', methods=['PUT'])
    @jwt_required()
    def api_update_timesheet(entry_id):
        user = current_user_fn()
        if not has_ops_sub_access_fn(user, 'timesheet'):
            return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
        row = DutyTimesheetEntry.query.filter_by(entry_id=entry_id).first()
        if not row:
            return error_response('Entry not found', status_code=404, error_code='NOT_FOUND')
        data = request.get_json(silent=True) or {}
        if 'staff_name' in data:
            row.staff_name = (data.get('staff_name') or '').strip() or row.staff_name
        if 'employee_id' in data:
            row.employee_id = (data.get('employee_id') or '').strip() or None
        if 'project_name' in data:
            row.project_name = (data.get('project_name') or '').strip() or row.project_name
        if 'project_code' in data:
            row.project_code = (data.get('project_code') or '').strip() or None
        if 'work_date' in data or 'date' in data:
            d = _parse_date(data.get('work_date') or data.get('date'))
            if d:
                row.work_date = d
        if 'start_time' in data:
            st = _parse_hhmm(data.get('start_time'))
            if st:
                row.start_time = st
        if 'end_time' in data:
            et = _parse_hhmm(data.get('end_time'))
            if et:
                row.end_time = et
        if 'remarks' in data:
            row.remarks = (data.get('remarks') or '').strip() or None
        row.hours = _hours_between(row.start_time, row.end_time)
        row.day_type = day_type_for_date_fn(row.work_date)
        row.rate_per_hour = rate_for_date_fn(row.work_date)
        row.total_amount = (
            round(row.hours * float(row.rate_per_hour), 2)
            if row.rate_per_hour is not None else None
        )
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return error_response(f'Database error: {e}', status_code=500, error_code='DATABASE_ERROR')
        return success_response(
            {'entry': row.to_dict(include_rates=_can_see_rates(user))},
            message='Timesheet entry updated.',
        )

    @bp.route('/api/timesheet/<entry_id>', methods=['DELETE'])
    @jwt_required()
    def api_delete_timesheet(entry_id):
        user = current_user_fn()
        if not has_ops_sub_access_fn(user, 'timesheet'):
            return error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
        row = DutyTimesheetEntry.query.filter_by(entry_id=entry_id).first()
        if not row:
            return error_response('Entry not found', status_code=404, error_code='NOT_FOUND')
        db.session.delete(row)
        db.session.commit()
        return success_response(message='Timesheet entry deleted.')
