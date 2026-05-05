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


class TestWorkflowPermissions:
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
