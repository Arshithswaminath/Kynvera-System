import os
import sys
import logging
import mimetypes
import subprocess
from datetime import datetime, timezone
from flask import Flask, send_from_directory, abort, render_template, jsonify, request, redirect, make_response, current_app, Response, url_for
from concurrent.futures import ThreadPoolExecutor
from werkzeug.exceptions import HTTPException
from flask_jwt_extended import JWTManager, jwt_required
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

# Optional Sentry error tracking. No-op when SENTRY_DSN is not set or the SDK
# is not installed — added so we get observability in production without
# forcing the dependency in development.
_sentry_dsn = (os.environ.get("SENTRY_DSN") or "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FlaskIntegration()],
            environment=os.environ.get("FLASK_ENV", "development"),
            release=os.environ.get("APP_VERSION") or None,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            send_default_pii=False,
        )
        logger.info("Sentry initialized")
    except Exception as _sentry_err:
        logger.warning(f"Sentry not initialized: {_sentry_err}")

# Try importing blueprints; if any import fails we log and continue so the app still starts.
auth_bp = None
bd_bp = None
docs_bp = None

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

# Files Module (Finder + optional Google Drive sync)
files_module_bp = None
try:
    from module_files.routes import files_bp as files_module_bp  # noqa: F401
    logger.info("Imported module_files.routes.files_bp")
except Exception as e:
    logger.exception("Could not import module_files.routes.files_bp: %s", e)
    files_module_bp = None

# Automations hub (daily HR Excel backup + future jobs)
automations_bp = None
try:
    from app.automations.routes import automations_bp  # noqa: F401
    logger.info("Imported app.automations.routes.automations_bp")
except Exception as e:
    logger.exception("Could not import app.automations.routes.automations_bp: %s", e)
    automations_bp = None

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

# QHSI Module (Quality, Hospitality, Safety & Inspection)
qhsi_bp = None
try:
    from module_qhsi.routes import qhsi_bp  # noqa: F401
    logger.info("Imported module_qhsi.routes.qhsi_bp")
except Exception as e:
    logger.exception("Could not import module_qhsi.routes.qhsi_bp: %s", e)
    qhsi_bp = None

# Live Assistant (no-LLM v1)
assistant_bp = None
try:
    from module_assistant.routes import assistant_bp  # noqa: F401
    logger.info("Imported module_assistant.routes.assistant_bp")
except Exception as e:
    logger.exception("Could not import module_assistant.routes.assistant_bp: %s", e)
    assistant_bp = None

# FM Assets registry
assets_bp = None
try:
    from module_assets.routes import assets_bp  # noqa: F401
    logger.info("Imported module_assets.routes.assets_bp")
