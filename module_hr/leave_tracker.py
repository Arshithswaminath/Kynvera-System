"""
Leave Tracker — Sick + Annual leave from Jan 2026.
Routes registered on hr_bp via register_leave_tracker_routes().
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from flask import current_app, jsonify, render_template, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.models import (
    LEAVE_COMPANIES,
    LEAVE_SICK_ALERT_WARNING,
    LEAVE_SICK_ENTITLEMENT,
    LEAVE_TRACKER_MONTH_LABELS,
    LEAVE_TRACKER_MONTHS,
    LEAVE_TRACKER_YEAR,
    LEAVE_WINDOW_END,
    LEAVE_WINDOW_START,
    LEAVE_TYPES,
    LeaveEmployee,
    LeaveLog,
    LeaveMonthlyUsage,
    LeavePlan,
    User,
    db,
    leave_company_db_values,
    normalize_leave_company,
    leave_sick_alert_level,
    leave_months_through,
    migrate_monthly_usage_to_logs,
    months_touched_by_range,
    recompute_monthly_usage,
    _log_days_in_month,
)
from common.datetime_utils import utc_now_naive
from common.error_responses import error_response, success_response
from module_hr.leave_excel import (
    build_leave_log_template_bytes,
    build_leave_workbook,
    import_leave_workbook,
    seed_employees_from_staff_list,
    split_plan_days_by_month,
)

logger = logging.getLogger(__name__)

STAFF_LIST_BUNDLED = os.path.join(
    os.path.dirname(__file__),
    'data',
    'staff_list_july_2026.xlsx',
)

PERIODS_MIN_YEAR = LEAVE_TRACKER_YEAR
PERIODS_MAX_YEAR = 2035


def _parse_ymd(raw: Optional[str]) -> Optional[date]:
    text = (raw or '').strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _role_is_admin(user: Optional[User]) -> bool:
    return bool(user and getattr(user, 'role', None) == 'admin')


def _user_desig_lc(user: Optional[User]) -> str:
    return (getattr(user, 'designation', None) or '').strip().lower()


def user_can_manage_leave_tracker(user: Optional[User]) -> bool:
    """Same access gate as Hiring Document Tracker."""
    if not user:
        return False
    return bool(user.has_hiring_submodule())


def _get_current_user():
    from module_hr.routes import get_current_user
    return get_current_user()


def _require_leave_user():
    user = _get_current_user()
    if not user:
        return None, error_response('User not found', status_code=404, error_code='NOT_FOUND')
    if not user_can_manage_leave_tracker(user):
        return None, error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    return user, None


def _parse_optional_float(raw):
    if raw is None or raw == '':
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return False  # sentinel for invalid


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
        return None


def _date_in_tracker_window(d: date) -> bool:
    return LEAVE_WINDOW_START <= d <= LEAVE_WINDOW_END


def _window_range_message() -> str:
    return f'{LEAVE_WINDOW_START.isoformat()} and {LEAVE_WINDOW_END.isoformat()}'


def _default_periods() -> dict[str, list[int]]:
    return {str(LEAVE_TRACKER_YEAR): list(LEAVE_TRACKER_MONTHS)}


def _periods_path() -> str:
    return os.path.join(current_app.instance_path, 'leave_tracker_periods.json')


def _normalize_periods(raw) -> dict[str, list[int]]:
    out = _default_periods()
    if not isinstance(raw, dict):
        return out
    for key, months in raw.items():
        try:
            year = int(key)
        except (TypeError, ValueError):
            continue
        if year < PERIODS_MIN_YEAR or year > PERIODS_MAX_YEAR:
            continue
        clean: list[int] = []
        for item in months or []:
            try:
                month = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= month <= 12 and month not in clean:
                clean.append(month)
        if year == LEAVE_TRACKER_YEAR:
            for month in LEAVE_TRACKER_MONTHS:
                if month not in clean:
                    clean.append(month)
        clean.sort()
        if clean:
            out[str(year)] = clean
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def _read_periods() -> dict[str, list[int]]:
    path = _periods_path()
    try:
        with open(path, encoding='utf-8') as fh:
            return _normalize_periods(json.load(fh))
    except Exception:
        return _default_periods()


def _write_periods(periods: dict[str, list[int]]) -> dict[str, list[int]]:
    clean = _normalize_periods(periods)
    os.makedirs(current_app.instance_path, exist_ok=True)
    path = _periods_path()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(clean, fh)
    os.replace(tmp, path)
    return clean


def _parse_year_arg(raw=None) -> int:
    text = (raw if raw is not None else request.args.get('year') or '').strip()
    if text.isdigit():
        year = int(text)
        if PERIODS_MIN_YEAR <= year <= PERIODS_MAX_YEAR:
            return year
    return LEAVE_TRACKER_YEAR


def _parse_month_arg(raw=None) -> Optional[int]:
    text = (raw if raw is not None else request.args.get('month') or '').strip()
    if text.isdigit():
        month = int(text)
        if 1 <= month <= 12:
            return month
    return None


def _ensure_migrated() -> None:
    """Ensure leave_logs columns exist; convert legacy monthly usage into logs once."""
    purged: list[tuple] = []
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'leave_logs' in inspector.get_table_names():
            cols = {c['name'] for c in inspector.get_columns('leave_logs')}
            with db.engine.begin() as conn:
                if 'end_date' not in cols:
                    conn.execute(text('ALTER TABLE leave_logs ADD COLUMN end_date DATE'))
                    logger.info('Added end_date to leave_logs')
                # Archive module revoked: drop archived rows + orphan prior-month usage
                if 'source' in cols:
                    purged = list(
                        conn.execute(
                            text(
                                'SELECT employee_id, leave_type, leave_date, end_date '
                                "FROM leave_logs WHERE source = 'archive'"
                            )
                        ).fetchall()
                    )
                    if purged:
                        conn.execute(text("DELETE FROM leave_logs WHERE source = 'archive'"))
                        conn.execute(
                            text(
                                'DELETE FROM leave_monthly_usage '
                                'WHERE year = :year AND month NOT IN (7, 8, 9, 10, 11, 12)'
                            ),
                            {'year': LEAVE_TRACKER_YEAR},
                        )
                        logger.info('Removed %s revoked archive leave logs', len(purged))
    except Exception:
        logger.exception('Could not ensure leave_logs columns')
        db.session.rollback()
    try:
        migrate_monthly_usage_to_logs()
    except Exception:
        logger.exception('Leave monthly→logs migration failed')
        db.session.rollback()
    if purged:
        try:
            touched: set[tuple[int, str, int, int]] = set()
            for emp_id, leave_type, leave_date, end_date in purged:
                end = end_date or leave_date
                for y, m in months_touched_by_range(leave_date, end):
                    if y == LEAVE_TRACKER_YEAR and m in LEAVE_TRACKER_MONTHS:
                        touched.add((emp_id, leave_type, y, m))
            for emp_id, leave_type, y, m in touched:
                recompute_monthly_usage(emp_id, leave_type, y, m)
            db.session.commit()
        except Exception:
            logger.exception('Leave usage recompute after archive purge failed')
            db.session.rollback()

def _recompute_range(employee_id: int, leave_type: str, start, end) -> None:
    for y, m in months_touched_by_range(start, end):
        recompute_monthly_usage(employee_id, leave_type, y, m)

def _set_month_usage(employee_id: int, leave_type: str, year: int, month: int, days):
    """Set or clear monthly usage. days=None clears the row."""
    row = LeaveMonthlyUsage.query.filter_by(
        employee_id=employee_id,
        leave_type=leave_type,
        year=year,
        month=month,
    ).first()
    if days is None:
        if row:
            db.session.delete(row)
        return
    if not row:
        row = LeaveMonthlyUsage(
            employee_id=employee_id,
            leave_type=leave_type,
            year=year,
            month=month,
        )
        db.session.add(row)
    row.days = float(days)
    row.updated_at = utc_now_naive()


def _employee_after_recompute(emp: LeaveEmployee) -> dict:
    db.session.expire(emp, ['usage'])
    db.session.refresh(emp)
    return emp.to_dict()

def _tracker_focus_month(today: Optional[date] = None) -> tuple[int, int]:
    """Return (year, month) to use for 'this month' KPIs inside the Jul–Dec window."""
    today = today or date.today()
    year = LEAVE_TRACKER_YEAR
    month = today.month
    if today.year != LEAVE_TRACKER_YEAR:
        month = LEAVE_TRACKER_MONTHS[0] if today.year < LEAVE_TRACKER_YEAR else LEAVE_TRACKER_MONTHS[-1]
    elif month < LEAVE_TRACKER_MONTHS[0]:
        month = LEAVE_TRACKER_MONTHS[0]
    elif month > LEAVE_TRACKER_MONTHS[-1]:
        month = LEAVE_TRACKER_MONTHS[-1]
    return year, month


def _days_val(raw) -> float:
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _fetch_tracker_logs(employee_ids: list[int]) -> list[LeaveLog]:
    """Leave logs that start inside the Jul–Dec tracker window."""
    if not employee_ids:
        return []
    return (
        LeaveLog.query.filter(
            LeaveLog.employee_id.in_(employee_ids),
            LeaveLog.leave_date >= LEAVE_WINDOW_START,
            LeaveLog.leave_date <= LEAVE_WINDOW_END,
        ).all()
    )


def _logs_by_employee(logs: list[LeaveLog]) -> dict[int, list[LeaveLog]]:
    out: dict[int, list[LeaveLog]] = {}
    for lg in logs:
        out.setdefault(lg.employee_id, []).append(lg)
    return out


def _log_days_in_tracker_window(lg: LeaveLog) -> float:
    total = 0.0
    for m in LEAVE_TRACKER_MONTHS:
        total += _log_days_in_month(lg, LEAVE_TRACKER_YEAR, m)
    return total


def _employee_took_leave_in_month(
    emp: LeaveEmployee,
    year: int,
    month: int,
    logs_by_emp: Optional[dict[int, list[LeaveLog]]] = None,
) -> bool:
    """True if employee has any leave overlapping year-month (prefers LeaveLog)."""
    if logs_by_emp is not None:
        for lg in logs_by_emp.get(emp.id, []):
            if _log_days_in_month(lg, year, month) > 0:
                return True
        return False
    return (
        _days_val(emp.month_days('sick', year, month)) > 0
        or _days_val(emp.month_days('annual', year, month)) > 0
    )


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _employee_used_in_month(
    emp_id: int,
    leave_type: str,
    year: int,
    month: int,
    logs_by_emp: dict[int, list[LeaveLog]],
) -> float:
    total = 0.0
    for lg in logs_by_emp.get(emp_id, []):
        if lg.leave_type != leave_type:
            continue
        total += _log_days_in_month(lg, year, month)
    return round(total, 2)


def _employee_used_through_month(
    emp_id: int,
    leave_type: str,
    year: int,
    month: int,
    logs_by_emp: dict[int, list[LeaveLog]],
) -> float:
    if year == LEAVE_TRACKER_YEAR:
        months = leave_months_through(month)
    else:
        months = tuple(range(1, month + 1))
    total = 0.0
    for m in months:
        total += _employee_used_in_month(emp_id, leave_type, year, m, logs_by_emp)
    return round(total, 2)


def _employee_used_from_logs(
    emp_id: int,
    leave_type: str,
    logs_by_emp: dict[int, list[LeaveLog]],
) -> float:
    total = 0.0
    for lg in logs_by_emp.get(emp_id, []):
        if lg.leave_type != leave_type:
            continue
        total += _log_days_in_tracker_window(lg)
    return round(total, 2)


def _employee_low_remaining(
    emp: LeaveEmployee,
    year: int = LEAVE_TRACKER_YEAR,
    logs_by_emp: Optional[dict[int, list[LeaveLog]]] = None,
) -> bool:
    """True when sick remaining is low (≤5) or annual remaining is low (≤3)."""
    if logs_by_emp is not None:
        sick_used = _employee_used_from_logs(emp.id, 'sick', logs_by_emp)
        annual_used = _employee_used_from_logs(emp.id, 'annual', logs_by_emp)
    else:
        sick_used = emp.used_total('sick', year)
        annual_used = emp.used_total('annual', year)
    sick_rem = LEAVE_SICK_ENTITLEMENT - sick_used
    if sick_rem <= (LEAVE_SICK_ENTITLEMENT - LEAVE_SICK_ALERT_WARNING):
        return True
    if emp.annual_entitlement is not None:
        annual_rem = float(emp.annual_entitlement) - annual_used
        if annual_rem <= 3:
            return True
    return False


def _repeat_sick_month_map(
    logs_by_emp: dict[int, list[LeaveLog]],
) -> dict[int, list[dict]]:
    """
    Employees with ≥2 sick applications starting in the same calendar month.
    Returns emp_id -> list of {year, month, apps, days}.
    """
    result: dict[int, list[dict]] = {}
    for emp_id, logs in logs_by_emp.items():
        by_month: dict[tuple[int, int], dict] = {}
        for lg in logs:
            if (lg.leave_type or '').lower() != 'sick' or not lg.leave_date:
                continue
            if not (LEAVE_WINDOW_START <= lg.leave_date <= LEAVE_WINDOW_END):
                continue
            key = (lg.leave_date.year, lg.leave_date.month)
            bucket = by_month.setdefault(key, {'apps': 0, 'days': 0.0})
            bucket['apps'] += 1
            bucket['days'] += _days_val(lg.days)
        hits = []
        for (y, m), bucket in sorted(by_month.items()):
            if bucket['apps'] >= 2:
                hits.append({
                    'year': y,
                    'month': m,
                    'month_label': LEAVE_TRACKER_MONTH_LABELS.get(m, str(m)),
                    'applications': bucket['apps'],
                    'days': round(bucket['days'], 1),
                })
        if hits:
            result[emp_id] = hits
    return result


def _employee_has_repeat_sick(
    emp: LeaveEmployee,
    logs_by_emp: dict[int, list[LeaveLog]],
) -> bool:
    return emp.id in _repeat_sick_month_map(logs_by_emp)


def _summary_for(
    employees: list[LeaveEmployee],
    focus_month: Optional[int] = None,
    year: Optional[int] = None,
) -> dict:
    total = len(employees)
    cal_year, calendar_month = _tracker_focus_month()
    year = year if year and PERIODS_MIN_YEAR <= year <= PERIODS_MAX_YEAR else cal_year
    month = focus_month if focus_month and 1 <= focus_month <= 12 else calendar_month
    emp_ids = [e.id for e in employees]
    logs_by_emp = _logs_by_employee(_fetch_tracker_logs(emp_ids))
    repeat_map = _repeat_sick_month_map(logs_by_emp)

    on_leave_month = 0
    sick_days = 0.0
    annual_days = 0.0
    sick_staff = 0
    annual_staff = 0
    low_remaining = 0
    approaching = 0
    exhausted = 0
    critical = 0
    rem_sum = 0.0
    repeat_this_month = 0

    for emp_id, hits in repeat_map.items():
        if any(h.get('month') == month for h in hits):
            repeat_this_month += 1

    for e in employees:
        if _employee_took_leave_in_month(e, year, month, logs_by_emp):
            on_leave_month += 1
        sick_used = _employee_used_through_month(e.id, 'sick', year, month, logs_by_emp)
        sick_in_month = _employee_used_in_month(e.id, 'sick', year, month, logs_by_emp)
        annual_in_month = _employee_used_in_month(e.id, 'annual', year, month, logs_by_emp)
        sick_days += sick_in_month
        annual_days += annual_in_month
        if sick_in_month > 0:
            sick_staff += 1
        if annual_in_month > 0:
            annual_staff += 1
        if _employee_low_remaining(e, year, logs_by_emp):
            low_remaining += 1
        rem_sum += max(0.0, LEAVE_SICK_ENTITLEMENT - sick_used)
        level = leave_sick_alert_level(sick_used)
        if level == 'warning':
            approaching += 1
        elif level == 'critical':
            critical += 1
            approaching += 1
        elif level == 'exhausted':
            exhausted += 1

    return {
        'total_staff': total,
        'on_leave_this_month': on_leave_month,
        'current_month': month,
        'current_month_label': LEAVE_TRACKER_MONTH_LABELS.get(month, ''),
        'sick_staff_month': sick_staff,
        'annual_staff_month': annual_staff,
        'sick_days_total': round(sick_days, 1),
        'annual_days_total': round(annual_days, 1),
        'low_remaining': low_remaining,
        'repeat_sick_month': repeat_this_month,
        # Legacy keys (still returned for older clients)
        'approaching': approaching,
        'critical': critical,
        'exhausted': exhausted,
        'avg_sick_remaining': round(rem_sum / total, 1) if total else LEAVE_SICK_ENTITLEMENT,
        'sick_entitlement': LEAVE_SICK_ENTITLEMENT,
        'year': LEAVE_TRACKER_YEAR,
        'months': list(LEAVE_TRACKER_MONTHS),
        'companies': list(LEAVE_COMPANIES),
    }


def _log_overlaps_dates(
    lg: LeaveLog,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> bool:
    start = lg.leave_date
    if not start:
        return False
    end = lg.end_date or lg.leave_date
    if date_from and end < date_from:
        return False
    if date_to and start > date_to:
        return False
    return True


def _parse_analytics_filters() -> tuple[Optional[int], Optional[date], Optional[date]]:
    """month (8–12), optional date_from / date_to clamped to tracker window."""
    month_raw = (request.args.get('month') or '').strip()
    month = None
    if month_raw.isdigit():
        m = int(month_raw)
        if m in LEAVE_TRACKER_MONTHS:
            month = m
    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'))
    if date_from and date_from < LEAVE_WINDOW_START:
        date_from = LEAVE_WINDOW_START
    if date_to and date_to > LEAVE_WINDOW_END:
        date_to = LEAVE_WINDOW_END
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return month, date_from, date_to


def _filter_sick_logs(
    logs: list[LeaveLog],
    month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[LeaveLog]:
    out: list[LeaveLog] = []
    for lg in logs:
        if (lg.leave_type or '').lower() != 'sick':
            continue
        if date_from or date_to:
            if not _log_overlaps_dates(lg, date_from, date_to):
                continue
        if month is not None:
            if _log_days_in_month(lg, LEAVE_TRACKER_YEAR, month) <= 0:
                continue
        out.append(lg)
    return out


def _build_repeat_sick_rows(
    employees: list[LeaveEmployee],
    month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    logs_by_emp = _logs_by_employee(_fetch_tracker_logs([e.id for e in employees]))
    # Apply date range before repeat detection so filtered apps drive the ≥2 rule
    if date_from or date_to:
        filtered: dict[int, list[LeaveLog]] = {}
        for emp_id, logs in logs_by_emp.items():
            kept = [
                lg for lg in logs
                if (lg.leave_type or '').lower() == 'sick'
                and _log_overlaps_dates(lg, date_from, date_to)
            ]
            if kept:
                filtered[emp_id] = kept
        logs_by_emp = filtered
    repeat_map = _repeat_sick_month_map(logs_by_emp)
    emp_by_id = {e.id: e for e in employees}
    rows = []
    for emp_id, months in repeat_map.items():
        emp = emp_by_id.get(emp_id)
        if not emp:
            continue
        for hit in months:
            if month is not None and hit['month'] != month:
                continue
            rows.append({
                'employee_id': emp.id,
                'emp_id': emp.emp_id,
                'full_name': emp.full_name,
                'company': emp.company or '',
                'designation': emp.designation or '',
                'year': hit['year'],
                'month': hit['month'],
                'month_label': hit['month_label'],
                'applications': hit['applications'],
                'days': hit['days'],
            })
    rows.sort(key=lambda r: (-r['applications'], -r['days'], r['full_name'], r['month']))
    return rows


def _build_sick_trends_rows(
    employees: list[LeaveEmployee],
    month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    """Rank staff by sick applications then days; flag rising vs prior-month average."""
    year, focus_month = _tracker_focus_month()
    if month is not None:
        focus_month = month
    logs_by_emp = _logs_by_employee(_fetch_tracker_logs([e.id for e in employees]))
    rows = []
    for e in employees:
        logs = _filter_sick_logs(
            logs_by_emp.get(e.id, []),
            month=month,
            date_from=date_from,
            date_to=date_to,
        )
        if not logs:
            continue
        apps = len(logs)
        days_by_month = {m: 0.0 for m in LEAVE_TRACKER_MONTHS}
        total_days = 0.0
        for lg in logs:
            for m in LEAVE_TRACKER_MONTHS:
                d = _log_days_in_month(lg, LEAVE_TRACKER_YEAR, m)
                if d > 0:
                    days_by_month[m] += d
                    total_days += d
        prior_months = [m for m in LEAVE_TRACKER_MONTHS if m < focus_month]
        prior_vals = [days_by_month[m] for m in prior_months]
        prior_avg = (sum(prior_vals) / len(prior_vals)) if prior_vals else 0.0
        latest = days_by_month.get(focus_month, 0.0)
        rising = bool(prior_vals) and latest > prior_avg and latest > 0
        rows.append({
            'employee_id': e.id,
            'emp_id': e.emp_id,
            'full_name': e.full_name,
            'company': e.company or '',
            'designation': e.designation or '',
            'applications': apps,
            'days': round(total_days, 1),
            'months': {str(m): round(days_by_month[m], 1) for m in LEAVE_TRACKER_MONTHS},
            'latest_month': focus_month,
            'latest_month_label': LEAVE_TRACKER_MONTH_LABELS.get(focus_month, ''),
            'latest_days': round(latest, 1),
            'prior_avg_days': round(prior_avg, 1),
            'trend': 'rising' if rising else ('active' if total_days > 0 else 'none'),
        })
    rows.sort(key=lambda r: (-r['applications'], -r['days'], r['full_name']))
    return rows



def register_leave_tracker_routes(hr_bp):
    """Attach leave tracker routes to the HR blueprint."""

    @hr_bp.route('/leave-tracker')
    @jwt_required()
    def leave_tracker_dashboard():
        user = _get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user_can_manage_leave_tracker(user):
            return jsonify({'error': 'Access denied'}), 403
        _ensure_migrated()
        return render_template(
            'hr_leave_tracker_dashboard.html',
            user=user,
            hiring_active='leave_tracker',
        )

    @hr_bp.route('/api/leave-tracker/employees', methods=['GET'])
    @jwt_required()
    def api_leave_list_employees():
        user, err = _require_leave_user()
        if err:
            return err
        _ensure_migrated()

        q = (request.args.get('q') or '').strip()
        company = (request.args.get('company') or 'all').strip()
        alerts_only = (request.args.get('alerts_only') or '').strip().lower() in (
            '1', 'true', 'yes',
        )
        alert_level = (request.args.get('alert_level') or '').strip().lower()
        month = _parse_month_arg()
        year = _parse_year_arg()

        query = LeaveEmployee.query.filter_by(active=True).options(
            joinedload(LeaveEmployee.usage),
        )
        if company and company != 'all':
            query = query.filter(LeaveEmployee.company.in_(leave_company_db_values(company)))
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                LeaveEmployee.full_name.ilike(like),
                LeaveEmployee.emp_id.ilike(like),
                LeaveEmployee.designation.ilike(like),
            ))
        employees = query.order_by(
            LeaveEmployee.company.asc(),
            LeaveEmployee.full_name.asc(),
        ).all()

        summary_q = LeaveEmployee.query.filter_by(active=True).options(
            joinedload(LeaveEmployee.usage),
        )
        if company and company != 'all':
            summary_q = summary_q.filter(LeaveEmployee.company.in_(leave_company_db_values(company)))
        summary_emps = summary_q.all()

        if alert_level == 'exhausted':
            employees = [
                e for e in employees
                if leave_sick_alert_level(e.used_total('sick')) == 'exhausted'
            ]
        elif alert_level == 'approaching':
            employees = [
                e for e in employees
                if leave_sick_alert_level(e.used_total('sick')) in ('warning', 'critical')
            ]
        elif alert_level in ('on_leave_month', 'low_remaining', 'repeat_sick_month'):
            logs_by_emp = _logs_by_employee(_fetch_tracker_logs([e.id for e in employees]))
            cal_year, calendar_month = _tracker_focus_month()
            focus_year = year if month is not None else cal_year
            focus = month if month is not None else calendar_month
            if alert_level == 'on_leave_month':
                employees = [
                    e for e in employees
                    if _employee_took_leave_in_month(e, focus_year, focus, logs_by_emp)
                ]
            elif alert_level == 'low_remaining':
                employees = [
                    e for e in employees
                    if _employee_low_remaining(e, focus_year, logs_by_emp)
                ]
            else:
                repeat_map = _repeat_sick_month_map(logs_by_emp)
                employees = [
                    e for e in employees
                    if any(h.get('month') == focus for h in repeat_map.get(e.id, []))
                ]
        elif alerts_only:
            employees = [
                e for e in employees
                if leave_sick_alert_level(e.used_total('sick'))
            ]

        return success_response({
            'employees': [e.to_dict(year=year) for e in employees],
            'summary': _summary_for(summary_emps, focus_month=month, year=year),
        })

    @hr_bp.route('/api/leave-tracker/employees/<int:emp_pk>/leave-profile', methods=['GET'])
    @jwt_required()
    def api_leave_employee_profile(emp_pk):
        """Employee identity, balances, latest leave, and recent applications."""
        user, err = _require_leave_user()
        if err:
            return err
        _ensure_migrated()
        emp = (
            LeaveEmployee.query.options(joinedload(LeaveEmployee.usage))
            .filter_by(id=emp_pk, active=True)
            .first()
        )
        if not emp:
            return error_response('Employee not found', status_code=404, error_code='NOT_FOUND')

        month = _parse_month_arg()
        year = _parse_year_arg()

        logs = (
            LeaveLog.query.filter(
                LeaveLog.employee_id == emp.id,
                LeaveLog.leave_date >= LEAVE_WINDOW_START,
                LeaveLog.leave_date <= LEAVE_WINDOW_END,
            )
            .order_by(LeaveLog.leave_date.desc(), LeaveLog.id.desc())
            .all()
        )
        latest = logs[0].to_dict() if logs else None
        apps = logs
        if month is not None:
            apps = [
                lg for lg in logs
                if _log_days_in_month(lg, year, month) > 0
            ]
        applications = [lg.to_dict() for lg in apps[:8]]

        return success_response({
            'employee': emp.to_dict(year=year),
            'latest': latest,
            'applications': applications,
            'month': month,
            'month_label': LEAVE_TRACKER_MONTH_LABELS.get(month, '') if month else '',
            'year': year,
        })

    @hr_bp.route('/api/leave-tracker/employees/<int:emp_pk>', methods=['PATCH'])
    @jwt_required()
    def api_leave_patch_employee(emp_pk):
        user, err = _require_leave_user()
        if err:
            return err
        emp = db.session.get(LeaveEmployee, emp_pk)
        if not emp:
            return error_response('Employee not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(silent=True) or {}
        if 'annual_entitlement' in data:
            raw = data.get('annual_entitlement')
            if raw is None or raw == '':
                emp.annual_entitlement = None
            else:
                try:
                    emp.annual_entitlement = int(raw)
                except (TypeError, ValueError):
                    return error_response('Invalid annual_entitlement', status_code=400)
        if 'full_name' in data and data['full_name']:
            emp.full_name = str(data['full_name']).strip()
        if 'designation' in data:
            emp.designation = str(data.get('designation') or '').strip()
        if 'company' in data:
            co = normalize_leave_company(data.get('company'), default=None)
            if data.get('company') and not co:
                return error_response('Invalid company', status_code=400)
            if co:
                emp.company = co
        if 'active' in data:
            emp.active = bool(data['active'])
        emp.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'employee': emp.to_dict()})

    @hr_bp.route('/api/leave-tracker/employees/<int:emp_pk>/usage', methods=['PUT'])
    @jwt_required()
    def api_leave_put_usage(emp_pk):
        """Deprecated direct month edit — creates/replaces a synthetic month log instead."""
        user, err = _require_leave_user()
        if err:
            return err
        emp = db.session.get(LeaveEmployee, emp_pk)
        if not emp:
            return error_response('Employee not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(silent=True) or {}
        leave_type = (data.get('leave_type') or '').strip().lower()
        if leave_type not in LEAVE_TYPES:
            return error_response('leave_type must be sick or annual', status_code=400)

        year = int(data.get('year') or LEAVE_TRACKER_YEAR)
        month = int(data.get('month') or 0)
        if month < 1 or month > 12:
            return error_response('Month must be between 1 and 12', status_code=400)

        if 'days' not in data:
            return error_response('days is required (null to clear)', status_code=400)
        days_raw = data.get('days')
        if days_raw is None or days_raw == '':
            days = None
        else:
            parsed = _parse_optional_float(days_raw)
            if parsed is False:
                return error_response('Invalid days value', status_code=400)
            if parsed is not None and parsed < 0:
                return error_response('days cannot be negative', status_code=400)
            days = parsed

        # Replace any logs for this month/type with a single synthetic log (or clear)
        month_start = date(year, month, 1)
        month_end = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
        existing = LeaveLog.query.filter(
            LeaveLog.employee_id == emp.id,
            LeaveLog.leave_type == leave_type,
            LeaveLog.leave_date >= month_start,
            LeaveLog.leave_date < month_end,
        ).all()
        for lg in existing:
            db.session.delete(lg)
        db.session.flush()

        if days is not None and days > 0:
            db.session.add(LeaveLog(
                employee_id=emp.id,
                leave_type=leave_type,
                leave_date=month_start,
                days=float(days),
                notes='Adjusted via monthly total',
                created_by=user.id,
            ))
        recompute_monthly_usage(emp.id, leave_type, year, month)
        emp.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'employee': _employee_after_recompute(emp)})

    # ── Leave Logs (source of truth) ────────────────────────────────────────

    @hr_bp.route('/api/leave-tracker/logs', methods=['GET'])
    @jwt_required()
    def api_leave_list_logs():
        user, err = _require_leave_user()
        if err:
            return err
        _ensure_migrated()

        q = (request.args.get('q') or '').strip()
        company = (request.args.get('company') or 'all').strip()
        leave_type = (request.args.get('leave_type') or 'all').strip().lower()
        month_raw = (request.args.get('month') or '').strip()
        year = _parse_year_arg()
        emp_id = request.args.get('employee_id')
        leave_from = _parse_ymd(request.args.get('leave_from'))
        leave_to = _parse_ymd(request.args.get('leave_to'))
        alerts_only = (request.args.get('alerts_only') or '').strip().lower() in (
            '1', 'true', 'yes',
        )
        alert_level = (request.args.get('alert_level') or '').strip().lower()

        query = LeaveLog.query.options(joinedload(LeaveLog.employee)).filter(
            LeaveLog.leave_date >= LEAVE_WINDOW_START,
            LeaveLog.leave_date <= LEAVE_WINDOW_END,
        )
        needs_join = (
            (company and company != 'all')
            or bool(q)
            or alerts_only
            or alert_level in ('approaching', 'exhausted')
        )
        if needs_join:
            query = query.join(LeaveEmployee)

        if company and company != 'all':
            query = query.filter(LeaveEmployee.company.in_(leave_company_db_values(company)))
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                LeaveEmployee.full_name.ilike(like),
                LeaveEmployee.emp_id.ilike(like),
                LeaveLog.notes.ilike(like),
            ))
        if leave_type in LEAVE_TYPES:
            query = query.filter(LeaveLog.leave_type == leave_type)
        if month_raw.isdigit() and 1 <= int(month_raw) <= 12:
            start, end = _month_bounds(year, int(month_raw))
            query = query.filter(
                func.coalesce(LeaveLog.end_date, LeaveLog.leave_date) >= start,
                LeaveLog.leave_date <= end,
            )
        if leave_from:
            query = query.filter(func.coalesce(LeaveLog.end_date, LeaveLog.leave_date) >= leave_from)
        if leave_to:
            query = query.filter(LeaveLog.leave_date <= leave_to)
        if emp_id:
            try:
                query = query.filter(LeaveLog.employee_id == int(emp_id))
            except (TypeError, ValueError):
                pass

        logs = query.order_by(LeaveLog.leave_date.desc(), LeaveLog.id.desc()).limit(2000).all()

        if alerts_only or alert_level in (
            'approaching', 'exhausted', 'on_leave_month', 'low_remaining', 'repeat_sick_month',
        ):
            filtered = []
            year, focus_month = _tracker_focus_month()
            emp_ids = list({lg.employee_id for lg in logs if lg.employee_id})
            logs_by_emp = _logs_by_employee(_fetch_tracker_logs(emp_ids)) if emp_ids else {}
            for lg in logs:
                emp = lg.employee
                if not emp:
                    continue
                if alert_level == 'on_leave_month':
                    if not _employee_took_leave_in_month(emp, year, focus_month, logs_by_emp):
                        continue
                elif alert_level == 'low_remaining':
                    if not _employee_low_remaining(emp, year, logs_by_emp):
                        continue
                elif alert_level == 'repeat_sick_month':
                    if not _employee_has_repeat_sick(emp, logs_by_emp):
                        continue
                else:
                    level = leave_sick_alert_level(emp.used_total('sick'))
                    if alert_level == 'exhausted' and level != 'exhausted':
                        continue
                    if alert_level == 'approaching' and level not in ('warning', 'critical'):
                        continue
                    if alerts_only and not alert_level and not level:
                        continue
                filtered.append(lg)
            logs = filtered

        return success_response({'logs': [lg.to_dict() for lg in logs]})

    @hr_bp.route('/api/leave-tracker/logs', methods=['POST'])
    @jwt_required()
    def api_leave_create_log():
        user, err = _require_leave_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        emp = db.session.get(LeaveEmployee, data.get('employee_id'))
        if not emp or not emp.active:
            return error_response('employee_id is required (active staff)', status_code=400)

        leave_type = (data.get('leave_type') or '').strip().lower()
        if leave_type not in LEAVE_TYPES:
            return error_response('leave_type must be sick or annual', status_code=400)

        leave_date = _parse_date(data.get('leave_date') or data.get('start_date'))
        if not leave_date:
            return error_response('leave_date (start) is required (YYYY-MM-DD)', status_code=400)
        end_date = _parse_date(data.get('end_date')) or leave_date
        if end_date < leave_date:
            return error_response('end_date must be on or after start date', status_code=400)
        if not _date_in_tracker_window(leave_date) or not _date_in_tracker_window(end_date):
            return error_response(f'dates must be between {_window_range_message()}', status_code=400)

        cal_days = (end_date - leave_date).days + 1
        days_raw = data.get('days', cal_days)
        parsed = _parse_optional_float(days_raw)
        if parsed is False or parsed is None or parsed <= 0:
            parsed = float(cal_days)

        log = LeaveLog(
            employee_id=emp.id,
            leave_type=leave_type,
            leave_date=leave_date,
            end_date=end_date if end_date != leave_date else None,
            days=float(parsed),
            notes=str(data.get('notes') or '').strip(),
            created_by=user.id,
        )
        db.session.add(log)
        db.session.flush()
        _recompute_range(emp.id, leave_type, leave_date, end_date)
        emp.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(log)
        return success_response({
            'log': log.to_dict(),
            'employee': _employee_after_recompute(emp),
        }, status_code=201)

    @hr_bp.route('/api/leave-tracker/logs/<int:log_id>', methods=['PATCH'])
    @jwt_required()
    def api_leave_patch_log(log_id):
        user, err = _require_leave_user()
        if err:
            return err
        log = db.session.get(LeaveLog, log_id)
        if not log:
            return error_response('Log not found', status_code=404, error_code='NOT_FOUND')

        old_emp = log.employee_id
        old_type = log.leave_type
        old_start = log.leave_date
        old_end = log.end_date or log.leave_date

        data = request.get_json(silent=True) or {}
        if 'employee_id' in data:
            emp = db.session.get(LeaveEmployee, data.get('employee_id'))
            if not emp:
                return error_response('Employee not found', status_code=404)
            log.employee_id = emp.id
        if 'leave_type' in data:
            lt = (data.get('leave_type') or '').strip().lower()
            if lt not in LEAVE_TYPES:
                return error_response('leave_type must be sick or annual', status_code=400)
            log.leave_type = lt
        if 'leave_date' in data or 'start_date' in data:
            leave_date = _parse_date(data.get('leave_date') or data.get('start_date'))
            if not leave_date:
                return error_response('Invalid leave_date', status_code=400)
            if not _date_in_tracker_window(leave_date):
                return error_response(f'leave_date must be between {_window_range_message()}', status_code=400)
            log.leave_date = leave_date
        if 'end_date' in data:
            end_date = _parse_date(data.get('end_date'))
            if end_date is None and data.get('end_date') in (None, ''):
                log.end_date = None
            elif end_date is None:
                return error_response('Invalid end_date', status_code=400)
            else:
                if not _date_in_tracker_window(end_date):
                    return error_response(f'end_date must be between {_window_range_message()}', status_code=400)
                log.end_date = end_date

        end_eff = log.end_date or log.leave_date
        if end_eff < log.leave_date:
            return error_response('end_date must be on or after start date', status_code=400)
        if log.end_date and log.end_date == log.leave_date:
            log.end_date = None

        # Recalculate days from range unless explicitly overridden
        cal_days = (end_eff - log.leave_date).days + 1
        if 'days' in data and data.get('days') not in (None, ''):
            parsed = _parse_optional_float(data.get('days'))
            if parsed is False or parsed is None or parsed <= 0:
                return error_response('days must be a positive number', status_code=400)
            log.days = float(parsed)
        else:
            log.days = float(cal_days)

        if 'notes' in data:
            log.notes = str(data.get('notes') or '').strip()

        log.updated_at = utc_now_naive()
        db.session.flush()

        _recompute_range(old_emp, old_type, old_start, old_end)
        _recompute_range(log.employee_id, log.leave_type, log.leave_date, log.end_date or log.leave_date)
        emp = db.session.get(LeaveEmployee, log.employee_id)
        if emp:
            emp.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(log)
        return success_response({
            'log': log.to_dict(),
            'employee': _employee_after_recompute(emp) if emp else None,
        })

    @hr_bp.route('/api/leave-tracker/logs/<int:log_id>', methods=['DELETE'])
    @jwt_required()
    def api_leave_delete_log(log_id):
        user, err = _require_leave_user()
        if err:
            return err
        log = db.session.get(LeaveLog, log_id)
        if not log:
            return error_response('Log not found', status_code=404, error_code='NOT_FOUND')
        emp_id = log.employee_id
        leave_type = log.leave_type
        start = log.leave_date
        end = log.end_date or log.leave_date
        db.session.delete(log)
        db.session.flush()
        _recompute_range(emp_id, leave_type, start, end)
        emp = db.session.get(LeaveEmployee, emp_id)
        if emp:
            emp.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({
            'deleted': True,
            'employee': _employee_after_recompute(emp) if emp else None,
        })

    @hr_bp.route('/api/leave-tracker/employees', methods=['POST'])
    @jwt_required()
    def api_leave_create_employee():
        user, err = _require_leave_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        emp_id = str(data.get('emp_id') or '').strip()
        full_name = str(data.get('full_name') or '').strip()
        if not emp_id or not full_name:
            return error_response('emp_id and full_name are required', status_code=400)
        if LeaveEmployee.query.filter(
            db.func.lower(LeaveEmployee.emp_id) == emp_id.lower()
        ).first():
            return error_response('Emp ID already exists', status_code=409, error_code='CONFLICT')
        company = normalize_leave_company(data.get('company'))
        if not company:
            return error_response('Invalid company', status_code=400)
        ent = data.get('annual_entitlement')
        entitlement = None
        if ent is not None and ent != '':
            try:
                entitlement = int(ent)
            except (TypeError, ValueError):
                return error_response('Invalid annual_entitlement', status_code=400)
        emp = LeaveEmployee(
            emp_id=emp_id,
            full_name=full_name,
            designation=str(data.get('designation') or '').strip(),
            company=company,
            annual_entitlement=entitlement,
            active=True,
        )
        db.session.add(emp)
        db.session.commit()
        return success_response({'employee': emp.to_dict()}, status_code=201)

    @hr_bp.route('/api/leave-tracker/plans', methods=['GET'])
    @jwt_required()
    def api_leave_list_plans():
        user, err = _require_leave_user()
        if err:
            return err
        company = (request.args.get('company') or 'all').strip()
        q = (request.args.get('q') or '').strip()
        query = LeavePlan.query.options(joinedload(LeavePlan.employee))
        needs_join = (company and company != 'all') or bool(q)
        if needs_join:
            query = query.join(LeaveEmployee)
        if company and company != 'all':
            query = query.filter(LeaveEmployee.company.in_(leave_company_db_values(company)))
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                LeaveEmployee.full_name.ilike(like),
                LeaveEmployee.emp_id.ilike(like),
            ))
        year = _parse_year_arg()
        month = _parse_month_arg()
        if month is not None:
            window_start, window_end = _month_bounds(year, month)
        else:
            window_start = LEAVE_WINDOW_START
            window_end = LEAVE_WINDOW_END
        query = query.filter(
            LeavePlan.start_date <= window_end,
            LeavePlan.end_date >= window_start,
        )
        plans = query.order_by(LeavePlan.start_date.asc()).all()
        return success_response({'plans': [p.to_dict() for p in plans]})

    @hr_bp.route('/api/leave-tracker/plans', methods=['POST'])
    @jwt_required()
    def api_leave_create_plan():
        user, err = _require_leave_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        emp_pk = data.get('employee_id')
        emp = db.session.get(LeaveEmployee, emp_pk) if emp_pk else None
        if not emp:
            return error_response('employee_id is required', status_code=400)
        start = _parse_date(data.get('start_date'))
        end = _parse_date(data.get('end_date'))
        if not start or not end:
            return error_response('start_date and end_date are required (YYYY-MM-DD)', status_code=400)
        if end < start:
            return error_response('end_date must be on or after start_date', status_code=400)
        days = LeavePlan.calendar_days(start, end)
        plan = LeavePlan(
            employee_id=emp.id,
            start_date=start,
            end_date=end,
            days=days,
            notes=str(data.get('notes') or '').strip(),
            created_by=user.id,
        )
        db.session.add(plan)
        db.session.commit()
        return success_response({'plan': plan.to_dict()}, status_code=201)

    @hr_bp.route('/api/leave-tracker/plans/<int:plan_id>', methods=['PATCH'])
    @jwt_required()
    def api_leave_patch_plan(plan_id):
        user, err = _require_leave_user()
        if err:
            return err
        plan = db.session.get(LeavePlan, plan_id)
        if not plan:
            return error_response('Plan not found', status_code=404, error_code='NOT_FOUND')
        data = request.get_json(silent=True) or {}
        if 'start_date' in data:
            start = _parse_date(data.get('start_date'))
            if not start:
                return error_response('Invalid start_date', status_code=400)
            plan.start_date = start
        if 'end_date' in data:
            end = _parse_date(data.get('end_date'))
            if not end:
                return error_response('Invalid end_date', status_code=400)
            plan.end_date = end
        if plan.end_date < plan.start_date:
            return error_response('end_date must be on or after start_date', status_code=400)
        plan.days = LeavePlan.calendar_days(plan.start_date, plan.end_date)
        if 'notes' in data:
            plan.notes = str(data.get('notes') or '').strip()
        if 'employee_id' in data:
            emp = db.session.get(LeaveEmployee, data.get('employee_id'))
            if not emp:
                return error_response('Employee not found', status_code=404)
            plan.employee_id = emp.id
        plan.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'plan': plan.to_dict()})

    @hr_bp.route('/api/leave-tracker/plans/<int:plan_id>', methods=['DELETE'])
    @jwt_required()
    def api_leave_delete_plan(plan_id):
        user, err = _require_leave_user()
        if err:
            return err
        plan = db.session.get(LeavePlan, plan_id)
        if not plan:
            return error_response('Plan not found', status_code=404, error_code='NOT_FOUND')
        db.session.delete(plan)
        db.session.commit()
        return success_response({'deleted': True})

    @hr_bp.route('/api/leave-tracker/plans/<int:plan_id>/apply-monthly', methods=['POST'])
    @jwt_required()
    def api_leave_apply_plan_monthly(plan_id):
        """Create annual leave logs from plan day buckets (one log per overlapping month)."""
        user, err = _require_leave_user()
        if err:
            return err
        plan = db.session.get(LeavePlan, plan_id)
        if not plan:
            return error_response('Plan not found', status_code=404, error_code='NOT_FOUND')
        buckets = split_plan_days_by_month(plan.start_date, plan.end_date)
        if not buckets:
            return error_response(
                f'Plan does not overlap the tracker window ({LEAVE_WINDOW_START.isoformat()} – {LEAVE_WINDOW_END.isoformat()})',
                status_code=400,
            )
        note = f'From plan #{plan.id} ({plan.start_date}–{plan.end_date})'
        for month, add_days in buckets.items():
            leave_date = date(LEAVE_TRACKER_YEAR, month, 1)
            db.session.add(LeaveLog(
                employee_id=plan.employee_id,
                leave_type='annual',
                leave_date=leave_date,
                days=float(add_days),
                notes=note,
                created_by=user.id,
            ))
            db.session.flush()
            recompute_monthly_usage(plan.employee_id, 'annual', LEAVE_TRACKER_YEAR, month)
        emp = db.session.get(LeaveEmployee, plan.employee_id)
        if emp:
            emp.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({
            'applied': buckets,
            'employee': _employee_after_recompute(emp) if emp else None,
            'plan': plan.to_dict(),
        })

    @hr_bp.route('/api/leave-tracker/template', methods=['GET'])
    @jwt_required()
    def api_leave_template():
        user, err = _require_leave_user()
        if err:
            return err
        buf = build_leave_log_template_bytes()
        filename = f'leave_log_template_{LEAVE_TRACKER_YEAR}_aug_dec.xlsx'
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @hr_bp.route('/api/leave-tracker/export', methods=['GET'])
    @jwt_required()
    def api_leave_export():
        user, err = _require_leave_user()
        if err:
            return err
        _ensure_migrated()
        employees = (
            LeaveEmployee.query.filter_by(active=True)
            .options(joinedload(LeaveEmployee.usage))
            .order_by(LeaveEmployee.company.asc(), LeaveEmployee.full_name.asc())
            .all()
        )
        plans = (
            LeavePlan.query.options(joinedload(LeavePlan.employee))
            .filter(
                LeavePlan.start_date <= LEAVE_WINDOW_END,
                LeavePlan.end_date >= LEAVE_WINDOW_START,
            )
            .order_by(LeavePlan.start_date.asc())
            .all()
        )
        logs = (
            LeaveLog.query.options(joinedload(LeaveLog.employee))
            .filter(
                LeaveLog.leave_date >= LEAVE_WINDOW_START,
                LeaveLog.leave_date <= LEAVE_WINDOW_END,
            )
            .order_by(LeaveLog.leave_date.asc(), LeaveLog.id.asc())
            .all()
        )
        buf = build_leave_workbook(employees, plans, logs)
        filename = f'leave_tracker_{LEAVE_TRACKER_YEAR}_aug_dec.xlsx'
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @hr_bp.route('/api/leave-tracker/import', methods=['POST'])
    @jwt_required()
    def api_leave_import():
        user, err = _require_leave_user()
        if err:
            return err
        f = request.files.get('file')
        if not f or not f.filename:
            return error_response('file is required', status_code=400)
        try:
            result = import_leave_workbook(f)
        except Exception as e:
            logger.exception('Leave tracker import failed')
            return error_response(f'Import failed: {e}', status_code=400)
        return success_response(result)

    @hr_bp.route('/api/leave-tracker/seed-staff', methods=['POST'])
    @jwt_required()
    def api_leave_seed_staff():
        user, err = _require_leave_user()
        if err:
            return err
        f = request.files.get('file')
        if f and f.filename:
            try:
                result = seed_employees_from_staff_list(f)
            except Exception as e:
                logger.exception('Staff seed from upload failed')
                return error_response(f'Seed failed: {e}', status_code=400)
            return success_response(result)

        path = current_app.config.get('LEAVE_TRACKER_STAFF_LIST') or STAFF_LIST_BUNDLED
        if not os.path.isfile(path):
            return error_response(
                'No staff list file uploaded and bundled staff list not found',
                status_code=404,
                error_code='NOT_FOUND',
            )
        try:
            result = seed_employees_from_staff_list(path)
        except Exception as e:
            logger.exception('Staff seed from bundled file failed')
            return error_response(f'Seed failed: {e}', status_code=400)
        return success_response(result)

    @hr_bp.route('/api/leave-tracker/meta', methods=['GET'])
    @jwt_required()
    def api_leave_meta():
        user, err = _require_leave_user()
        if err:
            return err
        count = LeaveEmployee.query.filter_by(active=True).count()
        return success_response({
            'year': LEAVE_TRACKER_YEAR,
            'months': list(LEAVE_TRACKER_MONTHS),
            'month_labels': {str(k): v for k, v in LEAVE_TRACKER_MONTH_LABELS.items()},
            'sick_entitlement': LEAVE_SICK_ENTITLEMENT,
            'companies': list(LEAVE_COMPANIES),
            'employee_count': count,
            'has_bundled_staff_list': os.path.isfile(STAFF_LIST_BUNDLED),
            'periods': _read_periods(),
            'window_start': LEAVE_WINDOW_START.isoformat(),
            'window_end': LEAVE_WINDOW_END.isoformat(),
        })

    @hr_bp.route('/api/leave-tracker/periods', methods=['GET', 'PUT'])
    @jwt_required()
    def api_leave_periods():
        user, err = _require_leave_user()
        if err:
            return err
        if request.method == 'GET':
            return success_response({'periods': _read_periods()})
        data = request.get_json(silent=True) or {}
        periods = _write_periods(data.get('periods') or data)
        return success_response({'periods': periods})

    # ── Analytics section pages ─────────────────────────────────────────────

    def _active_employees_for_company(company: str = 'all') -> list[LeaveEmployee]:
        query = LeaveEmployee.query.filter_by(active=True).options(
            joinedload(LeaveEmployee.usage),
        )
        if company and company != 'all':
            query = query.filter(LeaveEmployee.company.in_(leave_company_db_values(company)))
        return query.order_by(
            LeaveEmployee.company.asc(),
            LeaveEmployee.full_name.asc(),
        ).all()

    @hr_bp.route('/leave-tracker/repeat-sick')
    @jwt_required()
    def leave_tracker_repeat_sick():
        user = _get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user_can_manage_leave_tracker(user):
            return jsonify({'error': 'Access denied'}), 403
        _ensure_migrated()
        return render_template(
            'hr_leave_tracker_repeat_sick.html',
            user=user,
            hiring_active='leave_repeat_sick',
        )

    @hr_bp.route('/leave-tracker/sick-trends')
    @jwt_required()
    def leave_tracker_sick_trends():
        user = _get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user_can_manage_leave_tracker(user):
            return jsonify({'error': 'Access denied'}), 403
        _ensure_migrated()
        return render_template(
            'hr_leave_tracker_sick_trends.html',
            user=user,
            hiring_active='leave_sick_trends',
        )

    @hr_bp.route('/api/leave-tracker/analytics/repeat-sick', methods=['GET'])
    @jwt_required()
    def api_leave_analytics_repeat_sick():
        user, err = _require_leave_user()
        if err:
            return err
        _ensure_migrated()
        company = (request.args.get('company') or 'all').strip()
        month, date_from, date_to = _parse_analytics_filters()
        employees = _active_employees_for_company(company)
        rows = _build_repeat_sick_rows(
            employees, month=month, date_from=date_from, date_to=date_to,
        )
        return success_response({
            'rows': rows,
            'count': len({r['employee_id'] for r in rows}),
            'year': LEAVE_TRACKER_YEAR,
            'months': list(LEAVE_TRACKER_MONTHS),
            'month_labels': {str(k): v for k, v in LEAVE_TRACKER_MONTH_LABELS.items()},
            'companies': list(LEAVE_COMPANIES),
            'filters': {
                'company': company,
                'month': month,
                'date_from': date_from.isoformat() if date_from else None,
                'date_to': date_to.isoformat() if date_to else None,
            },
        })

    @hr_bp.route('/api/leave-tracker/analytics/sick-trends', methods=['GET'])
    @jwt_required()
    def api_leave_analytics_sick_trends():
        user, err = _require_leave_user()
        if err:
            return err
        _ensure_migrated()
        company = (request.args.get('company') or 'all').strip()
        month, date_from, date_to = _parse_analytics_filters()
        employees = _active_employees_for_company(company)
        rows = _build_sick_trends_rows(
            employees, month=month, date_from=date_from, date_to=date_to,
        )
        rising = sum(1 for r in rows if r.get('trend') == 'rising')
        year, focus_month = _tracker_focus_month()
        if month is not None:
            focus_month = month
        return success_response({
            'rows': rows,
            'count': len(rows),
            'rising_count': rising,
            'current_month': focus_month,
            'current_month_label': LEAVE_TRACKER_MONTH_LABELS.get(focus_month, ''),
            'year': LEAVE_TRACKER_YEAR,
            'months': list(LEAVE_TRACKER_MONTHS),
            'month_labels': {str(k): v for k, v in LEAVE_TRACKER_MONTH_LABELS.items()},
            'companies': list(LEAVE_COMPANIES),
            'filters': {
                'company': company,
                'month': month,
                'date_from': date_from.isoformat() if date_from else None,
                'date_to': date_to.isoformat() if date_to else None,
            },
        })
