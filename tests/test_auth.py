"""
Authentication API Tests
Tests for login, register, token refresh, and password change endpoints
"""
import pytest


class TestLogin:
    """Test login endpoint"""
    
    def test_login_success(self, client, standard_user, app):
        """Test successful login"""
        with app.app_context():
            response = client.post('/api/auth/login', json={
                'username': 'testuser',
                'password': 'TestPass123'
            })
            
            assert response.status_code == 200
            data = response.get_json()
            assert 'access_token' in data
            assert 'refresh_token' in data
            assert 'user' in data
            assert data['user']['username'] == 'testuser'

    def test_login_username_case_insensitive(self, client, standard_user, app):
        """Username login ignores letter case"""
        with app.app_context():
            response = client.post('/api/auth/login', json={
                'username': 'TestUser',
                'password': 'TestPass123'
            })

            assert response.status_code == 200
            data = response.get_json()
            assert data['user']['username'] == 'testuser'
    
    def test_login_wrong_password(self, client, standard_user, app):
        """Test login with wrong password"""
        with app.app_context():
            response = client.post('/api/auth/login', json={
                'username': 'testuser',
                'password': 'WrongPassword123'
            })
            
            assert response.status_code == 401
            data = response.get_json()
            assert data['success'] is False
            assert 'error' in data
            assert data['error_code'] == 'INVALID_CREDENTIALS'
    
    def test_login_nonexistent_user(self, client, app):
        """Test login with non-existent user"""
        with app.app_context():
            response = client.post('/api/auth/login', json={
                'username': 'nonexistent',
                'password': 'SomePassword123'
            })
            
            assert response.status_code == 401
            data = response.get_json()
            assert data['success'] is False
    
    def test_login_missing_fields(self, client, app):
        """Test login with missing fields"""
        with app.app_context():
            response = client.post('/api/auth/login', json={
                'username': 'testuser'
            })
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'VALIDATION_ERROR'
    
    def test_login_empty_body(self, client, app):
        """Test login with empty body"""
        with app.app_context():
            response = client.post('/api/auth/login', 
                                   data='',
                                   content_type='application/json')
            
            assert response.status_code == 400


class TestRegister:
    """Test registration endpoint"""

    @staticmethod
    def _wizard_payload(**overrides):
        payload = {
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@example.com',
            'mobile_number': '+971501234567',
            'project_name': 'Marina Tower',
            'job_designation': 'Technician',
            'employment_start_date': '2024-06-01',
        }
        payload.update(overrides)
        return payload
    
    def test_register_success(self, client, app):
        """Test successful wizard-style registration"""
        with app.app_context():
            response = client.post('/api/auth/register', json=self._wizard_payload())
            
            assert response.status_code == 201
            data = response.get_json()
            assert 'user' in data
            assert data['user']['email'] == 'newuser@example.com'
            assert data['user']['full_name'] == 'New User'
            assert data['user']['job_designation'] == 'Technician'
            assert data['default_password'] is not None
            assert data['login_hint'] == 'newuser@example.com'
    
    def test_register_weak_password(self, client, app):
        """Test legacy registration with weak password"""
        with app.app_context():
            response = client.post('/api/auth/register', json={
                **self._wizard_payload(email='weakpass@example.com'),
                'password': 'weak',
            })
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'WEAK_PASSWORD'
    
    def test_register_invalid_email(self, client, app):
        """Test registration with invalid email"""
        with app.app_context():
            response = client.post('/api/auth/register', json=self._wizard_payload(
                email='not-an-email',
            ))
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'VALIDATION_ERROR'
    
    def test_register_duplicate_username(self, client, standard_user, app):
        """Test registration with existing username"""
        with app.app_context():
            response = client.post('/api/auth/register', json={
                **self._wizard_payload(email='different@example.com'),
                'username': 'testuser',
            })
            
            assert response.status_code == 409
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'DUPLICATE_USERNAME'
    
    def test_register_duplicate_email(self, client, standard_user, app):
        """Test registration with existing email"""
        with app.app_context():
            response = client.post('/api/auth/register', json=self._wizard_payload(
                email='test@example.com',
            ))
            
            assert response.status_code == 409
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'DUPLICATE_EMAIL'
    
    def test_register_missing_fields(self, client, app):
        """Test registration with missing required fields"""
        with app.app_context():
            response = client.post('/api/auth/register', json={
                'first_name': 'Incomplete',
            })
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'VALIDATION_ERROR'


class TestTokenRefresh:
    """Test token refresh endpoint"""
    
    def test_refresh_success(self, client, standard_user, app):
        """Test successful token refresh"""
        with app.app_context():
            # First login to get tokens
            login_response = client.post('/api/auth/login', json={
                'username': 'testuser',
                'password': 'TestPass123'
            })
            tokens = login_response.get_json()
            refresh_token = tokens['refresh_token']
            
            # Use refresh token to get new access token
            response = client.post('/api/auth/refresh',
                                   headers={'Authorization': f'Bearer {refresh_token}'})
            
            assert response.status_code == 200
            data = response.get_json()
            assert 'access_token' in data
    
    def test_refresh_invalid_token(self, client, app):
        """Test refresh with invalid token"""
        with app.app_context():
            response = client.post('/api/auth/refresh',
                                   headers={'Authorization': 'Bearer invalid-token'})

            # flask-jwt-extended returns 401 on invalid tokens in newer versions (was 422)
            assert response.status_code in (401, 422)