except Exception as e:
    logger.exception("Could not import module_assets.routes.assets_bp: %s", e)
    assets_bp = None

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
    def _is_html_page_request():
        """True for full-page navigations that should silently refresh / redirect to login.

        API endpoints (JSON) are excluded — those return 401 so the client-side
        JS refresh flow can handle them. The two workflow "page render" routes
        live under /api/ but actually serve HTML, so they count as pages.
        """
        page_render_routes = ['/api/workflow/history', '/api/workflow/pending-reviews']
        if request.path in page_render_routes:
            return True
        if request.path.startswith('/api/') or '/api/' in request.path:
            return False
        return True

    def _silent_refresh_or_login():
        """Try to mint a new access token from the refresh cookie; else go to login.

        Used for HTML page navigations whose ACCESS token has expired or is
        missing. On a successful refresh we redirect back to the originally
        requested URL with a fresh access cookie attached, so the user never
        sees the login screen as long as their refresh token is still valid.
        """
        from flask import redirect, url_for
        from common.jwt_session import mint_access_token_from_refresh_cookie
        from flask_jwt_extended import set_access_cookies

        # Only GET navigations are safe to transparently replay via redirect.
        if request.method == 'GET':
            new_access_token = mint_access_token_from_refresh_cookie()
            if new_access_token:
                response = redirect(request.full_path if request.query_string else request.path)
                set_access_cookies(response, new_access_token)
                return response, 302
        return redirect(url_for('login_page')), 302

    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        """Handle missing JWT token"""
        if _is_html_page_request():
            return _silent_refresh_or_login()
        return jsonify({"success": False, "error": "Authentication required"}), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        """Handle invalid JWT token"""
        if _is_html_page_request():
            return _silent_refresh_or_login()
        return jsonify({"success": False, "error": "Invalid token"}), 401
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """Handle expired JWT token"""
        if _is_html_page_request():
            return _silent_refresh_or_login()
        return jsonify({"success": False, "error": "Token has expired"}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        """Signed-out / revoked tokens must not silently mint a new session."""
        if _is_html_page_request():
            from flask import redirect, url_for
            return redirect(url_for('login_page')), 302
        return jsonify({"success": False, "error": "Token has been revoked"}), 401
    
    # JWT token verification callback (check if token is revoked)
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """Return True if the access token must be rejected (revoked). Must not raise — that becomes HTTP 500."""
        try:
            from app.models import Session
            from common.jwt_session import sync_access_session_row

            jti = jwt_payload.get('jti')
            if not jti:
                return True
            is_refresh = jwt_payload.get('type') == 'refresh'
            session = Session.query.filter_by(token_jti=jti).first()
            # Only access tokens get auto-synced if their Session row is
            # missing (legacy tokens issued before this change). Refresh
            # tokens MUST have been recorded by /login or /refresh — a
            # missing row means the token is unknown and is treated as
            # revoked.
            if session is None and not is_refresh:
                session = sync_access_session_row(jti, jwt_payload)
            if session is None:
                logger.warning(
                    "JWT blocklist: missing session for jti=%s sub=%s — token treated as revoked",
                    jti,
                    jwt_payload.get('sub'),
                )
                return True
            return session.is_revoked
        except Exception as exc:
            logger.exception("JWT blocklist check failed; treating token as revoked: %s", exc)
            return True
    
    logger.info("✅ Database and JWT initialized")
    
    # Automatic database initialization and migration (fully self-contained for Render)
    if app.config.get('KYNVERA_MARKETING_ONLY'):
        logger.info("KYNVERA_MARKETING_ONLY: public landing site; skipping database bootstrap")
    else:
        with app.app_context():
            try:
                import time
                from sqlalchemy import inspect, text
            
                # Retry logic for database connection (Render databases may need a moment).
                # Each attempt is capped by SQLALCHEMY connect_timeout (10s) so a bad
                # DATABASE_URL cannot stall past Render's port-scan window.
                max_retries = 5
                retry_delay = 2
                inspector = None

                logger.info("Connecting to database (attempt 1/%s)...", max_retries)
                sys.stdout.flush()
                for attempt in range(max_retries):
                    try:
                        inspector = inspect(db.engine)
                        # Test connection by getting table names
                        inspector.get_table_names()
                        logger.info("✅ Database connection verified")
                        sys.stdout.flush()
                        break
                    except Exception as conn_error:
                        if attempt < max_retries - 1:
                            logger.info(
                                "Database connection attempt %s/%s failed (%s), retrying in %ss...",
                                attempt + 1,
                                max_retries,
                                conn_error,
                                retry_delay,
                            )
                            sys.stdout.flush()
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.error(f"❌ Failed to connect to database after {max_retries} attempts: {conn_error}")
                            raise

                try:
                    from app.database_admin import enable_sqlite_wal
                    enable_sqlite_wal()
                except Exception as wal_err:
                    logger.warning("SQLite WAL setup skipped: %s", wal_err)
            
                # Step 1: Create all tables if they don't exist (fully automatic)
                logger.info("Ensuring all database tables exist...")
                try:
                    db.create_all()
                    logger.info("✅ All database tables verified/created")
                except Exception as create_error:
                    logger.warning(f"Table creation check: {create_error}")
                    # Continue anyway - tables might already exist
            
                # Schema grows via create_all plus additive ALTER TABLE below.
                # Flask-Migrate is registered but there is no Alembic versions tree yet.
                logger.info("Database tables verified (create_all). Additive ALTER TABLE runs next for older databases.")
            
                # Step 2.5: Add missing columns if tables exist (one-time migration for existing databases)
                inspector = inspect(db.engine)
                if 'users' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('users')]
                    missing_columns = []
                    # Keep in sync with app.models.User — db.create_all() does not alter existing tables.
                    user_optional_columns = [
                        ('designation', 'VARCHAR(30) DEFAULT NULL'),
                        ('password_changed', 'BOOLEAN DEFAULT FALSE'),
                        ('default_signature', 'TEXT'),
                        ('default_comment', 'TEXT'),
                        ('access_hvac', 'BOOLEAN DEFAULT FALSE'),
                        ('access_civil', 'BOOLEAN DEFAULT FALSE'),
                        ('access_cleaning', 'BOOLEAN DEFAULT FALSE'),
                        ('access_hr', 'BOOLEAN DEFAULT FALSE'),
                        ('access_hiring', 'BOOLEAN DEFAULT FALSE'),
                        ('access_procurement_module', 'BOOLEAN DEFAULT FALSE'),
                        ('access_business_development', 'BOOLEAN DEFAULT FALSE'),
                        ('access_sales_manager', 'BOOLEAN DEFAULT FALSE'),
                        ('access_quotations', 'BOOLEAN DEFAULT FALSE'),
                        ('access_report_generation', 'BOOLEAN DEFAULT FALSE'),
                        ('access_submitted_forms', 'BOOLEAN DEFAULT FALSE'),
                        ('access_ticketing', 'BOOLEAN DEFAULT FALSE'),
                        ('access_qhsi', 'BOOLEAN DEFAULT FALSE'),
                        ('access_files', 'BOOLEAN DEFAULT FALSE'),
                        ('is_ticket_reporter', 'BOOLEAN DEFAULT FALSE'),
                        ('last_login', 'TIMESTAMP'),
                        ('employment_start_date', 'DATE'),
                        ('job_designation', 'VARCHAR(160)'),
                        ('annual_leave_days', 'INTEGER'),
                        ('other_leave_days', 'INTEGER'),
                        ('reporting_manager_id', 'INTEGER'),
                        ('operations_manager_id', 'INTEGER'),
                        ('admin_visible_password', 'VARCHAR(255)'),
                        ('phone', 'VARCHAR(40)'),
                        ('assigned_project', 'VARCHAR(200)'),
                        ('mfa_enabled', 'BOOLEAN DEFAULT FALSE'),
                        ('mfa_secret', 'VARCHAR(64)'),
                    ]
                    for col_name, col_def in user_optional_columns:
                        if col_name not in columns:
                            missing_columns.append((col_name, col_def))

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
                                if any(name == 'access_hiring' for name, _col_def in missing_columns):
                                    conn.execute(text("UPDATE users SET access_hiring = access_hr"))
                                    logger.info("Backfilled access_hiring from existing HR module access")
                        except Exception as e:
                            logger.warning(f"Could not add missing columns (non-critical): {e}")

                    # Populate admin_visible_password for existing accounts when we can match a known default.
                    if 'admin_visible_password' in [col['name'] for col in inspector.get_columns('users')]:
                        try:
                            from common.password_admin import backfill_admin_visible_passwords
                            stats = backfill_admin_visible_passwords()
                            if stats.get('updated'):
                                logger.info(
                                    "Admin password backfill: %s updated, %s still unknown (login or reset will fill)",
                                    stats['updated'],
                                    stats['skipped'],
                                )
                        except Exception as backfill_err:
                            logger.warning(f"Admin password backfill skipped: {backfill_err}")

                if 'bd_projects' in inspector.get_table_names():
                    bd_cols = {col['name'] for col in inspector.get_columns('bd_projects')}
                    if 'owner_user_id' not in bd_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text('ALTER TABLE bd_projects ADD COLUMN owner_user_id INTEGER'))
                            logger.info('✅ Added owner_user_id column to bd_projects')
                        except Exception as bd_col_err:
                            logger.warning('Could not add bd_projects.owner_user_id: %s', bd_col_err)
                    try:
                        with db.engine.begin() as conn:
                            conn.execute(text(
                                'UPDATE bd_projects SET owner_user_id = created_by '
                                'WHERE owner_user_id IS NULL AND created_by IS NOT NULL'
                            ))
                    except Exception:
                        pass

                if 'ticket_materials' in inspector.get_table_names():
                    tm_cols = {col['name'] for col in inspector.get_columns('ticket_materials')}
                    for col_name, col_sql in (
                        ('catalog_item_id', 'INTEGER'),
                        ('qty_short', 'FLOAT DEFAULT 0'),
                        ('created_at', 'DATETIME'),
                    ):
                        if col_name in tm_cols:
                            continue
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text(
                                    f'ALTER TABLE ticket_materials ADD COLUMN {col_name} {col_sql}'
                                ))
                            logger.info('Added %s to ticket_materials', col_name)
                        except Exception as tm_err:
                            logger.warning('Could not add ticket_materials.%s: %s', col_name, tm_err)

                if 'proc_stock' in inspector.get_table_names():
                    ps_cols = {col['name'] for col in inspector.get_columns('proc_stock')}
                    if 'imported_from_excel' not in ps_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text('ALTER TABLE proc_stock ADD COLUMN imported_from_excel BOOLEAN DEFAULT 0'))
                            logger.info('Added imported_from_excel to proc_stock')
                        except Exception as ps_err:
                            logger.warning('Could not add proc_stock.imported_from_excel: %s', ps_err)

                if 'proc_properties' in inspector.get_table_names():
                    pp_cols = {col['name'] for col in inspector.get_columns('proc_properties')}
                    if 'ticket_property_id' not in pp_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text('ALTER TABLE proc_properties ADD COLUMN ticket_property_id INTEGER'))
                            logger.info('Added ticket_property_id to proc_properties')
                        except Exception as pp_err:
                            logger.warning('Could not add proc_properties.ticket_property_id: %s', pp_err)
                    if 'is_shared' not in pp_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text('ALTER TABLE proc_properties ADD COLUMN is_shared BOOLEAN DEFAULT 0'))
                            logger.info('Added is_shared to proc_properties')
                        except Exception as pp_err:
                            logger.warning('Could not add proc_properties.is_shared: %s', pp_err)
                    if 'icon' not in pp_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text('ALTER TABLE proc_properties ADD COLUMN icon VARCHAR(32)'))
                            logger.info('Added icon to proc_properties')
                        except Exception as pp_err:
                            logger.warning('Could not add proc_properties.icon: %s', pp_err)

                if 'proc_email_templates' in inspector.get_table_names():
                    pe_cols = {col['name'] for col in inspector.get_columns('proc_email_templates')}
                    if 'attach_pdf' not in pe_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text(
                                    'ALTER TABLE proc_email_templates ADD COLUMN attach_pdf BOOLEAN DEFAULT 1'
                                ))
                            logger.info('Added attach_pdf to proc_email_templates')
                        except Exception as pe_err:
                            logger.warning('Could not add proc_email_templates.attach_pdf: %s', pe_err)

                if 'submissions' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('submissions')]
                    missing_columns = []
                
                    # Check for workflow columns (legacy 2-stage + 5-stage approval)
                    workflow_fields = [
                        ('workflow_status', "VARCHAR(30) DEFAULT 'submitted'"),
                        ('supervisor_id', 'INTEGER'),
                        ('manager_id', 'INTEGER'),
                        ('supervisor_notified_at', 'TIMESTAMP DEFAULT NULL'),
                        ('supervisor_reviewed_at', 'TIMESTAMP DEFAULT NULL'),
                        ('manager_notified_at', 'TIMESTAMP DEFAULT NULL'),
                        ('manager_reviewed_at', 'TIMESTAMP DEFAULT NULL'),
                        ('doc_number', 'VARCHAR(20) DEFAULT NULL'),
                        ('operations_manager_id', 'INTEGER'),
                        ('business_dev_id', 'INTEGER'),
                        ('procurement_id', 'INTEGER'),
                        ('general_manager_id', 'INTEGER'),
                        ('operations_manager_notified_at', 'TIMESTAMP'),
                        ('operations_manager_approved_at', 'TIMESTAMP'),
                        ('business_dev_notified_at', 'TIMESTAMP'),
                        ('business_dev_approved_at', 'TIMESTAMP'),
                        ('procurement_notified_at', 'TIMESTAMP'),
                        ('procurement_approved_at', 'TIMESTAMP'),
                        ('general_manager_notified_at', 'TIMESTAMP'),
                        ('general_manager_approved_at', 'TIMESTAMP'),
                        ('operations_manager_comments', 'TEXT'),
                        ('business_dev_comments', 'TEXT'),
                        ('procurement_comments', 'TEXT'),
                        ('general_manager_comments', 'TEXT'),
                        ('rejection_stage', 'VARCHAR(40)'),
                        ('rejection_reason', 'TEXT'),
                        ('rejected_at', 'TIMESTAMP'),
                        ('rejected_by_id', 'INTEGER'),
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

                if 'knowledge_base_entries' in inspector.get_table_names():
                    columns = [col['name'] for col in inspector.get_columns('knowledge_base_entries')]
                    # Keep in sync with app.models.KnowledgeBaseEntry — create_all does not alter existing tables.
                    kb_optional_columns = [
                        ('source_url', 'VARCHAR(1000)'),
                        ('fetched_at', 'TIMESTAMP'),
                    ]
                    missing_columns = [(c, d) for c, d in kb_optional_columns if c not in columns]
                    if missing_columns:
                        logger.info(f"Adding missing columns to knowledge_base_entries: {[c[0] for c in missing_columns]}")
                        try:
                            with db.engine.begin() as conn:
                                for col_name, col_def in missing_columns:
                                    try:
                                        conn.execute(text(f"ALTER TABLE knowledge_base_entries ADD COLUMN {col_name} {col_def}"))
                                        logger.info(f"✅ Added {col_name} column to knowledge_base_entries table")
                                    except Exception as col_error:
                                        error_str = str(col_error).lower()
                                        if 'already exists' in error_str or 'duplicate' in error_str:
                                            logger.info(f"Column {col_name} already exists, skipping")
                                        else:
                                            logger.warning(f"Could not add {col_name}: {col_error}")
                        except Exception as e:
                            logger.warning(f"Could not add missing knowledge_base columns (non-critical): {e}")

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

                if 'hiring_documents' in inspector.get_table_names():
                    hd_cols = [col['name'] for col in inspector.get_columns('hiring_documents')]
                    if 'notes' not in hd_cols:
                        try:
                            with db.engine.begin() as conn:
                                conn.execute(text('ALTER TABLE hiring_documents ADD COLUMN notes TEXT'))
                            logger.info('✅ Added notes to hiring_documents')
                        except Exception as col_error:
                            err = str(col_error).lower()
                            if 'already exists' in err or 'duplicate' in err:
                                logger.info('Column hiring_documents.notes already exists')
                            else:
                                logger.warning(f'Could not add hiring_documents.notes: {col_error}')

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
                        ('hr_ref', 'VARCHAR(80)'),
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
                    # Unique index for hr_ref (best-effort; ignore if exists / nulls)
                    try:
                        with db.engine.begin() as conn:
                            conn.execute(text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS ix_hiring_candidates_hr_ref "
                                "ON hiring_candidates (hr_ref)"
                            ))
                    except Exception as idx_err:
                        logger.debug('hr_ref index note: %s', idx_err)
                if 'hiring_offer_letters' not in inspector.get_table_names():
                    try:
                        db.create_all()
                        logger.info('✅ Ensured hiring_offer_letters table')
                    except Exception as tbl_err:
                        logger.warning('Could not ensure hiring_offer_letters: %s', tbl_err)
                if 'hiring_offer_letters' in inspector.get_table_names():
                    try:
                        hol_cols = {col['name'] for col in inspector.get_columns('hiring_offer_letters')}
                        if 'not_accepted' not in hol_cols:
                            with db.engine.begin() as conn:
                                conn.execute(text(
                                    'ALTER TABLE hiring_offer_letters '
                                    'ADD COLUMN not_accepted BOOLEAN DEFAULT FALSE NOT NULL'
                                ))
                            logger.info('✅ Added hiring_offer_letters.not_accepted')
                    except Exception as hol_err:
                        logger.warning('Could not ensure hiring_offer_letters.not_accepted: %s', hol_err)
                if 'automation_jobs' in inspector.get_table_names():
                    try:
                        auto_cols = {col['name'] for col in inspector.get_columns('automation_jobs')}
                        if 'export_modules' not in auto_cols:
                            with db.engine.begin() as conn:
                                conn.execute(text(
                                    'ALTER TABLE automation_jobs ADD COLUMN export_modules TEXT'
                                ))
                            logger.info('✅ Added automation_jobs.export_modules')
                    except Exception as auto_err:
                        logger.warning('Could not ensure automation_jobs.export_modules: %s', auto_err)
                # Step 3: Ensure default admin user exists (fully automatic for Render)
                try:
                    from app.models import User
                    default_admin_username = os.environ.get('DEFAULT_ADMIN_USERNAME', 'Kynvera')
                    admin = (
                        User.query.filter_by(username=default_admin_username).first()
                        or User.query.filter_by(username='admin').first()
                    )
                    if not admin:
                        logger.info("Creating default admin user...")
                        admin = User(
                            username=default_admin_username,
                            email=os.environ.get('DEFAULT_ADMIN_EMAIL', 'admin@injaaz.com'),
                            full_name=os.environ.get('DEFAULT_ADMIN_FULL_NAME', 'System Administrator'),
                            role='admin',
                            is_active=True,
                            access_hvac=True,
                            access_civil=True,
                            access_cleaning=True
                        )
                        # Use environment variable for default password, or the local default
                        default_password = os.environ.get('DEFAULT_ADMIN_PASSWORD') or 'Arshith&Taha@2026'
                        admin.set_password(default_password)
                        admin.password_changed = True
                        db.session.add(admin)
                        db.session.commit()
                        logger.info("✅ Default admin user created (username=%s)", default_admin_username)
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
                             '<h2>1. Company Overview</h2><p>Kynvera delivers excellence in facility services across the UAE.</p>'
                             '<h2>2. Your First Week</h2><ul><li><strong>Day 1:</strong> Meet your team lead, set up workstation</li>'
                             '<li><strong>Day 2:</strong> System access, security training</li><li><strong>Day 3-5:</strong> Department walkthroughs</li></ul>'
                             '<h2>3. Key Contacts</h2><ul><li><strong>HR:</strong> arshith@injaaz.ae</li><li><strong>IT:</strong> +971 50 156 0277</li></ul>'),
                            ('Project Services Agreement Template', 'contracts', 'review',
                             '<h1>Project Services Agreement</h1><p><em>Agreement between Service Provider and Client.</em></p>'
                             '<h2>1. Parties</h2><p><strong>Service Provider:</strong> Kynvera.<br/><strong>Client:</strong> [Client Name].</p>'
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

                # Step 5: Ensure ticket/asset additive columns before any ORM seed writes.
                # Blueprint record_once migrators also run later; this covers Postgres before seeds.
                try:
                    from module_ticketing.routes import (
                        _migrate_ticket_columns,
                        _migrate_ticket_project_columns,
                    )
                    _migrate_ticket_columns(app)
                    _migrate_ticket_project_columns(app)
                except Exception as tkt_mig_err:
                    logger.warning('Early ticket column migrate: %s', tkt_mig_err)
                try:
                    from module_assets.routes import _ensure_asset_columns
                    _ensure_asset_columns(app)
                except Exception as asset_mig_err:
                    logger.warning('Early asset column ensure: %s', asset_mig_err)

                # Step 6: Seed ticketing / FM / demo teams when empty (local + Render parity).
                # Does not insert sample HR/hiring rows — that is opt-in via seed_all_sample_data.py.
                try:
                    from common.runtime_seed import bootstrap_demo_data
                    seed_summary = bootstrap_demo_data()
                    logger.info("Reference/demo data bootstrap: %s", seed_summary)
                except Exception as bootstrap_err:
                    logger.warning(
                        "Could not bootstrap reference/demo data (non-critical): %s",
                        bootstrap_err,
                    )

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
        from common.kynvera_hub import (
            auth_home_url,
            hub_public_config,
            is_marketing_host,
            staff_forgot_url,
            staff_login_url,
            staff_register_url,
        )
        return {
            'hub': hub_public_config(),
            'marketing_host': is_marketing_host(),
            'staff_login_url': staff_login_url(),
            'staff_forgot_url': staff_forgot_url(),
            'staff_register_url': staff_register_url(),
            'allow_public_registration': bool(app.config.get('ALLOW_PUBLIC_REGISTRATION')),
            'auth_home_url': auth_home_url(),
        }

    @app.before_request
    def _kynvera_marketing_only_gate():
        """kynvera.net serves the public landing; staff URLs are not advertised here."""
        if not app.config.get('KYNVERA_MARKETING_ONLY'):
            return None
        path = request.path or '/'
        public_exact = {
            '/', '/privacy', '/terms', '/robots.txt', '/health',
            '/manifest.json', '/favicon.ico', '/offline',
            '/apple-touch-icon.png', '/apple-touch-icon-precomposed.png',
        }
        if path in public_exact or path.startswith('/static/'):
            return None
        return redirect('/')
    
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
        
        def _make_memory_limiter():
            """Fallback to in-memory storage when Redis is unavailable.

            Single-worker deployments (current default on Render) benefit from
            this because it still throttles brute-force attempts on /login
            and /register from a single IP. It is NOT shared across workers,
            so multi-worker setups should provide Redis.
            """
            lim = Limiter(
                app=app,
                key_func=get_remote_address,
                default_limits=[os.environ.get('RATELIMIT_DEFAULT', '100 per hour')],
                storage_uri="memory://",
                strategy="fixed-window",
            )
            return lim

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
                logger.warning(f"⚠️  Redis connection failed — falling back to in-memory rate limiter: {redis_error}")
                app.limiter = _make_memory_limiter()
        else:
            logger.info("✓ Rate limiting using in-memory storage (no Redis URL configured)")
            app.limiter = _make_memory_limiter()
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
        try:
            return render_template('404.html'), 404
        except Exception:
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
        request_id = request.headers.get('X-Request-ID', 'unknown')
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Internal server error", "request_id": request_id}), 500
        try:
            return render_template('500.html', request_id=request_id), 500
        except Exception:
            return ("Internal Server Error", 500)
    
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
        """PWA manifest: marketing host opens the landing; product host opens the app."""
        import json
        from common.kynvera_hub import is_marketing_host
        path = os.path.join(app.static_folder, 'manifest.json')
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        data['start_url'] = '/' if is_marketing_host() else '/dashboard'
        return Response(json.dumps(data), mimetype='application/manifest+json')

    @app.route('/favicon.ico')
    def favicon():
        """Site icon at the well-known URL Googlebot fetches for Search results.

        Must include a 48×48 (or multiple) size — 16/32px icons are ignored.
        """
        return send_from_directory(
            os.path.join(app.static_folder, 'images', 'kynvera'),
            'favicon.ico',
            mimetype='image/x-icon',
        )
    
    @app.route('/apple-touch-icon.png')
    @app.route('/apple-touch-icon-precomposed.png')
    def apple_touch_icon():
        """iOS fetches this at the site root when adding to the home screen."""
        return send_from_directory(
            os.path.join(app.static_folder, 'images', 'kynvera'),
            'kynvera-mark-180.png',
            mimetype='image/png',
        )

    @app.route('/robots.txt')
    def robots_txt():
        from common.kynvera_hub import is_marketing_host, is_operations_host, marketing_only

        if is_operations_host():
            body = "User-agent: *\nDisallow: /\n"
        elif marketing_only() or is_marketing_host():
            body = (
                "User-agent: *\n"
                "Allow: /\n"
                "Allow: /privacy\n"
                "Allow: /terms\n"
                "Allow: /static/\n"
                "Allow: /favicon.ico\n"
                "Allow: /apple-touch-icon.png\n"
                "Disallow: /login\n"
                "Disallow: /register\n"
                "Disallow: /forgot-password\n"
                "Disallow: /reset-password\n"
                "Disallow: /dashboard\n"
                "Disallow: /admin\n"
                "Disallow: /api/\n"
            )
        else:
            body = (
                "User-agent: *\n"
                "Allow: /\n"
                "Allow: /login\n"
                "Allow: /forgot-password\n"
                "Allow: /reset-password\n"
                "Allow: /privacy\n"
                "Allow: /terms\n"
                "Allow: /static/\n"
                "Allow: /favicon.ico\n"
                "Allow: /apple-touch-icon.png\n"
                "Allow: /offline\n"
                "Allow: /manifest.json\n"
                "Disallow: /admin\n"
                "Disallow: /api/\n"
                "Disallow: /dashboard\n"
                "Disallow: /hr\n"
                "Disallow: /tickets\n"
                "Disallow: /procurement\n"
                "Disallow: /qhsi\n"
                "Disallow: /inspection\n"
                "Disallow: /assets\n"
                "Disallow: /files\n"
                "Disallow: /automations\n"
                "Disallow: /dochub\n"
                "Disallow: /workflow\n"
                "Disallow: /register\n"
                "Disallow: /logout\n"
                "Disallow: /sso/\n"
            )
        return Response(body, mimetype='text/plain')

    @app.route('/privacy')
    def privacy_page():
        return render_template('legal.html', legal_page='privacy')

    @app.route('/terms')
    def terms_page():
        return render_template('legal.html', legal_page='terms')

    @app.route('/forgot-password')
    def forgot_password_page():
        return render_template('forgot_password.html')

    @app.route('/reset-password')
    def reset_password_page():
        return render_template(
            'reset_password.html',
            reset_token=(request.args.get('token') or '').strip(),
        )

    # Legacy trade URLs → unified inspection form (bookmarks / old emails)
    def _redirect_legacy_inspection():
        qs = request.query_string.decode('utf-8') if request.query_string else ''
        target = '/inspection/form'
        if qs:
            target = f'{target}?{qs}'
        return redirect(target, code=302)

    @app.route('/hvac-mep/', defaults={'rest': ''})
    @app.route('/hvac-mep/<path:rest>')
    @app.route('/hvac-mep')
    def legacy_hvac_redirect(rest=''):
        return _redirect_legacy_inspection()

    @app.route('/civil/', defaults={'rest': ''})
    @app.route('/civil/<path:rest>')
    @app.route('/civil')
    def legacy_civil_redirect(rest=''):
        return _redirect_legacy_inspection()

    @app.route('/cleaning/', defaults={'rest': ''})
    @app.route('/cleaning/<path:rest>')
    @app.route('/cleaning')
    def legacy_cleaning_redirect(rest=''):
        return _redirect_legacy_inspection()

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
        try:
            if not app.config.get('KYNVERA_MARKETING_ONLY'):
                from app.bd.email_scheduler import init_scheduler as init_bd_email_scheduler
                init_bd_email_scheduler(app)
        except Exception as sched_err:
            logger.warning("⚠️  BD email scheduler not started: %s", sched_err)
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

    # Register Files module blueprint (Finder + Drive sync)
    if files_module_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(files_module_bp)
        app.register_blueprint(files_module_bp, url_prefix='/files')
        @app.route('/files')
        def redirect_files_to_slash():
            return redirect('/files/', code=302)
        logger.info("✅ Registered Files blueprint at /files")
    else:
        logger.warning("⚠️  Files blueprint not available - check imports")

    # Register Automations hub
    if automations_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(automations_bp)
        app.register_blueprint(automations_bp, url_prefix='/automations')
        @app.route('/automations')
        def redirect_automations_to_slash():
            return redirect('/automations/', code=302)
        logger.info("✅ Registered Automations blueprint at /automations")
        try:
            if not app.config.get('KYNVERA_MARKETING_ONLY'):
                from app.automations.scheduler import init_scheduler as init_automations_scheduler
                init_automations_scheduler(app)
        except Exception as sched_err:
            logger.warning("⚠️  Automations scheduler not started: %s", sched_err)
    else:
        logger.warning("⚠️  Automations blueprint not available - check imports")
    
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
            if not app.config.get('KYNVERA_MARKETING_ONLY'):
                from module_mmr.scheduler import init_scheduler as init_mmr_scheduler
                init_mmr_scheduler(app)
        except Exception as sched_err:
            logger.warning(f"⚠️  MMR scheduler not started: {sched_err}")
    else:
        logger.warning("⚠️  MMR blueprint not available")

    # Register Ticketing blueprint
    if ticketing_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(ticketing_bp)
        app.register_blueprint(ticketing_bp, url_prefix='/tickets')
        logger.info("✅ Registered Ticketing blueprint at /tickets")
    else:
        logger.warning("⚠️  Ticketing blueprint not available - check imports")

    # Register QHSI blueprint
    if qhsi_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(qhsi_bp)
        app.register_blueprint(qhsi_bp)
        @app.route('/qhsi')
        def redirect_qhsi_to_slash():
            return redirect('/qhsi/', code=302)
        logger.info("✅ Registered QHSI blueprint at /qhsi")
        @app.route('/qhsi_staff_compliance/form')
        def redirect_legacy_qhsi_staff_form():
            qs = request.query_string.decode() if request.query_string else ''
            return redirect('/qhsi/staff-compliance' + ('?' + qs if qs else ''), code=302)

        @app.route('/qhsi_inspection/form')
        def redirect_legacy_qhsi_inspection_form():
            qs = request.query_string.decode() if request.query_string else ''
            return redirect('/qhsi/inspection' + ('?' + qs if qs else ''), code=302)
    else:
        logger.warning("⚠️  QHSI blueprint not available - check imports")

    # Register Live Assistant blueprint
    if assistant_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(assistant_bp)
        app.register_blueprint(assistant_bp)
        logger.info("✅ Registered Live Assistant blueprint at /api/assistant")
    else:
        logger.warning("⚠️  Live Assistant blueprint not available - check imports")

    # Register FM Assets blueprint
    if assets_bp:
        if hasattr(app, 'csrf') and app.csrf:
            app.csrf.exempt(assets_bp)
        app.register_blueprint(assets_bp)
        logger.info("✅ Registered FM Assets blueprint at /assets")
    else:
        logger.warning("⚠️  FM Assets blueprint not available - check imports")

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

    # Security headers middleware.
    #
    # CSP is enforced with a policy that still allows the inline scripts and
    # Google Fonts this app uses. Set CSP_ENFORCE=false to fall back to
    # Report-Only while debugging a new third-party origin.
    _is_prod = app.config.get('FLASK_ENV', 'development') == 'production'
    _csp_default = (
        "default-src 'self'; "
        "img-src 'self' data: blob: https:; "
        "media-src 'self' blob: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
        "font-src 'self' data: https:; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "object-src 'none'"
    )
    _csp_policy = os.environ.get('CSP_POLICY', _csp_default)
    _csp_enforce = os.environ.get('CSP_ENFORCE', 'true').lower() not in ('0', 'false', 'no', 'off')

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(self), microphone=(), geolocation=(self), payment=()'
        )
        # HSTS only makes sense over HTTPS — enable in production where the
        # service is fronted by TLS. 6 months + preload-friendly.
        if _is_prod:
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=15552000; includeSubDomains'
            )
        # Enforced Content-Security-Policy unless CSP_ENFORCE=false.
        csp_header = 'Content-Security-Policy' if _csp_enforce else 'Content-Security-Policy-Report-Only'
        response.headers.setdefault(csp_header, _csp_policy)

        from common.kynvera_hub import is_operations_host
        if is_operations_host():
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'

        # Authenticated HTML must not sit in bfcache. Back from /login was
        # restoring the previous app page without a server round-trip.
        mimetype = (response.mimetype or '')
        path = request.path or ''
        public_exact = {
            '/', '/offline', '/manifest.json', '/privacy', '/terms',
            '/robots.txt', '/forgot-password', '/reset-password',
            '/apple-touch-icon.png', '/apple-touch-icon-precomposed.png',
        }
        public_prefixes = (
            '/static/', '/assets/tag/', '/sso/', '/login', '/logout',
        )
        is_public = path in public_exact or any(path.startswith(p) for p in public_prefixes)
        if 'html' in mimetype and not is_public:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # Authentication routes
    @app.route('/login')
    def login_page():
        """Render login page"""
        response = make_response(render_template('login.html'))
        # Avoid bfcache restoring a post-login form when the user hits Back.
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        return response
    
    @app.route('/register')
    def register_page():
        """Public signup wizard. Closed when ALLOW_PUBLIC_REGISTRATION is false."""
        if current_app.config.get('ALLOW_PUBLIC_REGISTRATION'):
            return render_template('register.html')
        return redirect(url_for('login_page'))
    
    @app.route('/logout')
    def logout_page():
        """Logout and redirect to login"""
        # Clear any local storage via JS or just redirect
        return render_template('logout.html')
    

    @app.route('/dashboard')
    @jwt_required()
    def dashboard():
        """Protected dashboard - requires authentication"""
        from common.kynvera_hub import hub_public_config
        return render_template('dashboard.html', hub=hub_public_config())

    @app.route('/api/hub/config')
    def hub_config():
        from common.kynvera_hub import hub_public_config
        return jsonify(hub_public_config())

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
        """About is hidden from the product; old links go to the public landing."""
        return redirect('/', code=302)
    
    @app.route('/workflow/pending-reviews')
    def pending_reviews():
        """Pending reviews page - requires reviewer authentication"""
        return render_template('pending_reviews.html')
    
    @app.route('/workflow/submitted-forms')
    def submitted_forms():
        """Submitted forms page - supervisors can view their submissions"""
        return render_template('submitted_forms.html')

    @app.route('/workflow/inspection/<submission_id>')
    def open_inspection_submission(submission_id):
        """Resolve an inspection submission to its module-specific form URL.

        Used by in-app notification clicks so reviewers land directly on the
        form to review, comment, and sign without an intermediate listing page.
        """
        from app.models import Submission
        sub = Submission.query.filter_by(submission_id=submission_id).first()
        if not sub:
            return redirect('/workflow/pending-reviews')
        module_paths = {
            'inspection': '/inspection/form',
            'hvac_mep': '/inspection/form',
            'hvac': '/inspection/form',
            'civil': '/inspection/form',
            'cleaning': '/inspection/form',
        }
        mod = (sub.module_type or '').lower()
        if mod in ('qhsi_inspection', 'qhsi_staff_compliance'):
            wf = (sub.workflow_status or '').lower()
            if wf in ('approved', 'completed', 'rejected', 'gm_approved'):
                return redirect(
                    '/workflow/submitted-forms?scope=inspection&submission='
                    + submission_id
                )
            return redirect('/workflow/pending-reviews')
        base = module_paths.get(mod)
        if not base:
            return redirect('/workflow/pending-reviews')
        # Include review=true so the form opens in reviewer mode
        return redirect(f"{base}?edit={submission_id}&review=true")
    
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
        """Deep-link to the sent emails log on the admin dashboard."""
        return redirect('/admin/dashboard?focus=email-log')

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
        """Business Development module — BD team, managers, and admin"""
        return render_template('admin_bd_module.html', active_page='bd-module')

    @app.route('/admin/personal-progress')
    def admin_personal_progress():
        """Personal work-in-progress tracker — admin only"""
        return render_template('admin_personal_progress.html', active_page='personal-progress')

    @app.route('/admin/team-management')
    def admin_team_management():
        """Team & technician management — admin only"""
        return render_template('admin_team_management.html', active_page='team-management')

    @app.route('/admin/knowledge-base')
    def admin_knowledge_base():
        """Knowledge Base — admin-managed records that feed the assistant."""
        return render_template('admin_knowledge_base.html', active_page='knowledge-base')

    @app.route('/admin/database')
    def admin_database():
        """Database status and backup download — admin only."""
        return render_template('admin_database.html', active_page='database')

    @app.route('/dochub')
    def dochub():
        """DocHub module - all users with access"""
        return render_template('dochub.html', active_page='dochub')

    # Root: public landing. On operations this is the staff entry (Sign in / Create account).
    @app.route('/')
    def index():
        return render_template('landing.html')

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
        if app.config.get('KYNVERA_MARKETING_ONLY'):
            return jsonify({
                'status': 'healthy',
                'site': 'marketing',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }), 200
        try:
            # Check database connection and that core schema is present.
            # SELECT 1 alone was green after a local SQLite schema loss
            # while login failed with "no such table: users".
            from sqlalchemy import inspect as sa_inspect

            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            tables = set(sa_inspect(db.engine).get_table_names())
            if 'users' not in tables:
                logger.warning("Database health check: users table missing")
                db_status = 'unhealthy'
            else:
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


def _current_git_branch():
    """Best-effort branch name for local console hint (detached HEAD → short SHA)."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if r.returncode == 0:
            name = (r.stdout or "").strip()
            if name and name != "HEAD":
                return name
        r2 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if r2.returncode == 0 and (r2.stdout or "").strip():
            return "detached @ " + (r2.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


if __name__ == '__main__':
    app = create_app()
    _branch = _current_git_branch()
    if _branch:
        logger.info("Running from git branch: %s", _branch)
    else:
        logger.info("Git branch: (not available)")
    # Local default: 5002 (matches APP_BASE_URL in .env). Production hosts set PORT.
    _port = int(os.environ.get("PORT", "5002"))
    logger.info("Starting server on http://0.0.0.0:%s", _port)
    # For local development use debug=True. Remove or set False in production.
    app.run(debug=False, host='0.0.0.0', port=_port)