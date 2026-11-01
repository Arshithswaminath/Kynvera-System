"""
Tests for Tickets -> Email drafts (/tickets/drafts).

One list, bucketed into pending / converted / discarded / failed, with
date-range + status + search filters. The page opens on the pending queue.
Converted, discarded, and failed mail stays reachable from the same table.
"""
from datetime import datetime, timedelta

import pytest

from app.models import db, Notification, Ticket, TicketEmailIntake, TicketNote


def _make_intake(from_email, subject, status='processed', ticket=None, received_at=None):
    row = TicketEmailIntake(
        from_email=from_email,
        from_name=None,
        to_email='contact@kynvera.net',
        subject=subject,
        raw_body='body',
        message_id=f'{subject}-{from_email}',
        status=status,
        ticket_id=ticket.id if ticket else None,
        received_at=received_at or datetime.utcnow(),
    )
    db.session.add(row)
    return row


def _make_ticket(ticket_id, status, reporter_id, title='t'):
    t = Ticket(
        ticket_id=ticket_id, reporter_id=reporter_id, title=title, project='Unassigned',
        service_group='Unclassified', category='Unclassified', fault_type='Unclassified',
        priority='medium', work_description='d', status=status, source='email',
    )
    db.session.add(t)
    db.session.flush()
    return t


