"""Regression: ticketing users must not self-promote into the supervisor pool."""
import uuid

import pytest


def _login_headers(client, username, password):
    r = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json().get('access_token')
    assert token
    return {'Authorization': f'Bearer {token}'}


def _make_user(app, *, username, access_ticketing=True, designation=None, role='user'):
    from app.models import db, User

    with app.app_context():
        user = User(
            username=username,
            email=f'{username}@test.example',
            full_name=username.replace('_', ' ').title(),
            role=role,
            designation=designation,
            is_active=True,
            password_changed=True,
            access_ticketing=access_ticketing,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        return user.id, user.username


@pytest.fixture
def team_users(app):
    suffix = uuid.uuid4().hex[:8]
    reporter_id, reporter_u = _make_user(
        app, username=f'reporter_{suffix}', designation=None
    )
    tech_id, tech_u = _make_user(
        app, username=f'tech_{suffix}', designation=None
    )
    supervisor_id, supervisor_u = _make_user(
        app, username=f'sup_{suffix}', designation='supervisor'
    )
    return {
        'reporter': (reporter_id, reporter_u),
        'tech': (tech_id, tech_u),
        'supervisor': (supervisor_id, supervisor_u),
    }


def test_nondesignated_ticketing_user_cannot_self_promote_via_team(client, app, team_users):
    """access_ticketing alone must not create a TicketSupervisorTeam lead row."""
    from app.models import TicketSupervisorTeam, db
    from module_ticketing.routes import (
        _can_manage_own_supervisor_team,
        _is_supervisor_of_ticket,
        _user_in_supervisor_pool,
    )

    reporter_id, reporter_u = team_users['reporter']
    tech_id, _ = team_users['tech']
    headers = _login_headers(client, reporter_u, 'TestPass123!')

    before = client.post(
        '/tickets/api/supervisor/team',
        json={'technician_id': tech_id},
        headers=headers,
    )
    assert before.status_code == 403, before.get_json()
    assert before.get_json().get('success') is False

    with app.app_context():
        from app.models import User

        reporter = db.session.get(User, reporter_id)
        assert _can_manage_own_supervisor_team(reporter) is False
        assert _user_in_supervisor_pool(reporter) is False
        assert _is_supervisor_of_ticket(reporter) is False
        assert TicketSupervisorTeam.query.filter_by(
            supervisor_id=reporter_id, is_active=True
        ).count() == 0


def test_designated_supervisor_can_add_team_member(client, app, team_users):
    from app.models import TicketSupervisorTeam, db

    _, supervisor_u = team_users['supervisor']
    tech_id, _ = team_users['tech']
    headers = _login_headers(client, supervisor_u, 'TestPass123!')

    resp = client.post(
        '/tickets/api/supervisor/team',
        json={'technician_id': tech_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body.get('success') is True
    assert body.get('member', {}).get('technician_id') == tech_id

    with app.app_context():
        assert TicketSupervisorTeam.query.filter_by(
            supervisor_id=team_users['supervisor'][0],
            technician_id=tech_id,
            is_active=True,
        ).count() == 1
