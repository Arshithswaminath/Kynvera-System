"""Admin sent-email log: persist on send and list via admin API."""


def test_send_email_writes_log(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

    with app.app_context():
        ok = es.send_email(
            ['ops@example.com', 'gm@example.com'],
            'Inspection submitted',
            'Form CIV-1 was submitted.',
            cc='lead@example.com',
            source='inspection',
            related_id='sub_abc123',
        )
        assert ok is True
        row = EmailLog.query.order_by(EmailLog.id.desc()).first()
        assert row is not None
        assert row.status == 'sent'
        assert row.source == 'inspection'
        assert row.subject == 'Inspection submitted'
        assert 'ops@example.com' in row.to_emails
        assert 'gm@example.com' in row.to_emails
        assert row.cc_emails == 'lead@example.com'
        assert row.related_id == 'sub_abc123'
        assert row.error_message is None


def test_failed_send_writes_failed_log(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: False)

    with app.app_context():
        ok = es.send_email('bd@example.com', 'GM update', 'Please review.', source='bd_email')
        assert ok is False
        row = EmailLog.query.filter_by(source='bd_email').order_by(EmailLog.id.desc()).first()
        assert row is not None
        assert row.status == 'failed'
        assert row.error_message == 'Send failed'


def test_auth_preview_omits_password(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

    with app.app_context():
        es.send_password_reset_email('user@example.com', 'alice', 'SecretTemp99')
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row is not None
        assert row.body_preview == 'Password reset notification'
        assert 'SecretTemp99' not in (row.body_preview or '')


def test_email_logs_requires_admin(client, auth_headers):
    response = client.get('/api/admin/email-logs', headers=auth_headers)
    assert response.status_code == 403


def test_email_logs_admin_list_and_filter(client, admin_auth_headers, app, admin_user):
    from app.models import EmailLog, db

    with app.app_context():
        db.session.add(EmailLog(
            status='sent',
            source='inspection',
            subject='Inspection submitted',
            to_emails='ops@example.com',
            related_id='sub_one',
        ))
        db.session.add(EmailLog(
            status='sent',
            source='bd_email',
            subject='Approval Update',
            to_emails='gm@example.com',
            sent_by_user_id=admin_user.id,
            related_id='sub_two',
        ))
        db.session.add(EmailLog(
            status='failed',
            source='hr',
            subject='Leave signed',
            to_emails='hr@example.com',
            error_message='Send failed',
        ))
        db.session.commit()

    response = client.get('/api/admin/email-logs', headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('success') is True
    assert data.get('total') >= 3
    subjects = {item['subject'] for item in data.get('items') or []}
    assert 'Inspection submitted' in subjects
    assert 'Approval Update' in subjects

    filtered = client.get('/api/admin/email-logs?source=bd_email', headers=admin_auth_headers)
    assert filtered.status_code == 200
    fdata = filtered.get_json()
    assert fdata.get('success') is True
    assert fdata.get('total') >= 1
    assert all(item['source'] == 'bd_email' for item in fdata.get('items') or [])

    search = client.get('/api/admin/email-logs?q=Leave', headers=admin_auth_headers)
    assert search.status_code == 200
    sdata = search.get_json()
    assert any(item['subject'] == 'Leave signed' for item in sdata.get('items') or [])
    assert any(item['status'] == 'failed' for item in sdata.get('items') or [])
