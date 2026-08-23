"""Build HR form HTML for printing - matches HR Documents format"""
import html
from datetime import datetime


def _esc(s):
    if s is None or s == '':
        return '-'
    return html.escape(str(s))


def _fmt_date(v):
    if not v:
        return '-'
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return str(v)


def _row(label, value):
    if isinstance(value, str) and value.startswith('data:image'):
        val = f'<span class="doc-sig-wrap"><img src="{value}" class="doc-sig-img" alt="Signature"></span>'
    else:
        val = _esc(value)
    return f'<tr><td class="label">{_esc(label)}</td><td>{val}</td></tr>'


def _sig_row(label, value):
    if value and isinstance(value, str) and value.startswith('data:image'):
        return (
            f'<tr><td class="label">{_esc(label)}</td>'
            f'<td><span class="doc-sig-wrap"><img src="{value}" class="doc-sig-img" alt="Signature"></span></td></tr>'
        )
    return _row(label, value or '-')


def render_leave_print(fd):
    """Render Leave Application in HR Document format - two columns, matching reference form"""
    leave_labels = {
        'annual': 'Annual Leave', 'sick': 'Sick Leave',
        'ot_compensatory': 'OT Compensatory Off', 'unpaid': 'Unpaid Leave',
        'compassionate': 'Compassionate Leave', 'study': 'Study Leave',
        'examination': 'Examination Leave (UAE Nationals)', 'hajj': 'Hajj Leave',
        'other': 'Other'
    }
    leave_type = leave_labels.get(fd.get('leave_type'), fd.get('leave_type') or '-')
    if fd.get('leave_type') == 'other' and fd.get('leave_type_other'):
        leave_type += ' - ' + _esc(fd.get('leave_type_other'))
    salary = fd.get('salary_advance')
    salary_str = 'YES' if salary == 'yes' else 'NO' if salary == 'no' else '-'
    # Column 1: Employee Details (matches HR Document)
    emp_rows = [
        _row('Name', fd.get('employee_name')),
        _row('Job Title', fd.get('job_title')),
        _row('Employee ID', fd.get('employee_id')),
        _row('Date of Joining', _fmt_date(fd.get('date_of_joining'))),
        _row('Last Leave Date', _fmt_date(fd.get('last_leave_date'))),
        _row("Today's Date", _fmt_date(fd.get('today_date'))),
        _row('Department', fd.get('department')),
        _row('Mobile No.', fd.get('mobile_no')),
    ]
    # Column 2: Details of Leave (matches HR Document)
    leave_rows = [
        f'<tr><td class="label">Type of Leave</td><td>{leave_type}</td></tr>',
        _row('No. of Days', fd.get('number_of_days')),
        _row('Total No. of Days Requested', fd.get('total_days_requested')),
        _row('First Day of Leave', _fmt_date(fd.get('first_day_of_leave'))),
        _row('Last Day of Leave', _fmt_date(fd.get('last_day_of_leave'))),
        _row('Date Returning to Work', _fmt_date(fd.get('date_returning_to_work'))),
        _row('Leave Salary Advance', salary_str),
        _row('Telephone (reachable)', fd.get('telephone_reachable')),
        _row('Replacement Name', fd.get('replacement_name')),
        _sig_row('Employee Signature', fd.get('employee_signature')),
    ]
    # HR section (full width, matches "For Human Resources Only")
    hr_rows = [
        _row('Checked by HR', fd.get('hr_checked')),
        _row('HR Comments', fd.get('hr_comments')),
        _row('Balance C/F', fd.get('hr_balance_cf')),
        _row('Contract Year', fd.get('hr_contract_year')),
        _row('Paid', fd.get('hr_paid')),
        _row('Unpaid', fd.get('hr_unpaid')),
        _sig_row('HR Signature', fd.get('hr_signature')),
        _sig_row('GM Signature', fd.get('gm_signature')),
    ]
    return (
        '<div class="doc-form-grid doc-form-grid--leave">'
        '<div class="doc-panel">'
        '<div class="doc-section-title">Employee Details</div>'
        '<table class="doc-table">' + ''.join(emp_rows) + '</table>'
        '</div>'
        '<div class="doc-panel">'
        '<div class="doc-section-title">Details of Leave</div>'
        '<table class="doc-table">' + ''.join(leave_rows) + '</table>'
        '</div>'
        '</div>'
        '<div class="doc-panel doc-panel--hr">'
        '<div class="doc-section-title doc-section-title--hr">For Human Resources Only</div>'
        '<table class="doc-table">' + ''.join(hr_rows) + '</table>'
        '</div>'
    )


