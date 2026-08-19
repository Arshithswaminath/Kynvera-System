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
