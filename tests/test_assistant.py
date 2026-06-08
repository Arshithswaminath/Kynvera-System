"""
Tests for Injaaz Live Assistant (no-LLM v1) and Knowledge Base
"""
import os
import tempfile

import pytest

from module_assistant.intents import resolve_intent
from module_assistant.tools import get_my_leave_history, get_pending_summary, search_documents
from module_assistant import knowledge as kb_knowledge
from module_assistant.extract import extract_text


class TestIntentRouting:
    def test_pending_count_intent(self):
        r = resolve_intent('How many pending forms are there?')
        assert r.intent == 'pending_count'
        assert r.confidence > 0

    def test_my_last_leave_intent(self):
        r = resolve_intent('When did I take my last leave?')
        assert r.intent == 'my_last_leave'

    def test_find_document_intent(self):
        r = resolve_intent('Can I get the safety policy document?')
        assert r.intent == 'find_document'
        assert 'document_query' in r.entities

    def test_change_password_intent(self):
        r = resolve_intent('How do I change my password?')
        assert r.intent == 'change_password'

    def test_greeting_intent(self):
        r = resolve_intent('hello')
        assert r.intent == 'greeting'

    def test_fallback_intent(self):
        r = resolve_intent('xyzzy plugh completely random phrase')
        assert r.intent == 'fallback'

    def test_ticketing_help_intent(self):
        r = resolve_intent('How do I raise a work order ticket?')
        assert r.intent == 'ticketing_help'

    def test_inspection_help_intent(self):
        r = resolve_intent('How do I fill an HVAC inspection?')
        assert r.intent == 'inspection_help'

    def test_procurement_help_intent(self):
        r = resolve_intent('Where do I manage the material list and pricing?')
        assert r.intent == 'procurement_help'

    def test_hr_form_help_intent(self):
        r = resolve_intent('How do I submit a termination form?')
        assert r.intent == 'hr_form_help'

    def test_contact_admin_intent(self):
        r = resolve_intent('I want to talk to a person about a problem')
        assert r.intent == 'contact_admin'

    def test_my_drafts_intent(self):
        r = resolve_intent('Show me my drafts')
        assert r.intent == 'my_drafts'


class TestClaudeLlm:
    def test_claude_provider_generate_reply(self, app, monkeypatch):
        monkeypatch.setattr(
            'module_assistant.llm._generate_claude',
            lambda user_content: 'Injaaz is in Ajman, UAE.',
        )
        monkeypatch.setattr('module_assistant.llm._provider', lambda: 'claude')

        with app.app_context():
            from module_assistant.llm import generate_reply
            reply = generate_reply('Where is Injaaz?', [{'title': 'Injaaz', 'source': 'Web', 'text': 'Ajman'}])
            assert 'Ajman' in reply


class TestLlmNaturalChat:
    def test_llm_natural_reply_when_enabled(self, client, auth_headers, app, monkeypatch):
        monkeypatch.setattr('module_assistant.routes.is_llm_enabled', lambda: True)
        monkeypatch.setattr(
            'module_assistant.llm.generate_reply',
            lambda message, chunks, user_name='': 'Injaaz is based in Ajman, United Arab Emirates.',
        )

        with app.app_context():
            res = client.post(
                '/api/assistant/chat',
                json={'message': 'whereabouts is the company headquartered?'},
                headers=auth_headers,
            )
            assert res.status_code == 200
            payload = res.get_json().get('data') or res.get_json()
            assert 'Ajman' in payload.get('message', '')
            assert payload.get('intent') == 'chat'

    def test_live_data_stays_structured_when_llm_enabled(
        self, client, supervisor_auth_headers, sample_submission, app, monkeypatch
    ):
        monkeypatch.setattr('module_assistant.routes.is_llm_enabled', lambda: True)
        monkeypatch.setattr(
            'module_assistant.llm.generate_reply',
            lambda *a, **k: 'This should not be used for pending count.',
        )

        with app.app_context():
            res = client.post(
                '/api/assistant/chat',
                json={'message': 'How many pending forms?'},
                headers=supervisor_auth_headers,
            )
            payload = res.get_json().get('data') or res.get_json()
            assert payload.get('intent') == 'pending_count'
            assert 'Ajman' not in payload.get('message', '')


