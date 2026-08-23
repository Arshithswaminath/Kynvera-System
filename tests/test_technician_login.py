"""Creating a technician can also create a linked app login."""


def test_create_technician_with_login(client, admin_auth_headers, app):
    response = client.post('/api/admin/technicians', headers=admin_auth_headers, json={
        'employee_id': 'EMP-T1',
        'full_name': 'Ahmed Rashidi',
        'email': 'ahmed.rashidi@example.com',
        'create_login': True,
        'username': 'ahmed.rashidi',
        'password': 'TechPass123',
        'designation': 'HVAC Technician',
    })
    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    assert data.get('success') is True
    assert data.get('login_created') is True
    assert data.get('user', {}).get('username') == 'ahmed.rashidi'
    assert data.get('user', {}).get('designation') == 'technician'
    assert data.get('user', {}).get('access_ticketing') is True
    assert data.get('technician', {}).get('employee_id') == 'EMP-T1'

    listed = client.get('/api/admin/technicians', headers=admin_auth_headers)
    assert listed.status_code == 200
    rows = listed.get_json().get('technicians') or []
    match = next(r for r in rows if r.get('employee_id') == 'EMP-T1')
    assert match.get('has_login') is True
    assert match.get('user_id') == data['user']['id']


def test_create_technician_login_requires_email(client, admin_auth_headers):
    response = client.post('/api/admin/technicians', headers=admin_auth_headers, json={
        'employee_id': 'EMP-T2',
        'full_name': 'No Email Tech',
        'create_login': True,
        'username': 'noemailtech',
    })
    assert response.status_code == 400
    assert 'email' in (response.get_json().get('error') or '').lower()


def test_create_technician_without_login(client, admin_auth_headers, app):
    response = client.post('/api/admin/technicians', headers=admin_auth_headers, json={
        'employee_id': 'EMP-T3',
        'full_name': 'Roster Only',
    })
    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    assert data.get('login_created') is False
    from app.models import User
    with app.app_context():
        assert User.query.filter_by(username='roster.only').first() is None


def test_convert_staff_to_system_user_keeps_details(client, admin_auth_headers, app):
    created = client.post('/api/admin/technicians', headers=admin_auth_headers, json={
        'employee_id': 'EMP-CV1',
        'full_name': 'Demo Tech Team Alpha',
        'email': 'demo.tech.alpha@example.com',
        'phone': '+971-50-000-0000',
        'designation': 'Field Technician',
        'department': 'HVAC',
    })
    assert created.status_code == 201, created.get_json()
    tech_id = created.get_json()['technician']['id']

    converted = client.post(
        f'/api/admin/technicians/{tech_id}/create-login',
        headers=admin_auth_headers,
        json={'username': 'demo.tech.alpha', 'password': 'TechPass123'},
    )
    assert converted.status_code == 200, converted.get_json()
    data = converted.get_json()
    assert data.get('login_created') is True
    user = data.get('user') or {}
    assert user.get('username') == 'demo.tech.alpha'
    assert user.get('full_name') == 'Demo Tech Team Alpha'
    assert user.get('email') == 'demo.tech.alpha@example.com'
    assert user.get('phone') == '+971-50-000-0000'
    assert user.get('job_designation') == 'Field Technician'
    assert user.get('designation') == 'technician'


def test_convert_staff_rejects_duplicate_email(client, admin_auth_headers):
    first = client.post('/api/admin/technicians', headers=admin_auth_headers, json={
        'employee_id': 'EMP-CV2',
        'full_name': 'Already Linked',
        'email': 'already.linked@example.com',
        'create_login': True,
        'username': 'already.linked',
        'password': 'TechPass123',
    })
    assert first.status_code == 201, first.get_json()
    tech_id = first.get_json()['technician']['id']
    again = client.post(
        f'/api/admin/technicians/{tech_id}/create-login',
        headers=admin_auth_headers,
        json={'username': 'already.linked2'},
    )
    assert again.status_code == 409
