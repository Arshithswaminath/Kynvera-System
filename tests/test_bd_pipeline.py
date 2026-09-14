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


def _create_followup(client, headers, title='QA Follow-up', **extra):
    payload = {'title': title, 'company': 'QA Pipeline Co'}
    payload.update(extra)
    r = client.post('/api/admin/bd/followups', json=payload, headers=headers)
    data = r.get_json() or {}
    assert r.status_code == 201, data
    return data['followup']


def test_stage_move_persists_and_returns_stats(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Stage Move')

    r = client.post(
        f"/api/admin/bd/projects/{project['id']}/stage",
        json={'stage': 'negotiation'},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['project']['stage'] == 'negotiation'
    assert data['project']['stageChangedAt']

    by_stage = {s['stage']: s for s in data['stats']['stage_stats']}
    assert by_stage['negotiation']['count'] >= 1
    assert 'forecast' in data['stats'] and 'funnel' in data['stats']

    r = client.get(f"/api/admin/bd/projects/{project['id']}", headers=admin_auth_headers)
    assert (r.get_json() or {})['project']['stage'] == 'negotiation'


def test_stage_move_rejects_unknown_stage(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Stage Invalid')
    r = client.post(
        f"/api/admin/bd/projects/{project['id']}/stage",
        json={'stage': 'not-a-stage'},
        headers=admin_auth_headers,
    )
    assert r.status_code == 400
    r = client.get(f"/api/admin/bd/projects/{project['id']}", headers=admin_auth_headers)
    assert (r.get_json() or {})['project']['stage'] == 'proposal'


def test_same_stage_move_writes_no_activity(client, admin_auth_headers):
    from app.models import BDActivity

    project = _create_project(client, admin_auth_headers, 'QA Stage Idempotent')
    before = BDActivity.query.count()
    r = client.post(
        f"/api/admin/bd/projects/{project['id']}/stage",
        json={'stage': 'proposal'},
        headers=admin_auth_headers,
    )
    assert r.status_code == 200, r.get_json()
    assert BDActivity.query.count() == before


def test_status_endpoint_rejects_won(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Status Won')
    r = client.post(
        f"/api/admin/bd/projects/{project['id']}/status",
        json={'status': 'won'},
        headers=admin_auth_headers,
    )
    assert r.status_code == 400

    r = client.post(
        f"/api/admin/bd/projects/{project['id']}/status",
        json={'status': 'lost', 'reason': 'Budget cut'},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['project']['status'] == 'lost'


def test_delete_followup(client, admin_auth_headers):
    followup = _create_followup(client, admin_auth_headers, 'QA Delete Follow-up')
    r = client.delete(f"/api/admin/bd/followups/{followup['id']}", headers=admin_auth_headers)
    assert r.status_code == 200, r.get_json()
    r = client.delete(f"/api/admin/bd/followups/{followup['id']}", headers=admin_auth_headers)
    assert r.status_code == 404


def test_complete_followup_with_outcome_and_chain(client, admin_auth_headers):
    project = _create_project(client, admin_auth_headers, 'QA Complete Chain')
    followup = _create_followup(
        client, admin_auth_headers, 'QA Chain Parent', project_id=project['id']
    )

    r = client.post(
        f"/api/admin/bd/followups/{followup['id']}/complete",
        json={
            'outcome': 'Spoke to the FM, wants revised pricing',
            'outcome_code': 'connected',
            'next': {'title': 'Send revised pricing', 'due_at': '2026-10-01T09:00:00'},
        },
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['followup']['status'] == 'done'
    assert data['followup']['completedAt']
    assert data['followup']['outcomeCode'] == 'connected'
    assert data['next_followup']['title'] == 'Send revised pricing'
    # the chained follow-up inherits the deal link
    assert data['next_followup']['projectId'] == project['id']


def test_complete_followup_bad_next_date_leaves_parent_open(client, admin_auth_headers):
    followup = _create_followup(client, admin_auth_headers, 'QA Chain Bad Date')
    r = client.post(
        f"/api/admin/bd/followups/{followup['id']}/complete",
        json={'next': {'title': 'Follow up again', 'due_at': 'not-a-date'}},
        headers=admin_auth_headers,
    )
    assert r.status_code == 400

    r = client.get('/api/admin/bd/dashboard-data', headers=admin_auth_headers)
    rows = {f['id']: f for f in (r.get_json() or {}).get('followups', [])}
    assert rows[followup['id']]['status'] == 'open'


def test_snooze_tracks_original_due_date(client, admin_auth_headers):
    followup = _create_followup(
        client, admin_auth_headers, 'QA Snooze', due_at='2026-09-01T09:00:00'
    )
    r = client.post(
        f"/api/admin/bd/followups/{followup['id']}/snooze",
        json={'days': 3},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert data['followup']['snoozeCount'] == 1
    first_original = data['followup']['originalDueAt']
    assert first_original.startswith('2026-09-01')

    r = client.post(
        f"/api/admin/bd/followups/{followup['id']}/snooze",
        json={'days': 5},
        headers=admin_auth_headers,
    )
    data = r.get_json() or {}
    assert data['followup']['snoozeCount'] == 2
    # the original due date is captured once and never moves again
    assert data['followup']['originalDueAt'] == first_original


def test_bulk_reports_partial_failure(client, admin_auth_headers):
    a = _create_followup(client, admin_auth_headers, 'QA Bulk A')
    b = _create_followup(client, admin_auth_headers, 'QA Bulk B')

    r = client.post('/api/admin/bd/followups/bulk', json={
        'action': 'complete',
        'ids': [a['id'], b['id'], 999999],
    }, headers=admin_auth_headers)
    data = r.get_json() or {}
    assert r.status_code == 200, data
    assert sorted(data['result']['succeeded']) == sorted([a['id'], b['id']])
    assert data['result']['failed'][0]['id'] == 999999
    assert data['result']['failed'][0]['code'] == 'NOT_FOUND'
    assert all(f['status'] == 'done' for f in data['followups'])


def test_bulk_rejects_oversized_and_bad_assignee(client, admin_auth_headers):
    r = client.post('/api/admin/bd/followups/bulk', json={
        'action': 'complete', 'ids': list(range(1, 202)),
    }, headers=admin_auth_headers)
    assert r.status_code == 400

    followup = _create_followup(client, admin_auth_headers, 'QA Bulk Assign')
    r = client.post('/api/admin/bd/followups/bulk', json={
        'action': 'reassign',
        'ids': [followup['id']],
        'params': {'assignee_id': 999999},
    }, headers=admin_auth_headers)
    assert r.status_code == 400
    # rejected before any row was touched
    r = client.get('/api/admin/bd/dashboard-data', headers=admin_auth_headers)
    rows = {f['id']: f for f in (r.get_json() or {}).get('followups', [])}
    assert rows[followup['id']]['status'] == 'open'


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
    # kanban board + follow-ups workspace
    assert 'bfKanbanMoveStage' in html
    assert 'bfKanbanBoard' in html
    assert 'bfFuBulk' in html
    assert 'bfSaveFuOutcome' in html
    assert 'bfApplyFuSnooze' in html
    js = open('static/js/bd-project-detail.js').read()
    assert 'pdQuoteAttachLpo' in js
    assert 'pdSetFollowupStatus' in js
    assert 'pdDeleteProject' in js
