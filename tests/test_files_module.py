"""Files module: catalog/tree browsing, uploads, folders, items, and Google Drive sync.

Google Drive is always mocked via module_files.drive_service — no real network / OAuth calls.
"""

import os
from io import BytesIO

import pytest


# ── auth helpers ─────────────────────────────────────────────────────────

def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def files_user_headers(app, client):
    """Non-admin user explicitly granted access_files=True."""
    from tests.factories import make_user

    with app.app_context():
        user, pwd = make_user(access_files=True)
        username = user.username
    return _login(client, username, pwd)


@pytest.fixture
def hr_only_headers(app, client):
    """Non-admin user with access_hr only — reaches Files but is gated out of Drive connect."""
    from tests.factories import make_user

    with app.app_context():
        user, pwd = make_user(access_hr=True)
        username = user.username
    return _login(client, username, pwd)


class _FakeConn:
    """Stand-in for FilesDriveConnection with just the attributes drive_status() reads."""

    def __init__(self, email='drive-user@example.com', root_id='root-abc123', refresh_token_enc='enc:zzz'):
        self.connected_email = email
        self.root_drive_folder_id = root_id
        self.refresh_token_enc = refresh_token_enc
        self.connected_at = None


# ── fixture-ish helpers built on the real API ───────────────────────────

def _create_folder(client, headers, name='Test Folder', parent_id=None):
    payload = {'name': name}
    if parent_id is not None:
        payload['parent_id'] = parent_id
    res = client.post('/files/api/folders', json=payload, headers=headers)
    assert res.status_code == 200, res.get_json()
    return res.get_json()['folder']


