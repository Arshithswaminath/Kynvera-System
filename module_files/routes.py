"""Files module routes — Finder UI + APIs + Google Drive OAuth."""

from __future__ import annotations

import logging
from itsdangerous import BadSignature, URLSafeSerializer

from urllib.parse import quote

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    send_file,
)
from io import BytesIO
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models import FilesItem, User, db
from common.error_responses import error_response, success_response
from module_files import drive_service
from module_files import service as files_service
from module_files import sync_job
from module_files.catalog import (
    expand_module_catalog,
    get_excel_template,
    get_module_catalog,
    list_catalog,
    list_excel_templates_for_user,
    user_can_see_excel_template,
)

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__, template_folder='templates')


def _current_user() -> User | None:
    uid = get_jwt_identity()
    if uid is None:
        return None
    try:
        return db.session.get(User, int(uid))
    except (TypeError, ValueError):
        return None


def user_can_use_files(user: User | None) -> bool:
    """Admins, access_files, or HR (Leave/Manpower feed Files)."""
    if not user:
        return False
    if user.role == 'admin':
        return True
    if getattr(user, 'access_files', False):
        return True
    if getattr(user, 'access_hr', False):
        return True
    return False


def _require_files_user():
    user = _current_user()
    if not user:
        return None, error_response('User not found', status_code=404)
    if not user_can_use_files(user):
        return None, error_response('Access denied to Files module', status_code=403)
    return user, None


def _state_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config.get('SECRET_KEY') or 'change-me', salt='files-drive-oauth')


# ── UI ──────────────────────────────────────────────────────────────────────

@files_bp.route('/')
@jwt_required()
def files_home():
    user, err = _require_files_user()
    if err:
        return err
    files_service.ensure_default_folders(created_by=user.id)
    return render_template('files_home.html', user=user, active_page='files')


# ── Catalog / tree ──────────────────────────────────────────────────────────

@files_bp.route('/api/catalog', methods=['GET'])
@jwt_required()
def api_catalog():
    user, err = _require_files_user()
    if err:
        return err
    module = (request.args.get('module') or '').strip().lower()
    if module:
        cat = get_module_catalog(module)
        if not cat:
            return error_response('Unknown module', status_code=404)
        try:
            cat = expand_module_catalog(module, cat, user=user)
        except Exception:
            logger.exception('expand_module_catalog failed for module=%s', module)
            cat = {**cat, 'options': list(cat.get('options') or [])}
        return success_response({'module': module, **cat})
    return success_response(list_catalog())


@files_bp.route('/api/tree', methods=['GET'])
@jwt_required()
def api_tree():
    user, err = _require_files_user()
    if err:
        return err
    tree = files_service.build_tree()
    tree['drive'] = drive_service.drive_status()
    return success_response(tree)


# ── Excel template library (local, Drive opt-in) ─────────────────────────────

@files_bp.route('/api/templates', methods=['GET'])
@jwt_required()
def api_templates_list():
    user, err = _require_files_user()
    if err:
        return err
    templates = list_excel_templates_for_user(user)
    return success_response({
        'templates': templates,
        'count': len(templates),
        'unsynced_count': files_service.count_unsynced_items(),
        'drive': drive_service.drive_status(),
    })


@files_bp.route('/api/templates/<template_id>/download', methods=['GET'])
@jwt_required()
def api_template_download(template_id):
    user, err = _require_files_user()
    if err:
        return err
    entry = get_excel_template(template_id)
    if not entry:
        return error_response('Template not found', status_code=404)
    if not user_can_see_excel_template(user, entry):
        return error_response('Access denied', status_code=403)
    try:
        data, filename, _display = files_service.build_excel_template_bytes(template_id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        logger.exception('template download failed id=%s', template_id)
        return error_response(f'Could not build template: {e}', status_code=500)
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name=filename,
        mimetype=files_service.XLSX_MIME,
    )


@files_bp.route('/api/templates/download-zip', methods=['POST'])
@jwt_required()
def api_templates_download_zip():
    user, err = _require_files_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    if not isinstance(ids, list):
        ids = []
    try:
        zip_bytes, zip_name = files_service.build_templates_zip(ids, user=user)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        logger.exception('template zip failed')
        return error_response(f'Could not build zip: {e}', status_code=500)
    return send_file(
        BytesIO(zip_bytes),
        as_attachment=True,
        download_name=zip_name,
        mimetype='application/zip',
    )


