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
auth_bp = None
docs_bp = None

try:
    from module_hvac_mep.routes import hvac_mep_bp  # noqa: F401
    logger.info("Imported module_hvac_mep.routes.hvac_mep_bp")
except Exception as e:
    logger.exception("Could not import module_hvac_mep.routes.hvac_mep_bp: %s", e)
    hvac_mep_bp = None

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

# Store Module
store_module_bp = None
try:
    from module_store.routes import store_bp as store_module_bp  # noqa: F401
    logger.info("Imported module_store.routes.store_bp")
except Exception as e:
    logger.exception("Could not import module_store.routes.store_bp: %s", e)
    store_module_bp = None

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

# Ticketing / Work Order Module
ticketing_bp = None
try:
    from module_ticketing.routes import ticketing_bp  # noqa: F401
    logger.info("Imported module_ticketing.routes.ticketing_bp")
except Exception as e:
    logger.exception("Could not import module_ticketing.routes.ticketing_bp: %s", e)
    ticketing_bp = None

# Operations Module (Over Time + Trading Invoices)
operations_bp = None
try:
    from module_operations.routes import operations_bp  # noqa: F401
    logger.info("Imported module_operations.routes.operations_bp")
except Exception as e:
    logger.exception("Could not import module_operations.routes.operations_bp: %s", e)
    operations_bp = None

# Finance module (align with Amaan / local run)
finance_bp = None
try:
    from module_finance.routes import finance_bp  # noqa: F401
    logger.info("Imported module_finance.routes.finance_bp")
except Exception as e:
    logger.exception("Could not import module_finance.routes.finance_bp: %s", e)
    finance_bp = None

# Live Assistant module
assistant_bp = None
try:
    from module_assistant.routes import assistant_bp  # noqa: F401
    logger.info("Imported module_assistant.routes.assistant_bp")
