"""Letters of Intent register: flags, comment, uploads, and hiring connect paths."""
from io import BytesIO

from app.models import HiringCandidate, HiringDocument, HiringOfferLetter, db


def _create_letter(client, headers, **kwargs):
    payload = {
        'full_name': 'Aisha Khan',
        'role': 'Electrician',
        'doc_kind': 'letter_of_intent',
        'comments': 'Scanned from HR desk',
        'received': False,
        'signed_back': False,
    }
    payload.update(kwargs)
    response = client.post('/hr/api/hiring/offer-letters', headers=headers, json=payload)
    assert response.status_code == 201, response.get_json()
    letter = response.get_json().get('letter') or {}
    assert letter.get('id')
    return letter


def _create_candidate(client, headers, **kwargs):
    payload = {'full_name': 'Hiring File Person', 'role': 'Technician'}
    payload.update(kwargs)
    response = client.post('/hr/api/hiring/candidates', headers=headers, json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()['candidate']


def test_create_letter_with_comment_and_flags(client, admin_auth_headers):
    letter = _create_letter(
        client,
        admin_auth_headers,
        comments='Waiting on scan',
        received=False,
        signed_back=False,
    )
    assert letter['doc_kind'] == 'letter_of_intent'
    assert letter['comments'] == 'Waiting on scan'
    assert letter['received'] is False
    assert letter['signed_back'] is False
    assert letter['not_accepted'] is False
    assert letter['candidate_outcome'] == 'pending_hr'
    assert letter['link_status'] == 'unlinked'
    assert letter['prompt_connect'] is False
    assert letter['created_at']
    assert letter['updated_at']

    patched = client.patch(
        f'/hr/api/hiring/offer-letters/{letter["id"]}',
        headers=admin_auth_headers,
        json={'received': True, 'comments': 'Got it from HR'},
    )
    assert patched.status_code == 200, patched.get_json()
    body = patched.get_json()['letter']
    assert body['received'] is True
    assert body['comments'] == 'Got it from HR'
    assert body['candidate_outcome'] == 'awaiting_signature'
    assert body['prompt_connect'] is True


def test_signed_back_implies_received(client, admin_auth_headers):
    letter = _create_letter(client, admin_auth_headers)
    patched = client.patch(
        f'/hr/api/hiring/offer-letters/{letter["id"]}',
        headers=admin_auth_headers,
        json={'signed_back': True},
    )
    assert patched.status_code == 200, patched.get_json()
    body = patched.get_json()['letter']
    assert body['signed_back'] is True
    assert body['received'] is True
    assert body['not_accepted'] is False
    assert body['candidate_outcome'] == 'signed'


def test_not_accepted_after_received(client, admin_auth_headers):
    letter = _create_letter(client, admin_auth_headers, received=True)
    patched = client.patch(
        f'/hr/api/hiring/offer-letters/{letter["id"]}',
        headers=admin_auth_headers,
        json={'candidate_outcome': 'not_accepted'},
    )
    assert patched.status_code == 200, patched.get_json()
    body = patched.get_json()['letter']
    assert body['received'] is True
    assert body['not_accepted'] is True
    assert body['signed_back'] is False
    assert body['candidate_outcome'] == 'not_accepted'

    # Clearing received resets step 2
    cleared = client.patch(
        f'/hr/api/hiring/offer-letters/{letter["id"]}',
        headers=admin_auth_headers,
        json={'received': False},
    )
    assert cleared.status_code == 200, cleared.get_json()
    again = cleared.get_json()['letter']
    assert again['received'] is False
    assert again['not_accepted'] is False
    assert again['signed_back'] is False
    assert again['candidate_outcome'] == 'pending_hr'


def test_upload_scan_marks_received_and_prompt_connect(client, admin_auth_headers):
    letter = _create_letter(client, admin_auth_headers)
    upload = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/scan',
        headers=admin_auth_headers,
        data={'file': (BytesIO(b'%PDF-1.4 scan'), 'hr-scan.pdf')},
        content_type='multipart/form-data',
    )
    assert upload.status_code == 200, upload.get_json()
    body = upload.get_json()['letter']
    assert body['received'] is True
    assert body['has_scan_file'] is True
    assert body['prompt_connect'] is True

    fetched = client.get(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/file?kind=scan',
        headers=admin_auth_headers,
    )
    assert fetched.status_code == 200


