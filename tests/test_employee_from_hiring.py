"""Promote Candidate employed people onto the Employee List roster."""

from tests.factories import make_user


def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


def _create_candidate(client, headers, name='Hired Candidate', role='Technician'):
    response = client.post(
        '/hr/api/hiring/candidates',
        headers=headers,
        json={'full_name': name, 'role': role},
    )
    assert response.status_code == 201, response.get_json()
    return (response.get_json() or {}).get('candidate') or {}


def _mark_employed(client, headers, candidate_id):
    response = client.patch(
        f'/hr/api/hiring/candidates/{candidate_id}',
        headers=headers,
        json={'pipeline_status': 'candidate_employee'},
    )
    assert response.status_code == 200, response.get_json()
    return (response.get_json() or {}).get('candidate') or {}


def test_hired_candidate_is_pending_not_on_roster(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers)
    cid = created['id']
    hired = _mark_employed(client, admin_auth_headers, cid)
    assert hired.get('pipeline_status') == 'candidate_employee'
    assert hired.get('on_employee_list') is False
    assert hired.get('leave_employee_id') in (None, '')

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    assert pending.status_code == 200, pending.get_json()
    rows = (pending.get_json() or {}).get('pending') or []
    ids = [row.get('hiring_candidate_id') for row in rows]
    assert cid in ids
    match = next(row for row in rows if row.get('hiring_candidate_id') == cid)
    assert 'emp_id' in (match.get('required_reasons') or [])

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    assert roster.status_code == 200
    names = {row.get('full_name') for row in ((roster.get_json() or {}).get('employees') or [])}
    assert 'Hired Candidate' not in names

    count = client.get('/hr/api/employee-from-hiring/count', headers=admin_auth_headers)
    assert count.status_code == 200
    assert ((count.get_json() or {}).get('count') or 0) >= 1


def test_promote_requires_emp_id_and_name(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers, name='Need Fields')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    missing_id = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={'full_name': 'Need Fields', 'emp_id': ''},
    )
    assert missing_id.status_code == 400, missing_id.get_json()

    missing_name = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={'full_name': '', 'emp_id': 'EFH-1'},
    )
    assert missing_name.status_code == 400, missing_name.get_json()


def test_promote_creates_employee_and_leaves_queue(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers, name='Promote Me', role='Coordinator')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    promoted = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={
            'emp_id': 'EFH-OK-1',
            'full_name': 'Promote Me',
            'designation': 'Coordinator',
            'company': 'Kynvera',
        },
    )
    assert promoted.status_code == 200, promoted.get_json()
    body = promoted.get_json() or {}
    emp = body.get('employee') or {}
    assert emp.get('emp_id') == 'EFH-OK-1'
    assert emp.get('full_name') == 'Promote Me'
    assert emp.get('designation') == 'Coordinator'
    assert (body.get('candidate') or {}).get('on_employee_list') is True
    assert (body.get('candidate') or {}).get('leave_employee_id') == emp.get('id')

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    ids = [row.get('hiring_candidate_id') for row in ((pending.get_json() or {}).get('pending') or [])]
    assert cid not in ids

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    emp_ids = {row.get('emp_id') for row in ((roster.get_json() or {}).get('employees') or [])}
    assert 'EFH-OK-1' in emp_ids

    again = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-OK-2', 'full_name': 'Promote Me'},
    )
    assert again.status_code == 409, again.get_json()


