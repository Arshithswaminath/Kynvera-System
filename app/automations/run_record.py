"""Canonical AutomationRun.detail schema and API view.

Every job writes the same shape so Recent runs, the details modal, and
future catalogs (Technicians, MMR) can render one audit record.
"""
from __future__ import annotations

from typing import Any, Optional

from app.automations.jobs import get_catalog_entry
from app.models import AutomationRun, EmailLog

SCHEMA_VERSION = 1

OUTCOME_SENT = 'sent'
OUTCOME_FAILED = 'failed'
OUTCOME_SKIPPED = 'skipped'

REASON_SEND_EMAIL_OFF = 'send_email_off'
REASON_NO_RECIPIENTS = 'no_recipients'
REASON_EMAIL_NOT_CONFIGURED = 'email_not_configured'
REASON_NO_ATTACHMENTS = 'no_attachments'
REASON_SEND_FAILED = 'send_failed'

_REASON_LABELS = {
    REASON_SEND_EMAIL_OFF: 'Email was turned off for this job.',
    REASON_NO_RECIPIENTS: 'No recipients are set.',
    REASON_EMAIL_NOT_CONFIGURED: 'Email is not configured on this server.',
    REASON_NO_ATTACHMENTS: 'No Excel attachments were produced.',
    REASON_SEND_FAILED: 'The mail provider rejected or failed the send.',
}


def related_id_for_run(run_id: int) -> str:
    return f'automation_run:{int(run_id)}'


def lookup_email_log(related_id: Optional[str]) -> Optional[EmailLog]:
    text = (related_id or '').strip()
    if not text:
        return None
    return (
        EmailLog.query.filter_by(related_id=text)
        .order_by(EmailLog.id.desc())
        .first()
    )


