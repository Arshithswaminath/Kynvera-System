import os
import sys

basedir = os.path.abspath(os.path.dirname(__file__))

class BaseConfig:
    # Security: No default secrets in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    
    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,  # Check connections before using
        'pool_recycle': 300,    # Recycle connections every 5 minutes
    }
    
    # Cloudinary
    CLOUDINARY_UPLOAD_PRESET = os.environ.get('CLOUDINARY_UPLOAD_PRESET', 'render_site_upload')
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')
    
    # Redis
    REDIS_URL = os.environ.get('REDIS_URL')
    
    # App settings
    APP_BASE_URL = os.environ.get('APP_BASE_URL', '')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL')
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '100 per hour')
    RATELIMIT_HEADERS_ENABLED = True
    
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No expiration
    WTF_CSRF_SSL_STRICT = False  # Allow HTTP in dev

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/injaaz')
    # Dev defaults for secrets (only in dev!)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-production')
    WTF_CSRF_ENABLED = False  # Disable CSRF in dev for testing

class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    WTF_CSRF_SSL_STRICT = True  # Enforce HTTPS for CSRF
    
    # Enforce secrets in production
    def __init__(self):
        super().__init__()
        if not self.SECRET_KEY or self.SECRET_KEY == 'dev-secret':
            print("ERROR: SECRET_KEY must be set in production!", file=sys.stderr)
            sys.exit(1)
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY == 'jwt-secret':
            print("ERROR: JWT_SECRET_KEY must be set in production!", file=sys.stderr)
            sys.exit(1)
        if not self.SQLALCHEMY_DATABASE_URI:
            print("ERROR: DATABASE_URL must be set in production!", file=sys.stderr)
            sys.exit(1)

class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret'
    JWT_SECRET_KEY = 'test-jwt-secret'

config_by_name = dict(
    development=DevelopmentConfig,
    production=ProductionConfig,
    testing=TestingConfig
)