class TestAssistantChatEndpoint:
    def test_chat_no_auth(self, client, app):
        with app.app_context():
            response = client.post('/api/assistant/chat', json={'message': 'hello'})
            assert response.status_code == 401

    def test_chat_empty_message(self, client, auth_headers, app):
        with app.app_context():
            response = client.post(
                '/api/assistant/chat',
                json={'message': '   '},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_chat_pending_as_supervisor(
        self, client, supervisor_auth_headers, sample_submission, app
    ):
        with app.app_context():
            response = client.post(
                '/api/assistant/chat',
                json={'message': 'How many pending forms?'},
                headers=supervisor_auth_headers,
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('success') is True
            payload = data.get('data') or data
            assert payload.get('intent') == 'pending_count'
            assert 'message' in payload
            assert isinstance(payload.get('cards'), list)

    def test_chat_technician_pending(
        self, client, auth_headers, app
    ):
        with app.app_context():
            response = client.post(
                '/api/assistant/chat',
                json={'message': 'pending forms'},
                headers=auth_headers,
            )
            assert response.status_code == 200
            payload = response.get_json().get('data') or response.get_json()
            assert payload.get('intent') == 'pending_count'
            assert 'reviewer role' in payload.get('message', '').lower() or 'submitted' in payload.get('message', '').lower()

    def test_chat_change_password(self, client, auth_headers, app):
        with app.app_context():
            response = client.post(
                '/api/assistant/chat',
                json={'message': 'change my password'},
                headers=auth_headers,
            )
            assert response.status_code == 200
            payload = response.get_json().get('data') or response.get_json()
            assert payload.get('intent') == 'change_password'
            actions = payload.get('actions') or []
            assert any(a.get('kind') == 'profile_security' for a in actions)


class TestLeaveHistoryTool:
    def test_get_my_leave_history(self, app, standard_user):
        from app.models import db, Submission
        from common.utils import random_id

        with app.app_context():
            sub = Submission(
                submission_id=random_id('sub'),
                module_type='hr_leave_application',
                site_name='Leave',
                form_data={
                    'leave_type': 'annual',
                    'first_day_of_leave': '2025-01-10',
                    'last_day_of_leave': '2025-01-15',
                    'total_days_requested': 5,
                },
                workflow_status='completed',
                status='submitted',
                user_id=standard_user.id,
            )
            db.session.add(sub)
            db.session.commit()

            result = get_my_leave_history(standard_user)
            assert result['has_leave'] is True
            assert result['count'] >= 1
            assert result['entries'][0]['leave_type'] == 'annual'
            assert '10 Jan 2025' in result['entries'][0]['start_date']

            db.session.delete(sub)
            db.session.commit()


class TestDocumentSearch:
    def test_search_documents_finds_match(self, app, standard_user):
        from app.models import db, DocHubDocument

        with app.app_context():
            doc = DocHubDocument(
                title='QHSE Safety Policy Manual',
                category='policies',
                status='published',
                content='<p>Safety requirements for all staff.</p>',
                doc_type='content',
            )
            db.session.add(doc)
            db.session.commit()

            result = search_documents(standard_user, 'safety policy')
            assert result['allowed'] is True
            assert len(result['documents']) >= 1
            assert 'Safety' in result['documents'][0]['title']

            db.session.delete(doc)
            db.session.commit()

    def test_search_documents_denied_when_access_revoked(self, app, standard_user):
        from app.models import db, DocHubAccess

        with app.app_context():
            row = DocHubAccess(user_id=standard_user.id, can_access=False)
            db.session.add(row)
            db.session.commit()

            result = search_documents(standard_user, 'policy')
            assert result['allowed'] is False
            assert result['documents'] == []

            db.session.delete(row)
            db.session.commit()


class TestTextExtraction:
    def test_extract_txt(self):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write('Hello knowledge base content')
            path = f.name
        try:
            assert 'knowledge base' in extract_text(path, 'txt')
        finally:
            os.remove(path)

    def test_extract_md(self):
        with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('# Heading\nSome markdown body')
            path = f.name
        try:
            assert 'markdown body' in extract_text(path, 'md')
        finally:
            os.remove(path)

    def test_extract_missing_file(self):
        assert extract_text('/no/such/file.pdf', 'pdf') == ''


class TestKnowledgeMerge:
    def test_db_entry_found_and_inactive_ignored(self, app):
        from app.models import db, KnowledgeBaseEntry

        with app.app_context():
            active = KnowledgeBaseEntry(
                title='Carpool Policy',
                content='Staff can register for the company carpool scheme via HR.',
                keywords='carpool, transport, commute',
                category='Policy',
                source_type='text',
                is_active=True,
            )
            hidden = KnowledgeBaseEntry(
                title='Secret Draft',
                content='zztopsecret draft about quokka',
                keywords='quokka',
                category='Policy',
                source_type='text',
                is_active=False,
            )
            db.session.add_all([active, hidden])
            db.session.commit()
            kb_knowledge.invalidate_cache()

            results = kb_knowledge.search_faqs('carpool transport')
            assert any('Carpool' in r['question'] for r in results)

            hidden_results = kb_knowledge.search_faqs('quokka')
            assert all('Secret Draft' not in r['question'] for r in hidden_results)

            db.session.delete(active)
            db.session.delete(hidden)
            db.session.commit()
            kb_knowledge.invalidate_cache()

    def test_cache_invalidation_picks_up_new_entry(self, app):
        from app.models import db, KnowledgeBaseEntry

        with app.app_context():
            kb_knowledge.invalidate_cache()
            assert not kb_knowledge.search_faqs('zorblax')

            entry = KnowledgeBaseEntry(
                title='Zorblax Procedure',
                content='The zorblax procedure is documented here.',
                keywords='zorblax',
                category='General',
                source_type='text',
                is_active=True,
            )
            db.session.add(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

            results = kb_knowledge.search_faqs('zorblax')
            assert any('Zorblax' in r['question'] for r in results)

            db.session.delete(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()


class TestKnowledgeBaseAdminAPI:
    def test_list_requires_admin(self, client, auth_headers, app):
        with app.app_context():
            res = client.get('/api/admin/knowledge-base', headers=auth_headers)
            assert res.status_code == 403

    def test_list_no_auth(self, client, app):
        with app.app_context():
            res = client.get('/api/admin/knowledge-base')
            assert res.status_code == 401

    def test_admin_create_list_update_delete(self, client, admin_auth_headers, app):
        with app.app_context():
            create = client.post(
                '/api/admin/knowledge-base',
                json={
                    'title': 'Parking Rules',
                    'content': 'Park only in assigned bays.',
                    'keywords': 'parking, bay',
                    'category': 'Policy',
                },
                headers=admin_auth_headers,
            )
            assert create.status_code == 201
            entry_id = (create.get_json().get('data') or create.get_json())['entry']['id']

            listing = client.get('/api/admin/knowledge-base', headers=admin_auth_headers)
            assert listing.status_code == 200
            payload = listing.get_json()
            assert payload.get('count', 0) >= 1

            update = client.put(
                f'/api/admin/knowledge-base/{entry_id}',
                json={'is_active': False},
                headers=admin_auth_headers,
            )
            assert update.status_code == 200

            delete = client.delete(
                f'/api/admin/knowledge-base/{entry_id}',
                headers=admin_auth_headers,
            )
            assert delete.status_code == 200

    def test_create_requires_content(self, client, admin_auth_headers, app):
        with app.app_context():
            res = client.post(
                '/api/admin/knowledge-base',
                json={'title': 'No body'},
                headers=admin_auth_headers,
            )
            assert res.status_code == 400


class TestRelevantPassageSearch:
    def test_locations_beats_generic_injaaz_faq(self, app):
        from app.models import db, KnowledgeBaseEntry
        from module_assistant.knowledge import search_faqs

        with app.app_context():
            entry = KnowledgeBaseEntry(
                title='Injaaz company profile',
                content=(
                    'Summary about the company.\n\n--- Full page content ---\n\n'
                    'Injaaz operates across the UAE. Our head office is in Dubai. '
                    'We also have teams in Abu Dhabi and Sharjah locations.'
                ),
                keywords='locations, office, dubai, address',
                category='General',
                source_type='link',
                source_url='https://example.com/about',
                is_active=True,
            )
            db.session.add(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

            results = search_faqs('Injaaz locations?')
            assert results
            assert 'Dubai' in results[0]['answer'] or 'location' in results[0]['answer'].lower()
            assert results[0].get('is_db') is True

            db.session.delete(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

    def test_brand_only_query_not_confident_for_locations(self, app):
        from module_assistant.knowledge import is_confident_match, search_faqs

        with app.app_context():
            kb_knowledge.invalidate_cache()
            results = search_faqs('Injaaz locations?')
            if results:
                # Without a location KB record, generic FAQ should not be confident.
                assert not is_confident_match('Injaaz locations?', results[0])

    def test_where_is_injaaz_escalates_without_location_kb(self, app):
        from module_assistant.responses import compose_fallback

        with app.app_context():
            kb_knowledge.invalidate_cache()
            payload = compose_fallback('Where is Injaaz?')
            assert payload['intent'] == 'contact_admin'
            assert 'couldn' in payload['message'].lower() or 'ticket' in payload['message'].lower()

    def test_ajaan_address_in_link_satisfies_location_intent(self):
        from module_assistant.knowledge import _has_location_content, extract_relevant_passage

        text = (
            'Sheik Khalifa Bin Zayed St, Ajman, United Arab Emirates info@injaaz.ae '
            'INJAAZ Facilities Management provides integrated FM solutions.'
        )
        assert _has_location_content(text)
        passage = extract_relevant_passage('Where is Injaaz?', text)
        assert 'Ajman' in passage

    def test_where_is_injaaz_answers_from_location_kb(self, app):
        from app.models import db, KnowledgeBaseEntry
        from module_assistant.responses import compose_fallback

        with app.app_context():
            entry = KnowledgeBaseEntry(
                title='Injaaz offices',
                content='Injaaz head office is in Dubai, UAE. We also operate in Abu Dhabi.',
                keywords='location, office, dubai, address, where',
                category='General',
                source_type='text',
                is_active=True,
            )
            db.session.add(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

            payload = compose_fallback('Where is Injaaz?')
            assert 'Dubai' in payload['message']

            db.session.delete(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

    def test_extract_relevant_passage(self):
        from module_assistant.knowledge import extract_relevant_passage

        text = (
            'General intro about the platform.\n\n--- Full page content ---\n\n'
            'Head office: Dubai, UAE. Regional teams cover Abu Dhabi and Sharjah.'
        )
        passage = extract_relevant_passage('where are the office locations', text)
        assert 'Dubai' in passage


class TestFallbackAlwaysUsesKnowledge:
    def test_fallback_answers_from_kb_record(self, app):
        from app.models import db, KnowledgeBaseEntry
        from module_assistant.responses import compose_fallback

        with app.app_context():
            entry = KnowledgeBaseEntry(
                title='Where is the head office',
                content='The Injaaz head office is located in Dubai, UAE.',
                keywords='office, location, address, dubai',
                category='General',
                source_type='text',
                is_active=True,
            )
            db.session.add(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

            payload = compose_fallback('where is the office located')
            assert 'Dubai' in payload['message']
            assert payload['intent'] == 'fallback'

            db.session.delete(entry)
            db.session.commit()
            kb_knowledge.invalidate_cache()

    def test_fallback_escalates_when_no_match(self, app):
        from module_assistant.responses import compose_fallback

        with app.app_context():
            kb_knowledge.invalidate_cache()
            payload = compose_fallback('zzqwx vqxztp qwlkjh')
            assert payload['intent'] == 'contact_admin'
            assert any(a.get('href') == '/tickets/' for a in payload.get('actions', []))


class TestUrlFetchAndSummary:
    def test_summarize_returns_text(self):
        from module_assistant.fetch_url import summarize_extractive

        text = (
            'The Injaaz platform helps facilities teams manage inspections. '
            'Inspections are logged daily by site supervisors. '
            'Reports are generated automatically from inspection data. '
            'Managers review reports and approve corrective actions. '
            'The platform also tracks procurement and HR requests.'
        )
        summary = summarize_extractive(text, max_sentences=3)
        assert summary
        assert 'inspection' in summary.lower()

    def test_summarize_handles_tiny_input(self):
        from module_assistant.fetch_url import summarize_extractive

        assert summarize_extractive('') == ''
        assert summarize_extractive('Short.') == 'Short.'

    def test_html_to_text_strips_markup(self):
        from module_assistant.fetch_url import _html_to_text

        html = (
            '<html><head><title>My Page</title></head>'
            '<body><nav>menu</nav><main><p>Important body content here.</p>'
            '<script>var x = 1;</script></main><footer>foot</footer></body></html>'
        )
        title, text = _html_to_text(html)
        assert title == 'My Page'
        assert 'Important body content' in text
        assert 'var x' not in text
        assert 'menu' not in text

    def test_fetch_rejects_non_http(self):
        from module_assistant.fetch_url import fetch_url_text, FetchError

        with pytest.raises(FetchError):
            fetch_url_text('ftp://example.com/file')

    def test_fetch_rejects_private_host(self):
        from module_assistant.fetch_url import fetch_url_text, FetchError

        with pytest.raises(FetchError):
            fetch_url_text('http://localhost/secret')
        with pytest.raises(FetchError):
            fetch_url_text('http://127.0.0.1/secret')

    def test_fetch_happy_path_mocked(self, monkeypatch):
        import requests
        from module_assistant import fetch_url as fu

        monkeypatch.setattr(fu, '_is_blocked_host', lambda host: False)

        class FakeResp:
            url = 'https://example.com/page'
            status_code = 200
            headers = {'Content-Type': 'text/html; charset=utf-8'}
            encoding = 'utf-8'

            def iter_content(self, chunk_size=16384, decode_unicode=False):
                yield (
                    b'<html><head><title>Doc</title></head><body><main>'
                    b'<p>Annual leave is 30 days for full time staff.</p>'
                    b'</main></body></html>'
                )

            def close(self):
                pass

        monkeypatch.setattr(requests, 'get', lambda *a, **k: FakeResp())
        title, text = fu.fetch_url_text('https://example.com/page')
        assert title == 'Doc'
        assert 'Annual leave' in text


class TestKnowledgeBaseLinkAPI:
    def test_link_requires_admin(self, client, auth_headers, app):
        with app.app_context():
            res = client.post(
                '/api/admin/knowledge-base/link',
                json={'url': 'https://example.com'},
                headers=auth_headers,
            )
            assert res.status_code == 403

    def test_link_create_and_refetch(self, client, admin_auth_headers, app, monkeypatch):
        from module_assistant import fetch_url as fu

        calls = {'n': 0}

        def fake_fetch(url):
            calls['n'] += 1
            return ('Leave Policy', 'Annual leave is 30 days. Sick leave is separate. Apply via HR.')

        monkeypatch.setattr(fu, 'fetch_url_text', fake_fetch)

        with app.app_context():
            create = client.post(
                '/api/admin/knowledge-base/link',
                json={'url': 'https://example.com/leave', 'category': 'HR'},
                headers=admin_auth_headers,
            )
            assert create.status_code == 201
            body = create.get_json()
            data = body.get('data') or body
            entry = data['entry']
            assert entry['source_type'] == 'link'
            assert entry['source_url'] == 'https://example.com/leave'
            entry_id = entry['id']

            refetch = client.post(
                f'/api/admin/knowledge-base/{entry_id}/refetch',
                headers=admin_auth_headers,
            )
            assert refetch.status_code == 200
            assert calls['n'] == 2

            client.delete(
                f'/api/admin/knowledge-base/{entry_id}',
                headers=admin_auth_headers,
            )

    def test_refetch_rejects_non_link(self, client, admin_auth_headers, app):
        with app.app_context():
            create = client.post(
                '/api/admin/knowledge-base',
                json={'title': 'Plain text', 'content': 'Just text.', 'category': 'General'},
                headers=admin_auth_headers,
            )
            body = create.get_json()
            data = body.get('data') or body
            entry_id = data['entry']['id']

            res = client.post(
                f'/api/admin/knowledge-base/{entry_id}/refetch',
                headers=admin_auth_headers,
            )
            assert res.status_code == 400

            client.delete(
                f'/api/admin/knowledge-base/{entry_id}',
                headers=admin_auth_headers,
            )
