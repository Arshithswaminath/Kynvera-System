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


def test_account_created_email_includes_username_and_wordmark(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    captured = {}

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['subject'] = subject
        captured['body'] = body
        captured['html'] = html_body or ''
        captured['attachments'] = attachments or []
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)
    monkeypatch.setitem(app.config, 'APP_BASE_URL', 'https://app.kynvera.example')

    with app.app_context():
        ok = es.send_account_created_email(
            'new@example.com', 'arshith', full_name='Arshith', temp_password='TempPass99'
        )
        assert ok is True
        assert 'arshith' in captured['body']
        assert 'TempPass99' in captured['body']
        assert 'Kynvera</span>' in captured['html']
        assert '#ff8e68' in captured['html']
        assert 'kynvera-wordmark.png' not in captured['html']
        assert 'cid:kynvera-wordmark' not in captured['html']
        assert '<img ' not in captured['html']
        assert 'height:8px' not in captured['html']
        assert 'Username' in captured['html']
        assert captured['attachments'] == []
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row.body_preview == 'Account created notification'
        assert 'TempPass99' not in (row.body_preview or '')


def test_wordmark_src_skips_localhost(app):
    from common import email_service as es

    assert es._is_public_asset_base('https://app.kynvera.example') is True
    assert es._is_public_asset_base('http://localhost:5002') is False
    assert es._is_public_asset_base('http://127.0.0.1:5002') is False

    with app.app_context():
        app.config['APP_BASE_URL'] = 'http://localhost:5002'
        app.config['EMAIL_WORDMARK_URL'] = ''
        es._cloudinary_wordmark_url_cache = ''
        html = es._branded_auth_html(title='Login details', greeting='Hello', paragraphs=['Hi'])
        assert 'localhost' not in html
        assert 'cid:kynvera-wordmark' not in html
        assert 'kynvera-wordmark.png' not in html
        assert '<img ' not in html
        assert 'Kynvera</span>' in html
        assert '#ff8e68' in html


def test_brevo_replaces_cid_image_with_html_wordmark(app, monkeypatch):
    from common import email_service as es

    captured = {}

    class _Resp:
        status_code = 201

        def json(self):
            return {'messageId': 'test'}

    def _post(url, json=None, headers=None, timeout=None):
        captured['html'] = (json or {}).get('htmlContent', '')
        captured['attachment'] = (json or {}).get('attachment')
        return _Resp()

    monkeypatch.setattr(es.requests, 'post', _post)
    html = (
        '<img src="cid:kynvera-wordmark" alt="Kynvera" width="176" '
        'style="display:block;">'
    )
    with app.app_context():
        app.config['MAIL_DEFAULT_SENDER'] = 'noreply@injaaz.ae'
        ok = es._send_email_brevo_http(
            app, 'user@example.com', 'Subject', 'Body', html, None,
            [{'filename': 'kynvera-wordmark.png', 'content': b'x', 'mime_type': 'image/png',
              'cid': 'kynvera-wordmark', 'inline': True}],
            'test-key',
        )
    assert ok is True
    assert 'cid:' not in captured['html']
    assert 'data:image' not in captured['html']
    assert 'Kynvera</span>' in captured['html']
    assert not captured['attachment']


def test_brevo_remaps_unverified_contact_sender(app, monkeypatch):
    from common import email_service as es

    captured = {}

    class _Resp:
        status_code = 201

        def json(self):
            return {'messageId': 'test'}

    def _post(url, json=None, headers=None, timeout=None):
        captured['sender'] = (json or {}).get('sender')
        return _Resp()

    monkeypatch.setattr(es.requests, 'post', _post)
    with app.app_context():
        for bad_sender in ('contact@kynvera.net', 'support@kynvera.net'):
            app.config['MAIL_DEFAULT_SENDER'] = bad_sender
            ok = es._send_email_brevo_http(
                app, 'ops@example.com', 'Subject', 'Body', '<p>Hi</p>', None, None, 'test-key',
            )
            assert ok is True
            assert captured['sender'] == {'name': 'Kynvera', 'email': 'support@kynvera.store'}


