"""Saved BD email automations: ACL, attachment fetch-on-run, and send."""

from __future__ import annotations

import logging
import mimetypes
import os
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import urlopen

from flask import current_app, has_request_context, request
from sqlalchemy import and_, or_

from app.models import (
    EmailAutomation,
    EmailAutomationAttachment,
    EmailLog,
    EmailRecipientGroup,
    File,
    FilesFolder,
    FilesItem,
    Job,
    Submission,
    User,
    db,
)
from common.datetime_utils import naive_utc_isoformat_z, utc_now_naive
from common.email_service import is_email_configured, send_email
from module_files import service as files_service

logger = logging.getLogger(__name__)

SCOPE_PERSONAL = 'personal'
SCOPE_DIY = SCOPE_PERSONAL  # backward-compatible alias
SCOPE_PUBLIC = 'public'
SCOPES = (SCOPE_PERSONAL, SCOPE_PUBLIC)
PERSONAL_SCOPE_VALUES = ('personal', 'diy')
_SCOPE_ALIASES = {
    'diy': SCOPE_PERSONAL,
    'private': SCOPE_PERSONAL,
    'mine': SCOPE_PERSONAL,
    'personal': SCOPE_PERSONAL,
    'public': SCOPE_PUBLIC,
    'shared': SCOPE_PUBLIC,
}
KIND_LINKED_FILE = 'linked_file'
KIND_FOLDER_LATEST = 'folder_latest'
KIND_SUBMISSION_REPORTS = 'submission_reports'
ATTACHMENT_KINDS = (KIND_LINKED_FILE, KIND_FOLDER_LATEST, KIND_SUBMISSION_REPORTS)
EMAIL_FOLDER_PATH_KEY = 'reports/email'


class AutomationError(Exception):
    def __init__(self, message, status=400, skipped=False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.skipped = skipped


def is_bd_user(user):
    if not user or not getattr(user, 'is_active', True):
        return False
    if user.role == 'admin':
        return True
    return bool(user.is_bd_inspection_reviewer())


def _is_admin(user):
    return bool(user and user.role == 'admin')


def can_view_automation(user, auto):
    if not user or not auto:
        return False
    if _is_admin(user):
        return True
    if (auto.scope or SCOPE_PERSONAL) == SCOPE_PUBLIC:
        return is_bd_user(user)
    return auto.owner_id == user.id


def can_edit_automation(user, auto):
    if not user or not auto:
        return False
    if _is_admin(user):
        return True
    return auto.owner_id == user.id and is_bd_user(user)


def can_run_automation(user, auto):
    return can_view_automation(user, auto)


def can_view_group(user, group):
    if not user or not group:
        return False
    if _is_admin(user):
        return True
    if (group.scope or SCOPE_PERSONAL) == SCOPE_PUBLIC:
        return is_bd_user(user)
    return group.owner_id == user.id


def can_edit_group(user, group):
    if not user or not group:
        return False
    if _is_admin(user):
        return True
    return group.owner_id == user.id and is_bd_user(user)


def parse_scope(value, default=SCOPE_PERSONAL):
    raw = (value or default or SCOPE_PERSONAL).strip().lower()
    raw = _SCOPE_ALIASES.get(raw, raw)
    return raw if raw in SCOPES else default


def normalize_scope(value):
    if (value or '') == SCOPE_PUBLIC:
        return SCOPE_PUBLIC
    return SCOPE_PERSONAL


def parse_emails(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]
    raw = str(value)
    parts = [p.strip() for p in raw.replace(';', ',').split(',')]
    return [p for p in parts if p]


def emails_to_text(value):
    return ', '.join(parse_emails(value))


def parse_submission_ids(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]
    raw = str(value)
    parts = [p.strip() for p in raw.replace(';', ',').split(',')]
    return [p for p in parts if p]


def parse_file_item_ids(value):
    if not value:
        return []
    raw_ids = value if isinstance(value, list) else str(value).replace(';', ',').split(',')
    ids = []
    for raw in raw_ids:
        try:
            item_id = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if item_id > 0:
            ids.append(item_id)
    seen = set()
    unique = []
    for item_id in ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item_id)
    return unique


