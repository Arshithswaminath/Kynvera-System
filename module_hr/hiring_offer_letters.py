"""
Offer Letters / Letter of Intent register — HR inbox under Hiring Docs.
Routes registered on hr_bp via register_hiring_offer_letter_routes().
"""
from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import uuid
from typing import Optional

from flask import jsonify, render_template, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app.models import (
    HIRING_OFFER_LETTER_ALLOWED_EXT,
    HIRING_OFFER_LETTER_KIND_LABELS,
    HIRING_OFFER_LETTER_KINDS,
    HIRING_OFFER_LETTER_LINK_STATUSES,
    HIRING_PIPELINE_DEFAULT,
    HIRING_PIPELINE_STEPS,
    HiringCandidate,
    HiringOfferLetter,
    db,
)
from common.datetime_utils import utc_now_naive
from common.error_responses import error_response, success_response
from common.utils import save_uploaded_file_cloud
from config import MAX_UPLOAD_FILESIZE
from module_hr.hiring_documents import (
    _ext_of,
    _hiring_docs_dir,
    _is_remote_url,
    _require_hiring_user,
    _seed_documents,
    _stream_remote,
    _unlink_local,
    user_can_manage_hiring_docs,
)

logger = logging.getLogger(__name__)


def _get_current_user():
    from module_hr.routes import get_current_user
    return get_current_user()


def _as_bool(val, default=None):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if s in ('0', 'false', 'no', 'n', 'off', ''):
        return False
    return default


def _letter_or_404(letter_id):
    letter = db.session.get(HiringOfferLetter, letter_id)
    if not letter:
        return None, error_response('Offer letter not found', status_code=404, error_code='NOT_FOUND')
    return letter, None


