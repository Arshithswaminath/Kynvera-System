#!/usr/bin/env python3
"""
Generate docs/Injaaz_Full_Technical_Documentation.pdf
Full coverage: every module, every route/function, code snippets, flows.
Run: python scripts/generate_full_technical_doc.py
"""
import os, sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, NextPageTemplate,
    Paragraph, Spacer, Table, TableStyle, HRFlowable,
    PageBreak, KeepTogether,
)

# ── Palette ────────────────────────────────────────────────────────────────
NAVY  = colors.HexColor("#1a365d")
BLUE  = colors.HexColor("#2c5282")
TEAL  = colors.HexColor("#2b6cb0")
LGREY = colors.HexColor("#f7fafc")
MGREY = colors.HexColor("#e2e8f0")
DGREY = colors.HexColor("#4a5568")
BLACK = colors.HexColor("#1a202c")
WHITE = colors.white
GOLD  = colors.HexColor("#d69e2e")
CODE_BG = colors.HexColor("#f0f4f8")
CODE_FG = colors.HexColor("#1a202c")
GREEN_BG = colors.HexColor("#f0fff4")
GREEN_BD = colors.HexColor("#276749")

W, H = A4


# ── Page callbacks ─────────────────────────────────────────────────────────
def _cover_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY); canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(TEAL); canvas.rect(0, H*0.36, W, H*0.64, fill=1, stroke=0)
    canvas.setFillColor(GOLD); canvas.rect(0, H*0.355, W, 5, fill=1, stroke=0)
    canvas.restoreState()


def _body_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY); canvas.rect(0, 0, 5, H, fill=1, stroke=0)
    canvas.setFillColor(LGREY); canvas.rect(5, H-1.35*cm, W-5, 1.35*cm, fill=1, stroke=0)
    canvas.setFillColor(NAVY); canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(1.4*cm, H-0.82*cm, "INJAAZ")
    canvas.setFillColor(DGREY); canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W-1.4*cm, H-0.82*cm, "Full Technical Documentation — April 2026")
    canvas.setFillColor(MGREY); canvas.rect(5, 0, W-5, 1.15*cm, fill=1, stroke=0)
    canvas.setFillColor(DGREY); canvas.setFont("Helvetica", 8)
    canvas.drawString(1.4*cm, 0.42*cm, "Injaaz Facilities & Operations Platform")
    canvas.drawRightString(W-1.4*cm, 0.42*cm, f"Page {doc.page}")
    canvas.restoreState()


# ── Styles ─────────────────────────────────────────────────────────────────
def _styles():
    def ps(name, **kw): return ParagraphStyle(name, **kw)
    return dict(
        cover_title = ps("CT", fontSize=32, fontName="Helvetica-Bold", textColor=WHITE,
                          alignment=TA_LEFT, leading=40, spaceAfter=10),
        cover_sub   = ps("CS", fontSize=13, fontName="Helvetica", textColor=colors.HexColor("#bee3f8"),
                          alignment=TA_LEFT, leading=20),
        cover_meta  = ps("CM", fontSize=10, fontName="Helvetica", textColor=colors.HexColor("#90cdf4"),
                          alignment=TA_LEFT, spaceAfter=4),
        secnum      = ps("SN", fontSize=9, fontName="Helvetica-Bold", textColor=GOLD,
                          spaceBefore=0, spaceAfter=2),
        h1          = ps("H1", fontSize=16, fontName="Helvetica-Bold", textColor=NAVY,
                          spaceBefore=2, spaceAfter=6, leading=20),
        h2          = ps("H2", fontSize=12, fontName="Helvetica-Bold", textColor=BLUE,
                          spaceBefore=12, spaceAfter=5, leading=16),
        h3          = ps("H3", fontSize=10, fontName="Helvetica-Bold", textColor=TEAL,
                          spaceBefore=8, spaceAfter=4),
        body        = ps("BD", fontSize=9.5, fontName="Helvetica", textColor=BLACK,
                          leading=14, alignment=TA_JUSTIFY, spaceAfter=5),
        bullet      = ps("BL", fontSize=9.5, fontName="Helvetica", textColor=BLACK,
                          leading=14, leftIndent=16, bulletIndent=5, spaceAfter=3),
        code        = ps("CD", fontSize=8.3, fontName="Courier", textColor=CODE_FG,
                          leading=12, leftIndent=8, rightIndent=8, spaceAfter=2,
                          spaceBefore=2, backColor=CODE_BG),
        small       = ps("SM", fontSize=8, fontName="Helvetica", textColor=DGREY, leading=11),
        toc         = ps("TC", fontSize=9.5, fontName="Helvetica", textColor=BLACK, leading=15, spaceAfter=2),
        toch        = ps("TH", fontSize=10, fontName="Helvetica-Bold", textColor=NAVY, leading=16, spaceAfter=4),
        callout     = ps("CA", fontSize=9.5, fontName="Helvetica-Oblique", textColor=NAVY,
                          leading=14, leftIndent=10, rightIndent=10, spaceAfter=6, spaceBefore=3),
        note        = ps("NT", fontSize=9, fontName="Helvetica-Oblique", textColor=DGREY,
                          leading=13, spaceAfter=4),
    )


# ── Helpers ────────────────────────────────────────────────────────────────
def _rule(s):
    return HRFlowable(width="100%", thickness=0.5, color=MGREY, spaceAfter=6, spaceBefore=2)

def _sec(num, title, s):
    return KeepTogether([Paragraph(num, s["secnum"]), Paragraph(title, s["h1"]), _rule(s)])

def _tbl(data, widths, hbg=NAVY, stripe=LGREY):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  hbg),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [stripe, WHITE]),
        ("GRID",          (0,0),(-1,-1), 0.4, MGREY),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ]))
    return t

def _bp(text, s): return Paragraph(text, s["bullet"], bulletText="•")