def _upload_file(client, headers, folder_id, filename='test.txt', content=b'hello world'):
    res = client.post(
        '/files/api/upload',
        data={'folder_id': str(folder_id), 'file': (BytesIO(content), filename)},
        headers=headers,
        content_type='multipart/form-data',
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()['item']


def _system_folder_id(client, headers, path_key='hr'):
    res = client.get('/files/api/tree', headers=headers)
    folders = res.get_json()['folders']
    match = next(f for f in folders if f['path_key'] == path_key)
    return match['id']


# ── UI page ──────────────────────────────────────────────────────────────

class TestFilesHomePage:
    def test_no_token_redirects_to_login(self, client):
        response = client.get('/files/')
        assert response.status_code == 302

    def test_renders_for_admin(self, client, admin_auth_headers):
        response = client.get('/files/', headers=admin_auth_headers)
        assert response.status_code == 200
        assert b'files' in response.data.lower()


# ── Catalog / tree ────────────────────────────────────────────────────────

class TestCatalogAndTree:
    def test_catalog_requires_auth(self, client):
        response = client.get('/files/api/catalog')
        assert response.status_code in (401, 422)

    def test_catalog_denied_for_user_without_access(self, client, auth_headers):
        response = client.get('/files/api/catalog', headers=auth_headers)
        assert response.status_code == 403

    def test_full_catalog_no_module(self, client, admin_auth_headers):
        response = client.get('/files/api/catalog', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'manpower' in data
        assert 'leave' in data

    def test_module_catalog_scoped(self, client, admin_auth_headers):
        response = client.get('/files/api/catalog?module=manpower', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['module'] == 'manpower'
        assert data['folder_label'] == 'HR / Manpower'
        assert any(opt['kind'] == 'template' for opt in data['options'])

    def test_module_catalog_expands_dochub_options(self, client, admin_auth_headers):
        response = client.get('/files/api/catalog?module=dochub', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['module'] == 'dochub'
        assert isinstance(data['options'], list)

    def test_unknown_module_404(self, client, admin_auth_headers):
        response = client.get('/files/api/catalog?module=not_a_real_module', headers=admin_auth_headers)
        assert response.status_code == 404
        assert response.get_json()['success'] is False

    def test_tree_requires_auth(self, client):
        response = client.get('/files/api/tree')
        assert response.status_code in (401, 422)

    def test_tree_returns_folders_items_drive(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: False)
        monkeypatch.setattr('module_files.drive_service.get_connection', lambda: None)
        response = client.get('/files/api/tree', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert 'folders' in data and isinstance(data['folders'], list)
        assert 'items' in data and isinstance(data['items'], list)
        assert data['drive']['connected'] is False


# ── Save from Leave / Manpower / etc. ───────────────────────────────────

class TestSaveFromModule:
    def test_requires_auth(self, client):
        response = client.post('/files/api/save-from-module', json={})
        assert response.status_code in (401, 422)

    def test_missing_kinds_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/save-from-module', json={'module': 'devices'}, headers=admin_auth_headers,
        )
        assert response.status_code == 400
        assert response.get_json()['success'] is False

    def test_unsupported_module_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/save-from-module',
            json={'module': 'not_a_module', 'kinds': ['template']},
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_saves_devices_template(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/save-from-module',
            json={'module': 'devices', 'kinds': ['template']},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['saved'] == 1
        assert data['item'] is not None
        assert data['module'] == 'devices'
        assert data['folder_label'] == 'Admin / Devices'
        item_id = data['item']['id']
        downloaded = client.get(f'/files/api/items/{item_id}/download', headers=admin_auth_headers)
        assert downloaded.status_code == 200
        assert downloaded.data[:2] == b'PK'


# ── Upload ────────────────────────────────────────────────────────────────

class TestUpload:
    def test_requires_auth(self, client):
        response = client.post('/files/api/upload', data={}, content_type='multipart/form-data')
        assert response.status_code in (401, 422)

    def test_missing_folder_id_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/upload',
            data={'file': (BytesIO(b'x'), 'a.txt')},
            headers=admin_auth_headers,
            content_type='multipart/form-data',
        )
        assert response.status_code == 400

    def test_missing_file_400(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Upload Missing File')
        response = client.post(
            '/files/api/upload',
            data={'folder_id': str(folder['id'])},
            headers=admin_auth_headers,
            content_type='multipart/form-data',
        )
        assert response.status_code == 400

    def test_unknown_folder_id_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/upload',
            data={'folder_id': '999999999', 'file': (BytesIO(b'x'), 'a.txt')},
            headers=admin_auth_headers,
            content_type='multipart/form-data',
        )
        assert response.status_code == 400

    def test_empty_file_400(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Upload Empty')
        response = client.post(
            '/files/api/upload',
            data={'folder_id': str(folder['id']), 'file': (BytesIO(b''), 'empty.txt')},
            headers=admin_auth_headers,
            content_type='multipart/form-data',
        )
        assert response.status_code == 400

    def test_happy_path(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Upload Happy')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='doc.txt', content=b'hello world')
        assert item['filename'] == 'doc.txt'
        assert item['folder_id'] == folder['id']
        assert item['size_bytes'] == len(b'hello world')


# ── Folders ──────────────────────────────────────────────────────────────

class TestFolders:
    def test_create_requires_auth(self, client):
        response = client.post('/files/api/folders', json={'name': 'x'})
        assert response.status_code in (401, 422)

    def test_create_missing_name_400(self, client, admin_auth_headers):
        response = client.post('/files/api/folders', json={}, headers=admin_auth_headers)
        assert response.status_code == 400

    def test_create_invalid_parent_id_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/folders', json={'name': 'Bad Parent', 'parent_id': 'abc'}, headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_create_nonexistent_parent_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/folders', json={'name': 'Orphan', 'parent_id': 999999999}, headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_create_happy(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Fresh Folder')
        assert folder['name'] == 'Fresh Folder'
        assert folder['path_key'] is None

    def test_rename_requires_auth(self, client):
        response = client.patch('/files/api/folders/1', json={'name': 'x'})
        assert response.status_code in (401, 422)

    def test_rename_happy(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Rename Me')
        response = client.patch(
            f"/files/api/folders/{folder['id']}", json={'name': 'Renamed'}, headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.get_json()['folder']['name'] == 'Renamed'

    def test_rename_missing_name_400(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Rename Missing Name')
        response = client.patch(f"/files/api/folders/{folder['id']}", json={}, headers=admin_auth_headers)
        assert response.status_code == 400

    def test_rename_unknown_folder_400(self, client, admin_auth_headers):
        response = client.patch('/files/api/folders/999999999', json={'name': 'x'}, headers=admin_auth_headers)
        assert response.status_code == 400

    def test_delete_requires_auth(self, client):
        response = client.delete('/files/api/folders/1')
        assert response.status_code in (401, 422)

    def test_delete_happy(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Delete Me')
        response = client.delete(f"/files/api/folders/{folder['id']}", headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['deleted'] is True

    def test_delete_unknown_folder_400(self, client, admin_auth_headers):
        response = client.delete('/files/api/folders/999999999', headers=admin_auth_headers)
        assert response.status_code == 400

    def test_delete_system_folder_blocked(self, client, admin_auth_headers):
        fid = _system_folder_id(client, admin_auth_headers, path_key='hr')
        response = client.delete(f'/files/api/folders/{fid}', headers=admin_auth_headers)
        assert response.status_code == 400
        assert 'system' in response.get_json()['error'].lower()


# ── Items ────────────────────────────────────────────────────────────────

class TestItems:
    def test_rename_requires_auth(self, client):
        response = client.patch('/files/api/items/1', json={'name': 'x'})
        assert response.status_code in (401, 422)

    def test_rename_happy(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Item Rename Folder')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='a.txt')
        response = client.patch(
            f"/files/api/items/{item['id']}", json={'name': 'Renamed Item'}, headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.get_json()['item']['name'] == 'Renamed Item'

    def test_rename_missing_name_400(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Item Rename Missing')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='b.txt')
        response = client.patch(f"/files/api/items/{item['id']}", json={}, headers=admin_auth_headers)
        assert response.status_code == 400

    def test_rename_unknown_item_400(self, client, admin_auth_headers):
        response = client.patch('/files/api/items/999999999', json={'name': 'x'}, headers=admin_auth_headers)
        assert response.status_code == 400

    def test_delete_requires_auth(self, client):
        response = client.delete('/files/api/items/1')
        assert response.status_code in (401, 422)

    def test_delete_happy(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Item Delete Folder')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='c.txt')
        response = client.delete(f"/files/api/items/{item['id']}", headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['deleted'] is True
        assert body['had_drive_copy'] is False

    def test_delete_unknown_item_400(self, client, admin_auth_headers):
        response = client.delete('/files/api/items/999999999', headers=admin_auth_headers)
        assert response.status_code == 400

    def test_download_requires_auth(self, client):
        response = client.get('/files/api/items/1/download')
        assert response.status_code in (401, 422)

    def test_download_happy(self, client, admin_auth_headers):
        folder = _create_folder(client, admin_auth_headers, name='Item Download Folder')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='d.txt', content=b'download-bytes')
        response = client.get(f"/files/api/items/{item['id']}/download", headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.data == b'download-bytes'

    def test_download_unknown_item_404(self, client, admin_auth_headers):
        response = client.get('/files/api/items/999999999/download', headers=admin_auth_headers)
        assert response.status_code == 404

    def test_download_missing_on_disk_404(self, client, admin_auth_headers, app):
        folder = _create_folder(client, admin_auth_headers, name='Item Missing Disk Folder')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='e.txt')
        with app.app_context():
            from app.models import FilesItem, db
            from module_files import service as files_service

            row = db.session.get(FilesItem, item['id'])
            path = files_service.resolve_item_abs_path(row)
            os.remove(path)
        response = client.get(f"/files/api/items/{item['id']}/download", headers=admin_auth_headers)
        assert response.status_code == 404


# ── Drive: status ────────────────────────────────────────────────────────

class TestDriveStatus:
    def test_requires_auth(self, client):
        response = client.get('/files/api/drive/status')
        assert response.status_code in (401, 422)

    def test_disabled_branch(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: False)
        monkeypatch.setattr('module_files.drive_service.get_connection', lambda: None)
        response = client.get('/files/api/drive/status', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['enabled'] is False
        assert data['connected'] is False
        assert data['message'] == 'Google Drive sync is disabled'

    def test_enabled_not_configured_branch(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: True)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: False)
        monkeypatch.setattr('module_files.drive_service.get_connection', lambda: None)
        response = client.get('/files/api/drive/status', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['configured'] is False
        assert data['message'] == 'Google Drive credentials are not configured'

    def test_connected_branch(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: True)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: True)
        monkeypatch.setattr('module_files.drive_service.get_connection', lambda: _FakeConn())
        response = client.get('/files/api/drive/status', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['connected'] is True
        assert data['connected_email'] == 'drive-user@example.com'
        assert data['message'] is None


# ── Drive: connect (auth-url initiation, never a real OAuth flow) ────────

class TestDriveConnect:
    def test_requires_auth(self, client):
        response = client.get('/files/api/drive/connect')
        assert response.status_code in (401, 422)

    def test_denied_for_user_with_no_files_access(self, client, auth_headers):
        response = client.get('/files/api/drive/connect', headers=auth_headers)
        assert response.status_code == 403

    def test_denied_for_hr_only_user(self, client, hr_only_headers):
        response = client.get('/files/api/drive/connect', headers=hr_only_headers)
        assert response.status_code == 403

    def test_not_configured_json_error(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: False)
        response = client.get('/files/api/drive/connect?redirect=0', headers=admin_auth_headers)
        assert response.status_code == 400
        assert response.get_json()['success'] is False

    def test_not_configured_redirects_when_not_json(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: False)
        response = client.get('/files/api/drive/connect', headers=admin_auth_headers)
        assert response.status_code == 302
        assert 'drive=error' in response.headers['Location']

    def test_happy_path_returns_auth_url(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr(
            'module_files.drive_service.build_auth_url',
            lambda state, code_verifier: 'https://accounts.google.com/o/oauth2/auth?state=fake',
        )
        response = client.get('/files/api/drive/connect?redirect=0', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['auth_url'].startswith('https://accounts.google.com')


# ── Drive: callback (no auth by design — OAuth redirect target) ─────────

class TestDriveCallback:
    def test_error_param_redirects(self, client):
        response = client.get('/files/api/drive/callback?error=access_denied')
        assert response.status_code == 302
        assert 'drive=error' in response.headers['Location']

    def test_missing_code_and_state_redirects(self, client):
        response = client.get('/files/api/drive/callback')
        assert response.status_code == 302
        assert 'missing_code' in response.headers['Location']

    def test_invalid_state_signature_redirects(self, client):
        response = client.get('/files/api/drive/callback?code=fakecode&state=garbage-not-signed')
        assert response.status_code == 302
        assert 'invalid_state' in response.headers['Location']

    def test_missing_pkce_verifier_redirects(self, client, app, admin_user):
        from itsdangerous import URLSafeSerializer

        with app.app_context():
            secret = app.config.get('SECRET_KEY') or 'change-me'
            uid = admin_user.id
        state = URLSafeSerializer(secret, salt='files-drive-oauth').dumps({'uid': uid, 'cv': ''})
        response = client.get(f'/files/api/drive/callback?code=fakecode&state={state}')
        assert response.status_code == 302
        assert 'missing_pkce_verifier' in response.headers['Location']


# ── Drive: setup / disconnect ────────────────────────────────────────────

class TestDriveSetup:
    def test_requires_auth(self, client):
        response = client.post('/files/api/drive/setup')
        assert response.status_code in (401, 422)

    def test_not_connected_400(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr(
            'module_files.drive_service.drive_status',
            lambda: {
                'connected': False, 'enabled': False, 'configured': False,
                'connected_email': '', 'root_drive_folder_id': None,
                'connected_at': None, 'message': 'Google Drive sync is disabled',
            },
        )
        response = client.post('/files/api/drive/setup', headers=admin_auth_headers)
        assert response.status_code == 400

    def test_happy_path(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr(
            'module_files.drive_service.drive_status',
            lambda: {
                'connected': True, 'enabled': True, 'configured': True,
                'connected_email': 'x@example.com', 'root_drive_folder_id': None,
                'connected_at': None, 'message': None,
            },
        )
        monkeypatch.setattr('module_files.drive_service.ensure_drive_folder_tree', lambda: 'root-999')
        response = client.post('/files/api/drive/setup', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['root_drive_folder_id'] == 'root-999'


class TestDriveDisconnect:
    def test_requires_auth(self, client):
        response = client.post('/files/api/drive/disconnect')
        assert response.status_code in (401, 422)

    def test_denied_for_non_admin(self, client, files_user_headers):
        response = client.post('/files/api/drive/disconnect', headers=files_user_headers)
        assert response.status_code == 403

    def test_admin_happy_path(self, client, admin_auth_headers):
        response = client.post('/files/api/drive/disconnect', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['disconnected'] is True


# ── Drive: item / folder sync + bulk sync + resolve-missing ─────────────

class TestItemSync:
    def test_requires_auth(self, client):
        response = client.post('/files/api/items/1/sync')
        assert response.status_code in (401, 422)

    def test_disabled_400(self, client, admin_auth_headers, monkeypatch):
        folder = _create_folder(client, admin_auth_headers, name='Sync Item Folder Disabled')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='sync1.txt')
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        response = client.post(f"/files/api/items/{item['id']}/sync", headers=admin_auth_headers)
        assert response.status_code == 400

    def test_unknown_item_400(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: True)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: True)
        response = client.post('/files/api/items/999999999/sync', headers=admin_auth_headers)
        assert response.status_code == 400

    def test_happy_path_mocked(self, client, admin_auth_headers, monkeypatch):
        folder = _create_folder(client, admin_auth_headers, name='Sync Item Folder Happy')
        item = _upload_file(client, admin_auth_headers, folder['id'], filename='sync2.txt')

        def _fake_sync(item_id):
            from app.models import FilesItem, db

            row = db.session.get(FilesItem, item_id)
            row.sync_status = 'synced'
            row.drive_file_id = 'fake-drive-id'
            db.session.commit()
            return row

        monkeypatch.setattr('module_files.drive_service.sync_item', _fake_sync)
        response = client.post(f"/files/api/items/{item['id']}/sync", headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['item']['sync_status'] == 'synced'


class TestSyncNow:
    @pytest.mark.parametrize('path', ['/files/api/sync-pending', '/files/api/sync-now'])
    def test_requires_auth(self, client, path):
        response = client.post(path)
        assert response.status_code in (401, 422)

    @pytest.mark.parametrize('path', ['/files/api/sync-pending', '/files/api/sync-now'])
    def test_disabled_400(self, client, admin_auth_headers, monkeypatch, path):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        response = client.post(path, headers=admin_auth_headers)
        assert response.status_code == 400

    @pytest.mark.parametrize('path', ['/files/api/sync-pending', '/files/api/sync-now'])
    def test_happy_path_mocked(self, client, admin_auth_headers, monkeypatch, path):
        monkeypatch.setattr(
            'module_files.drive_service.sync_now',
            lambda: {
                'folders_created': 0, 'synced': [], 'failed': [],
                'missing_on_drive': {'folders': [], 'files': []}, 'needs_decision': False,
            },
        )
        response = client.post(path, headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['needs_decision'] is False


class TestResolveMissing:
    def test_requires_auth(self, client):
        response = client.post('/files/api/drive/resolve-missing', json={})
        assert response.status_code in (401, 422)

    def test_invalid_action_400(self, client, admin_auth_headers):
        response = client.post(
            '/files/api/drive/resolve-missing', json={'action': 'bogus'}, headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_disabled_400(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        response = client.post(
            '/files/api/drive/resolve-missing', json={'action': 'keep'}, headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_happy_path_mocked(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr(
            'module_files.drive_service.resolve_missing_on_drive',
            lambda action, folder_ids=None, item_ids=None: {
                'action': action, 'folders_kept': [], 'items_kept': [],
            },
        )
        response = client.post(
            '/files/api/drive/resolve-missing', json={'action': 'keep'}, headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.get_json()['action'] == 'keep'


class TestFolderSync:
    def test_requires_auth(self, client):
        response = client.post('/files/api/folders/1/sync')
        assert response.status_code in (401, 422)

    def test_disabled_400(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: False)
        response = client.post('/files/api/folders/1/sync', headers=admin_auth_headers)
        assert response.status_code == 400

    def test_unknown_folder_400(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: True)
        monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: True)
        monkeypatch.setattr('module_files.drive_service.get_connection', lambda: True)
        response = client.post('/files/api/folders/999999999/sync', headers=admin_auth_headers)
        assert response.status_code == 400

    def test_happy_path_mocked(self, client, admin_auth_headers, monkeypatch):
        folder = _create_folder(client, admin_auth_headers, name='Folder Sync Happy')
        monkeypatch.setattr(
            'module_files.drive_service.sync_folder',
            lambda folder_id: {
                'folder_id': folder_id, 'folders_synced': 1, 'synced': [], 'failed': [],
                'missing_on_drive': {'folders': [], 'files': []}, 'needs_decision': False,
            },
        )
        response = client.post(f"/files/api/folders/{folder['id']}/sync", headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['folder_id'] == folder['id']