def _apply_metadata(letter: HiringOfferLetter, data: dict, *, creating: bool = False):
    if creating or 'doc_kind' in data:
        kind = (data.get('doc_kind') or letter.doc_kind or 'letter_of_intent').strip()
        if kind not in HIRING_OFFER_LETTER_KINDS:
            return error_response(
                f'Invalid document type "{kind}"',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        letter.doc_kind = kind

    if creating or 'full_name' in data:
        name = (data.get('full_name') or '').strip()
        if not name:
            return error_response('Full name is required', status_code=400, error_code='VALIDATION_ERROR')
        letter.full_name = name

    if creating or 'role' in data:
        letter.role = (data.get('role') or '').strip() or None
    if creating or 'department' in data:
        letter.department = (data.get('department') or '').strip() or None
    if creating or 'phone' in data:
        letter.phone = (data.get('phone') or '').strip() or None
    if creating or 'email' in data:
        letter.email = (data.get('email') or '').strip() or None

    if creating or 'comments' in data:
        comments = (data.get('comments') or '').strip()
        if len(comments) > 4000:
            return error_response(
                'Comment must be 4000 characters or fewer',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        letter.comments = comments or None

    received_in_payload = 'received' in data
    if creating or received_in_payload:
        letter.received = bool(_as_bool(data.get('received'), False if creating else letter.received))

    # Explicitly clearing step 1 also clears the candidate response.
    if received_in_payload and not letter.received:
        letter.signed_back = False
        letter.not_accepted = False
        return None

    # Step 2 can arrive as candidate_outcome, or as signed_back / not_accepted flags.
    outcome = None
    if 'candidate_outcome' in data and data.get('candidate_outcome') is not None:
        outcome = str(data.get('candidate_outcome') or '').strip().lower()
        if outcome in ('pending', 'waiting', 'awaiting', 'awaiting_signature'):
            outcome = 'awaiting_signature'
        elif outcome in ('signed', 'signed_back', 'yes'):
            outcome = 'signed'
        elif outcome in ('not_accepted', 'declined', 'rejected', 'no'):
            outcome = 'not_accepted'
        elif outcome not in ('awaiting_signature', 'signed', 'not_accepted'):
            return error_response(
                'candidate_outcome must be awaiting_signature, signed, or not_accepted',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )

    if outcome is None:
        if creating or 'signed_back' in data:
            letter.signed_back = bool(
                _as_bool(data.get('signed_back'), False if creating else letter.signed_back)
            )
        if creating or 'not_accepted' in data:
            letter.not_accepted = bool(
                _as_bool(data.get('not_accepted'), False if creating else letter.not_accepted)
            )
    elif outcome == 'signed':
        letter.signed_back = True
        letter.not_accepted = False
    elif outcome == 'not_accepted':
        letter.signed_back = False
        letter.not_accepted = True
    else:
        letter.signed_back = False
        letter.not_accepted = False

    # Step 2 requires (and implies) the unsigned HR letter.
    if letter.signed_back or letter.not_accepted:
        letter.received = True
    if letter.signed_back and letter.not_accepted:
        letter.not_accepted = False
    if not letter.received:
        letter.signed_back = False
        letter.not_accepted = False
    return None


def _clear_scan(letter: HiringOfferLetter) -> None:
    _unlink_local(letter.file_path)
    letter.filename = None
    letter.file_path = None
    letter.cloud_url = None
    letter.mime_type = None
    letter.file_size = None


def _clear_signed(letter: HiringOfferLetter) -> None:
    _unlink_local(letter.signed_file_path)
    letter.signed_filename = None
    letter.signed_file_path = None
    letter.signed_cloud_url = None
    letter.signed_mime_type = None
    letter.signed_file_size = None


def _store_upload(letter: HiringOfferLetter, file_storage, *, signed: bool, user) -> Optional[tuple]:
    if not file_storage or not file_storage.filename:
        return error_response('No file uploaded', status_code=400, error_code='VALIDATION_ERROR')

    ext = _ext_of(file_storage.filename)
    if ext not in HIRING_OFFER_LETTER_ALLOWED_EXT:
        return error_response(
            f'File type .{ext or "unknown"} not allowed. Allowed: '
            f'{", ".join(sorted(HIRING_OFFER_LETTER_ALLOWED_EXT))}',
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
        logger.exception('Offer letter upload failed: %s', e)
        return error_response('Upload failed', status_code=500, error_code='UPLOAD_FAILED')

    is_cloud = bool(result.get('is_cloud'))
    cloud_url = result.get('url') if is_cloud else None
    local_path = result.get('local_path')
    stored_name = result.get('filename')
    if not is_cloud:
        if local_path and os.path.isfile(local_path):
            path = local_path
        elif stored_name:
            path = os.path.join(uploads_dir, stored_name)
        else:
            path = None
        cloud_url = None
    else:
        path = None

    original = secure_filename(file_storage.filename) or stored_name or f'offer.{ext}'
    mime = file_storage.mimetype or mimetypes.guess_type(original)[0]

    if signed:
        _clear_signed(letter)
        letter.signed_filename = original
        letter.signed_file_path = path
        letter.signed_cloud_url = cloud_url
        letter.signed_mime_type = mime
        letter.signed_file_size = size
        letter.signed_back = True
        letter.not_accepted = False
        letter.received = True
    else:
        _clear_scan(letter)
        letter.filename = original
        letter.file_path = path
        letter.cloud_url = cloud_url
        letter.mime_type = mime
        letter.file_size = size
        letter.received = True
    letter.updated_at = utc_now_naive()
    return None


def _copy_best_file_to_offer_slot(letter: HiringOfferLetter, candidate: HiringCandidate, user) -> None:
    """Copy signed copy (else HR scan) onto the candidate's offer_letter document slot."""
    _seed_documents(candidate)
    db.session.flush()
    doc = next((d for d in (candidate.documents or []) if d.doc_type == 'offer_letter'), None)
    if not doc:
        return

    kind = letter.best_file_kind()
    if kind == 'signed':
        filename = letter.signed_filename
        src_path = letter.signed_file_path
        cloud_url = letter.signed_cloud_url
        mime_type = letter.signed_mime_type
        file_size = letter.signed_file_size
    elif kind == 'scan':
        filename = letter.filename
        src_path = letter.file_path
        cloud_url = letter.cloud_url
        mime_type = letter.mime_type
        file_size = letter.file_size
    else:
        if letter.received and not doc.has_file():
            doc.status = 'uploaded'
            if not doc.uploaded_at:
                doc.uploaded_at = utc_now_naive()
            if not doc.uploaded_by and user:
                doc.uploaded_by = user.id
        if letter.comments and not (doc.notes or '').strip():
            doc.notes = letter.comments
        return

    dest_path = None
    if cloud_url and _is_remote_url(cloud_url):
        dest_path = None
    elif src_path and _is_remote_url(src_path):
        cloud_url = src_path
        dest_path = None
    elif src_path and os.path.isfile(src_path):
        uploads_dir = _hiring_docs_dir()
        ext = os.path.splitext(src_path)[1] or os.path.splitext(filename or '')[1] or '.pdf'
        dest_path = os.path.join(
            uploads_dir,
            f'offer_link_{letter.id}_{uuid.uuid4().hex[:8]}{ext}',
        )
        shutil.copy2(src_path, dest_path)
        cloud_url = None
        if doc.file_path and doc.file_path != dest_path:
            _unlink_local(doc.file_path)
    else:
        if letter.comments and not (doc.notes or '').strip():
            doc.notes = letter.comments
        return

    doc.filename = filename
    doc.file_path = dest_path
    doc.cloud_url = cloud_url
    doc.mime_type = mime_type
    doc.file_size = file_size
    doc.status = 'uploaded'
    doc.uploaded_at = utc_now_naive()
    if user:
        doc.uploaded_by = user.id
    if letter.comments and not (doc.notes or '').strip():
        doc.notes = letter.comments


def _bump_pipeline(candidate: HiringCandidate, letter: HiringOfferLetter) -> None:
    if candidate.pipeline_index() < 0:
        return
    target = 'offer_letter_signed' if letter.signed_back else 'offer_letter_prepared'
    try:
        target_idx = HIRING_PIPELINE_STEPS.index(target)
    except ValueError:
        return
    if candidate.pipeline_index() < target_idx:
        candidate.pipeline_status = target


def _attach_to_candidate(letter: HiringOfferLetter, candidate: HiringCandidate, user) -> None:
    letter.hiring_candidate_id = candidate.id
    letter.link_status = 'linked'
    letter.updated_at = utc_now_naive()
    _copy_best_file_to_offer_slot(letter, candidate, user)
    _bump_pipeline(candidate, letter)
    candidate.updated_at = utc_now_naive()


def _detach_letter(letter: HiringOfferLetter) -> None:
    letter.hiring_candidate_id = None
    letter.link_status = 'unlinked'
    letter.updated_at = utc_now_naive()


def _create_candidate_from_letter(letter: HiringOfferLetter, user) -> HiringCandidate:
    role = (letter.role or '').strip() or 'Pending'
    candidate = HiringCandidate(
        full_name=letter.full_name,
        role=role,
        department=letter.department,
        phone=letter.phone,
        email=letter.email,
        comments=letter.comments,
        pipeline_status=HIRING_PIPELINE_DEFAULT,
        created_by=user.id if user else None,
    )
    db.session.add(candidate)
    db.session.flush()
    _seed_documents(candidate)
    db.session.flush()
    _attach_to_candidate(letter, candidate, user)
    return candidate


def _payload(letter: HiringOfferLetter) -> dict:
    db.session.refresh(letter)
    return letter.to_dict()


def register_hiring_offer_letter_routes(hr_bp):
    """Attach offer-letter register routes to the HR blueprint."""

    @hr_bp.route('/hiring/offer-letters')
    @jwt_required()
    def hiring_offer_letters_page():
        user = _get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user_can_manage_hiring_docs(user):
            return jsonify({'error': 'Access denied'}), 403
        return render_template(
            'hr_hiring_offer_letters.html',
            user=user,
            hiring_active='offer_letters',
            kind_labels=HIRING_OFFER_LETTER_KIND_LABELS,
        )

    @hr_bp.route('/api/hiring/offer-letters', methods=['GET'])
    @jwt_required()
    def api_list_hiring_offer_letters():
        user, err = _require_hiring_user()
        if err:
            return err

        q = (request.args.get('q') or '').strip()
        kind = (request.args.get('kind') or 'all').strip().lower()
        received = (request.args.get('received') or 'all').strip().lower()
        signed = (request.args.get('signed') or request.args.get('signed_back') or 'all').strip().lower()
        outcome = (request.args.get('outcome') or request.args.get('candidate_outcome') or 'all').strip().lower()
        link_status = (request.args.get('link_status') or 'all').strip().lower()
        page = max(1, int(request.args.get('page') or 1))
        per_page = min(50, max(1, int(request.args.get('per_page') or 20)))

        query = HiringOfferLetter.query
        if q:
            like = f'%{q}%'
            query = query.filter(or_(
                HiringOfferLetter.full_name.ilike(like),
                HiringOfferLetter.role.ilike(like),
                HiringOfferLetter.department.ilike(like),
                HiringOfferLetter.email.ilike(like),
                HiringOfferLetter.comments.ilike(like),
            ))
        if kind in HIRING_OFFER_LETTER_KINDS:
            query = query.filter(HiringOfferLetter.doc_kind == kind)
        if received in ('yes', 'true', '1'):
            query = query.filter(HiringOfferLetter.received.is_(True))
        elif received in ('no', 'false', '0'):
            query = query.filter(HiringOfferLetter.received.is_(False))
        if outcome in ('awaiting', 'awaiting_signature', 'waiting'):
            query = query.filter(
                HiringOfferLetter.received.is_(True),
                HiringOfferLetter.signed_back.is_(False),
                HiringOfferLetter.not_accepted.is_(False),
            )
        elif outcome in ('signed', 'signed_back'):
            query = query.filter(HiringOfferLetter.signed_back.is_(True))
        elif outcome in ('not_accepted', 'declined', 'rejected'):
            query = query.filter(HiringOfferLetter.not_accepted.is_(True))
        elif signed in ('yes', 'true', '1'):
            query = query.filter(HiringOfferLetter.signed_back.is_(True))
        elif signed in ('no', 'false', '0'):
            query = query.filter(HiringOfferLetter.signed_back.is_(False))
        if link_status in HIRING_OFFER_LETTER_LINK_STATUSES:
            query = query.filter(HiringOfferLetter.link_status == link_status)

        total = query.count()
        rows = (
            query.order_by(
                HiringOfferLetter.updated_at.desc(),
                HiringOfferLetter.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        pending_received = HiringOfferLetter.query.filter(
            HiringOfferLetter.received.is_(False)
        ).count()
        pending_signed = HiringOfferLetter.query.filter(
            HiringOfferLetter.received.is_(True),
            HiringOfferLetter.signed_back.is_(False),
            HiringOfferLetter.not_accepted.is_(False),
        ).count()
        not_accepted_count = HiringOfferLetter.query.filter(
            HiringOfferLetter.not_accepted.is_(True)
        ).count()
        unlinked = HiringOfferLetter.query.filter(
            HiringOfferLetter.link_status == 'unlinked'
        ).count()

        return success_response({
            'letters': [r.to_dict() for r in rows],
            'count': total,
            'page': page,
            'per_page': per_page,
            'pages': max(1, (total + per_page - 1) // per_page),
            'stats': {
                'pending_received': pending_received,
                'pending_signed': pending_signed,
                'not_accepted': not_accepted_count,
                'unlinked': unlinked,
            },
            'kind_labels': dict(HIRING_OFFER_LETTER_KIND_LABELS),
        })

    @hr_bp.route('/api/hiring/offer-letters', methods=['POST'])
    @jwt_required()
    def api_create_hiring_offer_letter():
        user, err = _require_hiring_user()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        letter = HiringOfferLetter(
            doc_kind='letter_of_intent',
            full_name='',
            received=False,
            signed_back=False,
            not_accepted=False,
            link_status='unlinked',
            created_by=user.id,
        )
        apply_err = _apply_metadata(letter, data, creating=True)
        if apply_err:
            return apply_err
        db.session.add(letter)
        db.session.commit()
        payload = _payload(letter)
        return success_response(
            {'letter': payload},
            message='Offer letter added',
            status_code=201,
        )

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>', methods=['GET'])
    @jwt_required()
    def api_get_hiring_offer_letter(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        return success_response({'letter': letter.to_dict()})

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>', methods=['PATCH'])
    @jwt_required()
    def api_update_hiring_offer_letter(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        data = request.get_json(silent=True) or {}
        apply_err = _apply_metadata(letter, data, creating=False)
        if apply_err:
            return apply_err
        letter.updated_at = utc_now_naive()
        if letter.hiring_candidate_id and letter.hiring_candidate:
            _copy_best_file_to_offer_slot(letter, letter.hiring_candidate, user)
            _bump_pipeline(letter.hiring_candidate, letter)
        db.session.commit()
        return success_response({'letter': _payload(letter)}, message='Saved')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>', methods=['DELETE'])
    @jwt_required()
    def api_delete_hiring_offer_letter(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        _clear_scan(letter)
        _clear_signed(letter)
        db.session.delete(letter)
        db.session.commit()
        return success_response(message='Offer letter deleted')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/scan', methods=['POST'])
    @jwt_required()
    def api_upload_offer_letter_scan(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        file_storage = request.files.get('file') or request.files.get('photo')
        up_err = _store_upload(letter, file_storage, signed=False, user=user)
        if up_err:
            return up_err
        if letter.hiring_candidate_id and letter.hiring_candidate:
            _copy_best_file_to_offer_slot(letter, letter.hiring_candidate, user)
            _bump_pipeline(letter.hiring_candidate, letter)
        db.session.commit()
        return success_response({'letter': _payload(letter)}, message='Scan uploaded')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/signed', methods=['POST'])
    @jwt_required()
    def api_upload_offer_letter_signed(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        file_storage = request.files.get('file') or request.files.get('photo')
        up_err = _store_upload(letter, file_storage, signed=True, user=user)
        if up_err:
            return up_err
        if letter.hiring_candidate_id and letter.hiring_candidate:
            _copy_best_file_to_offer_slot(letter, letter.hiring_candidate, user)
            _bump_pipeline(letter.hiring_candidate, letter)
        db.session.commit()
        return success_response({'letter': _payload(letter)}, message='Signed copy uploaded')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/scan', methods=['DELETE'])
    @jwt_required()
    def api_clear_offer_letter_scan(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        _clear_scan(letter)
        letter.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'letter': _payload(letter)}, message='Scan cleared')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/signed', methods=['DELETE'])
    @jwt_required()
    def api_clear_offer_letter_signed(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        _clear_signed(letter)
        letter.updated_at = utc_now_naive()
        db.session.commit()
        return success_response({'letter': _payload(letter)}, message='Signed copy cleared')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/file', methods=['GET'])
    @jwt_required()
    def api_serve_offer_letter_file(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        kind = (request.args.get('kind') or 'scan').strip().lower()
        if kind == 'signed':
            filename = letter.signed_filename or 'signed-offer'
            cloud_url = letter.signed_cloud_url
            path = letter.signed_file_path
            mime = letter.signed_mime_type
        else:
            filename = letter.filename or 'offer-letter'
            cloud_url = letter.cloud_url
            path = letter.file_path
            mime = letter.mime_type

        if cloud_url and _is_remote_url(cloud_url):
            return _stream_remote(cloud_url, filename)
        if path and _is_remote_url(path):
            return _stream_remote(path, filename)
        if not path or not os.path.isfile(path):
            return error_response('Document file not found', status_code=404, error_code='NOT_FOUND')
        guessed = mime or mimetypes.guess_type(filename or '')[0] or 'application/octet-stream'
        return send_file(
            path,
            as_attachment=True,
            download_name=filename or 'document',
            mimetype=guessed,
        )

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/link', methods=['POST'])
    @jwt_required()
    def api_link_hiring_offer_letter(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        data = request.get_json(silent=True) or {}

        if _as_bool(data.get('manual'), False):
            letter.hiring_candidate_id = None
            letter.link_status = 'manual'
            letter.updated_at = utc_now_naive()
            db.session.commit()
            return success_response(
                {'letter': _payload(letter)},
                message='Marked for manual hiring',
            )

        if _as_bool(data.get('create_candidate'), False):
            candidate = _create_candidate_from_letter(letter, user)
            db.session.commit()
            return success_response({
                'letter': _payload(letter),
                'candidate': candidate.to_dict(),
            }, message='Hiring candidate created')

        raw_id = data.get('candidate_id')
        try:
            candidate_id = int(raw_id)
        except (TypeError, ValueError):
            return error_response(
                'Provide candidate_id, create_candidate, or manual',
                status_code=400,
                error_code='VALIDATION_ERROR',
            )
        candidate = db.session.get(HiringCandidate, candidate_id)
        if not candidate:
            return error_response('Candidate not found', status_code=404, error_code='NOT_FOUND')
        _attach_to_candidate(letter, candidate, user)
        db.session.commit()
        return success_response({
            'letter': _payload(letter),
            'candidate': candidate.to_dict(),
        }, message='Linked to hiring candidate')

    @hr_bp.route('/api/hiring/offer-letters/<int:letter_id>/unlink', methods=['POST'])
    @jwt_required()
    def api_unlink_hiring_offer_letter(letter_id):
        user, err = _require_hiring_user()
        if err:
            return err
        letter, missing = _letter_or_404(letter_id)
        if missing:
            return missing
        _detach_letter(letter)
        db.session.commit()
        return success_response({'letter': _payload(letter)}, message='Unlinked from hiring')
