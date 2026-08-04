"""
Regression tests for critical auth / HR correctness bugs found outside ticketing.
"""
import pytest


class TestRegisterPasswordIsolation:
    """Public registration must not leak the org-wide ADMIN_RESET_PASSWORD."""

    def test_register_page_does_not_embed_reset_secret(self, client, app, monkeypatch):
        monkeypatch.setenv('ADMIN_RESET_PASSWORD', 'OrgWideResetSecret9')
        with app.app_context():
            response = client.get('/register')
            assert response.status_code == 200
            body = response.get_data(as_text=True)
            assert 'OrgWideResetSecret9' not in body
            assert 'ChangeMeNow!@#' not in body

    def test_register_assigns_unique_password_not_shared_reset(self, client, app, monkeypatch):
        from common.password_admin import get_default_registration_password
        from app.models import User

        monkeypatch.setenv('ADMIN_RESET_PASSWORD', 'OrgWideResetSecret9')
        shared = get_default_registration_password()
        assert shared == 'OrgWideResetSecret9'

        with app.app_context():
            r1 = client.post('/api/auth/register', json={
                'first_name': 'Ada',
                'last_name': 'One',
                'email': 'ada.one@example.com',
                'mobile_number': '+971501111111',
                'project_name': 'Tower A',
                'job_designation': 'Technician',
                'employment_start_date': '2024-01-01',
            })
            r2 = client.post('/api/auth/register', json={
                'first_name': 'Bob',
                'last_name': 'Two',
                'email': 'bob.two@example.com',
                'mobile_number': '+971502222222',
                'project_name': 'Tower B',
                'job_designation': 'Technician',
                'employment_start_date': '2024-02-01',
            })
            assert r1.status_code == 201
            assert r2.status_code == 201
            pw1 = r1.get_json()['default_password']
            pw2 = r2.get_json()['default_password']
            assert pw1 and pw2
            assert pw1 != shared
            assert pw2 != shared
            assert pw1 != pw2

            u1 = User.query.filter_by(email='ada.one@example.com').first()
            u2 = User.query.filter_by(email='bob.two@example.com').first()
            assert u1.check_password(pw1)
            assert u2.check_password(pw2)
            assert not u1.check_password(shared)