def _int_or_none(value):
    if value is None or value == '':
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def visible_automations_query(user, scope=None):
    q = EmailAutomation.query
    wanted = parse_scope(scope, default='') if scope else None
    if wanted not in SCOPES:
        wanted = None
    if _is_admin(user):
        if wanted == SCOPE_PUBLIC:
            q = q.filter(EmailAutomation.scope == SCOPE_PUBLIC)
        elif wanted == SCOPE_PERSONAL:
            q = q.filter(EmailAutomation.scope.in_(PERSONAL_SCOPE_VALUES))
        return q.order_by(EmailAutomation.updated_at.desc())
    if wanted == SCOPE_PUBLIC:
        q = q.filter(EmailAutomation.scope == SCOPE_PUBLIC)
    elif wanted == SCOPE_PERSONAL:
        q = q.filter(EmailAutomation.scope.in_(PERSONAL_SCOPE_VALUES), EmailAutomation.owner_id == user.id)
    else:
        q = q.filter(or_(
            EmailAutomation.scope == SCOPE_PUBLIC,
            and_(EmailAutomation.scope.in_(PERSONAL_SCOPE_VALUES), EmailAutomation.owner_id == user.id),
        ))
    return q.order_by(EmailAutomation.updated_at.desc())


def visible_groups_query(user, scope=None):
    q = EmailRecipientGroup.query
    wanted = parse_scope(scope, default='') if scope else None
    if wanted not in SCOPES:
        wanted = None
    if _is_admin(user):
        if wanted == SCOPE_PUBLIC:
            q = q.filter(EmailRecipientGroup.scope == SCOPE_PUBLIC)
        elif wanted == SCOPE_PERSONAL:
            q = q.filter(EmailRecipientGroup.scope.in_(PERSONAL_SCOPE_VALUES))
        return q.order_by(EmailRecipientGroup.name.asc())
    if wanted == SCOPE_PUBLIC:
        q = q.filter(EmailRecipientGroup.scope == SCOPE_PUBLIC)
    elif wanted == SCOPE_PERSONAL:
        q = q.filter(EmailRecipientGroup.scope.in_(PERSONAL_SCOPE_VALUES), EmailRecipientGroup.owner_id == user.id)
    else:
        q = q.filter(or_(
            EmailRecipientGroup.scope == SCOPE_PUBLIC,
            and_(EmailRecipientGroup.scope.in_(PERSONAL_SCOPE_VALUES), EmailRecipientGroup.owner_id == user.id),
        ))
    return q.order_by(EmailRecipientGroup.name.asc())


def serialize_group(group):
    data = group.to_dict()
    data['scope'] = normalize_scope(data.get('scope'))
    owner = group.owner
    data['owner_name'] = (owner.full_name or owner.username) if owner else ''
    return data


def serialize_attachment(slot):
    file_name = ''
    folder_name = ''
    sync_status = ''
    folder_path = ''
    if slot.files_item:
        file_name = slot.files_item.name or slot.files_item.filename or ''
        sync_status = slot.files_item.sync_status or ''
        if slot.files_item.folder:
            folder_name = slot.files_item.folder.name or ''
    if slot.folder:
        folder_name = slot.folder.name or folder_name
        folder_path = slot.folder.path_key or ''
    return {
        'id': slot.id,
        'kind': slot.kind,
        'files_item_id': slot.files_item_id,
        'folder_id': slot.folder_id,
        'submission_id': slot.submission_id or '',
        'require_new': bool(slot.require_new),
        'sort_order': int(slot.sort_order or 0),
        'file_name': file_name,
        'folder_name': folder_name,
        'folder_path': folder_path,
        'sync_status': sync_status,
    }


