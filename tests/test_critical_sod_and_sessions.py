"""Regression tests for SoD verify/reopen and admin session-cut bugs."""
import uuid
from datetime import datetime, timedelta, timezone


def _login_headers(client, username, password):
    r = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json().get('access_token')
    assert token
    return {'Authorization': f'Bearer {token}'}


def _make_user(app, *, username, role='user', designation=None, access_ticketing=False, **extra):
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
            **extra,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        return user.id, user.username


def _seed_ticket(app, *, status, reporter_id, supervisor_id=None, technician_id=None):
    from app.models import db, Ticket

    tid = f'TKT-{uuid.uuid4().hex[:8].upper()}'
    with app.app_context():
        ticket = Ticket(
            ticket_id=tid,
            reporter_id=reporter_id,
            supervisor_id=supervisor_id,
            technician_id=technician_id,
            assigned_to_id=technician_id,
            project='Test Project',
            service_group='HVAC',
            category='Repair',
            fault_type='Leak',
            priority='medium',
            title='SoD guard ticket',
            work_description='Fixture ticket for SoD / session guards',
            status=status,
        )
        db.session.add(ticket)
        db.session.commit()
        return tid


class TestSupervisorCloseRequiresOwningSupervisor:
    """Technician who is also a global supervisor must not Stage-1 close own work."""

    def test_technician_with_supervisor_designation_cannot_self_verify(self, client, app):
        from app.models import db, Ticket

        suffix = uuid.uuid4().hex[:8]
        owner_id, _ = _make_user(
            app,
            username=f'owner_{suffix}',
            designation='supervisor',
            access_ticketing=True,
        )
        # Dual-role: assigned technician AND global supervisor designation.
        tech_id, tech_u = _make_user(
            app,
            username=f'dual_{suffix}',
            designation='supervisor',
            access_ticketing=True,
        )
        tid = _seed_ticket(
            app,
            status='work_completed',
            reporter_id=owner_id,
            supervisor_id=owner_id,
            technician_id=tech_id,
        )
        headers = _login_headers(client, tech_u, 'TestPass123!')

        resp = client.post(
            f'/tickets/api/tickets/{tid}/supervisor-close',
            json={
                'markup_pct': 10,
                'signature': 'data:image/png;base64,AAA',
                'signed_by': 'Dual Role',
                'signed_role': 'Supervisor',
            },
            headers=headers,
        )
        assert resp.status_code == 403, resp.get_json()
        assert resp.get_json().get('success') is False

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.status == 'work_completed'

    def test_owning_supervisor_can_stage1_close(self, client, app):
        from app.models import db, Ticket

        suffix = uuid.uuid4().hex[:8]
        owner_id, owner_u = _make_user(
            app,
            username=f'ownsup_{suffix}',
            designation='supervisor',
            access_ticketing=True,
        )
        tech_id, _ = _make_user(
            app,
            username=f'tech_{suffix}',
            designation='technician',
            access_ticketing=True,
        )
        tid = _seed_ticket(
            app,
            status='work_completed',
            reporter_id=owner_id,
            supervisor_id=owner_id,
            technician_id=tech_id,
        )
        headers = _login_headers(client, owner_u, 'TestPass123!')

        resp = client.post(
            f'/tickets/api/tickets/{tid}/supervisor-close',
            json={
                'markup_pct': 10,
                'signature': 'data:image/png;base64,AAA',
                'signed_by': 'Owning Supervisor',
                'signed_role': 'Supervisor',
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json().get('status') == 'provider_closed'

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.status == 'provider_closed'


class TestReopenRequiresPrivilege:
    """Reporters/technicians must not resurrect closed/invoiced tickets."""

    def test_reporter_cannot_reopen_closed_ticket(self, client, app):
        from app.models import db, Ticket

        suffix = uuid.uuid4().hex[:8]
        reporter_id, reporter_u = _make_user(
            app,
            username=f'rep_{suffix}',
            access_ticketing=True,
            is_ticket_reporter=True,
        )
        owner_id, _ = _make_user(
            app,
            username=f'sup_{suffix}',
            designation='supervisor',
            access_ticketing=True,
        )
        tid = _seed_ticket(
            app,
            status='closed',
            reporter_id=reporter_id,
            supervisor_id=owner_id,
        )
        headers = _login_headers(client, reporter_u, 'TestPass123!')

        resp = client.post(
            f'/tickets/api/tickets/{tid}/reopen',
            json={'reason': 'please reopen'},
            headers=headers,
        )
        assert resp.status_code == 403, resp.get_json()

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.status == 'closed'

    def test_owning_supervisor_can_reopen(self, client, app):
        from app.models import db, Ticket

        suffix = uuid.uuid4().hex[:8]
        reporter_id, _ = _make_user(
            app,
            username=f'rep2_{suffix}',
            access_ticketing=True,
            is_ticket_reporter=True,
        )
        owner_id, owner_u = _make_user(
            app,
            username=f'sup2_{suffix}',
            designation='supervisor',
            access_ticketing=True,
        )
        tid = _seed_ticket(
            app,
            status='closed',
            reporter_id=reporter_id,
            supervisor_id=owner_id,
        )
        headers = _login_headers(client, owner_u, 'TestPass123!')

        resp = client.post(
            f'/tickets/api/tickets/{tid}/reopen',
            json={'reason': 'rework needed'},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_json()

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.status == 'open'


class TestAdminDeactivateAndPasswordRevokeSessions:
    """Deactivate / admin password change must revoke live Session rows."""

    def test_deactivate_revokes_sessions(self, client, app, admin_user, admin_auth_headers):
        from app.models import db, Session, User

        suffix = uuid.uuid4().hex[:8]
        target_id, _ = _make_user(app, username=f'tgt_{suffix}', access_ticketing=True)

        with app.app_context():
            row = Session(
                user_id=target_id,
                token_jti=f'jti-deact-{suffix}',
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
                is_revoked=False,
            )
            db.session.add(row)
            db.session.commit()
            session_id = row.id

        resp = client.post(
            f'/api/admin/users/{target_id}/toggle-active',
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()

        with app.app_context():
            target = db.session.get(User, target_id)
            assert target.is_active is False
            row = db.session.get(Session, session_id)
            assert row is not None
            assert row.is_revoked is True

    def test_update_user_password_revokes_sessions(self, client, app, admin_user, admin_auth_headers):
        from app.models import db, Session

        suffix = uuid.uuid4().hex[:8]
        target_id, _ = _make_user(app, username=f'pwd_{suffix}', access_ticketing=True)

        with app.app_context():
            row = Session(
                user_id=target_id,
                token_jti=f'jti-pwd-{suffix}',
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
                is_revoked=False,
            )
            db.session.add(row)
            db.session.commit()
            session_id = row.id

        resp = client.put(
            f'/api/admin/users/{target_id}',
            json={'password': 'NewSecurePass1'},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()

        with app.app_context():
            row = db.session.get(Session, session_id)
            assert row is not None
            assert row.is_revoked is True
