"""Background Files → Google Drive sync so work continues after the user leaves /files/."""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid

from flask import current_app

from common.utils import read_job_state, write_job_state

logger = logging.getLogger(__name__)

_write_lock = threading.Lock()


def _jobs_dir() -> str:
    base = current_app.config.get('JOBS_DIR') or os.path.join('generated', 'jobs')
    path = os.path.join(base, 'files-sync')
    os.makedirs(path, exist_ok=True)
    return path


def _latest_path(user_id: int) -> str:
    return os.path.join(_jobs_dir(), f'latest-user-{int(user_id)}.json')


def _job_id_for_user(user_id: int) -> str | None:
    path = _latest_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        data = read_job_state(_jobs_dir(), f'latest-user-{int(user_id)}')
    except Exception:
        return None
    if not data:
        return None
    return data.get('job_id')


def _set_latest(user_id: int, job_id: str) -> None:
    write_job_state(_jobs_dir(), f'latest-user-{int(user_id)}', {'job_id': job_id, 'user_id': int(user_id)})


def _read(job_id: str) -> dict | None:
    return read_job_state(_jobs_dir(), job_id)


def _write(job_id: str, state: dict) -> None:
    with _write_lock:
        write_job_state(_jobs_dir(), job_id, state)


def public_status(state: dict | None) -> dict | None:
    if not state:
        return None
    return {
        'job_id': state.get('job_id'),
        'status': state.get('status') or 'running',
        'progress': int(state.get('progress') or 0),
        'done': int(state.get('done') or 0),
        'total': int(state.get('total') or 0),
        'folder_id': state.get('folder_id'),
        'message': state.get('message') or '',
        'synced': state.get('synced') or [],
        'failed': state.get('failed') or [],
    }


def get_latest_job(user_id: int) -> dict | None:
    job_id = _job_id_for_user(user_id)
    if not job_id:
        return None
    return public_status(_read(job_id))


def _shared_folder_id(item_ids: list[int]) -> int | None:
    from app.models import FilesItem, db

    folder_ids = set()
    for iid in item_ids:
        item = db.session.get(FilesItem, iid)
        if item and item.folder_id:
            folder_ids.add(item.folder_id)
    if len(folder_ids) == 1:
        return folder_ids.pop()
    return None


def collect_folder_item_ids(folder_id: int) -> list[int]:
    from app.models import FilesFolder, FilesItem, db
    from module_files.drive_service import _descendant_folder_ids

    folder = db.session.get(FilesFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')
    folder_ids = _descendant_folder_ids(folder_id)
    items = (
        FilesItem.query.filter(FilesItem.folder_id.in_(folder_ids))
        .order_by(FilesItem.id.asc())
        .all()
    )
    return [item.id for item in items]


def start_sync_job(user_id: int, item_ids: list[int], folder_id: int | None = None) -> dict:
    """Queue a Drive sync for the given item ids. One running job per user."""
    ids = []
    for raw in item_ids or []:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if n not in ids:
            ids.append(n)
    if not ids:
        raise ValueError('Select files to sync')

    existing = get_latest_job(user_id)
    if existing and existing.get('status') == 'running':
        raise ValueError('A sync is already running')

    if folder_id is None:
        folder_id = _shared_folder_id(ids)

    job_id = uuid.uuid4().hex[:12]
    state = {
        'job_id': job_id,
        'user_id': int(user_id),
        'status': 'running',
        'progress': 0,
        'done': 0,
        'total': len(ids),
        'item_ids': ids,
        'folder_id': folder_id,
        'synced': [],
        'failed': [],
        'message': 'Syncing…',
        'created_at': time.time(),
    }
    _write(job_id, state)
    _set_latest(user_id, job_id)

    app = current_app._get_current_object()
    if current_app.config.get('TESTING'):
        _run_job(app, job_id, ids)
        return public_status(_read(job_id)) or state

    threading.Thread(target=_run_job, args=(app, job_id, ids), daemon=True).start()
    return public_status(state) or state


def _run_job(app, job_id: str, item_ids: list[int]) -> None:
    with app.app_context():
        from module_files import drive_service

        state = _read(job_id) or {}
        synced: list[int] = []
        failed: list[dict] = []
        total = len(item_ids) or 1
        try:
            try:
                drive_service.ensure_drive_folder_tree()
            except Exception:
                logger.exception('Files sync job %s: folder tree setup failed', job_id)

            for i, item_id in enumerate(item_ids, 1):
                try:
                    drive_service.sync_item(item_id)
                    synced.append(item_id)
                except Exception as exc:
                    failed.append({'id': item_id, 'error': str(exc)})
                state.update({
                    'done': i,
                    'progress': int(i * 100 / total),
                    'synced': synced,
                    'failed': failed,
                    'message': f'Syncing {i} of {total}',
                    'status': 'running',
                })
                _write(job_id, state)

            if failed and not synced:
                state['status'] = 'error'
                state['message'] = 'Sync failed'
            else:
                state['status'] = 'done'
                state['message'] = 'Sync completed'
            state['progress'] = 100
            state['completed_at'] = time.time()
            _write(job_id, state)
        except Exception:
            logger.exception('Files sync job %s crashed', job_id)
            state = _read(job_id) or state
            state.update({
                'status': 'error',
                'message': 'Sync failed',
                'progress': 100,
                'synced': synced,
                'failed': failed,
                'completed_at': time.time(),
            })
            _write(job_id, state)
