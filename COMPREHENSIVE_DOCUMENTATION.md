# 📚 Injaaz Application - Comprehensive Documentation

**Version:** 1.0  
**Last Updated:** 2024-12-30  
**Purpose:** Complete technical documentation for understanding the Injaaz application codebase, architecture, flows, and implementation details.

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Technology Stack](#technology-stack)
3. [Project Architecture](#project-architecture)
4. [Codebase Structure](#codebase-structure)
5. [Database Schema](#database-schema)
6. [Application Flows](#application-flows)
7. [API Endpoints](#api-endpoints)
8. [Key Methods & Patterns](#key-methods--patterns)
9. [File Upload & Storage](#file-upload--storage)
10. [Report Generation](#report-generation)
11. [Authentication & Authorization](#authentication--authorization)
12. [Workflow Management](#workflow-management)
13. [Deployment & Configuration](#deployment--configuration)

---

## 🎯 Executive Summary

**Injaaz** is a professional web application for managing site visit reports and inspections across three specialized modules:

- **HVAC & MEP** (Heating, Ventilation, Air Conditioning & Mechanical, Electrical, Plumbing)
- **Civil Works**
- **Cleaning Services**

### Core Capabilities

- ✅ Multi-user authentication with role-based access control
- ✅ Module-level permission management
- ✅ Dynamic form submissions with photo uploads
- ✅ Background report generation (Excel & PDF)
- ✅ Cloud storage integration (Cloudinary)
- ✅ Supervisor/Manager review workflow
- ✅ Progressive Web App (PWA) support
- ✅ Mobile-responsive design

### Application Type

- **Backend:** Flask-based RESTful API
- **Frontend:** Server-side rendered HTML with JavaScript
- **Database:** PostgreSQL (production) / SQLite (development)
- **Deployment:** Render.com (or similar cloud platform)

---

## 🛠️ Technology Stack

### Backend Framework

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.8+ | Core programming language |
| **Flask** | 2.2.5 | Web framework |
| **Gunicorn** | 20.1.0 | WSGI HTTP server (production) |
| **Werkzeug** | 2.2.3 | WSGI utility library |

### Database & ORM

| Technology | Version | Purpose |
|------------|---------|---------|
| **Flask-SQLAlchemy** | 3.0.3 | ORM for database operations |
| **Flask-Migrate** | 4.0.4 | Database migrations |
| **PostgreSQL** | Latest | Production database |
| **SQLite** | Built-in | Development database |
| **psycopg2-binary** | ≥2.9.6 | PostgreSQL adapter |

### Authentication & Security

| Technology | Version | Purpose |
|------------|---------|---------|
| **Flask-JWT-Extended** | 4.4.4 | JWT token management |
| **Flask-Bcrypt** | 1.0.1 | Password hashing |
| **Flask-Limiter** | 3.5.0 | Rate limiting |
| **Flask-WTF** | 1.2.1 | CSRF protection |

### Background Tasks & Caching

| Technology | Version | Purpose |
|------------|---------|---------|
| **Redis** | 4.6.0 | Caching & job queue (optional) |
| **RQ** | 1.1.0 | Redis Queue for background jobs |
| **ThreadPoolExecutor** | Built-in | Fallback job executor |

### Cloud Storage

| Technology | Version | Purpose |
|------------|---------|---------|
| **Cloudinary** | 1.29.0 | Image/file hosting |
| **boto3** | 1.26.99 | AWS S3 support (optional) |

### Report Generation

| Technology | Version | Purpose |
|------------|---------|---------|
| **ReportLab** | 4.4.6 | PDF generation |
| **openpyxl** | 3.1.2 | Excel file manipulation |
| **XlsxWriter** | 3.1.2 | Excel file creation |
| **pandas** | ≥2.3.3 | Data processing |
| **Pillow** | ≥11.0.0 | Image processing |

### Utilities

| Technology | Version | Purpose |
|------------|---------|---------|
| **requests** | 2.31.0 | HTTP client |
| **python-dotenv** | 1.0.0 | Environment variable management |
| **tenacity** | 8.2.3 | Retry logic with exponential backoff |
| **marshmallow** | 3.20.1 | Data serialization/validation |

### Frontend Technologies

| Technology | Purpose |
|------------|---------|
| **HTML5** | Markup |
| **CSS3** | Styling |
| **JavaScript (ES6+)** | Client-side logic |
| **Bootstrap 5** | UI framework |
| **SignaturePad.js** | Digital signature capture |
| **PWA** | Progressive Web App features |

---

## 🏗️ Project Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Web Browser  │  │ Mobile Web   │  │  PWA App     │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼──────────────────┼──────────────────┼───────────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FLASK APPLICATION LAYER                      │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    Injaaz.py                               │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │ │
│  │  │ Auth Routes  │  │ Admin Routes │  │ Module Routes│   │ │
│  │  │ /api/auth/*  │  │/api/admin/* │  │/hvac-mep,etc │   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │ │
│  │  │ Workflow     │  │  Services    │  │ Background   │   │ │
│  │  │ Routes       │  │  Layer       │  │ Jobs         │   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────┬──────────────┬──────────────┬──────────────┬────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  PostgreSQL  │  │  Cloudinary  │  │    Redis     │  │  File System │
│   Database   │  │  (Cloud CDN)  │  │  (Optional)  │  │  (Local)     │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### Architecture Layers

#### 1. **Presentation Layer**
- Server-side rendered HTML templates
- JavaScript for client-side interactivity
- Progressive Web App (PWA) capabilities
- Responsive design for mobile/desktop

#### 2. **Application Layer**
- Flask blueprints for route organization
- Business logic separation
- Request/response handling
- Error handling & logging

#### 3. **Service Layer**
- PDF generation service
- Excel generation service
- Cloudinary integration service
- Email service (optional)

#### 4. **Data Layer**
- SQLAlchemy ORM models
- Database connection pooling
- Transaction management
- Query optimization

#### 5. **Storage Layer**
- PostgreSQL for structured data
- Cloudinary for file storage
- Local filesystem fallback
- Redis for caching (optional)

---

## 📂 Codebase Structure

### Directory Tree

```
Injaaz-App/
│
├── 📄 Core Application Files
│   ├── Injaaz.py              # Flask app factory & main entry point
│   ├── config.py              # Configuration management
│   ├── wsgi.py                # WSGI entry point (production)
│   ├── manage.py              # Management commands
│   └── init.py                # Package initialization
│
├── 📁 app/                    # Core Application Package
│   ├── __init__.py            # App initialization
│   ├── models.py              # SQLAlchemy database models
│   ├── config.py              # App-specific configuration
│   ├── extensions.py          # Flask extensions initialization
│   ├── forms.py               # WTForms definitions
│   ├── form_schemas.py        # Form validation schemas
│   ├── middleware.py          # Custom middleware
│   ├── reports_api.py         # Reports API endpoints
│   │
│   ├── 📁 auth/               # Authentication Module
│   │   ├── __init__.py
│   │   └── routes.py          # Login, register, JWT routes
│   │
│   ├── 📁 admin/              # Admin Module
│   │   ├── __init__.py
│   │   └── routes.py          # User management, access control
│   │
│   ├── 📁 workflow/           # Workflow Module
│   │   ├── __init__.py
│   │   └── routes.py          # Supervisor/Manager review routes
│   │
│   ├── 📁 services/           # Business Logic Services
│   │   ├── pdf_service.py     # PDF generation utilities
│   │   ├── excel_service.py   # Excel generation utilities
│   │   ├── professional_pdf_service.py  # Professional PDF templates
│   │   ├── professional_excel_service.py  # Professional Excel templates
│   │   ├── cloudinary_service.py  # Cloudinary integration
│   │   └── email_service.py  # Email sending (optional)
│   │
│   └── 📁 tasks/              # Background Job Tasks
│       ├── generate_report.py # Report generation worker
│       ├── worker.py          # Background worker
│       └── session_cleanup.py # Session cleanup tasks
│
├── 📁 module_hvac_mep/        # HVAC & MEP Module
│   ├── __init__.py
│   ├── routes.py              # Form routes & submission handling
│   ├── generator.py           # Report generators
│   ├── hvac_generators.py     # PDF/Excel generators
│   ├── dropdown_data.json     # Dropdown options
│   └── 📁 templates/
│       └── hvac_mep_form.html # Form template
│
├── 📁 module_civil/           # Civil Works Module
│   ├── __init__.py
│   ├── routes.py              # Form routes & submission handling
│   ├── civil_generators.py    # PDF/Excel generators
│   └── 📁 templates/
│       └── civil_form.html    # Form template
│
├── 📁 module_cleaning/        # Cleaning Services Module
│   ├── __init__.py
│   ├── routes.py              # Form routes & submission handling
│   ├── cleaning_generators.py # PDF/Excel generators
│   └── 📁 templates/
│       └── cleaning_form.html # Form template
│
├── 📁 templates/              # Shared HTML Templates
│   ├── dashboard.html          # Main user dashboard
│   ├── login.html              # Login page
│   ├── register.html           # Registration page
│   ├── admin_dashboard.html    # Admin dashboard
│   ├── workflow_history.html   # Workflow history page
│   ├── access_denied.html      # Access denied page
│   └── ...                    # Other templates
│
├── 📁 static/                 # Static Assets
│   ├── logo.png                # Application logo
│   ├── manifest.json           # PWA manifest
│   ├── service-worker.js       # PWA service worker
│   ├── photo_upload_queue.js   # Photo upload queue system
│   ├── photo_queue_ui.js       # Photo UI management
│   ├── form.js                 # Form utilities
│   ├── main.js                 # Main JavaScript
│   └── 📁 icons/              # PWA icons
│
├── 📁 common/                 # Common Utilities
│   ├── db_utils.py            # Database utilities
│   ├── retry_utils.py         # Retry logic with exponential backoff
│   ├── security.py            # Security utilities
│   ├── utils.py                # General utilities
│   ├── validation.py          # Validation helpers
│   ├── error_responses.py     # Standardized error responses
│   └── module_base.py         # Base module utilities
│
├── 📁 scripts/                # Utility Scripts
│   ├── create_admin.py        # Create admin user
│   ├── init_db.py             # Initialize database
│   └── ...                    # Other utility scripts
│
└── 📁 generated/              # Generated Reports (gitignored)
    ├── *.pdf
    ├── *.xlsx
    └── uploads/
```

### Module Organization Pattern

Each module (`module_hvac_mep`, `module_civil`, `module_cleaning`) follows a consistent structure:

```
module_name/
├── __init__.py           # Package initialization
├── routes.py             # Flask routes (GET form, POST submit)
├── *_generators.py       # Report generation functions
└── templates/
    └── *_form.html       # Form HTML template
```

**Benefits:**
- ✅ Clear separation of concerns
- ✅ Easy to add new modules
- ✅ Maintainable codebase
- ✅ Scalable architecture

---

## 🗄️ Database Schema

### Entity Relationship Diagram

```
┌─────────────┐
│    User     │
│─────────────│
│ id (PK)     │
│ username    │◄─────┐
│ email       │      │
│ password    │      │
│ role        │      │
│ designation │      │
│ access_*    │      │
└─────────────┘      │
       │              │
       │ 1            │ N
       │              │
       │              │
       ▼              │
┌─────────────┐      │
│ Submission  │      │
│─────────────│      │
│ id (PK)     │      │
│ submission_ │      │
│   id (UK)   │      │
│ user_id (FK)├──────┘
│ module_type │
│ site_name   │
│ visit_date  │
│ status      │
│ workflow_   │
│   status    │
│ supervisor_ │
│   id (FK)   │──────┐
│ manager_id  │      │
│   (FK)      │      │
│ form_data   │      │
│   (JSON)    │      │
└──────┬──────┘      │
       │              │
       │ 1            │ N
       │              │
       │              │
       ▼              │
┌─────────────┐      │
│    Job      │      │
│─────────────│      │
│ id (PK)     │      │
│ job_id (UK) │      │
│ submission_ │      │
│   id (FK)   │      │
│ status      │      │
│ progress    │      │
│ result_data │      │
│   (JSON)    │      │
└─────────────┘      │
                      │
                      │
┌─────────────┐      │
│    File     │      │
│─────────────│      │
│ id (PK)     │      │
│ file_id (UK)│      │
│ submission_ │      │
│   id (FK)   │      │
│ file_type   │      │
│ cloud_url   │      │
│ is_cloud    │      │
└─────────────┘      │
                      │
┌─────────────┐      │
│  AuditLog   │      │
│─────────────│      │
│ id (PK)     │      │
│ user_id (FK)├──────┘
│ action      │
│ resource_*  │
│ details     │
│   (JSON)    │
└─────────────┘
```

### Core Tables

#### 1. **users** Table

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(120),
    role VARCHAR(20) DEFAULT 'user',  -- 'admin', 'inspector', 'user'
    designation VARCHAR(20),           -- 'technician', 'supervisor', 'manager'
    is_active BOOLEAN DEFAULT TRUE,
    password_changed BOOLEAN DEFAULT FALSE,
    access_hvac BOOLEAN DEFAULT FALSE,
    access_civil BOOLEAN DEFAULT FALSE,
    access_cleaning BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

**Key Fields:**
- `role`: User role (admin has full access)
- `designation`: Workflow designation (technician, supervisor, manager)
- `access_*`: Module-level permissions

#### 2. **submissions** Table

```sql
CREATE TABLE submissions (
    id SERIAL PRIMARY KEY,
    submission_id VARCHAR(50) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id),
    module_type VARCHAR(20) NOT NULL,  -- 'hvac_mep', 'civil', 'cleaning'
    site_name VARCHAR(255),
    visit_date DATE,
    status VARCHAR(20) DEFAULT 'draft',  -- 'draft', 'submitted', 'processing', 'completed'
    workflow_status VARCHAR(30) DEFAULT 'submitted',  -- 'submitted', 'supervisor_reviewing', 'manager_reviewing', 'approved'
    supervisor_id INTEGER REFERENCES users(id),
    manager_id INTEGER REFERENCES users(id),
    supervisor_notified_at TIMESTAMP,
    supervisor_reviewed_at TIMESTAMP,
    manager_notified_at TIMESTAMP,
    manager_reviewed_at TIMESTAMP,
    form_data JSON NOT NULL,  -- All form fields as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_submissions_module_type ON submissions(module_type);
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_workflow_status ON submissions(workflow_status);
CREATE INDEX idx_submissions_user_created ON submissions(user_id, created_at);
```

**Key Fields:**
- `form_data`: JSON field containing all form fields
- `workflow_status`: Tracks review workflow state
- `supervisor_id`/`manager_id`: Assigned reviewers

#### 3. **jobs** Table

```sql
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) UNIQUE NOT NULL,
    submission_id INTEGER REFERENCES submissions(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    progress INTEGER DEFAULT 0,  -- 0-100
    result_data JSON,  -- {excel: "url", pdf: "url"}
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_submission_id ON jobs(submission_id);
```

**Key Fields:**
- `result_data`: JSON containing generated report URLs
- `progress`: 0-100 percentage for job completion

#### 4. **files** Table

```sql
CREATE TABLE files (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(50) UNIQUE NOT NULL,
    submission_id INTEGER REFERENCES submissions(id) ON DELETE CASCADE,
    file_type VARCHAR(20),  -- 'photo', 'signature', 'report_pdf', 'report_excel'
    filename VARCHAR(255),
    file_path VARCHAR(500),  -- Local path or NULL if cloud-only
    cloud_url VARCHAR(500),  -- Cloudinary URL
    is_cloud BOOLEAN DEFAULT TRUE,
    file_size INTEGER,  -- In bytes
    mime_type VARCHAR(100),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_files_submission_id ON files(submission_id);
CREATE INDEX idx_files_file_type ON files(file_type);
```

#### 5. **sessions** Table

```sql
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token_jti VARCHAR(100) UNIQUE NOT NULL,  -- JWT ID
    expires_at TIMESTAMP NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_token_jti ON sessions(token_jti);
CREATE INDEX idx_sessions_expires_revoked ON sessions(expires_at, is_revoked);
```

#### 6. **audit_logs** Table

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50) NOT NULL,  -- 'login', 'logout', 'create_submission', etc.
    resource_type VARCHAR(50),  -- 'submission', 'job', 'user'
    resource_id VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    details JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
```

---

## 🔄 Application Flows

### 1. User Authentication Flow

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │
       │ 1. POST /api/auth/login
       │    {username, password}
       ▼
┌─────────────────────────────────┐
│  Auth Route Handler              │
│  - Rate limit check (5/min)      │
│  - Find user by username         │
│  - Verify password (bcrypt)      │
│  - Check if user is active      │
└──────┬──────────────────────────┘
       │
       │ 2. Generate JWT Tokens
       │    - Access token (1 hour)
       │    - Refresh token (30 days)
       ▼
┌─────────────────────────────────┐
│  Create Session Record          │
│  - Store token_jti in DB        │
│  - Set expires_at               │
│  - Mark is_revoked = false      │
└──────┬──────────────────────────┘
       │
       │ 3. Update last_login
       ▼
┌─────────────────────────────────┐
│  Return Response                │
│  {                              │
│    access_token: "...",          │
│    refresh_token: "...",         │
│    user: {...}                  │
│  }                              │
└─────────────────────────────────┘
```

**Token Usage:**
- Every API request includes: `Authorization: Bearer <access_token>`
- JWT middleware validates token
- Checks if token is revoked (Session table)
- Extracts `user_id` from token claims

**Token Refresh:**
```
Access Token Expired?
    ↓
POST /api/auth/refresh
    {refresh_token: "..."}
    ↓
Validate refresh_token
    ↓
Check if revoked
    ↓
Generate new access_token
    ↓
Return {access_token: "..."}
```

### 2. Form Submission Flow

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: User Accesses Form                                  │
│ GET /hvac-mep/form (or /civil/form or /cleaning/form)       │
│                                                             │
│ 1. JWT Authentication Check                                │
│ 2. Check Module Access Permission                          │
│ 3. Render Form Template                                    │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: User Fills Form & Uploads Photos                  │
│                                                             │
│ Progressive Photo Upload:                                   │
│ POST /module/upload-photo                                   │
│   - Upload to Cloudinary                                    │
│   - Return photo URL                                        │
│   - Store in photo queue                                    │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: User Submits Form                                  │
│ POST /module/submit-with-urls                               │
│                                                             │
│ Payload:                                                    │
│ {                                                           │
│   project_name: "...",                                      │
│   date_of_visit: "...",                                     │
│   photo_urls: ["url1", "url2", ...],                       │
│   tech_signature: "data:image/png;base64,...",              │
│   ... (all form fields)                                     │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Backend Processing                                  │
│                                                             │
│ 1. Validate form data                                        │
│ 2. Upload signatures to Cloudinary                          │
│ 3. Create Submission record in DB                          │
│ 4. Create Job record in DB                                  │
│ 5. Submit background job for report generation             │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Background Job Processing                          │
│                                                             │
│ ThreadPoolExecutor.submit(process_job)                      │
│                                                             │
│ 1. Update job status: 'processing'                          │
│ 2. Get submission data from DB                             │
│ 3. Generate Excel report                                   │
│ 4. Generate PDF report                                     │
│ 5. Update job with result URLs                              │
│ 6. Update job status: 'completed'                           │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: Client Polls Job Status                            │
│                                                             │
│ GET /module/job-status/<job_id>                             │
│                                                             │
│ Response:                                                   │
│ {                                                           │
│   status: 'completed',                                      │
│   progress: 100,                                            │
│   result_data: {                                            │
│     excel: "https://...",                                   │
│     pdf: "https://..."                                       │
│   }                                                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 7: Display Download Links                              │
│                                                             │
│ - Show success message                                      │
│ - Display green download buttons                            │
│ - Links to Excel and PDF reports                            │
└─────────────────────────────────────────────────────────────┘
```

### 3. Workflow Review Flow

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Technician Submits Form                           │
│                                                             │
│ - Form submitted with workflow_status = 'submitted'        │
│ - Supervisor notified (if configured)                      │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Supervisor Reviews Submission                      │
│                                                             │
│ GET /module/form?edit=<submission_id>                      │
│                                                             │
│ - Load submission data                                       │
│ - Display all form fields (read-only)                       │
│ - Display photos                                            │
│ - Display technician signature                              │
│ - Show supervisor signature pad                             │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Supervisor Signs & Verifies                       │
│                                                             │
│ POST /module/submit-with-urls                               │
│                                                             │
│ Payload includes:                                           │
│ - supervisor_signature: "data:image/png;base64,..."         │
│ - supervisor_comments: "..."                                │
│ - supervisor_verified: true                                 │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Update Workflow Status                             │
│                                                             │
│ - workflow_status = 'supervisor_reviewed'                   │
│ - supervisor_reviewed_at = now()                            │
│ - Manager notified (if configured)                          │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Manager Reviews (Optional)                         │
│                                                             │
│ - Similar flow to supervisor review                         │
│ - workflow_status = 'manager_reviewed'                     │
│ - Final approval                                            │
└─────────────────────────────────────────────────────────────┘
```

### 4. File Upload Flow

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: User Selects Photos                                │
│                                                             │
│ - Photo upload queue system (JavaScript)                    │
│ - Multiple file selection                                   │
│ - Client-side validation (size, type)                      │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Progressive Upload                                 │
│                                                             │
│ For each photo:                                             │
│ POST /module/upload-photo                                    │
│   - Convert to base64 or FormData                           │
│   - Upload to Cloudinary with retry logic                   │
│   - Return secure URL                                        │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Store Photo URLs                                   │
│                                                             │
│ - Store URLs in photo queue (JavaScript)                    │
│ - Display thumbnails                                         │
│ - Allow removal before submission                           │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Include in Form Submission                         │
│                                                             │
│ - photo_urls: ["url1", "url2", ...]                        │
│ - Sent with form data                                       │
│ - Stored in submission.form_data                            │
└─────────────────────────────────────────────────────────────┘
```

**Cloudinary Upload with Retry:**
- Uses `tenacity` library for exponential backoff
- 3 retry attempts
- Wait: 2s, 4s, 8s (exponential)
- Falls back to local storage if Cloudinary fails

---

## 🌐 API Endpoints

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/register` | Register new user | No |
| POST | `/api/auth/login` | Login user | Yes (rate limited) |
| POST | `/api/auth/refresh` | Refresh access token | Refresh token |
| POST | `/api/auth/logout` | Logout user | Access token |
| POST | `/api/auth/change-password` | Change password | Access token |

### Admin Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/admin/users` | List all users | Admin |
| GET | `/api/admin/users/<id>` | Get user details | Admin |
| POST | `/api/admin/users` | Create new user | Admin |
| PUT | `/api/admin/users/<id>` | Update user | Admin |
| DELETE | `/api/admin/users/<id>` | Delete user | Admin |
| GET | `/api/admin/dashboard` | Admin dashboard | Admin |

### Module Form Endpoints

#### HVAC & MEP Module

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/hvac-mep/form` | Display form | Yes + module access |
| POST | `/hvac-mep/submit` | Submit form (legacy) | Yes |
| POST | `/hvac-mep/submit-with-urls` | Submit form with photos | Yes |
| POST | `/hvac-mep/upload-photo` | Upload photo | Yes |
| GET | `/hvac-mep/job-status/<job_id>` | Get job status | Yes |
| GET | `/hvac-mep/download/<job_id>/<file_type>` | Download report | Yes |

#### Civil Module

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/civil/form` | Display form | Yes + module access |
| POST | `/civil/submit` | Submit form | Yes |
| POST | `/civil/submit-with-urls` | Submit form with photos | Yes |
| GET | `/civil/job-status/<job_id>` | Get job status | Yes |

#### Cleaning Module

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/cleaning/form` | Display form | Yes + module access |
| POST | `/cleaning/submit` | Submit form | Yes |
| POST | `/cleaning/submit-with-urls` | Submit form with photos | Yes |
| POST | `/cleaning/upload-photo` | Upload photo | Yes |
| GET | `/cleaning/job-status/<job_id>` | Get job status | Yes |

### Workflow Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/workflow/dashboard` | Supervisor dashboard | Supervisor/Manager |
| GET | `/api/workflow/history` | Workflow history | Supervisor/Manager |
| GET | `/api/workflow/submissions/pending` | Pending submissions | Supervisor/Manager |
| GET | `/api/workflow/submissions/history` | History submissions | Supervisor/Manager |

---

## 🔧 Key Methods & Patterns

### 1. Database Utilities (`common/db_utils.py`)

#### `create_submission_db()`
```python
def create_submission_db(module_type, form_data, site_name=None, 
                        visit_date=None, user_id=None):
    """
    Create a new submission record in the database.
    
    - Generates unique submission_id
    - Creates Submission record
    - Notifies supervisor (if configured)
    - Returns Submission object
    """
```

#### `get_submission_db()`
```python
def get_submission_db(submission_id):
    """
    Retrieve submission data from database.
    
    - Returns form_data as dictionary
    - Handles JSON parsing
    - Returns None if not found
    """
```

#### `create_job_db()`
```python
def create_job_db(submission):
    """
    Create a background job for report generation.
    
    - Generates unique job_id
    - Links to submission
    - Sets initial status: 'pending'
    - Returns Job object
    """
```

### 2. File Upload Utilities (`common/utils.py`)

#### `save_uploaded_file_cloud()`
```python
def save_uploaded_file_cloud(file_storage, uploads_dir, folder="uploads"):
    """
    Upload file to Cloudinary with retry logic.
    
    Flow:
    1. Try Cloudinary upload (with retry)
    2. If fails, fallback to local storage
    3. Return dict with 'url', 'is_cloud', 'filename'
    """
```

#### `upload_base64_to_cloud()`
```python
def upload_base64_to_cloud(base64_string, folder="base64_uploads", 
                          prefix=None, uploads_dir=None):
    """
    Upload base64 image to Cloudinary.
    
    - Handles data URI format: "data:image/png;base64,..."
    - Uploads to Cloudinary with retry
    - Falls back to local storage
    """
```

#### `get_image_for_pdf()`
```python
def get_image_for_pdf(image_url, max_width=None, max_height=None):
    """
    Fetch image for PDF generation.
    
    - Handles HTTP/HTTPS URLs
    - Handles relative URLs
    - Handles Cloudinary URLs
    - Returns BytesIO stream
    """
```

### 3. Retry Utilities (`common/retry_utils.py`)

#### `upload_to_cloudinary_with_retry()`
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, 
                                   cloudinary.exceptions.Error))
)
def upload_to_cloudinary_with_retry(file_obj, **kwargs):
    """
    Upload to Cloudinary with exponential backoff retry.
    
    - 3 retry attempts
    - Exponential wait: 2s, 4s, 8s
    - Logs warnings before retry
    """
```

### 4. Report Generation Pattern

Each module has its own generator functions:

#### Excel Generation
```python
def create_excel_report(data, output_dir):
    """
    Generate Excel report from form data.
    
    - Uses openpyxl or XlsxWriter
    - Creates professional formatting
    - Includes images if applicable
    - Returns file path
    """
```

#### PDF Generation
```python
def create_pdf_report(data, output_dir):
    """
    Generate PDF report from form data.
    
    - Uses ReportLab
    - Professional PDF templates
    - Includes images, signatures
    - Returns file path
    """
```

### 5. Background Job Processing

#### Job Submission
```python
def process_job(sub_id, job_id, config, app):
    """
    Background worker for report generation.
    
    Flow:
    1. Get submission data from DB
    2. Generate Excel report
    3. Generate PDF report
    4. Update job with result URLs
    5. Mark job as completed
    """
```

#### Job Status Polling
```python
@route('/job-status/<job_id>')
def job_status(job_id):
    """
    Get current job status.
    
    Returns:
    {
        status: 'pending' | 'processing' | 'completed' | 'failed',
        progress: 0-100,
        result_data: {excel: "...", pdf: "..."},
        error_message: "..."
    }
    """
```

### 6. Authentication Patterns

#### JWT Required Decorator
```python
@jwt_required()
def protected_route():
    """
    Route requires valid JWT token.
    
    - Extracts user_id from token
    - Checks if token is revoked
    - Continues if valid
    """
```

#### Role-Based Access
```python
def require_role(role):
    """
    Decorator to require specific role.
    
    Usage:
    @require_role('admin')
    def admin_only_route():
        ...
    """
```

#### Module Access Check
```python
def check_module_access(user, module):
    """
    Check if user has access to module.
    
    - Admin has access to all
    - Others check access_* flags
    """
```

---

## 📤 File Upload & Storage

### Upload Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Client-Side Photo Queue System                               │
│                                                             │
│ - PhotoUploadQueue class (JavaScript)                        │
│ - Manages upload queue                                      │
│ - Retry failed uploads                                      │
│ - Progress tracking                                         │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ Upload Endpoint                                              │
│ POST /module/upload-photo                                    │
│                                                             │
│ 1. Receive file (FormData or base64)                        │
│ 2. Validate file (size, type)                                │
│ 3. Upload to Cloudinary (with retry)                        │
│ 4. Return secure URL                                        │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ Cloudinary Upload (with Retry)                               │
│                                                             │
│ - 3 retry attempts                                          │
│ - Exponential backoff (2s, 4s, 8s)                         │
│ - Fallback to local storage if fails                        │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ Storage Result                                               │
│                                                             │
│ {                                                           │
│   url: "https://res.cloudinary.com/...",                    │
│   is_cloud: true,                                           │
│   public_id: "..."                                          │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
```

### Storage Strategy

1. **Primary:** Cloudinary (cloud storage)
   - CDN delivery
   - Automatic image optimization
   - Secure URLs

2. **Fallback:** Local filesystem
   - If Cloudinary unavailable
   - Stored in `generated/uploads/`
   - Served via Flask static files

3. **Database:** File metadata
   - `files` table stores file records
   - Links to submissions
   - Tracks cloud vs local

### File Types Supported

- **Photos:** PNG, JPG, JPEG
- **Signatures:** Base64 data URIs (converted to PNG)
- **Reports:** PDF, XLSX (generated)

### Upload Limits

- **Max file size:** 10MB per file
- **Max total upload:** 100MB per request
- **Allowed extensions:** `png`, `jpg`, `jpeg`, `pdf`, `xlsx`, `csv`

---

## 📄 Report Generation

### Excel Report Generation

**Libraries Used:**
- `openpyxl` - Excel file manipulation
- `XlsxWriter` - Excel file creation
- `pandas` - Data processing

**Process:**
```
1. Extract form data from submission
2. Create workbook (openpyxl/XlsxWriter)
3. Apply professional formatting
   - Headers with company logo
   - Color-coded sections
   - Borders and alignment
4. Add data rows
5. Insert images (if applicable)
6. Save to generated/ directory
7. Return file path
```

**Features:**
- Professional styling
- Multi-sheet support (if needed)
- Image embedding
- Formula support

### PDF Report Generation

**Libraries Used:**
- `ReportLab` - PDF creation
- `Pillow` - Image processing

**Process:**
```
1. Extract form data from submission
2. Create PDF document (SimpleDocTemplate)
3. Build PDF content:
   - Header with logo
   - Project information table
   - Section headings
   - Form data tables
   - Photo grids
   - Signature sections
4. Apply professional styling
5. Save to generated/ directory
6. Return file path
```

**Features:**
- Professional layout
- Multi-page support
- Image embedding (with aspect ratio preservation)
- Signature display
- Table formatting

### Background Job Processing

**Job Lifecycle:**
```
pending → processing → completed
                    ↓
                 failed
```

**Progress Tracking:**
- 0%: Job created
- 10%: Excel generation started
- 40%: Excel completed
- 60%: PDF generation started
- 100%: Both reports completed

**Error Handling:**
- Job marked as 'failed' on error
- Error message stored in `error_message` field
- Client can retry by resubmitting form

---

## 🔐 Authentication & Authorization

### JWT Token Structure

**Access Token:**
```json
{
  "sub": "user_id",
  "iat": 1234567890,
  "exp": 1234571490,
  "type": "access",
  "jti": "unique_token_id"
}
```

**Refresh Token:**
```json
{
  "sub": "user_id",
  "iat": 1234567890,
  "exp": 1237897890,
  "type": "refresh",
  "jti": "unique_token_id"
}
```

### Token Storage

- **Access Token:** 1 hour expiry
- **Refresh Token:** 30 days expiry
- **Storage:** Database (`sessions` table)
- **Revocation:** `is_revoked` flag

### Role-Based Access Control

**Roles:**
- **admin:** Full access to all modules and admin functions
- **inspector:** Can submit forms in assigned modules
- **user:** Basic access (can be granted module access)

**Designations:**
- **technician:** Form submitter
- **supervisor:** Can review and approve submissions
- **manager:** Final approval authority

**Module Permissions:**
- `access_hvac`: HVAC & MEP module access
- `access_civil`: Civil Works module access
- `access_cleaning`: Cleaning module access

### Access Control Flow

```
Request → JWT Validation
    ↓
Extract user_id
    ↓
Load User from DB
    ↓
Check role/designation
    ↓
Check module access (if applicable)
    ↓
Allow/Deny request
```

---

## 🔄 Workflow Management

### Workflow States

```
submitted → supervisor_notified → supervisor_reviewing 
    → supervisor_reviewed → manager_notified 
    → manager_reviewing → approved
```

### Workflow Roles

**Technician:**
- Submits forms
- Cannot review other submissions

**Supervisor:**
- Reviews technician submissions
- Signs and verifies
- Can approve or request changes

**Manager:**
- Reviews supervisor-approved submissions
- Final approval authority
- Can override supervisor decisions

### Workflow Notifications

**Supervisor Notification:**
- Triggered when submission created
- Email notification (if configured)
- Dashboard notification

**Manager Notification:**
- Triggered when supervisor reviews
- Email notification (if configured)
- Dashboard notification

### Workflow History

**Tracking:**
- `supervisor_notified_at`: When supervisor was notified
- `supervisor_reviewed_at`: When supervisor reviewed
- `manager_notified_at`: When manager was notified
- `manager_reviewed_at`: When manager reviewed

**Audit Trail:**
- All workflow actions logged in `audit_logs` table
- Includes user, action, timestamp, IP address

---

## 🚀 Deployment & Configuration

### Environment Variables

**Required:**
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Security
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here

# Cloudinary (Optional but recommended)
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

**Optional:**
```bash
# Redis (for caching/queues)
REDIS_URL=redis://host:port

# Email (for notifications)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_USE_TLS=true

# Application
APP_BASE_URL=https://your-app.com
FLASK_ENV=production
DEBUG=false
```

### Database Setup

**Development (SQLite):**
```bash
# Automatic - creates injaaz.db on first run
```

**Production (PostgreSQL):**
```bash
# 1. Create database
createdb injaaz_db

# 2. Set DATABASE_URL environment variable
export DATABASE_URL=postgresql://user:pass@host:port/injaaz_db

# 3. Run migrations
flask db upgrade
```

### Deployment Steps

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd Injaaz-App
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements-prods.txt
   ```

3. **Set Environment Variables**
   ```bash
   # Create .env file or set in deployment platform
   cp .env.example .env
   # Edit .env with your values
   ```

4. **Initialize Database**
   ```bash
   python scripts/init_db.py
   python scripts/create_admin.py
   ```

5. **Run Application**
   ```bash
   # Development
   python Injaaz.py
   
   # Production (with Gunicorn)
   gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
   ```

### Render.com Deployment

**render.yaml:**
```yaml
services:
  - type: web
    name: injaaz-app
    env: python
    buildCommand: pip install -r requirements-prods.txt
    startCommand: gunicorn -w 4 -b 0.0.0.0:$PORT wsgi:app
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: SECRET_KEY
        generateValue: true
      - key: JWT_SECRET_KEY
        generateValue: true
```

### Configuration Files

**config.py:**
- Loads environment variables
- Sets default values
- Configures Flask app
- Database connection settings
- JWT settings
- File upload limits

**Key Settings:**
- `MAX_UPLOAD_FILESIZE`: 10MB
- `MAX_CONTENT_LENGTH`: 100MB
- `JWT_ACCESS_TOKEN_EXPIRES`: 3600 seconds (1 hour)
- `JWT_REFRESH_TOKEN_EXPIRES`: 2592000 seconds (30 days)

---

## 📊 Diagrams

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │  Web     │  │  Mobile  │  │   PWA    │                │
│  │ Browser  │  │   Web    │  │   App    │                │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                │
└───────┼──────────────┼──────────────┼───────────────────────┘
        │              │              │
        └──────────────┼──────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              FLASK APPLICATION SERVER                        │
│  ┌──────────────────────────────────────────────────────┐ │
│  │              Injaaz.py (App Factory)                  │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │ │
│  │  │  Auth    │  │  Admin   │  │  Module  │          │ │
│  │  │ Blueprint│  │ Blueprint│  │ Blueprint│          │ │
│  │  └──────────┘  └──────────┘  └──────────┘          │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │ │
│  │  │Workflow  │  │ Services │  │Background│          │ │
│  │  │Blueprint │  │  Layer   │  │   Jobs   │          │ │
│  │  └──────────┘  └──────────┘  └──────────┘          │ │
│  └──────────────────────────────────────────────────────┘ │
└───────┬──────────────┬──────────────┬──────────────┬────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│PostgreSQL│  │Cloudinary│  │   Redis   │  │  Local    │
│ Database │  │   CDN    │  │  (Cache)  │  │  Storage  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### Data Flow Diagram

```
User Input → Form Validation → Database Storage
    ↓
Photo Upload → Cloudinary → URL Storage
    ↓
Form Submission → Background Job Queue
    ↓
Report Generation → Excel + PDF Creation
    ↓
File Storage → Download URLs
    ↓
Client Display → Download Links
```

### Module Interaction Diagram

```
┌──────────────┐
│   User       │
└──────┬───────┘
       │
       │ 1. Access Form
       ▼
┌──────────────┐
│  Module      │
│  Routes      │
└──────┬───────┘
       │
       │ 2. Check Access
       ▼
┌──────────────┐
│  Database    │
│  (User)      │
└──────┬───────┘
       │
       │ 3. Render Form
       ▼
┌──────────────┐
│  Template    │
│  (HTML)      │
└──────┬───────┘
       │
       │ 4. Submit Form
       ▼
┌──────────────┐
│  Module      │
│  Routes      │
└──────┬───────┘
       │
       │ 5. Validate & Store
       ▼
┌──────────────┐
│  Database    │
│  (Submission)│
└──────┬───────┘
       │
       │ 6. Create Job
       ▼
┌──────────────┐
│ Background   │
│  Worker      │
└──────┬───────┘
       │
       │ 7. Generate Reports
       ▼
┌──────────────┐
│  Generators   │
│  (Excel/PDF) │
└──────┬───────┘
       │
       │ 8. Store Results
       ▼
┌──────────────┐
│  Database    │
│  (Job)       │
└──────────────┘
```

---

## 📝 Summary

This documentation provides a comprehensive overview of the Injaaz application, covering:

✅ **Technology Stack** - All libraries and frameworks used  
✅ **Architecture** - High-level system design  
✅ **Codebase Structure** - Directory organization  
✅ **Database Schema** - Complete data model  
✅ **Application Flows** - Step-by-step process flows  
✅ **API Endpoints** - Complete endpoint reference  
✅ **Key Methods** - Important functions and patterns  
✅ **File Upload** - Upload and storage mechanisms  
✅ **Report Generation** - Excel and PDF creation  
✅ **Authentication** - JWT and access control  
✅ **Workflow** - Review and approval process  
✅ **Deployment** - Configuration and deployment guide  

This document serves as a complete reference for understanding, maintaining, and extending the Injaaz application.

---

**Document Version:** 1.0  
**Last Updated:** 2024-12-30  
**Maintained By:** Injaaz Development Team