@files_bp.route('/api/templates/push-to-drive', methods=['POST'])
@jwt_required()
def api_templates_push_to_drive():
    user, err = _require_files_user()
    if err:
        return err
    status = drive_service.drive_status()
    if not status.get('connected'):
        return error_response('Connect Google Drive first', status_code=400)
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    if not isinstance(ids, list) or not ids:
        return error_response('Select at least one template', status_code=400)
    try:
        result = files_service.push_excel_templates_to_drive(
            ids, created_by=user.id, user=user
        )
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        logger.exception('push templates to drive failed')
        return error_response(str(e), status_code=500)
    saved = result['saved']
    synced = len(result.get('synced') or [])
    failed = result.get('failed') or []
    if not saved and failed:
        first = failed[0].get('error') or 'Could not push templates'
        return error_response(first, status_code=400)
    noun = 'template' if saved == 1 else 'templates'
    return success_response(
        {
            'items': [i.to_dict() for i in result['items']],
            'saved': saved,
            'synced': result.get('synced') or [],
            'failed': failed,
            'message': f'Pushed {synced} of {saved} {noun} to Google Drive.',
        },
        message=f'Pushed {synced} of {saved} {noun} to Google Drive',
    )


# ── Save from Leave / Manpower ──────────────────────────────────────────────

