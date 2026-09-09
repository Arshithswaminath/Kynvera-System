"""Hiring trackers are an HR submodule gated by access_hiring."""

from tests.factories import make_user


def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


TRACKER_PAGES = (
    '/hr/hiring',
    '/hr/hiring/offer-letters',
    '/hr/leave-tracker',
    '/hr/manpower-tracker',
    '/hr/employee-list',
    '/hr/employee-from-hiring',
)


def test_hr_without_hiring_cannot_open_trackers(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=False)
        username = user.username
    headers = _login(client, username, pwd)
    for path in TRACKER_PAGES:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.status_code, response.get_json())


def test_hr_with_hiring_can_open_trackers(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=True)
        username = user.username
    headers = _login(client, username, pwd)
    for path in TRACKER_PAGES:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.status_code, response.get_data(as_text=True)[:400])


def test_hr_dashboard_omits_hiring_cards_without_flag(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=False)
        username = user.username
    headers = _login(client, username, pwd)
    response = client.get('/hr/', headers=headers)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Hiring Documents' not in html
    assert 'Letters of Intent' not in html
    assert 'Manpower Tracker' not in html
    assert 'Employee List' not in html
    assert 'Employee from hiring' not in html
    assert 'Leave Application' in html


def test_hr_dashboard_shows_hiring_cards_with_flag(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=True)
        username = user.username
    headers = _login(client, username, pwd)
    response = client.get('/hr/', headers=headers)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Hiring Documents' in html
    assert 'Letters of Intent' in html
    assert 'Leave Tracker' in html
    assert 'Employee List' in html
    assert 'Staff — From hiring' not in html
    assert 'class="module-sublink"' not in html
    assert 'Manpower Tracker' in html
    assert 'Leave Application' in html


def test_employee_list_excel_template_and_export(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=True)
        username = user.username
    headers = _login(client, username, pwd)
    tmpl = client.get('/hr/api/employee-list/template', headers=headers)
    assert tmpl.status_code == 200, tmpl.get_data(as_text=True)[:400]
    assert 'spreadsheet' in (tmpl.content_type or '')
    exported = client.get('/hr/api/employee-list/export', headers=headers)
    assert exported.status_code == 200, exported.get_data(as_text=True)[:400]
    html = client.get('/hr/employee-list', headers=headers).get_data(as_text=True)
    assert 'Add employee' in html
    assert 'id="elTemplateBtn"' in html
    assert 'id="elExportBtn"' in html
    assert 'id="elImportBtn"' in html
    assert 'id="elEditBtn"' in html
    assert 'id="elDeleteBtn"' in html
    assert 'Remove from list' in html
    assert 'id="elAddCompany"' in html
    assert 'id="elIncompleteOnly"' in html
    assert 'list="elCompanySuggestions"' not in html


def test_employee_list_can_edit_and_soft_delete(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=True)
        username = user.username
    headers = _login(client, username, pwd)
    created = client.post(
        '/hr/api/leave-tracker/employees',
        json={
            'emp_id': 'EL-EDIT-1',
            'full_name': 'Edit Delete Person',
            'designation': 'Office Boy',
            'company': 'Kynvera',
            'annual_entitlement': 30,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.get_data(as_text=True)[:400]
    emp = (created.get_json() or {}).get('employee') or {}
    emp_pk = emp.get('id')
    assert emp_pk

    patched = client.patch(
        f'/hr/api/leave-tracker/employees/{emp_pk}',
        json={
            'emp_id': 'EL-EDIT-2',
            'full_name': 'Edited Person',
            'designation': 'Coordinator',
            'company': 'Tourism',
        },
        headers=headers,
    )
    assert patched.status_code == 200, patched.get_data(as_text=True)[:400]
    updated = (patched.get_json() or {}).get('employee') or {}
    assert updated.get('emp_id') == 'EL-EDIT-2'
    assert updated.get('full_name') == 'Edited Person'
    assert updated.get('designation') == 'Coordinator'
    assert updated.get('company') == 'Tourism'

    custom = client.post(
        '/hr/api/leave-tracker/employees',
        json={
            'emp_id': 'EL-CO-1',
            'full_name': 'Custom Company Person',
            'designation': 'Coordinator',
            'company': 'Ajman Tourism',
        },
        headers=headers,
    )
    assert custom.status_code == 201, custom.get_data(as_text=True)[:400]
    assert ((custom.get_json() or {}).get('employee') or {}).get('company') == 'Ajman Tourism'

    deleted = client.delete(f'/hr/api/leave-tracker/employees/{emp_pk}', headers=headers)
    assert deleted.status_code == 200, deleted.get_data(as_text=True)[:400]
    assert (deleted.get_json() or {}).get('deleted') is True

    listed = client.get('/hr/api/leave-tracker/employees', headers=headers)
    assert listed.status_code == 200
    ids = {row.get('emp_id') for row in ((listed.get_json() or {}).get('employees') or [])}
    assert 'EL-EDIT-2' not in ids
    assert 'EL-EDIT-1' not in ids

    restored = client.post(
        '/hr/api/leave-tracker/employees',
        json={
            'emp_id': 'EL-EDIT-2',
            'full_name': 'sample',
            'company': 'Injaaz',
        },
        headers=headers,
    )
    assert restored.status_code == 200, restored.get_data(as_text=True)[:400]
    assert ((restored.get_json() or {}).get('employee') or {}).get('full_name') == 'sample'
    listed_again = client.get('/hr/api/leave-tracker/employees', headers=headers)
    again_ids = {row.get('emp_id') for row in ((listed_again.get_json() or {}).get('employees') or [])}
    assert 'EL-EDIT-2' in again_ids
