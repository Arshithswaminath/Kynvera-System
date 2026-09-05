"""
Branded HR form emails: submitter confirmation, next-signer action, and progress updates.

In-app notifications stay in hr_management_chain / routes; this module only sends mail.
"""
from __future__ import annotations

from html import escape as html_escape

from flask import Flask, has_request_context, request

from app.models import User, Submission, db
from common.email_service import branded_kynvera_html, is_email_configured, send_email


FORM_TITLES = {
    "hr_leave_application": "Leave Application",
    "hr_commencement": "Commencement Form",
    "hr_duty_resumption": "Duty Resumption",
    "hr_contract_renewal": "Contract Renewal Assessment",
    "hr_performance_evaluation": "Performance Evaluation",
    "hr_grievance": "Grievance / Disciplinary",
    "hr_interview_assessment": "Interview Assessment",
    "hr_passport_release": "Passport Release",
    "hr_staff_appraisal": "Staff Appraisal",
    "hr_station_clearance": "Station Clearance",
    "hr_visa_renewal": "Visa Renewal",
    "hr_asset_handover": "Asset Handover & Takeover",
    "hr_termination": "Termination",
    "hr_long_vacation": "Long Vacation",
}


def form_title(submission: Submission) -> str:
    mt = getattr(submission, "module_type", None) or ""
    if mt in FORM_TITLES:
        return FORM_TITLES[mt]
    return mt.replace("hr_", "").replace("_", " ").title() or "HR Form"


def employee_name(submission: Submission) -> str:
    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    return (
        fd.get("employee_name")
        or fd.get("complainant_name")
        or fd.get("candidate_name")
        or fd.get("requester")
        or fd.get("submitted_by_name")
        or "Employee"
    )


def _base_url(app: Flask) -> str:
    if has_request_context():
        try:
            root = (request.url_root or "").rstrip("/")
            if root:
                return root
        except Exception:
            pass
    return (app.config.get("APP_BASE_URL") or "http://localhost:5002").rstrip("/")


def my_request_url(app: Flask, submission: Submission) -> str:
    return f"{_base_url(app)}/hr/my-requests?submission={submission.submission_id}"


def pending_review_url(app: Flask) -> str:
    return f"{_base_url(app)}/hr/pending-review"


def mgmt_sign_url(app: Flask, submission: Submission) -> str:
    return f"{_base_url(app)}/hr/mgmt-sign/{submission.submission_id}"


def replacement_sign_url(app: Flask, submission: Submission) -> str:
    return f"{_base_url(app)}/hr/replacement-sign/{submission.submission_id}"


def current_step_label(submission: Submission) -> str:
    from module_hr.hr_management_chain import MGMT_CHAIN_KEY, current_step, has_management_chain

    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    if has_management_chain(fd):
        step = current_step(fd[MGMT_CHAIN_KEY])
        if step:
            return str(step.get("pdf_label") or step.get("who_label") or "Approver")
    wf = (submission.workflow_status or "").strip()
    if wf == "replacement_signoff":
        return "Colleague signature"
    if wf == "hr_review":
        return "HR review"
    if wf == "gm_review":
        return "General Manager"
    return wf.replace("_", " ").title() or "Review"


def _details_html(rows: list[tuple[str, str]]) -> str:
    cells = []
    for label, value in rows:
        cells.append(
            "<tr>"
            f'<td style="padding:7px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;'
            f'letter-spacing:.04em;text-transform:uppercase;color:#8a7e78;width:38%;">{html_escape(label)}</td>'
            f'<td style="padding:7px 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;'
            f'font-weight:600;color:#191b23;">{html_escape(value)}</td>'
            "</tr>"
        )
    return (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:8px 0 16px 0;background-color:#fff8f5;border:1px solid #fde4d8;'
        'border-radius:12px;"><tr><td style="padding:14px 16px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{"".join(cells)}</table>'
        "</td></tr></table>"
    )


def _send(
    app: Flask,
    recipient: User | None,
    *,
    subject: str,
    greeting: str,
    paragraphs: list[str],
    rows: list[tuple[str, str]],
    cta_url: str,
    cta_label: str,
    related_id: str | None,
) -> bool:
    if not recipient or not getattr(recipient, "email", None):
        return False
    if not is_email_configured(app):
        app.logger.info("HR lifecycle email skipped (email not configured) to %s", recipient.email)
        return False
    name = recipient.full_name or recipient.username or "there"
    greeting_line = greeting.replace("{name}", name)
    plain_lines = [greeting_line, ""] + [p.replace("<strong>", "").replace("</strong>", "") for p in paragraphs] + [""]
    for label, value in rows:
        plain_lines.append(f"{label}: {value}")
    if cta_url:
        plain_lines += ["", cta_label + ":", cta_url]
    plain_lines += ["", "Kynvera"]
    html = branded_kynvera_html(
        greeting=greeting_line,
        paragraphs=paragraphs,
        extra_html=_details_html(rows),
        cta_url=cta_url,
        cta_label=cta_label,
    )
    try:
        return bool(
            send_email(
                recipient.email,
                subject,
                "\n".join(plain_lines),
                html_body=html,
                source="hr",
                related_id=related_id,
            )
        )
    except Exception:
        app.logger.exception("HR lifecycle email failed for %s", recipient.email)
        return False


