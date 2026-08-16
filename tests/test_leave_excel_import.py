"""Regression: Leave Log import must not double-count or ingest template examples."""
from datetime import date
from io import BytesIO

from werkzeug.datastructures import FileStorage


def _file_storage(buf: BytesIO, name: str = 'leave.xlsx') -> FileStorage:
    return FileStorage(stream=BytesIO(buf.getvalue()), filename=name)


def test_leave_log_export_reimport_is_idempotent(app):
    from app.models import (
        LEAVE_TRACKER_YEAR,
        LeaveEmployee,
        LeaveLog,
        LeaveMonthlyUsage,
        db,
        recompute_monthly_usage,
    )
    from module_hr.leave_excel import build_leave_workbook, import_leave_workbook

    with app.app_context():
        emp = LeaveEmployee(
            emp_id='E100',
            full_name='Idempotent Emp',
            designation='Tech',
            company='INJAAZ',
            annual_entitlement=30,
            active=True,
        )
        db.session.add(emp)
        db.session.flush()
        db.session.add(
            LeaveLog(
                employee_id=emp.id,
                leave_type='sick',
                leave_date=date(LEAVE_TRACKER_YEAR, 8, 10),
                days=1.0,
                notes='real sick day',
            )
        )
        db.session.commit()
        recompute_monthly_usage(emp.id, 'sick', LEAVE_TRACKER_YEAR, 8)
        db.session.commit()

        usage_before = LeaveMonthlyUsage.query.filter_by(
            employee_id=emp.id, leave_type='sick', year=LEAVE_TRACKER_YEAR, month=8,
        ).one()
        assert usage_before.days == 1.0
        assert LeaveLog.query.filter_by(employee_id=emp.id).count() == 1

        buf = build_leave_workbook([emp], [], LeaveLog.query.all())
        result = import_leave_workbook(_file_storage(buf))

        assert result['logs_created'] == 0
        assert result['logs_skipped'] >= 1
        assert LeaveLog.query.filter_by(employee_id=emp.id).count() == 1
        usage_after = LeaveMonthlyUsage.query.filter_by(
            employee_id=emp.id, leave_type='sick', year=LEAVE_TRACKER_YEAR, month=8,
        ).one()
        assert usage_after.days == 1.0


def test_leave_log_template_example_row_not_imported(app):
    from app.models import LEAVE_TRACKER_YEAR, LeaveEmployee, LeaveLog, db
    from module_hr.leave_excel import build_leave_log_template_bytes, import_leave_workbook

    with app.app_context():
        emp = LeaveEmployee(
            emp_id='170',
            full_name='Seed Emp',
            designation='Tech',
            company='INJAAZ',
            annual_entitlement=30,
            active=True,
        )
        db.session.add(emp)
        db.session.commit()

        result = import_leave_workbook(
            _file_storage(build_leave_log_template_bytes(), 'template.xlsx')
        )
        assert result['logs_created'] == 0
        assert result['logs_skipped'] >= 1
        assert LeaveLog.query.filter_by(employee_id=emp.id).count() == 0
        assert (
            LeaveLog.query.filter_by(
                employee_id=emp.id,
                leave_date=date(LEAVE_TRACKER_YEAR, 8, 3),
            ).count()
            == 0
        )


def test_leave_log_import_still_adds_new_rows(app):
    from app.models import LEAVE_TRACKER_YEAR, LeaveEmployee, LeaveLog, db
    from module_hr.leave_excel import import_leave_workbook
    from openpyxl import Workbook

    with app.app_context():
        emp = LeaveEmployee(
            emp_id='E200',
            full_name='New Leave Emp',
            designation='Tech',
            company='INJAAZ',
            annual_entitlement=30,
            active=True,
        )
        db.session.add(emp)
        db.session.commit()

        wb = Workbook()
        ws = wb.active
        ws.title = 'Leave Log'
        ws.append([
            'SN', 'Emp ID', 'Employee Name', 'Designation', 'Company', 'Project',
            'Leave Type', 'Start Date', 'End Date', 'No. of Days',
            'Reason / Notes', 'Approved', 'Month',
        ])
        ws.append([
            1, 'E200', 'New Leave Emp', 'Tech', 'INJAAZ', '',
            'Annual', date(LEAVE_TRACKER_YEAR, 9, 1), date(LEAVE_TRACKER_YEAR, 9, 2),
            2, 'vacation', 'Yes', 'September 2026',
        ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        result = import_leave_workbook(_file_storage(buf))
        assert result['logs_created'] == 1
        assert LeaveLog.query.filter_by(employee_id=emp.id, leave_type='annual').count() == 1
