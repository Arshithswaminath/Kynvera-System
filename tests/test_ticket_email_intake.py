"""Regression tests for ticket email intake webhook correctness."""
import os

import pytest


WEBHOOK_SECRET = 'test-inbound-webhook-secret'


@pytest.fixture(autouse=True)
def _configure_inbound_secret(app):
    previous = os.environ.get('TICKET_INBOUND_WEBHOOK_SECRET')
    os.environ['TICKET_INBOUND_WEBHOOK_SECRET'] = WEBHOOK_SECRET
    app.config['TICKET_INBOUND_WEBHOOK_SECRET'] = WEBHOOK_SECRET
    yield
    if previous is None:
        os.environ.pop('TICKET_INBOUND_WEBHOOK_SECRET', None)
    else:
        os.environ['TICKET_INBOUND_WEBHOOK_SECRET'] = previous


def _mailjet_payload(message_id='<msg-1@example.com>', subject='Leak in lobby', **overrides):
    payload = {
        'Sender': 'tenant@example.com',
        'From': 'Tenant User <tenant@example.com>',
        'Recipient': 'tickets@intake.example.com',
        'Subject': subject,
        'Text-part': 'Property: Tower A\nZone: Lobby\nUnit: G01\nWater leaking near entrance.',
        'Headers': {'Message-ID': message_id},
    }
    payload.update(overrides)
    return payload


class TestInboundEmailWebhook:
    def test_success_creates_draft(self, client, app):
        from app.models import Ticket, TicketEmailIntake

        with app.app_context():
            response = client.post(
                f'/tickets/api/inbound-email/{WEBHOOK_SECRET}',
                json=_mailjet_payload(),
            )
            assert response.status_code == 200
            assert response.get_json()['success'] is True

            ticket = Ticket.query.filter_by(source_message_id='<msg-1@example.com>').first()
            assert ticket is not None
            assert ticket.status == 'draft'
            assert ticket.source == 'email'

            intake = TicketEmailIntake.query.filter_by(message_id='<msg-1@example.com>').first()
            assert intake is not None
            assert intake.status == 'processed'
            assert intake.ticket_id == ticket.id

    def test_error_does_not_poison_message_id_and_returns_500(self, client, app, monkeypatch):
        from app.models import Ticket, TicketEmailIntake
        import module_ticketing.routes as routes

        with app.app_context():
            monkeypatch.setattr(routes, '_resolve_email_intake_reporter', lambda _email: None)

            first = client.post(
                f'/tickets/api/inbound-email/{WEBHOOK_SECRET}',
                json=_mailjet_payload(message_id='<fail-then-retry@example.com>'),
            )
            assert first.status_code == 500
            assert Ticket.query.filter_by(
                source_message_id='<fail-then-retry@example.com>'
            ).first() is None
            err_rows = TicketEmailIntake.query.filter_by(
                message_id='<fail-then-retry@example.com>',
                status='error',
            ).all()
            assert len(err_rows) == 1

            # Restore reporter resolution for retry
            monkeypatch.undo()

            retry = client.post(
                f'/tickets/api/inbound-email/{WEBHOOK_SECRET}',
                json=_mailjet_payload(message_id='<fail-then-retry@example.com>'),
            )
            assert retry.status_code == 200
            ticket = Ticket.query.filter_by(
                source_message_id='<fail-then-retry@example.com>'
            ).first()
            assert ticket is not None
            assert ticket.status == 'draft'
            processed = TicketEmailIntake.query.filter_by(
                message_id='<fail-then-retry@example.com>',
                status='processed',
            ).first()
            assert processed is not None
            assert processed.ticket_id == ticket.id

    def test_duplicate_after_success_is_ignored(self, client, app):
        from app.models import Ticket, TicketEmailIntake

        with app.app_context():
            first = client.post(
                f'/tickets/api/inbound-email/{WEBHOOK_SECRET}',
                json=_mailjet_payload(message_id='<dup@example.com>'),
            )
            assert first.status_code == 200

            second = client.post(
                f'/tickets/api/inbound-email/{WEBHOOK_SECRET}',
                json=_mailjet_payload(message_id='<dup@example.com>'),
            )
            assert second.status_code == 200
            assert Ticket.query.filter_by(source_message_id='<dup@example.com>').count() == 1
            assert TicketEmailIntake.query.filter_by(
                message_id='<dup@example.com>',
                status='duplicate',
            ).count() == 1

    def test_long_subject_fields_are_truncated_not_rejected(self, client, app):
        from app.models import Ticket

        long_project = 'P' * 200
        long_category = 'C' * 180
        long_title = 'T' * 300
        subject = f'[{long_project}] {long_category} - high - {long_title}'

        with app.app_context():
            response = client.post(
                f'/tickets/api/inbound-email/{WEBHOOK_SECRET}',
                json=_mailjet_payload(message_id='<long@example.com>', subject=subject),
            )
            assert response.status_code == 200
            ticket = Ticket.query.filter_by(source_message_id='<long@example.com>').first()
            assert ticket is not None
            assert len(ticket.project) <= 160
            assert len(ticket.category) <= 120
            assert len(ticket.title) <= 255
            assert ticket.source_subject is None or len(ticket.source_subject) <= 500
