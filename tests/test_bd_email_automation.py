"""BD email automations: personal/public ACL, cloud-file fetch, require_new, scheduler."""

from datetime import datetime, timedelta
from io import BytesIO

import pytest


def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


def _make_bd_user(app, username, email, full_name):
    from app.models import User, db

    with app.app_context():
        existing = User.query.filter_by(username=username).first()
        if existing:
            return existing.id
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role='user',
            designation='business_development',
            is_active=True,
            password_changed=True,
        )
        user.set_password('BdPass123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _headers(client, username):
    return _login(client, username, 'BdPass123')


@pytest.fixture
def bd_users(app, client):
    id_a = _make_bd_user(app, 'bd_alpha', 'alpha@example.com', 'BD Alpha')
    id_b = _make_bd_user(app, 'bd_bravo', 'bravo@example.com', 'BD Bravo')
    return {
        'a_id': id_a,
        'b_id': id_b,
        'a': _headers(client, 'bd_alpha'),
        'b': _headers(client, 'bd_bravo'),
    }


def _make_file(app, user_id, data=b'cloud-bytes', name='brief.txt'):
    from module_files.service import get_folder_by_path_key, save_bytes_to_folder

    with app.app_context():
        folder = get_folder_by_path_key('reports/email', created_by=user_id)
        item = save_bytes_to_folder(
            folder=folder,
            data=data,
            display_name=name,
            filename=name,
            mime_type='text/plain',
            source_module='upload',
            source_kind='upload',
            created_by=user_id,
        )
        return item.id, folder.id


def test_personal_hidden_from_other_bd_user(client, app, bd_users):
    created = client.post('/bd/email-module/automations', json={
        'name': 'Alpha personal',
        'scope': 'personal',
        'to_emails': 'gm@example.com',
        'subject': 'Hello',
        'body': 'Body',
    }, headers=bd_users['a'])
    assert created.status_code == 201, created.get_json()
    auto_id = created.get_json()['item']['id']

    listed = client.get('/bd/email-module/automations?scope=personal', headers=bd_users['b'])
    assert listed.status_code == 200
    ids = [item['id'] for item in listed.get_json().get('items') or []]
    assert auto_id not in ids

    denied = client.get(f'/bd/email-module/automations/{auto_id}', headers=bd_users['b'])
    assert denied.status_code == 403


def test_public_visible_and_runnable_but_not_editable(client, app, bd_users, monkeypatch):
    from common import email_service as es

    monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.email_automation.is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.routes.is_email_configured', lambda app=None: True)
    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

    created = client.post('/bd/email-module/automations', json={
        'name': 'Shared pack',
        'scope': 'public',
        'to_emails': 'gm@example.com',
        'subject': 'Public update',
        'body': 'Please review',
    }, headers=bd_users['a'])
    assert created.status_code == 201, created.get_json()
    auto_id = created.get_json()['item']['id']

    listed = client.get('/bd/email-module/automations?scope=public', headers=bd_users['b'])
    assert listed.status_code == 200
    ids = [item['id'] for item in listed.get_json().get('items') or []]
    assert auto_id in ids

    patched = client.patch(f'/bd/email-module/automations/{auto_id}', json={'name': 'Hijack'}, headers=bd_users['b'])
    assert patched.status_code == 403

    ran = client.post(f'/bd/email-module/automations/{auto_id}/run', headers=bd_users['b'])
    assert ran.status_code == 200, ran.get_json()
    assert ran.get_json().get('success') is True


def test_upload_and_linked_file_resolve_attaches_bytes(client, app, bd_users, monkeypatch):
    from common import email_service as es

    captured = {}

    def fake_deliver(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['attachments'] = attachments
        return True

    monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.email_automation.is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.routes.is_email_configured', lambda app=None: True)
    monkeypatch.setattr(es, '_deliver_email', fake_deliver)

    created = client.post('/bd/email-module/automations', json={
        'name': 'With file',
        'scope': 'personal',
        'to_emails': 'gm@example.com',
        'subject': 'File run',
        'body': 'See attached',
    }, headers=bd_users['a'])
    auto_id = created.get_json()['item']['id']

    upload = client.post(
        f'/bd/email-module/automations/{auto_id}/attachments/upload',
        data={'file': (BytesIO(b'hello-cloud'), 'pack.txt')},
        headers=bd_users['a'],
        content_type='multipart/form-data',
    )
    assert upload.status_code == 201, upload.get_json()

    ran = client.post(f'/bd/email-module/automations/{auto_id}/run', headers=bd_users['a'])
    assert ran.status_code == 200, ran.get_json()
    atts = captured.get('attachments') or []
    assert atts
    first = atts[0]
    if isinstance(first, dict):
        assert first['content'] == b'hello-cloud'
        assert 'pack.txt' in first['filename']
    else:
        with open(first, 'rb') as fh:
            assert fh.read() == b'hello-cloud'


def test_require_new_skips_when_unchanged_and_sends_when_newer(client, app, bd_users, monkeypatch):
    from app.models import FilesItem, db
    from common import email_service as es
    from common.datetime_utils import utc_now_naive

    sends = {'count': 0}

    def fake_deliver(*a, **k):
        sends['count'] += 1
        return True

    monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.email_automation.is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.routes.is_email_configured', lambda app=None: True)
    monkeypatch.setattr(es, '_deliver_email', fake_deliver)

    item_id, folder_id = _make_file(app, bd_users['a_id'], data=b'v1', name='weekly.txt')
    created = client.post('/bd/email-module/automations', json={
        'name': 'Fresh file',
        'scope': 'personal',
        'to_emails': 'gm@example.com',
        'subject': 'Fresh',
        'body': 'Need new file',
        'attachments': [{
            'kind': 'linked_file',
            'files_item_id': item_id,
            'require_new': True,
        }],
    }, headers=bd_users['a'])
    assert created.status_code == 201, created.get_json()
    auto_id = created.get_json()['item']['id']

    first = client.post(f'/bd/email-module/automations/{auto_id}/run', headers=bd_users['a'])
    assert first.status_code == 200, first.get_json()
    assert first.get_json().get('skipped') is not True
    assert sends['count'] == 1

    second = client.post(f'/bd/email-module/automations/{auto_id}/run', headers=bd_users['a'])
    assert second.status_code == 200, second.get_json()
    assert second.get_json().get('skipped') is True
    assert sends['count'] == 1

    with app.app_context():
        item = db.session.get(FilesItem, item_id)
        item.updated_at = utc_now_naive() + timedelta(seconds=5)
        db.session.commit()

    third = client.post(f'/bd/email-module/automations/{auto_id}/run', headers=bd_users['a'])
    assert third.status_code == 200, third.get_json()
    assert third.get_json().get('skipped') is not True
    assert sends['count'] == 2


def test_drive_refresh_mocked_updates_local_then_attaches(client, app, bd_users, monkeypatch):
    from app.models import FilesItem, db
    from common import email_service as es
    from module_files import service as files_service

    captured = {}

    def fake_deliver(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['attachments'] = attachments
        return True

    def fake_refresh(item_id):
        item = db.session.get(FilesItem, item_id)
        path = files_service.resolve_item_abs_path(item)
        with open(path, 'wb') as fh:
            fh.write(b'drive-latest')
        item.size_bytes = len(b'drive-latest')
        db.session.commit()
        return item

    monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.email_automation.is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.routes.is_email_configured', lambda app=None: True)
    monkeypatch.setattr(es, '_deliver_email', fake_deliver)
    monkeypatch.setattr('module_files.drive_service.drive_enabled', lambda: True)
    monkeypatch.setattr('module_files.drive_service.drive_configured', lambda: True)
    monkeypatch.setattr('module_files.drive_service.get_connection', lambda: True)
    monkeypatch.setattr('module_files.drive_service.refresh_item_from_drive', fake_refresh)

    item_id, _folder_id = _make_file(app, bd_users['a_id'], data=b'local-old', name='drive.txt')
    with app.app_context():
        item = db.session.get(FilesItem, item_id)
        item.drive_file_id = 'drive-file-1'
        item.sync_status = 'synced'
        db.session.commit()

    created = client.post('/bd/email-module/automations', json={
        'name': 'Drive fetch',
        'scope': 'personal',
        'to_emails': 'gm@example.com',
        'subject': 'Drive',
        'body': 'From drive',
        'attachments': [{'kind': 'linked_file', 'files_item_id': item_id}],
    }, headers=bd_users['a'])
    auto_id = created.get_json()['item']['id']
    ran = client.post(f'/bd/email-module/automations/{auto_id}/run', headers=bd_users['a'])
    assert ran.status_code == 200, ran.get_json()
    first = (captured.get('attachments') or [None])[0]
    assert isinstance(first, dict)
    assert first['content'] == b'drive-latest'


def test_scheduler_sends_once_per_dubai_day(app, bd_users, monkeypatch):
    from app.bd.email_scheduler import _already_ran_today, _run_due_automations
    from app.models import EmailAutomation, db
    from common import email_service as es
    from zoneinfo import ZoneInfo

    sends = {'count': 0}

    def fake_deliver(*a, **k):
        sends['count'] += 1
        return True

    monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.email_automation.is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.routes.is_email_configured', lambda app=None: True)
    monkeypatch.setattr(es, '_deliver_email', fake_deliver)

    now = datetime.now(ZoneInfo('Asia/Dubai'))
    with app.app_context():
        auto = EmailAutomation(
            name='Daily',
            scope='public',
            owner_id=bd_users['a_id'],
            to_emails='gm@example.com',
            subject='Daily',
            body='Scheduled',
            enabled=True,
            schedule_enabled=True,
            schedule_paused=False,
            schedule_hour=now.hour,
            schedule_minute=now.minute,
        )
        db.session.add(auto)
        db.session.commit()
        auto_id = auto.id

    _run_due_automations(app)
    _run_due_automations(app)
    assert sends['count'] == 1

    with app.app_context():
        auto = db.session.get(EmailAutomation, auto_id)
        assert auto.last_success_at is not None
        assert _already_ran_today(auto, datetime.now(ZoneInfo('Asia/Dubai'))) is True


def test_send_once_still_logs_bd_email(client, app, admin_auth_headers, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.email_automation.is_email_configured', lambda app=None: True)
    monkeypatch.setattr('app.bd.routes.is_email_configured', lambda app=None: True)
    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

    response = client.post('/bd/email-module/send', json={
        'to': 'gm@example.com',
        'subject': 'One shot',
        'message': 'Please review',
    }, headers=admin_auth_headers)
    assert response.status_code == 200, response.get_json()
    assert response.get_json().get('success') is True

    with app.app_context():
        row = EmailLog.query.filter_by(source='bd_email', subject='One shot').order_by(EmailLog.id.desc()).first()
        assert row is not None
        assert row.status == 'sent'
        assert 'gm@example.com' in (row.to_emails or '')