def serialize_automation(auto, include_attachments=True):
    owner = auto.owner
    data = {
        'id': auto.id,
        'name': auto.name or '',
        'scope': normalize_scope(auto.scope),
        'owner_id': auto.owner_id,
        'owner_name': (owner.full_name or owner.username) if owner else '',
        'to_emails': auto.to_emails or '',
        'cc_emails': auto.cc_emails or '',
        'subject': auto.subject or '',
        'body': auto.body or '',
        'enabled': bool(auto.enabled),
        'schedule_enabled': bool(auto.schedule_enabled),
        'schedule_hour': int(auto.schedule_hour if auto.schedule_hour is not None else 10),
        'schedule_minute': int(auto.schedule_minute if auto.schedule_minute is not None else 0),
        'schedule_paused': bool(auto.schedule_paused),
        'last_run_at': naive_utc_isoformat_z(auto.last_run_at),
        'last_success_at': naive_utc_isoformat_z(auto.last_success_at),
        'last_error': auto.last_error or '',
        'created_at': naive_utc_isoformat_z(auto.created_at),
        'updated_at': naive_utc_isoformat_z(auto.updated_at),
        'attachment_count': len(auto.attachments or []),
        'can_edit': False,
        'can_run': False,
    }
    if include_attachments:
        data['attachments'] = [serialize_attachment(s) for s in (auto.attachments or [])]
    return data


def parse_attachment_payload(raw):
    if not raw:
        return []
    if not isinstance(raw, list):
        raise AutomationError('Attachments must be a list')
    slots = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        kind = (item.get('kind') or KIND_LINKED_FILE).strip().lower()
        if kind == 'upload':
            kind = KIND_LINKED_FILE
        if kind not in ATTACHMENT_KINDS:
            raise AutomationError(f'Unknown attachment kind: {kind}')
        slot = {
            'kind': kind,
            'files_item_id': _int_or_none(item.get('files_item_id')),
            'folder_id': _int_or_none(item.get('folder_id')),
            'submission_id': (str(item.get('submission_id') or '').strip() or None),
            'require_new': bool(item.get('require_new')),
            'sort_order': i,
        }
        if kind == KIND_LINKED_FILE and not slot['files_item_id']:
            raise AutomationError('Linked file attachments need a Files item')
        if kind == KIND_FOLDER_LATEST and not slot['folder_id']:
            raise AutomationError('Folder-latest attachments need a folder')
        if kind == KIND_SUBMISSION_REPORTS and not slot['submission_id']:
            raise AutomationError('Submission report attachments need a submission')
        slots.append(slot)
    return slots


def replace_attachments(auto, slots):
    EmailAutomationAttachment.query.filter_by(automation_id=auto.id).delete()
    for i, spec in enumerate(slots):
        row = EmailAutomationAttachment(
            automation_id=auto.id,
            kind=spec['kind'],
            files_item_id=spec.get('files_item_id'),
            folder_id=spec.get('folder_id'),
            submission_id=spec.get('submission_id'),
            require_new=bool(spec.get('require_new')),
            sort_order=int(spec.get('sort_order', i) or 0),
        )
        db.session.add(row)
    db.session.flush()


def apply_automation_fields(auto, payload, creating=False):
    name = (payload.get('name') or auto.name or '').strip()
    if creating and not name:
        raise AutomationError('Name is required')
    if name:
        auto.name = name[:160]
    if 'scope' in payload or creating:
        auto.scope = parse_scope(payload.get('scope'), default=auto.scope or SCOPE_PERSONAL)
    if 'to' in payload or 'to_emails' in payload or creating:
        auto.to_emails = emails_to_text(payload.get('to_emails', payload.get('to')))
    if 'cc' in payload or 'cc_emails' in payload:
        auto.cc_emails = emails_to_text(payload.get('cc_emails', payload.get('cc')))
    if 'subject' in payload or creating:
        auto.subject = (payload.get('subject') or '').strip()[:500]
    if 'body' in payload or 'message' in payload or creating:
        auto.body = (payload.get('body', payload.get('message')) or '').strip()
    if 'enabled' in payload:
        auto.enabled = bool(payload.get('enabled'))
    if 'schedule_enabled' in payload:
        auto.schedule_enabled = bool(payload.get('schedule_enabled'))
    if 'schedule_paused' in payload:
        auto.schedule_paused = bool(payload.get('schedule_paused'))
    if 'schedule_hour' in payload:
        try:
            hour = int(payload.get('schedule_hour'))
        except (TypeError, ValueError):
            hour = 10
        auto.schedule_hour = max(0, min(23, hour))
    if 'schedule_minute' in payload:
        try:
            minute = int(payload.get('schedule_minute'))
        except (TypeError, ValueError):
            minute = 0
        auto.schedule_minute = max(0, min(59, minute))
    auto.updated_at = utc_now_naive()