class TestEmailIntakeHistoryBucketing:
    @pytest.fixture
    def seeded(self, app, admin_user):
        with app.app_context():
            admin_id = admin_user.id
            pending_t = _make_ticket('TKT-HIST-PEND', 'draft', admin_id, title='Pending one')
            converted_t = _make_ticket('TKT-HIST-CONV', 'pending_supervisor', admin_id, title='Converted one')
            discarded_t = _make_ticket('TKT-HIST-DISC', 'cancelled', admin_id, title='Discarded one')

            _make_intake('pending@example.com', 'Pending one', ticket=pending_t)
            _make_intake('converted@example.com', 'Converted one', ticket=converted_t)
            _make_intake('discarded@example.com', 'Discarded one', ticket=discarded_t)
            _make_intake('failed@example.com', 'Could not parse', status='error', ticket=None)
            db.session.commit()
        yield
        with app.app_context():
            TicketEmailIntake.query.filter(
                TicketEmailIntake.from_email.in_([
                    'pending@example.com', 'converted@example.com',
                    'discarded@example.com', 'failed@example.com',
                ])
            ).delete(synchronize_session=False)
            Ticket.query.filter(Ticket.ticket_id.in_(
                ['TKT-HIST-PEND', 'TKT-HIST-CONV', 'TKT-HIST-DISC']
            )).delete(synchronize_session=False)
            db.session.commit()

    def test_counts_bucket_by_ticket_status_not_intake_status(self, client, admin_auth_headers, seeded):
        resp = client.get('/tickets/drafts', headers=admin_auth_headers)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Pending one' in html
        assert 'Review &amp; Convert' in html
        assert 'class="draft-outcome ' not in html
        assert 'Converted one' not in html
        assert 'Email intake history' not in html
        assert 'Pending review' in html
        assert 'Discarded' in html
        assert 'Failed to parse' in html

        everything = client.get('/tickets/drafts?status=all', headers=admin_auth_headers)
        all_html = everything.get_data(as_text=True)
        assert 'Pending one' in all_html
        assert 'Converted one' in all_html
        assert 'Discarded one' in all_html
        assert 'Could not parse' in all_html
        assert 'class="draft-outcome draft-outcome--pending"' in all_html
        assert 'class="draft-outcome draft-outcome--converted"' in all_html
        assert 'class="draft-outcome draft-outcome--discarded"' in all_html
        assert 'class="draft-outcome draft-outcome--failed"' in all_html

    def test_status_filter_narrows_to_one_bucket(self, client, admin_auth_headers, seeded):
        resp = client.get('/tickets/drafts?status=converted', headers=admin_auth_headers)
        html = resp.get_data(as_text=True)
        assert 'Converted one' in html
        assert 'Pending one' not in html
        assert 'Discarded one' not in html
        assert 'Could not parse' not in html

    def test_search_filters_by_sender_and_subject(self, client, admin_auth_headers, seeded):
        resp = client.get(
            '/tickets/drafts?status=all&q=discarded%40example.com',
            headers=admin_auth_headers,
        )
        html = resp.get_data(as_text=True)
        assert 'Discarded one' in html
        assert 'Converted one' not in html
        assert 'Pending one' not in html

    def test_date_range_excludes_out_of_range_rows(self, client, admin_auth_headers, app, admin_user):
        with app.app_context():
            old_t = _make_ticket(
                'TKT-HIST-OLD', 'pending_supervisor', admin_user.id, title='Very old email',
            )
            _make_intake(
                'old@example.com', 'Very old email', ticket=old_t,
                received_at=datetime.utcnow() - timedelta(days=90),
            )
            db.session.commit()
        try:
            today = datetime.utcnow().date().isoformat()
            resp = client.get(
                f'/tickets/drafts?status=all&date_from={today}&date_to={today}',
                headers=admin_auth_headers,
            )
            html = resp.get_data(as_text=True)
            assert 'Very old email' not in html
        finally:
            with app.app_context():
                TicketEmailIntake.query.filter_by(from_email='old@example.com').delete()
                Ticket.query.filter_by(ticket_id='TKT-HIST-OLD').delete()
                db.session.commit()

    def test_review_and_convert_becomes_a_work_order(self, client, admin_auth_headers, app, admin_user):
        with app.app_context():
            ticket = _make_ticket(
                'TKT-CONVERT-1', 'draft', admin_user.id, title='AC issue at Injaaz HQ',
            )
            ticket.work_description = 'Hi, there is an issue with the AC at Injaaz HQ.'
            ticket.source_sender_name = 'Arshith'
            ticket.source_sender_email = ''
            _make_intake('convert-test@example.com', 'AC issue at Injaaz HQ', ticket=ticket)
            db.session.commit()
        try:
            review = client.get('/tickets/drafts/TKT-CONVERT-1/review', headers=admin_auth_headers)
            assert review.status_code == 200
            review_html = review.get_data(as_text=True)
            assert 'Convert to work order' in review_html
            assert 'AC issue at Injaaz HQ' in review_html
            assert 'Hi, there is an issue with the AC at Injaaz HQ.' in review_html

            blocked = client.post(
                '/tickets/api/tickets/TKT-CONVERT-1/convert-draft',
                headers=admin_auth_headers,
                json={
                    'title': 'AC issue at Injaaz HQ',
                    'priority': 'medium',
                    'work_description': 'Hi, there is an issue with the AC at Injaaz HQ.',
                },
            )
            assert blocked.status_code == 400
            with app.app_context():
                assert Ticket.query.filter_by(ticket_id='TKT-CONVERT-1').one().status == 'draft'

            converted = client.post(
                '/tickets/api/tickets/TKT-CONVERT-1/convert-draft',
                headers=admin_auth_headers,
                json={
                    'title': 'AC issue at Injaaz HQ',
                    'project': 'Injaaz HQ Office',
                    'service_group': 'HVAC systems',
                    'category': 'Air conditioning',
                    'fault_type': 'Not cooling',
                    'priority': 'medium',
                    'work_description': 'Hi, there is an issue with the AC at Injaaz HQ.',
                    'property_name': 'Injaaz HQ',
                },
            )
            assert converted.status_code == 200
            body = converted.get_json()
            assert body['success'] is True
            assert body['ticket_id'] == 'TKT-CONVERT-1'

            with app.app_context():
                saved = Ticket.query.filter_by(ticket_id='TKT-CONVERT-1').one()
                assert saved.status == 'pending_supervisor'
                assert saved.project == 'Injaaz HQ Office'
                assert saved.service_group == 'HVAC systems'
                assert saved.category == 'Air conditioning'
                assert saved.fault_type == 'Not cooling'
                assert saved.property_name == 'Injaaz HQ'

            gone = client.get('/tickets/drafts/TKT-CONVERT-1/review', headers=admin_auth_headers)
            assert gone.status_code == 302
            assert '/tickets/TKT-CONVERT-1' in (gone.headers.get('Location') or '')

            pending = client.get('/tickets/drafts', headers=admin_auth_headers)
            assert 'TKT-CONVERT-1' not in pending.get_data(as_text=True)
            history = client.get('/tickets/drafts?status=converted', headers=admin_auth_headers)
            assert 'TKT-CONVERT-1' in history.get_data(as_text=True)
            assert 'Open ticket' in history.get_data(as_text=True)
        finally:
            with app.app_context():
                row = Ticket.query.filter_by(ticket_id='TKT-CONVERT-1').first()
                if row is not None:
                    TicketNote.query.filter_by(ticket_id=row.id).delete()
                Notification.query.filter_by(submission_id='TKT-CONVERT-1').delete()
                TicketEmailIntake.query.filter_by(from_email='convert-test@example.com').delete()
                Ticket.query.filter_by(ticket_id='TKT-CONVERT-1').delete()
                db.session.commit()

    def test_requires_draft_review_access(self, client, auth_headers):
        resp = client.get('/tickets/drafts', headers=auth_headers)
        assert resp.status_code in (302, 403)