@files_bp.route('/api/save-from-module', methods=['POST'])
@jwt_required()
def api_save_from_module():
    user, err = _require_files_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    module = (data.get('module') or '').strip().lower()
    kinds = data.get('kinds')
    if not isinstance(kinds, list):
        kinds = []
    kind = (data.get('kind') or '').strip().lower()
    if kind and kind not in [str(k).strip().lower() for k in kinds]:
        kinds.append(kind)
    kinds = [str(k).strip().lower() for k in kinds if str(k or '').strip()]
    if not kinds:
        return error_response('Select at least one file to save', status_code=400)
    try:
        result = files_service.save_from_module_many(module, kinds, created_by=user.id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        logger.exception('save-from-module failed')
        return error_response(f'Could not save file: {e}', status_code=500)
    if not result['saved'] and result['failed']:
        first = result['failed'][0].get('error') or 'Could not save files'
        return error_response(first, status_code=400)
    folder_label = result.get('folder_label') or 'Files'
    saved = result['saved']
    noun = 'file' if saved == 1 else 'files'
    return success_response(
        {
            'item': result['items'][0].to_dict() if result['items'] else None,
            'items': [i.to_dict() for i in result['items']],
            'saved': saved,
            'failed': result['failed'],
            'folder_label': folder_label,
            'module': module,
            'module_label': (get_module_catalog(module) or {}).get('label') or module,
            'message': f'Saved {saved} {noun} to Files → {folder_label}. Open Files to sync to Google Drive.',
            'files_url': '/files/',
        },
        message=f'Saved {saved} {noun} to Files → {folder_label}',
    )


# ── Upload / folders / rename / download ────────────────────────────────────

@files_bp.route('/api/upload', methods=['POST'])
@jwt_required()
def api_upload():
    user, err = _require_files_user()
    if err:
        return err
    folder_id = request.form.get('folder_id') or request.args.get('folder_id')
    try:
        folder_id = int(folder_id)
    except (TypeError, ValueError):
        return error_response('folder_id is required', status_code=400)
    f = request.files.get('file')
    if not f or not f.filename:
        return error_response('file is required', status_code=400)
    try:
        item = files_service.save_upload(folder_id=folder_id, file_storage=f, created_by=user.id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        logger.exception('upload failed')
        return error_response(f'Upload failed: {e}', status_code=500)
    return success_response({'item': item.to_dict()})


@files_bp.route('/api/folders', methods=['POST'])
@jwt_required()
def api_create_folder():
    user, err = _require_files_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    parent_id = data.get('parent_id')
    if parent_id is not None:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            return error_response('Invalid parent_id', status_code=400)
    try:
        folder = files_service.create_folder(name, parent_id, created_by=user.id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    return success_response({'folder': folder.to_dict()})


@files_bp.route('/api/folders/<int:folder_id>', methods=['PATCH'])
@jwt_required()
def api_rename_folder(folder_id):
    user, err = _require_files_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        folder = files_service.rename_folder(folder_id, data.get('name'))
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    try:
        drive_service.rename_on_drive_folder(folder)
    except Exception:
        logger.exception('Drive folder rename skipped')
    return success_response({'folder': folder.to_dict()})


@files_bp.route('/api/items/<int:item_id>', methods=['PATCH'])
@jwt_required()
def api_rename_item(item_id):
    user, err = _require_files_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        item = files_service.rename_item(item_id, data.get('name'))
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    try:
        drive_service.rename_on_drive_item(item)
    except Exception:
        logger.exception('Drive item rename skipped')
    return success_response({'item': item.to_dict()})


@files_bp.route('/api/items/<int:item_id>', methods=['DELETE'])
@jwt_required()
def api_delete_item(item_id):
    user, err = _require_files_user()
    if err:
        return err
    try:
        result = files_service.delete_item(item_id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    drive_file_id = result.get('drive_file_id')
    drive_removed = result.get('drive_removed')
    # Backward-compatible: if service didn't attempt Drive yet, do it here
    if drive_file_id and drive_removed is None:
        try:
            drive_removed = bool(drive_service.delete_on_drive_item(drive_file_id))
        except Exception:
            logger.exception('Drive item delete skipped')
            drive_removed = False
    return success_response({
        'deleted': True,
        'id': item_id,
        'drive_removed': bool(drive_file_id) and bool(drive_removed),
        'had_drive_copy': bool(drive_file_id),
    })


@files_bp.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def api_delete_folder(folder_id):
    user, err = _require_files_user()
    if err:
        return err
    try:
        result = files_service.delete_folder(folder_id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    drive_stats = result.get('drive_stats') or {'drive_deleted': [], 'drive_failed': []}
    # If service didn't run Drive cleanup, do it here
    if (result.get('drive_file_ids') or result.get('drive_folder_ids')) and not result.get('drive_stats'):
        try:
            drive_stats = drive_service.delete_on_drive_ids(
                file_ids=result.get('drive_file_ids'),
                folder_ids=result.get('drive_folder_ids'),
            ) or drive_stats
        except Exception:
            logger.exception('Drive folder delete skipped')
    failed = drive_stats.get('drive_failed') or []
    had = bool(result.get('drive_file_ids') or result.get('drive_folder_ids'))
    return success_response({
        'deleted': True,
        'id': folder_id,
        'drive_removed': (not failed) if had else True,
        'drive_deleted_count': len(drive_stats.get('drive_deleted') or []),
        'drive_failed_count': len(failed),
        'had_drive_copies': had,
    })


@files_bp.route('/api/items/<int:item_id>/download', methods=['GET'])
@jwt_required()
def api_download_item(item_id):
    user, err = _require_files_user()
    if err:
        return err
    item = db.session.get(FilesItem, item_id)
    if not item:
        return error_response('File not found', status_code=404)
    try:
        path = files_service.resolve_item_abs_path(item)
    except FileNotFoundError:
        return error_response('File missing on disk', status_code=404)
    return send_file(
        path,
        as_attachment=True,
        download_name=item.filename,
        mimetype=item.mime_type or 'application/octet-stream',
    )


# ── Drive sync ──────────────────────────────────────────────────────────────

@files_bp.route('/api/drive/status', methods=['GET'])
@jwt_required()
def api_drive_status():
    user, err = _require_files_user()
    if err:
        return err
    return success_response(drive_service.drive_status())


@files_bp.route('/api/drive/connect', methods=['GET'])
@jwt_required()
def api_drive_connect():
    user, err = _require_files_user()
    if err:
        return err
    if user.role != 'admin' and not getattr(user, 'access_files', False):
        return error_response('Access denied', status_code=403)
    want_json = (
        request.args.get('redirect') == '0'
        or 'application/json' in (request.headers.get('Accept') or '')
    )
    try:
        code_verifier = drive_service.make_code_verifier()
        # Embed PKCE verifier in signed state so callback does not depend on Flask session cookies
        state = _state_serializer().dumps({'uid': user.id, 'cv': code_verifier})
        url = drive_service.build_auth_url(state, code_verifier)
    except Exception as e:
        if want_json:
            return error_response(str(e), status_code=400)
        return redirect('/files/?drive=error&msg=' + quote(str(e)[:80]))
    if want_json:
        return success_response({'auth_url': url})
    return redirect(url)


@files_bp.route('/api/drive/callback', methods=['GET'])
def drive_callback():
    """OAuth callback — no JWT (Google redirects here). State carries user id + PKCE verifier."""
    error = request.args.get('error')
    if error:
        return redirect('/files/?drive=error&msg=' + quote(str(error)[:80]))

    code = request.args.get('code')
    state = request.args.get('state') or ''
    if not code or not state:
        return redirect('/files/?drive=error&msg=missing_code')

    try:
        payload = _state_serializer().loads(state)
        user_id = int(payload.get('uid'))
        code_verifier = (payload.get('cv') or '').strip()
    except (BadSignature, TypeError, ValueError):
        return redirect('/files/?drive=error&msg=invalid_state')

    if not code_verifier:
        return redirect('/files/?drive=error&msg=missing_pkce_verifier_retry_connect')

    try:
        creds = drive_service.exchange_code(code, state, code_verifier=code_verifier)
        email = drive_service.fetch_email_from_creds(creds)
        drive_service.save_connection(creds, email=email, user_id=user_id)
    except Exception as e:
        logger.exception('Drive OAuth callback failed')
        return redirect('/files/?drive=error&msg=' + quote(str(e)[:80]))

    # Folder tree is created after redirect so Google login is not blocked on Drive API calls
    return redirect('/files/?drive=connected')


@files_bp.route('/api/drive/setup', methods=['POST'])
@jwt_required()
def api_drive_setup():
    """Create Kynvera Files + catalog folders on Drive after OAuth (non-blocking for login)."""
    user, err = _require_files_user()
    if err:
        return err
    status = drive_service.drive_status()
    if not status.get('connected'):
        return error_response('Connect Google Drive first', status_code=400)
    try:
        root_id = drive_service.ensure_drive_folder_tree()
    except Exception as e:
        logger.exception('Drive folder setup failed')
        return error_response(str(e), status_code=400)
    status = drive_service.drive_status()
    status['root_drive_folder_id'] = root_id
    return success_response(status)


@files_bp.route('/api/drive/disconnect', methods=['POST'])
@jwt_required()
def api_drive_disconnect():
    user, err = _require_files_user()
    if err:
        return err
    if user.role != 'admin':
        return error_response('Only admins can disconnect Google Drive', status_code=403)
    drive_service.disconnect()
    return success_response({'disconnected': True})


@files_bp.route('/api/items/<int:item_id>/sync', methods=['POST'])
@jwt_required()
def api_sync_item(item_id):
    user, err = _require_files_user()
    if err:
        return err
    try:
        item = drive_service.sync_item(item_id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        return error_response(str(e), status_code=400)
    return success_response({'item': item.to_dict()})


def _parse_sync_ids(data) -> list:
    ids = []
    raw = (data or {}).get('ids') if isinstance(data, dict) else None
    if raw is None:
        return ids
    if not isinstance(raw, list):
        return ids
    for x in raw:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n not in ids:
            ids.append(n)
    return ids


def _require_drive_ready():
    if not drive_service.drive_enabled():
        raise RuntimeError('Google Drive sync is disabled')
    if not drive_service.drive_configured():
        raise RuntimeError('Google Drive credentials are not configured')
    if not drive_service.get_connection():
        raise RuntimeError('Connect Google Drive first')


def _start_selected_sync(user, item_ids, folder_id=None):
    _require_drive_ready()
    return sync_job.start_sync_job(user.id, item_ids, folder_id=folder_id)


@files_bp.route('/api/sync-pending', methods=['POST'])
@jwt_required()
def api_sync_pending():
    """Legacy route — same as Sync now (selected ids only)."""
    return api_sync_now()


@files_bp.route('/api/sync-now', methods=['POST'])
@jwt_required()
def api_sync_now():
    user, err = _require_files_user()
    if err:
        return err
    ids = _parse_sync_ids(request.get_json(silent=True) or {})
    if not ids:
        return error_response('Select files to sync', status_code=400)
    try:
        result = _start_selected_sync(user, ids)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        return error_response(str(e), status_code=400)
    return success_response(result, status_code=202)


@files_bp.route('/api/sync-status', methods=['GET'])
@jwt_required()
def api_sync_status():
    user, err = _require_files_user()
    if err:
        return err
    return success_response({'job': sync_job.get_latest_job(user.id)})


@files_bp.route('/api/drive/resolve-missing', methods=['POST'])
@jwt_required()
def api_resolve_missing():
    """After Sync finds Drive deletions: delete locally or keep and restore to Drive."""
    user, err = _require_files_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip()
    try:
        result = drive_service.resolve_missing_on_drive(
            action=action,
            folder_ids=data.get('folder_ids') or [],
            item_ids=data.get('item_ids') or [],
        )
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        return error_response(str(e), status_code=400)
    return success_response(result)


@files_bp.route('/api/folders/<int:folder_id>/sync', methods=['POST'])
@jwt_required()
def api_sync_folder(folder_id):
    user, err = _require_files_user()
    if err:
        return err
    try:
        _require_drive_ready()
        ids = sync_job.collect_folder_item_ids(folder_id)
        if not ids:
            return error_response('No files in this folder to sync', status_code=400)
        result = sync_job.start_sync_job(user.id, ids, folder_id=folder_id)
    except ValueError as ve:
        return error_response(str(ve), status_code=400)
    except Exception as e:
        return error_response(str(e), status_code=400)
    return success_response(result, status_code=202)