def job_snapshot(job: Any, spec: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    spec = spec or get_catalog_entry(getattr(job, 'slug', '') or '') or {}
    return {
        'slug': getattr(job, 'slug', '') or spec.get('slug') or '',
        'title': spec.get('title') or getattr(job, 'slug', '') or 'Automation',
        'save_to_files': bool(getattr(job, 'save_to_files', True)),
        'send_email': bool(getattr(job, 'send_email', True)),
        'sync_drive': bool(getattr(job, 'sync_drive', True)),
    }


def file_record(
    *,
    module: str,
    label: str,
    item_id: Optional[int],
    filename: str,
    folder: str = '',
    size_bytes: Optional[int] = None,
    drive: Optional[dict[str, Any]] = None,
    attached_to_email: bool = False,
) -> dict[str, Any]:
    return {
        'module': module,
        'label': label,
        'item_id': item_id,
        'filename': filename,
        'folder': folder or '',
        'size_bytes': size_bytes,
        'attached_to_email': bool(attached_to_email),
        'drive': drive or {},
    }


def build_email_outcome(
    *,
    outcome: str,
    reason: Optional[str] = None,
    recipients: Optional[list[str]] = None,
    subject: str = '',
    attachment_names: Optional[list[str]] = None,
    email_log_id: Optional[int] = None,
    related_id: str = '',
) -> dict[str, Any]:
    """Persist both the new outcome fields and legacy sent/skipped flags."""
    recipients = list(recipients or [])
    attachment_names = list(attachment_names or [])
    sent = outcome == OUTCOME_SENT
    skipped = outcome == OUTCOME_SKIPPED
    return {
        'sent': sent,
        'skipped': skipped,
        'outcome': outcome,
        'reason': reason,
        'recipients': recipients,
        'subject': subject or '',
        'attachment_names': attachment_names,
        'email_log_id': email_log_id,
        'related_id': related_id or '',
    }


def build_run_detail(
    *,
    job: Any,
    spec: Optional[dict[str, Any]],
    files: list[dict[str, Any]],
    email: dict[str, Any],
    warnings: list[str],
    dubai_date: str,
) -> dict[str, Any]:
    return {
        'schema': SCHEMA_VERSION,
        'dubai_date': dubai_date,
        'job': job_snapshot(job, spec),
        'files': list(files or []),
        'email': email,
        'warnings': list(warnings or []),
    }


def _infer_outcome(email: dict[str, Any]) -> str:
    raw = (email.get('outcome') or '').strip()
    if raw in (OUTCOME_SENT, OUTCOME_FAILED, OUTCOME_SKIPPED):
        return raw
    if email.get('sent'):
        return OUTCOME_SENT
    if email.get('skipped') is False:
        return OUTCOME_FAILED
    return OUTCOME_SKIPPED


def _infer_reason(email: dict[str, Any], outcome: str, job_meta: dict[str, Any]) -> Optional[str]:
    reason = email.get('reason') or None
    if reason:
        return reason
    if outcome == OUTCOME_FAILED:
        return REASON_SEND_FAILED
    if outcome == OUTCOME_SKIPPED and job_meta.get('send_email') is False:
        return REASON_SEND_EMAIL_OFF
    return None


def reason_label(reason: Optional[str]) -> str:
    return _REASON_LABELS.get(reason or '', '')


def email_line(outcome: str, reason: Optional[str], recipients: list[str]) -> str:
    if outcome == OUTCOME_SENT:
        if not recipients:
            return 'Sent'
        if len(recipients) == 1:
            return f'Sent to {recipients[0]}'
        return f'Sent to {recipients[0]} +{len(recipients) - 1}'
    if reason == REASON_SEND_EMAIL_OFF:
        return 'Email off'
    if reason == REASON_NO_RECIPIENTS:
        return 'Not sent — no recipients'
    if reason == REASON_EMAIL_NOT_CONFIGURED:
        return 'Not sent — email not configured'
    if reason == REASON_NO_ATTACHMENTS:
        return 'Not sent — no attachments'
    if reason == REASON_SEND_FAILED or outcome == OUTCOME_FAILED:
        return 'Email send failed'
    return 'Email not sent'


def _email_note(outcome: str, reason: Optional[str]) -> str:
    if outcome == OUTCOME_SENT:
        return 'The mail provider accepted this message. Inbox delivery is not tracked.'
    return reason_label(reason) or 'This run did not send email.'


def normalize_run_view(
    run: AutomationRun,
    email_log: Optional[EmailLog] = None,
    spec: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """API payload: run.to_dict() plus a stable `view` for UI (legacy-safe)."""
    payload = run.to_dict()
    detail = dict(run.detail or {})
    email = dict(detail.get('email') or {})
    files = list(detail.get('files') or [])
    warnings = list(detail.get('warnings') or [])
    job_meta = dict(detail.get('job') or {})
    slug = payload.get('slug') or job_meta.get('slug') or ''
    spec = spec or get_catalog_entry(slug) or {}
    title = job_meta.get('title') or spec.get('title') or slug or 'Automation'
    recipients = [str(item).strip() for item in (email.get('recipients') or []) if str(item).strip()]
    outcome = _infer_outcome(email)
    reason = _infer_reason(email, outcome, job_meta)
    attachment_names = [str(n) for n in (email.get('attachment_names') or []) if n]
    if not attachment_names:
        attachment_names = [f.get('filename') for f in files if f.get('filename')]
    related_id = (email.get('related_id') or '').strip() or (
        related_id_for_run(run.id) if run.id else ''
    )
    view_files = []
    for row in files:
        item_id = row.get('item_id')
        view_files.append({
            **row,
            'download_url': f'/files/api/items/{item_id}/download' if item_id else None,
        })
    payload['view'] = {
        'job_title': title,
        'dubai_date': detail.get('dubai_date') or '',
        'save_to_files': job_meta.get('save_to_files'),
        'send_email': job_meta.get('send_email'),
        'sync_drive': job_meta.get('sync_drive'),
        'files': view_files,
        'email': {
            'outcome': outcome,
            'reason': reason,
            'reason_label': reason_label(reason),
            'recipients': recipients,
            'subject': email.get('subject') or '',
            'attachment_names': attachment_names,
            'email_log_id': email.get('email_log_id'),
            'related_id': related_id,
            'sent': outcome == OUTCOME_SENT,
            'skipped': outcome == OUTCOME_SKIPPED,
            'line': email_line(outcome, reason, recipients),
            'note': _email_note(outcome, reason),
        },
        'warnings': warnings,
        'email_log': email_log.to_dict() if email_log is not None else None,
    }
    return payload
