"""Admin Manage profile PUT emails the user when fields actually change."""

from tests.factories import make_user


def _capture_deliveries(monkeypatch):
    from common import email_service as es

    captured = []

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured.append({
            'to': recipient,
            'subject': subject,
            'body': body,
            'html': html_body or '',
        })
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)
    return captured


def test_update_user_emails_profile_changes(client, admin_auth_headers, app, monkeypatch):
    captured = _capture_deliveries(monkeypatch)

    with app.app_context():
        user, _ = make_user(full_name='Pat Staff', email='pat.staff@kynvera.net')
        uid = user.id

    response = client.put(
        f'/api/admin/users/{uid}',
        headers=admin_auth_headers,
        json={'full_name': 'Pat Staff Updated', 'access_hr': True},
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json() or {}
    assert data.get('success') is True
    assert 'emailed about the changes' in (data.get('message') or '')
    assert len(captured) == 1
    assert captured[0]['to'] == 'pat.staff@kynvera.net'
    assert captured[0]['subject'] == 'Your Kynvera profile was updated'
    assert 'Full name: Pat Staff → Pat Staff Updated' in captured[0]['body']
    assert 'HR module: Off → On' in captured[0]['body']
    assert 'password' not in captured[0]['subject'].lower()


def test_update_user_skips_email_when_nothing_changed(client, admin_auth_headers, app, monkeypatch):
    captured = _capture_deliveries(monkeypatch)

    with app.app_context():
        user, _ = make_user(full_name='Unchanged Staff', email='unchanged@kynvera.net')
        uid = user.id
        payload = {
            'full_name': user.full_name,
            'email': user.email,
            'username': user.username,
            'role': user.role,
        }

    response = client.put(
        f'/api/admin/users/{uid}',
        headers=admin_auth_headers,
        json=payload,
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json() or {}
    assert data.get('success') is True
    assert data.get('message') == 'User updated successfully'
    assert captured == []


def test_update_user_password_only_sends_password_email(client, admin_auth_headers, app, monkeypatch):
    captured = _capture_deliveries(monkeypatch)

    with app.app_context():
        user, _ = make_user(full_name='Pw Staff', email='pw.staff@kynvera.net')
        uid = user.id

    response = client.put(
        f'/api/admin/users/{uid}',
        headers=admin_auth_headers,
        json={'password': 'NewPass123'},
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json() or {}
    assert 'password-updated email' in (data.get('message') or '')
    assert 'other changes' not in (data.get('message') or '')
    assert len(captured) == 1
    assert captured[0]['subject'] == 'Your Kynvera password was updated'


def test_update_user_email_change_notifies_old_and_new(client, admin_auth_headers, app, monkeypatch):
    captured = _capture_deliveries(monkeypatch)

    with app.app_context():
        user, _ = make_user(full_name='Mail Staff', email='old.mail@kynvera.net')
        uid = user.id

    response = client.put(
        f'/api/admin/users/{uid}',
        headers=admin_auth_headers,
        json={'email': 'new.mail@kynvera.net'},
    )
    assert response.status_code == 200, response.get_json()
    assert [item['to'] for item in captured] == ['new.mail@kynvera.net', 'old.mail@kynvera.net']
    assert captured[0]['subject'] == 'Your Kynvera profile was updated'
    assert 'Email: old.mail@kynvera.net → new.mail@kynvera.net' in captured[0]['body']
    assert captured[1]['subject'] == 'Your Kynvera email address was changed'
    assert 'new.mail@kynvera.net' in captured[1]['body']
