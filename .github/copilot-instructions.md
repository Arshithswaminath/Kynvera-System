# Injaaz App - AI Agent Instructions

## Project Overview
Injaaz is a Flask-based site-visit reporting application with modular form submission and async report generation. The app handles three distinct modules (HVAC/MEP, Civil, Cleaning), each with its own form submission flow that generates Excel and PDF reports.

## Architecture

### Dual Flask App Pattern
The codebase has **two Flask applications**:
1. **`Injaaz.py`** (legacy/main): Entry point using simple blueprints, `ThreadPoolExecutor` for background tasks, JSON-based job state stored in `generated/jobs/`
2. **`app/__init__.py`** (newer): Flask app factory pattern with SQLAlchemy, Flask-Migrate, JWT auth, Redis/RQ for background tasks

**Key Decision**: Most active development happens in the legacy `Injaaz.py` structure. The `app/` directory appears to be a parallel attempt at restructuring but is less complete.

### Module Structure Pattern
Each module (`module_hvac_mep/`, `module_civil/`, `module_cleaning/`) follows an identical pattern:
```
module_*/
  routes.py          # Flask blueprint with /form, /dropdowns, /save-draft, /submit, /job-status
  *_generators.py    # create_excel_report(), create_pdf_report() (placeholders or real implementations)
  templates/         # Jinja2 form HTML
  dropdown_data.json # (optional) form dropdown options
```

**Blueprint Registration**: `Injaaz.py` uses defensive imports with try/except blocks to allow partial deployment if a module fails to import.

### Job Submission Flow
1. User submits form via `/submit` POST with multipart form data
2. Files uploaded to `generated/uploads/` with unique IDs (`common.utils.save_uploaded_file`)
3. Submission saved to `generated/submissions/sub_<id>.json`
4. Job created with ID `job_<id>`, state tracked in `generated/jobs/job_<id>.json`
5. Background task (via `ThreadPoolExecutor`) generates Excel + PDF reports
6. Job state updated with progress (0-100) and result URLs
7. Frontend polls `/job-status/<job_id>` to check completion

**Critical**: All paths come from `current_app.config['GENERATED_DIR']`, `UPLOADS_DIR`, `JOBS_DIR` set by `Injaaz.py:create_app()`.

## Services & Utilities

### `common/utils.py`
Core utilities used across all modules:
- `random_id(prefix)`: Generate unique IDs like `sub_abc123`, `job_def456`
- `save_uploaded_file()`: Secure file upload with UUID-based naming
- `mark_job_started()`, `update_job_progress()`, `mark_job_done()`: JSON-based job state management

### Report Generation (`app/services/`)
- **`pdf_service.py`**: Uses ReportLab to generate structured PDFs with images (fetched via requests), tables, and styling
- **`excel_service.py`**: (Not examined but likely uses openpyxl/xlsxwriter per requirements)
- **`cloudinary_service.py`**: Optional image upload to Cloudinary (signatures, reports). Returns URLs or `None` on failure

### Background Tasks
- **Legacy approach**: `ThreadPoolExecutor` (2 workers) stored in `app.config['EXECUTOR']`
- **New approach**: Redis + RQ (`app/extensions.py` provides `get_rq_queue()`)
- **HVAC/MEP module**: Uses `module_hvac_mep/generator.py:process_submission()` for advanced report generation with email support

## Configuration

### Environment Variables
Defined in `app/config.py` (3 environments: dev/prod/testing):
- `SECRET_KEY`, `JWT_SECRET_KEY`
- `DATABASE_URL` (PostgreSQL)
- `REDIS_URL` (optional, for RQ tasks)
- `CLOUDINARY_*` (CLOUD_NAME, API_KEY, API_SECRET)
- `MAIL_*` (SERVER, PORT, USERNAME, PASSWORD, USE_TLS, etc.) for HVAC/MEP email reports
- `APP_BASE_URL` for generating absolute URLs in background tasks

**Local Development**: Copy `.env.example` to `.env` (not tracked in git).

### Directory Structure
Root `config.py` defines:
- `BASE_DIR`, `GENERATED_DIR`, `UPLOADS_DIR`, `JOBS_DIR`
- `MAX_UPLOAD_FILESIZE = 10MB`, `ALLOWED_EXTENSIONS = {png, jpg, jpeg, pdf, xlsx, csv}`

## Development Workflows

### Running Locally
```bash
# Option 1: Direct Python (legacy app)
python Injaaz.py  # Runs on http://localhost:5000 with debug=True

# Option 2: Flask app factory (newer structure)
flask --app app run

# Option 3: Docker Compose (recommended for production-like env)
docker-compose up
```

### Testing
Single test file exists: `tests/test_pdf_service.py`. No comprehensive test suite yet.

### Dependencies
- **Core**: Flask 2.2.5, gunicorn (production server)
- **Database**: Flask-SQLAlchemy, Flask-Migrate, psycopg2-binary
- **Auth**: flask-jwt-extended, flask-bcrypt
- **Reports**: reportlab (PDF), openpyxl (Excel), pandas, XlsxWriter
- **Background**: redis, rq
- **Cloud**: cloudinary, boto3

Install via: `pip install -r requirements-prods.txt` (note: filename has typo, not "prods")

## Key Conventions

### Import Resilience Pattern
Blueprints and generators use defensive imports:
```python
try:
    from .hvac_generators import create_excel_report, create_pdf_report
except Exception:
    # Provide dummy fallback functions
    def create_excel_report(data, output_dir):
        ...  # placeholder implementation
```
This allows partial deployment even if dependencies are missing.

### URL Generation in Background Tasks
Background tasks must save `base_url` in submission JSON:
```python
submission_data["base_url"] = request.host_url.rstrip('/')
```
Then use it to build absolute URLs: `base_url + url_for('download_generated', filename=..., _external=False)`

### File Download Route
Single route serves all generated files: `/{GENERATED_DIR}/<path:filename>` → `download_generated()` in `Injaaz.py`

## Integration Points

### Frontend (JavaScript)
- `static/main.js`, `static/form.js`, `static/site_form.js`, `static/dropdown_init.js`
- Typical flow: Fetch dropdowns, handle form submission, poll job status
- Job status polling: `GET /module/job-status/<job_id>` returns JSON with `state`, `progress`, `results`

### External Services
- **Cloudinary**: Optional image hosting (signatures, report uploads)
- **Email (SMTP)**: HVAC/MEP module can email reports via `generator.py:_send_email()`
- **PostgreSQL**: Database for auth/models (if using `app/` structure)
- **Redis**: Optional queue backend (not required for legacy ThreadPoolExecutor approach)

## Common Pitfalls

1. **Dual App Confusion**: Ensure you're editing the correct Flask app structure (legacy `Injaaz.py` vs. `app/__init__.py`)
2. **Path Resolution**: Always use `current_app.config['GENERATED_DIR']` etc., not hardcoded paths
3. **Job State Race Conditions**: Job JSON files are written/read without locks; avoid concurrent modifications
4. **Missing Email Config**: HVAC/MEP email reports silently skip if `MAIL_SERVER` not configured
5. **Docker vs. Local**: `Dockerfile` uses `requirements-prods.txt`; ensure local env matches

## Quick Reference

**Add a new module**: Copy `module_cleaning/` structure, update `Injaaz.py` to import/register blueprint  
**Debug job failures**: Read `generated/jobs/job_<id>.json` for error messages  
**Test report generation**: Call `create_excel_report(data, output_dir)` directly from a route or script  
**Check logs**: Flask logger outputs to stdout; use `app.logger.info()` or `logging.getLogger(__name__)`
