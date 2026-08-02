"""Regression: Ticket hold/cancel/advance fields must persist via the ORM."""
import pytest


@pytest.fixture
def ticketing_user(app):
    from app.models import db, User, Ticket, TicketNote

    with app.app_context():
        user = User(
            username='tktuser',
            email='tktuser@example.com',
            full_name='Ticketing User',
            role='user',
            is_active=True,
            password_changed=True,
            access_ticketing=True,
        )
        user.set_password('TktPass123')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        yield user
        # Tickets reference reporter_id NOT NULL — remove dependent rows first.
        tickets = Ticket.query.filter_by(reporter_id=user_id).all()
        for ticket in tickets:
            TicketNote.query.filter_by(ticket_id=ticket.id).delete()
            db.session.delete(ticket)
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()


@pytest.fixture
def ticketing_auth_headers(client, ticketing_user, app):
    with app.app_context():
        response = client.post('/api/auth/login', json={
            'username': 'tktuser',
            'password': 'TktPass123',
        })
        data = response.get_json()
        return {'Authorization': f'Bearer {data["access_token"]}'}


def _make_ticket(app, reporter_id, status='work_started', ticket_id='TKT-HOLD01'):
    from app.models import db, Ticket

    with app.app_context():
        ticket = Ticket(
            ticket_id=ticket_id,
            reporter_id=reporter_id,
            title='Leaking valve',
            project='Ajman HQ',
            service_group='MEP',
            category='Plumbing',
            fault_type='Leak',
            priority='high',
            work_description='Valve leaking on level 2',
            status=status,
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket.ticket_id


class TestTicketHoldResumePersistence:
    def test_hold_persists_previous_status_and_resume_restores_it(
        self, client, app, ticketing_user, ticketing_auth_headers
    ):
        from app.models import db, Ticket

        code = _make_ticket(app, ticketing_user.id, status='work_started', ticket_id='TKT-HOLD01')

        hold = client.post(
            f'/tickets/api/tickets/{code}/hold',
            json={'reason': 'pending_materials', 'notes': 'Awaiting parts'},
            headers=ticketing_auth_headers,
        )
        assert hold.status_code == 200, hold.get_json()
        assert hold.get_json()['status'] == 'on_hold'

        with app.app_context():
            db.session.expire_all()
            ticket = Ticket.query.filter_by(ticket_id=code).first()
            assert ticket is not None
            assert ticket.status == 'on_hold'
            assert ticket.previous_status == 'work_started'
            assert ticket.on_hold_reason == 'pending_materials'

        resume = client.post(
            f'/tickets/api/tickets/{code}/resume',
            json={},
            headers=ticketing_auth_headers,
        )
        assert resume.status_code == 200, resume.get_json()
        assert resume.get_json()['status'] == 'work_started'

        with app.app_context():
            db.session.expire_all()
            ticket = Ticket.query.filter_by(ticket_id=code).first()
            assert ticket.status == 'work_started'
            assert ticket.previous_status is None
            assert ticket.on_hold_reason is None

    def test_cancel_persists_reason(self, client, app, ticketing_user, ticketing_auth_headers):
        from app.models import db, Ticket

        code = _make_ticket(app, ticketing_user.id, status='assigned', ticket_id='TKT-CANC01')

        cancel = client.post(
            f'/tickets/api/tickets/{code}/cancel',
            json={'reason': 'duplicate', 'notes': 'Already logged'},
            headers=ticketing_auth_headers,
        )
        assert cancel.status_code == 200, cancel.get_json()

        with app.app_context():
            db.session.expire_all()
            ticket = Ticket.query.filter_by(ticket_id=code).first()
            assert ticket.status == 'cancelled'
            assert ticket.cancelled_reason == 'duplicate'
            assert ticket.cancelled_at

    def test_advance_persists_milestone_timestamps(
        self, client, app, ticketing_user, ticketing_auth_headers
    ):
        from app.models import db, Ticket

        code = _make_ticket(app, ticketing_user.id, status='assigned', ticket_id='TKT-ADV01')
        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=code).first()
            ticket.technician_id = ticketing_user.id
            db.session.commit()

        advance = client.post(
            f'/tickets/api/tickets/{code}/advance',
            json={},
            headers=ticketing_auth_headers,
        )
        assert advance.status_code == 200, advance.get_json()
        assert advance.get_json()['status'] == 'site_attended'

        with app.app_context():
            db.session.expire_all()
            ticket = Ticket.query.filter_by(ticket_id=code).first()
            assert ticket.status == 'site_attended'
            assert ticket.site_attended_at