class TestAccessHrPrivilegeEscalation:
    """Bare access_hr must not grant HR approve / hiring-doc powers."""

    def _mk_user(self, app, *, username, email, access_hr=False, designation=None):
        from app.models import db, User
        with app.app_context():
            u = User(
                username=username,
                email=email,
                full_name=username,
                role='user',
                designation=designation,
                access_hr=access_hr,
                is_active=True,
                password_changed=True,
            )
            u.set_password('TestPass123')
            db.session.add(u)
            db.session.commit()
            return u.id

    def _token_for(self, client, username):
        r = client.post('/api/auth/login', json={
            'username': username,
            'password': 'TestPass123',
        })
        assert r.status_code == 200
        return r.get_json()['access_token']

    def test_access_hr_cannot_hr_approve(self, client, app):
        from app.models import db, Submission
        from common.datetime_utils import utc_now_naive

        uid = self._mk_user(
            app, username='hrflag', email='hrflag@example.com', access_hr=True
        )
        with app.app_context():
            sub = Submission(
                submission_id='HR-CRIT-APPROVE-1',
                user_id=uid,
                module_type='hr_leave_application',
                status='submitted',
                workflow_status='hr_review',
                form_data={'employee_name': 'Someone'},
                created_at=utc_now_naive(),
            )
            db.session.add(sub)
            db.session.commit()

        token = self._token_for(client, 'hrflag')
        resp = client.post(
            '/hr/api/hr-approve/HR-CRIT-APPROVE-1',
            json={'comments': 'ok', 'signature': 'data:image/png;base64,aaa'},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 403

    def test_access_hr_cannot_manage_hiring_candidates(self, client, app):
        self._mk_user(
            app, username='hrflag2', email='hrflag2@example.com', access_hr=True
        )
        token = self._token_for(client, 'hrflag2')
        resp = client.get(
            '/hr/api/hiring/candidates',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 403

    def test_hr_manager_can_still_approve(self, client, app):
        from app.models import db, Submission
        from common.datetime_utils import utc_now_naive

        uid = self._mk_user(
            app,
            username='hrmgr',
            email='hrmgr@example.com',
            access_hr=True,
            designation='hr_manager',
        )
        with app.app_context():
            sub = Submission(
                submission_id='HR-CRIT-APPROVE-2',
                user_id=uid,
                module_type='hr_leave_application',
                status='submitted',
                workflow_status='hr_review',
                form_data={'employee_name': 'Someone'},
                created_at=utc_now_naive(),
            )
            db.session.add(sub)
            db.session.commit()

        token = self._token_for(client, 'hrmgr')
        resp = client.post(
            '/hr/api/hr-approve/HR-CRIT-APPROVE-2',
            json={'comments': 'ok', 'signature': 'data:image/png;base64,aaa'},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 200
        with app.app_context():
            sub = Submission.query.filter_by(submission_id='HR-CRIT-APPROVE-2').first()
            assert sub.workflow_status == 'gm_review'


class TestHrRejectStatusGuards:
    """Reject endpoints must not undo approved / wrong-stage submissions."""

    def _mk_gm_and_hr(self, app, suffix: str):
        from app.models import db, User
        with app.app_context():
            hr = User(
                username=f'hrrej{suffix}',
                email=f'hrrej{suffix}@example.com',
                full_name='HR Rej',
                role='user',
                designation='hr_manager',
                access_hr=True,
                is_active=True,
                password_changed=True,
            )
            hr.set_password('TestPass123')
            gm = User(
                username=f'gmrej{suffix}',
                email=f'gmrej{suffix}@example.com',
                full_name='GM Rej',
                role='user',
                designation='general_manager',
                is_active=True,
                password_changed=True,
            )
            gm.set_password('TestPass123')
            db.session.add_all([hr, gm])
            db.session.commit()
            return hr.id, gm.id, hr.username, gm.username

    def _token(self, client, username):
        r = client.post('/api/auth/login', json={
            'username': username, 'password': 'TestPass123',
        })
        assert r.status_code == 200
        return r.get_json()['access_token']

    def test_hr_reject_cannot_undo_approved(self, client, app):
        from app.models import db, Submission
        from common.datetime_utils import utc_now_naive

        hr_id, _, hr_user, _ = self._mk_gm_and_hr(app, '1')
        with app.app_context():
            sub = Submission(
                submission_id='HR-CRIT-REJ-1',
                user_id=hr_id,
                module_type='hr_leave_application',
                status='completed',
                workflow_status='approved',
                form_data={'employee_name': 'Approved Emp'},
                created_at=utc_now_naive(),
            )
            db.session.add(sub)
            db.session.commit()

        token = self._token(client, hr_user)
        resp = client.post(
            '/hr/api/hr-reject/HR-CRIT-REJ-1',
            json={'reason': 'oops'},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 400
        with app.app_context():
            sub = Submission.query.filter_by(submission_id='HR-CRIT-REJ-1').first()
            assert sub.workflow_status == 'approved'
            assert sub.status == 'completed'

    def test_gm_reject_cannot_undo_approved(self, client, app):
        from app.models import db, Submission
        from common.datetime_utils import utc_now_naive

        hr_id, _, _, gm_user = self._mk_gm_and_hr(app, '2')
        with app.app_context():
            sub = Submission(
                submission_id='HR-CRIT-REJ-2',
                user_id=hr_id,
                module_type='hr_leave_application',
                status='completed',
                workflow_status='approved',
                form_data={'employee_name': 'Approved Emp'},
                created_at=utc_now_naive(),
            )
            db.session.add(sub)
            db.session.commit()

        token = self._token(client, gm_user)
        resp = client.post(
            '/hr/api/gm-reject/HR-CRIT-REJ-2',
            json={'reason': 'oops'},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 400
        with app.app_context():
            sub = Submission.query.filter_by(submission_id='HR-CRIT-REJ-2').first()
            assert sub.workflow_status == 'approved'
