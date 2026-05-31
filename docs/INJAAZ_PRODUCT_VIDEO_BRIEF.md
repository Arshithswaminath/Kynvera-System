# Injaaz Application — Product Video Brief

> **Purpose:** Single source document for marketing, stakeholders, and AI/cloud video tools.  
> **Use this file to:** understand the product, collect screenshots, write voiceover, and generate an animated explainer video.

---

## Table of contents

1. [What is Injaaz? (Company)](#1-what-is-injaaz-company)
2. [What is Injaaz Application? (Product)](#2-what-is-injaaz-application-product)
3. [Who is it for?](#3-who-is-it-for)
4. [Platform capabilities (cross-cutting)](#4-platform-capabilities-cross-cutting)
5. [Modules & features (detailed)](#5-modules--features-detailed)
6. [Workflow & approvals](#6-workflow--approvals)
7. [Administration & security](#7-administration--security)
8. [Our team & credibility](#8-our-team--credibility)
9. [Brand & visual guidelines (for video)](#9-brand--visual-guidelines-for-video)
10. [Screenshot & asset checklist](#10-screenshot--asset-checklist)
11. [Voiceover script (90 seconds)](#11-voiceover-script-90-seconds)
12. [Scene storyboard](#12-scene-storyboard)
13. [Master AI video generation prompt](#13-master-ai-video-generation-prompt)
14. [Short prompts (social cuts)](#14-short-prompts-social-cuts)

---

## 1. What is Injaaz? (Company)

**Injaaz Facilities Management** is a UAE-based facilities management (FM) company delivering end-to-end building and operations services across multiple sectors.

| Attribute | Detail |
|-----------|--------|
| **Industry** | Facilities Management (FM) |
| **Region** | United Arab Emirates (UAE) |
| **Experience** | 15+ years |
| **Projects completed** | 500+ |
| **Team size** | 50+ expert team members |
| **Service lines** | 16 (HVAC, cleaning, security, landscaping, pest control, contract management, engineering, MEP, and more) |
| **Sectors served** | Pharmaceutical, public sector, logistics, defence, industrial, healthcare |
| **Compliance** | QHSE-aligned processes; international health, safety, and environment standards |

**Company tagline (About page):**  
*Facilities Management done right.*

**Company values:** Excellence · International standards · Diverse expertise · Innovation · Partnership · Reliability

Injaaz FM serves clients who need reliable, compliant, and scalable operations — from routine maintenance to complex multi-site contracts.

---

## 2. What is Injaaz Application? (Product)

**Injaaz Application** is Injaaz’s **in-house web platform** that connects every part of how the organisation works — inspections, HR, procurement, ticketing, reporting, documents, and leadership visibility — in **one secure system**.

| Attribute | Detail |
|-----------|--------|
| **Product name** | Injaaz Application |
| **Product tagline** | **All Operations. One Platform.** |
| **Type** | Web application (PWA-capable; mobile-friendly; optional Capacitor mobile shell) |
| **Built for** | Supervisors, technicians, operations managers, HR, procurement, business development, and general management |
| **Problem it solves** | Replaces scattered spreadsheets, emails, and paper forms with guided digital workflows and audit-ready records |
| **Platform built by** | Arshith Swaminath P (internal development) |

**One-line pitch:**  
Injaaz Application is the digital backbone of Injaaz FM — one login, role-based modules, mobile-friendly forms in the field, and clear approval chains from submission to sign-off.

**Elevator pitch (30 seconds):**  
Facilities teams move fast — on site, in review, and in the back office. Injaaz Application brings inspections, HR, procurement, service tickets, and reporting into a single platform. Field staff capture data on mobile. Reviewers approve with signatures and full history. Leadership sees what’s pending today, not at month-end. Less admin. More service. All operations. One platform.

---

## 3. Who is it for?

| Role | Typical use |
|------|-------------|
| **Technician / field staff** | Submit inspection forms, HR requests, site data from mobile |
| **Supervisor** | First-line review and sign-off on team submissions |
| **Operations manager** | Workflow approvals, operational oversight |
| **Procurement** | Material lists, pricing, procurement workflows |
| **HR / HR manager** | Leave, termination, asset, visa, appraisal, and clearance forms |
| **Business development** | Pipeline, projects, contacts, BD email notifications |
| **General manager** | Final approvals, visibility across departments |
| **Administrator** | Users, teams, module access, devices, audit |

Access is **role- and module-based** — each user sees only what they need on the dashboard.

---

## 4. Platform capabilities (cross-cutting)

These apply across all modules:

| Capability | Description |
|------------|-------------|
| **Secure authentication** | Login with username or email; JWT-based sessions; password management and profile |
| **Role-based dashboard** | Personalised home screen showing only permitted modules |
| **Mobile-responsive UI** | Touch-friendly forms (44px targets), works on phones and tablets on site |
| **PWA support** | Installable app experience; theme colour `#125435` |
| **Digital signatures** | Signature pads on forms; default signature and approval comments saved to profile |
| **Photo & file attachments** | Capture site photos and upload documents on forms |
| **Draft & submit** | Save drafts; complete and submit when ready |
| **Workflow routing** | Submissions route to the correct reviewer by designation and rules |
| **Pending reviews hub** | Reviewers see everything awaiting their action in one place |
| **Submitted forms hub** | Users track their own HR and inspection submissions and status |
| **Workflow history** | Full audit trail of who approved, when, and with what comment |
| **PDF / Excel output** | Professional reports and exports from inspection and MMR data |
| **DocHub** | Central document repository for authorised users |
| **Administration** | User creation, team management, module permissions, device enrolment |
| **Notifications & email** | Automated emails (e.g. scheduled MMR reports, BD GM notifications) |

---

## 5. Modules & features (detailed)

### 5.1 Inspection forms (HVAC & MEP · Civil · Cleaning)

**Dashboard entry:** Inspection Form  
**Routes:** `/inspection`, `/hvac-mep`, `/civil`, `/cleaning`

| Feature | Detail |
|---------|--------|
| **Unified inspection hub** | One entry point for HVAC & MEP, Civil Works, and Cleaning Services |
| **Structured site forms** | Project info, visit date, areas, work descriptions, checklists |
| **Materials tracking** | Materials used sections with quantities (HVAC/MEP) |
| **Photo capture** | Multiple photos per submission from mobile |
| **Digital signatures** | Supervisor and reviewer signatures on approval |
| **Supervisor edit & review** | Supervisors can review and amend submissions |
| **Excel / PDF generation** | Professional formatted exports for client and internal records |
| **Workflow integration** | Routes through supervisor → operations → procurement → BD → GM as configured |

**Video highlight:** Technician on site → opens form on phone → photos + signature → submission enters approval chain.

---

### 5.2 HR module

**Dashboard entry:** HR Module  
**Route:** `/hr`

| Form / area | Purpose |
|-------------|---------|
| Leave application / leave form | Annual and other leave requests |
| Long vacation form | Extended leave applications |
| Termination form | Employee separation with clearance checklist |
| Asset form | Company asset issuance and return |
| Commencement form | New joiner / commencement documentation |
| Contract renewal | Contract extension workflow |
| Visa renewal | Visa-related HR processing |
| Passport release | Passport handover / return tracking |
| Duty resumption | Return-to-duty after leave |
| Station clearance | Exit clearance checklist |
| Grievance form | Employee grievance submission |
| Performance evaluation | Staff performance reviews |
| Staff appraisal | Appraisal cycles |
| Interview assessment | Recruitment assessment |
| GM approval | General manager HR approval lane |
| My requests | Employee view of own HR submissions |
| Approved forms | HR approved records |
| Pending review | HR reviewer queue |
| Print / PDF | HR form printing and PDF export |

**Workflow:** Technician submissions often route via assigned supervisor → operations manager → GM → HR, depending on designation.

**Video highlight:** Employee submits leave on mobile → supervisor approves with signature → status updates in “My requests”.

---

### 5.3 Procurement module

**Dashboard entry:** Procurement  
**Route:** `/procurement`

| Feature | Detail |
|---------|--------|
| Material lists | Create and manage material catalogues |
| Quantity tracking | Track quantities per property / project |
| Pricing management | Maintain pricing data |
| Excel import / export | Bulk data via spreadsheets |
| Registered properties | Property register for procurement context |
| Workflow integration | Procurement review lane on inspection submissions |

**Video highlight:** Material list screen → Excel import → linked to inspection/procurement approval.

---

### 5.4 Service tickets (work orders)

**Dashboard entry:** Service tickets  
**Route:** `/tickets`

| Feature | Detail |
|---------|--------|
| Ticket creation | Raise work orders with property, category, priority |
| Assignment | Assign technicians and track ownership |
| Materials on tickets | Link materials and labour to tickets |
| Status pipeline | Open → in progress → closed |
| Fault catalog | Structured fault / category selection |
| Mobile-friendly detail views | Field updates from phone |

**Video highlight:** New ticket → assign technician → close with notes and materials.

---

### 5.5 Report generation (MMR)

**Dashboard entry:** Report Generation  
**Route:** `/admin/mmr`

| Feature | Detail |
|---------|--------|
| CAFM Excel upload | Import maintenance / complaint data from CAFM exports |
| Analytics dashboard | Visualise resolved vs pending complaints |
| Chargeable rules engine | Configurable rules for chargeable vs non-chargeable items |
| Location register | Excel-based location register with per-row toggles |
| Excel & PDF reports | Generate client-ready MMR reports |
| Scheduled email | Automated daily/periodic report emails (Asia/Dubai timezone) |
| Network save paths | Optional save to shared folders |

**Video highlight:** Upload spreadsheet → dashboard charts update → one-click PDF report → scheduled email sent.

---

### 5.6 Business development

**Dashboard entries:** Business Development · Email Module  
**Routes:** `/admin/bd`, `/bd/email-module`

| Feature | Detail |
|---------|--------|
| BD pipeline | Projects, deals, stages, priority, value, progress |
| Contacts & follow-ups | Relationship and next-action tracking |
| Excel import | Import project lists from Excel |
| BD analytics | Pipeline summaries and metrics |
| Email module | Compose GM notifications with custom To/CC |

**Video highlight:** BD dashboard with project cards → deal stage update → email notification composed.

---

### 5.7 DocHub

**Dashboard / admin entry:** DocHub  
**Routes:** `/dochub`, `/api/docs`

| Feature | Detail |
|---------|--------|
| Document upload | Store and organise reference files |
| Access control | Per-user DocHub permission via admin |
| Search & browse | Find policies, templates, and reference documents |
| Inline viewing | View documents in browser where supported |

**Video highlight:** Admin uploads policy PDF → field user finds it in DocHub on mobile.

---

### 5.8 Workflow hubs

| Hub | Route | Who sees it |
|-----|-------|-------------|
| **Pending Review** | `/workflow/pending-reviews` | Reviewers with pending approvals |
| **Submitted Forms** | `/workflow/submitted-forms` | Users tracking their own submissions |
| **Workflow history** | `/workflow/history` | Audit trail of actions on a submission |

---

### 5.9 Site visit & other forms

| Feature | Route | Detail |
|---------|-------|--------|
| Site visit form | `/site-visit` | Structured site visit capture |
| Forms dashboard | `/forms` | Additional form entry points where configured |

---

### 5.10 Admin & people management

**Routes:** `/admin`, `/admin/team-management`, `/admin/devices`

| Feature | Detail |
|---------|--------|
| Admin dashboard | Organisation overview, quick links, user counts |
| Users & teams | Create users, assign designations, reporting managers |
| Manage profile | Identity, HR profile, module access, default signature, password reset |
| Module access flags | HVAC, Civil, Cleaning, HR, Procurement, BD, DocHub, MMR, Tickets, Submitted forms |
| Device management | Enrol and track registered devices |
| Personal progress | Admin personal progress tracking (where enabled) |
| Audit & activity | User activity views from manage profile |

---

## 6. Workflow & approvals

Typical approval chain (varies by form type and designation):

```
Field user submits
    → Supervisor (if technician)
    → Operations Manager
    → Procurement / Business Development (inspection lanes)
    → General Manager
    → HR (HR-specific forms)
    → Approved / archived with PDF
```

**Key messages for video:**
- Every step is logged (who, when, comment, signature).
- Reviewers get a **Pending Review** queue — nothing gets lost in email.
- Submitters see live status in **Submitted Forms** / **My requests**.

---

## 7. Administration & security

| Topic | Detail |
|-------|--------|
| Authentication | JWT access + refresh tokens; secure login |
| Registration | Self-service 3-step signup (personal details → project & role → account ready with default password) |
| Password policy | Strong password rules; admin can reset; users change password in profile |
| Role designations | Supervisor, Operations Manager, BD, Procurement, GM, HR Manager, Technician, Employee, Admin |
| Rate limiting | Login/register rate limits when configured |
| CSRF / headers | Standard web security on form routes |
| Cloud storage | Cloudinary for signatures and media in production |
| Data | SQLite (dev) / PostgreSQL (production) |

---

## 8. Our team & credibility

Use these facts in the video intro or closing card:

| Stat | Label |
|------|-------|
| 15+ | Years experience |
| 500+ | Projects completed |
| 50+ | Expert team members |
| 16 | Service lines |
| 6 | Sectors served |
| 100% | QHSE compliance focus |

**Platform credit (optional end card):**  
*Injaaz Application — built by Arshith Swaminath P*

**Team visual suggestion for AI/video:**  
Diverse FM professionals — supervisors with tablets on site, operations staff at laptops, HR at desk, leadership reviewing dashboard — all in Injaaz green/white brand colours, modern UAE office and high-rise building environments.

---

## 9. Brand & visual guidelines (for video)

| Element | Value |
|---------|--------|
| **Primary green** | `#125435` |
| **Deep green** | `#003b22` |
| **Light surface** | `#f7faf8` |
| **Accent mint** | `#95d5ac` / `#87c79f` |
| **Logo** | Injaaz icon + wordmark (white on green, green on white) |
| **Typography** | Clean sans-serif (SF Pro / system UI style) |
| **Mood** | Professional, trustworthy, modern, operations-focused — not playful |
| **Aspect ratio** | 16:9 (YouTube/website) + 9:16 cut (Instagram/Reels) |
| **Duration target** | 90–120 seconds main; 15s teaser |

**Do:** Show real UI screenshots, green gradients, clean white cards, mobile + desktop.  
**Avoid:** Generic stock “business handshake” clichés; overly dark or neon cyber aesthetics.

---

## 10. Screenshot & asset checklist

Capture these from a **staging or demo account** at **1920×1080** (desktop) and **390×844** (mobile).  
Save under `docs/video-assets/screenshots/` using the filenames below.

| # | Filename | Screen | Notes |
|---|----------|--------|-------|
| 1 | `01-login-desktop.png` | Login page | Split hero + sign-in card |
| 2 | `02-register-step1-desktop.png` | Register wizard step 1 | Personal details |
| 3 | `03-register-step3-desktop.png` | Register wizard step 3 | Account ready |
| 4 | `04-dashboard-desktop.png` | Main dashboard | Module grid visible (admin or mixed role) |
| 5 | `05-dashboard-mobile.png` | Dashboard | Mobile module cards |
| 6 | `06-inspection-hub-desktop.png` | Inspection module chooser | HVAC / Civil / Cleaning |
| 7 | `07-hvac-form-mobile.png` | HVAC form in progress | Photos + fields filled |
| 8 | `08-signature-pad-mobile.png` | Signature on form | Close-up of sign |
| 9 | `09-pending-review-desktop.png` | Pending Review queue | List with badges |
| 10 | `10-workflow-history-desktop.png` | Workflow history | Timeline / audit |
| 11 | `11-hr-dashboard-desktop.png` | HR module home | Form tiles |
| 12 | `12-hr-leave-form-mobile.png` | HR leave form | Partially filled |
| 13 | `13-procurement-dashboard-desktop.png` | Procurement home | |
| 14 | `14-ticket-list-desktop.png` | Service tickets list | |
| 15 | `15-ticket-detail-mobile.png` | Ticket detail | Assignment visible |
| 16 | `16-mmr-dashboard-desktop.png` | MMR / report generation | Charts + data |
| 17 | `17-mmr-report-preview-desktop.png` | Generated report preview | PDF or Excel |
| 18 | `18-bd-pipeline-desktop.png` | Business development | Project table/cards |
| 19 | `19-dochub-desktop.png` | DocHub file list | |
| 20 | `20-admin-team-desktop.png` | Users & Teams | |
| 21 | `21-manage-profile-desktop.png` | Manage profile modal | Identity + modules |
| 22 | `22-about-hero-desktop.png` | About page hero | Optional brand montage |

**Additional assets:**

| Asset | Path suggestion |
|-------|-----------------|
| Logo (PNG, transparent) | `static/icons/INJAAZ Logo - Edited.png` |
| App icon | `static/icons/icon-512x512.png` |
| Optional B-roll | Site footage: technician, building lobby, FM tools (user-provided) |

---

## 11. Voiceover script (90 seconds)

**Tone:** Confident, clear, professional. British or neutral international English. Moderate pace.

---

**[0:00 – HOOK]**  
Facilities management never stops. Teams are on site, supervisors are reviewing, HR is processing requests — and leadership needs answers today.

**[0:10 – PROBLEM]**  
When work lives in spreadsheets, emails, and paper forms, things slip. Approvals slow down. Records are hard to trace. And your best people spend too much time on admin.

**[0:20 – SOLUTION]**  
That’s why Injaaz built **Injaaz Application** — one platform for how we actually operate.

**[0:28 – PLATFORM]**  
One secure login. A personalised dashboard. Only the modules you need — inspections, HR, procurement, service tickets, reporting, and more.

**[0:38 – FIELD]**  
On site, teams use mobile-friendly forms — photos, checklists, and digital signatures — captured in minutes, not hours.

**[0:46 – WORKFLOW]**  
Every submission follows a clear approval path. Supervisors, operations, procurement, and leadership — each step logged with signatures and comments. Nothing lost in an inbox.

**[0:58 – MODULES MONTAGE]**  
HR requests. Procurement lists. Service tickets from open to closed. MMR reports generated and emailed on schedule. Business development pipeline and DocHub — all connected.

**[1:10 – OUTCOME]**  
The result: faster decisions, audit-ready records, and teams focused on delivering exceptional FM service.

**[1:18 – CLOSE]**  
**Injaaz Application.**  
**All Operations. One Platform.**

---

## 12. Scene storyboard

| Scene | Time | Visual | Text on screen |
|-------|------|--------|----------------|
| 1 | 0:00–0:08 | Animated city + building cut; technician walks with tablet | — |
| 2 | 0:08–0:18 | Split screen: messy email/Excel vs clean Injaaz UI | “Too many tools?” |
| 3 | 0:18–0:26 | Logo reveal on green gradient | **Injaaz Application** |
| 4 | 0:26–0:36 | Screenshot: login → dashboard (`01`, `04`) | “One login. Your modules.” |
| 5 | 0:36–0:46 | Mobile: inspection form + signature (`07`, `08`) | “Capture on site” |
| 6 | 0:46–0:56 | Animated workflow diagram + pending review (`09`) | “Guided approvals” |
| 7 | 0:56–1:06 | Quick cuts: HR, procurement, tickets, MMR (`11`, `13`, `14`, `16`) | Module names |
| 8 | 1:06–1:14 | Dashboard stats / team montage | “Built for FM teams” |
| 9 | 1:14–1:22 | Logo end card | **All Operations. One Platform.** |

---

## 13. Master AI video generation prompt

Copy everything inside the block below into your AI video tool (Runway, Pika, Kling, Sora, HeyGen, Invideo AI, etc.). **Attach the screenshots listed in Section 10** where the tool supports image/video references.

```
Create a 90-second professional animated product explainer video for "Injaaz Application" — an enterprise web platform for facilities management (FM) operations in the UAE.

BRAND
- Company: Injaaz Facilities Management
- Product: Injaaz Application
- Tagline: "All Operations. One Platform."
- Primary colour: #125435 (forest green)
- Secondary: white #FFFFFF, light surface #f7faf8, accent mint #95d5ac
- Style: clean, modern SaaS + corporate FM — trustworthy, not playful
- Typography: sans-serif, similar to SF Pro / Inter

AUDIENCE
FM supervisors, technicians, HR, procurement, operations managers, and leadership at Injaaz and similar FM organisations.

NARRATIVE ARC
1. Open on fast-paced FM environment (technician in building, supervisor with tablet).
2. Problem: scattered spreadsheets, email threads, paper forms — chaos montage (abstract, not negative).
3. Solution reveal: Injaaz Application logo on green gradient.
4. Show product UI (USE ATTACHED SCREENSHOTS as screen-in-device mockups):
   - Login and dashboard
   - Mobile inspection form with photo upload and signature pad
   - Pending review / workflow approval queue
   - HR module, procurement, service tickets, MMR reports dashboard
5. Explain workflow: submit → supervisor → operations → approval → audit trail.
6. Close with team credibility: "15+ years | 500+ projects | 50+ experts | 16 service lines"
7. End card: Injaaz logo + "All Operations. One Platform." + injaaz.com (if applicable)

ANIMATION STYLE
- Smooth 2.5D motion graphics
- UI screenshots animate inside laptop and iPhone device frames
- Subtle parallax on green gradient backgrounds
- Animated connector lines for workflow diagram (nodes: Submit → Review → Approve → Archive)
- Light particle/dot texture on green panels (subtle, professional)
- Transitions: soft cross-dissolve and slide-up (no flashy spins)

MUSIC & VOICE
- Background: light corporate ambient, uplifting, no vocals
- Optional voiceover: clear neutral English male or female, professional FM/tech tone
- Use the voiceover script provided in the project brief document

TEAM & PEOPLE (B-roll suggestions if generating live action)
- Diverse FM team in UAE office and on site
- Supervisor reviewing tablet on building floor
- HR coordinator at desk
- Operations manager viewing dashboard on monitor
- Wear professional work attire; hard hats where on active sites

TEXT OVERLAYS (minimal)
- "All Operations. One Platform."
- "Inspections · HR · Procurement · Tickets · Reports"
- "Guided workflows · Full audit trail"
- "Mobile-ready · Secure · Built for FM"

TECHNICAL SPECS
- Duration: 90 seconds
- Resolution: 1920×1080, 30fps
- Also export 9:16 vertical cut from key scenes for social media

ATTACHED REFERENCE FILES (insert your screenshots)
- 01-login-desktop.png
- 04-dashboard-desktop.png
- 07-hvac-form-mobile.png
- 09-pending-review-desktop.png
- 11-hr-dashboard-desktop.png
- 14-ticket-list-desktop.png
- 16-mmr-dashboard-desktop.png
- Logo PNG (white and green versions)

DO NOT
- Use generic stock "business handshake" clichés
- Use colours outside the green/white brand palette
- Show fake UI that contradicts the attached screenshots
- Make it look like a gaming app or consumer social app
```

---

## 14. Short prompts (social cuts)

### 15-second teaser

```
15-second vertical video ad. Injaaz Application — FM operations platform. Open on technician with tablet on site. Quick flash of dashboard, mobile form, approval tick. Green #125435 brand. Text: "All Operations. One Platform." Professional, UAE corporate FM aesthetic. 9:16.
```

### 30-second module montage

```
30-second product montage for Injaaz Application. Sequence: login → dashboard module cards → mobile inspection with signature → pending approvals → HR form → service ticket closed → MMR chart. Forest green #125435 and white UI. Device mockups. Upbeat corporate music. End logo.
```

---

## Appendix — Key URLs (for screenshot capture)

| Page | URL path |
|------|----------|
| Login | `/login` |
| Register | `/register` |
| Dashboard | `/dashboard` |
| About | `/about` |
| Inspection hub | `/inspection` |
| HR | `/hr` |
| Procurement | `/procurement` |
| Tickets | `/tickets` |
| MMR / Reports | `/admin/mmr` |
| BD admin | `/admin/bd` |
| DocHub | `/dochub` |
| Pending reviews | `/workflow/pending-reviews` |
| Submitted forms | `/workflow/submitted-forms` |
| Admin | `/admin` |
| Team management | `/admin/team-management` |

---

*Document version: 1.0 — for Injaaz Application product video production. Update when modules or branding change.*