except Exception as e:
    logger.exception("Could not import module_assistant.routes.assistant_bp: %s", e)
    assistant_bp = None

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

    # Trust the Render/reverse-proxy forwarded headers so request.remote_addr is the real
    # client IP (used for rate-limit keying and audit logs) and request.is_secure reflects
    # the client's HTTPS, not the internal HTTP hop. One proxy hop on Render.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Some container images lack /etc/mime.types; browsers enforce nosniff on CSS/JS.
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("application/json", ".json")

    # Inject `now` into every Jinja template so {{ now().year }} works everywhere,
    # including standalone templates that don't extend base.html.
    app.jinja_env.globals['now'] = lambda: datetime.now(timezone.utc)

    # Cache-bust static assets: append ?v=<file-mtime> to every url_for('static', ...)
    # so CSS/JS edits are picked up immediately without a hard refresh. The query
    # changes only when the file changes, so unchanged assets stay cacheable.
    @app.url_defaults
    def _static_cache_bust(endpoint, values):
        if endpoint == 'static' and values.get('filename') and 'v' not in values:
            try:
                fpath = os.path.join(app.static_folder, values['filename'])
                values['v'] = int(os.path.getmtime(fpath))
            except OSError:
                pass

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
    # Cookie JWT CSRF: on by default in production (see config.JWT_COOKIE_CSRF_PROTECT).
    # SPA Bearer-header auth is unaffected; cookie-only mutating requests need X-CSRF-TOKEN.
    if 'JWT_COOKIE_CSRF_PROTECT' in app.config:
        app.config['JWT_COOKIE_CSRF_PROTECT'] = bool(app.config['JWT_COOKIE_CSRF_PROTECT'])
    else:
        _env = (os.environ.get('FLASK_ENV') or '').lower()
        _default = 'true' if _env == 'production' else 'false'
        app.config['JWT_COOKIE_CSRF_PROTECT'] = (
            os.environ.get('JWT_COOKIE_CSRF_PROTECT', _default).lower() == 'true'
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
    # Short-TTL in-process cache reduces per-request DB hits; miss falls through to DB.
    _jwt_blocklist_cache = {}
    _JWT_BLOCKLIST_TTL_SEC = int(os.environ.get('JWT_BLOCKLIST_CACHE_TTL', '45') or '45')

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """Return True if the access token must be rejected (revoked). Must not raise — that becomes HTTP 500."""
        try:
            from app.models import Session
            from common.jwt_session import sync_access_session_row
            import time as _time

            if jwt_payload.get('type') == 'refresh':
                return False
            jti = jwt_payload.get('jti')
            if not jti:
                return True

            now = _time.time()
            cached = _jwt_blocklist_cache.get(jti)
            if cached is not None:
                revoked, expires_at = cached
                if expires_at > now:
                    return revoked

            session = Session.query.filter_by(token_jti=jti).first()
            if session is None:
                session = sync_access_session_row(jti, jwt_payload)
            if session is None:
                logger.warning(
                    "JWT blocklist: missing session for jti=%s sub=%s — token treated as revoked",
                    jti,
                    jwt_payload.get('sub'),
                )
                revoked = True
            else:
                revoked = bool(session.is_revoked)

            # Bound cache size (simple eviction of oldest half if large)
            if len(_jwt_blocklist_cache) > 5000:
                _jwt_blocklist_cache.clear()
            _jwt_blocklist_cache[jti] = (revoked, now + max(5, _JWT_BLOCKLIST_TTL_SEC))
            return revoked
        except Exception as exc:
            logger.exception("JWT blocklist check failed; treating token as revoked: %s", exc)
            return True
    
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
                # Register models on metadata before create_all (includes Employee directory)
                from app.models import (  # noqa: F401
                    DocHubDocument,
                    DocHubStar,
                    EmailOtp,
                    Employee,
                    Technician,
                    User,
                )
                db.create_all()
                logger.info("✅ All database tables verified/created")
            except Exception as create_error:
                logger.warning(f"Table creation check: {create_error}")
                # Continue anyway - tables might already exist
            
            # Step 2: Database migrations are now handled by Flask-Migrate
            # Run migrations manually using: flask db upgrade
            # This ensures version-controlled, reversible migrations
            logger.info("✅ Database tables verified. Use 'flask db upgrade' to apply migrations.")
            
            # Step 2.5: Inline ALTER TABLE (deprecated). Skip with FLASK_SKIP_INLINE_DDL=1 after Alembic.
            _skip_inline_ddl = (os.environ.get('FLASK_SKIP_INLINE_DDL') or '').lower() in ('1', 'true', 'yes')
            if _skip_inline_ddl:
                logger.info('Skipping inline ALTER TABLE DDL (FLASK_SKIP_INLINE_DDL set); use flask db upgrade')
            else:
                logger.warning('Inline DDL is deprecated — set FLASK_SKIP_INLINE_DDL=1 after applying Alembic migrations')
                # Step 2.5: Add missing columns if tables exist (one-time migration for existing databases)
                inspector = inspect(db.engine)
                if 'users' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('users')]
                    missing_columns = []
                
                    # Check for designation column
                    if 'designation' not in columns:
                        missing_columns.append(('designation', 'VARCHAR(20) DEFAULT NULL'))

                    # Operations module access flag
                    if 'access_operations' not in columns:
                        missing_columns.append(('access_operations', 'BOOLEAN DEFAULT 0'))

                    # Operations: full (create/edit) vs view-only
                    if 'access_operations_manage' not in columns:
                        missing_columns.append(('access_operations_manage', 'BOOLEAN DEFAULT 0'))

                    if 'admin_visible_password' not in columns:
                        missing_columns.append(('admin_visible_password', 'VARCHAR(255)'))
                    if 'password_changed_at' not in columns:
                        missing_columns.append(('password_changed_at', 'TIMESTAMP'))
                    if 'password_locked' not in columns:
                        missing_columns.append(('password_locked', 'BOOLEAN DEFAULT 0'))
                    if 'access_finance' not in columns:
                        missing_columns.append(('access_finance', 'BOOLEAN DEFAULT 0'))
                    if 'access_sales_manager' not in columns:
                        missing_columns.append(('access_sales_manager', 'BOOLEAN DEFAULT 0'))
                    if 'access_quotations' not in columns:
                        missing_columns.append(('access_quotations', 'BOOLEAN DEFAULT 0'))
                    if 'access_operations_overtime' not in columns:
                        missing_columns.append(('access_operations_overtime', 'BOOLEAN DEFAULT 0'))
                    if 'access_operations_invoices' not in columns:
                        missing_columns.append(('access_operations_invoices', 'BOOLEAN DEFAULT 0'))
                    if 'access_operations_clients' not in columns:
                        missing_columns.append(('access_operations_clients', 'BOOLEAN DEFAULT 0'))
                    if 'access_operations_cheques' not in columns:
                        missing_columns.append(('access_operations_cheques', 'BOOLEAN DEFAULT 0'))
                    if 'access_operations_timesheet' not in columns:
                        missing_columns.append(('access_operations_timesheet', 'BOOLEAN DEFAULT 0'))
                    if 'access_operations_attendance' not in columns:
                        missing_columns.append(('access_operations_attendance', 'BOOLEAN DEFAULT 0'))
                    if 'sick_leave_days' not in columns:
                        missing_columns.append(('sick_leave_days', 'INTEGER'))
                    if 'insurance_details' not in columns:
                        missing_columns.append(('insurance_details', 'VARCHAR(255)'))
                    if 'admin_protect_pin_hash' not in columns:
                        missing_columns.append(('admin_protect_pin_hash', 'VARCHAR(255)'))
                    if 'access_fire_app' not in columns:
                        missing_columns.append(('access_fire_app', 'BOOLEAN DEFAULT 0'))
                    if 'access_municipality_app' not in columns:
                        missing_columns.append(('access_municipality_app', 'BOOLEAN DEFAULT 0'))

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

                    try:
                        from app.models import User as _UserBF
                        dirty = False
                        for _u in _UserBF.query.filter_by(access_operations=True).all():
                            if not (
                                getattr(_u, 'access_operations_overtime', False)
                                or getattr(_u, 'access_operations_timesheet', False)
                                or getattr(_u, 'access_operations_attendance', False)
                                or getattr(_u, 'access_operations_invoices', False)
                                or getattr(_u, 'access_operations_clients', False)
                                or getattr(_u, 'access_operations_cheques', False)
                            ):
                                _u.access_operations_overtime = True
                                _u.access_operations_timesheet = True
                                _u.access_operations_attendance = True
                                _u.access_operations_invoices = True
                                _u.access_operations_clients = True
                                _u.access_operations_cheques = True
                                dirty = True
                        if dirty:
                            db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        logger.warning(f"Could not backfill operations sub-module access (non-critical): {e}")
            
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
                        ('manager_reviewed_at', 'TIMESTAMP DEFAULT NULL'),
                        ('doc_number', 'VARCHAR(20) DEFAULT NULL')
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

                if 'tickets' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('tickets')]
                    if 'source_inspection_notif_id' not in columns:
                        logger.info("Adding source_inspection_notif_id column to tickets table")
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text("ALTER TABLE tickets ADD COLUMN source_inspection_notif_id INTEGER"))
                            logger.info("✅ Added source_inspection_notif_id to tickets")
                        except Exception as col_error:
                            err = str(col_error).lower()
                            if 'already exists' in err or 'duplicate' in err:
                                logger.info("Column source_inspection_notif_id already exists")
                            else:
                                logger.warning(f"Could not add source_inspection_notif_id: {col_error}")

                # Inspection outcome columns on inspection_notifications (CD pass/fail branching)
                if 'inspection_notifications' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('inspection_notifications')]
                    outcome_cols = {
                        'outcome': 'VARCHAR(10)',
                        'rectify_by': 'VARCHAR(20)',
                        'outcome_notes': 'TEXT',
                        'outcome_recorded_at': 'DATETIME',
                        'outcome_recorded_by_id': 'INTEGER',
                        'reinspection_count': 'INTEGER DEFAULT 0',
                    }
                    for col_name, col_def in outcome_cols.items():
                        if col_name not in columns:
                            logger.info(f"Adding {col_name} column to inspection_notifications table")
                            try:
                                with db.engine.begin() as conn:
                                    conn.execute(text(f"ALTER TABLE inspection_notifications ADD COLUMN {col_name} {col_def}"))
                                logger.info(f"✅ Added {col_name} to inspection_notifications")
                            except Exception as col_error:
                                err = str(col_error).lower()
                                if 'already exists' in err or 'duplicate' in err:
                                    logger.info(f"Column {col_name} already exists")
                                else:
                                    logger.warning(f"Could not add {col_name}: {col_error}")

                # quotations: Excel-aligned letter fields (ref, discount, sections, signatures)
                if 'quotations' in inspector.get_table_names():
                    q_columns = {col['name'] for col in inspector.get_columns('quotations')}
                    quote_extra = {
                        'ref_no': 'VARCHAR(80)',
                        'kind_attn': 'VARCHAR(160)',
                        'client_tel': 'VARCHAR(60)',
                        'subject': 'VARCHAR(500)',
                        'project_name': 'VARCHAR(255)',
                        'intro_text': 'TEXT',
                        'discount_amount': 'FLOAT DEFAULT 0',
                        'amount_in_words': 'VARCHAR(400)',
                        'notes_text': 'TEXT',
                        'exclusions_text': 'TEXT',
                        'terms_text': 'TEXT',
                        'signatory_name': 'VARCHAR(160)',
                        'signatory_email': 'VARCHAR(255)',
                        'signatory_phone': 'VARCHAR(60)',
                        'signoff_label': 'VARCHAR(120)',
                        'prepared_signature': 'TEXT',
                    }
                    for col_name, col_def in quote_extra.items():
                        if col_name not in q_columns:
                            try:
                                with db.engine.begin() as conn:
                                    conn.execute(text(
                                        f"ALTER TABLE quotations ADD COLUMN {col_name} {col_def}"
                                    ))
                                logger.info(f"✅ Added {col_name} to quotations")
                            except Exception as col_error:
                                err = str(col_error).lower()
                                if 'already exists' in err or 'duplicate' in err:
                                    logger.info(f"Column {col_name} already exists on quotations")
                                else:
                                    logger.warning(f"Could not add quotations.{col_name}: {col_error}")

                # finance_contracts: account handler + shorter public ids
                if 'finance_contracts' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('finance_contracts')]
                    if 'account_handler' not in columns:
                        logger.info("Adding account_handler column to finance_contracts table")
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text(
                                    "ALTER TABLE finance_contracts ADD COLUMN account_handler VARCHAR(255)"
                                ))
                            logger.info("✅ Added account_handler to finance_contracts")
                        except Exception as col_error:
                            err = str(col_error).lower()
                            if 'already exists' in err or 'duplicate' in err:
                                logger.info("Column account_handler already exists")
                            else:
                                logger.warning(f"Could not add account_handler: {col_error}")
                    try:
                        from app.models import FinanceContract as _FinCon
                        import re as _re
                        dirty = False
                        contracts = _FinCon.query.all()
                        used_ids = {(c.contract_id or '').upper() for c in contracts}
                        for c in contracts:
                            cid = (c.contract_id or '').strip().upper()
                            if cid.startswith('FIN-CON-'):
                                hex_part = cid[8:]
                                candidate = f"FC-{hex_part[:5]}" if hex_part else ''
                                if candidate and candidate not in used_ids:
                                    used_ids.discard(cid)
                                    used_ids.add(candidate)
                                    c.contract_id = candidate
                                    dirty = True
                            notes = c.notes or ''
                            if not (c.account_handler or '').strip() and notes:
                                m = _re.search(r'(?im)^\s*PM:\s*(.+)$', notes)
                                if m:
                                    c.account_handler = m.group(1).strip()[:255]
                                    dirty = True
                        if dirty:
                            db.session.commit()
                            logger.info("✅ Migrated finance contract ids / account handlers")
                    except Exception as mig_err:
                        db.session.rollback()
                        logger.warning(f"Finance contract migration skipped: {mig_err}")

                if 'hiring_candidates' in inspector.get_table_names():
                    hc_cols = [col['name'] for col in inspector.get_columns('hiring_candidates')]
                    if 'pipeline_status' not in hc_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text(
                                    "ALTER TABLE hiring_candidates "
                                    "ADD COLUMN pipeline_status VARCHAR(40) "
                                    "DEFAULT 'interview_completed'"
                                ))
                            logger.info("✅ Added pipeline_status to hiring_candidates")
                        except Exception as col_error:
                            err = str(col_error).lower()
                            if 'already exists' in err or 'duplicate' in err:
                                logger.info("Column pipeline_status already exists")
                            else:
                                logger.warning(f"Could not add pipeline_status: {col_error}")
                    for col_name, col_sql in (
                        ('replacement_name', 'VARCHAR(200)'),
                        ('replacement_employee_id', 'VARCHAR(80)'),
                        ('comments', 'TEXT'),
                    ):
                        if col_name not in hc_cols:
                            try:
                                with db.engine.begin() as conn:
                                    conn.execute(text(
                                        f"ALTER TABLE hiring_candidates ADD COLUMN {col_name} {col_sql}"
                                    ))
                                logger.info(f"✅ Added {col_name} to hiring_candidates")
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
                    )
                    # Use environment variable for default password, or generate random one
                    import secrets
                    default_password = os.environ.get('DEFAULT_ADMIN_PASSWORD', None)
                    if not default_password:
                        # Generate a secure random password if not set
                        default_password = secrets.token_urlsafe(16)
                        logger.warning("⚠️  No DEFAULT_ADMIN_PASSWORD set - using generated password")
                        logger.warning("⚠️  SECURITY: Generated admin password is not logged. Set DEFAULT_ADMIN_PASSWORD or reset via admin tools.")
                    
                    admin.set_password(default_password)
                    admin.password_changed = False  # Force password change on first login
                    db.session.add(admin)
                    db.session.commit()
                    logger.info("✅ Default admin user created")
                    if not os.environ.get('DEFAULT_ADMIN_PASSWORD'):
                        logger.warning("⚠️  Default admin was seeded with a generated password (not logged). Set DEFAULT_ADMIN_PASSWORD or use password reset.")
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
                         '<h2>1. Company Overview</h2><p>Amaan Facilities Management delivers excellence in facility services across the UAE.</p>'
                         '<h2>2. Your First Week</h2><ul><li><strong>Day 1:</strong> Meet your team lead, set up workstation</li>'
                         '<li><strong>Day 2:</strong> System access, security training</li><li><strong>Day 3-5:</strong> Department walkthroughs</li></ul>'
                         '<h2>3. Key Contacts</h2><ul><li><strong>HR:</strong> arshith@injaaz.ae</li><li><strong>IT:</strong> +971 50 156 0277</li></ul>'),
                        ('Project Services Agreement Template', 'contracts', 'review',
                         '<h1>Project Services Agreement</h1><p><em>Agreement between Service Provider and Client.</em></p>'
                         '<h2>1. Parties</h2><p><strong>Service Provider:</strong> Amaan FM.<br/><strong>Client:</strong> [Client Name].</p>'
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

    @app.context_processor
    def inject_kynvera_hub():
        from common.kynvera_hub import hub_public_config
        return {'hub': hub_public_config()}
    
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
    
    # Setup rate limiting with Redis (memory:// fallback when Redis is unavailable)
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        
        # Get Redis URL from app config or environment
        redis_url = app.config.get('REDIS_URL') or os.environ.get('RATELIMIT_STORAGE_URL') or os.environ.get('REDIS_URL')
        if redis_url:
            redis_url = redis_url.strip()
        
        storage_uri = 'memory://'
        if redis_url:
            try:
                # Test Redis connection first (Upstash: use rediss:// URL from dashboard)
                import redis
                r = redis.from_url(redis_url, socket_connect_timeout=5)
                r.ping()
                storage_uri = redis_url
                logger.info("✓ Redis connection test successful")
            except Exception as redis_error:
                logger.warning(f"⚠️  Redis connection failed - using in-memory rate limiting: {redis_error}")
        else:
            logger.info("✓ Rate limiting using in-memory storage (no Redis URL configured)")

        testing = (
            app.config.get('TESTING')
            or (os.environ.get('TESTING') or '').lower() in ('1', 'true', 'yes')
            or (os.environ.get('FLASK_ENV') or '').lower() == 'testing'
        )
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[os.environ.get('RATELIMIT_DEFAULT', '100 per hour')],
            storage_uri=storage_uri,
            strategy="fixed-window",
            enabled=not testing,
        )
        app.limiter = limiter
        if testing:
            logger.info("✓ Rate limiting installed but disabled (TESTING)")
        elif storage_uri == 'memory://':
            logger.info("✓ Rate limiting enabled with in-memory storage (per-process; use Redis for multi-worker)")
        else:
            logger.info("✓ Rate limiting enabled with Redis storage")
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
        if os.path.exists(os.path.join(app.template_folder, '404.html')):
            return render_template('404.html'), 404
        return ("Not Found", 404)
    
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
        logger.info("✓ Registered Fire Systems blueprint at /hvac-mep")
    else:
        # Provide a helpful placeholder endpoint so someone visiting knows the blueprint failed to import
        @app.route('/hvac-mep')
        def hvac_mep_missing():
            return (
                "Fire Systems module is not available on this deployment. "
                "Check server logs for import errors."
            ), 500

    # Register authentication blueprint
    if auth_bp:
        # Exempt auth blueprint from CSRF (uses JWT instead)
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(auth_bp)
        
        app.register_blueprint(auth_bp)  # Already has /api/auth prefix
        try:
            from app.auth.routes import apply_deferred_rate_limits
            n = apply_deferred_rate_limits(app)
            if n:
                logger.info("✓ Applied deferred rate limits to %s auth view(s)", n)
        except Exception as rl_err:
            logger.warning("Could not apply deferred rate limits: %s", rl_err)
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
    
    # Register Store module blueprint
    if store_module_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(store_module_bp)
        app.register_blueprint(store_module_bp, url_prefix='/store')
        logger.info("✅ Registered Store blueprint at /store")
    else:
        logger.warning("⚠️  Store blueprint not available - check imports")
    
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

    # Register Email Automation blueprint
    if mmr_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(mmr_bp)
        app.register_blueprint(mmr_bp)
        logger.info("✅ Registered Email Automation blueprint at /admin/mmr")
        # Start APScheduler for email automations
        try:
            from module_mmr.scheduler import init_scheduler as init_mmr_scheduler
            init_mmr_scheduler(app)
        except Exception as sched_err:
            logger.warning(f"⚠️  Email Automation scheduler not started: {sched_err}")
    else:
        logger.warning("⚠️  Email Automation blueprint not available")

    # Register Ticketing blueprint
    if ticketing_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(ticketing_bp)
        app.register_blueprint(ticketing_bp, url_prefix='/tickets')
        logger.info("✅ Registered Ticketing blueprint at /tickets")
    else:
        logger.warning("⚠️  Ticketing blueprint not available - check imports")

    # Register Operations blueprint (Over Time + Trading Invoices)
    if operations_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(operations_bp)
        app.register_blueprint(operations_bp)
        logger.info("✅ Registered Operations blueprint at /operations")
    else:
        logger.warning("⚠️  Operations blueprint not available - check imports")

    # Register Finance blueprint (parity with Amaan local run)
    if finance_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(finance_bp)
        app.register_blueprint(finance_bp)
        logger.info("✅ Registered Finance blueprint at /finance")
    else:
        logger.warning("⚠️  Finance blueprint not available - check imports")

    # Register Assistant blueprint
    if assistant_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(assistant_bp)
        app.register_blueprint(assistant_bp)
        logger.info("✅ Registered Assistant blueprint")
    else:
        logger.warning("⚠️  Assistant blueprint not available - check imports")

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

    # Apply deferred limits/exemptions after all blueprints are registered
    try:
        from app.auth.routes import apply_deferred_rate_limits
        n = apply_deferred_rate_limits(app)
        if n:
            logger.info("✓ Applied deferred rate limits/exemptions to %s view(s)", n)
    except Exception as rl_err:
        logger.warning("Could not apply deferred rate limits: %s", rl_err)
    
    # Temporary initialization endpoint - DISABLED FOR PRODUCTION SECURITY
    # Database already initialized on Render - no need for this endpoint
    # try:
    #     from temp_init import init_bp
    #     app.register_blueprint(init_bp)
    #     logger.warning("⚠️  TEMP INIT ENDPOINT ACTIVE - Visit /init-database-temp-delete-me once, then delete temp_init.py!")
    # except:
    #     pass  # File doesn't exist or already deleted (good!)

    # Security headers middleware
    _is_production = (os.environ.get('FLASK_ENV') or os.environ.get('ENV') or '').lower() == 'production'

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # Don't leak full URLs (which may carry ids) to third-party origins.
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        # Disable powerful features the app doesn't use. Camera is intentionally left
        # allowed so photo-capture inputs on the inspection forms keep working.
        response.headers.setdefault(
            'Permissions-Policy',
            'geolocation=(), microphone=(), payment=(), usb=(), magnetometer=()'
        )
        # Force HTTPS for a year once served over TLS (production/proxy only). Sending
        # this over plain HTTP is ignored by browsers, but we gate it to be correct.
        if _is_production and request.is_secure:
            response.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
            )
        # Content-Security-Policy shipped in REPORT-ONLY mode: browsers report what would
        # be blocked without blocking anything, so we can tighten it later with zero risk
        # of breaking inline scripts or the Cloudinary widget. Flip the header name to
        # 'Content-Security-Policy' (enforcing) after reviewing reports.
        response.headers.setdefault(
            'Content-Security-Policy-Report-Only',
            "default-src 'self'; "
            "img-src 'self' data: blob: https://res.cloudinary.com https://*.cloudinary.com; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "connect-src 'self' https://api.cloudinary.com https://*.cloudinary.com; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "object-src 'none'"
        )
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
        from common.kynvera_hub import hub_public_config
        return render_template('dashboard.html', hub=hub_public_config())

    @app.route('/api/hub/config')
    def hub_config():
        """Public hub URL config for the portal launcher (no secrets)."""
        from common.kynvera_hub import hub_public_config
        return jsonify(hub_public_config())

    @app.route('/launch/fire')
    def launch_fire():
        """Sign-in bridge → Fire System Application SSO."""
        from common.kynvera_hub import hub_public_config
        return render_template(
            'launch_app.html',
            hub=hub_public_config(),
            app_key='fire',
            app_label='Fire System',
            launch_path='/launch/fire',
            access_flag='access_fire_app',
        )

    @app.route('/launch/municipality')
    def launch_municipality():
        """Sign-in bridge → Ajman Municipality Application SSO."""
        from common.kynvera_hub import hub_public_config
        return render_template(
            'launch_app.html',
            hub=hub_public_config(),
            app_key='municipality',
            app_label='Ajman Municipality',
            launch_path='/launch/municipality',
            access_flag='access_municipality_app',
        )

    @app.route('/sso/consume')
    def sso_consume():
        """Accept a JWT from the Kynvera hub and establish a local session."""
        from flask_jwt_extended import decode_token
        from common.kynvera_hub import sanitize_next_path

        token = (request.args.get('token') or '').strip()
        next_path = sanitize_next_path(request.args.get('next'), '/dashboard')
        error = None
        if not token:
            error = 'Missing access token.'
        else:
            try:
                decode_token(token)
            except Exception:
                error = 'Invalid or expired token. Please sign in again from Kynvera Home.'
        return render_template(
            'sso_consume.html',
            token='' if error else token,
            next_url=next_path,
            error=error,
        )
    
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
        """Workflow email recipient settings now live on the Email Automation page."""
        return redirect('/admin/mmr/')

    @app.route('/admin/devices')
    def admin_devices():
        """Device management - admin only"""
        return render_template('admin_device_management.html', active_page='devices')

    @app.route('/admin/bd')
    def admin_bd():
        """Sales module - admin only"""
        return render_template('admin_bd_module.html', active_page='bd-module')

    @app.route('/admin/bd/projects/<int:project_id>')
    def admin_bd_project_detail(project_id):
        """Deep-link into Sales project bento (keeps the list page shell)."""
        return redirect(f'/admin/bd?project={int(project_id)}')

    @app.route('/admin/personal-progress')
    def admin_personal_progress():
        """Personal work-in-progress tracker — admin only"""
        return render_template('admin_personal_progress.html', active_page='personal-progress')

    @app.route('/admin/team-management')
    def admin_team_management():
        """Team & technician management — admin only"""
        return render_template('admin_team_management.html', active_page='team-management')

    @app.route('/dochub')
    def dochub():
        """DocHub module - all users with access"""
        return render_template('dochub.html', active_page='dochub')

    # Root route: public Kynvera landing (2 applications)
    @app.route('/')
    def index():
        """Public marketing landing — Fire System + Ajman Municipality launchers."""
        from common.kynvera_hub import hub_public_config
        return render_template('landing.html', hub=hub_public_config())

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
    import subprocess
    try:
        branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        branch = 'unknown'
    print(f"\n  Running on branch: [{branch}]\n")
    app = create_app()
    # For local development use debug=True. Remove or set False in production.
    app.run(debug=False, host='0.0.0.0', port=5001)
