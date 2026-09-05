"""Admin can delete a user only after the account is deactivated."""

from app.models import User, db
from tests.factories import make_user


def test_cannot_delete_active_user(client, admin_auth_headers, app):
    with app.app_context():
        user, _ = make_user(full_name='Active Delete Target')
        uid = user.id
        assert user.is_active is True

    response = client.delete(f'/api/admin/users/{uid}', headers=admin_auth_headers)
    assert response.status_code == 400
    data = response.get_json() or {}
    assert 'Deactivate this account before deleting it' in (data.get('error') or '')

    with app.app_context():
        assert db.session.get(User, uid) is not None


def test_delete_inactive_user_with_dochub_access(client, admin_auth_headers, app):
    from app.models import DocHubAccess

    with app.app_context():
        user, _ = make_user(full_name='DocHub Delete Target')
        uid = user.id
        username = user.username
        db.session.add(DocHubAccess(user_id=uid, can_access=True))
        db.session.commit()

    deactivated = client.post(
        f'/api/admin/users/{uid}/toggle-active',
        headers=admin_auth_headers,
    )
    assert deactivated.status_code == 200

    deleted = client.delete(f'/api/admin/users/{uid}', headers=admin_auth_headers)
    assert deleted.status_code == 200, deleted.get_json()
    body = deleted.get_json() or {}
    assert body.get('success') is True
    assert username in (body.get('message') or '')

    with app.app_context():
        assert db.session.get(User, uid) is None
        assert DocHubAccess.query.filter_by(user_id=uid).first() is None


def test_delete_inactive_user(client, admin_auth_headers, app):
    with app.app_context():
        user, _ = make_user(full_name='Inactive Delete Target')
        uid = user.id
        username = user.username

    deactivated = client.post(
        f'/api/admin/users/{uid}/toggle-active',
        headers=admin_auth_headers,
    )
    assert deactivated.status_code == 200
    assert (deactivated.get_json() or {}).get('success') is True

    deleted = client.delete(f'/api/admin/users/{uid}', headers=admin_auth_headers)
    assert deleted.status_code == 200
    body = deleted.get_json() or {}
    assert body.get('success') is True
    assert username in (body.get('message') or '')

    with app.app_context():
        assert db.session.get(User, uid) is None


def test_cannot_delete_own_account(client, admin_auth_headers, admin_user, app):
    with app.app_context():
        uid = admin_user.id

    response = client.delete(f'/api/admin/users/{uid}', headers=admin_auth_headers)
    assert response.status_code == 400
    data = response.get_json() or {}
    assert 'Cannot delete your own account' in (data.get('error') or '')

    with app.app_context():
        assert db.session.get(User, uid) is not None


def test_non_admin_cannot_delete_user(client, auth_headers, app):
    with app.app_context():
        user, _ = make_user(is_active=False, full_name='Guard Delete Target')
        uid = user.id

    response = client.delete(f'/api/admin/users/{uid}', headers=auth_headers)
    assert response.status_code == 403

    with app.app_context():
        assert db.session.get(User, uid) is not None


def test_team_page_gates_delete_to_inactive_users(client):
    response = client.get('/admin/team-management')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-action="delete-user"' in html
    assert '!u.is_active && Number(u.id) !== tmSelfUserId()' in html
    assert 'profileDeleteConfirmModal' in html
    assert 'id="profileDeleteUserBtn"' in html


def test_delete_inactive_user_who_reported_tickets(client, admin_auth_headers, admin_user, app):
    from app.models import Ticket

    with app.app_context():
        user, _ = make_user(full_name='Reporter Delete Target')
        uid = user.id
        actor_id = admin_user.id
        codes = [f'TKT-DEL{uid}-0', f'TKT-DEL{uid}-1']
        for code in codes:
            db.session.add(Ticket(
                ticket_id=code,
                reporter_id=uid,
                title='Pump leak',
                project='Ajman',
                service_group='HVAC',
                category='AC',
                fault_type='Leak',
                work_description='Water on floor',
            ))
        db.session.commit()

    deactivated = client.post(
        f'/api/admin/users/{uid}/toggle-active',
        headers=admin_auth_headers,
    )
    assert deactivated.status_code == 200

    deleted = client.delete(f'/api/admin/users/{uid}', headers=admin_auth_headers)
    assert deleted.status_code == 200, deleted.get_json()
    body = deleted.get_json() or {}
    assert body.get('success') is True
    assert body.get('tickets_reassigned') == 2
    message = body.get('message') or ''
    assert '2 tickets' in message
    assert 'Reporter Delete Target' in message

    with app.app_context():
        assert db.session.get(User, uid) is None
        leftover = []
        for code in (f'TKT-DEL{uid}-0', f'TKT-DEL{uid}-1'):
            ticket = Ticket.query.filter_by(ticket_id=code).first()
            assert ticket is not None
            assert ticket.reporter_id == actor_id
            leftover.append(ticket)
        for ticket in leftover:
            db.session.delete(ticket)
        db.session.commit()


def test_list_users_omits_email_intake_account(client, admin_auth_headers, app):
    from tests.factories import make_user

    with app.app_context():
        make_user(
            username='email_intake',
            email='email-intake@injaaz.system',
            full_name='Email Intake (System)',
        )

    response = client.get('/api/admin/users', headers=admin_auth_headers)
    assert response.status_code == 200
    users = (response.get_json() or {}).get('users') or []
    names = {u.get('username') for u in users}
    assert 'email_intake' not in names
