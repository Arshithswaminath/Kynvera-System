# Amaan / Injaaz — Application Modules (Detailed)

**Product:** Amaan Systems (facilities & operations platform)  
**Architecture:** Modular Flask monolith — many blueprints, one database, shared auth and infrastructure  
**Primary app factories:** `Amaan.py`, `Injaaz.py`  
**Last updated:** July 2026 (aligned with repository code)

This document is the **full module reference**: purpose, URL prefixes, capabilities, routes, data entities, document outputs, and access control. For a short product overview see [APPLICATION_OVERVIEW.md](APPLICATION_OVERVIEW.md). For client demos see [AMAAN_CLIENT_DEMO_USER_GUIDE.md](AMAAN_CLIENT_DEMO_USER_GUIDE.md).

---

## Table of contents

1. [Platform at a glance](#1-platform-at-a-glance)
2. [Blueprint registration map](#2-blueprint-registration-map)
3. [Access control model](#3-access-control-model)
4. [Shared infrastructure](#4-shared-infrastructure)
5. [Core UI shells](#5-core-ui-shells)
6. [Authentication](#6-authentication-appauth)
7. [Administration & Sales (BD)](#7-administration--sales-bd-appadmin)
8. [Inspection workflow](#8-inspection-workflow-appworkflow)
9. [Fire Systems](#9-fire-systems-module_hvac_mep)
10. [Inspection hub & CD notifications](#10-inspection-hub--cd-notifications-module_inspection)
11. [HR](#11-hr-module_hr)
12. [Service Tickets](#12-service-tickets-module_ticketing)
13. [Store / Procurement](#13-store--procurement-module_store)
14. [Operations](#14-operations-module_operations)
15. [Finance](#15-finance-module_finance)
16. [Email Automation (MMR)](#16-email-automation-mmr-module_mmr)
17. [DocHub](#17-dochub-appdocs)
18. [Live Assistant](#18-live-assistant-module_assistant)
19. [Reports API](#19-reports-api-appreports_api)
20. [Background jobs](#20-background-jobs-apptasks)
21. [Site visit (legacy / alternate factory)](#21-site-visit-legacy--alternate-factory)
22. [Document & report outputs matrix](#22-document--report-outputs-matrix)
23. [Related docs](#23-related-docs)

---

## 1. Platform at a glance

Amaan unifies day-to-day facilities work for AMAAN LLC (fire protection, fire-fighting, security systems, and facility operations):

| Area | What users do |
|------|----------------|
| **Inspections** | Digital fire-system inspections with photos, signatures, multi-stage approval, PDF/Excel |
| **HR** | Staff request forms with HR → GM approval and branded PDF/DOCX |
| **Service tickets** | Work orders from create → site work → review → finance → invoice |
| **Store** | Materials catalog, sets, property assignment, Excel import/export |
| **Operations** | Overtime, timesheet, attendance, clients, trading invoices, cheques |
| **Finance** | Contracts, costing/margin gate, monthly reports, ticket–contract linking |
| **Sales (BD)** | Pipeline, follow-ups, contacts, quotations → invoice / LPO |
| **DocHub** | Shared document library with per-user grants |
| **Email automation** | Scheduled recurring emails with attachments |
| **Admin** | Users, access flags, designations, devices, team, knowledge base |

---

## 2. Blueprint registration map

Registered in `Amaan.py` / `Injaaz.py` (defensive `try/except` so a broken module does not stop the app):

| Module / area | Blueprint | URL prefix |
|---------------|-----------|------------|
| Fire Systems | `hvac_mep_bp` | `/hvac-mep` |
| Auth | `auth_bp` | `/api/auth` |
| Admin (+ BD APIs) | `admin_bp` | `/api/admin` |
| Inspection workflow | `workflow_bp` | `/api/workflow` |
| DocHub API | `docs_bp` | `/api/docs` |
| HR | `hr_bp` | `/hr` |
| Store | `store_module` | `/store` |
| Inspection hub | `inspection_bp` | `/inspection` |
| Email Automation | `mmr_bp` | `/admin/mmr` |
| Ticketing | `ticketing` | `/tickets` |
| Operations | `operations_bp` | `/operations` |
| Finance | `finance` | `/finance` |
| Assistant | `assistant_bp` | `/api/assistant` |
| Reports regenerate | `reports` | `/api/reports` |

**Note:** `site_visit_bp` (`/site-visit`) is registered only in the alternate `app/__init__.py` factory, not in the primary Amaan/Injaaz apps.

---

## 3. Access control model

Authorization combines three layers:

1. **Role** — e.g. `admin` (typically full bypass of module flags)
2. **Designation** — workflow stage gates (who can approve)
3. **Module / submodule flags** on `User`

### 3.1 Module access flags

| Flag | Gates |
|------|--------|
| `access_hvac` | Fire Systems inspection forms |
| `access_hr` | HR module entry |
| `access_procurement_module` | Store / procurement |
| `access_business_development` | Sales pipeline (+ BD inspection reviewer lane) |
| `access_sales_manager` | View all salespeople’s pipelines |
| `access_quotations` | Create / edit / submit quotations |
| `access_report_generation` | Email Automation (MMR) hub |
| `access_submitted_forms` | Submitted-forms workflow hub |
| `access_ticketing` | Service tickets |
| `access_operations` | Operations hub (any / overall) |
| `access_operations_manage` | Operations mutate (vs view-only) |
| `access_operations_overtime` | Overtime |
| `access_operations_timesheet` | Timesheet |
| `access_operations_attendance` | Attendance |
| `access_operations_invoices` | Trading invoices |
| `access_operations_clients` | Clients |
| `access_operations_cheques` | Cheques |
| `access_finance` | Finance module |

### 3.2 Typical designations (workflow)

| Designation | Typical stage |
|-------------|---------------|
| `supervisor` | First inspection / ticket review |
| `operations_manager` | Ops manager approval |
| `sales` / `business_development` | BD inspection lane; sales work |
| `procurement` | Procurement inspection lane |
| `general_manager` | Final GM gate |
| `hr_manager` | HR staff review |
| `finance` | Finance confirm / cheque verify |

Admins usually see all modules; other users only see tiles and APIs their flags allow.

---

## 4. Shared infrastructure

| Concern | Location | Role |
|---------|----------|------|
| JWT / session | `app/middleware.py`, `common/jwt_session.py`, `common/login_guard.py` | `token_required`, `admin_required`, BD helpers |
| Security | `common/security.py`, password helpers, CSRF in app factory | Sanitize, rate limits, URL checks |
| Email | `common/email_service.py` | SMTP / Brevo / Mailjet |
| WhatsApp | `common/whatsapp.py` | Optional CD reminders (`WHATSAPP_*`) |
| Workflow emails | `common/workflow_notifications.py` | Inspection / HR stage emails |
| Inspection in-app alerts | `common/inspection_inapp_notifications.py` | Notification rows for inspection events |
| SLA | `common/sla.py` | Priority → hours; ticket due / breach |
| Ownership | `common/ownership.py` | Owner or elevated mutate on Ops records |
| Signatures | `templates/partials/signature_modal.html`, `static/js/signature_modal.js` | Shared capture UI |
| Models hub | `app/models.py` | Primary ORM entities |
| Config | `config.py`, `common/config_validator.py` | Paths, secrets, Redis, mail, schedules |

---

## 5. Core UI shells

Defined on the main app (not a separate blueprint):

| Path | Purpose |
|------|---------|
| `/`, `/dashboard` | Home dashboard — module cards, notification poll |
| `/login`, `/register`, `/logout` | Auth pages |
| `/about` | Company / product about |
| `/workflow/pending-reviews` | Pending inspection (and related) reviews |
| `/workflow/submitted-forms` | User’s submitted forms hub |
| `/admin/dashboard` | Admin shell |
| `/admin/bd` | Sales / BD UI |
| `/admin/devices` | Device management |
| `/admin/team-management` | Team management |
| `/admin/personal-progress` | Personal progress projects |
| `/dochub` | DocHub UI |
| `/offline`, `/manifest.json`, `/health` | PWA / health |
| Generated file serve | Configurable `GENERATED_DIR` paths |

---

## 6. Authentication (`app/auth`)

**Prefix:** `/api/auth`  
**Pages:** `/login`, `/register`, `/logout`

### Purpose

Identity, JWT sessions (header + optional cookies), profile, and password recovery.

### Capabilities

- Register / login / refresh / logout
- Current user (`/me`), profile update, default signature
- Change password
- Forgot-password OTP flow (`EmailOtp`)
- Session revocation via JTI blocklist

### Key entities

`User`, `Session`, `EmailOtp`

### Access

Public: login, register, OTP. JWT required for profile and session endpoints. Login is rate-limited when limiter is configured.

---

## 7. Administration & Sales (BD) (`app/admin`)

**API prefix:** `/api/admin`  
**UI:** `/admin/dashboard`, `/admin/bd`, `/admin/devices`, `/admin/team-management`, `/admin/personal-progress`

### Purpose

Platform administration plus the **Sales / Business Development** commercial pipeline (projects, follow-ups, contacts, quotations).

### 7.1 Admin capabilities

| Area | What it covers |
|------|----------------|
| **Users** | CRUD, module access flags, designation, password reset/unlock, activity, Excel import/export |
| **Employees / technicians** | CRUD + import |
| **Devices** | CRUD, bulk, Excel |
| **Documents** | List/delete; DocHub access-user grants |
| **Notification config** | Email / alert configuration |
| **Protect PIN + OTP** | Sensitive admin actions |
| **Dashboard / stats** | Overview, workflow stats, designations |
| **Personal progress** | Admin personal projects |
| **Knowledge base** | CRUD, upload, link, refetch (feeds Live Assistant) |

### 7.2 Sales / BD capabilities

| Area | Details |
|------|---------|
| **Pipeline stages** | prospecting → qualifying → proposal → negotiation → closing |
| **Projects** | CRUD, Excel import, promote |
| **Follow-ups & contacts** | Activity tracking |
| **Quotations** | CRUD, submit, approve/reject/cancel, generate invoice, attach LPO, PDF |
| **Quotation statuses** | `draft`, `sent`, `pending_approval`, `approved`, `rejected`, `cancelled`, `accepted`, `expired` |
| **Analytics helpers** | `app/bd/analytics.py` — weighted forecast, funnel, stalled deals (no separate BD blueprint) |

**Quotation PDF builder:** `module_operations/quotation_builder.py` (invoked from admin BD APIs, not an Operations HTTP route).

### Key entities

`User`, `Employee`, `Technician`, `Device`, `BDProject`, `BDFollowUp`, `BDContact`, `BDActivity`, quotation models, `AdminPersonalProject`, `KnowledgeBaseEntry`, DocHub access models, `NotificationConfig`

### Access

Mostly `admin_required`. BD endpoints use BD access helpers; preparing quotes requires `access_quotations`. Sales managers can see broader pipelines via `access_sales_manager`.

### Key templates

`admin_dashboard.html`, `admin_bd_module.html`, `admin_bd_project_detail.html`, `admin_team_management.html`, `admin_device_management.html`, `admin_personal_progress.html`, BD partials (`bd_project_workspace*`, `bd_quote_editor.html`)

---

## 8. Inspection workflow (`app/workflow`)

**API prefix:** `/api/workflow`  
**Pages:** `/workflow/pending-reviews`, `/workflow/submitted-forms`

### Purpose

Multi-stage review pipeline for Fire Systems inspection submissions, including drafts, history, trail, reject, withdraw, revoke, revise, and resubmit.

### Typical approval flow

```text
Submitter
  → Supervisor
  → Operations Manager
  → Business Development  ─┐
  → Procurement           ─┴─ (parallel lanes)
  → General Manager
```

### Key API groups

| Group | Examples |
|-------|----------|
| Queues / stats | dashboard, history, pending, stats, inspection-dashboard-stats |
| Mine | my-submissions, my-trail |
| Approve | approve-supervisor, approve-ops-manager, approve-bd, approve-procurement, approve-gm |
| Lifecycle | reject, withdraw, revoke, cancel-and-revise, update, resubmit, save-draft |

### Key entities

`Submission`, `User`, `Notification`, related `Job` / `File`

### Access

JWT + designation-based stage gates. `access_submitted_forms` for the submitted-forms hub. BD lane via BD / sales designation helpers.

### Related

`common/workflow_notifications.py`, `common/inspection_inapp_notifications.py`, `templates/workflow_signatures.html`, `pending_reviews.html`, `submitted_forms.html`

---

## 9. Fire Systems (`module_hvac_mep`)

**Prefix:** `/hvac-mep`  
**`module_type`:** `hvac_mep`  
**UI label:** Fire Systems Inspection (`fire_inspection_form.html`)

### Purpose

Field fire-system inspection capture (alarms, sprinklers, pumps, extinguishers, emergency lighting, smoke control, and related systems), photos, signatures, draft/submit, and async PDF + Excel generation.

### Key routes

| Area | Paths (examples) |
|------|------------------|
| Form | `/hvac-mep/form` |
| Data | `/dropdowns`, `/save-draft`, `/submit`, `/submit-with-urls` |
| Media | `/upload-photo`, `/add-photos-to-item` |
| Jobs | `/status/<job_id>`, `/generated/<file>`, `/download/<job_id>/<file_type>` |

### Document generation

`hvac_generators.py`, `inspection_service_report.py`, `generator.py`, plus shared professional PDF/Excel services. Background: `app.tasks.inspection_jobs.run_hvac_process_job`.

### Access

`access_hvac`; workflow roles control edit/view by stage.

---

## 10. Inspection hub & CD notifications (`module_inspection`)

**Prefix:** `/inspection`

### Purpose

Landing hub for inspection work and **Civil Defense / regulatory inspection notification** tracking. The Fire Systems form engine lives under `/hvac-mep`.

### Capabilities

- Dashboard (`/inspection/`)
- Notifications UI (`/inspection/notifications`)
- APIs: notifications CRUD, outcome, comment, stats
- Emails via `common.email_service`; optional WhatsApp reminders

### Key entities

`InspectionNotification`, `Notification`, `User`

### Access

`access_hvac` or admin. Notification write also available to sales/BD flags and related designations.

### Templates

`inspection_dashboard.html`, `inspection_notifications.html`

---

## 11. HR (`module_hr`)

**Prefix:** `/hr`

### Purpose

Digitize staff requests and HR processes: employee submit → optional replacement / management-chain signoffs → HR manager review → GM final approval, with branded PDF and DOCX export and in-app notifications.

### Live form types (`module_type`)

| Form | Typical path |
|------|----------------|
| Leave application | `/hr/leave-application-form` |
| Commencement | `/hr/commencement-form` |
| Duty resumption | `/hr/duty-resumption-form` |
| Contract renewal | `/hr/contract-renewal-form` |
| Performance evaluation | `/hr/performance-evaluation-form` |
| Grievance / disciplinary | `/hr/grievance-form` |
| Interview assessment | `/hr/interview-assessment-form` |
| Passport release / submission | `/hr/passport-release-form` |
| Staff appraisal | `/hr/staff-appraisal-form` |
| Station clearance | `/hr/station-clearance-form` |
| Visa renewal | `/hr/visa-renewal-form` |
| Asset handover / takeover | `/hr/asset-handover-form` |

*(Some legacy templates exist without live routes, e.g. long vacation / termination.)*

### Hub pages

| Path | Role |
|------|------|
| `/hr/` | HR dashboard |
| `/hr/my-requests` | Employee list |
| `/hr/pending-review` | HR staff queue |
| `/hr/gm-approval` | GM final approval |
| `/hr/approved-forms` | Completed / approved |

### Key APIs

| Group | Examples |
|-------|----------|
| Submit / list | `POST /hr/api/submit`, my-submissions, submissions |
| Approvals | hr-approve / hr-reject / gm-approve / gm-reject |
| Signoffs | replacement-signoff*, mgmt-signoff*; sign pages `/hr/replacement-sign/<id>`, `/hr/mgmt-sign/<id>` |
| Export | print, print-pdf, download-pdf, download-docx |
| Notifications | `/hr/api/notifications*` (also polled by main dashboard) |
| Leave | `/hr/api/leave-balances/me` |

### Document generation

- PDF: `hr_pdf_builder.py`, `pdf_service.py` (ReportLab)
- DOCX: `docx_builder.py`, `docx_service.py` (templates + placeholders)

### Key supporting modules

`hr_management_chain.py`, `hr_routed_signoffs.py`, `hr_signoff_activity.py`, `hr_visibility.py`, `hr_commencement_reporting.py`, `replacement_signoff.py`, `attendance_api.py`, `signature_preprocess.py`, `print_utils.py`

### Access

JWT. `access_hr` = module entry. `designation == hr_manager` for HR staff queues. GM / admin for org-wide GM approve. Bare `access_hr` alone does not grant org-wide list visibility.

---

## 12. Service Tickets (`module_ticketing`)

**Prefix:** `/tickets`

### Purpose

End-to-end work-order / complaint lifecycle: create, assign, site work, materials & manpower, hold/cancel, supervisor / GM / finance gates, PDFs, analytics, and settings.

### Canonical statuses

```text
open → assigned → site_attended → work_started → work_completed
  → verification → pending_gm_approval → pending_finance → closed
```

Also: `on_hold`, `cancelled` (+ some legacy display statuses).

### Pages

| Path | Purpose |
|------|---------|
| `/tickets/` | Dashboard / KPIs |
| `/tickets/list` | Queue list |
| `/tickets/new` | Create work order |
| `/tickets/<ticket_id>` | Detail / actions |
| `/tickets/settings` | Projects, locations, fault catalog |
| `/tickets/reports` | Report downloads |
| `/tickets/analytics` | Analytics UI |
| Service report UI | Per-ticket service report |

### API capability groups

- Create, status transitions, assign, notes, images
- Manpower; materials (bulk / set / ad-hoc + OM then GM approve)
- Hold / resume / cancel; close / advance
- Submit to supervisor; assign technician; mark completed; supervisor close
- Client sign; GM approve/reject; finance confirm; mark paid
- Docs: work-order PDF, invoice, service report (+ PDF)
- Settings: projects, location tree (property / zone / sub-zone / base-unit), title templates, fault catalog rebuild, BD active projects
- Reports download keys: `work_orders`, `financial`, `projects`, `team`, `materials`
- SLA via `common.sla`; CD notifications feed on dashboard where applicable

### Document builders

`ticket_pdf_builder.py`, `ticket_invoice_builder.py`, `service_report_pdf_builder.py`, `service_report.py`, `report_builders.py`

### Related

`analytics.py`, `fault_catalog.py`, `fault_catalog_build.py`, `data/fault_codes.json`

### Access

`access_ticketing` (admin always). Visibility by role / assignment; finance reports gated; supervisor teams; ad-hoc materials require OM then GM.

### Key entities

Ticket family models, `AdHocMaterialRequest`, `BDProject`, `InspectionNotification`, `Notification`, technicians, store materials linkage

---

## 13. Store / Procurement (`module_store`)

**Prefix:** `/store`

### Purpose

Fire / life-safety materials catalog, stock, property assignment, **material sets**, and Excel import/export — used by tickets and operations invoicing.

### Catalog departments

Fire Alarm · Fire Suppression · Fire Safety · Emergency

### Pages

Dashboard, materials, sets, add-material, properties, property detail, catalog by department.

### API areas

Materials CRUD, stock patch, alerts, consumption ledger, Excel, catalog CRUD, property assign; sets API (`/api/sets*`, `/api/catalog/sets` via `sets_api.py`).

### Key entities

`Submission` with `module_type` `procurement_material` / `catalog_material`; `MaterialSet`, `MaterialSetItem`

### Access

Admin or `access_procurement_module`

### Outputs

Excel sample / export (no branded PDF in this module)

---

## 14. Operations (`module_operations`)

**Prefix:** `/operations`

### Purpose

Operations hub for overtime, clients, trading invoices, cheque preparation, duty timesheet, and attendance. Overtime / clients / invoices are primarily CRUD + ownership (not the inspection multi-stage workflow).

### Sub-modules

| Sub-module | Path / APIs | Notes |
|------------|-------------|--------|
| **Hub** | `/operations/` | Entry dashboard |
| **Overtime** | page + CRUD, Excel import/export/template, settings | Cost calculation |
| **Clients** | pages + CRUD + detail | Master data for invoicing |
| **Trading invoices** | pages + CRUD + PDF | Material sales invoices |
| **Cheques** | pages + CRUD + status + PDF + notification config | Full lifecycle below |
| **Timesheet** | `/operations/timesheet` + `/api/timesheet` | Duty timesheet entries |
| **Attendance** | `/operations/attendance` + import/list/update | Import batches |
| **Catalog materials** | `GET /api/catalog-materials` | Invoice line helpers |

### Cheque lifecycle

```text
requested → verified → prepared → approved → submitted → cleared
```

*(Finance verifies; GM approves — exact labels may vary slightly in UI copy.)*

### Document builders

- Trading invoice: `trading_invoice_builder.py`
- Cheque: `cheque_pdf_builder.py`
- Quotation PDF (used by admin BD): `quotation_builder.py`

### Related API modules

`timesheet_api.py`, `attendance_api.py`

### Key entities

`OvertimeRecord`, `OvertimeSettings`, `Client`, `TradingInvoice`, `TradingInvoiceItem`, `ChequeRequest`, `ChequeRequestItem`, `ChequeStatusLog`, `ChequeNotificationConfig`, `DutyTimesheetEntry`, `AttendanceImportBatch`, `AttendanceEntry`

### Access

`access_operations` and/or submodule flags; `access_operations_manage` for elevated mutate; ownership via `common.ownership`.

### Templates

`operations_dashboard.html`, `overtime.html`, `clients.html`, `client_detail.html`, `trading_invoices.html`, `trading_invoice_detail.html`, `operations_cheques.html`, `operations_cheque_detail.html`, `timesheet.html`, `attendance.html`

---

## 15. Finance (`module_finance`)

**Prefix:** `/finance`

### Purpose

Commercial control: contracts, monthly billing reports, costing / markup, margin gate (~15% default via settings), ticket–contract linking, and processing queue.

### Pages

| Path | Purpose |
|------|---------|
| `/finance/` | Dashboard / invoice queue entry |
| `/finance/contracts` | Contracts |
| `/finance/reports` | Monthly reports |
| `/finance/processing` | Processing queue |
| `/finance/settings` | Finance settings |

### API areas

Settings, stats, contracts CRUD + Excel import/template, reports list/dashboard/export (xlsx|pdf)/generate/send, costing calculate, jobs/queue, `POST /api/tickets/<id>/link-contract`.

### Document generation

`finance_report_builder.py` (PDF + Excel)

### Key entities

`FinanceContract`, `FinanceMonthlyReport`, `FinanceSettings`, `Ticket`, `Job`

### Access

`access_finance`, or designation `general_manager` / `operations_manager` / `finance`, or (for some ticket-linked views) `access_ticketing`. Write (contracts/reports) typically admin or GM.

---

## 16. Email Automation / MMR (`module_mmr`)

**Prefix:** `/admin/mmr`  
**UI name:** Email Automation (legacy folder name “MMR”)

### Purpose

Recurring emails (daily / weekly / monthly / quarterly / interval) with attachments. **APScheduler** (default timezone **Asia/Dubai**) also registers domain SLA scans and daily reminder jobs.

### Capabilities

- Dashboard UI
- Defaults, automations CRUD, toggle, run-now, logs, attachments
- Recipients constrained (e.g. `@injaaz.ae` where enforced in code)

### Key entities

`EmailAutomation`, `EmailAutomationAttachment`, `EmailAutomationRunLog`, `EmailAutomationDefaults`

### Access

Admin or `access_report_generation`

### Related

`scheduler.py` → email jobs + `run_sla_breach_scan` + `run_all_daily_reminders`  
Chargeable-rule notes (where present): `module_mmr/CHARGEABLE_RULES.md`

---

## 17. DocHub (`app/docs`)

**API prefix:** `/api/docs`  
**Page:** `/dochub`

### Purpose

Central company document library: upload, preview, download, star, patch, delete; inline images/references; access-check.

### Key entities

`DocHubDocument`, `DocHubStar`, `DocHubAccess`

### Access

JWT + DocHub access rows (granted via admin) / admin.

---

## 18. Live Assistant (`module_assistant`)

**Prefix:** `/api/assistant`  
**Route:** `POST /api/assistant/chat`

### Purpose

In-app Live Assistant — intent routing, optional LLM, and tools over the signed-in user’s live data and knowledge base.

### Example intents / tools

Pending counts, submissions/drafts, leave history, DocHub search, tickets, inspections, procurement summary, profile help, password/admin help.

### Supporting files

`intents.py`, `responses.py`, `tools.py`, `llm.py`, `rag.py`, `knowledge.py`, `knowledge/faqs.json`, `extract.py`, `fetch_url.py`

### Access

Any authenticated user (JWT). Answers are scoped by that user’s permissions.

---

## 19. Reports API (`app/reports_api`)

**Prefix:** `/api/reports`

### Purpose

On-demand regeneration and lookup of inspection-module reports.

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/reports/regenerate/<submission_id>/excel\|pdf` | Rebuild report |
| GET | `/api/reports/list/<module_type>` | List by module |
| GET | `/api/reports/submission/<submission_id>` | Submission report metadata |

### Access

JWT; submitter, workflow participant, or admin.

---

## 20. Background jobs (`app/tasks`)

| File | Role |
|------|------|
| `worker.py` | RQ worker entry (`REDIS_URL`); optional MMR scheduler |
| `job_runner.py` | `enqueue_or_run` — RQ → ThreadPool → thread → sync fallback |
| `inspection_jobs.py` | HVAC / Civil / Cleaning process jobs + submit notify + email |
| `generate_report.py` | Site-visit report generation |
| `sla_jobs.py` | Ticket SLA breach scan + email |
| `reminder_jobs.py` | AMC renewal, payment follow-up, CD inspection reminders |
| `session_cleanup.py` | Expired session cleanup helper |

Triggered from MMR `scheduler.py` and from form submit paths via inspection enqueue helpers.

---

## 21. Site visit (legacy / alternate factory)

**Paths:** `app/modules/site_visit/`, `app/site_visit_form.py`  
**Prefix (when registered):** `/site-visit`

Registered in `app/__init__.py` only — **not** in primary Amaan/Injaaz `create_app`. Includes form, metadata submit, photo update, finalize, report status, generated file serve; uses Cloudinary signatures and `app/tasks/generate_report.py` where wired.

Treat as legacy / alternate entry unless that factory is the active deployment path.

---

## 22. Document & report outputs matrix

| Domain | Typical outputs |
|--------|-----------------|
| **HR** | Branded PDF; DOCX from templates; HTML print |
| **Fire Systems** | Inspection PDF; Excel; signed workflow / service-style PDF |
| **Service tickets** | Work order PDF; service report PDF; invoice PDF; report packs (work orders, financial, projects, team, materials) |
| **Operations** | Trading invoice PDF; cheque PDF |
| **Sales / BD** | Quotation PDF; generate trading invoice / LPO after approval |
| **Finance** | Monthly finance report PDF + Excel |
| **Email Automation** | Scheduled email packages with attachments |
| **Store** | Excel import/export |
| **Reports API** | On-demand PDF/Excel regenerate for submissions |

---

## 23. Related docs

| Document | Contents |
|----------|----------|
| [APPLICATION_OVERVIEW.md](APPLICATION_OVERVIEW.md) | High-level product overview |
| [PROJECT_SCOPE_METHODS_AND_TECHNIQUES.md](PROJECT_SCOPE_METHODS_AND_TECHNIQUES.md) | Scope + engineering methods |
| [AMAAN_CLIENT_DEMO_USER_GUIDE.md](AMAAN_CLIENT_DEMO_USER_GUIDE.md) | Demo walkthrough |
| [SECURITY_POSTURE_CLIENT.md](SECURITY_POSTURE_CLIENT.md) | Client-facing security posture |
| [SECURITY_SCALABILITY_AUDIT.md](SECURITY_SCALABILITY_AUDIT.md) | Security / scalability audit notes |
| [SECRET_ROTATION.md](SECRET_ROTATION.md) | Secret rotation |
| README / SETUP / PROJECT_STRUCTURE (repo root) | Setup and folder layout |

---

*This modules reference is derived from the live codebase (blueprints, routes, models, and builders). Update it when modules, URL prefixes, or access flags change.*
