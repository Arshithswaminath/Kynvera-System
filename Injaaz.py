import os
import sys
import logging
import mimetypes
from datetime import datetime, timezone
from flask import Flask, send_from_directory, abort, render_template, jsonify, request, redirect
from concurrent.futures import ThreadPoolExecutor
from werkzeug.exceptions import HTTPException
from flask_jwt_extended import JWTManager
from sqlalchemy import text

# Import Flask extensions
from app.models import db, bcrypt

# App config constants (ensure config.py exists)
from config import BASE_DIR, GENERATED_DIR, UPLOADS_DIR, JOBS_DIR

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Try importing blueprints; if any import fails we log and continue so the app still starts.
hvac_mep_bp = None
civil_bp = None
cleaning_bp = None
auth_bp = None
bd_bp = None
docs_bp = None

try:
    from module_hvac_mep.routes import hvac_mep_bp  # noqa: F401
    logger.info("Imported module_hvac_mep.routes.hvac_mep_bp")
except Exception as e:
    logger.exception("Could not import module_hvac_mep.routes.hvac_mep_bp: %s", e)
    hvac_mep_bp = None

try:
    from module_civil.routes import civil_bp  # noqa: F401
    logger.info("Imported module_civil.routes.civil_bp")
except Exception as e:
    logger.exception("Could not import module_civil.routes.civil_bp: %s", e)
    civil_bp = None

try:
    from module_cleaning.routes import cleaning_bp  # noqa: F401
    logger.info("Imported module_cleaning.routes.cleaning_bp")
except Exception as e:
    logger.exception("Could not import module_cleaning.routes.cleaning_bp: %s", e)
    cleaning_bp = None

try:
    from app.auth.routes import auth_bp  # noqa: F401
    logger.info("Imported app.auth.routes.auth_bp")
except Exception as e:
    logger.exception("Could not import app.auth.routes.auth_bp: %s", e)
    auth_bp = None

try:
    from app.admin.routes import admin_bp  # noqa: F401
    logger.info("Imported app.admin.routes.admin_bp")
except Exception as e:
    logger.exception("Could not import app.admin.routes.admin_bp: %s", e)
    admin_bp = None

try:
    from app.workflow.routes import workflow_bp  # noqa: F401
    logger.info("Imported app.workflow.routes.workflow_bp")
except Exception as e:
    logger.exception("Could not import app.workflow.routes.workflow_bp: %s", e)
    workflow_bp = None

try:
    from app.bd.routes import bd_bp  # noqa: F401
    logger.info("Imported app.bd.routes.bd_bp")
except Exception as e:
    logger.exception("Could not import app.bd.routes.bd_bp: %s", e)
    bd_bp = None

try:
    from app.docs.routes import docs_bp  # noqa: F401
    logger.info("Imported app.docs.routes.docs_bp")
except Exception as e:
    logger.exception("Could not import app.docs.routes.docs_bp: %s", e)
    docs_bp = None

# HR Module
hr_bp = None
try:
    from module_hr.routes import hr_bp  # noqa: F401
    logger.info("Imported module_hr.routes.hr_bp")
except Exception as e:
    logger.exception("Could not import module_hr.routes.hr_bp: %s", e)
    hr_bp = None

# Procurement Module
procurement_module_bp = None
try:
    from module_procurement.routes import procurement_bp as procurement_module_bp  # noqa: F401
    logger.info("Imported module_procurement.routes.procurement_bp")
except Exception as e:
    logger.exception("Could not import module_procurement.routes.procurement_bp: %s", e)
    procurement_module_bp = None

# Inspection Form Module (HVAC, Civil, Cleaning)
inspection_bp = None
try:
    from module_inspection.routes import inspection_bp  # noqa: F401
    logger.info("Imported module_inspection.routes.inspection_bp")
except Exception as e:
    logger.exception("Could not import module_inspection.routes.inspection_bp: %s", e)
    inspection_bp = None

# MMR (Report Generation) Module
mmr_bp = None
try:
    from module_mmr.routes import mmr_bp  # noqa: F401
    logger.info("Imported module_mmr.routes.mmr_bp")
except Exception as e:
    logger.exception("Could not import module_mmr.routes.mmr_bp: %s", e)
    mmr_bp = None

# Ensure required directories exist at startup
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(JOBS_DIR, exist_ok=True)

# Simple background executor for report generation tasks
# Reduced to 1 worker for free tier memory constraints (512MB limit)
executor = ThreadPoolExecutor(max_workers=1)


