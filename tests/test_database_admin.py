"""Admin database status and backup APIs."""


def test_database_page_renders(client):
    response = client.get('/admin/database')
    assert response.status_code == 200
    assert b'Download a copy' in response.data


def test_database_status_requires_admin(client, auth_headers):
    response = client.get('/api/admin/database/status', headers=auth_headers)
    assert response.status_code == 403


def test_database_status_admin(client, admin_auth_headers):
    response = client.get('/api/admin/database/status', headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('success') is True
    assert data.get('environment') in ('local', 'live')
    assert data.get('engine') in ('sqlite', 'postgresql')
    assert 'environment_plain' in data
    assert isinstance(data.get('modules'), list)
    assert data.get('database_name')
    assert '://' not in (data.get('host') or '')


def test_database_backup_download(client, admin_auth_headers, app):
    response = client.post('/api/admin/database/backup', headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.data
    cd = response.headers.get('Content-Disposition', '')
    assert 'injaaz-local-' in cd
    from app.models import DatabaseBackup
    with app.app_context():
        row = DatabaseBackup.query.filter_by(status='ok').first()
        assert row is not None
        assert row.environment == 'local'


def test_browse_users_read_only(client, admin_auth_headers, admin_user):
    response = client.get('/api/admin/database/tables/users', headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('read_only') is True
    assert data.get('table') == 'users'
    assert data.get('total') >= 1
    assert data.get('rows')
    first = data['rows'][0]
    assert 'password_hash' not in (first.get('preview') or {})
    detail = first.get('detail') or {}
    assert detail.get('password_hash', {}).get('hidden') is True
    assert detail.get('mfa_secret', {}).get('hidden') is True
    preview = first.get('preview') or {}
    assert 'username' in preview or 'email' in preview


def test_browse_unknown_table(client, admin_auth_headers):
    response = client.get('/api/admin/database/tables/not_a_real_table', headers=admin_auth_headers)
    assert response.status_code == 404


def test_browse_requires_admin(client, auth_headers):
    response = client.get('/api/admin/database/tables/users', headers=auth_headers)
    assert response.status_code == 403