def test_revoke_employee_returns_to_hiring_queue(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers, name='Duplicate Add', role='Cleaner')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    promoted = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-DUP-ADD', 'full_name': 'Duplicate Add', 'designation': 'Cleaner'},
    )
    assert promoted.status_code == 200, promoted.get_json()
    emp_id = ((promoted.get_json() or {}).get('employee') or {}).get('id')
    assert emp_id

    after_promote = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    assert cid not in [
        row.get('hiring_candidate_id')
        for row in ((after_promote.get_json() or {}).get('pending') or [])
    ]
    promoted_roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    promoted_row = next(
        row for row in ((promoted_roster.get_json() or {}).get('employees') or [])
        if row.get('emp_id') == 'EFH-DUP-ADD'
    )
    assert promoted_row.get('from_hiring') is True
    assert promoted_row.get('has_prior_record') is False

    revoked = client.delete(
        f'/hr/api/leave-tracker/employees/{emp_id}',
        headers=admin_auth_headers,
    )
    assert revoked.status_code == 200, revoked.get_json()
    body = revoked.get_json() or {}
    assert body.get('reverted_hiring_candidate_id') == cid
    assert body.get('kept_employee_record') is False

    candidate = client.get(f'/hr/api/hiring/candidates/{cid}', headers=admin_auth_headers)
    assert candidate.status_code == 200, candidate.get_json()
    cand_data = (candidate.get_json() or {}).get('candidate') or {}
    assert cand_data.get('pipeline_status') == 'candidate_employee'
    assert cand_data.get('leave_employee_id') in (None, '')
    assert cand_data.get('on_employee_list') is False

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    assert pending.status_code == 200, pending.get_json()
    ids = [row.get('hiring_candidate_id') for row in ((pending.get_json() or {}).get('pending') or [])]
    assert cid in ids

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    emp_ids = {row.get('emp_id') for row in ((roster.get_json() or {}).get('employees') or [])}
    assert 'EFH-DUP-ADD' not in emp_ids

    again = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-DUP-ADD', 'full_name': 'Duplicate Add', 'designation': 'Cleaner'},
    )
    assert again.status_code == 200, again.get_json()
    assert ((again.get_json() or {}).get('employee') or {}).get('emp_id') == 'EFH-DUP-ADD'


def test_revoke_keeps_existing_employee_list_record(client, admin_auth_headers):
    existing = client.post(
        '/hr/api/leave-tracker/employees',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-KEEP', 'full_name': 'Already On List', 'company': 'Kynvera'},
    )
    assert existing.status_code == 201, existing.get_json()
    emp_pk = ((existing.get_json() or {}).get('employee') or {}).get('id')
    assert emp_pk

    created = _create_candidate(client, admin_auth_headers, name='Already On List')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    merged = client.post(
        f'/hr/api/employee-from-hiring/{cid}/dismiss',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-KEEP'},
    )
    assert merged.status_code == 200, merged.get_json()

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    listed = next(
        row for row in ((roster.get_json() or {}).get('employees') or [])
        if row.get('emp_id') == 'EFH-KEEP'
    )
    assert listed.get('from_hiring') is True
    assert listed.get('has_prior_record') is True

    revoked = client.delete(
        f'/hr/api/leave-tracker/employees/{emp_pk}',
        headers=admin_auth_headers,
    )
    assert revoked.status_code == 200, revoked.get_json()
    body = revoked.get_json() or {}
    assert body.get('kept_employee_record') is True
    assert body.get('deleted') is False
    assert body.get('reverted_hiring_candidate_id') == cid

    still = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    emp_ids = {row.get('emp_id') for row in ((still.get_json() or {}).get('employees') or [])}
    assert 'EFH-KEEP' in emp_ids
    kept = next(
        row for row in ((still.get_json() or {}).get('employees') or [])
        if row.get('emp_id') == 'EFH-KEEP'
    )
    assert kept.get('from_hiring') is False
    assert kept.get('has_prior_record') is False

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    ids = [row.get('hiring_candidate_id') for row in ((pending.get_json() or {}).get('pending') or [])]
    assert cid in ids


def test_promote_duplicate_emp_id_offers_merge(client, admin_auth_headers):
    existing = client.post(
        '/hr/api/leave-tracker/employees',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-DUP', 'full_name': 'Already There', 'company': 'Kynvera'},
    )
    assert existing.status_code == 201, existing.get_json()

    created = _create_candidate(client, admin_auth_headers, name='Dup Hire')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    dup = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-DUP', 'full_name': 'Dup Hire'},
    )
    assert dup.status_code == 409, dup.get_json()
    body = dup.get_json() or {}
    assert body.get('error_code') == 'NEEDS_MERGE'
    match = ((body.get('details') or {}).get('matched_employee') or {})
    assert match.get('emp_id') == 'EFH-DUP'

    merged = client.post(
        f'/hr/api/employee-from-hiring/{cid}/dismiss',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-DUP'},
    )
    assert merged.status_code == 200, merged.get_json()
    assert (merged.get_json() or {}).get('employee', {}).get('full_name') == 'Already There'