def create_app():
    # Pin root_path to the repo directory. If import_name is "__main__", Flask can fall back to
    # os.getcwd() when resolving "templates/", which loads a stale or wrong admin_dashboard.html.
    app = Flask(
        __name__,
        root_path=BASE_DIR,
        static_folder='static',
        template_folder='templates',
    )

    # Some container images lack /etc/mime.types; browsers enforce nosniff on CSS/JS.
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("application/json", ".json")

    # Inject `now` into every Jinja template so {{ now().year }} works everywhere,
    # including standalone templates that don't extend base.html.
    app.jinja_env.globals['now'] = lambda: datetime.now(timezone.utc)
    
    # Enable template auto-reload for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Load configuration from config.py
    # Import config module and load all uppercase variables (config settings)
    import config as config_module
    # Use vars() to get only attributes defined in the module, not imported ones
    for key, value in vars(config_module).items():
        if key.isupper() and not key.startswith('_') and not callable(value):
            app.config[key] = value
    
    # Validate configuration
    from common.config_validator import validate_config
    is_valid, errors = validate_config(app)
    
    if not is_valid:
        error_msg = "❌ CRITICAL: Configuration validation failed!\n"
        error_msg += "\n".join(f"  - {error}" for error in errors)
        logger.error(error_msg)
        # Raise exception instead of sys.exit() to avoid crashing WSGI worker
        raise RuntimeError(error_msg)
    
    # Initialize Flask extensions
    db.init_app(app)
    bcrypt.init_app(app)
    
    # Initialize Flask-Migrate for database migrations
    from flask_migrate import Migrate
    migrate = Migrate(app, db)
    
    # Initialize JWT
    jwt = JWTManager(app)
    
    # Configure JWT to read from both headers and cookies
    # This allows HTML links to work (cookies) and API calls to work (headers)
    app.config.setdefault('JWT_TOKEN_LOCATION', ['headers', 'cookies'])
    app.config.setdefault('JWT_COOKIE_SECURE', app.config.get('SESSION_COOKIE_SECURE', False))
    app.config.setdefault('JWT_COOKIE_HTTPONLY', True)
    app.config.setdefault('JWT_COOKIE_SAMESITE', 'Lax')
    app.config.setdefault('JWT_ACCESS_COOKIE_NAME', 'access_token_cookie')
    app.config.setdefault('JWT_REFRESH_COOKIE_NAME', 'refresh_token_cookie')
    # JWTManager defaults JWT_COOKIE_CSRF_PROTECT=True if missing — breaks multipart uploads (no CSRF header).
    # Explicit opt-in only: JWT_COOKIE_CSRF_PROTECT=true in environment.
    app.config['JWT_COOKIE_CSRF_PROTECT'] = (
        os.environ.get('JWT_COOKIE_CSRF_PROTECT', '').lower() == 'true'
    )
    
    # JWT Error Handlers - ensure proper error responses
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        """Handle missing or invalid JWT token"""
        # Check if this is a page render route (returns HTML) vs API route (returns JSON)
        # Page render routes: /api/workflow/history, /api/workflow/pending-reviews, etc.
        page_render_routes = ['/api/workflow/history', '/api/workflow/pending-reviews']
        if request.path in page_render_routes:
            # For page render routes, redirect to login
            from flask import redirect, url_for
            return redirect(url_for('login_page')), 302
        elif request.path.startswith('/api/') or '/api/' in request.path:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        # For other HTML pages, redirect to login
        from flask import redirect, url_for
        return redirect(url_for('login_page')), 302
    
    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        """Handle invalid JWT token"""
        # Check if this is a page render route
        page_render_routes = ['/api/workflow/history', '/api/workflow/pending-reviews']
        if request.path in page_render_routes:
            from flask import redirect, url_for
            return redirect(url_for('login_page')), 302
        elif request.path.startswith('/api/') or '/api/' in request.path:
            return jsonify({"success": False, "error": "Invalid token"}), 401
        from flask import redirect, url_for
        return redirect(url_for('login_page')), 302
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """Handle expired JWT token"""
        # Check if this is a page render route
        page_render_routes = ['/api/workflow/history', '/api/workflow/pending-reviews']
        if request.path in page_render_routes:
            from flask import redirect, url_for
            return redirect(url_for('login_page')), 302
        elif request.path.startswith('/api/') or '/api/' in request.path:
            return jsonify({"success": False, "error": "Token has expired"}), 401
        from flask import redirect, url_for
        return redirect(url_for('login_page')), 302
    
    # JWT token verification callback (check if token is revoked)
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        from app.models import Session
        from common.jwt_session import sync_access_session_row

        if jwt_payload.get('type') == 'refresh':
            return False
        jti = jwt_payload.get('jti')
        if not jti:
            return True
        session = Session.query.filter_by(token_jti=jti).first()
        if session is None:
            session = sync_access_session_row(jti, jwt_payload)
        if session is None:
            logger.warning(
                "JWT blocklist: missing session for jti=%s sub=%s — token treated as revoked",
                jti,
                jwt_payload.get('sub'),
            )
            return True
        return session.is_revoked
    
    logger.info("✅ Database and JWT initialized")
    
    # Automatic database initialization and migration (fully self-contained for Render)
    with app.app_context():
        try:
            import time
            from sqlalchemy import inspect, text
            
            # Retry logic for database connection (Render databases may need a moment)
            max_retries = 5
            retry_delay = 2
            inspector = None
            
            for attempt in range(max_retries):
                try:
                    inspector = inspect(db.engine)
                    # Test connection by getting table names
                    inspector.get_table_names()
                    logger.info("✅ Database connection verified")
                    break
                except Exception as conn_error:
                    if attempt < max_retries - 1:
                        logger.info(f"Database connection attempt {attempt + 1}/{max_retries} failed, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error(f"❌ Failed to connect to database after {max_retries} attempts: {conn_error}")
                        raise
            
            # Step 1: Create all tables if they don't exist (fully automatic)
            logger.info("Ensuring all database tables exist...")
            try:
                db.create_all()
                logger.info("✅ All database tables verified/created")
            except Exception as create_error:
                logger.warning(f"Table creation check: {create_error}")
                # Continue anyway - tables might already exist
            
            # Step 2: Database migrations are now handled by Flask-Migrate
            # Run migrations manually using: flask db upgrade
            # This ensures version-controlled, reversible migrations
            logger.info("✅ Database tables verified. Use 'flask db upgrade' to apply migrations.")
            
            # Step 2.5: Add missing columns if tables exist (one-time migration for existing databases)
            inspector = inspect(db.engine)
            if 'users' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('users')]
                missing_columns = []
                
                # Check for designation column
                if 'designation' not in columns:
                    missing_columns.append(('designation', 'VARCHAR(20) DEFAULT NULL'))
                
                if missing_columns:
                    logger.info(f"Adding missing columns to users table: {[col[0] for col in missing_columns]}")
                    try:
                        with db.engine.begin() as conn:
                            for col_name, col_def in missing_columns:
                                try:
                                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                                    logger.info(f"✅ Added {col_name} column to users table")
                                except Exception as col_error:
                                    error_str = str(col_error).lower()
                                    if 'already exists' in error_str or 'duplicate' in error_str:
                                        logger.info(f"Column {col_name} already exists, skipping")
                                    else:
                                        logger.warning(f"Could not add {col_name}: {col_error}")
                    except Exception as e:
                        logger.warning(f"Could not add missing columns (non-critical): {e}")
            
            if 'submissions' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('submissions')]
                missing_columns = []
                
                # Check for workflow columns
                workflow_fields = [
                    ('workflow_status', "VARCHAR(30) DEFAULT 'submitted'"),
                    ('supervisor_id', 'INTEGER'),
                    ('manager_id', 'INTEGER'),
                    ('supervisor_notified_at', 'TIMESTAMP DEFAULT NULL'),
                    ('supervisor_reviewed_at', 'TIMESTAMP DEFAULT NULL'),
                    ('manager_notified_at', 'TIMESTAMP DEFAULT NULL'),
                    ('manager_reviewed_at', 'TIMESTAMP DEFAULT NULL')
                ]
                
                for col_name, col_def in workflow_fields:
                    if col_name not in columns:
                        missing_columns.append((col_name, col_def))
                
                if missing_columns:
                    logger.info(f"Adding missing workflow columns to submissions table: {[col[0] for col in missing_columns]}")
                    try:
                        with db.engine.begin() as conn:
                            for col_name, col_def in missing_columns:
                                try:
                                    conn.execute(text(f"ALTER TABLE submissions ADD COLUMN {col_name} {col_def}"))
                                    logger.info(f"✅ Added {col_name} column to submissions table")
                                except Exception as col_error:
                                    error_str = str(col_error).lower()
                                    if 'already exists' in error_str or 'duplicate' in error_str:
                                        logger.info(f"Column {col_name} already exists, skipping")
                                    else:
                                        logger.warning(f"Could not add {col_name}: {col_error}")
                    except Exception as e:
                        logger.warning(f"Could not add missing workflow columns (non-critical): {e}")

            if 'dochub_documents' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('dochub_documents')]
                missing_columns = []
                if 'doc_type' not in columns:
                    missing_columns.append(('doc_type', "VARCHAR(20) DEFAULT 'upload'"))
                if 'content' not in columns:
                    missing_columns.append(('content', 'TEXT'))
                if 'inline_asset' not in columns:
                    # PostgreSQL rejects BOOLEAN DEFAULT 0; use FALSE (SQLite accepts FALSE too)
                    missing_columns.append(('inline_asset', 'BOOLEAN DEFAULT FALSE'))
                if 'reference_attachments' not in columns:
                    missing_columns.append(('reference_attachments', 'TEXT'))
                if missing_columns:
                    logger.info(f"Adding DocHub columns: {[c[0] for c in missing_columns]}")
                    for col_name, col_def in missing_columns:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text(f"ALTER TABLE dochub_documents ADD COLUMN {col_name} {col_def}"))
                            logger.info(f"✅ Added {col_name} to dochub_documents")
                        except Exception as col_error:
                            err = str(col_error).lower()
                            if 'already exists' in err or 'duplicate' in err:
                                logger.info(f"Column {col_name} already exists")
                            else:
                                logger.warning(f"Could not add {col_name}: {col_error}")

            # Step 3: Ensure default admin user exists (fully automatic for Render)
            try:
                from app.models import User
                admin = User.query.filter_by(username='admin').first()
                if not admin:
                    logger.info("Creating default admin user...")
                    admin = User(
                        username='admin',
                        email='admin@injaaz.com',
                        full_name='System Administrator',
                        role='admin',
                        is_active=True,
                        access_hvac=True,
                        access_civil=True,
                        access_cleaning=True
                    )
                    # Use environment variable for default password, or generate random one
                    import secrets
                    default_password = os.environ.get('DEFAULT_ADMIN_PASSWORD', None)
                    if not default_password:
                        # Generate a secure random password if not set
                        default_password = secrets.token_urlsafe(16)
                        logger.warning("⚠️  No DEFAULT_ADMIN_PASSWORD set - using generated password")
                        # Log to a secure location (not just console)
                        logger.critical(f"🔐 DEFAULT ADMIN PASSWORD GENERATED: {default_password}")
                        logger.critical("⚠️  SECURITY: Change this password immediately after first login!")
                    
                    admin.set_password(default_password)
                    admin.password_changed = False  # Force password change on first login
                    db.session.add(admin)
                    db.session.commit()
                    logger.info("✅ Default admin user created")
                    if not os.environ.get('DEFAULT_ADMIN_PASSWORD'):
                        logger.critical(f"⚠️  CRITICAL: Default admin password is: {default_password}")
                        logger.critical("⚠️  This password will be required on first login. CHANGE IT IMMEDIATELY!")
                    else:
                        logger.warning("⚠️  Default admin password set from DEFAULT_ADMIN_PASSWORD env var")
                        logger.warning("⚠️  Password change will be required on first login")
                else:
                    logger.info("✅ Admin user already exists")
            except Exception as admin_create_error:
                logger.warning(f"Could not create admin user (non-critical): {admin_create_error}")
            else:
                logger.info("Users table will be created when first user is registered")

            # Step 4: Seed sample DocHub documents if empty
            try:
                from app.models import DocHubDocument, User
                if DocHubDocument.query.count() == 0:
                    admin_user = User.query.filter_by(role='admin').first()
                    author_id = admin_user.id if admin_user else None
                    samples = [
                        ('Employee Onboarding Guide', 'onboarding', 'published',
                         '<h1>Employee Onboarding Guide</h1>'
                         '<div class="callout callout-blue"><span class="callout-icon">👋</span><div><strong>Welcome to the team!</strong> This guide will help you get up and running quickly.</div></div>'
                         '<h2>1. Company Overview</h2><p>Injaaz Facilities Management delivers excellence in facility services across the UAE.</p>'
                         '<h2>2. Your First Week</h2><ul><li><strong>Day 1:</strong> Meet your team lead, set up workstation</li>'
                         '<li><strong>Day 2:</strong> System access, security training</li><li><strong>Day 3-5:</strong> Department walkthroughs</li></ul>'
                         '<h2>3. Key Contacts</h2><ul><li><strong>HR:</strong> arshith@injaaz.ae</li><li><strong>IT:</strong> +971 50 156 0277</li></ul>'),
                        ('Project Services Agreement Template', 'contracts', 'review',
                         '<h1>Project Services Agreement</h1><p><em>Agreement between Service Provider and Client.</em></p>'
                         '<h2>1. Parties</h2><p><strong>Service Provider:</strong> Injaaz FM.<br/><strong>Client:</strong> [Client Name].</p>'
                         '<h2>2. Scope</h2><ul><li>Facility management services</li><li>Maintenance and repairs</li><li>Cleaning and HVAC</li></ul>'
                         '<h2>3. Payment Terms</h2><p>As per agreed milestones.</p>'),
                        ('Remote Work Policy', 'policies', 'published',
                         '<h1>Remote Work Policy</h1><div class="callout"><span class="callout-icon">⚠️</span><div>Effective January 2025.</div></div>'
                         '<h2>1. Purpose</h2><p>Guidelines for remote work to ensure productivity and security.</p>'
                         '<h2>2. Eligibility</h2><p>Available after 90-day probation.</p>'
                         '<h2>3. Core Hours</h2><p>10:00 AM – 3:00 PM local time.</p>'),
                        ('DocHub User Manual', 'manuals', 'published',
                         '<h1>DocHub User Manual</h1><p><em>Version 1.0 — March 2025</em></p>'
                         '<h2>1. Getting Started</h2><p>DocHub is your document management platform.</p>'
                         '<h2>2. Creating Documents</h2><ol><li>Click + New Document</li><li>Select a template</li><li>Edit and Save</li></ol>'
                         '<h2>3. Shortcuts</h2><p><strong>Ctrl+S</strong> — Save. <strong>Ctrl+B</strong> — Bold.</p>'),
                        ('Q1 2025 Performance Report', 'reports', 'draft',
                         '<h1>Q1 2025 Performance Report</h1><p><em>Analytics Team — April 2025</em></p>'
                         '<div class="callout callout-green"><span class="callout-icon">📈</span><div>Strong quarter across key metrics.</div></div>'
                         '<h2>1. Executive Summary</h2><p>Q1 marked a solid start to the fiscal year.</p>'
                         '<h2>2. Key Metrics</h2><table><tr><th>Metric</th><th>Target</th><th>Actual</th></tr>'
                         '<tr><td>Revenue</td><td>—</td><td>—</td></tr><tr><td>Projects</td><td>—</td><td>—</td></tr></table>'),
                    ]
                    for title, cat, status, content in samples:
                        doc = DocHubDocument(
                            title=title,
                            filename='',
                            stored_path='',
                            file_type='',
                            doc_type='content',
                            content=content,
                            category=cat,
                            status=status,
                            author_id=author_id
                        )
                        db.session.add(doc)
                    db.session.commit()
                    logger.info("Seeded 5 sample DocHub documents")
            except Exception as seed_err:
                logger.warning(f"Could not seed DocHub samples (non-critical): {seed_err}")

            logger.info("✅ Database initialization and migration complete")
            
        except Exception as e:
            # Log the full error for debugging
            logger.error(f"❌ Database initialization failed: {str(e)}", exc_info=True)
            # Don't fail startup - app might still work if tables exist
            logger.warning("⚠️  App will continue, but some features may not work until database is initialized")
    
    # Set environment variables for cloudinary library
    if app.config.get('CLOUDINARY_CLOUD_NAME'):
        os.environ['CLOUDINARY_CLOUD_NAME'] = app.config['CLOUDINARY_CLOUD_NAME']
    if app.config.get('CLOUDINARY_API_KEY'):
        os.environ['CLOUDINARY_API_KEY'] = app.config['CLOUDINARY_API_KEY']
    if app.config.get('CLOUDINARY_API_SECRET'):
        os.environ['CLOUDINARY_API_SECRET'] = app.config['CLOUDINARY_API_SECRET']
    
    # Set Redis URL for other services
    redis_url = app.config.get('REDIS_URL')
    if redis_url:
        os.environ['REDIS_URL'] = redis_url
    
    logger.info(f"✅ Cloudinary configured: {app.config.get('CLOUDINARY_CLOUD_NAME')}")
    
    # Warn if using default secret (only in dev)
    flask_env = app.config.get('FLASK_ENV', 'development')
    if flask_env != 'production' and app.config['SECRET_KEY'] in ['dev-secret-change-in-production', 'change-me-in-production']:
        logger.warning("⚠️  Using default SECRET_KEY! Set SECRET_KEY in .env for production!")

    # App-wide config used by blueprints and utils
    app.config['BASE_DIR'] = BASE_DIR
    app.config['GENERATED_DIR'] = GENERATED_DIR
    app.config['UPLOADS_DIR'] = UPLOADS_DIR
    app.config['JOBS_DIR'] = JOBS_DIR
    app.config['EXECUTOR'] = executor
    
    # Ensure directories exist (critical for Render deployment)
    try:
        os.makedirs(GENERATED_DIR, exist_ok=True)
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        os.makedirs(JOBS_DIR, exist_ok=True)
        os.makedirs(os.path.join(GENERATED_DIR, 'dochub'), exist_ok=True)
        os.makedirs(os.path.join(GENERATED_DIR, 'dochub', 'inline'), exist_ok=True)
        logger.info("✅ Directory structure verified (GENERATED_DIR=%s)", GENERATED_DIR)
    except Exception as e:
        logger.error(f"❌ Failed to create directories: {e}")
        # Don't fail, continue anyway (may be permissions issue)
    
    # Setup rate limiting with Redis
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        
        # Get Redis URL from app config or environment
        redis_url = app.config.get('REDIS_URL') or os.environ.get('RATELIMIT_STORAGE_URL') or os.environ.get('REDIS_URL')
        if redis_url:
            redis_url = redis_url.strip()
        
        if redis_url:
            try:
                # Test Redis connection first (Upstash: use rediss:// URL from dashboard)
                import redis
                r = redis.from_url(redis_url, socket_connect_timeout=5)
                r.ping()
                logger.info("✓ Redis connection test successful")
                
                limiter = Limiter(
                    app=app,
                    key_func=get_remote_address,
                    default_limits=[os.environ.get('RATELIMIT_DEFAULT', '100 per hour')],
                    storage_uri=redis_url,
                    strategy="fixed-window"
                )
                app.limiter = limiter
                logger.info("✓ Rate limiting enabled with Redis storage")
            except Exception as redis_error:
                logger.warning(f"⚠️  Redis connection failed - Rate limiting disabled: {redis_error}")
                app.limiter = None
        else:
            logger.info("✓ Rate limiting disabled (no Redis URL configured)")
            app.limiter = None
    except ImportError:
        logger.warning("⚠️  Flask-Limiter not installed - rate limiting disabled")
        app.limiter = None
    except Exception as e:
        logger.warning(f"⚠️  Rate limiting setup failed: {e}")
        app.limiter = None
    
    # Setup CSRF protection (if Flask-WTF available)
    try:
        from flask_wtf.csrf import CSRFProtect
        
        # Enable CSRF in production by default, disable in dev unless explicitly enabled
        enable_csrf = (
            os.environ.get('FLASK_ENV') == 'production' or 
            os.environ.get('ENABLE_CSRF', '').lower() == 'true'
        ) and os.environ.get('DISABLE_CSRF', '').lower() != 'true'
        
        if enable_csrf:
            csrf = CSRFProtect(app)
            app.csrf = csrf
            logger.info("✓ CSRF protection enabled (API routes will be exempted)")
        else:
            logger.warning("⚠️  CSRF protection disabled (development mode)")
            app.csrf = None
    except ImportError:
        logger.warning("⚠️  Flask-WTF not installed - CSRF protection disabled")
        app.csrf = None
    
    # Global error handlers
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Resource not found"}), 404
        return render_template('404.html') if os.path.exists(os.path.join(app.template_folder, '404.html')) else ("Not Found", 404)
    
    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"success": False, "error": "File too large. Maximum upload size: 100MB"}), 413
    
    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        logger.warning(f"Rate limit exceeded from IP: {request.remote_addr}")
        return jsonify({"success": False, "error": "Rate limit exceeded. Please try again later."}), 429
    
    @app.errorhandler(500)
    def internal_error(e):
        logger.exception(f"Internal server error: {e}")
        return jsonify({"success": False, "error": "Internal server error", "request_id": request.headers.get('X-Request-ID', 'unknown')}), 500
    
    @app.errorhandler(400)
    def bad_request(e):
        """Handle 400 errors - return JSON for API routes"""
        if request.path.startswith('/api/'):
            return jsonify({"error": "Bad request", "message": str(e)}), 400
        return str(e), 400
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Pass through HTTP errors
        if isinstance(e, HTTPException):
            return e
        
        # Log the error
        logger.exception(f"Unhandled exception: {e}")
        
        # Return JSON error for API calls
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({"error": "An unexpected error occurred"}), 500
        
        # Return HTML error for browser requests
        return "An unexpected error occurred", 500
    
    # PWA Routes
    @app.route('/offline')
    def offline():
        """Offline fallback page for PWA"""
        return render_template('offline.html')
    
    @app.route('/manifest.json')
    def pwa_manifest():
        """Serve PWA manifest (use static_folder so path works regardless of process cwd)."""
        return send_from_directory(
            app.static_folder, 'manifest.json', mimetype='application/manifest+json'
        )
    
    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon"""
        return send_from_directory(app.static_folder, 'logo.png', mimetype='image/png')

    # Register blueprints only if they were imported successfully.
    if hvac_mep_bp:
        # Exempt from CSRF (handles file uploads via API)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(hvac_mep_bp)
        
        app.register_blueprint(hvac_mep_bp, url_prefix='/hvac-mep')  # Must be /hvac-mep with dash
        logger.info("✓ Registered HVAC/MEP blueprint at /hvac-mep")
    else:
        # Provide a helpful placeholder endpoint so someone visiting knows the blueprint failed to import
        @app.route('/hvac-mep')
        def hvac_mep_missing():
            return (
                "HVAC & MEP module is not available on this deployment. "
                "Check server logs for import errors."
            ), 500

    if civil_bp:
        # Exempt from CSRF (handles file uploads via API)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(civil_bp)
        
        app.register_blueprint(civil_bp, url_prefix='/civil')
        logger.info("Registered blueprint: /civil")
    else:
        @app.route('/civil')
        def civil_missing():
            return (
                "Civil module is not available on this deployment. "
                "Check server logs for import errors."
            ), 500

    if cleaning_bp:
        # Exempt from CSRF (handles file uploads via API)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(cleaning_bp)
        
        app.register_blueprint(cleaning_bp, url_prefix='/cleaning')
        logger.info("Registered blueprint: /cleaning")
    else:
        @app.route('/cleaning')
        def cleaning_missing():
            return (
                "Cleaning module is not available on this deployment. "
                "Check server logs for import errors."
            ), 500

    # Register authentication blueprint
    if auth_bp:
        # Exempt auth blueprint from CSRF (uses JWT instead)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(auth_bp)
        
        app.register_blueprint(auth_bp)  # Already has /api/auth prefix
        logger.info("✅ Registered authentication blueprint at /api/auth")
    else:
        logger.warning("⚠️  Authentication blueprint not available - check imports")
    
    # Register admin blueprint
    if admin_bp:
        # Exempt admin API from CSRF (uses JWT instead)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(admin_bp)
        app.register_blueprint(admin_bp)  # Already has /api/admin prefix
        logger.info("✅ Registered admin blueprint at /api/admin")
    else:
        logger.warning("⚠️  Admin blueprint not available - check imports")
    
    # Register workflow blueprint
    if workflow_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(workflow_bp)
        app.register_blueprint(workflow_bp)  # Already has /api/workflow prefix
        logger.info("✅ Registered workflow blueprint at /api/workflow")
    else:
        logger.warning("⚠️  Workflow blueprint not available - check imports")

    # Register BD email module blueprint
    if bd_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(bd_bp)
        app.register_blueprint(bd_bp)
        logger.info("✅ Registered BD blueprint at /bd")
    else:
        logger.warning("⚠️  BD blueprint not available - check imports")

    # Register DocHub API blueprint
    if docs_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(docs_bp)
        app.register_blueprint(docs_bp)
        logger.info("✅ Registered DocHub API blueprint at /api/docs")
    else:
        logger.warning("⚠️  DocHub API blueprint not available - check imports")
    
    # Register HR module blueprint
    if hr_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(hr_bp)
        app.register_blueprint(hr_bp, url_prefix='/hr')
        # So /hr (no trailing slash) works: redirect to /hr/
        @app.route('/hr')
        def redirect_hr_to_slash():
            return redirect('/hr/', code=302)
        logger.info("✅ Registered HR blueprint at /hr")
    else:
        logger.warning("⚠️  HR blueprint not available - check imports")
    
    # Register Procurement module blueprint
    if procurement_module_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(procurement_module_bp)
        app.register_blueprint(procurement_module_bp, url_prefix='/procurement')
        logger.info("✅ Registered Procurement blueprint at /procurement")
    else:
        logger.warning("⚠️  Procurement blueprint not available - check imports")
    
    # Register Inspection Form blueprint
    if inspection_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(inspection_bp)
        app.register_blueprint(inspection_bp)
        @app.route('/inspection')
        def redirect_inspection_to_slash():
            return redirect('/inspection/', code=302)
        logger.info("✅ Registered Inspection blueprint at /inspection")
    else:
        logger.warning("⚠️  Inspection blueprint not available - check imports")

    # Register MMR blueprint
    if mmr_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(mmr_bp)
        app.register_blueprint(mmr_bp)
        logger.info("✅ Registered MMR blueprint at /admin/mmr")
        # Start APScheduler for daily report emails
        try:
            from module_mmr.scheduler import init_scheduler as init_mmr_scheduler
            init_mmr_scheduler(app)
        except Exception as sched_err:
            logger.warning(f"⚠️  MMR scheduler not started: {sched_err}")
    else:
        logger.warning("⚠️  MMR blueprint not available")

    # Register reports API blueprint for on-demand regeneration
    try:
        from app.reports_api import reports_bp
        
        # Exempt reports API from CSRF (uses JWT if needed)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(reports_bp)
        
        app.register_blueprint(reports_bp)
        logger.info("✅ Registered reports API at /api/reports")
    except Exception as e:
        logger.warning(f"⚠️  Reports API not available: {e}")
    
    # Temporary initialization endpoint - DISABLED FOR PRODUCTION SECURITY
    # Database already initialized on Render - no need for this endpoint
    # try:
    #     from temp_init import init_bp
    #     app.register_blueprint(init_bp)
    #     logger.warning("⚠️  TEMP INIT ENDPOINT ACTIVE - Visit /init-database-temp-delete-me once, then delete temp_init.py!")
    # except:
    #     pass  # File doesn't exist or already deleted (good!)

    # Security headers middleware
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    # Authentication routes
    @app.route('/login')
    def login_page():
        """Render login page"""
        return render_template('login.html')
    
    @app.route('/register')
    def register_page():
        """Render register page"""
        return render_template('register.html')
    
    @app.route('/logout')
    def logout_page():
        """Logout and redirect to login"""
        # Clear any local storage via JS or just redirect
        return render_template('logout.html')
    
    @app.route('/dashboard')
    def dashboard():
        """Protected dashboard - requires authentication"""
        return render_template('dashboard.html')
    
    @app.route('/about')
    def about():
        """About page - accessible to all users"""
        return render_template('about.html')
    
    @app.route('/workflow/pending-reviews')
    def pending_reviews():
        """Pending reviews page - requires reviewer authentication"""
        return render_template('pending_reviews.html')
    
    @app.route('/workflow/submitted-forms')
    def submitted_forms():
        """Submitted forms page - supervisors can view their submissions"""
        return render_template('submitted_forms.html')
    
    @app.route('/admin')
    def admin_root():
        """Convenience: many users type /admin — send them to the dashboard."""
        return redirect('/admin/dashboard')

    @app.route('/admin/dashboard')
    def admin_dashboard():
        """Admin dashboard - requires admin authentication"""
        return render_template('admin_dashboard.html', active_page='admin')

    @app.route('/admin/email-notifications')
    def admin_email_notifications():
        """Deep-link to the workflow email settings card (query param survives redirects reliably)."""
        return redirect('/admin/dashboard?focus=email-notifications')

    @app.route('/admin/mmr-chargeable')
    def mmr_chargeable_settings_page():
        """Report setting: chargeable / BaseUnit rules (admin UI)."""
        return render_template('mmr_chargeable_settings.html', active_page='mmr-chargeable')

    @app.route('/admin/devices')
    def admin_devices():
        """Device management - admin only"""
        return render_template('admin_device_management.html', active_page='devices')

    @app.route('/admin/bd')
    def admin_bd():
        """Business Development module - admin only"""
        return render_template('admin_bd_module.html', active_page='bd-module')

    @app.route('/admin/personal-progress')
    def admin_personal_progress():
        """Personal work-in-progress tracker — admin only"""
        return render_template('admin_personal_progress.html', active_page='personal-progress')

    @app.route('/dochub')
    def dochub():
        """DocHub module - all users with access"""
        return render_template('dochub.html', active_page='dochub')

    # Root route: Show login page
    @app.route('/')
    def index():
        """Redirect to login page"""
        from flask import redirect, url_for
        return redirect(url_for('login_page'))

    # Serve generated files (downloads) - DEPRECATED in production (use cloud URLs)
    # This route is kept for backward compatibility in development only
    GENERATED_DIR_NAME = os.path.basename(GENERATED_DIR.rstrip(os.sep))
    @app.route(f'/{GENERATED_DIR_NAME}/<path:filename>')
    def download_generated(filename):
        flask_env = app.config.get('FLASK_ENV', 'development')
        
        # In production, files should be served from cloud storage
        if flask_env == 'production':
            logger.warning(f"Attempted to access local file in production: {filename}")
            return jsonify({
                'success': False,
                'error': 'File serving from local filesystem is not available in production. Use cloud URLs instead.'
            }), 404
        
        # Development fallback - serve from local filesystem
        from common.security import safe_path_join
        try:
            safe_path = safe_path_join(GENERATED_DIR, filename)
            if not os.path.exists(safe_path):
                logger.warning(f"File not found: {filename}")
                abort(404)
            logger.info(f"Serving file from local filesystem (development): {filename}")
            return send_from_directory(GENERATED_DIR, filename, as_attachment=False)
        except ValueError as e:
            logger.warning(f"Path traversal attempt blocked: {filename}")
            abort(403)

    # Health check endpoint for monitoring
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint for monitoring and load balancers"""
        try:
            # Check database connection
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            db_status = 'healthy'
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            db_status = 'unhealthy'
        
        health_status = {
            'status': 'healthy' if db_status == 'healthy' else 'degraded',
            'database': db_status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        status_code = 200 if health_status['status'] == 'healthy' else 503
        return jsonify(health_status), status_code

    return app


if __name__ == '__main__':
    app = create_app()
    # For local development use debug=True. Remove or set False in production.
    app.run(debug=False, host='0.0.0.0', port=5000)