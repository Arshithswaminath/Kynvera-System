"""
Workflow email notifications — uses the same send_email() path as the MMR daily report.

Every approval stage for both Inspection and HR forms triggers an email to the
recipients configured in the admin Notification Settings panel.

Subject lines and body copy are intentionally left as clear placeholders
so they can be finalised without touching code.
"""
from __future__ import annotations
from flask import current_app
from app.models import User, db
from common.email_service import branded_details_html, branded_kynvera_html, send_email
from html import escape as html_escape


# ─── Display helpers ──────────────────────────────────────────────────────────

def _module_display(module_type: str | None) -> str:
    return {
        'hvac_mep':  'HVAC & MEP',
        'civil':     'Civil Works',
        'cleaning':  'Cleaning Services',
    }.get(module_type or '', module_type or 'Form')


def _hr_form_display(module_type: str | None) -> str:
    return {
        'hr_leave_application':    'Leave Application',
        'hr_commencement':         'Commencement Form',
        'hr_duty_resumption':      'Duty Resumption',
        'hr_contract_renewal':     'Contract Renewal Assessment',
        'hr_performance_evaluation': 'Performance Evaluation',
        'hr_grievance':            'Grievance / Disciplinary',
        'hr_interview_assessment': 'Interview Assessment',
        'hr_passport_release':     'Passport Release & Submission',
        'hr_staff_appraisal':      'Staff Appraisal',
        'hr_station_clearance':    'Station Clearance',
        'hr_visa_renewal':         'Visa Renewal',
    }.get(module_type or '', 'HR Form')


# ─── Config / recipient helpers ───────────────────────────────────────────────

def _load_notification_config() -> dict:
    """Load notification config from DB, falling back to empty dict."""
    try:
        from app.models import NotificationConfig
        row = NotificationConfig.query.first()
        if row and row.config_json:
            return row.config_json
    except Exception as exc:
        current_app.logger.warning("Could not load notification config: %s", exc)
    return {}


def _get_recipients(module: str, submitter_email: str | None) -> tuple[list, list]:
    """Return (to_list, cc_list) from admin config for *module* ('inspection' or 'hr')."""
    cfg = _load_notification_config().get(module, {})
    to_list = list(cfg.get('to') or [])
    cc_list = list(cfg.get('cc') or [])
    if cfg.get('include_submitter', True) and submitter_email:
        email_lower = submitter_email.strip().lower()
        if email_lower not in [e.lower() for e in to_list]:
            to_list.append(submitter_email)
    return to_list, cc_list


def _submitter_email(submission) -> str | None:
    try:
        uid = getattr(submission, 'user_id', None)
        if uid:
            u = db.session.get(User, uid)
            return u.email if u and u.email else None
    except Exception:
        pass
    return None


# ─── HTML email builder ───────────────────────────────────────────────────────

def _html_email(
    *,
    title: str,
    status_label: str,
    status_type: str = 'pending',
    rows: list[tuple[str, str]],
    cta_url: str = '',
    cta_label: str = 'Open in Kynvera',
) -> str:
    """Kynvera transactional card — same layout as auth / HR lifecycle mail."""
    del status_type
    detail_rows = [('Status', status_label)] + list(rows or [])
    return branded_kynvera_html(
        greeting=html_escape(title),
        paragraphs=[],
        extra_html=branded_details_html(detail_rows),
        cta_url=cta_url,
        cta_label=cta_label,
    )


def _plain_text(title: str, rows: list[tuple[str, str]], cta_url: str = '') -> str:
    lines = [title, '=' * len(title), '']
    for label, value in rows:
        lines.append(f'{label}: {value}')
    if cta_url:
        lines += ['', f'Open here: {cta_url}']
    lines += ['', 'Kynvera Team']
    return '\n'.join(lines)


def _base_url() -> str:
    return (current_app.config.get('APP_BASE_URL') or '').rstrip('/')


