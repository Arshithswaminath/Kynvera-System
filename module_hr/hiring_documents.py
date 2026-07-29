"""
Hiring Document Tracker — HR-only checklist for onboarding documents.
Routes registered on hr_bp via register_hiring_document_routes().
"""
from __future__ import annotations

import logging
import mimetypes
import os
import urllib.request
from typing import Optional

from io import BytesIO

from flask import (
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    stream_with_context,
)
from flask_jwt_extended import jwt_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app.models import (
    HIRING_DOC_ALLOWED_EXT,
    HIRING_DOC_TYPES,
    HIRING_PIPELINE_DEFAULT,
    HIRING_PIPELINE_LABELS,
    HIRING_PIPELINE_STATUSES,
    HIRING_PIPELINE_STEPS,
    HIRING_VISA_GATED_DOC_TYPES,
    HiringCandidate,
    HiringDocument,
    Submission,
    User,
    db,
)
from common.datetime_utils import utc_now_naive
from common.error_responses import error_response, success_response
from common.utils import ensure_dir, save_uploaded_file_cloud
from config import GENERATED_DIR, MAX_UPLOAD_FILESIZE

logger = logging.getLogger(__name__)

HIRING_DOCS_DIR = os.path.join(GENERATED_DIR, 'hiring_docs')

STATUS_LABELS = {
    'not_started': 'Not Started',
    'in_progress': 'In Progress',
    'complete': 'Complete',
}


def _role_is_admin(user: Optional[User]) -> bool:
    return bool(user and getattr(user, 'role', None) == 'admin')


def _user_desig_lc(user: Optional[User]) -> str:
    return (getattr(user, 'designation', None) or '').strip().lower()


def user_can_manage_hiring_docs(user: Optional[User]) -> bool:
    """HR staff who may manage the hiring document tracker."""
    if not user:
        return False
    if _role_is_admin(user):
        return True
    if getattr(user, 'access_hr', False):
        return True
    return _user_desig_lc(user) == 'hr_manager'


def _get_current_user():
    from module_hr.routes import get_current_user
    return get_current_user()


def _require_hiring_user():
    user = _get_current_user()
    if not user:
        return None, error_response('User not found', status_code=404, error_code='NOT_FOUND')
    if not user_can_manage_hiring_docs(user):
        return None, error_response('Access denied', status_code=403, error_code='ACCESS_DENIED')
    return user, None


def _hiring_docs_dir() -> str:
    path = current_app.config.get('HIRING_DOCS_DIR') or HIRING_DOCS_DIR
    ensure_dir(path)
    return path


def _seed_documents(candidate: HiringCandidate) -> None:
    """Ensure all fixed doc slots exist. Append via relationship so the
    in-memory collection stays in sync (session.add alone does not)."""
    if candidate.documents is None:
        candidate.documents = []
    existing = {d.doc_type for d in candidate.documents}
    for doc_type in HIRING_DOC_TYPES:
        if doc_type in existing:
            continue
        candidate.documents.append(HiringDocument(
            doc_type=doc_type,
            status='missing',
        ))


def _ext_of(filename: str) -> str:
    return (filename.rsplit('.', 1)[1].lower() if filename and '.' in filename else '')


def _is_remote_url(path: Optional[str]) -> bool:
    return bool(path and str(path).startswith(('http://', 'https://')))


def _unlink_local(path: Optional[str]) -> None:
    if not path or _is_remote_url(path):
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError as e:
        logger.warning('Could not remove hiring doc file %s: %s', path, e)


def _clear_document_file(doc: HiringDocument) -> None:
    _unlink_local(doc.file_path)
    doc.filename = None
    doc.file_path = None
    doc.cloud_url = None
    doc.mime_type = None
    doc.file_size = None
    doc.uploaded_at = None
    doc.uploaded_by = None
    doc.status = 'missing'


