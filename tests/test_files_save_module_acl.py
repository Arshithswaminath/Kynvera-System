"""Save-to-Files must enforce source-module ACLs (not only access_files)."""


def _login_headers(client, username, password):
    r = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_files_user_cannot_export_technicians_roster(client, app):
    """access_files alone must not pull admin Team Management (incl. Salary)."""
    from app.models import Technician, User, db

    with app.app_context():
        files_user = User(
            username='files_acl_user',
            email='files_acl@example.com',
            full_name='Files Only',
            role='user',
            is_active=True,
            password_changed=True,
            access_files=True,
            access_hr=False,
        )
        files_user.set_password('FilesPass123!')
        db.session.add(files_user)
        db.session.flush()

        tech = Technician(
            employee_id='EMP-ACL-1',
            full_name='Secret Tech',
            designation='Electrician',
            salary=12500.0,
            status='active',
        )
        db.session.add(tech)
        db.session.commit()

        headers = _login_headers(client, 'files_acl_user', 'FilesPass123!')

        deny_catalog = client.get('/files/api/catalog?module=technicians', headers=headers)
        assert deny_catalog.status_code == 403, deny_catalog.get_json()

        deny_save = client.post(
            '/files/api/save-from-module',
            headers=headers,
            json={'module': 'technicians', 'kinds': ['export']},
        )
        assert deny_save.status_code == 403, deny_save.get_json()

        catalog = client.get('/files/api/catalog', headers=headers)
        assert catalog.status_code == 200
        body = catalog.get_json()
        # success_response may wrap under data
        payload = body.get('data') if isinstance(body.get('data'), dict) else body
        assert 'technicians' not in payload
        assert 'devices' not in payload


def test_hr_user_can_export_manpower_but_not_devices(client, app):
    from app.models import User, db

    with app.app_context():
        hr = User(
            username='hr_files_acl',
            email='hr_files_acl@example.com',
            full_name='HR Files',
            role='user',
            is_active=True,
            password_changed=True,
            access_hr=True,
            access_files=False,
        )
        hr.set_password('HrPass123!')
        db.session.add(hr)
        db.session.commit()

        headers = _login_headers(client, 'hr_files_acl', 'HrPass123!')

        ok_catalog = client.get('/files/api/catalog?module=manpower', headers=headers)
        assert ok_catalog.status_code == 200, ok_catalog.get_json()

        deny_devices = client.post(
            '/files/api/save-from-module',
            headers=headers,
            json={'module': 'devices', 'kinds': ['export']},
        )
        assert deny_devices.status_code == 403, deny_devices.get_json()


def test_procurement_files_user_can_export_procurement(client, app):
    from app.models import User, db

    with app.app_context():
        proc = User(
            username='proc_files_acl',
            email='proc_files_acl@example.com',
            full_name='Proc Files',
            role='user',
            is_active=True,
            password_changed=True,
            access_files=True,
            access_procurement_module=True,
        )
        proc.set_password('ProcPass123!')
        db.session.add(proc)
        db.session.commit()

        headers = _login_headers(client, 'proc_files_acl', 'ProcPass123!')
        ok = client.get('/files/api/catalog?module=procurement', headers=headers)
        assert ok.status_code == 200, ok.get_json()

        deny_tech = client.post(
            '/files/api/save-from-module',
            headers=headers,
            json={'module': 'technicians', 'kinds': ['template']},
        )
        assert deny_tech.status_code == 403
