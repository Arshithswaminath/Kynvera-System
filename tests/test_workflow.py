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