def download_attachment_from_url(url, fallback_name):
    if url and url.startswith('/generated/'):
        base_dir = current_app.config.get(
            'GENERATED_DIR',
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated'),
        )
        rel_path = url.lstrip('/')
        if rel_path.startswith('generated/'):
            rel_path = rel_path.replace('generated/', '', 1)
        local_path = os.path.join(base_dir, rel_path)
        if os.path.exists(local_path):
            with open(local_path, 'rb') as fh:
                data = fh.read()
            mime_type = mimetypes.guess_type(local_path)[0] or 'application/octet-stream'
            return {'content': data, 'filename': os.path.basename(local_path), 'mime_type': mime_type}

    if url and url.startswith('/'):
        base_url = current_app.config.get('APP_BASE_URL') or ''
        if not base_url and has_request_context():
            base_url = request.url_root.rstrip('/')
        if not base_url:
            raise RuntimeError('Cannot resolve relative attachment URL')
        url = f'{base_url}{url}'

    parsed = urlparse(url)
    filename = os.path.basename(parsed.path) or fallback_name
    with urlopen(url) as response:
        data = response.read()
    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return {'content': data, 'filename': filename, 'mime_type': mime_type}


def collect_submission_attachments(submission):
    attachments = []
    found_documents = False

    report_files = File.query.filter_by(
        submission_id=submission.id
    ).filter(
        File.file_type.in_(['report_excel', 'report_pdf'])
    ).all()

    for file in report_files:
        if file.file_path and os.path.exists(file.file_path):
            attachments.append(file.file_path)
            found_documents = True
            continue
        if file.cloud_url:
            try:
                fallback = f'{submission.submission_id}.pdf' if file.file_type == 'report_pdf' else f'{submission.submission_id}.xlsx'
                attachments.append(download_attachment_from_url(file.cloud_url, fallback))
                found_documents = True
            except Exception:
                logger.exception('Failed to download cloud report for %s', submission.submission_id)

    if found_documents:
        return attachments, found_documents

    job = Job.query.filter_by(
        submission_id=submission.id,
        status='completed',
    ).order_by(Job.completed_at.desc()).first()
    if job and job.result_data:
        pdf_url = job.result_data.get('pdf_url') or job.result_data.get('pdf')
        excel_url = job.result_data.get('excel_url') or job.result_data.get('excel')
        try:
            if pdf_url:
                attachments.append(download_attachment_from_url(pdf_url, f'{submission.submission_id}.pdf'))
                found_documents = True
            if excel_url:
                attachments.append(download_attachment_from_url(excel_url, f'{submission.submission_id}.xlsx'))
                found_documents = True
        except Exception:
            logger.exception('Failed to download job result files')

    return attachments, found_documents


def _try_refresh_from_drive(item):
    if not item or not item.drive_file_id:
        return item
    try:
        from module_files import drive_service
        if not drive_service.drive_enabled() or not drive_service.drive_configured():
            return item
        if not drive_service.get_connection():
            return item
        return drive_service.refresh_item_from_drive(item.id)
    except Exception:
        logger.warning('Drive refresh failed for Files item %s; using local copy', item.id, exc_info=True)
        return item


def read_files_item_attachment(item, refresh_drive=True):
    if not item:
        raise FileNotFoundError('File not found')
    if refresh_drive:
        item = _try_refresh_from_drive(item) or item
        item = db.session.get(FilesItem, item.id) or item
    abs_path = files_service.resolve_item_abs_path(item)
    filename = item.filename or item.name or os.path.basename(abs_path)
    mime_type = item.mime_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    with open(abs_path, 'rb') as fh:
        data = fh.read()
    return {
        'content': data,
        'filename': filename,
        'mime_type': mime_type,
        'item': item,
        'abs_path': abs_path,
    }