def test_password_updated_email_logs_preview(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

    with app.app_context():
        ok = es.send_password_updated_email('user@example.com', 'alice', by_admin=True)
        assert ok is True
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row is not None
        assert row.body_preview == 'Password updated notification'


def test_account_status_email_logs_preview(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

    with app.app_context():
        ok = es.send_account_status_email(
            'user@example.com', 'alice', is_active=False, full_name='Alice'
        )
        assert ok is True
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row.body_preview == 'Account deactivated notification'

        ok = es.send_account_status_email(
            'user@example.com', 'alice', is_active=True, full_name='Alice'
        )
        assert ok is True
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row.body_preview == 'Account activated notification'


def test_mfa_emails_log_preview_and_inline_wordmark(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    captured = {}

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['subject'] = subject
        captured['body'] = body
        captured['html'] = html_body or ''
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)

    with app.app_context():
        ok = es.send_mfa_enabled_email('user@example.com', 'alice', full_name='Alice')
        assert ok is True
        assert captured['subject'] == 'Your Kynvera authenticator is on'
        assert 'is now required' in captured['body']
        assert 'Kynvera</span>' in captured['html']
        assert '<img ' not in captured['html']
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row.body_preview == 'Authenticator enabled notification'

        ok = es.send_mfa_disabled_email('user@example.com', 'alice', full_name='Alice')
        assert ok is True
        assert captured['subject'] == 'Your Kynvera authenticator was turned off'
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row.body_preview == 'Authenticator disabled notification'

        ok = es.send_mfa_disabled_email(
            'user@example.com', 'alice', by_admin=True, full_name='Alice'
        )
        assert ok is True
        assert captured['subject'] == 'Your Kynvera authenticator was reset'
        assert 'administrator reset' in captured['body']
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row.body_preview == 'Authenticator disabled notification'


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


def test_login_details_email_omits_password_from_log(app, monkeypatch):
    from app.models import EmailLog
    from common import email_service as es

    captured = {}

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['body'] = body
        captured['html'] = html_body or ''
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)

    with app.app_context():
        ok = es.send_login_details_email(
            'user@example.com', 'alice', 'SecretStored99', full_name='Alice'
        )
        assert ok is True
        assert 'alice' in captured['body']
        assert 'SecretStored99' in captured['body']
        assert 'Username' in captured['html']
        row = EmailLog.query.filter_by(source='auth').order_by(EmailLog.id.desc()).first()
        assert row is not None
        assert row.body_preview == 'Login details notification'
        assert 'SecretStored99' not in (row.body_preview or '')


def test_email_login_details_endpoint_sends(client, admin_auth_headers, standard_user, app, monkeypatch):
    from app.models import User, db
    from common import email_service as es

    captured = {}

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['to'] = recipient
        captured['body'] = body
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)

    with app.app_context():
        user = User.query.filter_by(username='testuser').one()
        user.admin_visible_password = 'StoredPass99'
        db.session.commit()
        uid = user.id

    response = client.post(f'/api/admin/users/{uid}/email-login-details', headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('success') is True
    assert 'test@example.com' in (data.get('message') or '')
    assert 'StoredPass99' in captured['body']
    assert 'testuser' in captured['body']


def test_email_login_details_requires_stored_password(client, admin_auth_headers, standard_user, app):
    from app.models import User, db

    with app.app_context():
        user = User.query.filter_by(username='testuser').one()
        user.admin_visible_password = None
        db.session.commit()
        uid = user.id

    response = client.post(f'/api/admin/users/{uid}/email-login-details', headers=admin_auth_headers)
    assert response.status_code == 400
    data = response.get_json()
    assert data.get('success') is False
    assert 'password' in (data.get('error') or '').lower()


def test_email_login_details_requires_admin(client, auth_headers, standard_user):
    uid = standard_user.id
    response = client.post(f'/api/admin/users/{uid}/email-login-details', headers=auth_headers)
    assert response.status_code == 403


def test_toggle_active_emails_user(client, admin_auth_headers, standard_user, app, monkeypatch):
    from app.models import User
    from common import email_service as es

    captured = []

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured.append({'subject': subject, 'body': body})
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)

    with app.app_context():
        uid = User.query.filter_by(username='testuser').one().id

    deactivated = client.post(f'/api/admin/users/{uid}/toggle-active', headers=admin_auth_headers)
    assert deactivated.status_code == 200
    assert deactivated.get_json().get('success') is True
    assert 'deactivat' in captured[-1]['subject'].lower()
    assert 'test@example.com' in (deactivated.get_json().get('message') or '')

    activated = client.post(f'/api/admin/users/{uid}/toggle-active', headers=admin_auth_headers)
    assert activated.status_code == 200
    assert 'activat' in captured[-1]['subject'].lower()
    assert 'deactivat' not in captured[-1]['subject'].lower()


def test_user_change_password_sends_notification(client, auth_headers, app, monkeypatch):
    from common import email_service as es

    captured = {}

    def _capture(recipient, subject, body, html_body=None, cc=None, attachments=None):
        captured['subject'] = subject
        captured['body'] = body
        return True

    monkeypatch.setattr(es, '_deliver_email', _capture)

    response = client.post(
        '/api/auth/change-password',
        headers=auth_headers,
        json={'current_password': 'TestPass123', 'new_password': 'NewSecurePass456'},
    )
    assert response.status_code == 200
    assert 'password' in captured.get('subject', '').lower()
    assert 'administrator updated' not in captured.get('body', '').lower()
