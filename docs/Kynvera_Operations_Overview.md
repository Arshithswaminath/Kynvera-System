# Kynvera Operations

**Kynvera Operations Application**  
*All operations. One sign-in. One audit trail.*

This document is a comprehensive overview of the Kynvera Operations Application: what it is, who uses it, what each module does, and how day-to-day work moves through the platform.

Companion documents:

- [Module Architecture](Kynvera_Operations_Architecture.md) — how each module is designed and how work streams through it
- [Security, Scale & Continuity](Kynvera_Operations_Security_Scale_Continuity.md) — security measures, growth, backup, and client questions

---

## 1. What Kynvera Operations is

Kynvera Operations is a **facilities and workforce operations application**. It is the system field teams, supervisors, HR, procurement, and leadership use to capture work on site, move it through review, keep documents and records in one place, and produce reports that operations can stand behind.

It is **one application**, not a collection of disconnected tools. A person signs in once. They only see the modules they are allowed to use. Every material action — a form submitted, a ticket closed, a leave approved, a report emailed — is recorded against that person.

The platform covers the full operations stack:

| Area | What people do here |
|------|---------------------|
| **Field work** | Inspections, photos, signatures, work orders, asset tags |
| **People** | HR forms, leave, hiring documents, manpower tracking |
| **Materials** | Catalogues, stock, purchase requests, suppliers |
| **Quality & safety** | QHSI inspections, staff kit / PPE compliance, training |
| **Commercial** | Business-development pipeline, quotations, client email packs |
| **Reporting** | CAFM / MMR analytics, scheduled Excel packs, chargeable rules |
| **Records** | Controlled documents (DocHub), in-app Files, optional Drive sync |
| **Oversight** | Pending reviews, history, admin, devices, automations |
| **Assistance** | In-app assistant that answers from live data and never acts silently |

Kynvera Operations is the **operations backbone**. It complements finance systems, CAFM, and email. It does not replace payroll, ERP, or Microsoft 365.

---

## 2. Who it is for

Typical users sit in facilities and operations organisations:

| Who | What they use it for |
|-----|----------------------|
| **Technicians / site staff** | Raise or update tickets, capture inspection photos, complete assigned work |
| **Supervisors** | Assign work, review forms, convert email drafts, close or escalate tickets |
| **Operations managers** | Oversee queues, approve inspections, watch SLA and site load |
| **HR** | Leave, commencement, visa, appraisals, hiring documents, manpower boards |
| **General Manager** | Final sign-off on HR and inspection workflows that require GM |
| **Procurement** | Materials, stock, purchase requests, supplier records |
| **Business development** | Pipeline, quotations, client-facing email packs |
| **QHSI / quality** | Safety and hospitality inspections, training, staff compliance |
| **Administrators** | Users, access flags, devices, knowledge, database convenience backups |

Access is **not** “everyone sees everything.” Each account has a role, a designation, and **per-module flags**. Tickets are further limited to the people on that ticket or project. Documents in DocHub can be limited per person.

---

## 3. How people use it

Kynvera Operations is a **web application**. People use it from:

- A **browser** on office desktops
- A **phone or tablet** (responsive layout, installable as a Progressive Web App)
- An optional **native Android shell** (Capacitor) where a wrapped app is required

There is one sign-in. After login, the **dashboard** shows only the modules that person may open. Field capture (photos, signatures, forms) is designed for phones; review, reporting, and administration are comfortable on desktop.

Notifications, email, and scheduled jobs keep work moving when someone is not looking at the screen.

---

## 4. How a typical day flows

```text
Sign in
   → Dashboard (only permitted modules)
      → Capture work in a module (form, ticket, HR request, PR, …)
         → Workflow / supervisor review where the process requires it
            → Signed record + PDF / Excel / letter as needed
               → History, notifications, optional email
```

Nothing commercially binding or client-facing leaves the organisation on assistant say-so. People approve, sign, assign, and close.

---

## 5. Modules — what they do and what they include

Each module below is a real part of the application. People only see a module if an administrator has granted that access (admins see all).

### 5.1 Identity, dashboard, and administration

**What it does.** This is the front door and the control room. People sign in, land on a dashboard of their modules, and administrators manage who can do what.

**Features**

- Username / email and password sign-in; sessions with access and refresh tokens
- Dashboard that hides modules the person cannot use
- User management: create accounts, reset access, set designation and module flags
- Team and device management (who holds which device)
- Knowledge base that feeds the in-app assistant
- Convenience database download for administrators (not a substitute for host backups)
- Security-conscious session handling (logout revokes the session)

**Who uses it.** Everyone signs in here. Administrators live in Administration.

---

### 5.2 Workflow and pending review

**What it does.** Shared review pipeline for inspection (and related) submissions. A form does not “disappear into email.” It sits in a queue with a status, a history, and the next person who must act.

**Features**

