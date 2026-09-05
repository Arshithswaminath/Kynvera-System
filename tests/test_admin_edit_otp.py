"""Administrator profile edits require a verified email OTP grant."""

from app.models import User, db
from tests.factories import make_admin, make_user


OTP = '123456'


def _patch_otp_send(monkeypatch, sent=None, *, succeed=True):
    monkeypatch.setattr('app.admin.routes._generate_otp_code', lambda: OTP)

    def fake_send(user_email, code, full_name=None):
        if sent is not None:
            sent['email'] = user_email
            sent['code'] = code
            sent['full_name'] = full_name
        return succeed

    monkeypatch.setattr('common.email_service.send_admin_edit_otp_email', fake_send)


def _put_name(client, headers, user_id, name):
    return client.put(
        f'/api/admin/users/{user_id}',
        headers=headers,
        json={'full_name': name},
    )


def test_put_admin_without_grant_is_forbidden(client, admin_auth_headers, app):
    with app.app_context():
        target, _ = make_admin(full_name='Locked Admin Target')
        uid = target.id
        original = target.full_name

    response = _put_name(client, admin_auth_headers, uid, 'Hacked Name')
    assert response.status_code == 403
    data = response.get_json() or {}
    assert data.get('otp_required') is True
    assert 'one-time code' in (data.get('error') or '').lower()

    with app.app_context():
        row = db.session.get(User, uid)
        assert row is not None
        assert row.full_name == original


def test_request_otp_still_blocks_put_until_verify(client, admin_auth_headers, app, monkeypatch):
    sent = {}
    _patch_otp_send(monkeypatch, sent)

    with app.app_context():
        target, _ = make_admin(full_name='Awaiting Verify Admin', email='target-admin@example.com')
        uid = target.id
        original = target.full_name

    requested = client.post(f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers)
    assert requested.status_code == 200, requested.get_json()
    body = requested.get_json() or {}
    assert body.get('success') is True
    assert sent.get('email') == 'target-admin@example.com'
    assert sent.get('code') == OTP
    assert 't***@example.com' in (body.get('sent_to') or '')

    blocked = _put_name(client, admin_auth_headers, uid, 'Still Locked')
    assert blocked.status_code == 403
    assert (blocked.get_json() or {}).get('otp_required') is True
    with app.app_context():
        assert db.session.get(User, uid).full_name == original


def test_wrong_code_and_five_failures_invalidate(client, admin_auth_headers, app, monkeypatch):
    _patch_otp_send(monkeypatch)

    with app.app_context():
        target, _ = make_admin(full_name='Attempt Lock Admin')
        uid = target.id

    assert client.post(
        f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers
    ).status_code == 200

    for remaining in (4, 3, 2, 1):
        wrong = client.post(
            f'/api/admin/users/{uid}/edit-otp/verify',
            headers=admin_auth_headers,
            json={'code': '000000'},
        )
        assert wrong.status_code == 400
        err = (wrong.get_json() or {}).get('error') or ''
        assert 'Incorrect' in err
        assert str(remaining) in err

    fifth = client.post(
        f'/api/admin/users/{uid}/edit-otp/verify',
        headers=admin_auth_headers,
        json={'code': '000000'},
    )
    assert fifth.status_code == 400
    assert 'Too many' in ((fifth.get_json() or {}).get('error') or '')

    even_correct = client.post(
        f'/api/admin/users/{uid}/edit-otp/verify',
        headers=admin_auth_headers,
        json={'code': OTP},
    )
    assert even_correct.status_code == 400


