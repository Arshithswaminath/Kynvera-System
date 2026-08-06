"""Regression tests for critical auth / invoice routing bugs."""
from datetime import datetime, timedelta, timezone

import pytest


class TestMfaSetupDoesNotDisableEnrolledUsers:
    """POST /api/auth/mfa/setup must not silently turn off enrolled MFA."""

    def test_setup_refuses_when_mfa_already_enabled(self, client, auth_headers, standard_user, app):
        pytest.importorskip('pyotp')
        from app.models import db, User

        with app.app_context():
            user = db.session.get(User, standard_user.id)
            user.mfa_enabled = True
            user.mfa_secret = 'EXISTINGSECRETBASE32AAA'
            db.session.commit()
            prior_secret = user.mfa_secret

            response = client.post('/api/auth/mfa/setup', headers=auth_headers)
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'MFA_ALREADY_ENABLED'

            user = db.session.get(User, standard_user.id)
            assert user.mfa_enabled is True
            assert user.mfa_secret == prior_secret

    def test_setup_allowed_when_mfa_not_enabled(self, client, auth_headers, standard_user, app):
        pytest.importorskip('pyotp')
        from app.models import db, User

        with app.app_context():
            user = db.session.get(User, standard_user.id)
            user.mfa_enabled = False
            user.mfa_secret = None
            db.session.commit()

            response = client.post('/api/auth/mfa/setup', headers=auth_headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('success') is True
            assert data.get('mfa_enabled') is False
            assert data.get('secret')

            user = db.session.get(User, standard_user.id)
            assert user.mfa_enabled is False
            assert user.mfa_secret


class TestAdminPasswordResetRevokesSessions:
    """Admin reset must revoke active sessions like change-password does."""

    def test_reset_password_revokes_target_sessions(self, client, admin_auth_headers, standard_user, app):
        from app.models import db, Session, User

        with app.app_context():
            target = db.session.get(User, standard_user.id)
            session_row = Session(
                user_id=target.id,
                token_jti='test-jti-still-valid',
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
                is_revoked=False,
            )
            db.session.add(session_row)
            db.session.commit()
            session_id = session_row.id

            response = client.post(
                f'/api/admin/users/{target.id}/reset-password',
                headers=admin_auth_headers,
            )
            assert response.status_code == 200

            row = db.session.get(Session, session_id)
            assert row is not None
            assert row.is_revoked is True


class TestInvoiceRecipientsIgnoreInactiveProjects:
    """Closing invoices must not use soft-deleted project contact lists."""

    def test_prefers_active_project_contacts(self, app, standard_user):
        from app.models import db, Ticket, TicketProject
        from module_ticketing.routes import _invoice_recipient_emails

        with app.app_context():
            inactive = TicketProject(
                name='Ajman HQ',
                is_active=False,
                finance_emails='old-finance@client.gov',
                ops_emails='old-ops@client.gov',
            )
            active = TicketProject(
                name='Ajman HQ',
                is_active=True,
                finance_emails='new-finance@client.gov',
                ops_emails='new-ops@client.gov',
            )
            db.session.add_all([inactive, active])
            db.session.flush()

            ticket = Ticket(
                ticket_id='TKT-TEST-INVOICE-1',
                reporter_id=standard_user.id,
                project='Ajman HQ',
                service_group='HVAC',
                category='Repair',
                fault_type='Leak',
                priority='medium',
                title='AC leak',
                work_description='Fix leak',
                status='closed',
            )
            db.session.add(ticket)
            db.session.commit()

            recipients = _invoice_recipient_emails(ticket)
            assert 'new-finance@client.gov' in recipients
            assert 'new-ops@client.gov' in recipients
            assert 'old-finance@client.gov' not in recipients
            assert 'old-ops@client.gov' not in recipients

            db.session.delete(ticket)
            db.session.delete(active)
            db.session.delete(inactive)
            db.session.commit()