def collect_files_item_attachments(file_item_ids, refresh_drive=True):
    attachments = []
    missing = []
    for item_id in file_item_ids:
        item = db.session.get(FilesItem, item_id)
        if not item:
            missing.append(str(item_id))
            continue
        try:
            packed = read_files_item_attachment(item, refresh_drive=refresh_drive)
        except FileNotFoundError:
            missing.append(item.name or item.filename or str(item_id))
            continue
        except Exception:
            logger.exception('Failed to read Files item %s', item_id)
            missing.append(item.name or item.filename or str(item_id))
            continue
        attachments.append({
            'content': packed['content'],
            'filename': packed['filename'],
            'mime_type': packed['mime_type'],
        })
    return attachments, missing


def _stamp_for_item(item, packed=None):
    stamp = item.updated_at
    path = packed.get('abs_path') if packed else None
    if not path:
        try:
            path = files_service.resolve_item_abs_path(item)
        except Exception:
            path = None
    if path:
        try:
            mtime = datetime.utcfromtimestamp(os.path.getmtime(path))
            if stamp is None or mtime > stamp:
                stamp = mtime
        except OSError:
            pass
    return stamp


def _is_fresh_enough(stamp, last_success_at):
    if last_success_at is None:
        return True
    if stamp is None:
        return True
    return stamp > last_success_at


def _latest_item_in_folder(folder_id):
    return (
        FilesItem.query.filter_by(folder_id=folder_id)
        .order_by(FilesItem.updated_at.desc(), FilesItem.id.desc())
        .first()
    )


def resolve_automation_attachments(auto, user=None):
    """Return (attachments, skip_reason). skip_reason is set when require_new fails."""
    attachments = []
    last_success = auto.last_success_at
    slots = list(auto.attachments or [])
    slots.sort(key=lambda s: int(s.sort_order or 0))

    for slot in slots:
        kind = slot.kind or KIND_LINKED_FILE
        if kind == KIND_LINKED_FILE:
            item = slot.files_item or db.session.get(FilesItem, slot.files_item_id) if slot.files_item_id else None
            if not item:
                msg = 'Linked cloud file is missing'
                if slot.require_new:
                    return [], msg
                raise AutomationError(msg)
            try:
                packed = read_files_item_attachment(item, refresh_drive=True)
            except FileNotFoundError:
                msg = f'Cloud file not found: {item.name or item.filename}'
                if slot.require_new:
                    return [], msg
                raise AutomationError(msg)
            if slot.require_new and not _is_fresh_enough(_stamp_for_item(packed['item'], packed), last_success):
                return [], f'Waiting for a new file: {packed["filename"]}'
            attachments.append({
                'content': packed['content'],
                'filename': packed['filename'],
                'mime_type': packed['mime_type'],
            })
        elif kind == KIND_FOLDER_LATEST:
            folder = slot.folder or db.session.get(FilesFolder, slot.folder_id) if slot.folder_id else None
            if not folder:
                msg = 'Attachment folder is missing'
                if slot.require_new:
                    return [], msg
                raise AutomationError(msg)
            item = _latest_item_in_folder(folder.id)
            if not item:
                msg = f'No files in folder: {folder.name}'
                if slot.require_new:
                    return [], msg
                raise AutomationError(msg)
            try:
                packed = read_files_item_attachment(item, refresh_drive=True)
            except FileNotFoundError:
                msg = f'Latest file missing in {folder.name}'
                if slot.require_new:
                    return [], msg
                raise AutomationError(msg)
            if slot.require_new and not _is_fresh_enough(_stamp_for_item(packed['item'], packed), last_success):
                return [], f'Waiting for a new file in {folder.name}'
            attachments.append({
                'content': packed['content'],
                'filename': packed['filename'],
                'mime_type': packed['mime_type'],
            })
        elif kind == KIND_SUBMISSION_REPORTS:
            sid = (slot.submission_id or '').strip()
            q = Submission.query.filter_by(submission_id=sid)
            if user and not _is_admin(user):
                q = q.filter_by(business_dev_id=user.id)
            submission = q.first()
            if not submission:
                raise AutomationError(f'Submission not found: {sid}')
            docs, found = collect_submission_attachments(submission)
            if not found:
                raise AutomationError(f'No PDF/Excel documents for {sid}')
            attachments.extend(docs)
        else:
            raise AutomationError(f'Unknown attachment kind: {kind}')

    return attachments, None


