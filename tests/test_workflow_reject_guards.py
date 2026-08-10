"""Shared workflow reject endpoint must not undo finalized or out-of-stage work."""
from datetime import datetime, timezone


def _login_headers(client, username, password):
    r = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.get_json()
    token = r.get_json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _make_user(db, *, username, email, designation, **extra):
    from app.models import User

    user = User(
        username=username,
        email=email,
        full_name=username,
        role='user',
        designation=designation,
        is_active=True,
        password_changed=True,
        access_hvac=True,
        access_civil=True,
        **extra,
    )
    user.set_password('RejectPass123!')
    db.session.add(user)
    db.session.flush()
    return user


def test_reject_blocks_completed_inspection(client, app):
    from app.models import db, Submission

    with app.app_context():
        om = _make_user(
            db,
            username='om_reject_done',
            email='om_reject_done@example.com',
            designation='operations_manager',
        )
        row = Submission(
            submission_id='INSP-REJECT-DONE1',
            module_type='civil',
            site_name='Finished Site',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'items': []},
            workflow_status='completed',
            status='completed',
            user_id=om.id,
            supervisor_id=om.id,
        )
        db.session.add(row)
        db.session.commit()

        headers = _login_headers(client, 'om_reject_done', 'RejectPass123!')
        resp = client.post(
            '/api/workflow/submissions/INSP-REJECT-DONE1/reject',
            headers=headers,
            json={'reason': 'undo final approval'},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False
        assert body.get('error_code') == 'INVALID_STATUS'

        refreshed = Submission.query.filter_by(submission_id='INSP-REJECT-DONE1').first()
        assert refreshed is not None
        assert refreshed.workflow_status == 'completed'


def test_reject_blocks_wrong_stage_designation(client, app):
    from app.models import db, Submission

    with app.app_context():
        supervisor = _make_user(
            db,
            username='sup_reject_stage',
            email='sup_reject_stage@example.com',
            designation='supervisor',
        )
        row = Submission(
            submission_id='INSP-REJECT-STAGE1',
            module_type='hvac_mep',
            site_name='GM Queue',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'items': []},
            workflow_status='general_manager_review',
            status='submitted',
            user_id=supervisor.id,
            supervisor_id=supervisor.id,
        )
        db.session.add(row)
        db.session.commit()

        headers = _login_headers(client, 'sup_reject_stage', 'RejectPass123!')
        resp = client.post(
            '/api/workflow/submissions/INSP-REJECT-STAGE1/reject',
            headers=headers,
            json={'reason': 'supervisor bypass'},
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body.get('error_code') == 'INVALID_STAGE'

        refreshed = Submission.query.filter_by(submission_id='INSP-REJECT-STAGE1').first()
        assert refreshed.workflow_status == 'general_manager_review'


def test_reject_blocks_hr_module_submissions(client, app):
    from app.models import db, Submission

    with app.app_context():
        om = _make_user(
            db,
            username='om_reject_hr',
            email='om_reject_hr@example.com',
            designation='operations_manager',
        )
        row = Submission(
            submission_id='HR-REJECT-CROSS1',
            module_type='hr_leave_application',
            site_name='Leave',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'employee_name': 'Victim'},
            workflow_status='approved',
            status='completed',
            user_id=om.id,
            supervisor_id=om.id,
        )
        db.session.add(row)
        db.session.commit()

        headers = _login_headers(client, 'om_reject_hr', 'RejectPass123!')
        resp = client.post(
            '/api/workflow/submissions/HR-REJECT-CROSS1/reject',
            headers=headers,
            json={'reason': 'cross-module undo'},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('error_code') == 'INVALID_MODULE'

        refreshed = Submission.query.filter_by(submission_id='HR-REJECT-CROSS1').first()
        assert refreshed.workflow_status == 'approved'


def test_reject_allows_om_at_own_stage(client, app):
    from app.models import db, Submission

    with app.app_context():
        om = _make_user(
            db,
            username='om_reject_ok',
            email='om_reject_ok@example.com',
            designation='operations_manager',
        )
        row = Submission(
            submission_id='INSP-REJECT-OK1',
            module_type='civil',
            site_name='Active Site',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'items': []},
            workflow_status='operations_manager_review',
            status='submitted',
            user_id=om.id,
            supervisor_id=om.id,
        )
        db.session.add(row)
        db.session.commit()

        headers = _login_headers(client, 'om_reject_ok', 'RejectPass123!')
        resp = client.post(
            '/api/workflow/submissions/INSP-REJECT-OK1/reject',
            headers=headers,
            json={'reason': 'needs rework'},
        )
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body.get('success') is True

        refreshed = Submission.query.filter_by(submission_id='INSP-REJECT-OK1').first()
        assert refreshed.workflow_status == 'rejected'
        assert refreshed.rejection_stage == 'operations_manager_review'
        assert refreshed.rejection_reason == 'needs rework'
