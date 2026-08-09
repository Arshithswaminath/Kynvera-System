"""Procurement material endpoints must not touch non-procurement submissions."""
from datetime import datetime, timezone


def _login_headers(client, username, password):
    r = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_delete_material_does_not_delete_other_module_submissions(client, app):
    from app.models import db, User, Submission

    with app.app_context():
        proc = User(
            username='proc_scope_user',
            email='proc_scope@example.com',
            full_name='Proc User',
            role='user',
            is_active=True,
            password_changed=True,
            access_procurement_module=True,
        )
        proc.set_password('ProcPass123!')
        db.session.add(proc)
        db.session.flush()

        foreign = Submission(
            submission_id='HR-LEAVE-SCOPE1',
            module_type='hr_leave_application',
            site_name='Leave Request',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'employee_name': 'Victim'},
            workflow_status='approved',
            status='completed',
            user_id=proc.id,
            supervisor_id=proc.id,
        )
        own = Submission(
            submission_id='PROC-MAT-SCOPE1',
            module_type='procurement_material',
            site_name='Bolt',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'material_name': 'Bolt', 'property': 'Unassigned'},
            workflow_status='submitted',
            status='submitted',
            user_id=proc.id,
            supervisor_id=proc.id,
        )
        db.session.add_all([foreign, own])
        db.session.commit()

        headers = _login_headers(client, 'proc_scope_user', 'ProcPass123!')

        deny = client.delete('/procurement/api/materials/HR-LEAVE-SCOPE1', headers=headers)
        assert deny.status_code == 404
        assert Submission.query.filter_by(submission_id='HR-LEAVE-SCOPE1').first() is not None

        ok = client.delete('/procurement/api/materials/PROC-MAT-SCOPE1', headers=headers)
        assert ok.status_code == 200
        assert Submission.query.filter_by(submission_id='PROC-MAT-SCOPE1').first() is None
        assert Submission.query.filter_by(submission_id='HR-LEAVE-SCOPE1').first() is not None


def test_assign_property_does_not_mutate_other_module_submissions(client, app):
    from app.models import db, User, Submission

    with app.app_context():
        proc = User(
            username='proc_assign_user',
            email='proc_assign@example.com',
            full_name='Proc Assign',
            role='user',
            is_active=True,
            password_changed=True,
            access_procurement_module=True,
        )
        proc.set_password('ProcPass123!')
        db.session.add(proc)
        db.session.flush()

        foreign = Submission(
            submission_id='CIVIL-SCOPE1',
            module_type='civil',
            site_name='Site A',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'notes': 'keep me', 'property': 'Original'},
            workflow_status='submitted',
            status='submitted',
            user_id=proc.id,
            supervisor_id=proc.id,
        )
        db.session.add(foreign)
        db.session.commit()

        headers = _login_headers(client, 'proc_assign_user', 'ProcPass123!')
        resp = client.post(
            '/procurement/api/material-assign-property',
            headers=headers,
            json={'material_id': 'CIVIL-SCOPE1', 'property': 'Hacked Property'},
        )
        assert resp.status_code == 404

        refreshed = Submission.query.filter_by(submission_id='CIVIL-SCOPE1').first()
        assert refreshed is not None
        assert refreshed.form_data.get('property') == 'Original'
        assert refreshed.form_data.get('notes') == 'keep me'
