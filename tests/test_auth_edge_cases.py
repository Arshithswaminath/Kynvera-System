"""
Auth/session edge cases not covered by tests/test_auth.py:

1. A revoked Session row rejects an otherwise-valid access token.
2. Invalid/garbage-token handling differs between JSON API routes and
   full HTML-page routes (the custom jwt error-callback branching in
   Injaaz.py around _is_html_page_request / _silent_refresh_or_login).
3. Several admin/dochub/workflow "page shell" routes render with no auth
   decorator at all (by design - the client fetches protected /api/... data
   afterwards), so an unauthenticated GET must still return a bare HTML
   shell, never JSON with user data.
4. /api/docs/inline/<filename> is deliberately unauthenticated but only
   serves filenames matching the generated UUID-shaped pattern.
5. The ticketing inbound-email webhook validates its path secret and
   404s (not 401/403) on a mismatch, creating no draft rows.

Style follows tests/test_ticket_geocode.py: class-per-concern, using the
shared fixtures from tests/conftest.py plus unittest.mock where useful.
"""
import io

import pytest
from flask_jwt_extended import decode_token


class TestRevokedSessionRejected:
    """Background note #1: revoking the Session row for a JTI must reject
    that access token on the very next request, even though the JWT
    signature itself is still valid."""

    def test_revoked_session_returns_401(self, client, standard_user, app):
        from app.models import db, Session

        login_resp = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'TestPass123',
        })
        assert login_resp.status_code == 200
        access_token = login_resp.get_json()['access_token']

        with app.app_context():
            jti = decode_token(access_token)['jti']
            session = Session.query.filter_by(token_jti=jti).first()
            assert session is not None
            session.is_revoked = True
            db.session.commit()

        me_resp = client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {access_token}'
        })
        assert me_resp.status_code == 401
        body = me_resp.get_json()
        assert body is not None
        error_text = str(body.get('error') or body.get('msg') or '').lower()
        assert 'revoked' in error_text

    def test_unrevoked_session_still_works(self, client, standard_user):
        """Sanity check: a freshly-issued token (nobody revoked it) still
        authenticates, isolating the 401 above to the revocation itself."""
        login_resp = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'TestPass123',
        })
        access_token = login_resp.get_json()['access_token']

        me_resp = client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {access_token}'
        })
        assert me_resp.status_code == 200


class TestApiVsHtmlPageErrorBranching:
    """Background note #2: bare @jwt_required() routes route failures
    through Injaaz.py's custom JWT error callbacks, which branch on
    _is_html_page_request(). /api/... paths get a flat JSON 401; full-page
    GETs get redirected (302) toward /login instead."""

    def test_invalid_token_on_api_route_returns_json_401(self, client):
        resp = client.get('/api/auth/me', headers={
            'Authorization': 'Bearer not-a-real-jwt-token'
        })
        assert resp.status_code == 401
        assert resp.content_type.startswith('application/json')
        body = resp.get_json()
        assert body is not None
        assert body.get('success') is False

    def test_missing_token_on_html_page_redirects_to_login(self, client):
        resp = client.get('/dashboard')
        assert resp.status_code == 302
        assert '/login' in resp.headers.get('Location', '')

    def test_invalid_token_on_html_page_redirects_not_json(self, client):
        """Same garbage-token trigger as the API case above, but on a page
        route - should redirect (via _silent_refresh_or_login/invalid_token
        callback) instead of returning a JSON 401 body."""
        client.set_cookie('localhost', 'access_token_cookie', 'not-a-real-jwt-token')
        resp = client.get('/dashboard')
        assert resp.status_code == 302
        assert '/login' in resp.headers.get('Location', '')


class TestPageShellVsProtectedApiPairing:
    """Background note #3: /admin/dashboard, /dochub, and
    /workflow/pending-reviews render an HTML template with no auth
    decorator (client-side gate design) - confirm that's still true and
    that the shells don't leak per-user JSON data, while the /api/...
    endpoints they depend on remain properly protected."""

    @pytest.mark.parametrize('page_path', [
        '/admin/dashboard',
        '/dochub',
        '/workflow/pending-reviews',
    ])
    def test_shell_renders_unauthenticated(self, client, page_path):
        resp = client.get(page_path)
        assert resp.status_code == 200
        assert resp.content_type.startswith('text/html')
        # An HTML shell should not be a JSON payload of user/session data.
        assert resp.get_json(silent=True) is None

    @pytest.mark.parametrize('api_path', [
        '/api/admin/users',
        '/api/docs',
        '/api/workflow/submissions/pending',
    ])
    def test_backing_api_requires_auth(self, client, api_path):
        resp = client.get(api_path)
        assert resp.status_code in (401, 422)


