"""PR documents, stamps, finance tokens, and email templates."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets

from flask import current_app, url_for
from werkzeug.utils import secure_filename

from app.models import db
from common.email_service import send_email
from config import UPLOADS_DIR
from module_procurement.models import (
    EMAIL_EVENT_KEYS,
    MAX_QUOTATIONS,
    QUOTATION_KINDS,
    ProcEmailTemplate,
    ProcPurchaseDocument,
    ProcPurchaseRequest,
    _utcnow,
)
from module_procurement.pr_pdf import build_pr_pdf, stamp_pdf_bytes, wrap_image_as_pdf

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXT = {'.pdf', '.png', '.jpg', '.jpeg'}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

EMAIL_DEFAULTS = {
    'quotation_for_approval': {
        'label': 'Quotation ready for GM / finance',
        'subject': 'Purchase request {pr_id} — quotation for approval',
        'body': (
            'A supplier quotation is ready for approval.\n\n'
            'Request: {pr_id}\n'
            'Property: {property}\n'
            'Total: {total}\n'
            'Status: {status}\n\n'
            'Approve: {approve_url}\n'
        ),
    },
    'quotation_approved': {
        'label': 'Quotation approved',
        'subject': 'Purchase request {pr_id} — quotation approved',
        'body': (
            'The quotation for {pr_id} has been approved.\n\n'
            'Property: {property}\n'
            'Total: {total}\n'
        ),
    },
    'invoice_for_approval': {
        'label': 'Supplier invoice for approval',
        'subject': 'Purchase request {pr_id} — invoice for approval',
        'body': (
            'A supplier invoice has been uploaded and needs approval.\n\n'
            'Request: {pr_id}\n'
            'Property: {property}\n'
            'Total: {total}\n\n'
            'Approve: {approve_url}\n'
        ),
    },
    'invoice_approved': {
        'label': 'Invoice approved',
        'subject': 'Purchase request {pr_id} — invoice approved',
        'body': (
            'The supplier invoice for {pr_id} has been approved.\n\n'
            'Property: {property}\n'
            'Total: {total}\n'
        ),
    },
}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def pr_upload_dir(pr: ProcPurchaseRequest) -> str:
    path = os.path.join(UPLOADS_DIR, 'procurement', str(pr.public_id))
    os.makedirs(path, exist_ok=True)
    return path


def quotation_docs(pr: ProcPurchaseRequest) -> list[ProcPurchaseDocument]:
    rows = ProcPurchaseDocument.query.filter(
        ProcPurchaseDocument.request_id == pr.id,
        ProcPurchaseDocument.kind.in_(QUOTATION_KINDS),
    ).order_by(ProcPurchaseDocument.id.asc()).all()
    return [d for d in rows if d.original_path]


def next_quotation_kind(pr: ProcPurchaseRequest) -> str | None:
    used = {d.kind for d in quotation_docs(pr)}
    for kind in QUOTATION_KINDS:
        if kind not in used:
            return kind
    return None


def _empty_doc(kind: str) -> dict:
    return {
        'kind': kind, 'status': 'missing', 'original_name': '',
        'has_original': False, 'has_stamped': False,
        'approved_by': '', 'approved_at': None, 'slot': 1,
    }


def documents_payload(pr: ProcPurchaseRequest) -> dict:
    out = {}
    quotes = quotation_docs(pr)
    stamped = next((d for d in quotes if d.status == 'approved' and d.stamped_path), None)
    quote_items = []
    for doc in quotes:
        d = doc.to_dict()
        d['can_upload'] = False
        d['can_approve'] = _can_in_app_approve(pr, 'quotation', d['status'])
        quote_items.append(d)
    summary = (stamped or (quotes[0] if quotes else None))
    if summary:
        q = summary.to_dict()
    else:
        q = _empty_doc('quotation')
    q['can_upload'] = _can_upload(pr, 'quotation')
    q['can_approve'] = _can_in_app_approve(pr, 'quotation', q['status'])
    q['count'] = len(quotes)
    q['max'] = MAX_QUOTATIONS
    q['can_send'] = pr.status == 'awaiting_quotation' and len(quotes) >= 1
    q['has_stamped'] = bool(stamped)
    q['status'] = stamped.status if stamped else (quotes[0].status if quotes else 'missing')
    out['quotation'] = q
    out['quotations'] = quote_items

    for kind in ('pr_pdf', 'invoice'):
        doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind=kind).first()
        d = doc.to_dict() if doc else _empty_doc(kind)
        d['can_upload'] = _can_upload(pr, kind)
        d['can_approve'] = _can_in_app_approve(pr, kind, d['status'])
        out[kind] = d
    return out


def _can_upload(pr, kind) -> bool:
    if kind in QUOTATION_KINDS or kind == 'quotation':
        return pr.status == 'awaiting_quotation' and next_quotation_kind(pr) is not None
    if kind == 'invoice':
        return pr.status == 'received'
    return False


def _can_in_app_approve(pr, kind, status) -> bool:
    if status != 'pending_approval':
        return False
    if kind == 'quotation':
        return pr.status == 'gm_review'
    if kind == 'invoice':
        return pr.status == 'received'
    return False


def quotation_is_stamped(pr: ProcPurchaseRequest) -> bool:
    return any(d.status == 'approved' and d.stamped_path for d in quotation_docs(pr))


def invoice_is_stamped(pr: ProcPurchaseRequest) -> bool:
    doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind='invoice').first()
    return bool(doc and doc.status == 'approved' and doc.stamped_path)


def close_if_invoice_complete(pr: ProcPurchaseRequest) -> bool:
    """Received PRs with a stamped invoice become closed (also heals older rows)."""
    if pr.status != 'received' or not invoice_is_stamped(pr):
        return False
    pr.status = 'closed'
    return True


def get_or_create_doc(pr: ProcPurchaseRequest, kind: str) -> ProcPurchaseDocument:
    doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind=kind).first()
    if doc:
        return doc
    doc = ProcPurchaseDocument(request=pr, kind=kind, status='missing')
    db.session.add(doc)
    db.session.flush()
    return doc


def generate_pr_pdf(pr: ProcPurchaseRequest) -> ProcPurchaseDocument:
    doc = get_or_create_doc(pr, 'pr_pdf')
    pdf_bytes = build_pr_pdf(pr)
    dest = os.path.join(pr_upload_dir(pr), 'purchase-request.pdf')
    with open(dest, 'wb') as fh:
        fh.write(pdf_bytes)
    doc.original_path = dest
    doc.original_name = f'{pr.public_id}-purchase-request.pdf'
    doc.status = 'approved'
    doc.approved_at = _utcnow()
    doc.approved_by = 'procurement'
    return doc


def save_upload(pr: ProcPurchaseRequest, kind: str, file_storage, *, user=None) -> ProcPurchaseDocument:
    if kind not in ('quotation', 'invoice') and kind not in QUOTATION_KINDS:
        raise ValueError('Only quotation or invoice can be uploaded')
    if kind == 'quotation' or kind in QUOTATION_KINDS:
        if pr.status != 'awaiting_quotation':
            raise ValueError('Quotations can be added before sending for approval')
        kind = next_quotation_kind(pr)
        if not kind:
            raise ValueError('You can add up to three quotations')
    if not file_storage or not getattr(file_storage, 'filename', None):
        raise ValueError('Choose a PDF or image to upload')
    name = secure_filename(file_storage.filename) or f'{kind}.pdf'
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise ValueError('Upload a PDF, PNG, or JPEG')
    data = file_storage.read()
    if not data:
        raise ValueError('File is empty')
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('File is larger than 10 MB')
    dest = os.path.join(pr_upload_dir(pr), f'{kind}{ext}')
    with open(dest, 'wb') as fh:
        fh.write(data)
    doc = get_or_create_doc(pr, kind)
    doc.original_path = dest
    doc.original_name = name
    doc.stamped_path = None
    doc.approved_by = None
    doc.approved_at = None
    doc.approval_token = None
    doc.uploaded_by_id = user.id if user else None
    doc.status = 'uploaded'
    doc.updated_at = _utcnow()
    return doc


def _source_pdf_bytes(doc: ProcPurchaseDocument) -> bytes:
    path = doc.original_path
    if not path or not os.path.isfile(path):
        raise ValueError('No file to stamp')
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.png', '.jpg', '.jpeg'):
        return wrap_image_as_pdf(path)
    with open(path, 'rb') as fh:
        return fh.read()


def stamp_document(doc: ProcPurchaseDocument, *, approver: str) -> ProcPurchaseDocument:
    src = _source_pdf_bytes(doc)
    stamped = stamp_pdf_bytes(
        src,
        pr_id=doc.request.public_id if doc.request else '',
        approver=approver,
        kind=doc.kind,
    )
    dest = os.path.join(pr_upload_dir(doc.request), f'{doc.kind}-approved.pdf')
    with open(dest, 'wb') as fh:
        fh.write(stamped)
    doc.stamped_path = dest
    doc.status = 'approved'
    doc.approved_by = approver
    doc.approved_at = _utcnow()
    doc.approval_token = None
    return doc


def issue_approval_token(doc: ProcPurchaseDocument) -> str:
    raw = secrets.token_urlsafe(32)
    doc.approval_token = _hash_token(raw)
    return raw


def find_doc_by_token(raw: str) -> ProcPurchaseDocument | None:
    if not raw:
        return None
    return ProcPurchaseDocument.query.filter_by(approval_token=_hash_token(raw)).first()


def approve_document(doc: ProcPurchaseDocument, *, approver: str):
    pr = doc.request
    stamp_document(doc, approver=approver)
    if doc.kind in QUOTATION_KINDS:
        for other in quotation_docs(pr):
            if other.id != doc.id and other.status == 'pending_approval':
                other.status = 'uploaded'
                other.approval_token = None
        pr.status = 'approved'
        pr.approved_at = _utcnow()
        pr_pdf = generate_pr_pdf(pr)
        stamp_document(pr_pdf, approver=approver)
        send_pr_event_email(pr, 'quotation_approved')
    elif doc.kind == 'invoice':
        pr.status = 'closed'
        send_pr_event_email(pr, 'invoice_approved')
    return doc


def seed_email_templates():
    for key in EMAIL_EVENT_KEYS:
        row = ProcEmailTemplate.query.filter_by(event_key=key).first()
        if row:
            continue
        defaults = EMAIL_DEFAULTS[key]
        db.session.add(ProcEmailTemplate(
            event_key=key,
            to_emails='',
            cc_emails='',
            subject=defaults['subject'],
            body=defaults['body'],
            attach_pdf=True,
        ))
    db.session.flush()


def list_email_templates():
    seed_email_templates()
    rows = {r.event_key: r for r in ProcEmailTemplate.query.all()}
    out = []
    for key in EMAIL_EVENT_KEYS:
        row = rows.get(key)
        item = row.to_dict() if row else {
            'event_key': key, 'to_emails': '', 'cc_emails': '',
            'subject': EMAIL_DEFAULTS[key]['subject'],
            'body': EMAIL_DEFAULTS[key]['body'],
            'attach_pdf': True,
        }
        item['label'] = EMAIL_DEFAULTS[key]['label']
        out.append(item)
    return out


def save_email_template(event_key, *, to_emails='', cc_emails='', subject=None, body=None, attach_pdf=None):
    if event_key not in EMAIL_EVENT_KEYS:
        raise ValueError('Unknown email event')
    seed_email_templates()
    row = ProcEmailTemplate.query.filter_by(event_key=event_key).first()
    if not row:
        row = ProcEmailTemplate(event_key=event_key)
        db.session.add(row)
    row.to_emails = (to_emails or '').strip()
    row.cc_emails = (cc_emails or '').strip()
    if subject is not None:
        row.subject = (subject or '').strip() or EMAIL_DEFAULTS[event_key]['subject']
    if body is not None:
        row.body = body if str(body).strip() else EMAIL_DEFAULTS[event_key]['body']
    elif not row.body:
        row.body = EMAIL_DEFAULTS[event_key]['body']
    if not row.subject:
        row.subject = EMAIL_DEFAULTS[event_key]['subject']
    if attach_pdf is not None:
        row.attach_pdf = bool(attach_pdf)
    elif row.attach_pdf is None:
        row.attach_pdf = True
    return row


def reset_email_template(event_key):
    defaults = EMAIL_DEFAULTS.get(event_key)
    if not defaults:
        raise ValueError('Unknown email event')
    return save_email_template(
        event_key, to_emails='', cc_emails='',
        subject=defaults['subject'], body=defaults['body'], attach_pdf=True,
    )


def _parse_emails(raw: str) -> list[str]:
    parts = re.split(r'[,\s;]+', raw or '')
    return [p.strip() for p in parts if '@' in p]


def _fill(template: str, ctx: dict) -> str:
    text = template or ''
    for key, val in ctx.items():
        text = text.replace('{' + key + '}', str(val or ''))
    return text


def _email_context(pr: ProcPurchaseRequest, approve_url='') -> dict:
    return {
        'pr_id': pr.public_id,
        'property': pr.property.name if pr.property else 'Unassigned',
        'total': f'AED {float(pr.total_aed or 0):,.2f}',
        'status': (pr.status or '').replace('_', ' '),
        'approve_url': approve_url or '',
        'supplier': pr.supplier.name if pr.supplier else '',
    }


def _event_attachments(pr: ProcPurchaseRequest, event_key: str) -> list[str]:
    paths = []
    if event_key == 'quotation_for_approval':
        paths.append(_pr_pdf_path(pr))
        paths.extend(d.original_path for d in quotation_docs(pr))
    elif event_key == 'quotation_approved':
        pr_pdf = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind='pr_pdf').first()
        if pr_pdf and pr_pdf.stamped_path:
            paths.append(pr_pdf.stamped_path)
        stamped = next(
            (d for d in quotation_docs(pr) if d.status == 'approved' and d.stamped_path),
            None,
        )
        if stamped:
            paths.append(stamped.stamped_path)
    elif event_key == 'invoice_for_approval':
        inv = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind='invoice').first()
        if inv:
            paths.append(inv.original_path)
    elif event_key == 'invoice_approved':
        inv = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind='invoice').first()
        if inv:
            paths.append(inv.stamped_path or inv.original_path)
    return [p for p in paths if p]


def send_pr_event_email(pr: ProcPurchaseRequest, event_key: str, *, approve_url='', attachments=None):
    seed_email_templates()
    row = ProcEmailTemplate.query.filter_by(event_key=event_key).first()
    defaults = EMAIL_DEFAULTS[event_key]
    to_list = _parse_emails(row.to_emails if row else '')
    if not to_list:
        logger.info('PR email %s skipped — no To recipients for %s', event_key, pr.public_id)
        return False
    cc_list = _parse_emails(row.cc_emails if row else '')
    ctx = _email_context(pr, approve_url=approve_url)
    subject = _fill((row.subject if row and row.subject else defaults['subject']), ctx)
    body = _fill((row.body if row and (row.body or '').strip() else defaults['body']), ctx)
    if 'Kynvera' not in body:
        body = body.rstrip() + '\n\n—\nKynvera Procurement'
    html = '<pre style="font-family:inherit;white-space:pre-wrap;">' + (
        body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    ) + '</pre>'
    attach_on = True if row is None else row.attach_pdf is not False
    if not attach_on:
        paths = []
    elif attachments is not None:
        paths = [p for p in attachments if p and os.path.isfile(p)]
    else:
        paths = [p for p in _event_attachments(pr, event_key) if os.path.isfile(p)]
    return send_email(
        to_list[0],
        subject,
        body,
        html_body=html,
        cc=(cc_list + to_list[1:]) or None,
        attachments=paths or None,
        source='procurement_pr',
        related_id=pr.public_id,
    )


def approve_url_for_token(raw: str) -> str:
    try:
        path = url_for('procurement_module.doc_approve_page', token=raw)
    except Exception:
        path = f'/procurement/doc-approve/{raw}'
    base = (current_app.config.get('APP_BASE_URL') or '').rstrip('/')
    if base:
        return base + path
    return path


def pick_quotation_for_approval(pr: ProcPurchaseRequest, kind: str | None = None) -> ProcPurchaseDocument:
    pending = [d for d in quotation_docs(pr) if d.status == 'pending_approval']
    if kind:
        match = next((d for d in pending if d.kind == kind), None)
        if not match:
            raise ValueError('Choose a quotation that is waiting for approval')
        return match
    if len(pending) == 1:
        return pending[0]
    if not pending:
        raise ValueError('No quotation is waiting for approval')
    raise ValueError('Choose which quotation to approve')


def send_quotations_for_approval(pr: ProcPurchaseRequest) -> str | None:
    """Procurement sends 1–3 uploaded quotations for GM or system-admin approval. Does not stamp yet."""
    docs = quotation_docs(pr)
    if not docs:
        raise ValueError('Upload at least one quotation before sending for approval')
    if pr.status != 'awaiting_quotation':
        raise ValueError('Quotations have already been sent for approval')
    for doc in docs:
        doc.status = 'pending_approval'
    raw = issue_approval_token(docs[0])
    pr.status = 'gm_review'
    url = approve_url_for_token(raw)
    send_pr_event_email(pr, 'quotation_for_approval', approve_url=url)
    return raw


def begin_quotation_review(pr: ProcPurchaseRequest, doc: ProcPurchaseDocument) -> str | None:
    """Kept for older call sites; sending to GM is explicit now."""
    return send_quotations_for_approval(pr)


def begin_invoice_review(pr: ProcPurchaseRequest, doc: ProcPurchaseDocument) -> str | None:
    """Every supplier invoice waits for GM or system-admin approval before the stamp."""
    doc.status = 'pending_approval'
    raw = issue_approval_token(doc)
    url = approve_url_for_token(raw)
    send_pr_event_email(pr, 'invoice_for_approval', approve_url=url)
    return raw


def _pr_pdf_path(pr: ProcPurchaseRequest):
    doc = ProcPurchaseDocument.query.filter_by(request_id=pr.id, kind='pr_pdf').first()
    return doc.original_path if doc else None


def absolute_file(doc: ProcPurchaseDocument, stamped=False) -> str | None:
    path = doc.stamped_path if stamped else doc.original_path
    if path and os.path.isfile(path):
        return path
    return None
