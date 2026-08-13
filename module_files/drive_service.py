"""Google Drive OAuth + upload helpers for the Files module.

Feature-flagged via GOOGLE_DRIVE_ENABLED + client credentials.
Works as a no-op / clear error when not configured.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional, Tuple

from flask import current_app, url_for
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.models import FilesDriveConnection, FilesFolder, FilesItem, db
from common.datetime_utils import utc_now_naive
from module_files import service as files_service

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

# Root folder created on the connected Google Drive
DRIVE_ROOT_FOLDER_NAME = 'Kynvera Files'
_LEGACY_DRIVE_ROOT_NAMES = ('Injaaz Files',)


def drive_enabled() -> bool:
    flag = (current_app.config.get('GOOGLE_DRIVE_ENABLED') or os.environ.get('GOOGLE_DRIVE_ENABLED') or 'false')
    return str(flag).strip().lower() in ('1', 'true', 'yes', 'on')


def drive_configured() -> bool:
    cid = (current_app.config.get('GOOGLE_DRIVE_CLIENT_ID') or os.environ.get('GOOGLE_DRIVE_CLIENT_ID') or '').strip()
    secret = (current_app.config.get('GOOGLE_DRIVE_CLIENT_SECRET') or os.environ.get('GOOGLE_DRIVE_CLIENT_SECRET') or '').strip()
    return bool(cid and secret)


def _redirect_uri() -> str:
    configured = (
        current_app.config.get('GOOGLE_DRIVE_REDIRECT_URI')
        or os.environ.get('GOOGLE_DRIVE_REDIRECT_URI')
        or ''
    ).strip()
    if configured:
        return configured
    return url_for('files.drive_callback', _external=True)


def _client_config() -> dict:
    return {
        'web': {
            'client_id': (current_app.config.get('GOOGLE_DRIVE_CLIENT_ID') or os.environ.get('GOOGLE_DRIVE_CLIENT_ID') or '').strip(),
            'client_secret': (current_app.config.get('GOOGLE_DRIVE_CLIENT_SECRET') or os.environ.get('GOOGLE_DRIVE_CLIENT_SECRET') or '').strip(),
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [_redirect_uri()],
        }
    }


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    secret = (current_app.config.get('SECRET_KEY') or 'change-me').encode('utf-8')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_token(plain: str) -> str:
    f = _fernet()
    if not f:
        # Fallback: store as base64 (still better than plain for casual peeking)
        return 'b64:' + base64.urlsafe_b64encode(plain.encode('utf-8')).decode('ascii')
    return 'enc:' + f.encrypt(plain.encode('utf-8')).decode('ascii')


def decrypt_token(blob: str) -> Optional[str]:
    if not blob:
        return None
    try:
        if blob.startswith('enc:'):
            f = _fernet()
            if not f:
                return None
            return f.decrypt(blob[4:].encode('ascii')).decode('utf-8')
        if blob.startswith('b64:'):
            return base64.urlsafe_b64decode(blob[4:].encode('ascii')).decode('utf-8')
        return blob
    except Exception:
        logger.exception('Failed to decrypt Drive refresh token')
        return None


def get_connection() -> Optional[FilesDriveConnection]:
    return FilesDriveConnection.query.order_by(FilesDriveConnection.id.asc()).first()


def drive_status() -> dict:
    conn = get_connection()
    enabled = drive_enabled()
    configured = drive_configured()
    connected = bool(conn and conn.refresh_token_enc)
    return {
        'enabled': enabled,
        'configured': configured,
        'connected': connected and enabled,
        'connected_email': (conn.connected_email if conn else '') or '',
        'root_drive_folder_id': conn.root_drive_folder_id if conn else None,
        'connected_at': conn.connected_at.isoformat() if conn and conn.connected_at else None,
        'message': (
            None if (enabled and configured)
            else ('Google Drive sync is disabled' if not enabled else 'Google Drive credentials are not configured')
        ),
    }


def make_code_verifier(length: int = 64) -> str:
    """RFC 7636 code_verifier (43–128 chars from unreserved set)."""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits + '-._~'
    n = max(43, min(128, int(length or 64)))
    return ''.join(secrets.choice(alphabet) for _ in range(n))


def build_auth_url(state: str, code_verifier: str) -> str:
    if not drive_enabled() or not drive_configured():
        raise RuntimeError('Google Drive is not enabled or configured')
    # Allow http://localhost redirect during local development
    if (current_app.config.get('FLASK_ENV') or '').lower() != 'production':
        os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')
    # Google may return slightly different / previously granted scope strings
    os.environ.setdefault('OAUTHLIB_RELAX_TOKEN_SCOPE', '1')
    if not code_verifier:
        raise RuntimeError('OAuth PKCE code_verifier is required')
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = _redirect_uri()
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent',
    )
    return auth_url


def exchange_code(code: str, state: str, code_verifier: str) -> Credentials:
    if (current_app.config.get('FLASK_ENV') or '').lower() != 'production':
        os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')
    os.environ.setdefault('OAUTHLIB_RELAX_TOKEN_SCOPE', '1')
    if not code_verifier:
        raise RuntimeError('OAuth PKCE code_verifier is required')
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = _redirect_uri()
    # Pass verifier explicitly — setdefault on Flow alone is easy to miss
    flow.fetch_token(code=code, code_verifier=code_verifier)
    return flow.credentials


def save_connection(creds: Credentials, email: str, user_id: Optional[int]) -> FilesDriveConnection:
    if not creds.refresh_token:
        # May be missing on re-consent; keep existing if present
        existing = get_connection()
        if existing and existing.refresh_token_enc:
            refresh = decrypt_token(existing.refresh_token_enc)
        else:
            raise RuntimeError('No refresh token returned. Revoke app access in Google Account and try again with prompt=consent.')
    else:
        refresh = creds.refresh_token

    conn = get_connection()
    now = utc_now_naive()
    if not conn:
        conn = FilesDriveConnection()
        db.session.add(conn)
    conn.connected_email = email or conn.connected_email
    conn.refresh_token_enc = encrypt_token(refresh)
    conn.connected_by = user_id
    conn.connected_at = now
    conn.updated_at = now
    db.session.commit()
    return conn


def disconnect() -> None:
    conn = get_connection()
    if not conn:
        return
    conn.refresh_token_enc = None
    conn.connected_email = None
    conn.root_drive_folder_id = None
    conn.connected_at = None
    conn.updated_at = utc_now_naive()
    # Clear drive ids on folders/items so next connect remaps cleanly
    for f in FilesFolder.query.filter(FilesFolder.drive_folder_id.isnot(None)).all():
        f.drive_folder_id = None
    for item in FilesItem.query.filter(FilesItem.drive_file_id.isnot(None)).all():
        item.drive_file_id = None
        item.sync_status = 'local'
        item.last_synced_at = None
    db.session.commit()


def _credentials_from_store() -> Credentials:
    conn = get_connection()
    if not conn or not conn.refresh_token_enc:
        raise RuntimeError('Google Drive is not connected')
    refresh = decrypt_token(conn.refresh_token_enc)
    if not refresh:
        raise RuntimeError('Stored Drive token could not be decrypted')
    creds = Credentials(
        token=None,
        refresh_token=refresh,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=_client_config()['web']['client_id'],
        client_secret=_client_config()['web']['client_secret'],
        scopes=SCOPES,
    )
    if not creds.valid:
        creds.refresh(Request())
    return creds


def _drive_service():
    creds = _credentials_from_store()
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def _fetch_user_email(creds: Credentials) -> str:
    try:
        svc = build('oauth2', 'v2', credentials=creds, cache_discovery=False)
        info = svc.userinfo().get().execute()
        return (info.get('email') or '').strip()
    except Exception:
        logger.exception('Could not fetch Google user email')
        return ''


def fetch_email_from_creds(creds: Credentials) -> str:
    return _fetch_user_email(creds)


def _find_folder(service, name: str, parent_id: Optional[str] = None) -> Optional[str]:
    q_parts = [
        "mimeType='application/vnd.google-apps.folder'",
        "trashed=false",
        f"name='{name.replace(chr(39), chr(92) + chr(39))}'",
    ]
    if parent_id:
        q_parts.append(f"'{parent_id}' in parents")
    else:
        q_parts.append("'root' in parents")
    q = ' and '.join(q_parts)
    res = service.files().list(q=q, spaces='drive', fields='files(id, name)', pageSize=5).execute()
    files = res.get('files') or []
    return files[0]['id'] if files else None


def _find_or_create_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    existing = _find_folder(service, name, parent_id=parent_id)
    if existing:
        return existing
    meta = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if parent_id:
        meta['parents'] = [parent_id]
    created = service.files().create(body=meta, fields='id').execute()
    return created['id']


def _rename_drive_file(service, file_id: str, name: str) -> None:
    try:
        service.files().update(fileId=file_id, body={'name': name}, fields='id,name').execute()
    except Exception:
        logger.exception('Failed to rename Drive file %s to %s', file_id, name)


def _ensure_root_drive_folder(service, conn: FilesDriveConnection) -> str:
    """Ensure the brand root folder exists (Kynvera Files); migrate legacy Injaaz Files name."""
    root_id = conn.root_drive_folder_id
    if root_id:
        try:
            meta = service.files().get(fileId=root_id, fields='id,name,trashed').execute()
            if meta.get('trashed'):
                root_id = None
            elif (meta.get('name') or '') != DRIVE_ROOT_FOLDER_NAME:
                _rename_drive_file(service, root_id, DRIVE_ROOT_FOLDER_NAME)
        except Exception:
            logger.exception('Stored Drive root folder missing; will recreate')
            root_id = None

    if not root_id:
        root_id = _find_folder(service, DRIVE_ROOT_FOLDER_NAME, parent_id=None)
        if not root_id:
            for legacy in _LEGACY_DRIVE_ROOT_NAMES:
                legacy_id = _find_folder(service, legacy, parent_id=None)
                if legacy_id:
                    _rename_drive_file(service, legacy_id, DRIVE_ROOT_FOLDER_NAME)
                    root_id = legacy_id
                    break
        if not root_id:
            root_id = _find_or_create_folder(service, DRIVE_ROOT_FOLDER_NAME, parent_id=None)
        conn.root_drive_folder_id = root_id
        db.session.commit()
    return root_id


def ensure_drive_folder_tree() -> str:
    """Create Kynvera Files / catalog folders / custom folders on Drive; map ids onto FilesFolder rows."""
    files_service.ensure_default_folders()
    service = _drive_service()
    conn = get_connection()
    if not conn:
        raise RuntimeError('Not connected')

    root_id = _ensure_root_drive_folder(service, conn)
    _sync_all_local_folders(service, root_id)
    return root_id


def _folders_parent_first() -> list:
    """Return all folders ordered so parents appear before children."""
    folders = FilesFolder.query.order_by(FilesFolder.id.asc()).all()
    by_id = {f.id: f for f in folders}
    children = {}
    roots = []
    for f in folders:
        if f.parent_id and f.parent_id in by_id:
            children.setdefault(f.parent_id, []).append(f)
        else:
            roots.append(f)
    ordered = []

    def walk(node):
        ordered.append(node)
        for kid in children.get(node.id, []):
            walk(kid)

    for r in roots:
        walk(r)
    # Any orphans skipped above
    seen = {f.id for f in ordered}
    for f in folders:
        if f.id not in seen:
            ordered.append(f)
    return ordered


def _http_status(exc) -> Optional[int]:
    resp = getattr(exc, 'resp', None)
    status = getattr(resp, 'status', None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            return None
    return None


def _drive_id_missing(service, file_id: Optional[str]) -> bool:
    """True if Drive id is deleted, trashed, or not found."""
    if not file_id:
        return False
    try:
        meta = service.files().get(
            fileId=file_id,
            fields='id,trashed',
            supportsAllDrives=True,
        ).execute()
        return bool(meta.get('trashed'))
    except Exception as e:
        status = _http_status(e)
        if status in (404, 410):
            return True
        # Some clients surface notFound in the error body without resp.status
        msg = str(e).lower()
        if 'notfound' in msg or '404' in msg or 'file not found' in msg:
            return True
        logger.warning('Could not probe Drive id %s: %s', file_id, e)
        return False


def detect_missing_on_drive(scope_folder_ids: Optional[list] = None) -> dict:
    """Find local folders/files whose linked Drive objects were deleted or trashed.

    If scope_folder_ids is set, only inspect that subtree.
    """
    if not drive_enabled() or not drive_configured() or not get_connection():
        return {'folders': [], 'files': []}

    service = _drive_service()
    scope = set(scope_folder_ids) if scope_folder_ids is not None else None

    folders_q = FilesFolder.query.filter(FilesFolder.drive_folder_id.isnot(None))
    if scope is not None:
        folders_q = folders_q.filter(FilesFolder.id.in_(scope))
    missing_folders = []
    for folder in folders_q.all():
        if _drive_id_missing(service, folder.drive_folder_id):
            missing_folders.append({
                'id': folder.id,
                'name': folder.name,
                'type': 'folder',
                'is_system': bool(folder.path_key),
                'path_key': folder.path_key,
            })

    items_q = FilesItem.query.filter(FilesItem.drive_file_id.isnot(None))
    if scope is not None:
        items_q = items_q.filter(FilesItem.folder_id.in_(scope))
    missing_files = []
    for item in items_q.all():
        if _drive_id_missing(service, item.drive_file_id):
            missing_files.append({
                'id': item.id,
                'name': item.filename,
                'type': 'file',
                'folder_id': item.folder_id,
            })

    return {'folders': missing_folders, 'files': missing_files}


def _sync_all_local_folders(service, root_id: str, *, recreate_missing: bool = False) -> dict:
    """Ensure every local folder exists on Drive under the correct parent; rename if needed.

    When recreate_missing is False (default), folders whose Drive id is gone/trashed are
    left alone so the UI can ask delete-local vs keep-and-restore.
    """
    created = 0
    renamed = 0
    skipped_missing = 0
    missing_local_ids = set()

    for folder in _folders_parent_first():
        parent_drive = root_id
        parent_blocked = False
        if folder.parent_id:
            parent = db.session.get(FilesFolder, folder.parent_id)
            if parent and parent.drive_folder_id:
                parent_drive = parent.drive_folder_id
            if folder.parent_id in missing_local_ids:
                parent_blocked = True

        if folder.drive_folder_id:
            try:
                meta = service.files().get(
                    fileId=folder.drive_folder_id,
                    fields='id,name,trashed',
                    supportsAllDrives=True,
                ).execute()
                if meta.get('trashed'):
                    missing_local_ids.add(folder.id)
                    skipped_missing += 1
                    if recreate_missing:
                        folder.drive_folder_id = None
                    else:
                        continue
                elif (meta.get('name') or '') != folder.name:
                    _rename_drive_file(service, folder.drive_folder_id, folder.name)
                    renamed += 1
            except Exception as e:
                status = _http_status(e)
                msg = str(e).lower()
                is_missing = (
                    status in (404, 410)
                    or 'notfound' in msg
                    or 'file not found' in msg
                )
                if is_missing:
                    missing_local_ids.add(folder.id)
                    skipped_missing += 1
                    if recreate_missing:
                        folder.drive_folder_id = None
                    else:
                        continue
                else:
                    logger.exception('Drive folder probe failed for local folder %s', folder.id)
                    continue

        if not folder.drive_folder_id:
            if parent_blocked and not recreate_missing:
                missing_local_ids.add(folder.id)
                skipped_missing += 1
                continue
            folder.drive_folder_id = _find_or_create_folder(
                service, folder.name, parent_id=parent_drive
            )
            created += 1

    db.session.commit()
    return {
        'folders_created': created,
        'folders_renamed': renamed,
        'folders_skipped_missing': skipped_missing,
    }


def _ensure_folder_on_drive(folder: FilesFolder, service) -> str:
    if folder.drive_folder_id:
        return folder.drive_folder_id
    ensure_drive_folder_tree()
    db.session.refresh(folder)
    if folder.drive_folder_id:
        return folder.drive_folder_id
    # Custom folder without path_key — create under root or parent
    parent_drive = None
    if folder.parent_id:
        parent = db.session.get(FilesFolder, folder.parent_id)
        if parent:
            parent_drive = _ensure_folder_on_drive(parent, service)
    else:
        conn = get_connection()
        parent_drive = conn.root_drive_folder_id if conn else None
        if not parent_drive:
            parent_drive = ensure_drive_folder_tree()
    drive_id = _find_or_create_folder(service, folder.name, parent_id=parent_drive)
    folder.drive_folder_id = drive_id
    db.session.commit()
    return drive_id


def sync_item(item_id: int) -> FilesItem:
    if not drive_enabled():
        raise RuntimeError('Google Drive sync is disabled')
    if not drive_configured():
        raise RuntimeError('Google Drive credentials are not configured')

    item = db.session.get(FilesItem, item_id)
    if not item:
        raise ValueError('File not found')
    folder = db.session.get(FilesFolder, item.folder_id)
    if not folder:
        raise ValueError('Folder not found')

    try:
        service = _drive_service()
        ensure_drive_folder_tree()
        parent_id = _ensure_folder_on_drive(folder, service)
        abs_path = files_service.resolve_item_abs_path(item)
        media = MediaFileUpload(abs_path, mimetype=item.mime_type or 'application/octet-stream', resumable=True)

        if item.drive_file_id:
            # Update content + name
            service.files().update(
                fileId=item.drive_file_id,
                body={'name': item.filename},
                media_body=media,
                fields='id',
            ).execute()
            drive_id = item.drive_file_id
        else:
            created = service.files().create(
                body={'name': item.filename, 'parents': [parent_id]},
                media_body=media,
                fields='id',
            ).execute()
            drive_id = created['id']

        item.drive_file_id = drive_id
        item.sync_status = 'synced'
        item.sync_error = None
        item.last_synced_at = utc_now_naive()
        item.updated_at = utc_now_naive()
        db.session.commit()
        return item
    except Exception as e:
        logger.exception('Drive sync failed for item %s', item_id)
        item.sync_status = 'error'
        item.sync_error = str(e)[:480]
        db.session.commit()
        raise


def sync_pending() -> dict:
    """Backward-compatible alias for sync_now (files only historically)."""
    return sync_now()


def sync_now() -> dict:
    """Push full folder structure (create/rename) + all pending/error files to Drive.

    Does not auto-recreate items deleted on Drive — returns missing_on_drive for the UI
    to ask whether to delete locally or keep and restore.
    """
    if not drive_enabled():
        raise RuntimeError('Google Drive sync is disabled')
    if not drive_configured():
        raise RuntimeError('Google Drive credentials are not configured')
    if not get_connection():
        raise RuntimeError('Connect Google Drive first')

    missing = detect_missing_on_drive()
    missing_folder_ids = {f['id'] for f in missing['folders']}
    missing_item_ids = {i['id'] for i in missing['files']}

    service = _drive_service()
    conn = get_connection()
    root_id = _ensure_root_drive_folder(service, conn)
    folder_stats = _sync_all_local_folders(service, root_id, recreate_missing=False)

    items = FilesItem.query.filter(
        FilesItem.sync_status.in_(['local', 'error'])
    ).order_by(FilesItem.id.asc()).all()
    ok, failed = [], []
    for item in items:
        if item.id in missing_item_ids or item.folder_id in missing_folder_ids:
            continue
        try:
            sync_item(item.id)
            ok.append(item.id)
        except Exception as e:
            failed.append({'id': item.id, 'error': str(e)})

    # Remove Drive leftovers that no longer exist in Files (e.g. deleted folders/files)
    prune_stats = prune_drive_orphans()

    return {
        'folders_created': folder_stats.get('folders_created', 0),
        'folders_renamed': folder_stats.get('folders_renamed', 0),
        'folders_skipped_missing': folder_stats.get('folders_skipped_missing', 0),
        'synced': ok,
        'failed': failed,
        'missing_on_drive': missing,
        'needs_decision': bool(missing['folders'] or missing['files']),
        **prune_stats,
    }


def resolve_missing_on_drive(
    action: str,
    folder_ids: Optional[list] = None,
    item_ids: Optional[list] = None,
) -> dict:
    """Resolve local rows whose Drive copies were deleted.

    action:
      - keep: clear Drive ids and re-create/upload to Drive
      - delete_local: remove from Files (system folders are kept and restored instead)
    """
    if action not in ('keep', 'delete_local'):
        raise ValueError('action must be keep or delete_local')
    if not drive_enabled() or not drive_configured() or not get_connection():
        raise RuntimeError('Connect Google Drive first')

    folder_ids = [int(x) for x in (folder_ids or [])]
    item_ids = [int(x) for x in (item_ids or [])]

    kept_folders, deleted_folders, system_restored = [], [], []
    kept_items, deleted_items = [], []

    if action == 'keep':
        for fid in folder_ids:
            folder = db.session.get(FilesFolder, fid)
            if not folder:
                continue
            folder.drive_folder_id = None
            kept_folders.append(fid)
        for iid in item_ids:
            item = db.session.get(FilesItem, iid)
            if not item:
                continue
            item.drive_file_id = None
            item.sync_status = 'local'
            item.sync_error = None
            kept_items.append(iid)
        db.session.commit()

        service = _drive_service()
        conn = get_connection()
        root_id = _ensure_root_drive_folder(service, conn)
        folder_stats = _sync_all_local_folders(service, root_id, recreate_missing=True)

        synced, failed = [], []
        for iid in kept_items:
            try:
                sync_item(iid)
                synced.append(iid)
            except Exception as e:
                failed.append({'id': iid, 'error': str(e)})

        return {
            'action': 'keep',
            'folders_kept': kept_folders,
            'items_kept': kept_items,
            'folders_created': folder_stats.get('folders_created', 0),
            'synced': synced,
            'failed': failed,
        }

    # delete_local — deepest folders first so parents can go after children
    for iid in item_ids:
        item = db.session.get(FilesItem, iid)
        if not item:
            continue
        try:
            files_service.delete_item(iid)
            deleted_items.append(iid)
        except Exception as e:
            logger.exception('Failed to delete local item %s after Drive deletion', iid)
            failed_msg = str(e)
            raise ValueError(f'Could not delete file: {failed_msg}') from e

    folders = []
    for fid in folder_ids:
        folder = db.session.get(FilesFolder, fid)
        if folder:
            folders.append(folder)

    # Depth: process deepest first
    by_id = {f.id: f for f in FilesFolder.query.all()}

    def depth(f):
        d = 0
        cur = f
        seen = set()
        while cur and cur.parent_id and cur.parent_id in by_id and cur.id not in seen:
            seen.add(cur.id)
            d += 1
            cur = by_id[cur.parent_id]
        return d

    folders.sort(key=depth, reverse=True)

    for folder in folders:
        if folder.path_key:
            folder.drive_folder_id = None
            system_restored.append(folder.id)
            db.session.commit()
            continue
        # Skip if already removed as descendant of a deleted parent
        if not db.session.get(FilesFolder, folder.id):
            continue
        try:
            files_service.delete_folder(folder.id)
            deleted_folders.append(folder.id)
        except ValueError as ve:
            # System folder race / already gone
            logger.warning('Skip folder delete %s: %s', folder.id, ve)
        except Exception as e:
            logger.exception('Failed to delete local folder %s after Drive deletion', folder.id)
            raise ValueError(f'Could not delete folder: {e}') from e

    folder_stats = {'folders_created': 0}
    if system_restored:
        service = _drive_service()
        conn = get_connection()
        root_id = _ensure_root_drive_folder(service, conn)
        folder_stats = _sync_all_local_folders(service, root_id, recreate_missing=True)

    return {
        'action': 'delete_local',
        'folders_deleted': deleted_folders,
        'items_deleted': deleted_items,
        'system_folders_restored': system_restored,
        'folders_created': folder_stats.get('folders_created', 0),
    }


def _descendant_folder_ids(folder_id: int) -> list:
    ids = [folder_id]
    kids = FilesFolder.query.filter_by(parent_id=folder_id).all()
    for kid in kids:
        ids.extend(_descendant_folder_ids(kid.id))
    return ids


def sync_folder(folder_id: int) -> dict:
    """Sync one folder subtree to Drive: create/rename folders + sync files under it."""
    if not drive_enabled():
        raise RuntimeError('Google Drive sync is disabled')
    if not drive_configured():
        raise RuntimeError('Google Drive credentials are not configured')
    if not get_connection():
        raise RuntimeError('Connect Google Drive first')

    folder = db.session.get(FilesFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')

    folder_ids = _descendant_folder_ids(folder_id)
    missing = detect_missing_on_drive(scope_folder_ids=folder_ids)
    missing_folder_ids = {f['id'] for f in missing['folders']}
    missing_item_ids = {i['id'] for i in missing['files']}

    service = _drive_service()
    # Ensure ancestors + this subtree exist with current names (do not auto-restore missing)
    ensure_drive_folder_tree()
    db.session.refresh(folder)

    # Re-apply names for this subtree when Drive object still exists
    for fid in folder_ids:
        if fid in missing_folder_ids:
            continue
        f = db.session.get(FilesFolder, fid)
        if f and f.drive_folder_id:
            try:
                meta = service.files().get(fileId=f.drive_folder_id, fields='name,trashed').execute()
                if meta.get('trashed'):
                    continue
                if (meta.get('name') or '') != f.name:
                    _rename_drive_file(service, f.drive_folder_id, f.name)
            except Exception:
                logger.exception('Folder rename during sync_folder failed for %s', fid)

    items = FilesItem.query.filter(FilesItem.folder_id.in_(folder_ids)).order_by(FilesItem.id.asc()).all()
    ok, failed = [], []
    for item in items:
        if item.id in missing_item_ids or item.folder_id in missing_folder_ids:
            continue
        try:
            sync_item(item.id)
            ok.append(item.id)
        except Exception as e:
            failed.append({'id': item.id, 'error': str(e)})

    return {
        'folder_id': folder_id,
        'folders_synced': len(folder_ids),
        'synced': ok,
        'failed': failed,
        'missing_on_drive': missing,
        'needs_decision': bool(missing['folders'] or missing['files']),
    }


def rename_on_drive_folder(folder: FilesFolder) -> None:
    if not folder.drive_folder_id or not drive_enabled() or not get_connection():
        return
    try:
        service = _drive_service()
        service.files().update(fileId=folder.drive_folder_id, body={'name': folder.name}, fields='id').execute()
    except Exception:
        logger.exception('Drive folder rename failed for %s', folder.id)


def rename_on_drive_item(item: FilesItem) -> None:
    if not item.drive_file_id or not drive_enabled() or not get_connection():
        return
    try:
        service = _drive_service()
        service.files().update(fileId=item.drive_file_id, body={'name': item.filename}, fields='id').execute()
        item.sync_status = 'synced'
        item.last_synced_at = utc_now_naive()
        db.session.commit()
    except Exception:
        logger.exception('Drive file rename failed for %s', item.id)


def _delete_drive_id(file_id: Optional[str]) -> bool:
    """Permanently delete a Drive file/folder the app owns. Falls back to trash. Returns True on success."""
    if not file_id or not drive_enabled() or not get_connection():
        return False
    service = _drive_service()
    # Try plain delete first (My Drive), then shared-drive flag, then trash
    attempts = (
        {'fileId': file_id},
        {'fileId': file_id, 'supportsAllDrives': True},
    )
    for kwargs in attempts:
        try:
            service.files().delete(**kwargs).execute()
            logger.info('Deleted Drive object %s', file_id)
            return True
        except Exception as e:
            logger.warning('Drive delete attempt failed for %s: %s', file_id, e)
    try:
        service.files().update(
            fileId=file_id,
            body={'trashed': True},
            fields='id,trashed',
        ).execute()
        logger.info('Trashed Drive object %s', file_id)
        return True
    except Exception:
        logger.exception('Drive trash also failed for %s', file_id)
        return False


def delete_on_drive_item(drive_file_id: Optional[str]) -> bool:
    return _delete_drive_id(drive_file_id)


def delete_on_drive_folder(drive_folder_id: Optional[str]) -> bool:
    return _delete_drive_id(drive_folder_id)


def delete_on_drive_ids(file_ids: Optional[list] = None, folder_ids: Optional[list] = None) -> dict:
    """Delete Drive files first, then folders deepest-first."""
    ok, failed = [], []
    for fid in file_ids or []:
        if not fid:
            continue
        if _delete_drive_id(fid):
            ok.append(fid)
        else:
            failed.append(fid)
    # folder_ids are parent-first; reverse → deepest first
    folders = [fid for fid in (folder_ids or []) if fid]
    for fid in reversed(folders):
        if _delete_drive_id(fid):
            ok.append(fid)
        else:
            failed.append(fid)
    return {'drive_deleted': ok, 'drive_failed': failed}


def _iter_drive_children(service, parent_id: str):
    page_token = None
    while True:
        res = service.files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, name, mimeType)',
            pageSize=100,
            pageToken=page_token,
        ).execute()
        for f in res.get('files') or []:
            yield f
        page_token = res.get('nextPageToken')
        if not page_token:
            break


def prune_drive_orphans() -> dict:
    """Remove Drive files/folders under Kynvera Files that are no longer tracked locally."""
    if not drive_enabled() or not drive_configured() or not get_connection():
        return {'orphans_removed': 0, 'orphan_failed': 0}
    conn = get_connection()
    root_id = conn.root_drive_folder_id
    if not root_id:
        return {'orphans_removed': 0, 'orphan_failed': 0}

    known = {root_id}
    known.update(
        f.drive_folder_id
        for f in FilesFolder.query.filter(FilesFolder.drive_folder_id.isnot(None)).all()
        if f.drive_folder_id
    )
    known.update(
        i.drive_file_id
        for i in FilesItem.query.filter(FilesItem.drive_file_id.isnot(None)).all()
        if i.drive_file_id
    )

    service = _drive_service()
    # Collect all descendants (parent-first BFS)
    ordered = []
    queue = [root_id]
    seen = {root_id}
    while queue:
        parent = queue.pop(0)
        for child in _iter_drive_children(service, parent):
            cid = child.get('id')
            if not cid or cid in seen:
                continue
            seen.add(cid)
            ordered.append(child)
            if child.get('mimeType') == 'application/vnd.google-apps.folder':
                queue.append(cid)

    orphans = [f['id'] for f in ordered if f.get('id') not in known]
    removed, failed = 0, 0
    # Deepest first
    for fid in reversed(orphans):
        if _delete_drive_id(fid):
            removed += 1
        else:
            failed += 1
    logger.info('Drive orphan prune: removed=%s failed=%s', removed, failed)
    return {'orphans_removed': removed, 'orphan_failed': failed}