# ─── Generic dispatcher ───────────────────────────────────────────────────────

def _send(
    *,
    module: str,                  # 'inspection' or 'hr'
    submission,
    subject: str,
    title: str,
    status_label: str,
    status_type: str,
    rows: list[tuple[str, str]],
    cta_url: str = '',
    cta_label: str = 'Open in Kynvera',
) -> bool:
    """
    Resolve recipients from admin config then send via the same send_email()
    path used by the MMR daily report (Mailjet / SMTP).
    """
    try:
        sub_email = _submitter_email(submission)
        to_list, cc_list = _get_recipients(module, sub_email)
        if not to_list:
            current_app.logger.warning(
                "Workflow notification skipped — no recipients configured for module '%s'", module
            )
            return False

        html_body = _html_email(
            title=title,
            status_label=status_label,
            status_type=status_type,
            rows=rows,
            cta_url=cta_url,
            cta_label=cta_label,
        )
        plain = _plain_text(title, rows, cta_url)

        ok = send_email(
            recipient=to_list,
            subject=subject,
            body=plain,
            html_body=html_body,
            cc=cc_list or None,
            source=module if module in ('inspection', 'hr') else 'other',
            related_id=getattr(submission, 'submission_id', None),
        )
        if not ok:
            current_app.logger.warning(
                "send_email returned False for module '%s' stage '%s'", module, title
            )
        return bool(ok)
    except Exception as exc:
        current_app.logger.error(
            "Workflow notification error (%s / %s): %s", module, title, exc, exc_info=True
        )
        return False


# ─── Inspection form notifications ───────────────────────────────────────────

def send_inspection_submitted(submission, submitter) -> bool:
    """Stage 0 — Supervisor submits the inspection form."""
    module_name = _module_display(getattr(submission, 'module_type', None))
    sid = getattr(submission, 'submission_id', '')
    site = getattr(submission, 'site_name', '') or 'N/A'
    visit = getattr(submission, 'visit_date', None)
    visit_str = visit.strftime('%d %b %Y') if visit else 'N/A'
    actor = getattr(submitter, 'full_name', None) or getattr(submitter, 'username', '') or 'Supervisor'
    cta = f"{_base_url()}/workflow/pending-reviews"

    return _send(
        module='inspection',
        submission=submission,
        subject=f"[Kynvera] {module_name} — New Submission",
        title=f"New {module_name} Form Submitted",
        status_label='New Submission',
        status_type='submitted',
        rows=[
            ('Module',        module_name),
            ('Submission ID', sid),
            ('Site / Project', site),
            ('Visit Date',    visit_str),
            ('Submitted By',  actor),
            ('Next Step',     'Pending Operations Manager review'),
        ],
        cta_url=cta,
        cta_label='Review Submission',
    )


def send_team_notification(submission, action_user, action_label: str) -> bool:
    """
    General-purpose inspection stage notification (Supervisor re-sign, OM, BD,
    Procurement, GM). Called from app/workflow/routes.py at every approval point.
    """
    module_name = _module_display(getattr(submission, 'module_type', None))
    sid = getattr(submission, 'submission_id', '')
    site = getattr(submission, 'site_name', '') or 'N/A'
    visit = getattr(submission, 'visit_date', None)
    visit_str = visit.strftime('%d %b %Y') if visit else 'N/A'
    actor_name = getattr(action_user, 'full_name', None) or getattr(action_user, 'username', '') or 'User'
    actor_role = getattr(action_user, 'designation', None) or getattr(action_user, 'role', '') or 'User'
    cta = f"{_base_url()}/workflow/pending-reviews"

    # Determine status colouring from label
    label_lower = action_label.lower()
    if 'complet' in label_lower or 'general manager' in label_lower:
        status_type, status_label = 'completed', 'Completed'
    else:
        status_type, status_label = 'signed', 'Signed'

    return _send(
        module='inspection',
        submission=submission,
        subject=f"[Kynvera] {module_name} — {action_label}",
        title=action_label,
        status_label=status_label,
        status_type=status_type,
        rows=[
            ('Module',        module_name),
            ('Submission ID', sid),
            ('Site / Project', site),
            ('Visit Date',    visit_str),
            ('Signed By',     f'{actor_name} ({actor_role})'),
        ],
        cta_url=cta,
        cta_label='Open Pending Reviews',
    )


