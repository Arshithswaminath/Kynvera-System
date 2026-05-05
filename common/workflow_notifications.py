"""
Workflow email notifications — uses the same send_email() path as the MMR daily report.

Every approval stage for both Inspection and HR forms triggers an email to the
recipients configured in the admin Notification Settings panel.

Subject lines and body copy are intentionally left as clear placeholders
so they can be finalised without touching code.
"""
from __future__ import annotations
from datetime import datetime
from flask import current_app
from app.models import User, db
from common.email_service import send_email


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

_STATUS_COLOUR = {
    'submitted':    '#2563eb',
    'approved':     '#16a34a',
    'completed':    '#16a34a',
    'rejected':     '#dc2626',
    'pending':      '#d97706',
    'signed':       '#7c3aed',
}


def _html_email(
    *,
    title: str,
    status_label: str,
    status_type: str = 'pending',
    rows: list[tuple[str, str]],
    cta_url: str = '',
    cta_label: str = 'Open in Injaaz',
) -> str:
    """
    Outlook-safe HTML email (table-based layout, VML button, bgcolor attributes).
    Tested against Outlook 2007/2010/2013/2016 Word rendering engine.
    """
    accent = _STATUS_COLOUR.get(status_type, '#125435')
    now_str = datetime.now().strftime('%d %b %Y, %H:%M')

    # Details rows — alternating row shading works in all Outlook versions
    rows_html = ''
    for i, (label, value) in enumerate(rows):
        bg = ' bgcolor="#f8fafc"' if i % 2 == 0 else ''
        rows_html += (
            f'<tr{bg}>'
            f'<td width="160" valign="top" style="padding:8px 12px 8px 0;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:13px;color:#64748b;border-bottom:1px solid #e2e8f0;">{label}</td>'
            f'<td valign="top" style="padding:8px 0;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:13px;color:#1e293b;font-weight:bold;border-bottom:1px solid #e2e8f0;">{value}</td>'
            f'</tr>'
        )

    # CTA button — VML rectangle so it renders in Outlook, plain <a> for everyone else
    cta_html = ''
    if cta_url:
        cta_html = f'''
<tr>
  <td align="left" style="padding:24px 32px 0 32px;">
    <!--[if mso]>
    <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"
                 xmlns:w="urn:schemas-microsoft-com:office:word"
                 href="{cta_url}"
                 style="height:38px;v-text-anchor:middle;width:200px;"
                 arcsize="8%"
                 strokecolor="{accent}"
                 fillcolor="{accent}">
      <w:anchorlock/>
      <center style="color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:bold;">{cta_label}</center>
    </v:roundrect>
    <![endif]-->
    <!--[if !mso]><!-->
    <table cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td align="center" bgcolor="{accent}" style="padding:0;">
          <a href="{cta_url}"
             style="display:inline-block;background-color:{accent};color:#ffffff;
                    font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:bold;
                    text-decoration:none;padding:10px 24px;border:1px solid {accent};">
            {cta_label}
          </a>
        </td>
      </tr>
    </table>
    <!--<![endif]-->
  </td>
</tr>'''

    return f'''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!--[if gte mso 9]>
  <xml>
    <o:OfficeDocumentSettings>
      <o:AllowPNG/>
      <o:PixelsPerInch>96</o:PixelsPerInch>
    </o:OfficeDocumentSettings>
  </xml>
  <![endif]-->
  <style type="text/css">
    body, table, td {{ font-family: Arial, Helvetica, sans-serif; }}
    img {{ border: 0; display: block; }}
    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;" bgcolor="#f1f5f9">

<!--[if mso]><table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center"><![endif]-->
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f1f5f9"
       style="background-color:#f1f5f9;">
  <tr>
    <td align="center" valign="top" style="padding:32px 16px;">

      <!-- Email card — 600px wide -->
      <table width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff"
             style="background-color:#ffffff;width:600px;max-width:600px;border:1px solid #e2e8f0;">

        <!-- ── Header ── -->
        <tr>
          <td bgcolor="#125435" style="background-color:#125435;padding:18px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;
                           color:#ffffff;letter-spacing:-0.5px;">Injaaz</td>
                <td align="right" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;
                           color:#a7f3c4;">Workflow Notification</td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ── Status badge ── -->
        <tr>
          <td style="padding:24px 32px 0 32px;">
            <table cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td bgcolor="{accent}" style="background-color:{accent};padding:4px 12px;">
                  <span style="font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:bold;
                               color:#ffffff;text-transform:uppercase;letter-spacing:1px;">{status_label}</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ── Title ── -->
        <tr>
          <td style="padding:12px 32px 0 32px;">
            <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;
                      color:#0f172a;line-height:1.4;">{title}</p>
          </td>
        </tr>

        <!-- ── Divider ── -->
        <tr>
          <td style="padding:16px 32px 0 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td height="1" bgcolor="#e2e8f0" style="background-color:#e2e8f0;font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
          </td>
        </tr>

        <!-- ── Details table ── -->
        <tr>
          <td style="padding:8px 32px 0 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {rows_html}
            </table>
          </td>
        </tr>

        <!-- ── CTA button ── -->
        {cta_html}

        <!-- ── Bottom divider ── -->
        <tr>
          <td style="padding:24px 32px 0 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td height="1" bgcolor="#e2e8f0" style="background-color:#e2e8f0;font-size:0;line-height:0;">&nbsp;</td></tr>
            </table>
          </td>
        </tr>

        <!-- ── Footer ── -->
        <tr>
          <td bgcolor="#f8fafc" style="background-color:#f8fafc;padding:16px 32px 20px 32px;">
            <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#94a3b8;line-height:1.6;">
              Sent automatically by <strong style="color:#64748b;">Injaaz Workflow</strong> on {now_str}.<br>
              Do not reply to this email.
            </p>
          </td>
        </tr>

      </table>
      <!-- /Email card -->

    </td>
  </tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->

</body>
</html>'''


def _plain_text(title: str, rows: list[tuple[str, str]], cta_url: str = '') -> str:
    lines = [title, '=' * len(title), '']
    for label, value in rows:
        lines.append(f'{label}: {value}')
    if cta_url:
        lines += ['', f'Open here: {cta_url}']
    lines += ['', 'Injaaz Team']
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
    cta_label: str = 'Open in Injaaz',
) -> bool:
    """
    Resolve recipients from admin config then send via the same send_email()
    path used by the MMR daily report (Brevo / Mailjet / SMTP).
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
        subject=f"[Injaaz] {module_name} — New Submission",
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
        subject=f"[Injaaz] {module_name} — {action_label}",
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
        subject=f"[Injaaz HR] {form_name} — New Submission",
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
        subject=f"[Injaaz HR] {form_name} — {action_label}",
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
        subject=f"[Injaaz HR] {form_name} — Rejected",
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