def render_generic_print(fd, skip_keys=None):
    skip = set(skip_keys or []) | {'submitted_by_id', 'submitted_by_name', 'submitted_at', 'form_type'}
    rows = []
    for k, v in (fd or {}).items():
        if any(s in k for s in skip) or k.startswith('hr_') or k.startswith('gm_'):
            continue
        if v is None or v == '':
            continue
        label = k.replace('_', ' ').title()
        if isinstance(v, str) and v.startswith('data:image'):
            rows.append(_sig_row(label, v))
        elif 'date' in k.lower():
            rows.append(_row(label, _fmt_date(v)))
        else:
            rows.append(_row(label, v))
    return '<table class="doc-table">' + ''.join(rows) + '</table>' if rows else '<p>No data</p>'


def render_form_for_print(module_type, form_data, submission_id):
    """Build form HTML in HR document format for printing"""
    from module_hr.form_data_normalize import normalize_hr_form_data_for_view

    fd = normalize_hr_form_data_for_view(form_data or {}, module_type)
    form_type = (module_type or '').replace('hr_', '')
    
    if form_type in ('leave_application', 'leave'):
        body = render_leave_print(fd)
    elif form_type == 'grievance':
        loc = {'camp': 'Camp', 'site': 'Site', 'head_office': 'Head Office'}
        loc_val = loc.get(fd.get('issue_location'), fd.get('issue_location')) if fd.get('issue_location') else '-'
        rows = [
            _row('Complainant Name', fd.get('complainant_name')),
            _row('Employee ID', fd.get('complainant_id')),
            _row('Designation', fd.get('complainant_designation')),
            _row('Date of Incident', _fmt_date(fd.get('date_of_incident'))),
            _row('Description', fd.get('complaint_description')),
            _sig_row('Complainant Signature', fd.get('complainant_signature')),
        ]
        body = '<div class="doc-section-title">Complaint</div><table class="doc-table">' + ''.join(rows) + '</table>'
    elif form_type == 'passport_release':
        rows = [
            _row('Requester', fd.get('requester')),
            _row('Employee Name', fd.get('employee_name')),
            _row('Employee ID', fd.get('employee_id')),
            _row('Job Title', fd.get('job_title')),
            _sig_row('Employee Signature', fd.get('employee_signature')),
        ]
        body = '<div class="doc-section-title">Passport Release</div><table class="doc-table">' + ''.join(rows) + '</table>'
    elif form_type == 'duty_resumption':
        rows = [
            _row('Requester', fd.get('requester')),
            _row('Employee Name', fd.get('employee_name')),
            _row('Employee ID', fd.get('employee_id')),
            _row('Leave Started', _fmt_date(fd.get('leave_started'))),
            _row('Actual Resumption', _fmt_date(fd.get('actual_resumption_date'))),
            _sig_row('Employee Signature', fd.get('employee_signature')),
            _sig_row('Reporting Manager Signature', fd.get('reporting_manager_signature')),
            _sig_row('GM Signature', fd.get('gm_signature')),
            _sig_row('HR Signature', fd.get('hr_signature')),
        ]
        body = '<div class="doc-section-title">Duty Resumption</div><table class="doc-table">' + ''.join(rows) + '</table>'
    else:
        body = render_generic_print(fd)
        body = f'<div class="doc-form-grid form-single"><div class="doc-form-col">{body}</div></div>'
    return body
