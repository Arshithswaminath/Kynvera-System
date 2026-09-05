"""
Workflow API Tests
Tests for the 5-stage approval workflow system
"""
import pytest


class TestGetPendingSubmissions:
    """Test pending submissions endpoint"""
    
    def test_get_pending_as_admin(self, client, admin_auth_headers, sample_submission, app):
        """Test admin can see all pending submissions"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/pending',
                                  headers=admin_auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'submissions' in data
            assert isinstance(data['submissions'], list)
    
    def test_get_pending_as_supervisor(self, client, supervisor_auth_headers, app):
        """Test supervisor can see their pending submissions"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/pending',
                                  headers=supervisor_auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
    
    def test_get_pending_no_auth(self, client, app):
        """Test cannot get pending without authentication"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/pending')
            
            assert response.status_code == 401


class TestGetMyTrail:
    """GET /api/workflow/submissions/my-trail — pending + reviewed for current user"""

    def test_my_trail_as_admin(self, client, admin_auth_headers, app):
        with app.app_context():
            response = client.get(
                '/api/workflow/submissions/my-trail',
                headers=admin_auth_headers,
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data.get('success') is True
            assert 'pending' in data
            assert 'reviewed' in data
            assert isinstance(data['pending'], list)
            assert isinstance(data['reviewed'], list)

    def test_my_trail_no_auth(self, client, app):
        with app.app_context():
            response = client.get('/api/workflow/submissions/my-trail')
            assert response.status_code == 401

    def test_my_trail_supervisor_reviewed(
        self, client, supervisor_auth_headers, supervisor_user, app
    ):
        """Supervisor signed-off inspection forms appear under reviewed, not pending."""
        from app.models import db, Submission
        from common.utils import random_id
        from common.datetime_utils import utc_now_naive

        with app.app_context():
            tech = supervisor_user
            signed = Submission(
                submission_id=random_id('sub'),
                module_type='hvac_mep',
                site_name='Signed Site',
                form_data={'items': []},
                workflow_status='operations_manager_review',
                user_id=tech.id,
                supervisor_id=supervisor_user.id,
                supervisor_reviewed_at=utc_now_naive(),
            )
            pending_row = Submission(
                submission_id=random_id('sub'),
                module_type='hvac_mep',
                site_name='Pending Site',
                form_data={'items': []},
                workflow_status='supervisor_review',
                user_id=tech.id,
                supervisor_id=supervisor_user.id,
            )
            db.session.add_all([signed, pending_row])
            db.session.commit()

            try:
                response = client.get(
                    '/api/workflow/submissions/my-trail',
                    headers=supervisor_auth_headers,
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data.get('success') is True
                reviewed_ids = {s['submission_id'] for s in data.get('reviewed', [])}
                pending_ids = {s['submission_id'] for s in data.get('pending', [])}
                assert signed.submission_id in reviewed_ids
                assert signed.submission_id not in pending_ids
                assert pending_row.submission_id in pending_ids
            finally:
                db.session.delete(signed)
                db.session.delete(pending_row)
                db.session.commit()

    def test_gm_reporting_manager_sign_appears_in_signed_off(self, client, app):
        """GM who signs the RM chain step must land in Signed off, not vanish."""
        import uuid
        from app.models import db, User

        sig = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        tag = uuid.uuid4().hex[:6]
        created_ids = []
        sid = None

        def _mk(username, designation, **kw):
            u = User(
                username=username,
                email=f"{username}@example.com",
                full_name=username.replace("_", " ").title(),
                role="user",
                designation=designation,
                is_active=True,
                password_changed=True,
                **kw,
            )
            u.set_password("TestPass123")
            db.session.add(u)
            db.session.flush()
            created_ids.append(u.id)
            return u

        with app.app_context():
            gm = _mk(f"gm_rm_{tag}", "general_manager")
            emp = _mk(f"emp_rm_{tag}", "employee", reporting_manager_id=gm.id)
            db.session.commit()
            emp_name, gm_name = emp.username, gm.username

        def _login(username):
            r = client.post("/api/auth/login", json={"username": username, "password": "TestPass123"})
            assert r.status_code == 200, r.get_json()
            return {"Authorization": f"Bearer {r.get_json()['access_token']}"}

        try:
            sub_r = client.post(
                "/hr/api/submit",
                json={
                    "form_type": "visa_renewal",
                    "employee_name": "Trail Tester",
                    "employee_signature": sig,
                },
                headers=_login(emp_name),
            )
            assert sub_r.status_code == 200, sub_r.get_json()
            sid = sub_r.get_json()["submission_id"]

            sign_r = client.post(
                f"/hr/api/mgmt-signoff/{sid}/sign",
                json={"signature": sig},
                headers=_login(gm_name),
            )
            assert sign_r.status_code == 200, sign_r.get_json()

            trail = client.get("/api/workflow/submissions/my-trail", headers=_login(gm_name))
            assert trail.status_code == 200, trail.get_json()
            data = trail.get_json()
            pending_ids = {s["submission_id"] for s in data.get("pending") or []}
            reviewed_ids = {s["submission_id"] for s in data.get("reviewed") or []}
            assert sid not in pending_ids
            assert sid in reviewed_ids
        finally:
            with app.app_context():
                from app.models import Submission
                if sid:
                    Submission.query.filter_by(submission_id=sid).delete()
                for uid in created_ids:
                    obj = db.session.get(User, uid)
                    if obj is not None:
                        db.session.delete(obj)
                db.session.commit()


class TestGetHistorySubmissions:
    """Test history submissions endpoint"""
    
    def test_get_history_as_admin(self, client, admin_auth_headers, sample_submission, app):
        """Test admin can see all history"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/history',
                                  headers=admin_auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'submissions' in data
    
    def test_get_history_as_supervisor(self, client, supervisor_auth_headers, sample_submission, app):
        """Test supervisor can see their history"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/history',
                                  headers=supervisor_auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True


class TestGetSubmissionDetail:
    """Test submission detail endpoint"""
    
    def test_get_detail_as_admin(self, client, admin_auth_headers, sample_submission, app):
        """Test admin can see submission details"""
        with app.app_context():
            response = client.get(f'/api/workflow/submissions/{sample_submission.submission_id}',
                                  headers=admin_auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'submission_id' in data
    
    def test_get_detail_not_found(self, client, admin_auth_headers, app):
        """Test 404 for non-existent submission"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/nonexistent_id',
                                  headers=admin_auth_headers)
            
            assert response.status_code == 404
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'NOT_FOUND'


