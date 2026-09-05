"""Hiring candidate pipeline PATCH: stages + process states (on hold / not hired)."""


def _create_candidate(client, headers):
    response = client.post(
        '/hr/api/hiring/candidates',
        headers=headers,
        json={'full_name': 'Pipeline Test Candidate', 'role': 'Technician'},
    )
    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    candidate = data.get('candidate') or {}
    assert candidate.get('id')
    return candidate


def test_pipeline_process_states_are_valid(client, admin_auth_headers, app):
    from app.models import HIRING_PIPELINE_PROCESS_STATUSES, HIRING_PIPELINE_STATUSES

    assert 'on_hold' in HIRING_PIPELINE_STATUSES
    assert 'not_hired' in HIRING_PIPELINE_STATUSES
    assert HIRING_PIPELINE_PROCESS_STATUSES == ('on_hold', 'not_hired')

    created = _create_candidate(client, admin_auth_headers)
    cid = created['id']

    for status in HIRING_PIPELINE_PROCESS_STATUSES:
        response = client.patch(
            f'/hr/api/hiring/candidates/{cid}',
            headers=admin_auth_headers,
            json={'pipeline_status': status},
        )
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        candidate = body.get('candidate') or {}
        assert candidate.get('pipeline_status') == status
        assert candidate.get('is_on_hold') is (status == 'on_hold')
        assert candidate.get('is_not_hired') is (status == 'not_hired')

    resume = client.patch(
        f'/hr/api/hiring/candidates/{cid}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'gathering_documents'},
    )
    assert resume.status_code == 200, resume.get_json()
    assert resume.get_json()['candidate']['pipeline_status'] == 'gathering_documents'


def test_pipeline_reopen_not_hired_to_interview_completed(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers)
    cid = created['id']
    closed = client.patch(
        f'/hr/api/hiring/candidates/{cid}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'not_hired'},
    )
    assert closed.status_code == 200, closed.get_json()
    assert closed.get_json()['candidate']['pipeline_status'] == 'not_hired'
    assert closed.get_json()['candidate']['is_not_hired'] is True

    reopened = client.patch(
        f'/hr/api/hiring/candidates/{cid}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'interview_completed'},
    )
    assert reopened.status_code == 200, reopened.get_json()
    candidate = reopened.get_json()['candidate']
    assert candidate['pipeline_status'] == 'interview_completed'
    assert candidate['is_not_hired'] is False
    assert candidate['is_on_hold'] is False


def test_link_picker_omits_not_hired_and_keeps_active_role(client, admin_auth_headers):
    electrician = client.post(
        '/hr/api/hiring/candidates',
        headers=admin_auth_headers,
        json={'full_name': 'Kuppai Mydeen', 'role': 'Electrician'},
    )
    assert electrician.status_code == 201, electrician.get_json()
    electrician_id = electrician.get_json()['candidate']['id']

    not_hired = client.post(
        '/hr/api/hiring/candidates',
        headers=admin_auth_headers,
        json={'full_name': 'Bencis Camacho Betinol', 'role': 'Office Boy'},
    )
    assert not_hired.status_code == 201, not_hired.get_json()
    not_hired_id = not_hired.get_json()['candidate']['id']
    closed = client.patch(
        f'/hr/api/hiring/candidates/{not_hired_id}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'not_hired'},
    )
    assert closed.status_code == 200, closed.get_json()

    on_hold = client.post(
        '/hr/api/hiring/candidates',
        headers=admin_auth_headers,
        json={'full_name': 'On Hold Plumber', 'role': 'Plumber'},
    )
    assert on_hold.status_code == 201, on_hold.get_json()
    on_hold_id = on_hold.get_json()['candidate']['id']
    paused = client.patch(
        f'/hr/api/hiring/candidates/{on_hold_id}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'on_hold'},
    )
    assert paused.status_code == 200, paused.get_json()

    listing = client.get(
        '/hr/api/staffing/unassigned-candidates',
        headers=admin_auth_headers,
    )
    assert listing.status_code == 200, listing.get_json()
    body = listing.get_json()
    candidates = body.get('candidates') or []
    ids = [c.get('id') for c in candidates]
    assert electrician_id in ids
    assert on_hold_id in ids
    assert not_hired_id not in ids
    assert all(c.get('pipeline_status') != 'not_hired' for c in candidates)
    match = next(c for c in candidates if c.get('id') == electrician_id)
    assert match.get('role') == 'Electrician'
    assert match.get('is_not_hired') is False


def test_role_trade_match_accepts_technician_typo():
    from module_hr.staffing_link import role_trade_match_score

    assert role_trade_match_score('AC Techinician', 'AC Technician') >= 30
    assert role_trade_match_score('AC Technician', 'AC Technician') >= 30
    assert role_trade_match_score('Electrician', 'AC Technician') < 30
    assert role_trade_match_score('HVAC Technician', 'AC Technician') < 30


def test_pipeline_rejects_unknown_status(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers)
    response = client.patch(
        f'/hr/api/hiring/candidates/{created["id"]}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'paused'},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data.get('success') is False
    assert 'paused' in (data.get('error') or '')


def test_employed_cannot_move_to_hold_or_not_hired(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers)
    cid = created['id']
    hired = client.patch(
        f'/hr/api/hiring/candidates/{cid}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'candidate_employee'},
    )
    assert hired.status_code == 200, hired.get_json()
    assert hired.get_json()['candidate']['pipeline_status'] == 'candidate_employee'

    for status in ('on_hold', 'not_hired'):
        blocked = client.patch(
            f'/hr/api/hiring/candidates/{cid}',
            headers=admin_auth_headers,
            json={'pipeline_status': status},
        )
        assert blocked.status_code == 400, blocked.get_json()
        body = blocked.get_json()
        assert body.get('success') is False
        assert 'already been hired' in (body.get('error') or '').lower()

    still_hired = client.patch(
        f'/hr/api/hiring/candidates/{cid}',
        headers=admin_auth_headers,
        json={'pipeline_status': 'visa_process_started'},
    )
    assert still_hired.status_code == 200, still_hired.get_json()
    assert still_hired.get_json()['candidate']['pipeline_status'] == 'visa_process_started'