- Draft vs submitted records
- Pending Review hub for people who approve
- “My submitted forms” for people who raised the work
- Review history and personal trail
- Multi-stage approval: supervisor → operations manager → business development / procurement (as required) → general manager
- Approve, reject, withdraw, update, and resubmit
- Notifications when a record is waiting

**Who uses it.** Supervisors, operations managers, BD, procurement, and GM — according to designation.

---

### 5.3 Inspections (HVAC & MEP, Civil, Cleaning)

**What it does.** Digital site inspections. Staff fill a structured form on site, attach photos, capture signatures, and submit. The record then follows the workflow above. PDF and Excel packs are generated for the file.

**Features**

- Trade-specific catalogues (HVAC/MEP, Civil, Cleaning)
- Structured fields, photos, and signatures
- Save as draft; submit when complete
- Photo upload (including queued uploads on mobile)
- Background report generation so the phone is not stuck waiting
- Download of generated PDF / Excel against the submission
- Workflow status visible to the next reviewer

**Who uses it.** Site teams capture; supervisors and managers review and sign.

---

### 5.4 Ticketing (work orders)

**What it does.** Live work-order system: create, assign, attend, complete, verify, and close. Tickets carry location, fault type, photos, manpower, materials, costs, and chargeable flags.

**Features**

- Create from the UI, from the assistant (as a **proposal** until confirmed), or from **inbound email** (arrives as a **draft** until a supervisor converts it)
- Status lifecycle: draft → open → assigned → site attended → work started → work completed → verification → close (plus on-hold and cancelled)
- Project / property / zone / sub-zone / base-unit location tree
- Fault catalogue, priority, SLA-oriented fields
- Assign supervisor and technician; supervisor teams
- Photos, notes, manpower entries, materials (including bulk)
- Chargeable flag; supervisor markup before close
- AI **triage preview** (suggested priority / technician / parts) — human must confirm
- PDF, invoice-style, and Excel exports
- Per-ticket visibility (not “all tickets because you have the module”)

**Who uses it.** Anyone with ticketing access, scoped to tickets they are allowed to see. Supervisors own assignment and close.

---

### 5.5 Assets (FM registry)

**What it does.** Equipment register for the estate: what is installed, where it is, how healthy it is, and how to find it in the field.

**Features**

- Asset list, create / edit / retire
- QR codes and printable labels; scan-to-open
- Map pins (GIS)
- 2D digital twin / floor-plan hotspots
- Executive dashboard and KPIs
- Optional remaining-useful-life **estimates** (labelled as estimates, not certified remaining life)
- Integration hooks (API keys / webhooks) for later connectors

**Who uses it.** FM / operations staff who maintain master data; field staff who scan tags.

---

### 5.6 Human resources

**What it does.** Digital HR for operations: forms that used to live as Word files, plus trackers for leave, manpower, and hiring documents. Approval is **employee → HR → General Manager** where the form requires it.

**Forms**

- Leave application
- Commencement
- Duty resumption
- Contract renewal assessment
- Performance evaluation
- Grievance / disciplinary
- Interview assessment
- Passport release & submission
- Staff appraisal
- Station clearance
- Visa renewal
- Asset handover

**Trackers and hiring**

- Leave tracker (including sick trends / planner views)
- Manpower requirement tracker
- Hiring document tracker (candidates and required papers)
- Offer letters (scan and signed copies)

**Other features**

- Pending HR review and GM approval queues
- Replacement / management-chain sign-off when the usual signer is away
- Official **DOCX** from templates and **PDF** layouts
- Notifications on approve / reject
- Daily Excel backup of hiring, leave, and manpower via Automations

**Who uses it.** Staff raise requests; HR reviews; GM signs where required.

---

### 5.7 Procurement

**What it does.** Materials and purchasing for sites: what is stocked, what is low, who supplies it, and which purchase request is in flight.

**Features**

- Materials catalogue (by department)
- Properties and stock assignment; transfer / share stock across properties
- Suppliers
- Purchase requests with approve / reject
- Goods receive against a request
- Low-stock and refill (create a PR from refill)
- Excel import / export and a branded sample workbook
- Usage log and activity
- Document-approve links for stamped paperwork
- Daily materials export via Automations

**Who uses it.** Procurement and operations staff with the procurement flag.

---

### 5.8 QHSI (Quality, Hospitality, Safety & Inspection)

**What it does.** Quality and safety hub alongside trade inspections: staff kit / PPE compliance, training records, and QHSI inspection capture.

**Features**

- Staff compliance import and submit (uniform, PPE, ID, and related kit types)
- Training register (create, update, remove)
- Inspection capture using HVAC / Civil / Cleaning catalogues
- Project list and stats
- Excel import template for compliance

**Who uses it.** QHSI / quality users with the QHSI flag.

---

### 5.9 Report generation (MMR)

**What it does.** Turns CAFM-style Excel / HTML exports into a **Maintenance Management Report**: dashboards, chargeable vs non-chargeable classification, Excel packs, and scheduled email.

**Features**