def test_verify_unlocks_put(client, admin_auth_headers, app, monkeypatch):
    _patch_otp_send(monkeypatch)

    with app.app_context():
        target, _ = make_admin(full_name='Unlockable Admin')
        uid = target.id

    assert client.post(
        f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers
    ).status_code == 200

    verified = client.post(
        f'/api/admin/users/{uid}/edit-otp/verify',
        headers=admin_auth_headers,
        json={'code': OTP},
    )
    assert verified.status_code == 200, verified.get_json()
    vbody = verified.get_json() or {}
    assert vbody.get('unlocked') is True
    assert vbody.get('grant_expires_at')

    saved = _put_name(client, admin_auth_headers, uid, 'Updated Admin Name')
    assert saved.status_code == 200, saved.get_json()
    assert (saved.get_json() or {}).get('success') is True
    with app.app_context():
        assert db.session.get(User, uid).full_name == 'Updated Admin Name'


def test_non_admin_put_does_not_need_otp(client, admin_auth_headers, app):
    with app.app_context():
        user, _ = make_user(full_name='Regular Staff')
        uid = user.id

    response = _put_name(client, admin_auth_headers, uid, 'Regular Staff Updated')
    assert response.status_code == 200, response.get_json()
    with app.app_context():
        assert db.session.get(User, uid).full_name == 'Regular Staff Updated'


def test_promoting_to_admin_requires_grant_on_actor(client, admin_auth_headers, admin_user, app, monkeypatch):
    _patch_otp_send(monkeypatch)

    with app.app_context():
        staff, _ = make_user(full_name='Soon Admin')
        staff_id = staff.id
        actor_id = admin_user.id

    blocked = client.put(
        f'/api/admin/users/{staff_id}',
        headers=admin_auth_headers,
        json={'role': 'admin'},
    )
    assert blocked.status_code == 403
    assert (blocked.get_json() or {}).get('otp_required') is True
    with app.app_context():
        assert db.session.get(User, staff_id).role == 'user'

    # Grant is issued against the signed-in admin (actor), not the staff user.
    staff_request = client.post(
        f'/api/admin/users/{staff_id}/edit-otp/request',
        headers=admin_auth_headers,
    )
    assert staff_request.status_code == 400

    actor_request = client.post(
        f'/api/admin/users/{actor_id}/edit-otp/request',
        headers=admin_auth_headers,
    )
    assert actor_request.status_code == 200, actor_request.get_json()
    actor_verify = client.post(
        f'/api/admin/users/{actor_id}/edit-otp/verify',
        headers=admin_auth_headers,
        json={'code': OTP},
    )
    assert actor_verify.status_code == 200, actor_verify.get_json()

    promoted = client.put(
        f'/api/admin/users/{staff_id}',
        headers=admin_auth_headers,
        json={'role': 'admin'},
    )
    assert promoted.status_code == 200, promoted.get_json()
    with app.app_context():
        assert db.session.get(User, staff_id).role == 'admin'


def test_otp_request_returns_502_when_mail_fails(client, admin_auth_headers, app, monkeypatch):
    _patch_otp_send(monkeypatch, succeed=False)

    with app.app_context():
        target, _ = make_admin(full_name='Unmailed Admin')
        uid = target.id
        original = target.full_name

    failed = client.post(f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers)
    assert failed.status_code == 502
    blocked = _put_name(client, admin_auth_headers, uid, 'Should Stay Locked')
    assert blocked.status_code == 403
    with app.app_context():
        assert db.session.get(User, uid).full_name == original


def test_admin_pages_include_otp_lock_ui(client):
    team = client.get('/admin/team-management')
    assert team.status_code == 200
    team_html = team.get_data(as_text=True)
    assert 'profileAdminOtpModal' in team_html
    assert 'admin-edit-otp.js' in team_html
    assert 'Send verification code' in team_html
    assert 'profileAdminOtpBannerTitle' in team_html

    dash = client.get('/admin/dashboard')
    assert dash.status_code == 200
    dash_html = dash.get_data(as_text=True)
    assert 'profileAdminOtpModal' in dash_html
    assert 'admin-edit-otp.js' in dash_html
    assert 'Send verification code' in dash_html
    assert 'profileAdminOtpBannerTitle' in dash_html
    assert 'lockAdminProfileNow' in team_html
    assert 'unlockAdminProfileWithPassword' in team_html
    assert 'Your admin password' in dash_html