class TestWorkflowTransitions:
    """Test workflow state transitions"""
    
    def test_submission_initial_state(self, sample_submission, app):
        """Test submission starts in submitted state"""
        with app.app_context():
            assert sample_submission.workflow_status == 'submitted'
    
    def test_submission_has_user_relation(self, sample_submission, app):
        """Test submission has user relationship"""
        with app.app_context():
            assert sample_submission.user_id is not None
            assert sample_submission.supervisor_id is not None


class TestMySubmissions:
    """Test my-submissions endpoint"""
    
    def test_get_my_submissions(self, client, supervisor_auth_headers, sample_submission, app):
        """Test user can get their own submissions"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/my-submissions',
                                  headers=supervisor_auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert 'submissions' in data

    def test_get_my_submissions_as_hr_submitter_without_module_flag(
        self, client, auth_headers, standard_user, app
    ):
        """Any submitter sees their own HR forms — no access_submitted_forms flag required."""
        from app.models import Submission, db

        with app.app_context():
            sub = Submission(
                submission_id='hr-pytest-submitter-own',
                user_id=standard_user.id,
                module_type='hr_leave_application',
                status='submitted',
                workflow_status='hr_review',
                form_data={'employee_name': 'Test User'},
            )
            db.session.add(sub)
            db.session.commit()

            response = client.get(
                '/api/workflow/submissions/my-submissions?scope=hr',
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            ids = [s['submission_id'] for s in data.get('submissions', [])]
            assert 'hr-pytest-submitter-own' in ids

    def test_admin_sees_all_hr_submissions(
        self, client, admin_auth_headers, standard_user, app
    ):
        """Admin on scope=hr sees every user's HR submissions, not only their own."""
        from app.models import Submission, db

        with app.app_context():
            sub = Submission(
                submission_id='hr-pytest-other-user',
                user_id=standard_user.id,
                module_type='hr_leave_application',
                status='submitted',
                workflow_status='hr_review',
                form_data={'employee_name': 'Other User'},
            )
            db.session.add(sub)
            db.session.commit()

            response = client.get(
                '/api/workflow/submissions/my-submissions?scope=hr',
                headers=admin_auth_headers,
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert data.get('list_scope') == 'all'
            assert data.get('org_wide') is True
            ids = [s['submission_id'] for s in data.get('submissions', [])]
            assert 'hr-pytest-other-user' in ids
            assert isinstance(data.get('live_activity_feed'), list)

    def test_qhsi_forms_listed_on_submitted_forms_hidden_from_pending(
        self, client, admin_auth_headers, standard_user, app
    ):
        """QHSE records appear on Submitted Forms so they can be viewed; pending queue still hides them."""
        from app.models import Submission, db

        with app.app_context():
            db.session.add(Submission(
                submission_id='QHSI-PYTEST-STAFF',
                user_id=standard_user.id,
                module_type='qhsi_staff_compliance',
                site_name='Marina Towers',
                status='submitted',
                workflow_status='operations_manager_review',
                form_data={'project_name': 'Marina Towers'},
            ))
            db.session.add(Submission(
                submission_id='QHSI-PYTEST-INSP',
                user_id=standard_user.id,
                module_type='qhsi_inspection',
                site_name='Marina Towers',
                status='submitted',
                workflow_status='operations_manager_review',
                form_data={'project_name': 'Marina Towers'},
            ))
            db.session.commit()

            listed = client.get(
                '/api/workflow/submissions/my-submissions',
                headers=admin_auth_headers,
            )
            assert listed.status_code == 200
            listed_data = listed.get_json()
            listed_ids = [s['submission_id'] for s in listed_data.get('submissions', [])]
            assert 'QHSI-PYTEST-STAFF' in listed_ids
            assert 'QHSI-PYTEST-INSP' in listed_ids
            names = {
                s['submission_id']: s.get('module_name')
                for s in listed_data.get('submissions', [])
            }
            assert names['QHSI-PYTEST-STAFF'] == 'QHSI Staff Compliance'
            assert names['QHSI-PYTEST-INSP'] == 'QHSI Inspection'

            insp_page = client.get(
                '/qhsi/inspection?edit=QHSI-PYTEST-INSP',
                headers=admin_auth_headers,
            )
            assert insp_page.status_code == 200
            staff_page = client.get(
                '/qhsi/staff-compliance?edit=QHSI-PYTEST-STAFF',
                headers=admin_auth_headers,
            )
            assert staff_page.status_code == 200

            pending = client.get(
                '/api/workflow/submissions/pending',
                headers=admin_auth_headers,
            )
            assert pending.status_code == 200
            pending_ids = [
                s['submission_id'] for s in pending.get_json().get('submissions', [])
            ]
            assert 'QHSI-PYTEST-STAFF' not in pending_ids
            assert 'QHSI-PYTEST-INSP' not in pending_ids

    def test_nested_leave_form_data_is_viewable(
        self, client, admin_auth_headers, admin_user, app
    ):
        """Legacy smoke-test shape (fields under form_data.data) still prints and hydrates."""
        from app.models import Submission, db

        with app.app_context():
            sid = 'HR-LEAVE-NESTED-PYTEST'
            db.session.add(Submission(
                submission_id=sid,
                user_id=admin_user.id,
                module_type='hr_leave_application',
                site_name='System Administrator',
                status='submitted',
                workflow_status='hr_review',
                form_data={
                    'form_type': 'leave_application',
                    'submitted_by_name': 'System Administrator',
                    'data': {
                        'employee_name': 'Smoke Test User',
                        'employee_id': 'SMOKE-001',
                        'leave_type': 'Annual',
                        'from_date': '2026-08-10',
                        'to_date': '2026-08-12',
                        'reason': 'Module functional smoke',
                        'number_of_days': 3,
                    },
                },
            ))
            db.session.commit()

            detail = client.get(
                f'/api/workflow/submissions/{sid}',
                headers=admin_auth_headers,
            )
            assert detail.status_code == 200
            fd = detail.get_json().get('form_data') or {}
            assert fd.get('employee_name') == 'Smoke Test User'
            assert fd.get('first_day_of_leave') == '2026-08-10'
            assert fd.get('last_day_of_leave') == '2026-08-12'
            assert fd.get('total_days_requested') == 3
            assert fd.get('leave_type') == 'annual'

            printed = client.get(f'/hr/print/{sid}', headers=admin_auth_headers)
            assert printed.status_code == 200
            body = printed.get_data(as_text=True)
            assert 'Smoke Test User' in body
            assert 'SMOKE-001' in body

            form_page = client.get(
                f'/hr/leave-application-form?edit={sid}',
                headers=admin_auth_headers,
            )
            assert form_page.status_code == 200

            pdf = client.get(f'/hr/download-pdf/{sid}', headers=admin_auth_headers)
            assert pdf.status_code == 200
            assert pdf.headers.get('Content-Type', '').startswith('application/pdf')

    def test_inspection_hero_count_matches_my_submissions(
        self, client, app, admin_user, supervisor_user
    ):
        """Inspection hero 'Forms submitted' must match scope=inspection my-submissions count."""
        from app.models import Submission, User, db
        from common.utils import random_id

        with app.app_context():
            tech = User(
                username='techhero',
                email='techhero@example.com',
                full_name='Tech Hero',
                role='user',
                designation='technician',
                is_active=True,
                password_changed=True,
                access_hvac=True,
            )
            tech.set_password('TechPass123')
            db.session.add(tech)
            db.session.flush()

            own_ids = []
            for _ in range(2):
                sid = random_id('sub')
                own_ids.append(sid)
                db.session.add(Submission(
                    submission_id=sid,
                    module_type='hvac_mep',
                    site_name='Tech Site',
                    form_data={'items': []},
                    workflow_status='operations_manager_review',
                    status='submitted',
                    user_id=tech.id,
                ))

            other_id = random_id('sub')
            db.session.add(Submission(
                submission_id=other_id,
                module_type='hvac_mep',
                site_name='Admin Site',
                form_data={'items': []},
                workflow_status='operations_manager_review',
                status='submitted',
                user_id=admin_user.id,
            ))
            db.session.commit()

            login = client.post('/api/auth/login', json={
                'username': 'techhero',
                'password': 'TechPass123',
            })
            token = login.get_json()['access_token']
            headers = {'Authorization': f'Bearer {token}'}

            stats = client.get('/api/workflow/inspection-dashboard-stats', headers=headers)
            assert stats.status_code == 200
            hero = stats.get_json()
            hero_count = int(hero['hero_metrics'][0]['value'])
            assert hero['submitted'] == 2
            assert hero['pending'] == 2
            assert hero['approved'] == 0
            assert hero['total'] == 2

            listing = client.get(
                '/api/workflow/submissions/my-submissions?scope=inspection',
                headers=headers,
            )
            assert listing.status_code == 200
            list_ids = [s['submission_id'] for s in listing.get_json().get('submissions', [])]

            assert hero_count == len(list_ids) == 2
            assert set(list_ids) == set(own_ids)
            assert other_id not in list_ids

            db.session.delete(Submission.query.filter_by(submission_id=other_id).first())
            for sid in own_ids:
                db.session.delete(Submission.query.filter_by(submission_id=sid).first())
            db.session.delete(User.query.filter_by(username='techhero').first())
            db.session.commit()
    """Test workflow permission checks"""
    
    def test_regular_user_cannot_approve(self, client, auth_headers, sample_submission, app):
        """Test regular user cannot approve submissions"""
        with app.app_context():
            response = client.post(
                f'/api/workflow/submissions/{sample_submission.submission_id}/approve-ops-manager',
                headers=auth_headers,
                json={'comments': 'Test approval'}
            )
            
            # Should fail - regular user doesn't have operations_manager designation
            assert response.status_code in [403, 404]


class TestWorkflowErrorResponses:
    """Test workflow error response formats"""
    
    def test_not_found_error_format(self, client, admin_auth_headers, app):
        """Test not found error has correct format"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/nonexistent',
                                  headers=admin_auth_headers)
            
            data = response.get_json()
            assert 'success' in data
            assert data['success'] is False
            assert 'error' in data
            assert 'error_code' in data
    
    def test_unauthorized_error_format(self, client, app):
        """Test unauthorized error response"""
        with app.app_context():
            response = client.get('/api/workflow/submissions/pending')
            
            assert response.status_code == 401
