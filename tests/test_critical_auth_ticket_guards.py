"""
Regression tests for critical auth and ticketing integrity bugs.
"""
import uuid
from unittest.mock import patch

import pytest


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


class TestMfaFailClosed:
    """Enrolled MFA must never be skipped when pyotp is missing."""

    def test_login_refuses_when_pyotp_missing(self, client, app):
        from app.models import db, User

        suffix = uuid.uuid4().hex[:8]
        with app.app_context():
            user = User(
                username=f'mfauser_{suffix}',
                email=f'mfauser_{suffix}@test.example',
                full_name='MFA User',
                role='user',
                is_active=True,
                password_changed=True,
                mfa_enabled=True,
                mfa_secret='JBSWY3DPEHPK3PXP',
            )
            user.set_password('TestPass123!')
            db.session.add(user)
            db.session.commit()
            username = user.username

        # sys.modules['pyotp'] = None makes `import pyotp` raise ImportError.
        with patch.dict('sys.modules', {'pyotp': None}):
            resp = client.post('/api/auth/login', json={
                'username': username,
                'password': 'TestPass123!',
                'mfa_code': '123456',
            })

        assert resp.status_code == 503, resp.get_json()
        body = resp.get_json()
        assert body.get('success') is False
        assert body.get('error_code') == 'MFA_UNAVAILABLE'
        assert 'access_token' not in body


class TestAdminSelfGuardIdentityCoercion:
    """JWT identity is a string; self-protection must compare as ints."""

    def test_admin_cannot_deactivate_self(self, client, app, admin_user, admin_auth_headers):
        with app.app_context():
            admin_id = admin_user.id
            was_active = admin_user.is_active

        resp = client.post(
            f'/api/admin/users/{admin_id}/toggle-active',
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400, resp.get_json()
        assert 'own account' in (resp.get_json().get('error') or '').lower()

        with app.app_context():
            from app.models import db, User
            still = db.session.get(User, admin_id)
            assert still.is_active is was_active

    def test_admin_cannot_delete_self(self, client, app, admin_user, admin_auth_headers):
        with app.app_context():
            admin_id = admin_user.id

        resp = client.delete(
            f'/api/admin/users/{admin_id}',
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400, resp.get_json()
        assert 'own account' in (resp.get_json().get('error') or '').lower()

        with app.app_context():
            from app.models import db, User
            assert db.session.get(User, admin_id) is not None

    def test_admin_cannot_demote_self(self, client, app, admin_user, admin_auth_headers):
        with app.app_context():
            admin_id = admin_user.id

        resp = client.put(
            f'/api/admin/users/{admin_id}',
            json={'role': 'user'},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400, resp.get_json()
        assert 'own role' in (resp.get_json().get('error') or '').lower()

        with app.app_context():
            from app.models import db, User
            assert db.session.get(User, admin_id).role == 'admin'


class TestTicketWorkflowGuards:
    """Assign / cost-delete / status must not break closed or late-stage tickets."""

    def _seed_ticket(self, app, *, status, reporter_id, supervisor_id=None):
        from app.models import db, Ticket

        tid = f'TKT-{uuid.uuid4().hex[:8].upper()}'
        with app.app_context():
            ticket = Ticket(
                ticket_id=tid,
                reporter_id=reporter_id,
                supervisor_id=supervisor_id or reporter_id,
                project='Test Project',
                service_group='HVAC',
                category='Repair',
                fault_type='Leak',
                priority='medium',
                title='Critical guard ticket',
                work_description='Fixture ticket for integrity guards',
                status=status,
            )
            db.session.add(ticket)
            db.session.commit()
            return tid, ticket.id

    def test_assign_technician_rejects_closed_ticket(self, client, app):
        from app.models import db, Ticket

        suffix = uuid.uuid4().hex[:8]
        admin_id, admin_u = _make_user(
            app, username=f'adm_{suffix}', role='admin', access_ticketing=True
        )
        tech_id, _ = _make_user(
            app, username=f'tech_{suffix}', designation='technician', access_ticketing=True
        )
        tid, _ = self._seed_ticket(app, status='closed', reporter_id=admin_id)
        headers = _login_headers(client, admin_u, 'TestPass123!')

        resp = client.post(
            f'/tickets/api/tickets/{tid}/assign-technician',
            json={'technician_id': tech_id},
            headers=headers,
        )
        assert resp.status_code == 400, resp.get_json()
        assert resp.get_json().get('success') is False

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.status == 'closed'
            assert ticket.technician_id is None

    def test_status_endpoint_rejects_closed_ticket(self, client, app):
        from app.models import db, Ticket

        suffix = uuid.uuid4().hex[:8]
        admin_id, admin_u = _make_user(
            app, username=f'adm2_{suffix}', role='admin', access_ticketing=True
        )
        tid, _ = self._seed_ticket(app, status='closed', reporter_id=admin_id)
        headers = _login_headers(client, admin_u, 'TestPass123!')

        resp = client.post(
            f'/tickets/api/tickets/{tid}/status',
            json={'status': 'open'},
            headers=headers,
        )
        assert resp.status_code == 400, resp.get_json()

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.status == 'closed'

    def test_delete_manpower_rejects_provider_closed(self, client, app):
        from app.models import db, Ticket, TicketManpower

        suffix = uuid.uuid4().hex[:8]
        admin_id, admin_u = _make_user(
            app, username=f'adm3_{suffix}', role='admin', access_ticketing=True
        )
        tid, internal_id = self._seed_ticket(
            app, status='provider_closed', reporter_id=admin_id
        )

        with app.app_context():
            entry = TicketManpower(
                ticket_id=internal_id,
                worker_name='Tech A',
                hours=2.0,
                rate_per_hour=50.0,
                total_cost=100.0,
            )
            db.session.add(entry)
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            ticket.total_cost = 100.0
            db.session.commit()
            entry_id = entry.id

        headers = _login_headers(client, admin_u, 'TestPass123!')
        resp = client.delete(
            f'/tickets/api/tickets/{tid}/manpower/{entry_id}',
            headers=headers,
        )
        assert resp.status_code == 400, resp.get_json()

        with app.app_context():
            assert db.session.get(TicketManpower, entry_id) is not None
            ticket = Ticket.query.filter_by(ticket_id=tid).first()
            assert ticket.total_cost == 100.0