def test_verify_grant_is_ten_minutes(client, admin_auth_headers, app, monkeypatch):
    from datetime import datetime, timezone

    _patch_otp_send(monkeypatch)
    with app.app_context():
        target, _ = make_admin(full_name='Ten Minute Grant Admin')
        uid = target.id

    assert client.post(
        f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers
    ).status_code == 200
    verified = client.post(
        f'/api/admin/users/{uid}/edit-otp/verify',
        headers=admin_auth_headers,
        json={'code': OTP},
    )
    assert verified.status_code == 200
    body = verified.get_json() or {}
    assert '10 minutes' in (body.get('message') or '')
    iso = body.get('grant_expires_at') or ''
    dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    delta = (dt - datetime.now(timezone.utc)).total_seconds()
    assert 9 * 60 < delta <= 10 * 60 + 5


def test_resend_blocked_for_one_minute(client, admin_auth_headers, app, monkeypatch):
    from datetime import timedelta
    from common.datetime_utils import utc_now_naive

    _patch_otp_send(monkeypatch)
    with app.app_context():
        target, _ = make_admin(full_name='Resend Cooldown Admin')
        uid = target.id

    first = client.post(f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers)
    assert first.status_code == 200, first.get_json()
    first_body = first.get_json() or {}
    assert first_body.get('has_pending_code') is True
    assert (first_body.get('resend_after_seconds') or 0) > 0

    status = client.get(f'/api/admin/users/{uid}/edit-otp/status', headers=admin_auth_headers)
    assert status.status_code == 200
    st = status.get_json() or {}
    assert st.get('has_pending_code') is True
    assert (st.get('resend_after_seconds') or 0) > 0
    assert st.get('code_expires_at')
    assert st.get('unlocked') is False

    blocked = client.post(f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers)
    assert blocked.status_code == 429
    assert (blocked.get_json() or {}).get('resend_after_seconds', 0) > 0

    future = utc_now_naive() + timedelta(minutes=1, seconds=2)
    monkeypatch.setattr('app.admin.routes.utc_now_naive', lambda: future)
    allowed = client.post(f'/api/admin/users/{uid}/edit-otp/request', headers=admin_auth_headers)
    assert allowed.status_code == 200, allowed.get_json()


def test_password_unlock_and_lock_now(client, admin_auth_headers, app):
    with app.app_context():
        target, _ = make_admin(full_name='Password Unlock Admin')
        uid = target.id
        original = target.full_name

    wrong = client.post(
        f'/api/admin/users/{uid}/edit-otp/unlock-with-password',
        headers=admin_auth_headers,
        json={'password': 'not-the-admin-password'},
    )
    assert wrong.status_code == 400
    blocked = _put_name(client, admin_auth_headers, uid, 'Should Stay Locked')
    assert blocked.status_code == 403
    with app.app_context():
        assert db.session.get(User, uid).full_name == original

    unlocked = client.post(
        f'/api/admin/users/{uid}/edit-otp/unlock-with-password',
        headers=admin_auth_headers,
        json={'password': 'AdminPass123'},
    )
    assert unlocked.status_code == 200, unlocked.get_json()
    ubody = unlocked.get_json() or {}
    assert ubody.get('unlocked') is True
    assert ubody.get('grant_expires_at')
    assert '10 minutes' in (ubody.get('message') or '')

    saved = _put_name(client, admin_auth_headers, uid, 'Password Unlocked Name')
    assert saved.status_code == 200, saved.get_json()

    locked = client.post(
        f'/api/admin/users/{uid}/edit-otp/lock',
        headers=admin_auth_headers,
    )
    assert locked.status_code == 200, locked.get_json()
    assert (locked.get_json() or {}).get('unlocked') is False

    again = _put_name(client, admin_auth_headers, uid, 'After Lock Name')
    assert again.status_code == 403
    with app.app_context():
        assert db.session.get(User, uid).full_name == 'Password Unlocked Name'
