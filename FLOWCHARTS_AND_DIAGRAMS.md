# 📊 Injaaz Application - Flowcharts & Diagrams

**Version:** 1.0  
**Last Updated:** 2024-12-30  
**Purpose:** Visual flowcharts and diagrams for understanding application processes

---

## 📋 Table of Contents

1. [User Authentication Flow](#user-authentication-flow)
2. [Form Submission Flow](#form-submission-flow)
3. [File Upload Flow](#file-upload-flow)
4. [Report Generation Flow](#report-generation-flow)
5. [Workflow Review Process](#workflow-review-process)
6. [Database Relationships](#database-relationships)
7. [System Architecture](#system-architecture)
8. [Module Interaction Flow](#module-interaction-flow)

---

## 🔐 User Authentication Flow

### Complete Authentication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER AUTHENTICATION FLOW                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   User      │
│  (Client)   │
└──────┬──────┘
       │
       │ 1. POST /api/auth/login
       │    {username, password}
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Auth Route Handler                                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Rate Limit Check (5 requests/minute)                  │  │
│  │ 2. Find User by username                                  │  │
│  │ 3. Verify password (bcrypt.check_password_hash)            │  │
│  │ 4. Check if user is_active                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ 2. Generate JWT Tokens
       │    - Access Token (1 hour expiry)
       │    - Refresh Token (30 days expiry)
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Create Session Record                                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ - Store token_jti in sessions table                      │  │
│  │ - Set expires_at timestamp                                │  │
│  │ - Mark is_revoked = false                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ 3. Update last_login timestamp
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Return Response                                                │
│  {                                                              │
│    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",  │
│    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",  │
│    "user": {                                                    │
│      "id": 1,                                                   │
│      "username": "john_doe",                                    │
│      "role": "inspector",                                       │
│      "designation": "technician",                               │
│      "access_hvac": true,                                       │
│      "access_civil": true,                                      │
│      "access_cleaning": false                                   │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### Token Usage Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    TOKEN USAGE FLOW                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   Client    │
│  Request    │
└──────┬──────┘
       │
       │ Request Header:
       │ Authorization: Bearer <access_token>
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  JWT Middleware                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Extract token from Authorization header                 │  │
│  │ 2. Decode and validate token signature                     │  │
│  │ 3. Check token expiration                                  │  │
│  │ 4. Extract token_jti (JWT ID)                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Check if token is revoked
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Database Query                                                 │
│  SELECT * FROM sessions                                        │
│  WHERE token_jti = ? AND is_revoked = false                    │
│  AND expires_at > NOW()                                        │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Token valid?
       │ Yes → Extract user_id from token
       │ No → Return 401 Unauthorized
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Continue to Route Handler                                      │
│  - user_id available via get_jwt_identity()                    │
│  - User object available via User.query.get(user_id)          │
└─────────────────────────────────────────────────────────────────┘
```

### Token Refresh Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    TOKEN REFRESH FLOW                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       │ Access Token Expired?
       │ (401 Unauthorized)
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/auth/refresh                                         │
│  {                                                              │
│    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  │
│  }                                                              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ 1. Validate refresh_token
       │ 2. Check if refresh_token is revoked
       │ 3. Check if refresh_token is expired
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Generate New Access Token                                      │
│  - Same user_id                                                │
│  - New expiration (1 hour from now)                            │
│  - New token_jti                                               │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Create new session record
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Return Response                                                │
│  {                                                              │
│    "access_token": "new_token_here..."                         │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📝 Form Submission Flow

### Complete Form Submission Process

```
┌─────────────────────────────────────────────────────────────────┐
│              COMPLETE FORM SUBMISSION FLOW                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: User Accesses Form                                     │
│ GET /hvac-mep/form (or /civil/form or /cleaning/form)          │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ 1. JWT Authentication Check
       │ 2. Check Module Access Permission
       │ 3. Render Form Template
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: User Fills Form & Uploads Photos                      │
│                                                                 │
│ ┌──────────────────────────────────────────────────────────┐  │
│ │ Progressive Photo Upload:                                 │  │
│ │ POST /module/upload-photo                                  │  │
│ │   - Upload to Cloudinary                                   │  │
│ │   - Return photo URL                                       │  │
│ │   - Store in photo queue (JavaScript)                      │  │
│ └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ User clicks "Submit & Generate Reports"
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Form Submission                                        │
│ POST /module/submit-with-urls                                   │
│                                                                 │
│ Payload:                                                       │
│ {                                                              │
│   "project_name": "Building A",                                │
│   "date_of_visit": "2024-12-30",                              │
│   "photo_urls": [                                              │
│     "https://res.cloudinary.com/.../photo1.jpg",              │
│     "https://res.cloudinary.com/.../photo2.jpg"               │
│   ],                                                           │
│   "tech_signature": "data:image/png;base64,iVBORw0KGgo...",   │
│   "technician_name": "John Doe",                              │
│   ... (all other form fields)                                  │
│ }                                                              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ 1. Validate form data
       │ 2. Upload signatures to Cloudinary
       │ 3. Create Submission record
       │ 4. Create Job record
       │ 5. Submit background job
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Background Job Processing                              │
│                                                                 │
│ ThreadPoolExecutor.submit(process_job)                          │
│                                                                 │
│ ┌──────────────────────────────────────────────────────────┐  │
│ │ 1. Update job status: 'processing'                       │  │
│ │ 2. Get submission data from database                       │  │
│ │ 3. Generate Excel report                                  │  │
│ │    - Progress: 10% → 40%                                   │  │
│ │ 4. Generate PDF report                                    │  │
│ │    - Progress: 40% → 100%                                 │  │
│ │ 5. Update job with result URLs                             │  │
│ │ 6. Mark job as 'completed'                                │  │
│ └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Client polls job status
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Job Status Polling                                     │
│ GET /module/job-status/<job_id>                                │
│                                                                 │
│ Response:                                                      │
│ {                                                              │
│   "status": "completed",                                      │
│   "progress": 100,                                            │
│   "result_data": {                                            │
│     "excel": "https://app.com/generated/report.xlsx",        │
│     "pdf": "https://app.com/generated/report.pdf"             │
│   }                                                            │
│ }                                                              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Display download links
       ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Display Download Links                                 │
│                                                                 │
│ ✅ Reports generated successfully!                              │
│                                                                 │
│ [📊 Download Excel Report] [📄 Download PDF Report]           │
└─────────────────────────────────────────────────────────────────┘
```

### Form Submission State Diagram

```
┌─────────────┐
│   Draft     │ (User filling form)
└──────┬──────┘
       │
       │ Submit
       ▼
┌─────────────┐
│  Submitted  │ (Form submitted, job created)
└──────┬──────┘
       │
       │ Background job starts
       ▼
┌─────────────┐
│ Processing  │ (Reports being generated)
└──────┬──────┘
       │
       │ Reports generated
       ▼
┌─────────────┐
│  Completed  │ (Reports ready for download)
└─────────────┘
       │
       │ OR Error occurred
       ▼
┌─────────────┐
│   Failed    │ (Error message stored)
└─────────────┘
```

---

## 📤 File Upload Flow

### Photo Upload Process

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHOTO UPLOAD FLOW                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   User      │
│  Selects    │
│  Photos     │
└──────┬──────┘
       │
       │ Multiple file selection
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Client-Side Photo Queue (JavaScript)                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ PhotoUploadQueue class                                     │  │
│  │ - Validates file size (max 10MB)                          │  │
│  │ - Validates file type (PNG, JPG, JPEG)                    │  │
│  │ - Creates preview thumbnails                              │  │
│  │ - Manages upload queue                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ For each photo in queue
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /module/upload-photo                                       │
│  FormData: {file: File object}                                  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ 1. Validate file
       │ 2. Upload to Cloudinary
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cloudinary Upload (with Retry)                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Attempt 1: Upload                                          │  │
│  │   ↓ Failed?                                                │  │
│  │ Wait 2 seconds                                             │  │
│  │   ↓                                                        │  │
│  │ Attempt 2: Upload                                          │  │
│  │   ↓ Failed?                                                │  │
│  │ Wait 4 seconds                                            │  │
│  │   ↓                                                        │  │
│  │ Attempt 3: Upload                                          │  │
│  │   ↓ Failed?                                                │  │
│  │ Fallback to local storage                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Return URL
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Response                                                        │
│  {                                                              │
│    "url": "https://res.cloudinary.com/.../photo.jpg",         │
│    "is_cloud": true,                                            │
│    "public_id": "uploads/photo_abc123"                          │
│  }                                                              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Store in photo queue
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Display Photo Preview                                          │
│  - Thumbnail image                                              │
│  - Remove button                                                │
│  - Upload status indicator                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Upload Retry Logic Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              UPLOAD RETRY LOGIC FLOW                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  Upload     │
│  Request    │
└──────┬──────┘
       │
       │ Attempt 1
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Try Cloudinary Upload                                           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Success?
       │ Yes → Return URL
       │ No → Continue
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Wait 2 seconds (exponential backoff)                           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Attempt 2
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Try Cloudinary Upload                                           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Success?
       │ Yes → Return URL
       │ No → Continue
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Wait 4 seconds (exponential backoff)                           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Attempt 3
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Try Cloudinary Upload                                           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Success?
       │ Yes → Return URL
       │ No → Fallback
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Fallback to Local Storage                                       │
│  - Save to generated/uploads/                                   │
│  - Return local URL                                             │
│  - Mark is_cloud = false                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📄 Report Generation Flow

### Report Generation Process

```
┌─────────────────────────────────────────────────────────────────┐
│              REPORT GENERATION FLOW                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  Background │
│  Job        │
│  Created    │
└──────┬──────┘
       │
       │ ThreadPoolExecutor.submit()
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  process_job(sub_id, job_id, config, app)                      │
│                                                                 │
│  1. Update job status: 'processing'                            │
│  2. Update job progress: 0%                                    │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Get submission data
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Get Submission Data                                            │
│  - Query database for submission                                │
│  - Parse form_data JSON                                         │
│  - Extract all form fields                                      │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Generate Excel
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Generate Excel Report                                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Create workbook (openpyxl/XlsxWriter)                  │  │
│  │ 2. Apply professional formatting                           │  │
│  │ 3. Add header with logo                                    │  │
│  │ 4. Add project information                                 │  │
│  │ 5. Add form data tables                                    │  │
│  │ 6. Insert images (if applicable)                          │  │
│  │ 7. Save to generated/ directory                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Progress: 10% → 40%                                           │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Generate PDF
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Generate PDF Report                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Create PDF document (ReportLab)                       │  │
│  │ 2. Add header with logo                                    │  │
│  │ 3. Add project information table                          │  │
│  │ 4. Add section headings                                    │  │
│  │ 5. Add form data tables                                    │  │
│  │ 6. Add photo grids (with aspect ratio preservation)        │  │
│  │ 7. Add signature sections                                  │  │
│  │ 8. Apply professional styling                               │  │
│  │ 9. Save to generated/ directory                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Progress: 40% → 100%                                          │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Update job with results
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Complete Job                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ - Update result_data: {                                    │  │
│  │     excel: "https://.../report.xlsx",                      │  │
│  │     pdf: "https://.../report.pdf"                          │  │
│  │   }                                                        │  │
│  │ - Update status: 'completed'                                │  │
│  │ - Update progress: 100%                                     │  │
│  │ - Set completed_at timestamp                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Report Generation State Diagram

```
┌─────────────┐
│   Pending   │ (Job created, waiting to start)
└──────┬──────┘
       │
       │ Worker picks up job
       ▼
┌─────────────┐
│ Processing  │ (Reports being generated)
│             │
│ Progress:   │
│ 0% → 10%    │ (Started)
│ 10% → 40%   │ (Excel generation)
│ 40% → 100%  │ (PDF generation)
└──────┬──────┘
       │
       │ Reports generated successfully
       ▼
┌─────────────┐
│  Completed  │ (Reports ready)
└─────────────┘
       │
       │ OR Error occurred
       ▼
┌─────────────┐
│   Failed    │ (Error message stored)
└─────────────┘
```

---

## 🔄 Workflow Review Process

### Supervisor Review Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              SUPERVISOR REVIEW FLOW                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│ Technician  │
│  Submits    │
│   Form      │
└──────┬──────┘
       │
       │ workflow_status = 'submitted'
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Supervisor Notification                                        │
│  - Email notification (if configured)                           │
│  - Dashboard notification                                       │
│  - supervisor_notified_at = now()                               │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Supervisor accesses dashboard
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  GET /api/workflow/submissions/pending                          │
│  Returns list of pending submissions                            │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Supervisor clicks on submission
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  GET /module/form?edit=<submission_id>                          │
│                                                                 │
│  Load submission data:                                           │
│  - All form fields (read-only)                                  │
│  - Photos (displayed as thumbnails)                            │
│  - Technician signature (displayed as image)                    │
│  - Supervisor signature pad (editable)                          │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Supervisor reviews and signs
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /module/submit-with-urls                                   │
│                                                                 │
│  Payload includes:                                             │
│  - supervisor_signature: "data:image/png;base64,..."            │
│  - supervisor_comments: "Reviewed and approved"                │
│  - supervisor_verified: true                                    │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Update workflow status
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Update Submission                                              │
│  - workflow_status = 'supervisor_reviewed'                       │
│  - supervisor_reviewed_at = now()                                │
│  - supervisor_id = current_user.id                              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Manager notification (if configured)
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Manager Notification                                            │
│  - Email notification (if configured)                           │
│  - Dashboard notification                                       │
│  - manager_notified_at = now()                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow State Diagram

```
┌─────────────┐
│  Submitted  │ (Technician submitted form)
└──────┬──────┘
       │
       │ Supervisor notified
       ▼
┌─────────────┐
│ Supervisor  │
│  Notified   │
└──────┬──────┘
       │
       │ Supervisor starts review
       ▼
┌─────────────┐
│ Supervisor  │
│  Reviewing  │
└──────┬──────┘
       │
       │ Supervisor signs and verifies
       ▼
┌─────────────┐
│ Supervisor  │
│  Reviewed   │
└──────┬──────┘
       │
       │ Manager notified
       ▼
┌─────────────┐
│  Manager    │
│  Notified   │
└──────┬──────┘
       │
       │ Manager starts review
       ▼
┌─────────────┐
│  Manager    │
│  Reviewing  │
└──────┬──────┘
       │
       │ Manager approves
       ▼
┌─────────────┐
│  Approved   │ (Final approval)
└─────────────┘
```

---

## 🗄️ Database Relationships

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│              DATABASE RELATIONSHIPS                               │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────┐
                    │    User     │
                    │─────────────│
                    │ id (PK)     │
                    │ username    │◄─────┐
                    │ email       │      │
                    │ role        │      │
                    │ designation │      │
                    │ access_*    │      │
                    └──────┬──────┘      │
                           │              │
                           │ 1            │ N
                           │              │
                           │              │
                    ┌──────▼──────┐      │
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
                    ┌──────▼──────┐      │
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

### Relationship Details

**User → Submission (1:N)**
- One user can have many submissions
- Foreign key: `submission.user_id` → `user.id`

**User → Submission (Supervisor) (1:N)**
- One supervisor can review many submissions
- Foreign key: `submission.supervisor_id` → `user.id`

**User → Submission (Manager) (1:N)**
- One manager can review many submissions
- Foreign key: `submission.manager_id` → `user.id`

**Submission → Job (1:N)**
- One submission can have multiple jobs (retries)
- Foreign key: `job.submission_id` → `submission.id`
- Cascade delete: If submission deleted, jobs deleted

**Submission → File (1:N)**
- One submission can have multiple files
- Foreign key: `file.submission_id` → `submission.id`
- Cascade delete: If submission deleted, files deleted

**User → AuditLog (1:N)**
- One user can have many audit log entries
- Foreign key: `audit_log.user_id` → `user.id`

**User → Session (1:N)**
- One user can have multiple active sessions
- Foreign key: `session.user_id` → `user.id`
- Cascade delete: If user deleted, sessions deleted

---

## 🏗️ System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SYSTEM ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  Web         │  │  Mobile      │  │  PWA          │        │
│  │  Browser     │  │  Web         │  │  App          │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼──────────────────┼──────────────────┼───────────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              FLASK APPLICATION LAYER                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Injaaz.py (App Factory)                      │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │  │
│  │  │  Auth    │  │  Admin   │  │  Module  │              │  │
│  │  │Blueprint │  │Blueprint │  │Blueprint │              │  │
│  │  └──────────┘  └──────────┘  └──────────┘              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │  │
│  │  │Workflow  │  │ Services │  │Background│              │  │
│  │  │Blueprint │  │  Layer   │  │   Jobs   │              │  │
│  │  └──────────┘  └──────────┘  └──────────┘              │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────┬──────────────┬──────────────┬──────────────┬───────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  PostgreSQL  │  │  Cloudinary  │  │    Redis     │  │  File System │
│   Database   │  │   (CDN)      │  │  (Optional)  │  │   (Local)    │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### Component Interaction

```
┌─────────────────────────────────────────────────────────────────┐
│              COMPONENT INTERACTION                               │
└─────────────────────────────────────────────────────────────────┘

Client Request
    │
    ▼
┌──────────────┐
│   Flask      │
│  Routes      │
└──────┬───────┘
       │
       ├──► JWT Middleware ──► Validate Token
       │
       ├──► Access Control ──► Check Permissions
       │
       ├──► Business Logic ──► Process Request
       │
       ├──► Database ──► Query/Update Data
       │
       ├──► Cloudinary ──► Upload/Retrieve Files
       │
       ├──► Background Jobs ──► Generate Reports
       │
       └──► Response ──► Return to Client
```

---

## 🔗 Module Interaction Flow

### Module Request Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              MODULE INTERACTION FLOW                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   User      │
│  Request    │
└──────┬──────┘
       │
       │ GET /hvac-mep/form
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Module Route Handler                                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Extract JWT token from request                         │  │
│  │ 2. Validate token                                         │  │
│  │ 3. Get user_id from token                                 │  │
│  │ 4. Load User from database                                │  │
│  │ 5. Check module access (user.has_module_access('hvac_mep'))│ │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Access granted?
       │ Yes → Continue
       │ No → Return 403 Forbidden
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Render Form Template                                           │
│  - Load template: module_hvac_mep/templates/hvac_mep_form.html │
│  - Pass user data to template                                  │
│  - Pass module access flags                                     │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Return HTML
       ▼
┌─────────────┐
│   Client    │
│  Displays   │
│   Form      │
└─────────────┘
```

### Module Submission Flow

```
┌─────────────┐
│   User      │
│  Submits    │
│   Form      │
└──────┬──────┘
       │
       │ POST /hvac-mep/submit-with-urls
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Module Route Handler                                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Validate JWT token                                     │  │
│  │ 2. Validate form data                                    │  │
│  │ 3. Upload signatures to Cloudinary                       │  │
│  │ 4. Create Submission record                               │  │
│  │ 5. Create Job record                                      │  │
│  │ 6. Submit background job                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Background job
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Module Generator Functions                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ - create_excel_report(data, output_dir)                   │  │
│  │ - create_pdf_report(data, output_dir)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────┘
       │
       │ Reports generated
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Update Job Status                                              │
│  - status: 'completed'                                          │
│  - result_data: {excel: "...", pdf: "..."}                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Summary

This document provides visual flowcharts and diagrams for:

✅ **Authentication Flow** - Login, token usage, refresh  
✅ **Form Submission Flow** - Complete submission process  
✅ **File Upload Flow** - Photo upload with retry logic  
✅ **Report Generation Flow** - Excel and PDF creation  
✅ **Workflow Review Process** - Supervisor/Manager review  
✅ **Database Relationships** - Entity relationship diagram  
✅ **System Architecture** - High-level architecture  
✅ **Module Interaction Flow** - Request and submission flows  

These diagrams serve as visual references for understanding the application's processes and data flows.

---

**Document Version:** 1.0  
**Last Updated:** 2024-12-30  
**Maintained By:** Injaaz Development Team