class TestInlineDocServing:
    """Background note #4: /api/docs/inline/<filename> intentionally skips
    auth (comment: "Serve inline assets without Authorization") but only
    for filenames matching the generated 32-hex-char UUID pattern; anything
    else - including path-traversal-shaped input - must 404 before ever
    touching the filesystem."""

    def test_uploaded_inline_image_is_publicly_fetchable(self, client, admin_auth_headers, app):
        upload_resp = client.post(
            '/api/docs/inline-image',
            headers=admin_auth_headers,
            data={'file': (io.BytesIO(b'fake-png-bytes'), 'note.png')},
            content_type='multipart/form-data',
        )
        assert upload_resp.status_code == 201
        url = upload_resp.get_json()['url']
        assert url.startswith('/api/docs/inline/')

        try:
            # No Authorization header at all - this endpoint is deliberately public.
            fetch_resp = client.get(url)
            assert fetch_resp.status_code == 200
            assert fetch_resp.data == b'fake-png-bytes'
        finally:
            # This endpoint writes to the real GENERATED_DIR/dochub/inline on
            # disk (tests don't override it to a tmp dir) - clean up after
            # ourselves so repeated runs don't litter the repo.
            import os
            with app.app_context():
                generated_root = app.config.get('GENERATED_DIR')
            if generated_root:
                fname = url.rsplit('/', 1)[-1]
                stray_path = os.path.join(generated_root, 'dochub', 'inline', fname)
                if os.path.isfile(stray_path):
                    os.remove(stray_path)

    def test_non_uuid_filename_rejected(self, client):
        resp = client.get('/api/docs/inline/not-a-real-file.png')
        assert resp.status_code == 404

    def test_path_traversal_shaped_filename_rejected(self, client):
        resp = client.get('/api/docs/inline/..%2F..%2Fetc%2Fpasswd')
        assert resp.status_code in (404, 400)

    def test_valid_shape_but_nonexistent_file_rejected(self, client):
        # 32 hex chars + an allowed extension - matches _INLINE_FILE_RE but
        # was never actually generated by an upload.
        fake_uuid = 'a' * 32
        resp = client.get(f'/api/docs/inline/{fake_uuid}.png')
        assert resp.status_code == 404


class TestTicketInboundEmailWebhookSecret:
    """Background note #5: the Mailjet Parse webhook target validates its
    path secret against TICKET_INBOUND_WEBHOOK_SECRET and must abort(404)
    - not 401/403 - on any mismatch, without creating draft rows."""

    MAILJET_PAYLOAD = {
        'From': 'Jane Doe <jane.reporter@example.com>',
        'Sender': 'jane.reporter@example.com',
        'Recipient': 'intake@injaaz.example',
        'Subject': '[Ajman Mall] HVAC - high - AC not cooling',
        'Text-part': (
            'Property: Retail Podium\n'
            'Zone: Ground Level\n'
            'Unit: Staff Canteen\n'
            'AC not cooling in the food court.'
        ),
        'Headers': {'Message-ID': 'test-auth-edge-msg-001@mailjet'},
    }

    @pytest.fixture
    def webhook_secret(self, app):
        original = app.config.get('TICKET_INBOUND_WEBHOOK_SECRET')
        app.config['TICKET_INBOUND_WEBHOOK_SECRET'] = 'expected-secret-for-test'
        yield 'expected-secret-for-test'
        app.config['TICKET_INBOUND_WEBHOOK_SECRET'] = original

    def test_wrong_secret_returns_404_and_creates_nothing(self, client, app, webhook_secret):
        from app.models import Ticket, TicketEmailIntake

        with app.app_context():
            intake_count_before = TicketEmailIntake.query.count()
            ticket_count_before = Ticket.query.count()

        resp = client.post(
            '/tickets/api/inbound-email/wrong-secret',
            json=self.MAILJET_PAYLOAD,
        )
        assert resp.status_code == 404

        with app.app_context():
            assert TicketEmailIntake.query.count() == intake_count_before
            assert Ticket.query.count() == ticket_count_before

    def test_correct_secret_accepts_and_creates_draft(self, client, app, webhook_secret):
        from app.models import Ticket, TicketEmailIntake

        resp = client.post(
            f'/tickets/api/inbound-email/{webhook_secret}',
            json=self.MAILJET_PAYLOAD,
        )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        with app.app_context():
            intake = TicketEmailIntake.query.filter_by(
                message_id='test-auth-edge-msg-001@mailjet'
            ).first()
            assert intake is not None
            assert intake.status == 'processed'
            assert intake.ticket_id is not None

            ticket = db_get_ticket(intake.ticket_id)
            assert ticket is not None
            assert ticket.source == 'email'
            assert ticket.status == 'draft'
            assert ticket.source_sender_email == 'jane.reporter@example.com'


def db_get_ticket(ticket_id):
    from app.models import db, Ticket
    return db.session.get(Ticket, ticket_id)