- Upload current CAFM workbook
- pandas-based processing and **chargeable rules** (policy-driven, not guessed by chat)
- Dashboard KPIs and cycle history
- Download report / monthly pack
- Save to folder or Drive (where configured)
- Email configuration, presets, send now
- Scheduled daily email (default timezone **Asia/Dubai**)
- Pause / resume automation

**Who uses it.** People with report-generation access. Recipients of the email are configured, not implied.

---

### 5.10 Business development

**What it does.** Commercial pipeline and the email module used to send client-facing packs from approved operational records — not from a free-form chatbot.

**Features**

- BD admin shell and pipeline (accounts, status, owners)
- Quotations where the user has the quotations flag
- Email module: attach generated files, cloud files, groups
- Email automations with run history
- Sales-manager view across salespeople when flagged

**Who uses it.** BD and sales-flagged users. Client email is a human action.

---

### 5.11 DocHub

**What it does.** Controlled document library for policies, procedures, and published files that the organisation wants in one place — including as source material for the assistant when retrieval is allowed.

**Features**

- Publish / organise documents for authorised users
- Per-user access rows where needed
- In-app viewing and download
- Assistant may cite published titles only if the signed-in user can already see them

**Who uses it.** Administrators publish; authorised staff read.

---

### 5.12 Files

**What it does.** In-app file cabinet for exports and uploads (HR backups, procurement workbooks, generated reports). Optional **Google Drive** sync of files **this app created**, not the user’s entire Drive.

**Features**

- Folder tree, upload, rename, delete, download
- Save-from-module (other modules drop exports here)
- HR / module templates download
- Optional Drive connect (user consents); sync folder or item
- Works fully **without** Drive

**Who uses it.** Users with Files access; HR also uses it as the landing place for automated backups.

---

### 5.13 Automations

**What it does.** Scheduled operational jobs so backups and exports happen even if nobody clicks Export that day.

**Features (implemented jobs)**

- HR daily Excel backup (hiring, leave, manpower) + optional screen PDFs; save to Files; email; Drive if connected
- Procurement daily materials Excel
- Devices export
- Technicians export
- Linked view of MMR daily Excel (owned by Report Generation)

Schedules default to evening **Asia/Dubai**. Recipients are configured per job.

**Who uses it.** Admins and HR (automations hub access).

---

### 5.14 In-app assistant

**What it does.** A grounded assistant inside the application. It answers from **live records the signed-in user may already see**, plus approved FAQs / knowledge / DocHub. It can **propose** creating a ticket or a leave draft. A person must **Confirm**. It cannot approve forms, close tickets, send email, or change payroll.

**Features**

- Natural-language questions over tickets, leave, pending forms, FM stats (when allowed)
- Cited answers or an honest “I don’t have that”
- Confirm cards for writes
- Works with the organisation’s chosen model (cloud, private compatible endpoint, or **off**)
- When the model is off, the rest of Kynvera Operations continues; the assistant falls back to simpler replies

**Who uses it.** Signed-in users. It never impersonates another person.

---

### 5.15 Devices

**What it does.** Track organisation devices (tablets / phones) assigned to people — useful for MDM-style operational control of who holds what.

**Features**

- Device register, status, assignment
- Daily devices export via Automations

**Who uses it.** Administrators.

---

## 6. How the pieces fit together

Kynvera Operations is built as a **modular monolith**: many modules, one application, one database, one sign-in.

```text
People (browser / PWA / Android shell)
        │
        ▼
   Kynvera Operations  ── RBAC, workflow, audit
        │
        ├── PostgreSQL     (records, users, knowledge, audit)
        ├── Redis          (rate limits / optional job queue)
        ├── Files on disk  (generated reports, local uploads)
        ├── Cloudinary     (production photos / signatures)
        ├── Email          (notifications, MMR, automations)
        └── Optional Drive (only files this app created)
```

**Field modules** (inspections, tickets, QHSI, assets) create structured records.  
**Workflow and HR chains** move those records through people.  
**Procurement, BD, MMR, Files, DocHub** sit on the same identity and storage.  
**The assistant** reads through the same permissions; it does not get a back door.

---

## 7. What stays with people

Automation is used for **capture, filing, routing, and drafting**. People remain responsible for:

- Approving and signing forms
- Converting email-intake drafts into live tickets
- Applying or overriding triage suggestions
- Setting markup and closing tickets
- HR and GM sign-off
- Client-facing wording and commercial decisions
- Connecting their own Google account if Drive sync is used

That split is intentional. Kynvera Operations speeds operations without unsupervised writes.

---

## 8. Where to read next

| Document | Use it when |
|----------|-------------|
| [Module Architecture](Kynvera_Operations_Architecture.md) | You need how each module is structured and how work streams through it |
| [Security, Scale & Continuity](Kynvera_Operations_Security_Scale_Continuity.md) | You need security, growth, backup, and prepared answers for client questions |

---

*Kynvera Operations — Operations Application*  
*August 2026*