def _stream_remote(url: str, filename: str):
    fn = secure_filename(filename or 'document') or 'document'
    mime, _ = mimetypes.guess_type(fn)

    def generate():
        req = urllib.request.Request(url, headers={'User-Agent': 'Injaaz-HiringDocs/1.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype=mime or 'application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename="{fn}"'},
    )


def _candidate_matches_status(candidate: HiringCandidate, status_filter: str) -> bool:
    _, _, status = candidate.progress()
    if not status_filter or status_filter == 'all':
        return True
    if status_filter == 'pending':
        return status in ('not_started', 'in_progress')
    if status_filter == 'complete':
        return status == 'complete'
    return status == status_filter


def register_hiring_document_routes(hr_bp):
    """Attach hiring document tracker routes to the HR blueprint."""

    # ── Pages ──────────────────────────────────────────────────────────────

    @hr_bp.route('/hiring')
    @jwt_required()
    def hiring_dashboard():
        user = _get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user_can_manage_hiring_docs(user):
            return jsonify({'error': 'Access denied'}), 403
        return render_template(
            'hr_hiring_dashboard.html',
            user=user,
            hiring_active='documents',
        )

    @hr_bp.route('/hiring/candidates/<int:candidate_id>')
    @jwt_required()
    def hiring_candidate_detail(candidate_id):
        user = _get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user_can_manage_hiring_docs(user):
            return jsonify({'error': 'Access denied'}), 403
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        return render_template(
            'hr_hiring_candidate_detail.html',
            user=user,
            candidate=candidate,
            hiring_active='documents',
        )

    # ── API: candidates ────────────────────────────────────────────────────

    @hr_bp.route('/api/hiring/candidates', methods=['GET'])
    @jwt_required()
    def api_list_hiring_candidates():
        user, err = _require_hiring_user()
        if err:
            return err

        q = (request.args.get('q') or '').strip()
        status_filter = (request.args.get('status') or 'all').strip().lower()
        pipeline_filter = (request.args.get('pipeline') or 'all').strip().lower()
        page = max(1, int(request.args.get('page') or 1))
        per_page = min(50, max(1, int(request.args.get('per_page') or 10)))

        query = HiringCandidate.query
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                HiringCandidate.full_name.ilike(like),
                HiringCandidate.role.ilike(like),
                HiringCandidate.department.ilike(like),
                HiringCandidate.email.ilike(like),
                HiringCandidate.replacement_name.ilike(like),
                HiringCandidate.replacement_employee_id.ilike(like),
            ))
        if pipeline_filter and pipeline_filter != 'all':
            if pipeline_filter in HIRING_PIPELINE_STATUSES:
                query = query.filter(HiringCandidate.pipeline_status == pipeline_filter)
        # Stable secondary key (id) prevents the same row appearing on two pages
        # when several candidates share the same updated_at.
        candidates = query.order_by(
            HiringCandidate.updated_at.desc(),
            HiringCandidate.id.desc(),
        ).all()
        filtered = [c for c in candidates if _candidate_matches_status(c, status_filter)]
        total = len(filtered)
        start = (page - 1) * per_page
        page_items = filtered[start:start + per_page]

        return success_response({
            'candidates': [c.to_dict(include_documents=False) for c in page_items],
            'count': total,
            'page': page,
            'per_page': per_page,
            'pages': max(1, (total + per_page - 1) // per_page) if total else 1,
            'status_labels': STATUS_LABELS,
            'pipeline_labels': HIRING_PIPELINE_LABELS,
            'pipeline_steps': list(HIRING_PIPELINE_STEPS),
            'pipeline_statuses': list(HIRING_PIPELINE_STATUSES),
        })

    @hr_bp.route('/api/hiring/candidates', methods=['POST'])
    @jwt_required()
    def api_create_hiring_candidate():
        user, err = _require_hiring_user()
        if err:
            return err

        data = request.get_json(silent=True) or {}
        full_name = (data.get('full_name') or '').strip()
        if not full_name:
            return error_response('Full name is required', status_code=400, error_code='VALIDATION_ERROR')
        role = (data.get('role') or data.get('position') or '').strip()
        if not role:
            return error_response('Role / position is required', status_code=400, error_code='VALIDATION_ERROR')

        candidate = HiringCandidate(
            full_name=full_name,
            role=role,
            department=(data.get('department') or '').strip() or None,
            phone=(data.get('phone') or '').strip() or None,
            email=(data.get('email') or '').strip() or None,
            replacement_name=(data.get('replacement_name') or '').strip() or None,
            replacement_employee_id=(data.get('replacement_employee_id') or '').strip() or None,
            comments=(data.get('comments') or '').strip() or None,
            pipeline_status=HIRING_PIPELINE_DEFAULT,
            created_by=user.id,
        )
        db.session.add(candidate)
        db.session.flush()
        _seed_documents(candidate)
        db.session.commit()
        db.session.refresh(candidate)
        return success_response({'candidate': candidate.to_dict()}, message='Candidate created', status_code=201)

    @hr_bp.route('/api/hiring/interview-assessments', methods=['GET'])
    @jwt_required()
    def api_list_interview_assessments_for_hiring():
        """List Interview Assessment submissions so HR can prefill a hiring candidate.

        Reads structured form_data (candidate_name, position_title) — not OCR of PDFs.
        """
        user, err = _require_hiring_user()
        if err:
            return err

        q = (request.args.get('q') or '').strip().lower()
        limit = min(50, max(1, int(request.args.get('limit') or 30)))

        rows = (
            Submission.query
            .filter(Submission.module_type == 'hr_interview_assessment')
            .order_by(Submission.created_at.desc())
            .limit(120)
            .all()
        )

        items = []
        for sub in rows:
            fd = sub.form_data if isinstance(sub.form_data, dict) else {}
            name = (fd.get('candidate_name') or fd.get('employee_name') or '').strip()
            role = (fd.get('position_title') or fd.get('position_applied') or '').strip()
            if not name:
                continue
            if q and q not in name.lower() and q not in role.lower():
                continue
            items.append({
                'submission_id': sub.id,
                'submission_ref': sub.submission_id,
                'full_name': name,
                'role': role,
                'interview_date': (fd.get('interview_date') or '').strip() or None,
                'interview_by': (fd.get('interview_by') or '').strip() or None,
                'workflow_status': sub.workflow_status or sub.status,
                'created_at': sub.created_at.isoformat() if sub.created_at else None,
            })
            if len(items) >= limit:
                break

        return success_response({'assessments': items, 'count': len(items)})

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>', methods=['GET'])
    @jwt_required()
    def api_get_hiring_candidate(candidate_id):
        user, err = _require_hiring_user()
        if err:
            return err
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')
        _seed_documents(candidate)
        db.session.commit()
        db.session.refresh(candidate)
        return success_response({'candidate': candidate.to_dict()})

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>', methods=['PATCH'])
    @jwt_required()
    def api_update_hiring_candidate(candidate_id):
        user, err = _require_hiring_user()
        if err:
            return err
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(silent=True) or {}
        if 'full_name' in data:
            name = (data.get('full_name') or '').strip()
            if not name:
                return error_response('Full name is required', status_code=400, error_code='VALIDATION_ERROR')
            candidate.full_name = name
        if 'role' in data or 'position' in data:
            candidate.role = (data.get('role') or data.get('position') or '').strip() or None
        if 'department' in data:
            candidate.department = (data.get('department') or '').strip() or None
        if 'phone' in data:
            candidate.phone = (data.get('phone') or '').strip() or None
        if 'email' in data:
            candidate.email = (data.get('email') or '').strip() or None
        if 'replacement_name' in data:
            candidate.replacement_name = (data.get('replacement_name') or '').strip() or None
        if 'replacement_employee_id' in data:
            candidate.replacement_employee_id = (
                (data.get('replacement_employee_id') or '').strip() or None
            )
        if 'comments' in data:
            comments = (data.get('comments') or '').strip()
            if len(comments) > 4000:
                return error_response(
                    'Comments must be 4000 characters or fewer',
                    status_code=400,
                    error_code='VALIDATION_ERROR',
                )
            candidate.comments = comments or None
        if 'pipeline_status' in data:
            pipeline = (data.get('pipeline_status') or '').strip()
            if pipeline not in HIRING_PIPELINE_STATUSES:
                return error_response(
                    'Invalid pipeline status',
                    status_code=400,
                    error_code='VALIDATION_ERROR',
                )
            candidate.pipeline_status = pipeline
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'candidate': candidate.to_dict()}, message='Candidate updated')

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>', methods=['DELETE'])
    @jwt_required()
    def api_delete_hiring_candidate(candidate_id):
        user, err = _require_hiring_user()
        if err:
            return err
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        for doc in list(candidate.documents or []):
            _clear_document_file(doc)
        db.session.delete(candidate)
        db.session.commit()
        return success_response(message='Candidate deleted')

    # ── API: documents ─────────────────────────────────────────────────────

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>/mark-all-documents-submitted', methods=['POST'])
    @jwt_required()
    def api_mark_all_hiring_documents_submitted(candidate_id):
        """Mark every document slot complete (received/uploaded; PCC attested). Keeps existing files."""
        user, err = _require_hiring_user()
        if err:
            return err

        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        _seed_documents(candidate)
        db.session.flush()

        updated = 0
        for doc in list(candidate.documents or []):
            if HiringCandidate.doc_is_complete(doc):
                continue
            if doc.doc_type == 'pcc':
                doc.status = 'attested'
            else:
                doc.status = 'uploaded'
            if not doc.uploaded_at:
                doc.uploaded_at = utc_now_naive()
            if not doc.uploaded_by:
                doc.uploaded_by = user.id
            updated += 1

        candidate.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(candidate)
        return success_response({
            'candidate': candidate.to_dict(),
            'updated': updated,
        }, message='All documents marked as submitted')

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>/documents/<doc_type>', methods=['POST'])
    @jwt_required()
    def api_upload_hiring_document(candidate_id, doc_type):
        user, err = _require_hiring_user()
        if err:
            return err

        doc_type = (doc_type or '').strip().lower()
        if doc_type not in HIRING_DOC_TYPES:
            return error_response('Invalid document type', status_code=400, error_code='VALIDATION_ERROR')

        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        _seed_documents(candidate)
        db.session.flush()

        if doc_type in HIRING_VISA_GATED_DOC_TYPES and not candidate.visa_docs_unlocked():
            return error_response(
                'Insurance, e-visa, and contract unlock after status is Visa process started',
                status_code=400,
                error_code='PIPELINE_LOCKED',
            )

        doc = next((d for d in candidate.documents if d.doc_type == doc_type), None)
        if not doc:
            return error_response('Document slot not found', status_code=404, error_code='NOT_FOUND')

        file_storage = request.files.get('file') or request.files.get('photo')
        if not file_storage or not file_storage.filename:
            return error_response('No file uploaded', status_code=400, error_code='VALIDATION_ERROR')

        ext = _ext_of(file_storage.filename)
        allowed = HIRING_DOC_ALLOWED_EXT.get(doc_type, set())
        if ext not in allowed:
            return error_response(
                f'File type .{ext or "unknown"} not allowed. Allowed: {", ".join(sorted(allowed))}',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        file_storage.seek(0, os.SEEK_END)
        size = file_storage.tell()
        file_storage.seek(0)
        max_bytes = MAX_UPLOAD_FILESIZE if MAX_UPLOAD_FILESIZE else 10 * 1024 * 1024
        if size > max_bytes:
            return error_response('File too large', status_code=413, error_code='FILE_TOO_LARGE')

        uploads_dir = _hiring_docs_dir()
        try:
            result = save_uploaded_file_cloud(file_storage, uploads_dir, folder='hiring_docs')
        except Exception as e:
            logger.exception('Hiring document upload failed: %s', e)
            return error_response('Upload failed', status_code=500, error_code='UPLOAD_FAILED')

        # Replace previous file
        _unlink_local(doc.file_path)

        is_cloud = bool(result.get('is_cloud'))
        cloud_url = result.get('url') if is_cloud else None
        local_path = result.get('local_path')
        stored_name = result.get('filename')
        if not is_cloud:
            if local_path and os.path.isfile(local_path):
                doc.file_path = local_path
            elif stored_name:
                doc.file_path = os.path.join(uploads_dir, stored_name)
            else:
                doc.file_path = None
            # Prefer absolute local path; cloud_url unused for local
            cloud_url = None
        else:
            doc.file_path = None

        original = secure_filename(file_storage.filename) or stored_name or f'{doc_type}.{ext}'
        mime = file_storage.mimetype or mimetypes.guess_type(original)[0]

        doc.filename = original
        doc.cloud_url = cloud_url
        doc.mime_type = mime
        doc.file_size = size
        doc.uploaded_at = utc_now_naive()
        doc.uploaded_by = user.id
        # PCC needs a separate attest step; others are complete on upload
        doc.status = 'uploaded'
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(candidate)

        return success_response({
            'document': doc.to_dict(),
            'candidate': candidate.to_dict(),
        }, message='Document uploaded')

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>/documents/<doc_type>/notes', methods=['PATCH'])
    @jwt_required()
    def api_update_hiring_document_notes(candidate_id, doc_type):
        """Update per-document notes. Currently only offer_letter supports notes in the UI."""
        user, err = _require_hiring_user()
        if err:
            return err

        doc_type = (doc_type or '').strip().lower()
        if doc_type != 'offer_letter':
            return error_response(
                'Notes are only supported for offer letter',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        _seed_documents(candidate)
        db.session.flush()

        doc = next((d for d in (candidate.documents or []) if d.doc_type == 'offer_letter'), None)
        if not doc:
            return error_response('Document slot not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(silent=True) or {}
        notes = (data.get('notes') or '').strip()
        if len(notes) > 2000:
            return error_response(
                'Offer letter comment max 2000 characters',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        doc.notes = notes or None
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(candidate)
        return success_response({
            'document': doc.to_dict(),
            'candidate': candidate.to_dict(),
        }, message='Offer letter comment saved')

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>/documents/<doc_type>/mark-received', methods=['POST'])
    @jwt_required()
    def api_mark_hiring_document_received(candidate_id, doc_type):
        """Mark a document slot as received without storing a file copy."""
        user, err = _require_hiring_user()
        if err:
            return err

        doc_type = (doc_type or '').strip().lower()
        if doc_type not in HIRING_DOC_TYPES:
            return error_response('Invalid document type', status_code=400, error_code='VALIDATION_ERROR')

        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        _seed_documents(candidate)
        db.session.flush()

        if doc_type in HIRING_VISA_GATED_DOC_TYPES and not candidate.visa_docs_unlocked():
            return error_response(
                'Insurance, e-visa, and contract unlock after status is Visa process started',
                status_code=400,
                error_code='PIPELINE_LOCKED',
            )

        doc = next((d for d in (candidate.documents or []) if d.doc_type == doc_type), None)
        if not doc:
            return error_response('Document slot not found', status_code=404, error_code='NOT_FOUND')

        # Received = checklist done with no copy in the system
        _clear_document_file(doc)
        doc.status = 'uploaded'
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(candidate)
        return success_response({
            'document': doc.to_dict(),
            'candidate': candidate.to_dict(),
        }, message='Marked as received (no file in system)')

    @hr_bp.route('/api/hiring/candidates/<int:candidate_id>/documents/<doc_type>/attest', methods=['POST'])
    @jwt_required()
    def api_attest_hiring_document(candidate_id, doc_type):
        user, err = _require_hiring_user()
        if err:
            return err

        doc_type = (doc_type or '').strip().lower()
        if doc_type != 'pcc':
            return error_response('Only PCC can be marked attested', status_code=400, error_code='VALIDATION_ERROR')

        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')

        doc = next((d for d in (candidate.documents or []) if d.doc_type == 'pcc'), None)
        if not doc or not doc.has_file():
            return error_response('Upload PCC before marking attested', status_code=400, error_code='VALIDATION_ERROR')

        doc.status = 'attested'
        candidate.updated_at = utc_now_naive()
        db.session.commit()
        db.session.refresh(candidate)
        return success_response({
            'document': doc.to_dict(),
            'candidate': candidate.to_dict(),
        }, message='PCC marked as attested')

    @hr_bp.route('/api/hiring/documents/<int:doc_id>/file', methods=['GET'])
    @jwt_required()
    def api_serve_hiring_document(doc_id):
        user, err = _require_hiring_user()
        if err:
            return err

        doc = db.session.get(HiringDocument, doc_id)
        if not doc or not doc.has_file():
            return error_response('Document file not found', status_code=404, error_code='NOT_FOUND')

        if doc.cloud_url and _is_remote_url(doc.cloud_url):
            return _stream_remote(doc.cloud_url, doc.filename or 'document')

        path = doc.file_path
        if path and _is_remote_url(path):
            return _stream_remote(path, doc.filename or 'document')
        if not path or not os.path.isfile(path):
            return error_response('Document file not found', status_code=404, error_code='NOT_FOUND')

        mime = doc.mime_type or mimetypes.guess_type(doc.filename or '')[0] or 'application/octet-stream'
        return send_file(
            path,
            as_attachment=True,
            download_name=doc.filename or 'document',
            mimetype=mime,
        )

    @hr_bp.route('/api/hiring/documents/<int:doc_id>', methods=['DELETE'])
    @jwt_required()
    def api_delete_hiring_document(doc_id):
        user, err = _require_hiring_user()
        if err:
            return err

        doc = db.session.get(HiringDocument, doc_id)
        if not doc:
            return error_response('Document not found', status_code=404, error_code='NOT_FOUND')

        candidate = doc.candidate
        _clear_document_file(doc)
        if candidate:
            candidate.updated_at = utc_now_naive()
        db.session.commit()
        payload = {'document': doc.to_dict()}
        if candidate:
            payload['candidate'] = candidate.to_dict()
        return success_response(payload, message='Document cleared')

    # ── API: Excel template / export / import ───────────────────────────────

    @hr_bp.route('/api/hiring/import-template', methods=['GET'])
    @jwt_required()
    def api_hiring_import_template():
        user, err = _require_hiring_user()
        if err:
            return err
        from module_hr.hiring_excel import build_hiring_template_bytes

        data = build_hiring_template_bytes()
        return send_file(
            BytesIO(data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='Hiring_Document_Tracker_Template.xlsx',
        )

    @hr_bp.route('/api/hiring/export', methods=['GET'])
    @jwt_required()
    def api_hiring_export():
        user, err = _require_hiring_user()
        if err:
            return err
        from module_hr.hiring_excel import build_hiring_template_bytes

        candidates = HiringCandidate.query.order_by(HiringCandidate.updated_at.desc()).all()
        data = build_hiring_template_bytes(candidates=candidates)
        return send_file(
            BytesIO(data),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='Hiring_Document_Tracker_Export.xlsx',
        )

    @hr_bp.route('/api/hiring/import', methods=['POST'])
    @jwt_required()
    def api_hiring_import():
        user, err = _require_hiring_user()
        if err:
            return err

        if 'file' not in request.files:
            return error_response('No file uploaded', status_code=400, error_code='VALIDATION_ERROR')
        file = request.files['file']
        if not file or not file.filename:
            return error_response('No file selected', status_code=400, error_code='VALIDATION_ERROR')

        from module_hr.hiring_excel import apply_hiring_import, parse_hiring_workbook

        try:
            rows = parse_hiring_workbook(file)
        except ImportError:
            return error_response(
                'Excel import requires pandas and openpyxl',
                status_code=500,
                error_code='SERVER_ERROR',
            )
        except ValueError as e:
            return error_response(str(e), status_code=400, error_code='VALIDATION_ERROR')
        except Exception as e:
            logger.exception('Hiring Excel parse failed')
            return error_response(
                f'Could not parse file: {e}',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

        try:
            result = apply_hiring_import(
                rows,
                user,
                seed_documents_fn=_seed_documents,
                clear_document_file_fn=_clear_document_file,
            )
        except ValueError as e:
            return error_response(str(e), status_code=400, error_code='VALIDATION_ERROR')
        except Exception as e:
            logger.exception('Hiring Excel import failed')
            return error_response(
                f'Import failed: {e}',
                status_code=500,
                error_code='SERVER_ERROR',
            )

        msg_parts = []
        if result['created']:
            msg_parts.append(f"{result['created']} created")
        if result['updated']:
            msg_parts.append(f"{result['updated']} updated")
        if result['skipped']:
            msg_parts.append(f"{result['skipped']} skipped")
        message = 'Import complete' + (': ' + ', '.join(msg_parts) if msg_parts else '')

        return success_response(result, message=message)