def _code(lines, s):
    blks = []
    for ln in lines:
        blks.append(Paragraph(ln.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"), s["code"]))
    return blks

def _callout(text, s):
    t = Table([[Paragraph(text, s["callout"])]], colWidths=["100%"])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#ebf8ff")),
                            ("LINEAFTER",  (0,0),(0,-1), 3, TEAL),
                            ("LEFTPADDING",(0,0),(-1,-1),14),
                            ("TOPPADDING", (0,0),(-1,-1),7),
                            ("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    return t

def _note(text, s):
    t = Table([[Paragraph(text, s["note"])]], colWidths=["100%"])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#fffbeb")),
                            ("LINEAFTER",  (0,0),(0,-1), 3, GOLD),
                            ("LEFTPADDING",(0,0),(-1,-1),12),
                            ("TOPPADDING", (0,0),(-1,-1),5),
                            ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    return t


# ── Document build ─────────────────────────────────────────────────────────
def build(path):
    s = _styles()
    LM, RM, TM, BM = 1.7*cm, 1.7*cm, 1.9*cm, 1.8*cm

    cov_frame  = Frame(0, 0, W, H, leftPadding=2.4*cm, rightPadding=2.4*cm,
                       topPadding=H*0.41, bottomPadding=2*cm, id="cov")
    body_frame = Frame(LM+3, BM+1.3*cm, W-LM-RM-3, H-TM-BM-2.65*cm, id="body")

    doc = BaseDocTemplate(path, pagesize=A4,
                          title="Injaaz — Full Technical Documentation",
                          author="Injaaz Development Team")
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cov_frame], onPage=_cover_bg),
        PageTemplate(id="Body",  frames=[body_frame], onPage=_body_page),
    ])

    story = []
    gen = datetime.now().strftime("%d %B %Y")

    # ── Cover ──────────────────────────────────────────────────────────────
    story += [NextPageTemplate("Cover"), Spacer(1,1),
              Paragraph("INJAAZ", s["cover_title"]),
              Paragraph("Full Technical Documentation", s["cover_sub"]),
              Spacer(1, 0.5*cm),
              Paragraph("Methods · Functions · Flows · Code References", s["cover_meta"]),
              Paragraph(f"Generated: {gen}", s["cover_meta"]),
              Paragraph("Version 1.0 — Internal Reference", s["cover_meta"]),
              NextPageTemplate("Body"), PageBreak()]

    # ── Table of contents ─────────────────────────────────────────────────
    story += [Paragraph("Table of Contents", s["h1"]), _rule(s), Spacer(1,0.2*cm)]
    toc_entries = [
        ("1",  "Application Overview & Architecture"),
        ("2",  "Application Factory — Injaaz.py"),
        ("3",  "Configuration — config.py"),
        ("4",  "Database Models — app/models.py"),
        ("5",  "Common Utilities — common/"),
        ("6",  "Authentication — app/auth/routes.py"),
        ("7",  "Admin Module — app/admin/routes.py"),
        ("8",  "Workflow Engine — app/workflow/routes.py"),
        ("9",  "HR Module — module_hr/"),
        ("10", "HR PDF Builder — hr_pdf_builder.py"),
        ("11", "HR DOCX Service — docx_service.py"),
        ("12", "HR Print Utilities — print_utils.py"),
        ("13", "HVAC & MEP Module — module_hvac_mep/"),
        ("14", "Civil Works Module — module_civil/"),
        ("15", "Cleaning Module — module_cleaning/"),
        ("16", "Inspection Module — module_inspection/"),
        ("17", "Procurement Module — module_procurement/"),
        ("18", "MMR Reporting — module_mmr/"),
        ("19", "Business Development — app/bd/"),
        ("20", "DocHub — app/docs/"),
        ("21", "Reports API — app/reports_api.py"),
        ("22", "Security Architecture"),
        ("23", "End-to-End Request Flows"),
        ("24", "Function & Method Quick Reference"),
    ]
    for num, title in toc_entries:
        row = Table([[Paragraph(f"{num}.", s["toc"]), Paragraph(title, s["toc"])]],
                    colWidths=[1.0*cm, None])
        row.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),3),("TOPPADDING",(0,0),(-1,-1),2),
                                  ("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        story.append(row)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 1. ARCHITECTURE
    # ══════════════════════════════════════════════════════════════════════
    story.append(_sec("1", "Application Overview & Architecture", s))
    story.append(Paragraph(
        "Injaaz is a <b>modular monolith</b> built with <b>Python / Flask</b>. One deployable "
        "application exposes many Flask blueprints — each covering a business domain — that all "
        "share a single SQLAlchemy database, a common authentication layer, and shared utility "
        "libraries under <b>common/</b>.", s["body"]))
    story.append(Paragraph("Modules and URL prefixes", s["h2"]))
    story.append(_tbl([
        ["Module / Blueprint","URL Prefix","File"],
        ["Authentication",    "/api/auth",      "app/auth/routes.py"],
        ["Admin",             "/api/admin",     "app/admin/routes.py"],
        ["Workflow",          "/api/workflow",  "app/workflow/routes.py"],
        ["Reports API",       "/api/reports",   "app/reports_api.py"],
        ["HVAC & MEP",        "/hvac-mep",      "module_hvac_mep/routes.py"],
        ["Civil Works",       "/civil",         "module_civil/routes.py"],
        ["Cleaning",          "/cleaning",      "module_cleaning/routes.py"],
        ["Inspection",        "/inspection",    "module_inspection/routes.py"],
        ["HR",                "/hr",            "module_hr/routes.py"],
        ["Procurement",       "/procurement",   "module_procurement/routes.py"],
        ["MMR / Reporting",   "/admin/mmr",     "module_mmr/routes.py"],
        ["Business Dev",      "/bd",            "app/bd/routes.py"],
        ["DocHub",            "/api/docs",      "app/docs/routes.py"],
    ], [3.5*cm, 3.5*cm, 8.5*cm]))
    story.append(Spacer(1,0.3*cm))
    story.append(Paragraph("Blueprint registration pattern", s["h2"]))
    story.append(Paragraph(
        "Each blueprint is imported in a guarded <b>try/except</b> block at the top of "
        "<b>Injaaz.py</b>. If an import fails (e.g. a missing dependency), the app still "
        "starts and all other modules remain available. The failed module is silently absent "
        "from the URL space until fixed.", s["body"]))
    story += _code([
        "# Safe import pattern used for every blueprint",
        "hr_bp = None",
        "try:",
        "    from module_hr.routes import hr_bp",
        "except Exception as e:",
        "    logger.exception('Could not import hr_bp: %s', e)",
        "",
        "# Registration inside create_app()",
        "if hr_bp:",
        "    app.register_blueprint(hr_bp, url_prefix='/hr')",
    ], s)
    story.append(Spacer(1,0.4*cm))

    # ══════════════════════════════════════════════════════════════════════
    # 2. APP FACTORY
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("2", "Application Factory — Injaaz.py", s))
    story.append(Paragraph(
        "<b>create_app()</b> is the Flask application factory. It is the single entry point "
        "that wires together every component. Nothing is initialised at module level — "
        "all setup happens inside this function, which means the app can be instantiated "
        "multiple times with different config (e.g. test suite vs production).", s["body"]))
    story.append(Paragraph("What create_app() does — in order", s["h2"]))
    steps = [
        ("Load config", "Reads every uppercase variable from config.py and sets it on app.config."),
        ("Validate config", "Calls common.config_validator.validate_config(app) — raises RuntimeError on critical failures so a misconfigured production deployment refuses to start."),
        ("Init DB + Bcrypt", "db.init_app(app) and bcrypt.init_app(app) — SQLAlchemy and password hashing."),
        ("Init Flask-Migrate", "Migrate(app, db) — registers 'flask db upgrade/migrate' CLI commands for schema versioning."),
        ("Init JWTManager", "Attaches JWT error handlers: missing token → redirect or 401; expired → redirect or 401; invalid → same; token in blocklist → 401."),
        ("JWT blocklist check", "token_in_blocklist_loader — every request queries the Session table by JTI. If the session row is missing or is_revoked=True, the request is rejected."),
        ("DB startup migration", "Runs db.create_all() then inspects existing columns; adds any missing columns with ALTER TABLE for backwards-compatible live upgrades."),
        ("Default admin seed", "If no admin user exists, creates one with a generated or configured password and logs it prominently so operators can log in for the first time."),
        ("Register blueprints", "Registers all successfully imported blueprints with their URL prefixes."),
        ("Register page routes", "Attaches non-blueprint routes: /, /login, /dashboard, /about, /admin/*, etc. as plain view functions."),
        ("PWA + static routes", "Serves manifest.json, service-worker.js, offline.html from the static folder."),
        ("Error handlers", "404 and 500 handlers return JSON for /api/* paths and HTML pages otherwise."),
        ("Health endpoint", "GET /health — no auth required; returns {status:ok, database:ok}."),
    ]
    step_data = [["Step","What happens"]] + [[a,b] for a,b in steps]
    story.append(_tbl(step_data, [3.8*cm, 11.7*cm]))
    story.append(Spacer(1,0.3*cm))

    # ══════════════════════════════════════════════════════════════════════
    # 3. CONFIG
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("3", "Configuration — config.py", s))
    story.append(Paragraph(
        "All runtime settings live in <b>config.py</b> as uppercase module-level variables, "
        "driven by <b>os.getenv()</b> calls. The app factory loads them automatically. "
        "Sensitive values must be set as environment variables — never hard-coded.", s["body"]))
    cfg_data = [
        ["Variable","Purpose","Default"],
        ["SECRET_KEY",          "Flask session signing",                   "change-me-in-production"],
        ["JWT_SECRET_KEY",      "JWT signing secret",                       "change-me-jwt-secret"],
        ["DATABASE_URL",        "Full DB connection string",                "SQLite in dev, required in prod"],
        ["REDIS_URL",           "Rate limiter / background queue",          "None (optional)"],
        ["CLOUDINARY_*",        "Cloud file storage credentials",           "None (required in prod)"],
        ["MAILJET_* / BREVO_*", "Email API keys",                          "None (optional)"],
        ["JWT_ACCESS_TOKEN_EXPIRES", "Access token lifetime",              "1 hour"],
        ["JWT_REFRESH_TOKEN_EXPIRES","Refresh token lifetime",             "7 days"],
        ["MAX_CONTENT_LENGTH",  "Max total upload size",                    "100 MB"],
        ["GENERATED_DIR",       "Where uploads and jobs are stored",        "./generated"],
        ["FLASK_ENV",           "development / production",                "development"],
    ]
    story.append(_tbl(cfg_data, [3.8*cm, 6.5*cm, 5.2*cm]))
    story.append(Spacer(1,0.3*cm))

    # ══════════════════════════════════════════════════════════════════════
    # 4. MODELS
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("4", "Database Models — app/models.py", s))
    story.append(Paragraph(
        "All ORM models are defined in <b>app/models.py</b> using Flask-SQLAlchemy. "
        "The file also exports <b>db</b> (SQLAlchemy instance) and <b>bcrypt</b> "
        "(Bcrypt instance) used across the application.", s["body"]))

    models = [
        ("User","stores user account: username, email, bcrypt password hash, role, designation, is_active, per-module flags (access_hvac, access_civil, access_cleaning, access_hr, access_procurement_module), default_signature, default_comment, last_login.",
         ["set_password(password) — hashes and stores password",
          "check_password(password) → bool — verifies against hash",
          "has_module_access(module) → bool — respects admin bypass",
          "to_dict() → dict — API serialisation"]),
        ("Submission","central record for every form submission across all modules. Key fields: submission_id (unique slug), user_id, module_type, site_name, visit_date, status, workflow_status, form_data (JSON), created_at, updated_at. Holds FK columns for every approval participant (supervisor_id, operations_manager_id, general_manager_id …).",
         ["to_dict(include_form_data, include_latest_job) → dict"]),
        ("Job","tracks a background report-generation task. Fields: job_id, submission_id, status (pending/processing/completed/failed), progress (0–100), result_data (JSON with file URLs), error_message, started_at, completed_at.",
         ["to_dict() → dict"]),
        ("File","metadata for an uploaded file: submission_id, file_type, cloud_url, filename, file_size.",
         ["to_dict() → dict"]),
        ("AuditLog","immutable event record: user_id, action, resource_type, resource_id, ip_address, user_agent, details (JSON).",
         ["to_dict() → dict"]),
        ("Session","JWT session row: user_id, token_jti (unique), expires_at, is_revoked.",
         ["to_dict() → dict"]),
        ("Notification","in-app notification: user_id, title, message, notification_type, submission_id, is_read.",
         ["to_dict() → dict"]),
        ("Device","tracked device record used by admin module.",
         ["to_dict() — includes human-readable 'last_active' string"]),
        ("BDProject / BDFollowUp / BDContact / BDActivity","Business Development entities with relational links.",
         ["to_dict() for each — BD card-style payload"]),
        ("AdminPersonalProject / AdminPersonalProgressStep","Personal project tracking with checklist steps and progress %.",
         ["to_dict() — computes progress percentage from steps"]),
        ("DocHubDocument / DocHubAccess","Document hub storage and per-user access flags.",
         ["to_dict() — includes content/refs for content-type docs"]),
        ("MmrChargeableConfig","Single-row JSON config for MMR chargeable rules.",
         []),
    ]
    for name, desc, methods in models:
        story.append(KeepTogether([
            Paragraph(name, s["h3"]),
            Paragraph(desc, s["body"]),
        ] + ([Paragraph("Key methods:", s["small"])] +
              [_bp(m, s) for m in methods] if methods else []) +
            [Spacer(1,0.15*cm)]))

    # ══════════════════════════════════════════════════════════════════════
    # 5. COMMON
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("5", "Common Utilities — common/", s))
    story.append(Paragraph(
        "The <b>common/</b> package is imported by every module. It prevents code "
        "duplication and ensures consistent behaviour across the application.", s["body"]))

    common_files = [
        ("config_validator.py", [
            ("validate_config(app) → (bool, list)",
             "Checks SECRET_KEY, JWT_SECRET_KEY and DATABASE_URL for unsafe values in production. Returns (is_valid, error_list). Called at app factory startup."),
        ]),
        ("jwt_session.py", [
            ("sync_access_session_row(jti, jwt_payload) → Session | None",
             "Ensures a Session row exists for the given JTI. Used by the JWT blocklist loader when a token arrives via cookie and no row was inserted by login (e.g. cross-device token share)."),
        ]),
        ("error_responses.py", [
            ("error_response(message, status_code, error_code, details) → (Response, int)",
             "Returns JSON {success:false, error:…, error_code:…, details:…}. Used by every API route for consistent error shapes."),
            ("success_response(data, message, status_code) → (Response, int)",
             "Returns JSON {success:true, data:…, message:…}."),
            ("handle_exceptions(f)",
             "Decorator that wraps a route in try/except and returns error_response(500) on unhandled exceptions."),
        ]),
        ("utils.py", [
            ("random_id(prefix='') → str", "UUID4 hex with optional prefix — used to generate submission_id and job_id."),
            ("ensure_dir(path)", "os.makedirs with exist_ok=True."),
            ("write_job_state / read_job_state", "Read/write a JSON job-state file in JOBS_DIR (file-based fallback when DB unavailable)."),
            ("mark_job_started / update_job_progress / mark_job_done", "Update Job row in DB and write state file."),
            ("upload_file_to_cloud(file_path, public_id) → url", "Upload a local file to Cloudinary and return the secure URL."),
            ("upload_base64_to_cloud(data_url, public_id) → url", "Decode a base64 data URL and upload to Cloudinary."),
            ("get_image_for_pdf(url_or_b64) → BytesIO | None", "Download image from URL (with retry) or decode base64, returning bytes for ReportLab."),
            ("is_path_safe_for_directory(base, path) → bool", "Prevent path traversal by confirming resolved path is inside base directory."),
        ]),
        ("db_utils.py", [
            ("create_submission_db(…) → Submission", "Insert a new Submission row; returns the committed object."),
            ("create_job_db(submission_id) → Job", "Insert a pending Job row for a submission."),
            ("update_job_progress_db(job_id, progress, message)", "Set Job.progress and update timestamp."),
            ("complete_job_db(job_id, result_data)", "Set Job.status='completed', store result_data JSON."),
            ("fail_job_db(job_id, error_message)", "Set Job.status='failed', store error string."),
            ("get_job_status_db(job_id) → dict", "Return serialised Job or {status:'not_found'}."),
        ]),
        ("module_base.py", [
            ("process_report_job(sub_id, job_id, app, module_name, create_excel_report, create_pdf_report)",
             "Standard background job pipeline shared by HVAC, Civil, and Cleaning. Steps: mark started → load submission → generate Excel → upload → generate PDF → upload → complete. Each step updates job progress (10 → 30 → 45 → 60 → 75 → 100)."),
        ]),
        ("security.py", [
            ("sanitize_filename(name) → str", "Remove non-alphanumeric chars except dots and dashes."),
            ("safe_path_join(base, *parts) → str | None", "Return joined path only if it stays inside base; returns None on traversal attempt."),
            ("validate_json_request(required_fields) → decorator", "Raise 400 if required JSON fields are missing."),
            ("validate_file_upload(file, allowed_exts, max_mb) → (bool, msg)", "Check extension and size."),
            ("log_security_event(event, user_id, details)", "Write a WARNING-level security audit entry."),
            ("check_cloudinary_configured() → bool", "Return True if all three Cloudinary env vars are set."),
        ]),
        ("email_service.py", [
            ("send_email(to, subject, body_html, body_text, attachments) → (bool, msg)",
             "Primary email sending function. Tries Brevo HTTP API → Mailjet HTTP API → SMTP in order, depending on configured credentials. Returns success flag and message."),
            ("send_password_reset_email(user, temp_password)", "Composes and sends a password reset email using send_email."),
            ("is_email_configured() → bool", "Returns True if at least one email provider is configured."),
        ]),
        ("cache.py", [
            ("get_redis_connection() → Redis | None", "Return Redis client from REDIS_URL, or None if unavailable."),
            ("cached(key, ttl=3600) → decorator", "Cache the return value of the decorated function in Redis for ttl seconds."),
            ("invalidate_cache(key)", "Delete a key from Redis."),
        ]),
        ("retry_utils.py", [
            ("upload_to_cloudinary_with_retry(data, public_id, retries=3) → url",
             "Cloudinary upload with exponential backoff on transient failures."),
            ("fetch_url_with_retry(url, retries=3) → bytes", "HTTP GET with retry."),
        ]),
        ("validation.py", [
            ("HVACItemSchema, CivilWorkItemSchema, CleaningSubmissionSchema (Marshmallow)",
             "Field-level schemas with type coercion and missing/required checks for API payloads."),
            ("validate_request(schema_class, data) → (errors_dict | None, loaded_data | None)",
             "Load data through a schema and return validation errors or the clean object."),
        ]),
        ("workflow_notifications.py", [
            ("send_team_notification(submission, action_user, action_label)",
             "Send an in-app (and optionally email) notification to the relevant team members when a workflow action occurs."),
        ]),
    ]

    for filename, fns in common_files:
        story.append(Paragraph(filename, s["h2"]))
        fn_data = [["Function / Class", "Description"]] + [[a, b] for a, b in fns]
        story.append(_tbl(fn_data, [5.5*cm, 10*cm]))
        story.append(Spacer(1,0.2*cm))

    # ══════════════════════════════════════════════════════════════════════
    # 6. AUTH
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("6", "Authentication — app/auth/routes.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/api/auth</b>. Handles registration, login, token refresh, "
        "logout, profile, default signature, and password change.", s["body"]))

    story.append(_tbl([
        ["Function","Method","Path","Auth","Description"],
        ["validate_email(email)","—","—","—","Regex email check used before DB query."],
        ["validate_password(pw)","—","—","—","Min 8 chars, upper, lower, digit. Returns (ok, msg)."],
        ["log_audit(…)","—","—","—","Writes AuditLog row with IP and user-agent."],
        ["register","POST","/api/auth/register","None","Create user; validates uniqueness, hashes pw."],
        ["login","POST","/api/auth/login","None (rate-limited)","Verify creds → issue access+refresh JWT → Session row → set cookies."],
        ["refresh","POST","/api/auth/refresh","Refresh JWT","Mint new access token from valid refresh token."],
        ["logout","POST","/api/auth/logout","JWT","Revoke Session row, clear cookies."],
        ["get_current_user","GET","/api/auth/me","JWT","Return caller's User.to_dict()."],
        ["update_signature_default","POST","/api/auth/signature-default","JWT","Store base64 signature + default comment on User."],
        ["change_password","POST","/api/auth/change-password","JWT","Verify old pw, update hash, revoke all sessions (force re-login)."],
    ], [3.5*cm, 1.5*cm, 4.5*cm, 2.5*cm, 5.5*cm]))

    story.append(Paragraph("Login flow — step by step", s["h2"]))
    story += _code([
        "POST /api/auth/login  { username, password }",
        "",
        "1. Rate limit check (Flask-Limiter, 5/min)",
        "2. User.query.filter( username OR email == input ).first()",
        "3. user.check_password(password)  →  bcrypt.check_password_hash",
        "4. user.is_active check",
        "5. create_access_token(identity=str(user.id))   # JWT_ACCESS_TOKEN_EXPIRES",
        "6. create_refresh_token(identity=str(user.id))  # JWT_REFRESH_TOKEN_EXPIRES",
        "7. Session(token_jti=jti, expires_at=exp) → db.session.commit()",
        "8. set_access_cookies() + set_refresh_cookies()  # HTTP-only",
        "9. Return { access_token, refresh_token, user:{…}, requires_password_change }",
    ], s)
    story.append(Spacer(1,0.3*cm))

    # ══════════════════════════════════════════════════════════════════════
    # 7. ADMIN
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("7", "Admin Module — app/admin/routes.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/api/admin</b>. All routes require <b>JWT + role=admin</b>. "
        "Covers user management, submission editing, MMR config, BD projects, devices, "
        "DocHub access control, and a personal progress tracker.", s["body"]))

    story.append(Paragraph("User management functions", s["h2"]))
    story.append(_tbl([
        ["Function","Path","Description"],
        ["list_users",              "/users",                    "List all users; supports query filters."],
        ["get_user",                "/users/<id>",               "Single user detail + recent audit entries."],
        ["update_user",             "PUT /users/<id>",           "Change email, full_name, role, designation."],
        ["reset_user_password",     "/users/<id>/reset-password","Generate temp password, email it, mark password_changed=False."],
        ["toggle_user_active",      "/users/<id>/toggle-active", "Flip is_active; revokes sessions if deactivating."],
        ["update_user_access",      "/users/<id>/update-access", "Set any combination of module access flags."],
        ["set_user_designation",    "PUT /users/<id>/designation","Set GM/HR/supervisor/etc. designation."],
        ["delete_user",             "DELETE /users/<id>",        "Delete user and associated records."],
        ["get_user_activity",       "/users/<id>/activity",      "AuditLog entries for user."],
        ["get_users_by_designation","/users/by-designation/<d>", "Filter users by designation."],
    ], [4*cm, 5*cm, 6.5*cm]))

    story.append(Paragraph("Other admin functions", s["h2"]))
    story.append(_tbl([
        ["Function","Description"],
        ["dashboard_overview",         "Aggregate stats: user count, submissions by status, pending counts across all modules."],
        ["get_workflow_stats",          "Per-module submission counts, completion rates, recent activity."],
        ["update_submission",           "Admin-only direct edit of any submission's form_data or metadata."],
        ["close_submission",            "Admin force-close a submission at any workflow stage."],
        ["mmr_chargeable_config GET/PUT","Load or replace the MMR chargeable-classification JSON rules."],
        ["mmr_chargeable_preview",      "Test a set of rows against the chargeable rules and return classification preview."],
        ["bd_dashboard_data",           "BD projects, follow-ups, contacts, and statistics in one payload."],
        ["bd_create/update_project",    "CRUD for BD projects."],
        ["bd_import_projects_excel",    "Parse an Excel upload and bulk-insert BD projects."],
        ["list/create_device",          "Device register management."],
        ["import_devices_excel",        "Bulk device import from Excel."],
        ["list_dochub_access_users",    "Return per-user DocHub access flags."],
        ["set_dochub_user_access",      "Grant or revoke DocHub access for a specific user."],
        ["personal_progress_*",         "CRUD for admin's personal task/project checklist with step tracking."],
    ], [4.5*cm, 11*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 8. WORKFLOW
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("8", "Workflow Engine — app/workflow/routes.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/api/workflow</b>. All routes use JWT. This module is the "
        "multi-stage approval backbone used by Civil, HVAC, Cleaning, and Inspection "
        "submissions (HR has its own separate workflow in module_hr).", s["body"]))

    story.append(Paragraph("Workflow stages", s["h2"]))
    story.append(_tbl([
        ["Stage (workflow_status)","Actor","Endpoint"],
        ["submitted",          "Submitter (auto)",      "POST /submit"],
        ["operations_manager_review", "Operations Manager", "POST /approve-ops-manager"],
        ["bd_procurement_review",     "BD / Procurement",  "POST /approve-bd  or  /approve-procurement"],
        ["general_manager_review",    "General Manager",   "POST /approve-gm"],
        ["completed",          "System",                  "After GM approval"],
        ["rejected",           "Any approver",            "POST /reject"],
    ], [5*cm, 4*cm, 6.5*cm]))

    story.append(Paragraph("Key helper functions (non-route)", s["h2"]))
    story.append(_tbl([
        ["Helper","Description"],
        ["_dashboard_persona(user)","Returns 'admin'/'manager'/'user' to tailor dashboard data."],
        ["_hero_metrics_for_user(user)","Builds the four headline metric cards shown on the workflow dashboard."],
        ["_forms_needing_completion_count(user)","Count of submissions where the current user is a required next approver."],
        ["_filter_inspection(submissions, user)","Visibility filter for inspection submissions."],
        ["_filter_hr(submissions, user)","Visibility filter for HR submissions."],
        ["_completion_rate_pct(user)","Percentage of completed vs total relevant submissions."],
        ["_time_ago(dt)","Human-readable relative time string ('2 hours ago')."],
        ["_signature_url_from_field(field_value)","Extract a usable URL or base64 string from a stored signature field."],
        ["can_edit_submission(user, submission)","Returns True if the user is allowed to edit the given submission."],
        ["_admin_reviewers_for_history(submission)","Resolve the list of approvers who should appear in history view."],
    ], [5*cm, 10.5*cm]))

    story.append(Paragraph("Approval route pattern (example)", s["h2"]))
    story += _code([
        "POST /api/workflow/submissions/<submission_id>/approve-ops-manager",
        "",
        "1. @jwt_required() — validate token",
        "2. Verify user.designation == 'operations_manager' or role == 'admin'",
        "3. submission = Submission.query.filter_by(submission_id=…).first()",
        "4. Verify submission.workflow_status == 'submitted'",
        "5. form_data = dict(submission.form_data or {})   # copy for ORM detection",
        "6. form_data['operations_manager_signature'] = request.json.get('signature')",
        "7. form_data['operations_manager_comments']  = request.json.get('comments')",
        "8. submission.workflow_status = 'bd_procurement_review'",
        "9. submission.operations_manager_id = user.id",
        "10. db.session.commit()",
        "11. send_team_notification(submission, user, 'approved')",
        "12. Return {success:true, message:'Forwarded to BD/Procurement'}",
    ], s)

    # ══════════════════════════════════════════════════════════════════════
    # 9. HR MODULE
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("9", "HR Module — module_hr/routes.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/hr</b>. All routes require JWT. The HR module handles "
        "11 form types through a two-stage approval chain: Employee → HR → General Manager.", s["body"]))

    story.append(Paragraph("Helper functions", s["h2"]))
    story.append(_tbl([
        ["Helper","Description"],
        ["get_current_user()","Resolve User from JWT identity string."],
        ["_hr_form_context(user)","Returns {is_hr, is_gm} booleans — used to show/hide fields in templates."],
        ["create_notification(user_id, title, message, type, submission_id)","Insert a Notification row for one user."],
        ["get_form_type_display(module_type)","Maps 'hr_leave_application' → 'Leave Application'."],
    ], [5*cm, 10.5*cm]))

    story.append(Paragraph("Page routes (HTML views)", s["h2"]))
    story.append(_tbl([
        ["Handler","Path","Purpose"],
        ["hr_dashboard",              "/hr/",                           "Main HR dashboard page."],
        ["my_requests",               "/hr/my-requests",                "Employee's own submission history."],
        ["leave_application_form",    "/hr/leave-application-form",     "Leave form HTML."],
        ["commencement_form",         "/hr/commencement-form",          "Commencement form HTML."],
        ["duty_resumption_form",      "/hr/duty-resumption-form",       "Duty resumption HTML."],
        ["contract_renewal_form",     "/hr/contract-renewal-form",      "Contract renewal HTML."],
        ["performance_evaluation_form","/hr/performance-evaluation-form","Evaluation HTML."],
        ["grievance_form",            "/hr/grievance-form",             "Grievance HTML."],
        ["interview_assessment_form", "/hr/interview-assessment-form",  "Interview assessment HTML."],
        ["passport_release_form",     "/hr/passport-release-form",      "Passport release HTML."],
        ["staff_appraisal_form",      "/hr/staff-appraisal-form",       "Staff appraisal HTML."],
        ["station_clearance_form",    "/hr/station-clearance-form",     "Station clearance HTML."],
        ["visa_renewal_form",         "/hr/visa-renewal-form",          "Visa renewal HTML."],
        ["pending_review",            "/hr/pending-review",             "HR review queue."],
        ["gm_approval",               "/hr/gm-approval",                "GM approval queue."],
        ["approved_forms",            "/hr/approved-forms",             "Approved submissions archive."],
        ["hr_print",                  "/hr/print/<id>",                 "Print-ready HTML view of a submission."],
        ["hr_download_docx",          "/hr/download-docx/<id>",         "Stream DOCX file download."],
        ["hr_download_pdf",           "/hr/download-pdf/<id>",          "Stream PDF file download."],
    ], [4.5*cm, 5.5*cm, 5.5*cm]))

    story.append(PageBreak())
    story.append(Paragraph("API routes (JSON)", s["h2"]))
    story.append(_tbl([
        ["Handler","Method","Path","Who can call","Description"],
        ["submit_hr_form",             "POST",  "/hr/api/submit",                     "All authenticated users","Create Submission (workflow_status=hr_review), notify all HR users."],
        ["get_my_submissions",         "GET",   "/hr/api/my-submissions",             "All","Return caller's own HR submissions."],
        ["get_user_permissions",       "GET",   "/hr/api/user-permissions",           "All","Return {can_review_hr, can_approve_gm, is_admin}."],
        ["get_pending_hr_review",      "GET",   "/hr/api/pending-hr-review",          "HR / Admin","Submissions with workflow_status=hr_review."],
        ["get_pending_gm_approval",    "GET",   "/hr/api/pending-gm-approval",        "GM / Admin","Submissions with workflow_status=gm_review."],
        ["get_approved_hr_submissions","GET",   "/hr/api/approved-hr-submissions",    "HR / GM / Admin","Submissions with workflow_status=approved."],
        ["hr_approve",                 "POST",  "/hr/api/hr-approve/<id>",            "HR / Admin","Add hr_signature, hr_comments, optional form_data_hr, advance to gm_review."],
        ["hr_reject",                  "POST",  "/hr/api/hr-reject/<id>",             "HR / Admin","Reject with reason; notify submitter."],
        ["gm_approve",                 "POST",  "/hr/api/gm-approve/<id>",            "GM / Admin","Add gm_signature, gm_comments; mark approved/completed; notify all parties."],
        ["gm_reject",                  "POST",  "/hr/api/gm-reject/<id>",             "GM / Admin","Reject with reason; notify submitter."],
        ["get_hr_submissions",         "GET",   "/hr/api/submissions",                "HR / GM / Admin","All HR submissions with filters."],
        ["get_notifications",          "GET",   "/hr/api/notifications",              "All","Notification list for current user."],
        ["get_unread_count",           "GET",   "/hr/api/notifications/unread-count", "All","Integer count of unread notifications."],
        ["mark_notification_read",     "POST",  "/hr/api/notifications/<id>/read",    "All","Mark one notification as read."],
        ["mark_all_notifications_read","POST",  "/hr/api/notifications/mark-all-read","All","Mark all as read."],
    ], [4.5*cm, 1.3*cm, 4.5*cm, 2.5*cm, 4.7*cm]))

    story.append(Paragraph("HR approval — code pattern", s["h2"]))
    story += _code([
        "# hr_approve endpoint (key logic only)",
        "form_data = dict(submission.form_data or {})   # copy — critical for ORM JSON detection",
        "form_data['hr_reviewed_by_id']   = user.id",
        "form_data['hr_reviewed_by_name'] = user.full_name",
        "form_data['hr_reviewed_at']      = datetime.now().isoformat()",
        "form_data['hr_comments']         = data.get('comments', '')",
        "form_data['hr_signature']        = data.get('signature', '')",
        "for k, v in (data.get('form_data_hr') or {}).items():",
        "    form_data[k] = v   # e.g. hr_balance_cf, hr_checked",
        "submission.form_data     = form_data",
        "submission.workflow_status = 'gm_review'",
        "db.session.commit()",
        "# then notify GM users via create_notification()",
    ], s)
    story.append(_note(
        "Important: Always assign a new dict copy before mutating form_data. "
        "SQLAlchemy's JSON column type does not track in-place mutations; "
        "without a new dict assignment the changes are silently lost on commit.", s))

    # ══════════════════════════════════════════════════════════════════════
    # 10. HR PDF BUILDER
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("10", "HR PDF Builder — module_hr/hr_pdf_builder.py", s))
    story.append(Paragraph(
        "Builds professional A4 PDFs using <b>ReportLab</b> directly — no intermediate "
        "format. Each form type has a dedicated <b>_build_*</b> function that constructs "
        "the exact table layout of the official form.", s["body"]))

    story.append(Paragraph("Shared building blocks", s["h2"]))
    story.append(_tbl([
        ["Function","Description"],
        ["_fmt(v)","Format any value as string; returns em-dash for empty/None."],
        ["_fd(fd, key)","Safe dict get with _fmt fallback."],
        ["_sig_to_image(data_url, w_mm, h_mm)","Decode base64 data URL → ReportLab Image; optionally uses Pillow to knock out white background."],
        ["_get_styles()","Return dict of named ParagraphStyles (LABEL, VALUE, HEADER, SECTION, etc.)."],
        ["_header_table(title, submission_id, doc_no)","Render the Injaaz logo, form title, and reference bar at the top of every PDF."],
        ["_section_bar(title) / _section_bar_numbered(n, title)","Coloured full-width section header row."],
        ["_data_table(rows, col_widths)","Generic label/value two-column table."],
        ["_form_fields(pairs)","Shortcut to build a _data_table from (label, value) pairs."],
        ["_long_field(label, value)","Full-width text area row."],
        ["_rating_table(rows)","5-column rating table (criterion + score 1–5)."],
        ["_checklist_table(items, checked_set)","Checkbox grid — ticked or empty per item."],
        ["_signature_block(signers)","Multi-column row with name label, signature image, and date."],
        ["_footer_block(doc_no, issue_date)","Document control footer."],
        ["_fstyles / _flv / _fsec / _fchk / _fsig / _ftable","Compact inline builders for the later-form template style."],
        ["_leave_tick(fd, key, label)","Returns '[✓] Label' or '[ ] Label' for leave type checkbox rows."],
    ], [4.5*cm, 11*cm]))

    story.append(Paragraph("Form-specific build functions", s["h2"]))
    story.append(_tbl([
        ["Function","Form covered","Notable features"],
        ["_build_leave",                 "Leave Application",     "29-row table mirroring the Word doc; leave type checkboxes; HR-only section with balance C/F, contract year, paid/unpaid."],
        ["_build_commencement",          "Commencement",          "Employee joining info, bank details, reporting manager, dual signatures."],
        ["_build_duty_resumption",       "Duty Resumption",       "Leave dates, resumption date, manager remarks, three signatures (employee/HR/GM)."],
        ["_build_passport_release",      "Passport Release",      "Release/deposit toggle, purpose, date, three signatures."],
        ["_build_visa_renewal",          "Visa Renewal",          "Employee details, expiry, renewal date, three signatures."],
        ["_build_station_clearance",     "Station Clearance",     "Departure checklist with 14 checkbox items (equipment return, system access, etc.)."],
        ["_build_grievance",             "Grievance",             "Complainant details, grievance description, parties involved, HR + GM signatures."],
        ["_build_interview_assessment",  "Interview Assessment",  "Rating matrix across competencies, recommendation, interviewer signature."],
        ["_build_staff_appraisal",       "Staff Appraisal",       "Detailed rating categories, strengths, improvement areas, overall score."],
        ["_build_performance_evaluation","Performance Evaluation","10 scored criteria, evaluator + HR + GM signatures."],
        ["_build_contract_renewal",      "Contract Renewal",      "Four category rating blocks (5 criteria each), recommendation, three signatures."],
    ], [4*cm, 3.5*cm, 8*cm]))

    story.append(Paragraph("Entry points", s["h2"]))
    story += _code([
        "# Called by module_hr/pdf_service.py",
        "build_hr_pdf(form_type, form_data, output_stream, submission_id=None) → bool",
        "  # Looks up form_type in _BUILDERS dict, calls the _build_* function,",
        "  # wraps in SimpleDocTemplate(A4), doc.build(story) to output_stream.",
        "",
        "supports_pdf(form_type) → bool",
        "  # Returns True if form_type is a key in _BUILDERS.",
    ], s)

    # ══════════════════════════════════════════════════════════════════════
    # 11. DOCX SERVICE
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("11", "HR DOCX Service — module_hr/docx_service.py", s))
    story.append(Paragraph(
        "Produces <b>Word documents</b> by merging submission data into professionally "
        "designed <b>.docx template files</b> using <b>docxtpl</b> (Jinja2-style "
        "placeholders). Signature images are inserted as inline images at exact cell "
        "positions.", s["body"]))

    story.append(_tbl([
        ["Function","Description"],
        ["_get_hr_documents_path()","Returns the path to the 'HR Documents - Main' template folder."],
        ["_get_template_path(form_type)","Locate the .docx template for a given form type; auto-detects whether it contains docxtpl placeholders."],
        ["_fmt_date(v)","Format date as DD/MM/YYYY; handles string, date, and datetime inputs."],
        ["_normalize_form_data_for_docx(form_data, form_type)","Map UI field names to template placeholder keys for each form type. Ensures every placeholder in the template has a matching key."],
        ["_build_generic_context(fd, form_type)","Build the full docxtpl context dict from form_data, applying date formatting and field normalization."],
        ["_add_signatures_to_context(doc, context, fd, form_type)","Decode each base64 signature in form_data into a docxtpl InlineImage and insert into the context at the correct key."],
        ["_signature_to_transparent_png(data_url)","Convert a base64 PNG/JPEG signature to a white-background PNG suitable for DOCX embedding."],
        ["_signature_to_inline_image(doc, data_url, width_mm)","Return a docxtpl InlineImage from a base64 data URL."],
        ["_post_render_leave_checkboxes(doc, fd)","After docxtpl render, scan the document for leave-type checkbox placeholders and tick the correct one."],
        ["_post_render_leave_options_integrity(doc, fd)","Ensure leave checkboxes are consistent (exactly one ticked)."],
        ["_post_render_leave_salary_advance(doc, fd)","Tick YES or NO for salary advance on the rendered document."],
        ["_post_render_interview_ratings(doc, fd)","Fill interview rating cells after template render."],
        ["_apply_post_render(doc, fd, form_type)","Dispatch to the appropriate post-render helpers for the given form type."],
        ["_generate_filled_docx_generic(submission, output_stream)","Main pipeline: get template → build context → render via docxtpl → post-render → write to stream."],
        ["generate_commencement_docx(submission, output_stream)","Commencement-specific generator with custom context and signature placement."],
        ["generate_performance_evaluation_docx(sub, stream)","Performance evaluation-specific generator."],
        ["generate_hr_docx(submission, output_stream)","Entry point called by the download route. Selects the correct generator for the form type."],
        ["get_supported_docx_forms()","Returns list of form type strings that have a DOCX template."],
        ["fit_docx_to_one_page(doc)","Reduce margins and font sizes on the rendered document to keep it on a single page if possible."],
    ], [5*cm, 10.5*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 12. PRINT UTILS
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("12", "HR Print Utilities — module_hr/print_utils.py", s))
    story.append(Paragraph(
        "Generates <b>HTML fragments</b> suitable for browser printing or embedding in "
        "the <b>hr_print.html</b> template. The print view is available at "
        "<b>/hr/print/&lt;submission_id&gt;</b> and renders all fields plus embedded "
        "signature images.", s["body"]))
    story.append(_tbl([
        ["Function","Description"],
        ["_esc(v)","HTML-escape a value for safe insertion into markup."],
        ["_fmt_date(v)","Format a date value as DD/MM/YYYY."],
        ["_row(label, value)","Return an HTML table row with a bold label cell and a value cell."],
        ["_sig_row(label, data_url)","Return an HTML row with an embedded base64 signature image (or blank if absent)."],
        ["render_leave_print(fd, sid)","Build the complete Leave Application HTML table including all leave details and all four signature rows."],
        ["render_generic_print(module_type, fd, sid)","Iterate form_data key/value pairs (skipping hr_/gm_ internal keys) and render as a simple HTML table."],
        ["render_form_for_print(module_type, fd, sid)","Dispatch: leaves → render_leave_print; grievance/passport/duty → specialised renderers; all others → render_generic_print."],
    ], [4.5*cm, 11*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 13. HVAC
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("13", "HVAC & MEP Module — module_hvac_mep/", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/hvac-mep</b>. Handles HVAC and MEP site visit forms. "
        "Report generation (Excel + PDF) runs asynchronously via a background thread.", s["body"]))
    story.append(_tbl([
        ["Function / Route","Auth","Description"],
        ["index  GET /hvac-mep/form",         "JWT","Render the HVAC form page. Checks access_hvac flag."],
        ["dropdowns  GET /hvac-mep/dropdowns","None","Return dropdown JSON (equipment types, observations). Cached if Redis available."],
        ["save_draft  POST /hvac-mep/save-draft","None","Save draft JSON to a local file keyed by a draft ID."],
        ["upload_photo  POST /hvac-mep/upload-photo","Optional JWT","Validate file (≤10MB, image type) → upload to Cloudinary → return URL."],
        ["submit  POST /hvac-mep/submit",     "Optional JWT","Validate payload → create_submission_db → create_job_db → executor.submit(process_job) → return {job_id}."],
        ["status  GET /hvac-mep/status/<job_id>","None","Poll get_job_status_db(job_id) → return {status, progress, result_data}."],
        ["download_file  GET /hvac-mep/download/<job_id>/<type>","None","Stream Excel or PDF from cloud URL stored in job.result_data."],
        ["process_job(sub_id, job_id, …)","Background","Full pipeline via common.module_base.process_report_job: Excel → Cloudinary → PDF → Cloudinary → complete."],
    ], [5*cm, 2.5*cm, 8*cm]))

    story.append(Paragraph("Background report pipeline", s["h2"]))
    story += _code([
        "# common/module_base.py — process_report_job()",
        "mark_job_started(job_id)                          # progress = 10",
        "submission = get_submission_db(sub_id)",
        "excel_bytes = create_excel_report(submission)      # progress = 30",
        "excel_url   = upload_file_to_cloud(excel_bytes)   # progress = 45",
        "pdf_bytes   = create_pdf_report(submission)        # progress = 60",
        "pdf_url     = upload_file_to_cloud(pdf_bytes)     # progress = 75",
        "complete_job_db(job_id, {excel: excel_url, pdf: pdf_url})  # 100",
    ], s)

    # ══════════════════════════════════════════════════════════════════════
    # 14-16. Civil / Cleaning / Inspection (combined — same pattern)
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("14", "Civil Works Module — module_civil/", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/civil</b>. Identical structure to HVAC/MEP. "
        "Key routes: <b>GET /civil/form</b> (JWT), <b>POST /civil/submit</b> (optional JWT), "
        "<b>GET /civil/status/&lt;job_id&gt;</b>, <b>POST /civil/upload-photo</b>. "
        "Background pipeline uses the same <b>process_report_job</b> from common.", s["body"]))
    story.append(Paragraph(
        "The Civil module's <b>civil_generators.py</b> implements <b>create_excel_report</b> "
        "and <b>create_pdf_report</b> using openpyxl/XlsxWriter and ReportLab respectively, "
        "with Civil-specific field layout and photo embedding.", s["body"]))

    story.append(_sec("15", "Cleaning Module — module_cleaning/", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/cleaning</b>. Same pattern as HVAC and Civil. "
        "Notable difference: <b>submit_with_urls</b> requires JWT while plain <b>submit</b> "
        "accepts unauthenticated requests (for mobile offline scenarios). "
        "Background report pipeline is identical.", s["body"]))

    story.append(_sec("16", "Inspection Module — module_inspection/", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/inspection</b>. A cross-trade wrapper. "
        "<b>_has_inspection_access(user)</b> returns True if the user has any of "
        "access_hvac, access_civil, or access_cleaning. The dashboard route "
        "redirects to the appropriate trade module or shows a combined view.", s["body"]))

    # ══════════════════════════════════════════════════════════════════════
    # 17. PROCUREMENT
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("17", "Procurement Module — module_procurement/", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/procurement</b>. All routes require JWT + access_procurement_module. "
        "Manages a materials catalogue, properties, and per-property material assignments.", s["body"]))
    story.append(_tbl([
        ["Function group","Routes","Description"],
        ["Dashboard & pages",         "/procurement/, /materials, /add-material",  "HTML dashboard pages."],
        ["Materials CRUD",            "/api/materials (GET, POST, DELETE)",         "List, add, delete materials. Includes recent activity feed."],
        ["Excel import/export",       "/api/import-excel, /export-excel, /sample-excel","Bulk import from Excel; export current catalogue; download a sample template."],
        ["Properties",                "/api/properties (GET, POST)",               "List and create property records."],
        ["Property materials",        "/api/properties/<id>/materials (GET, POST)","List or assign materials to a specific property."],
        ["Catalog by department",     "/api/catalog/<dept> (GET, POST, PUT, DELETE)","Full CRUD on the materials catalog filtered by department."],
        ["Registered properties",     "/api/registered-properties (GET)",          "List all registered property records."],
    ], [4*cm, 5.5*cm, 6*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 18. MMR
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("18", "MMR Reporting — module_mmr/", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/admin/mmr</b>. All routes require JWT. "
        "MMR handles CAFM data ingestion, analytics, report generation, scheduled "
        "email automation, and cycle lifecycle management.", s["body"]))

    story.append(Paragraph("Internal helper functions", s["h2"]))
    story.append(_tbl([
        ["Helper","Description"],
        ["_load_config() / _save_config(cfg)","Read/write the MMR JSON config file (schedule, recipients, paths)."],
        ["_env_schedule_override()","Read MMR schedule from environment variables — survives redeploys if the config file is ephemeral."],
        ["_dashboard_payload_from_path(path)","Parse an uploaded CAFM file and return structured analytics payload for the dashboard."],
        ["_save_report_to_folder(bytes, name)","Write a generated report to the configured local reports folder."],
        ["_save_email_report_to_network(bytes, name)","Write report to a configured network/UNC path (optional Windows feature)."],
        ["_save_report_to_drive(bytes, filename, path)","Save to a configurable drive/directory path."],
        ["_start_new_cycle / _approve_current_cycle / _complete_current_cycle","Lifecycle functions for the MMR cycle (upload → approve → email sent)."],
        ["_load_cycle_log / _save_cycle_log","Read/write the JSON cycle log file."],
        ["append_automation_activity(action, status, detail)","Append a timestamped entry to the automation activity log."],
        ["_activities_for_cycle_id(cycle_id)","Return activity log entries matching a cycle."],
        ["_report_filename(date, range_str, format)","Build a standardised report filename including date and format suffix."],
        ["_resolve_report_format(explicit)","Determine output format (xlsx/pdf/csv) from request or config."],
        ["_validate_injaaz_emails(raw)","Parse a comma-separated email string; validate each address; return (valid_list, error_msg)."],
    ], [5.5*cm, 10*cm]))

    story.append(Paragraph("API route handlers", s["h2"]))
    story.append(_tbl([
        ["Handler","Method","Description"],
        ["dashboard",              "GET",  "Render MMR dashboard HTML page."],
        ["upload",                 "POST", "Accept CAFM file upload → parse → start new cycle → return dashboard payload."],
        ["current_upload",         "GET",  "Return metadata of the currently staged upload."],
        ["clear_upload",           "POST", "Clear the staged upload file and reset cycle."],
        ["download_report",        "GET",  "Generate and stream the daily/custom date-range report."],
        ["download_report_monthly","GET",  "Generate and stream a monthly summary report."],
        ["save_to_folder",         "POST", "Generate report and save to the local reports folder."],
        ["save_to_drive",          "POST", "Generate and save to a configured network/drive path."],
        ["list_report_folder",     "GET",  "Return list of saved reports in the reports folder."],
        ["download_report_folder_file","GET","Stream a specific saved report file."],
        ["get_email_config",       "GET",  "Return current email schedule and recipients config."],
        ["save_email_config",      "POST", "Update email config (schedule time, timezone, recipients)."],
        ["send_email_now",         "POST", "Immediately generate report and send to configured recipients."],
        ["get_automation_status",  "GET",  "Return scheduler running/paused state, last run, next run, last result."],
        ["pause_automation",       "POST", "Pause the APScheduler job."],
        ["resume_automation",      "POST", "Resume the APScheduler job."],
        ["get_cycles",             "GET",  "Return list of all reporting cycles."],
        ["approve_cycle",          "POST", "Mark the current cycle as approved."],
        ["get_automation_activities","GET","Return automation activity log (last N entries)."],
    ], [4.5*cm, 1.5*cm, 9.5*cm]))

    story.append(Paragraph("Scheduler integration", s["h2"]))
    story += _code([
        "# APScheduler is initialised in Injaaz.py create_app()",
        "# MMR module registers a daily job when the config enables automation.",
        "# Key config keys (from _load_config()):",
        "#   schedule_enabled: true/false",
        "#   schedule_hour: 10         # local time in schedule_timezone",
        "#   schedule_minute: 0",
        "#   schedule_timezone: 'Asia/Dubai'   # default",
        "#   recipients: ['ops@company.com', ...]",
        "",
        "# Environment overrides (survive redeploys when config file is ephemeral):",
        "# MMR_SCHEDULE_ENABLED, MMR_SCHEDULE_HOUR, MMR_SCHEDULE_MINUTE, MMR_SCHEDULE_TIMEZONE",
    ], s)

    # ══════════════════════════════════════════════════════════════════════
    # 19. BD
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("19", "Business Development — app/bd/routes.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/bd</b>. All routes require JWT. "
        "Provides an email composition module that allows BD users to select completed "
        "submissions and email them with their generated report attachments to the GM "
        "or other recipients.", s["body"]))
    story.append(_tbl([
        ["Helper","Description"],
        ["_is_bd_user(user)","True if user has BD designation or is admin."],
        ["_parse_emails(raw)","Split comma-separated email string into list."],
        ["_collect_submission_attachments(submission_ids)","Gather Excel/PDF URLs from Job.result_data for a list of submission IDs."],
        ["_get_report_urls(submission)","Extract excel_url and pdf_url from the submission's most recent completed Job."],
        ["_get_gm_emails()","Query all users with designation=general_manager and return their email addresses."],
        ["_get_role_emails(role)","Query users by role and return emails."],
    ], [5*cm, 10.5*cm]))
    story.append(_tbl([
        ["Route","Method","Description"],
        ["email_module  /bd/email-module",                                "GET", "Render the BD email composition page."],
        ["list_email_attachments  /bd/email-module/attachments",          "GET", "Return all completed submissions with their Excel/PDF attachment URLs."],
        ["download_attachment  /bd/email-module/attachment/<id>/<type>",  "GET", "Stream one attachment file (Excel or PDF) from Cloudinary."],
        ["send_email_to_gm  /bd/email-module/send",                       "POST","Compose and send email with selected submission attachments to GM (or custom recipients)."],
    ], [7*cm, 1.5*cm, 7*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 20. DOCHUB
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("20", "DocHub — app/docs/routes.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/api/docs</b>. Most routes use <b>token_required</b> "
        "(JWT + valid non-revoked Session + is_active user). The inline image serve "
        "endpoint is intentionally public but uses unguessable UUID filenames.", s["body"]))
    story.append(_tbl([
        ["Function","Method","Path","Description"],
        ["access_check",              "GET",    "/api/docs/access-check",           "Verify the caller has DocHub access (DocHubAccess flag set for user)."],
        ["list_documents",            "GET",    "/api/docs",                        "Return all documents the caller is allowed to see."],
        ["create_document",           "POST",   "/api/docs",                        "Create a new content-type document with title and body."],
        ["upload_documents",          "POST",   "/api/docs/upload",                 "Upload one or more file-type documents (PDF, DOCX, etc.); store to Cloudinary or local."],
        ["get_document",              "GET",    "/api/docs/<id>",                   "Return full document including body/refs."],
        ["download_document",         "GET",    "/api/docs/<id>/download",          "Stream document file; DOCX converted to PDF via LibreOffice if available."],
        ["preview_upload_as_pdf",     "GET",    "/api/docs/<id>/preview",           "Return a PDF preview of the document (conversion via LibreOffice/docx2pdf)."],
        ["update_document",           "PATCH",  "/api/docs/<id>",                   "Update title, body, or file attachment."],
        ["delete_document",           "DELETE", "/api/docs/<id>",                   "Delete document record and cloud file."],
        ["upload_inline_editor_image","POST",   "/api/docs/inline-image",           "Upload image pasted into the rich-text editor; return local serve URL."],
        ["serve_inline_editor_image", "GET",    "/api/docs/inline/<filename>",      "No-auth serve of inline editor images (UUID filenames prevent enumeration)."],
        ["upload_inline_reference",   "POST",   "/api/docs/inline-reference",       "Attach a reference file to a document."],
        ["_has_dochub_access(user)",  "—","—",                                      "Returns True if DocHubAccess row exists for user, or user is admin."],
        ["_docx_to_pdf_cached(path)", "—","—",                                      "Convert a .docx to PDF using LibreOffice if available; cache result."],
    ], [4.5*cm, 1.4*cm, 4.8*cm, 5.8*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 21. REPORTS API
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("21", "Reports API — app/reports_api.py", s))
    story.append(Paragraph(
        "Blueprint prefix: <b>/api/reports</b>. JWT-protected. Allows on-demand "
        "regeneration of Excel and PDF reports for Civil, HVAC, and Cleaning submissions "
        "without re-submitting the form.", s["body"]))
    story.append(_tbl([
        ["Function","Method","Path","Description"],
        ["_user_can_access_submission(user, sub)","—","—","True if admin, submission owner, or workflow participant (supervisor/ops/gm)."],
        ["regenerate_excel","GET","/api/reports/regenerate/<id>/excel","Re-run create_excel_report for the module; stream result."],
        ["regenerate_pdf",  "GET","/api/reports/regenerate/<id>/pdf",  "Re-run create_pdf_report; stream result."],
        ["list_reports",    "GET","/api/reports/list/<module_type>",   "Return submissions for a module with their download URLs."],
        ["get_submission_details","GET","/api/reports/submission/<id>","Return submission detail including regenerate links."],
    ], [5*cm, 1.5*cm, 5.5*cm, 4.5*cm]))

    # ══════════════════════════════════════════════════════════════════════
    # 22. SECURITY
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("22", "Security Architecture", s))
    story.append(Paragraph("Authentication flow (JWT + sessions)", s["h2"]))
    story += _code([
        "Every protected route:",
        "  @jwt_required()                       # Flask-JWT-Extended decorator",
        "  ↓",
        "  JWTManager checks token signature + expiry",
        "  ↓",
        "  token_in_blocklist_loader(jti) called:",
        "      Session.query.filter_by(token_jti=jti).first()",
        "      → None or is_revoked=True  →  reject (401)",
        "      → found and not revoked    →  allow",
        "  ↓",
        "  get_jwt_identity()  →  user_id string",
        "  User.query.get(user_id)  →  user object",
    ], s)
    story.append(Paragraph("Password security", s["h2"]))
    story += _code([
        "# On register / password change:",
        "user.set_password(plain_text)",
        "  → bcrypt.generate_password_hash(plain_text).decode('utf-8')",
        "  → stored in user.password_hash",
        "",
        "# On login:",
        "user.check_password(plain_text)",
        "  → bcrypt.check_password_hash(user.password_hash, plain_text)",
        "  → True/False  (original plain text never stored)",
    ], s)
    story.append(Paragraph("Rate limiting", s["h2"]))
    story.append(Paragraph(
        "<b>Flask-Limiter</b> is applied to the login and registration endpoints. "
        "Default limit: <b>5 requests per minute</b>. If Redis is configured, limits "
        "are tracked across workers; otherwise in-memory (single worker only).", s["body"]))
    story.append(Paragraph("Path traversal prevention", s["h2"]))
    story += _code([
        "# common/security.py",
        "def safe_path_join(base_dir, *parts) -> str | None:",
        "    joined = os.path.realpath(os.path.join(base_dir, *parts))",
        "    if not joined.startswith(os.path.realpath(base_dir)):",
        "        log_security_event('path_traversal_attempt', ...)",
        "        return None",
        "    return joined",
    ], s)

    # ══════════════════════════════════════════════════════════════════════
    # 23. FLOWS
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("23", "End-to-End Request Flows", s))
    story.append(Paragraph("Flow A — Employee submits a Leave Application", s["h2"]))
    story += _code([
        "1.  Employee logs in → POST /api/auth/login → JWT access token stored in cookie",
        "2.  Employee opens /hr/leave-application-form → hr_leave_application_form() renders HTML",
        "3.  Employee fills form, draws signature in canvas (stored as base64 data URL)",
        "4.  POST /hr/api/submit  {form_type:'leave_application', employee_name:…, employee_signature:'data:…', …}",
        "    → submit_hr_form():",
        "         submission_id = 'HR-LEAVE_APPLICATION-' + uuid4().hex[:8].upper()",
        "         Submission(module_type='hr_leave_application', workflow_status='hr_review', form_data={…})",
        "         db.session.commit()",
        "         create_notification(hr_user_id, 'New HR Request', …) for each HR user",
        "    ← {success:true, submission_id:'HR-LEAVE_APPLICATION-XXXX'}",
        "",
        "5.  HR Officer opens /hr/pending-review → get_pending_hr_review() → list of hr_review submissions",
        "6.  POST /hr/api/hr-approve/HR-LEAVE_APPLICATION-XXXX",
        "    {signature:'data:…', comments:'Approved', form_data_hr:{hr_checked:'yes', hr_balance_cf:'10', …}}",
        "    → hr_approve():",
        "         form_data = dict(submission.form_data)   # copy",
        "         form_data['hr_signature'] = 'data:…'",
        "         submission.workflow_status = 'gm_review'",
        "         db.session.commit()",
        "         create_notification(gm_user_id, 'Pending Your Approval', …)",
        "    ← {success:true, message:'Forwarded to GM'}",
        "",
        "7.  GM opens /hr/gm-approval → get_pending_gm_approval()",
        "8.  POST /hr/api/gm-approve/HR-LEAVE_APPLICATION-XXXX  {signature:'data:…', comments:'Approved'}",
        "    → gm_approve():",
        "         form_data['gm_signature'] = 'data:…'",
        "         submission.workflow_status = 'approved'; submission.status = 'completed'",
        "         create_notification(employee_id, 'Request Approved', …)",
        "         create_notification(hr_reviewer_id, 'Approved by GM', …)",
        "    ← {success:true}",
        "",
        "9.  Employee downloads document:",
        "    GET /hr/download-pdf/HR-LEAVE_APPLICATION-XXXX",
        "    → hr_download_pdf() → generate_hr_pdf(submission, buf) → build_hr_pdf('leave_application', …)",
        "    ← stream PDF with all three signatures embedded",
    ], s)

    story.append(Paragraph("Flow B — Field inspector submits HVAC/MEP report", s["h2"]))
    story += _code([
        "1.  Inspector opens /hvac-mep/form (JWT checked, access_hvac verified)",
        "2.  GET /hvac-mep/dropdowns  ← cached equipment/observation options",
        "3.  Inspector uploads photos: POST /hvac-mep/upload-photo (each photo)",
        "       → validate_file_upload() → upload_to_cloudinary_with_retry() → return {url}",
        "4.  Inspector submits: POST /hvac-mep/submit  {site_name, visit_date, form_data:{items:[…]}}",
        "       → create_submission_db()  → Submission(status='submitted')",
        "       → create_job_db(sub_id)   → Job(status='pending')",
        "       → executor.submit(process_job, sub_id, job_id, config, app)",
        "    ← {job_id: 'job_abc123'}",
        "",
        "5.  Frontend polls: GET /hvac-mep/status/job_abc123  every 2 seconds",
        "    ← {status:'processing', progress:45}",
        "",
        "6.  Background thread (process_report_job):",
        "       create_excel_report(submission)  → .xlsx bytes",
        "       upload_file_to_cloud(.xlsx)       → excel_url",
        "       create_pdf_report(submission)     → .pdf bytes  (photos fetched from Cloudinary)",
        "       upload_file_to_cloud(.pdf)        → pdf_url",
        "       complete_job_db(job_id, {excel:excel_url, pdf:pdf_url})  # progress=100",
        "",
        "7.  Frontend receives: {status:'completed', result_data:{excel:…, pdf:…}}",
        "    → show download links",
        "8.  GET /hvac-mep/download/job_abc123/pdf  ← stream PDF",
    ], s)

    # ══════════════════════════════════════════════════════════════════════
    # 24. QUICK REFERENCE
    # ══════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(_sec("24", "Function & Method Quick Reference", s))
    story.append(Paragraph(
        "A consolidated index of key functions across the codebase for quick lookup.", s["body"]))

    qr_data = [
        ["Function","File","Purpose"],
        ["create_app()","Injaaz.py","Flask application factory; registers all blueprints and extensions."],
        ["validate_config(app)","common/config_validator.py","Startup config check; raises on critical failures."],
        ["sync_access_session_row(jti, payload)","common/jwt_session.py","Ensure a JWT session row exists (blocklist safety)."],
        ["error_response(msg, code, …)","common/error_responses.py","Standardised JSON error body."],
        ["success_response(data, msg)","common/error_responses.py","Standardised JSON success body."],
        ["random_id(prefix)","common/utils.py","Generate unique submission/job IDs."],
        ["upload_file_to_cloud(path)","common/utils.py","Cloudinary upload returning secure URL."],
        ["upload_base64_to_cloud(data_url)","common/utils.py","Base64 data URL → Cloudinary."],
        ["get_image_for_pdf(url_or_b64)","common/utils.py","Fetch/decode image for ReportLab embedding."],
        ["safe_path_join(base, *parts)","common/security.py","Path traversal guard."],
        ["send_email(to, subject, html, …)","common/email_service.py","Multi-provider email send (Brevo/Mailjet/SMTP)."],
        ["process_report_job(…)","common/module_base.py","Standard HVAC/Civil/Cleaning background job pipeline."],
        ["validate_request(schema, data)","common/validation.py","Marshmallow schema validation helper."],
        ["cached(key, ttl) decorator","common/cache.py","Redis-backed function result caching."],
        ["retry_on_failure(fn, n)","common/retry_utils.py","Re-call fn up to n times on exception."],
        ["create_submission_db(…)","common/db_utils.py","Insert Submission ORM row."],
        ["complete_job_db(job_id, result)","common/db_utils.py","Mark Job completed with result URLs."],
        ["User.set_password(pw)","app/models.py","Bcrypt hash and store password."],
        ["User.has_module_access(module)","app/models.py","Permission check respecting admin bypass."],
        ["Submission.to_dict(…)","app/models.py","API serialisation of a submission."],
        ["login()","app/auth/routes.py","Credential verification + JWT issuance + session row."],
        ["logout()","app/auth/routes.py","Session revocation + cookie clear."],
        ["hr_approve(submission_id)","module_hr/routes.py","HR sign-off; advance to gm_review stage."],
        ["gm_approve(submission_id)","module_hr/routes.py","GM final approval; mark approved/completed."],
        ["create_notification(user_id, …)","module_hr/routes.py","Insert Notification row for one user."],
        ["generate_hr_docx(submission, stream)","module_hr/docx_service.py","Entry point: pick template + merge + signatures."],
        ["generate_hr_pdf(submission, stream)","module_hr/pdf_service.py","Entry point: normalise data + build ReportLab PDF."],
        ["build_hr_pdf(form_type, fd, stream)","module_hr/hr_pdf_builder.py","Dispatch to _build_* function + doc.build()."],
        ["_sig_to_image(data_url, w, h)","module_hr/hr_pdf_builder.py","Base64 signature → ReportLab Image."],
        ["render_form_for_print(module, fd, id)","module_hr/print_utils.py","Build print-ready HTML for any HR form."],
        ["_normalize_form_data_for_docx(fd, ft)","module_hr/docx_service.py","Map UI keys to DOCX template placeholder keys."],
        ["upload()","module_mmr/routes.py","Accept CAFM file, parse, start new reporting cycle."],
        ["send_email_now()","module_mmr/routes.py","Immediately generate and email the MMR report."],
        ["_load_config()","module_mmr/routes.py","Read MMR schedule + email config JSON file."],
        ["_start_new_cycle(uploaded_by)","module_mmr/routes.py","Open a new reporting cycle in the cycle log."],
        ["append_automation_activity(…)","module_mmr/routes.py","Record automation event in activity log."],
        ["send_email_to_gm()","app/bd/routes.py","Compose and send email with report attachments."],
        ["download_document()","app/docs/routes.py","Stream DocHub document; DOCX→PDF if needed."],
        ["regenerate_excel/pdf()","app/reports_api.py","On-demand report regeneration without re-submit."],
    ]
    story.append(_tbl(qr_data, [5.5*cm, 5*cm, 5.5*cm]))

    story.append(Spacer(1, 0.5*cm))
    story.append(_callout(
        f"This document was generated on {gen}. It reflects the full function "
        "and method surface of the Injaaz platform as implemented. "
        "Re-run 'python scripts/generate_full_technical_doc.py' to refresh after code changes.", s))

    doc.build(story)


def main():
    out = os.path.join(PROJECT_ROOT, "docs", "Injaaz_Full_Technical_Documentation.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    build(out)
    print(f"Written: {out}")

if __name__ == "__main__":
    main()