# ─── HR form notifications ────────────────────────────────────────────────────

def _hr_rows(submission, extra: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    module_type = getattr(submission, 'module_type', None)
    form_data = getattr(submission, 'form_data', {}) or {}
    employee = (
        form_data.get('employee_name')
        or form_data.get('complainant_name')
        or form_data.get('requester')
        or 'Employee'
    )
    rows = [
        ('Form Type',     _hr_form_display(module_type)),
        ('Submission ID', getattr(submission, 'submission_id', '')),
        ('Employee',      employee),
    ]
    if extra:
        rows.extend(extra)
    return rows


def send_hr_submitted(submission, submitter) -> bool:
    """Stage 0 — Employee submits an HR form."""
    actor = getattr(submitter, 'full_name', None) or getattr(submitter, 'username', '') or 'Employee'
    form_name = _hr_form_display(getattr(submission, 'module_type', None))
    cta = f"{_base_url()}/hr/pending-review"

    return _send(
        module='hr',
        submission=submission,
        subject=f"[Kynvera HR] {form_name} — New Submission",
        title=f"New {form_name} Submitted",
        status_label='Submitted',
        status_type='submitted',
        rows=_hr_rows(submission, [
            ('Submitted By', actor),
            ('Next Step',    'Pending HR Manager review'),
        ]),
        cta_url=cta,
        cta_label='Review HR Request',
    )


def send_hr_notification(submission, action_user, action_label: str) -> bool:
    """HR approval / GM final approval stage notification."""
    actor_name = getattr(action_user, 'full_name', None) or getattr(action_user, 'username', '') or 'User'
    actor_role = getattr(action_user, 'designation', None) or getattr(action_user, 'role', '') or 'User'
    form_name = _hr_form_display(getattr(submission, 'module_type', None))
    cta = f"{_base_url()}/hr/pending-review"

    label_lower = action_label.lower()
    if 'complet' in label_lower or 'gm final' in label_lower or 'approved' in label_lower:
        status_type, status_label = 'approved', 'Approved'
    else:
        status_type, status_label = 'pending', 'Pending GM'

    return _send(
        module='hr',
        submission=submission,
        subject=f"[Kynvera HR] {form_name} — {action_label}",
        title=action_label,
        status_label=status_label,
        status_type=status_type,
        rows=_hr_rows(submission, [
            ('Action By', f'{actor_name} ({actor_role})'),
        ]),
        cta_url=cta,
        cta_label='View HR Request',
    )


def send_hr_rejected(submission, rejected_by, reason: str = '') -> bool:
    """HR rejected or GM rejected — notify configured HR recipients."""
    actor_name = getattr(rejected_by, 'full_name', None) or getattr(rejected_by, 'username', '') or 'User'
    actor_role = getattr(rejected_by, 'designation', None) or getattr(rejected_by, 'role', '') or 'User'
    form_name = _hr_form_display(getattr(submission, 'module_type', None))
    cta = f"{_base_url()}/hr/pending-review"

    return _send(
        module='hr',
        submission=submission,
        subject=f"[Kynvera HR] {form_name} — Rejected",
        title=f"{form_name} — Rejected",
        status_label='Rejected',
        status_type='rejected',
        rows=_hr_rows(submission, [
            ('Rejected By', f'{actor_name} ({actor_role})'),
            ('Reason',      reason or 'No reason provided'),
        ]),
        cta_url=cta,
        cta_label='View HR Request',
    )