def test_link_existing_candidate_copies_file_and_bumps_pipeline(client, admin_auth_headers, app):
    candidate = _create_candidate(client, admin_auth_headers)
    letter = _create_letter(client, admin_auth_headers, received=True, comments='Desk copy')
    upload = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/scan',
        headers=admin_auth_headers,
        data={'file': (BytesIO(b'%PDF-1.4 offer'), 'offer.pdf')},
        content_type='multipart/form-data',
    )
    assert upload.status_code == 200, upload.get_json()

    linked = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/link',
        headers=admin_auth_headers,
        json={'candidate_id': candidate['id']},
    )
    assert linked.status_code == 200, linked.get_json()
    body = linked.get_json()
    assert body['letter']['link_status'] == 'linked'
    assert body['letter']['hiring_candidate_id'] == candidate['id']
    assert body['letter']['prompt_connect'] is False
    cand = body['candidate']
    assert cand['pipeline_status'] == 'offer_letter_prepared'
    offer_doc = next(d for d in cand['documents'] if d['doc_type'] == 'offer_letter')
    assert offer_doc['has_file'] is True
    assert offer_doc['is_complete'] is True
    assert offer_doc['notes'] == 'Desk copy'
    assert cand['linked_offer_letters']

    with app.app_context():
        slot = HiringDocument.query.filter_by(
            candidate_id=candidate['id'], doc_type='offer_letter'
        ).first()
        assert slot is not None
        assert slot.has_file()


def test_create_candidate_from_letter(client, admin_auth_headers):
    letter = _create_letter(
        client,
        admin_auth_headers,
        full_name='New Hire Ali',
        role='Plumber',
        department='Ops',
        received=True,
        signed_back=True,
        comments='Signed at reception',
    )
    created = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/link',
        headers=admin_auth_headers,
        json={'create_candidate': True},
    )
    assert created.status_code == 200, created.get_json()
    body = created.get_json()
    cand = body['candidate']
    assert cand['full_name'] == 'New Hire Ali'
    assert cand['role'] == 'Plumber'
    assert cand['department'] == 'Ops'
    assert cand['pipeline_status'] == 'offer_letter_signed'
    assert body['letter']['link_status'] == 'linked'
    assert body['letter']['hiring_candidate_id'] == cand['id']
    offer_doc = next(d for d in cand['documents'] if d['doc_type'] == 'offer_letter')
    assert offer_doc['is_complete'] is True
    assert offer_doc['notes'] == 'Signed at reception'


def test_manual_hiring_then_unlink(client, admin_auth_headers):
    letter = _create_letter(client, admin_auth_headers, received=True)
    manual = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/link',
        headers=admin_auth_headers,
        json={'manual': True},
    )
    assert manual.status_code == 200, manual.get_json()
    body = manual.get_json()['letter']
    assert body['link_status'] == 'manual'
    assert body['hiring_candidate_id'] is None
    assert body['prompt_connect'] is False

    unlinked = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/unlink',
        headers=admin_auth_headers,
        json={},
    )
    assert unlinked.status_code == 200, unlinked.get_json()
    again = unlinked.get_json()['letter']
    assert again['link_status'] == 'unlinked'
    assert again['prompt_connect'] is True


def test_delete_candidate_detaches_letter(client, admin_auth_headers, app):
    letter = _create_letter(client, admin_auth_headers, received=True)
    created = client.post(
        f'/hr/api/hiring/offer-letters/{letter["id"]}/link',
        headers=admin_auth_headers,
        json={'create_candidate': True},
    )
    assert created.status_code == 200, created.get_json()
    cid = created.get_json()['candidate']['id']

    deleted = client.delete(f'/hr/api/hiring/candidates/{cid}', headers=admin_auth_headers)
    assert deleted.status_code == 200, deleted.get_json()

    remaining = client.get(
        f'/hr/api/hiring/offer-letters/{letter["id"]}',
        headers=admin_auth_headers,
    )
    assert remaining.status_code == 200, remaining.get_json()
    body = remaining.get_json()['letter']
    assert body['hiring_candidate_id'] is None
    assert body['link_status'] == 'unlinked'

    with app.app_context():
        assert db.session.get(HiringOfferLetter, letter['id']) is not None
        assert db.session.get(HiringCandidate, cid) is None


def test_offer_letters_page_renders(client, admin_auth_headers):
    page = client.get('/hr/hiring/offer-letters', headers=admin_auth_headers)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Letters of Intent' in html
    assert 'ol-toolbar' in html
    assert 'Connect to hiring' in html
    assert 'Add letter of intent' in html
    assert 'name="doc_kind"' not in html
    assert 'ol-status-card' in html
    assert 'Add HR scan' in html
    assert 'olPreviewModal' in html
    assert 'name="candidate_outcome"' in html
    assert 'Not accepted' in html
    assert 'olStep2Card' in html


def test_new_letter_defaults_to_letter_of_intent(client, admin_auth_headers):
    response = client.post(
        '/hr/api/hiring/offer-letters',
        headers=admin_auth_headers,
        json={'full_name': 'No Kind Specified'},
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()['letter']['doc_kind'] == 'letter_of_intent'


def test_list_filters_and_comment_search(client, admin_auth_headers):
    _create_letter(
        client, admin_auth_headers,
        full_name='Blue Folder Person', comments='blue folder',
    )
    _create_letter(
        client, admin_auth_headers,
        full_name='Pink Folder Person', comments='pink folder',
    )
    search = client.get(
        '/hr/api/hiring/offer-letters?q=blue%20folder',
        headers=admin_auth_headers,
    )
    assert search.status_code == 200, search.get_json()
    found = [x['full_name'] for x in search.get_json()['letters']]
    assert 'Blue Folder Person' in found
    assert 'Pink Folder Person' not in found