def _html_body(message, user=None):
    signature_name = ''
    if user:
        signature_name = user.full_name or user.username or ''
    escaped = (message or '').replace('\n', '<br>')
    sent_by = f'<p><strong>Sent by:</strong> {signature_name}<br>Kynvera Team</p>' if signature_name else '<p>Kynvera Team</p>'
    return f'<html><body><p>{escaped}</p>{sent_by}</body></html>'


def _text_body(message, user=None):
    if user:
        return f"{message}\n\nSent by: {user.full_name or user.username}\nKynvera Team"
    return f'{message}\n\nKynvera Team'


def run_automation(auto, user=None, trigger='manual'):
    if not auto:
        raise AutomationError('Automation not found', status=404)
    if not auto.enabled and trigger != 'manual':
        raise AutomationError('Automation is disabled')
    if not is_email_configured():
        raise AutomationError('Email is not configured')

    recipients = parse_emails(auto.to_emails)
    if not recipients:
        raise AutomationError('At least one To recipient is required')
    subject = (auto.subject or '').strip()
    message = (auto.body or '').strip()
    if not subject:
        raise AutomationError('Subject is required')
    if not message:
        raise AutomationError('Message is required')

    now = utc_now_naive()
    auto.last_run_at = now
    try:
        attachments, skip_reason = resolve_automation_attachments(auto, user=user)
    except AutomationError as err:
        auto.last_error = err.message[:500]
        db.session.commit()
        raise

    if skip_reason:
        auto.last_error = skip_reason[:500]
        db.session.commit()
        return {
            'success': True,
            'skipped': True,
            'message': skip_reason,
            'attachment_count': 0,
        }

    sent = send_email(
        recipients,
        subject,
        _text_body(message, user),
        html_body=_html_body(message, user),
        cc=parse_emails(auto.cc_emails) or None,
        attachments=attachments or None,
        source='bd_email',
        sent_by_user_id=user.id if user else auto.owner_id,
        related_id=f'automation:{auto.id}',
    )
    if sent:
        auto.last_success_at = now
        auto.last_error = None
        db.session.commit()
        return {
            'success': True,
            'skipped': False,
            'message': 'Email sent successfully',
            'attachment_count': len(attachments or []),
        }

    auto.last_error = 'Failed to send email'
    db.session.commit()
    raise AutomationError('Failed to send email', status=500)


def list_run_history(auto, limit=20):
    related = f'automation:{auto.id}'
    rows = (
        EmailLog.query.filter_by(source='bd_email', related_id=related)
        .order_by(EmailLog.created_at.desc())
        .limit(max(1, min(int(limit or 20), 100)))
        .all()
    )
    return [row.to_dict() for row in rows]


def ensure_email_files_folder(created_by=None):
    return files_service.get_folder_by_path_key(EMAIL_FOLDER_PATH_KEY, created_by=created_by)


def save_upload_for_automation(file_storage, created_by=None, sync_drive=True):
    folder = ensure_email_files_folder(created_by=created_by)
    item = files_service.save_upload(
        folder_id=folder.id,
        file_storage=file_storage,
        created_by=created_by,
    )
    if sync_drive:
        try:
            from module_files import drive_service
            if (
                drive_service.drive_enabled()
                and drive_service.drive_configured()
                and drive_service.get_connection()
            ):
                drive_service.sync_item(item.id)
                item = db.session.get(FilesItem, item.id) or item
        except Exception:
            logger.warning('Drive sync after email upload failed for item %s', item.id, exc_info=True)
    return item, folder


def append_linked_file_slot(auto, files_item_id, require_new=False):
    order = len(auto.attachments or [])
    slot = EmailAutomationAttachment(
        automation_id=auto.id,
        kind=KIND_LINKED_FILE,
        files_item_id=files_item_id,
        require_new=bool(require_new),
        sort_order=order,
    )
    db.session.add(slot)
    db.session.commit()
    return slot
