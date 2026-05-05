import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Set GENERATED_DIR on Render (persistent disk mount, e.g. /var/data/generated) so uploads survive redeploys.
# Default: project ./generated (ephemeral on most PaaS).
_gen_override = (os.environ.get("GENERATED_DIR") or "").strip()
GENERATED_DIR = os.path.abspath(_gen_override) if _gen_override else os.path.join(BASE_DIR, "generated")
UPLOADS_DIR = os.path.join(GENERATED_DIR, "uploads")
JOBS_DIR = os.path.join(GENERATED_DIR, "jobs")

# simple limits
# Standardized file upload limits (10MB for all modules)
MAX_UPLOAD_FILESIZE = 10 * 1024 * 1024  # 10MB per file
MAX_FILE_SIZE_MB = 10  # Standardized max file size in MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx', 'csv'}

# To increase total upload size (all files combined):
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB total

# ============================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ============================================================

# SECRET_KEY - Used for session encryption and CSRF protection
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-jwt-secret")

# CLOUDINARY - Image hosting service
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

# DATABASE - PostgreSQL for production (REQUIRED in production)
# Fix for Render: Replace postgres:// with postgresql:// for SQLAlchemy compatibility
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Only allow SQLite in development
    if os.getenv("FLASK_ENV", "development") == "development":
        DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'injaaz.db')}"
    else:
        # Production requires DATABASE_URL environment variable
        raise ValueError("DATABASE_URL environment variable is required in production")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# FLASK ENVIRONMENT
FLASK_ENV = os.getenv("FLASK_ENV", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# REDIS (for rate limiting and background tasks)
# Strip whitespace — common copy/paste issue from Render/Upstash dashboards
_redis = (os.getenv("REDIS_URL") or "").strip()
REDIS_URL = _redis or None

# MMR module: optional schedule overrides (survive redeploys when GENERATED_DIR is ephemeral).
# Set in Render dashboard if mmr_email_config.json is lost each deploy. See module_mmr.routes._load_config.
# MMR_SCHEDULE_ENABLED=true|false  MMR_SCHEDULE_HOUR=10  MMR_SCHEDULE_MINUTE=0
# MMR_SCHEDULE_TIMEZONE=Asia/Dubai  (default; hour/minute are in this zone, not UTC)

# JWT Settings - Token expiry times (configurable via environment variables)
# JWT_ACCESS_HOURS: Number of hours for access token validity (default: 1 hour)
# JWT_REFRESH_DAYS: Number of days for refresh token validity (default: 7 days)
from datetime import timedelta

_jwt_access_hours = int(os.getenv("JWT_ACCESS_HOURS", 1))
_jwt_refresh_days = int(os.getenv("JWT_REFRESH_DAYS", 7))

JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=_jwt_access_hours)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_jwt_refresh_days)
# JWT Cookie Settings - Enable cookie-based authentication for HTML links
JWT_TOKEN_LOCATION = ['headers', 'cookies']  # Read from both headers and cookies
JWT_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"  # HTTPS only in production
JWT_COOKIE_HTTPONLY = True  # Prevent XSS attacks
JWT_COOKIE_SAMESITE = 'Lax'  # CSRF protection
JWT_ACCESS_COOKIE_NAME = 'access_token_cookie'
JWT_REFRESH_COOKIE_NAME = 'refresh_token_cookie'
# Flask-JWT-Extended defaults JWT_COOKIE_CSRF_PROTECT=True. When True, POST requests that use
# the access JWT from cookies require X-CSRF-TOKEN. Multipart uploads (DocHub) do not send it → 401.
# The SPA uses Authorization: Bearer from localStorage; cookies are a fallback. Default off; set
# JWT_COOKIE_CSRF_PROTECT=true in env only if you add CSRF headers to all API calls.
JWT_COOKIE_CSRF_PROTECT = os.getenv("JWT_COOKIE_CSRF_PROTECT", "false").lower() == "true"

# EMAIL (Optional - for HVAC module email reports)
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@injaaz.com")

# Brevo (Sendinblue) — HTTPS API; use on hosts that block SMTP (e.g. Render free tier blocks ports 25/465/587).
BREVO_API_KEY = os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY")

# Mailjet — optional explicit keys for REST API (HTTPS). If unset, MAIL_USERNAME/PASSWORD with MAIL_SERVER=in-v3.mailjet.com still work (SMTP or REST on Render).
MAILJET_API_KEY = os.getenv("MAILJET_API_KEY")
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY")

# Application
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")

# Security
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# SQLALCHEMY
SQLALCHEMY_DATABASE_URI = DATABASE_URL
SQLALCHEMY_TRACK_MODIFICATIONS = False
# SQLite does not support pool_size, max_overflow, pool_timeout - use minimal options
_use_sqlite = DATABASE_URL and 'sqlite' in DATABASE_URL.lower()
SQLALCHEMY_ENGINE_OPTIONS = {
    'echo': False,                   # Don't log all SQL queries (set to True for debugging)
} if _use_sqlite else {
    'pool_pre_ping': True,           # Check connections before using
    'pool_recycle': 300,             # Recycle connections every 5 minutes
    'pool_size': 5,                  # Number of connections to maintain (reduced for free tier)
    'max_overflow': 10,              # Maximum overflow connections (reduced for free tier)
    'pool_timeout': 30,              # Timeout for getting connection from pool
    'echo': False,                   # Don't log all SQL queries (set to True for debugging)
}