def test_similar_names_offer_merge_and_update_full_name(client, admin_auth_headers):
    existing = client.post(
        '/hr/api/leave-tracker/employees',
        headers=admin_auth_headers,
        json={
            'emp_id': '905',
            'full_name': 'Mohammad Faheem',
            'designation': 'HVAC Technician',
            'company': 'Kynvera',
        },
    )
    assert existing.status_code == 201, existing.get_json()

    created = _create_candidate(
        client,
        admin_auth_headers,
        name='Mohamed Faheem Moeen Uddin',
        role='HVAC Technician',
    )
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    match = next(
        row for row in ((pending.get_json() or {}).get('pending') or [])
        if row.get('hiring_candidate_id') == cid
    )
    assert match.get('already_on_list') is True
    assert (match.get('matched_employee') or {}).get('emp_id') == '905'
    assert (match.get('matched_employee') or {}).get('name_can_update') is True

    merged = client.post(
        f'/hr/api/employee-from-hiring/{cid}/dismiss',
        headers=admin_auth_headers,
        json={'emp_id': '905'},
    )
    assert merged.status_code == 200, merged.get_json()
    body = merged.get_json() or {}
    assert body.get('name_updated') is True
    assert (body.get('employee') or {}).get('full_name') == 'Mohamed Faheem Moeen Uddin'


def test_already_on_list_can_be_removed_from_queue(client, admin_auth_headers):
    existing = client.post(
        '/hr/api/leave-tracker/employees',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-LISTED', 'full_name': 'Listed Person', 'company': 'Kynvera'},
    )
    assert existing.status_code == 201, existing.get_json()

    created = _create_candidate(client, admin_auth_headers, name='Listed Person')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    assert pending.status_code == 200, pending.get_json()
    match = next(
        row for row in ((pending.get_json() or {}).get('pending') or [])
        if row.get('hiring_candidate_id') == cid
    )
    assert match.get('already_on_list') is True
    assert (match.get('matched_employee') or {}).get('emp_id') == 'EFH-LISTED'

    merged = client.post(
        f'/hr/api/employee-from-hiring/{cid}/dismiss',
        headers=admin_auth_headers,
    )
    assert merged.status_code == 200, merged.get_json()
    assert (merged.get_json() or {}).get('employee', {}).get('from_hiring') is True

    after = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    ids = [row.get('hiring_candidate_id') for row in ((after.get_json() or {}).get('pending') or [])]
    assert cid not in ids

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    listed = next(
        row for row in ((roster.get_json() or {}).get('employees') or [])
        if row.get('emp_id') == 'EFH-LISTED'
    )
    assert listed.get('from_hiring') is True
    assert listed.get('full_name') == 'Listed Person'


def test_merge_updates_shorter_staff_name(client, admin_auth_headers):
    existing = client.post(
        '/hr/api/leave-tracker/employees',
        headers=admin_auth_headers,
        json={'emp_id': 'EFH-SHORT', 'full_name': 'Sherif Rahaman', 'company': 'Kynvera'},
    )
    assert existing.status_code == 201, existing.get_json()

    created = _create_candidate(
        client, admin_auth_headers, name='Sherif Rahaman Sekh Sentu Sekh'
    )
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    match = next(
        row for row in ((pending.get_json() or {}).get('pending') or [])
        if row.get('hiring_candidate_id') == cid
    )
    assert match.get('already_on_list') is True
    assert (match.get('matched_employee') or {}).get('name_can_update') is True

    merged = client.post(
        f'/hr/api/employee-from-hiring/{cid}/dismiss',
        headers=admin_auth_headers,
    )
    assert merged.status_code == 200, merged.get_json()
    body = merged.get_json() or {}
    assert body.get('name_updated') is True
    assert (body.get('employee') or {}).get('full_name') == 'Sherif Rahaman Sekh Sentu Sekh'

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    listed = next(
        row for row in ((roster.get_json() or {}).get('employees') or [])
        if row.get('emp_id') == 'EFH-SHORT'
    )
    assert listed.get('full_name') == 'Sherif Rahaman Sekh Sentu Sekh'
    assert listed.get('from_hiring') is True


