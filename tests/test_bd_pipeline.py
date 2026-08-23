"""BD pipeline: quote approval, LPO, follow-up complete, deletes."""
from io import BytesIO


SIG = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


def _create_project(client, headers, name='QA Pipeline Deal'):
    r = client.post('/api/admin/bd/projects', json={
        'name': name,
        'company': 'QA Pipeline Co',
        'stage': 'proposal',
        'status': 'active',
        'value_amount': 10000,
    }, headers=headers)
    data = r.get_json() or {}
    assert r.status_code == 201, data
    return data['project']


def _create_quote(client, headers, project_id):
    r = client.post('/api/admin/bd/quotations', json={
        'bd_project_id': project_id,
        'company_name': 'QA Pipeline Co',
        'items': [{'description': 'Retainer', 'qty': 1, 'unit': 'lot', 'unit_price': 500}],
    }, headers=headers)
    data = r.get_json() or {}
    assert r.status_code == 201, data
    return data['quotation']


def test_submit_sets_pending_approval_not_won(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Submit Pending')
    quote = _create_quote(client, admin_auth_headers, project['id'])

    r = client.post(
        f"/api/admin/bd/quotations/{quote['id']}/submit",
        json={'signature': SIG},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['quotation']['status'] == 'pending_approval'
    assert data['quotation']['approved_at'] is None

    r = client.get(f"/api/admin/bd/projects/{project['id']}", headers=admin_auth_headers)
    got = (r.get_json() or {}).get('project') or {}
    assert got.get('status') != 'won'
    assert got.get('progress') != 100


def test_approve_marks_quote_and_deal_won(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Approve Won')
    quote = _create_quote(client, admin_auth_headers, project['id'])
    client.post(
        f"/api/admin/bd/quotations/{quote['id']}/submit",
        json={'signature': SIG},
        headers=admin_auth_headers,
    )
    r = client.post(
        f"/api/admin/bd/quotations/{quote['id']}/approve",
        json={'signature': SIG},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['quotation']['status'] == 'approved'

    r = client.get(f"/api/admin/bd/projects/{project['id']}", headers=admin_auth_headers)
    got = (r.get_json() or {}).get('project') or {}
    assert got.get('status') == 'won'
    assert got.get('stage') == 'closing'


def test_reject_pending_quote(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Reject Quote')
    quote = _create_quote(client, admin_auth_headers, project['id'])
    client.post(
        f"/api/admin/bd/quotations/{quote['id']}/submit",
        json={'signature': SIG},
        headers=admin_auth_headers,
    )
    r = client.post(
        f"/api/admin/bd/quotations/{quote['id']}/reject",
        json={'notes': 'Price too high'},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['quotation']['status'] == 'rejected'


def test_lpo_only_after_approval(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA LPO Gate')
    quote = _create_quote(client, admin_auth_headers, project['id'])
    r = client.post(
        f"/api/admin/bd/quotations/{quote['id']}/lpo",
        data={'file': (BytesIO(b'LPO-BYTES'), 'lpo.txt')},
        content_type='multipart/form-data',
        headers=admin_auth_headers,
    )
    assert r.status_code == 400

    client.post(
        f"/api/admin/bd/quotations/{quote['id']}/submit",
        json={'signature': SIG},
        headers=admin_auth_headers,
    )
    client.post(
        f"/api/admin/bd/quotations/{quote['id']}/approve",
        json={'signature': SIG},
        headers=admin_auth_headers,
    )
    r = client.post(
        f"/api/admin/bd/quotations/{quote['id']}/lpo",
        data={'file': (BytesIO(b'LPO-BYTES'), 'lpo.txt')},
        content_type='multipart/form-data',
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['quotation'].get('lpo_filename') == 'lpo.txt'
    assert data['quotation'].get('lpo_url')

    r = client.get(
        f"/api/admin/bd/quotations/{quote['id']}/lpo",
        headers=admin_auth_headers,
    )
    assert r.status_code == 200
    assert r.data == b'LPO-BYTES'


def test_followup_mark_done_and_reopen(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Followup Done')
    r = client.post('/api/admin/bd/followups', json={
        'title': 'Call the client',
        'company': 'QA Pipeline Co',
        'project_id': project['id'],
        'followup_type': 'call',
    }, headers=admin_auth_headers)
    data = r.get_json() or {}
    assert r.status_code == 201, data
    fid = data['followup']['id']
    assert data['followup']['status'] == 'open'

    r = client.put(
        f'/api/admin/bd/followups/{fid}',
        json={'status': 'done'},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['followup']['status'] == 'done'

    r = client.put(
        f'/api/admin/bd/followups/{fid}',
        json={'status': 'open'},
        headers=admin_auth_headers,
    )
    assert (r.get_json() or {}).get('followup', {}).get('status') == 'open'


def test_delete_contact(client, admin_auth_headers):
    r = client.post('/api/admin/bd/contacts', json={
        'name': 'QA Delete Contact',
        'company': 'QA Pipeline Co',
        'title': 'FM',
    }, headers=admin_auth_headers)
    data = r.get_json() or {}
    assert r.status_code == 201, data
    cid = data['contact']['id']

    r = client.delete(f'/api/admin/bd/contacts/{cid}', headers=admin_auth_headers)
    assert r.status_code == 200
    r = client.delete(f'/api/admin/bd/contacts/{cid}', headers=admin_auth_headers)
    assert r.status_code == 404


def test_delete_project_unlinks_quote(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Delete Project')
    quote = _create_quote(client, admin_auth_headers, project['id'])
    pid = project['id']
    qid = quote['id']

    r = client.delete(f'/api/admin/bd/projects/{pid}', headers=admin_auth_headers)
    assert r.status_code == 200, r.get_json()

    r = client.get(f'/api/admin/bd/projects/{pid}', headers=admin_auth_headers)
    assert r.status_code == 404

    r = client.get(f'/api/admin/bd/quotations/{qid}', headers=admin_auth_headers)
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['quotation']['bd_project_id'] is None


def test_bd_hub_exposes_new_actions(client):
    r = client.get('/admin/bd')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'bfQuoteAttachLpo' in html
    assert 'bfSetFollowupStatus' in html
    assert 'bfDeleteContact' in html
    assert 'bfDeleteProject' in html
    assert 'Conversion funnel' in html
    assert 'Outcome loop' in html
    js = open('static/js/bd-project-detail.js').read()
    assert 'pdQuoteAttachLpo' in js
    assert 'pdSetFollowupStatus' in js
    assert 'pdDeleteProject' in js
