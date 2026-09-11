"""Regression tests for the Sep 2026 security hardening pass."""


def test_public_registration_defaults_closed():
    from config import ALLOW_PUBLIC_REGISTRATION
    assert ALLOW_PUBLIC_REGISTRATION is False


def test_set_password_does_not_store_plaintext(app, standard_user):
    from app.models import User, db

    with app.app_context():
        user = User.query.filter_by(username='testuser').one()
        user.set_password('NewPass456')
        db.session.commit()
        db.session.refresh(user)
        assert not (user.admin_visible_password or '')
        payload = user.to_dict(include_sensitive=True)
        assert 'admin_visible_password' not in payload
        assert payload.get('password_stored') is False


def test_admin_user_list_omits_plaintext_password(client, admin_auth_headers, standard_user):
    response = client.get('/api/admin/users', headers=admin_auth_headers)
    assert response.status_code == 200
    users = response.get_json().get('users') or []
    match = next(u for u in users if u.get('username') == 'testuser')
    assert 'admin_visible_password' not in match


def test_cookie_only_mutation_is_blocked(client, admin_user, app):
    login = client.post('/api/auth/login', json={
        'username': 'testadmin',
        'password': 'AdminPass123',
    })
    assert login.status_code == 200
    token = login.get_json()['access_token']
    cookie_name = app.config.get('JWT_ACCESS_COOKIE_NAME', 'access_token_cookie')
    client.set_cookie('localhost', cookie_name, token)

    blocked = client.post('/api/admin/users/backfill-passwords')
    assert blocked.status_code == 401
    body = blocked.get_json() or {}
    assert body.get('error_code') == 'CSRF_COOKIE_BLOCKED'


def test_bearer_mutation_still_works_with_cookies(client, admin_auth_headers):
    response = client.post('/api/admin/users/backfill-passwords', headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.get_json().get('success') is True


def test_login_still_allowed_without_bearer(client, standard_user):
    response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': 'TestPass123',
    })
    assert response.status_code == 200
    assert response.get_json().get('access_token')