def send_submitter_confirmation(app: Flask, submission: Submission, submitter: User | None) -> None:
    title = form_title(submission)
    step = current_step_label(submission)
    sid = submission.submission_id
    _send(
        app,
        submitter,
        subject=f"We received your {title} — {sid}",
        greeting="Hello {name},",
        paragraphs=[
            f"Thank you. Your <strong>{html_escape(title)}</strong> is in and the approval chain has started.",
            f"It is currently with <strong>{html_escape(step)}</strong> for signature. We will email you as it moves.",
        ],
        rows=[
            ("Form", title),
            ("Reference", sid),
            ("Employee", employee_name(submission)),
            ("Now with", step),
        ],
        cta_url=my_request_url(app, submission),
        cta_label="Track this request",
        related_id=sid,
    )


def send_action_required(
    app: Flask,
    submission: Submission,
    recipient: User | None,
    *,
    role_label: str,
    sign_url: str | None = None,
) -> None:
    title = form_title(submission)
    sid = submission.submission_id
    emp = employee_name(submission)
    role = (role_label or "Approver").strip() or "Approver"
    url = sign_url or mgmt_sign_url(app, submission)
    _send(
        app,
        recipient,
        subject=f"Action required: sign {title} — {sid}",
        greeting="Hello {name},",
        paragraphs=[
            f"<strong>{html_escape(emp)}</strong> submitted a <strong>{html_escape(title)}</strong> that needs your signature.",
            f"This request is with you as <strong>{html_escape(role)}</strong>. Review the form in Kynvera and sign to send it to the next person in the chain.",
        ],
        rows=[
            ("Form", title),
            ("Reference", sid),
            ("Employee", emp),
            ("Your role", role),
        ],
        cta_url=url,
        cta_label="Review and sign",
        related_id=sid,
    )


def send_submitter_progress(
    app: Flask,
    submission: Submission,
    *,
    signed_by_name: str,
    signed_role: str,
) -> None:
    title = form_title(submission)
    sid = submission.submission_id
    submitter = db.session.get(User, submission.user_id) if submission.user_id else None
    nxt = current_step_label(submission)
    who = (signed_by_name or "An approver").strip()
    role = (signed_role or "Approver").strip()
    _send(
        app,
        submitter,
        subject=f"Update on your {title} — now with {nxt}",
        greeting="Hello {name},",
        paragraphs=[
            f"<strong>{html_escape(who)}</strong> signed as <strong>{html_escape(role)}</strong>.",
            f"Your request is now with <strong>{html_escape(nxt)}</strong>. We will write again when they act.",
        ],
        rows=[
            ("Form", title),
            ("Reference", sid),
            ("Signed by", f"{who} ({role})"),
            ("Now with", nxt),
        ],
        cta_url=my_request_url(app, submission),
        cta_label="View this request",
        related_id=sid,
    )


def send_submitter_outcome(
    app: Flask,
    submission: Submission,
    *,
    approved: bool,
    reason: str | None = None,
) -> None:
    title = form_title(submission)
    sid = submission.submission_id
    submitter = db.session.get(User, submission.user_id) if submission.user_id else None
    if approved:
        _send(
            app,
            submitter,
            subject=f"Your {title} is approved — {sid}",
            greeting="Hello {name},",
            paragraphs=[
                f"Good news — your <strong>{html_escape(title)}</strong> is fully approved. Every required signature is on the record.",
                "You can open the request any time from My Requests, including the signed PDF.",
            ],
            rows=[
                ("Form", title),
                ("Reference", sid),
                ("Employee", employee_name(submission)),
                ("Status", "Approved"),
            ],
            cta_url=my_request_url(app, submission),
            cta_label="Open this request",
            related_id=sid,
        )
        return
    why = (reason or "").strip() or "No reason was given."
    _send(
        app,
        submitter,
        subject=f"Your {title} was not approved — {sid}",
        greeting="Hello {name},",
        paragraphs=[
            f"Your <strong>{html_escape(title)}</strong> was not approved during management sign-off.",
            f"Reason: {html_escape(why)}",
        ],
        rows=[
            ("Form", title),
            ("Reference", sid),
            ("Employee", employee_name(submission)),
            ("Status", "Not approved"),
        ],
        cta_url=my_request_url(app, submission),
        cta_label="View this request",
        related_id=sid,
    )


def send_action_required_to_users(
    app: Flask,
    submission: Submission,
    users: list[User],
    *,
    role_label: str,
    sign_url: str | None = None,
) -> None:
    seen: set[int] = set()
    for u in users:
        if not u or u.id in seen:
            continue
        seen.add(u.id)
        send_action_required(app, submission, u, role_label=role_label, sign_url=sign_url)