class TestGetCurrentUser:
    """Test get current user endpoint"""
    
    def test_get_me_success(self, client, auth_headers, app):
        """Test getting current user info"""
        with app.app_context():
            response = client.get('/api/auth/me', headers=auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert 'user' in data
            assert data['user']['username'] == 'testuser'
    
    def test_get_me_no_token(self, client, app):
        """Test getting user info without token"""
        with app.app_context():
            response = client.get('/api/auth/me')
            
            assert response.status_code == 401


class TestChangePassword:
    """Test change password endpoint"""
    
    def test_change_password_success(self, client, auth_headers, app):
        """Test successful password change"""
        with app.app_context():
            response = client.post('/api/auth/change-password',
                                   headers=auth_headers,
                                   json={
                                       'current_password': 'TestPass123',
                                       'new_password': 'NewSecurePass456'
                                   })
            
            assert response.status_code == 200
            data = response.get_json()
            assert 'message' in data
    
    def test_change_password_wrong_current(self, client, auth_headers, app):
        """Test password change with wrong current password"""
        with app.app_context():
            response = client.post('/api/auth/change-password',
                                   headers=auth_headers,
                                   json={
                                       'current_password': 'WrongPassword',
                                       'new_password': 'NewSecurePass456'
                                   })
            
            assert response.status_code == 401
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'INVALID_PASSWORD'
    
    def test_change_password_weak_new(self, client, auth_headers, app):
        """Test password change with weak new password"""
        with app.app_context():
            response = client.post('/api/auth/change-password',
                                   headers=auth_headers,
                                   json={
                                       'current_password': 'TestPass123',
                                       'new_password': 'weak'
                                   })
            
            assert response.status_code == 400
            data = response.get_json()
            assert data['success'] is False
            assert data['error_code'] == 'WEAK_PASSWORD'


class TestLogout:
    """Test logout endpoint"""
    
    def test_logout_success(self, client, auth_headers, app):
        """Test successful logout"""
        with app.app_context():
            response = client.post('/api/auth/logout', headers=auth_headers)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['message'] == 'Logout successful'
    
    def test_logout_no_token(self, client, app):
        """Logout without a token still succeeds and clears cookies."""
        with app.app_context():
            response = client.post('/api/auth/logout')

            assert response.status_code == 200
            data = response.get_json()
            assert data['message'] == 'Logout successful'

    def test_logout_revokes_session_and_blocks_dashboard(self, client, standard_user, app):
        """After logout, dashboard HTML must ask for credentials again."""
        with app.app_context():
            login = client.post('/api/auth/login', json={
                'username': 'testuser',
                'password': 'TestPass123'
            })
            assert login.status_code == 200
            token = login.get_json()['access_token']
            headers = {'Authorization': f'Bearer {token}'}

            dash = client.get('/dashboard', headers=headers)
            assert dash.status_code == 200
            assert 'no-store' in (dash.headers.get('Cache-Control') or '')

            logout = client.post('/api/auth/logout', headers=headers)
            assert logout.status_code == 200

            blocked = client.get('/dashboard', headers=headers)
            assert blocked.status_code in (302, 401)
            if blocked.status_code == 302:
                assert '/login' in (blocked.headers.get('Location') or '')

            cookie_blocked = client.get('/dashboard')
            assert cookie_blocked.status_code in (302, 401)
            if cookie_blocked.status_code == 302:
                assert '/login' in (cookie_blocked.headers.get('Location') or '')

    def test_dashboard_requires_auth(self, client, app):
        """Anonymous GET /dashboard redirects to login."""
        with app.app_context():
            response = client.get('/dashboard')
            assert response.status_code in (302, 401)
            if response.status_code == 302:
                assert '/login' in (response.headers.get('Location') or '')

    def test_logout_is_idempotent(self, client, auth_headers, app):
        """A second logout after the session is already revoked still returns 200."""
        with app.app_context():
            first = client.post('/api/auth/logout', headers=auth_headers)
            assert first.status_code == 200
            second = client.post('/api/auth/logout', headers=auth_headers)
            assert second.status_code == 200


class TestErrorResponseFormat:
    """Test that error responses follow the standard format"""
    
    def test_error_has_success_false(self, client, app):
        """Test that errors have success: false"""
        with app.app_context():
            response = client.post('/api/auth/login', json={})
            
            data = response.get_json()
            assert 'success' in data
            assert data['success'] is False
    
    def test_error_has_error_message(self, client, app):
        """Test that errors have error message"""
        with app.app_context():
            response = client.post('/api/auth/login', json={})
            
            data = response.get_json()
            assert 'error' in data
            assert isinstance(data['error'], str)
    
    def test_error_has_error_code(self, client, app):
        """Test that errors have error_code"""
        with app.app_context():
            response = client.post('/api/auth/login', json={
                'username': 'test'
            })
            
            data = response.get_json()
            assert 'error_code' in data
            assert isinstance(data['error_code'], str)


class TestHealthEndpoint:
    def test_health_ok_when_users_table_exists(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('database') == 'healthy'
        assert data.get('status') == 'healthy'
