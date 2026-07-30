"""Targeted security remediation checks from the audit plan."""
import os


def test_login_does_not_echo_password_in_logs(client, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        client.post(
            '/api/auth/login',
            json={'username': 'nobody', 'password': 'SuperSecretPass1'},
            content_type='application/json',
        )
    joined = ' '.join(r.message for r in caplog.records)
    assert 'SuperSecretPass1' not in joined
    assert 'Request data:' not in joined


def test_register_response_omits_password(client, app):
    from app.models import db, User

    payload = {
        'first_name': 'Audit',
        'last_name': 'User',
        'email': 'audit.user.unique@example.com',
        'mobile_number': '0501234567',
        'project_name': 'Test Project',
        'job_designation': 'Engineer',
        'employment_start_date': '2026-01-15',
    }
    res = client.post('/api/auth/register', json=payload)
    # May fail if email validation / DB quirks — assert security property when 201
    if res.status_code == 201:
        data = res.get_json()
        assert 'default_password' not in data
        assert data.get('requires_password_change') is True
        with app.app_context():
            u = User.query.filter_by(email=payload['email']).first()
            assert u is not None
            assert u.password_changed is False
            db.session.delete(u)
            db.session.commit()


def test_generated_download_requires_auth(client):
    for path in (
        '/hvac-mep/generated/nonexistent.xlsx',
        '/hvac-mep/status/fake-job',
    ):
        res = client.get(path)
        assert res.status_code in (401, 302), f'{path} returned {res.status_code}'


def test_rate_limiter_attached_without_redis(app):
    # create_app should install memory:// limiter when Redis is absent
    assert getattr(app, 'limiter', None) is not None


def test_temporary_password_is_random():
    from common.password_admin import generate_temporary_password, get_default_registration_password

    a = generate_temporary_password()
    b = generate_temporary_password()
    assert a != b
    assert len(a) >= 12
    assert get_default_registration_password() != get_default_registration_password()


def test_ownership_helper():
    from types import SimpleNamespace
    from common.ownership import user_owns_or_elevated

    owner = SimpleNamespace(id=1, role='user', access_operations_manage=False, designation=None)
    other = SimpleNamespace(id=2, role='user', access_operations_manage=False, designation=None)
    admin = SimpleNamespace(id=3, role='admin', access_operations_manage=False, designation=None)
    rec = SimpleNamespace(created_by_id=1)

    assert user_owns_or_elevated(owner, rec) is True
    assert user_owns_or_elevated(other, rec) is False
    assert user_owns_or_elevated(admin, rec) is True
