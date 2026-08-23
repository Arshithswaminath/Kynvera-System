"""
Pytest fixtures for Injaaz application testing
"""
import pytest
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set testing environment variables at module import time, not inside the `app`
# fixture. pytest always imports tests/conftest.py before collecting any test
# file in this directory, but several test files (e.g. test_hr_forms_pdf_suite.py's
# `@pytest.mark.parametrize(..., module_hr.pdf_service.get_supported_pdf_forms())`)
# eagerly import application modules as a side effect of a decorator argument —
# which happens at COLLECTION time, before any fixture (including this one) ever
# runs. That import chain pulls in config.py, whose module-level env-var reads
# (RATELIMIT_ENABLED, DATABASE_URL, etc.) only execute once and get cached in
# sys.modules — so if config.py loads before these os.environ writes, it freezes
# in production defaults for the rest of the process, no matter what the `app`
# fixture sets afterward. Setting them here, at conftest.py's own import time,
# guarantees they land before ANY test module (and its collection-time imports)
# can be evaluated.
os.environ['FLASK_ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing'
os.environ['ASSISTANT_LLM_ENABLED'] = 'false'
os.environ['ANTHROPIC_API_KEY'] = ''
os.environ['OPENAI_API_KEY'] = ''
# The full suite calls /api/auth/login far more than its intended 5-per-minute
# limit via the per-test auth-header fixtures below. Without this, a full
# `pytest tests/` run gets rate-limited mid-suite: login silently returns no
# access_token, headers become "Bearer None", and every later test cascades into
# unrelated 401s. Config key is read by config.py -> Flask-Limiter directly.
os.environ['RATELIMIT_ENABLED'] = 'false'


@pytest.fixture(scope='session')
def app():
    """Create test application"""
    from Injaaz import create_app
    from app.models import db
    
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'JWT_SECRET_KEY': 'test-jwt-secret-key',
        'JWT_ACCESS_TOKEN_EXPIRES': False,  # No expiry for tests
        'ASSISTANT_LLM_ENABLED': False,
        'ANTHROPIC_API_KEY': '',
        'OPENAI_API_KEY': '',
        'RATELIMIT_ENABLED': False,
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for testing"""
    from app.models import db
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture(scope='function')
def standard_user(app):
    """Create a test user (not named test_* so pytest does not collect it as a test)."""
    from app.models import db, User
    
    with app.app_context():
        user = User(
            username='testuser',
            email='test@example.com',
            full_name='Test User',
            role='user',
            is_active=True,
            password_changed=True
        )
        user.set_password('TestPass123')
        db.session.add(user)
        db.session.commit()
        
        yield user
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()


@pytest.fixture(scope='function')
def admin_user(app):
    """Create an admin test user"""
    from app.models import db, User
    
    with app.app_context():
        user = User(
            username='testadmin',
            email='admin@example.com',
            full_name='Test Admin',
            role='admin',
            is_active=True,
            password_changed=True
        )
        user.set_password('AdminPass123')
        db.session.add(user)
        db.session.commit()
        
        yield user
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()


@pytest.fixture(scope='function')
def supervisor_user(app):
    """Create a supervisor test user"""
    from app.models import db, User
    
    with app.app_context():
        user = User(
            username='testsupervisor',
            email='supervisor@example.com',
            full_name='Test Supervisor',
            role='user',
            designation='supervisor',
            is_active=True,
            password_changed=True,
            access_hvac=True,
            access_civil=True,
            access_cleaning=True
        )
        user.set_password('SuperPass123')
        db.session.add(user)
        db.session.commit()
        
        yield user
        
        # Cleanup
        db.session.delete(user)
        db.session.commit()


@pytest.fixture(scope='function')
def auth_headers(client, standard_user, app):
    """Get authentication headers for test user"""
    with app.app_context():
        response = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'TestPass123'
        })
        data = response.get_json()
        token = data.get('access_token')
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='function')
def admin_auth_headers(client, admin_user, app):
    """Get authentication headers for admin user"""
    with app.app_context():
        response = client.post('/api/auth/login', json={
            'username': 'testadmin',
            'password': 'AdminPass123'
        })
        data = response.get_json()
        token = data.get('access_token')
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='function')
def supervisor_auth_headers(client, supervisor_user, app):
    """Get authentication headers for supervisor user"""
    with app.app_context():
        response = client.post('/api/auth/login', json={
            'username': 'testsupervisor',
            'password': 'SuperPass123'
        })
        data = response.get_json()
        token = data.get('access_token')
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='function')
def sample_submission(app, supervisor_user):
    """Create a test submission (fixture name avoids pytest test_* collection)."""
    from app.models import db, Submission
    from common.utils import random_id
    
    with app.app_context():
        submission = Submission(
            submission_id=random_id('sub'),
            module_type='civil',
            site_name='Test Site',
            visit_date=datetime.now(timezone.utc).date(),
            form_data={'test': 'data'},
            workflow_status='submitted',
            user_id=supervisor_user.id,
            supervisor_id=supervisor_user.id
        )
        db.session.add(submission)
        db.session.commit()
        
        yield submission
        
        # Cleanup
        db.session.delete(submission)
        db.session.commit()
