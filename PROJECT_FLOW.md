# 📖 Injaaz Application - Complete Project Flow Documentation

**Last Updated:** 2024-12-30  
**Purpose:** Comprehensive guide to understand the entire application flow

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture Overview](#architecture-overview)
3. [User Authentication Flow](#user-authentication-flow)
4. [Form Submission Flow](#form-submission-flow)
5. [Report Generation Flow](#report-generation-flow)
6. [File Upload Flow](#file-upload-flow)
7. [Admin Operations Flow](#admin-operations-flow)
8. [Database Structure](#database-structure)
9. [API Endpoints Overview](#api-endpoints-overview)
10. [Background Job Processing](#background-job-processing)

---

## 🎯 Project Overview

**Injaaz** is a Flask-based web application for managing site visit reports across three modules:
- **HVAC & MEP** (Heating, Ventilation, Air Conditioning & Mechanical, Electrical, Plumbing)
- **Civil Works**
- **Cleaning**

### Key Features
- User authentication with JWT tokens
- Role-based access control (Admin, Inspector, User)
- Module-level permissions
- Form submissions with photo uploads
- Background report generation (Excel & PDF)
- Cloud storage integration (Cloudinary)
- Admin dashboard for user management

---

## 🏗️ Architecture Overview

### High-Level Architecture

```
┌─────────────┐
│   Client    │ (Web Browser / Mobile)
│  (Frontend) │
└──────┬──────┘
       │ HTTPS
       │
┌──────▼─────────────────────────────────────────┐
│         Flask Application (Injaaz.py)          │
│  ┌──────────────────────────────────────────┐  │
│  │  Routes & Blueprints                     │  │
│  │  - Auth Routes (/api/auth/*)             │  │
│  │  - Admin Routes (/api/admin/*)           │  │
│  │  - Module Routes (/hvac-mep, /civil, etc)│  │
│  └──────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────┐  │
│  │  Business Logic                          │  │
│  │  - Authentication & Authorization        │  │
│  │  - Form Validation                       │  │
│  │  - Report Generation (Excel/PDF)         │  │
│  └──────────────────────────────────────────┘  │
└──────┬───────────────────┬──────────────────┬──┘
       │                   │                  │
       ▼                   ▼                  ▼
┌──────────┐      ┌──────────────┐    ┌──────────┐
│PostgreSQL│      │  Cloudinary  │    │  Redis   │
│ Database │      │  (File Store)│    │ (Cache/  │
│          │      │              │    │  Queue)  │
└──────────┘      └──────────────┘    └──────────┘
```

### Technology Stack

- **Backend:** Python 3.8+, Flask 2.2.5
- **Database:** PostgreSQL (production), SQLite (development)
- **Authentication:** Flask-JWT-Extended
- **File Storage:** Cloudinary
- **Caching/Queue:** Redis (optional)
- **Background Jobs:** ThreadPoolExecutor (can migrate to Redis/RQ)
- **Report Generation:** ReportLab (PDF), openpyxl/XlsxWriter (Excel)

---

## 🔐 User Authentication Flow

### 1. User Registration

```
User → POST /api/auth/register
     ↓
Validation (username, email, password)
     ↓
Check if username/email exists
     ↓
Hash password (bcrypt)
     ↓
Create User record in database
     ↓
Return: {success: true, user: {...}}
```

### 2. User Login

```
User → POST /api/auth/login
     ↓
Rate Limiting Check (5 req/min)
     ↓
Find User by username
     ↓
Verify password (bcrypt.check_password_hash)
     ↓
Check if user is active
     ↓
Generate JWT Access Token (1 hour expiry)
     ↓
Generate JWT Refresh Token (30 days expiry)
     ↓
Create Session record in database
     ↓
Update last_login timestamp
     ↓
Return: {
  access_token: "...",
  refresh_token: "...",
  user: {...}
}
```

### 3. Token Usage

```
Every API Request:
Client → Request with Header: Authorization: Bearer <access_token>
      ↓
JWT Middleware validates token
      ↓
Check if token is revoked (Session table)
      ↓
Extract user_id from token
      ↓
Continue to route handler
```

### 4. Token Refresh

```
Access Token Expired?
     ↓
POST /api/auth/refresh (with refresh_token)
     ↓
Validate refresh_token
     ↓
Check if refresh_token is revoked
     ↓
Generate new access_token
     ↓
Return: {access_token: "..."}
```

### 5. Logout

```
User → POST /api/auth/logout
     ↓
Get JWT token from request
     ↓
Mark Session as revoked (is_revoked = true)
     ↓
Return: {message: "Logged out successfully"}
```

---

## 📝 Form Submission Flow

### Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Accesses Form                                       │
│    GET /hvac-mep/ (or /civil/ or /cleaning/)                │
│    ↓                                                         │
│    JWT Authentication Check                                 │
│    ↓                                                         │
│    Check Module Access Permission                           │
│    ↓                                                         │
│    Render Form Template                                     │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. User Fills Form & Uploads Photos                        │
│    ↓                                                         │
│    Progressive Photo Upload                                 │
│    POST /hvac-mep/upload-photo                              │
│    ↓                                                         │
│    Upload to Cloudinary                                     │
│    ↓                                                         │
│    Return Cloudinary URL                                    │
│    ↓                                                         │
│    Store URL in form data                                   │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. User Submits Form                                        │
│    POST /hvac-mep/submit                                    │
│    ↓                                                         │
│    Validate Form Data                                       │
│    ↓                                                         │
│    Create Submission Record (Database)                      │
│    - submission_id: "sub_abc123"                            │
│    - user_id, module_type, form_data (JSON)                 │
│    - status: "submitted"                                    │
│    ↓                                                         │
│    Create Job Record (Database)                             │
│    - job_id: "job_def456"                                   │
│    - submission_id, status: "pending"                       │
│    ↓                                                         │
│    Queue Background Task (ThreadPoolExecutor)               │
│    ↓                                                         │
│    Return: {job_id: "job_def456", status: "pending"}       │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Frontend Polls Job Status                                │
│    GET /hvac-mep/job-status/job_def456                      │
│    ↓                                                         │
│    Check Job Status in Database                             │
│    ↓                                                         │
│    Return: {                                                │
│      status: "processing",                                  │
│      progress: 45,                                          │
│      results: null                                          │
│    }                                                         │
└─────────────────────────────────────────────────────────────┘
```

### Detailed Step-by-Step

#### Step 1: Form Access

**Route:** `GET /hvac-mep/` (or `/civil/` or `/cleaning/`)

1. User requests form page
2. Middleware checks JWT token in cookie/header
3. Extract user_id from token
4. Query User from database
5. Check `user.is_active`
6. Check `user.has_module_access('hvac_mep')`
7. If authorized, render form template
8. Frontend fetches dropdown data: `GET /hvac-mep/dropdowns` (cached)

#### Step 2: Photo Upload (Progressive)

**Route:** `POST /hvac-mep/upload-photo`

```
User selects photo
     ↓
Frontend converts to base64 or File object
     ↓
POST request to /upload-photo endpoint
     ↓
Backend receives file
     ↓
Validate file (size, type)
     ↓
Upload to Cloudinary
     ↓
Return: {url: "https://res.cloudinary.com/.../image.jpg"}
     ↓
Frontend stores URL in form data
     ↓
UI updates with preview
```

#### Step 3: Form Submission

**Route:** `POST /hvac-mep/submit`

**Request Body:**
```json
{
  "site_name": "Site ABC",
  "visit_date": "2024-12-30",
  "form_data": {
    "field1": "value1",
    "photos": [
      {"url": "https://cloudinary.com/photo1.jpg"},
      {"url": "https://cloudinary.com/photo2.jpg"}
    ],
    "signature": "data:image/png;base64,..."
  }
}
```

**Process:**
1. Validate required fields
2. Create Submission record:
   ```python
   Submission(
     submission_id="sub_abc123",
     user_id=user.id,
     module_type="hvac_mep",
     site_name="Site ABC",
     visit_date="2024-12-30",
     form_data={...},  # JSON
     status="submitted"
   )
   ```
3. Create Job record:
   ```python
   Job(
     job_id="job_def456",
     submission_id=submission.id,
     status="pending",
     progress=0
   )
   ```
4. Queue background task:
   ```python
   executor.submit(process_job, sub_id, job_id, config, app)
   ```
5. Return response:
   ```json
   {
     "job_id": "job_def456",
     "status": "pending",
     "message": "Submission received, processing..."
   }
   ```

#### Step 4: Job Status Polling

**Route:** `GET /hvac-mep/job-status/<job_id>`

**Frontend Logic:**
```javascript
// Poll every 2 seconds
setInterval(() => {
  fetch(`/hvac-mep/job-status/${jobId}`)
    .then(response => response.json())
    .then(data => {
      if (data.status === 'completed') {
        // Show download links
        showResults(data.results);
      } else if (data.status === 'failed') {
        // Show error
        showError(data.error_message);
      } else {
        // Update progress bar
        updateProgress(data.progress);
      }
    });
}, 2000);
```

---

## 📊 Report Generation Flow

### Background Job Processing

```
ThreadPoolExecutor picks up job
     ↓
process_job(sub_id, job_id, config, app)
     ↓
┌─────────────────────────────────────────┐
│ 1. Setup (10% progress)                 │
│    - Get app context                    │
│    - Ensure GENERATED_DIR exists        │
│    - Update job status: "processing"    │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 2. Load Submission Data (10% progress)  │
│    - Query Submission by sub_id         │
│    - Extract form_data JSON             │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 3. Generate Excel Report (30% progress) │
│    - Call create_excel_report()         │
│    - Creates Excel file in GENERATED_DIR│
│    - Update progress: 30%               │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 4. Upload Excel to Cloudinary (45%)     │
│    - Upload file to Cloudinary          │
│    - Get cloud URL                      │
│    - Delete local file (production)     │
│    - Update progress: 45%               │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 5. Generate PDF Report (60% progress)   │
│    - Call create_pdf_report()           │
│    - Downloads photos from Cloudinary   │
│    - Creates PDF with images            │
│    - Update progress: 60%               │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 6. Upload PDF to Cloudinary (75%)       │
│    - Upload file to Cloudinary          │
│    - Get cloud URL                      │
│    - Delete local file (production)     │
│    - Update progress: 75%               │
└─────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────┐
│ 7. Complete Job (100% progress)         │
│    - Update Job record:                 │
│      status: "completed"                │
│      progress: 100                      │
│      result_data: {                     │
│        excel: "https://...",            │
│        pdf: "https://...",              │
│        excel_filename: "...",           │
│        pdf_filename: "..."              │
│      }                                   │
│    - completed_at: now()                │
└─────────────────────────────────────────┘
     ↓
Frontend receives completion status
     ↓
Display download links
```

### Report Generation Functions

**Excel Report:**
- Location: `module_hvac_mep/hvac_generators.py::create_excel_report()`
- Uses: `openpyxl` or `XlsxWriter`
- Output: `.xlsx` file

**PDF Report:**
- Location: `module_hvac_mep/hvac_generators.py::create_pdf_report()`
- Uses: `ReportLab`
- Features:
  - Fetches photos from Cloudinary URLs
  - Embeds images in PDF
  - Structured layout with tables
  - Styling and formatting

---

## 📤 File Upload Flow

### Photo Upload (Progressive)

```
┌─────────────────────────────────────────────┐
│ User selects multiple photos                │
│ (e.g., 10 photos at once)                   │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Frontend: PhotoUploadQueue                  │
│ - Queues all photos                         │
│ - Processes one at a time                   │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ For each photo:                             │
│ POST /module/upload-photo                   │
│ Content-Type: multipart/form-data           │
│ Body: {file: File object}                   │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Backend Processing:                         │
│ 1. Validate file (size ≤ 10MB, type)        │
│ 2. Generate unique filename (UUID)          │
│ 3. Upload to Cloudinary                     │
│    - Resource type: "image"                 │
│    - Folder: "injaaz/uploads"               │
│    - Transformation: resize if needed       │
│ 4. Return Cloudinary URL                    │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Frontend: PhotoQueueUI                      │
│ - Updates UI with uploaded photo            │
│ - Shows progress indicator                  │
│ - Displays preview with cloud URL           │
│ - Marks as "completed"                      │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ All photos uploaded?                        │
│ → Store URLs in form data                   │
│ → Enable submit button                      │
└─────────────────────────────────────────────┘
```

### Signature Upload

Similar to photo upload, but:
- Single file (not queued)
- Base64 data URL from canvas
- Smaller size limit
- Stored in form data as data URL or cloud URL

---

## 👨‍💼 Admin Operations Flow

### User Management Flow

```
┌─────────────────────────────────────────────┐
│ Admin accesses dashboard                    │
│ GET /admin/dashboard                        │
│ (JWT + admin role required)                 │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ List All Users                              │
│ GET /api/admin/users                        │
│ ↓                                           │
│ Query all users (with eager loading)        │
│ ↓                                           │
│ Return: [{user1}, {user2}, ...]            │
└───────────────┬─────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Admin Actions:                              │
│                                              │
│ 1. Create User                              │
│    POST /api/admin/users                    │
│    → Create user with role/permissions      │
│                                              │
│ 2. Update User                              │
│    PUT /api/admin/users/<id>                │
│    → Update email, username, role, etc.     │
│                                              │
│ 3. Reset Password                           │
│    POST /api/admin/users/<id>/reset-password│
│    → Generate temp password                 │
│    → Email to user                          │
│                                              │
│ 4. Toggle Active Status                     │
│    POST /api/admin/users/<id>/toggle-active │
│    → Activate/deactivate user               │
│                                              │
│ 5. Update Module Access                     │
│    POST /api/admin/users/<id>/update-access │
│    → Set access_hvac, access_civil, etc.    │
└─────────────────────────────────────────────┘
```

### Access Control

**Roles:**
- **Admin:** Full access to all modules and admin dashboard
- **Inspector:** Can submit forms in assigned modules
- **User:** Basic access (can be granted module access)

**Module Permissions:**
- `access_hvac`: Access to HVAC & MEP module
- `access_civil`: Access to Civil Works module
- `access_cleaning`: Access to Cleaning module

**Admin users automatically have access to all modules.**

---

## 🗄️ Database Structure

### Core Tables

#### Users Table
```sql
users
├── id (PK)
├── username (unique, indexed)
├── email (unique, indexed)
├── password_hash
├── full_name
├── role (admin, inspector, user)
├── is_active
├── access_hvac
├── access_civil
├── access_cleaning
├── created_at
└── last_login
```

#### Submissions Table
```sql
submissions
├── id (PK)
├── submission_id (unique, indexed)
├── user_id (FK → users.id)
├── module_type (hvac_mep, civil, cleaning) (indexed)
├── site_name
├── visit_date
├── status (draft, submitted, processing, completed) (indexed)
├── form_data (JSON)
├── created_at (indexed)
└── updated_at

Indexes:
- idx_submission_module_status (module_type, status)
- idx_submission_user_created (user_id, created_at)
```

#### Jobs Table
```sql
jobs
├── id (PK)
├── job_id (unique, indexed)
├── submission_id (FK → submissions.id, CASCADE DELETE)
├── status (pending, processing, completed, failed) (indexed)
├── progress (0-100)
├── result_data (JSON) -- {excel: "...", pdf: "..."}
├── error_message
├── started_at
├── completed_at
└── created_at
```

#### Sessions Table
```sql
sessions
├── id (PK)
├── user_id (FK → users.id, CASCADE DELETE) (indexed)
├── token_jti (unique, indexed) -- JWT ID
├── expires_at (indexed)
├── is_revoked (indexed)
└── created_at

Indexes:
- idx_session_expires_revoked (expires_at, is_revoked)
```

#### Files Table
```sql
files
├── id (PK)
├── submission_id (FK → submissions.id, CASCADE DELETE)
├── file_type (photo, signature, document)
├── cloud_url
├── filename
├── file_size
└── uploaded_at
```

#### Audit Logs Table
```sql
audit_logs
├── id (PK)
├── user_id (FK → users.id)
├── action (login, logout, create_submission, etc.) (indexed)
├── resource_type (submission, job, user)
├── resource_id
├── ip_address
├── user_agent
├── details (JSON)
└── created_at (indexed)
```

### Relationships

```
User (1) ──── (N) Submission
  │                │
  │                │
  │                ├── (N) Job
  │                │
  │                └── (N) File
  │
  ├── (N) Session
  │
  └── (N) AuditLog
```

---

## 🌐 API Endpoints Overview

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/register` | Register new user | No |
| POST | `/api/auth/login` | Login user | No |
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
| POST | `/api/admin/users/<id>/reset-password` | Reset password | Admin |
| POST | `/api/admin/users/<id>/toggle-active` | Toggle active status | Admin |
| POST | `/api/admin/users/<id>/update-access` | Update module access | Admin |

### Module Endpoints (HVAC/Civil/Cleaning)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/<module>/` | Form page | Access token |
| GET | `/<module>/dropdowns` | Get dropdown data (cached) | Access token |
| POST | `/<module>/upload-photo` | Upload photo | Access token |
| POST | `/<module>/submit` | Submit form | Access token |
| GET | `/<module>/job-status/<job_id>` | Get job status | Access token |

### System Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/health` | Health check | No |
| POST | `/admin/cleanup-sessions` | Cleanup expired sessions | API Key |

---

## ⚙️ Background Job Processing

### Current Implementation

**ThreadPoolExecutor:**
- Configured with 2 worker threads
- Stored in `app.config['EXECUTOR']`
- Jobs run in background threads

### Job Lifecycle

```
1. PENDING
   ↓
   (Queued in ThreadPoolExecutor)
   ↓
2. PROCESSING
   ↓
   (Generating reports)
   ↓
3. COMPLETED or FAILED
```

### Job Status Updates

- Progress: 0 → 10 → 30 → 45 → 60 → 75 → 100
- Status: pending → processing → completed/failed
- Database updated after each major step

### Future Migration

**Recommended:** Migrate to Redis/RQ or Celery
- Persistence across server restarts
- Better job tracking
- Distributed processing
- Job retry mechanisms

---

## 🔄 Complete Request Flow Example

### Example: User Submits HVAC Form

```
1. User logs in
   POST /api/auth/login
   → Returns: {access_token: "...", refresh_token: "..."}
   
2. User accesses form
   GET /hvac-mep/
   → JWT validation
   → Check module access
   → Render form
   
3. User uploads 5 photos
   POST /hvac-mep/upload-photo (5 times)
   → Upload to Cloudinary
   → Return URLs
   → UI updates
   
4. User fills form and submits
   POST /hvac-mep/submit
   → Validate data
   → Create Submission record
   → Create Job record
   → Queue background task
   → Return: {job_id: "job_123"}
   
5. Frontend polls job status
   GET /hvac-mep/job-status/job_123 (every 2 seconds)
   → Check Job.status in database
   → Return: {status: "processing", progress: 45}
   
6. Background job completes
   → Excel generated → Uploaded to Cloudinary
   → PDF generated → Uploaded to Cloudinary
   → Job.status = "completed"
   → Job.result_data = {excel: "...", pdf: "..."}
   
7. Frontend receives completion
   → Stop polling
   → Display download links
   → User can download reports
```

---

## 🔒 Security Flow

### Authentication & Authorization

1. **JWT Token Validation:**
   - Every protected route checks JWT token
   - Token contains: `user_id`, `role`, `exp`, `jti`
   - Middleware validates token signature and expiry

2. **Role-Based Access:**
   - Admin routes: `@admin_required` decorator
   - Module routes: Check `user.has_module_access()`

3. **Session Management:**
   - Every login creates a Session record
   - Logout marks session as revoked
   - Token validation checks if session is revoked

4. **Rate Limiting:**
   - Login/Register: 5 requests per minute
   - Uses Flask-Limiter (Redis-backed if available)

---

## 📦 File Storage Strategy

### Development vs Production

**Development:**
- Files can be stored locally in `generated/` directory
- Local file serving enabled
- SQLite database allowed

**Production:**
- **All files must be in Cloudinary** (CLOUD_ONLY_MODE)
- Local file serving disabled (404 for `/generated/<filename>`)
- PostgreSQL required
- Reports uploaded directly to Cloudinary
- No local file dependencies

### File Types

1. **Photos:** Uploaded to Cloudinary → URLs stored in form_data
2. **Signatures:** Uploaded to Cloudinary or stored as base64
3. **Reports:** Generated locally → Uploaded to Cloudinary → Local file deleted
4. **Other Documents:** Uploaded to Cloudinary

---

## 🎯 Key Design Patterns

### 1. Blueprint Pattern
- Each module is a Flask Blueprint
- Routes organized by feature
- Easy to add new modules

### 2. Factory Pattern
- `create_app()` function creates Flask app
- Allows different configurations
- Supports testing

### 3. Background Jobs
- Asynchronous report generation
- Non-blocking user experience
- Status polling for updates

### 4. Progressive Upload
- Photos uploaded individually
- Immediate feedback
- Better error handling

### 5. Caching Strategy
- Dropdown data cached in Redis (1 hour TTL)
- Reduces database queries
- Improves response time

---

## 📚 Key Files & Their Roles

### Application Entry Point
- `Injaaz.py` - Main Flask application factory
- `wsgi.py` - WSGI entry point for production

### Configuration
- `config.py` - Environment-based configuration
- `.env` - Environment variables (not in git)

### Models
- `app/models.py` - SQLAlchemy database models

### Routes
- `app/auth/routes.py` - Authentication routes
- `app/admin/routes.py` - Admin routes
- `module_hvac_mep/routes.py` - HVAC module routes
- `module_civil/routes.py` - Civil module routes
- `module_cleaning/routes.py` - Cleaning module routes

### Business Logic
- `common/module_base.py` - Shared module logic
- `common/db_utils.py` - Database utilities
- `common/error_responses.py` - Standardized error responses
- `common/cache.py` - Redis caching utilities
- `common/email_service.py` - Email sending service

### Report Generation
- `module_hvac_mep/hvac_generators.py` - HVAC Excel/PDF generators
- `module_civil/civil_generators.py` - Civil Excel/PDF generators
- `module_cleaning/cleaning_generators.py` - Cleaning Excel/PDF generators

### Services
- `app/services/cloudinary_service.py` - Cloudinary integration
- `app/services/pdf_service.py` - PDF generation utilities
- `app/services/excel_service.py` - Excel generation utilities

---

## 🚀 Deployment Flow

### Render Deployment

1. **Git Push:**
   ```
   git push origin main
   ```

2. **Render Build:**
   - Detects `requirements-prods.txt`
   - Installs Python dependencies
   - Runs application with Gunicorn

3. **Application Startup:**
   - `create_app()` is called
   - Database connection initialized
   - Tables created if needed
   - Default admin user created (if none exists)
   - Configuration validated
   - Blueprints registered

4. **Health Check:**
   - Render monitors `/health` endpoint
   - Database connectivity checked

---

## 🔍 Troubleshooting Flow

### Common Issues

1. **Job Stuck in Processing:**
   - Check application logs
   - Verify Cloudinary credentials
   - Check database connection
   - Manual job status check

2. **Photo Upload Fails:**
   - Check Cloudinary credentials
   - Verify file size limits
   - Check network connectivity

3. **Report Generation Fails:**
   - Check generator imports
   - Verify form_data structure
   - Check Cloudinary upload permissions

4. **Authentication Issues:**
   - Verify JWT secret key
   - Check token expiry
   - Verify session not revoked

---

## 📖 Additional Resources

- **README.md** - Setup and configuration guide
- **CODEBASE_SUGGESTIONS.md** - Code quality recommendations
- **MONITORING_SETUP.md** - Monitoring and error tracking setup
- **CLOUD_ONLY_SETUP.md** - Cloud-only deployment guide
- **ENV_VARIABLES_CHECK.md** - Environment variable verification

---

**Document Version:** 1.0  
**Last Updated:** 2024-12-30  
**Maintained By:** Development Team