def test_similar_name_can_create_separate_employee(client, admin_auth_headers):
    existing = client.post(
        '/hr/api/leave-tracker/employees',
        headers=admin_auth_headers,
        json={'emp_id': '698', 'full_name': 'Mohd Arif', 'company': 'Kynvera'},
    )
    assert existing.status_code == 201, existing.get_json()

    created = _create_candidate(
        client, admin_auth_headers, name='Mohammed Arif', role='Technician'
    )
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    pending = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    match = next(
        row for row in ((pending.get_json() or {}).get('pending') or [])
        if row.get('hiring_candidate_id') == cid
    )
    assert match.get('already_on_list') is True
    assert (match.get('matched_employee') or {}).get('emp_id') == '698'

    promoted = client.post(
        f'/hr/api/employee-from-hiring/{cid}/promote',
        headers=admin_auth_headers,
        json={
            'emp_id': 'EFH-NEW-ARIF',
            'full_name': 'Mohammed Arif',
            'designation': 'Technician',
            'company': 'Kynvera',
        },
    )
    assert promoted.status_code == 200, promoted.get_json()
    emp = (promoted.get_json() or {}).get('employee') or {}
    assert emp.get('emp_id') == 'EFH-NEW-ARIF'
    assert emp.get('full_name') == 'Mohammed Arif'

    roster = client.get('/hr/api/leave-tracker/employees', headers=admin_auth_headers)
    emp_ids = {row.get('emp_id') for row in ((roster.get_json() or {}).get('employees') or [])}
    assert '698' in emp_ids
    assert 'EFH-NEW-ARIF' in emp_ids

    after = client.get('/hr/api/employee-from-hiring', headers=admin_auth_headers)
    ids = [row.get('hiring_candidate_id') for row in ((after.get_json() or {}).get('pending') or [])]
    assert cid not in ids


def test_dismiss_requires_existing_employee(client, admin_auth_headers):
    created = _create_candidate(client, admin_auth_headers, name='Only In Hiring')
    cid = created['id']
    _mark_employed(client, admin_auth_headers, cid)

    dismissed = client.post(
        f'/hr/api/employee-from-hiring/{cid}/dismiss',
        headers=admin_auth_headers,
    )
    assert dismissed.status_code == 409, dismissed.get_json()


def test_employee_from_hiring_requires_hiring_access(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=False)
        username = user.username
    headers = _login(client, username, pwd)
    page = client.get('/hr/employee-from-hiring', headers=headers)
    assert page.status_code == 403
    listing = client.get('/hr/api/employee-from-hiring', headers=headers)
    assert listing.status_code == 403
    promote = client.post(
        '/hr/api/employee-from-hiring/1/promote',
        headers=headers,
        json={'emp_id': 'X', 'full_name': 'Nope'},
    )
    assert promote.status_code == 403
    dismiss = client.post(
        '/hr/api/employee-from-hiring/1/dismiss',
        headers=headers,
    )
    assert dismiss.status_code == 403


def test_employee_list_page_has_incomplete_toggle(client, admin_auth_headers):
    page = client.get('/hr/employee-list', headers=admin_auth_headers)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="elIncompleteOnly"' in html
    assert 'Incomplete only' in html
    assert 'id="elHiringBanner"' in html
    assert 'id="elStatPending"' in html
    assert 'id="efhPromoteModal"' in html

    queue = client.get('/hr/employee-from-hiring', headers=admin_auth_headers)
    assert queue.status_code == 200
    queue_html = queue.get_data(as_text=True)
    assert 'href="/hr/employee-from-hiring" class="hh-nav-item hh-nav-subitem' in queue_html
    assert 'href="/hr/employee-from-hiring" class="hh-nav-item hh-nav-subitem' in html
    assert 'aria-label="Employee List"' in html
    assert 'id="efhPromoteModal"' in queue_html
    assert 'id="efhGrid"' in queue_html
    assert 'id="efhCompany"' in queue_html
    assert 'id="efhIncompleteOnly"' in queue_html
    assert 'Type Emp ID or name' in queue_html
    assert 'id="efhHiringBanner"' in queue_html
    assert 'id="efhStatIncomplete"' in queue_html
    assert 'id="efhDismissModal"' in queue_html
    assert 'id="efhDismissCreate"' in queue_html
    assert 'Create new' in queue_html
    assert 'id="elModalMergeBtn"' in html
