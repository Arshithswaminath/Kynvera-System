# Amaan Systems — Client Demo User Guide

**All Operations. One Platform.**

Welcome to the **Amaan** operations platform. This guide is designed for client demos and first-time users. It explains what the application does, how to navigate it, and how to walk through the main modules during a presentation.

---

## 1. What Is Amaan?

Amaan is a unified **facilities and operations management** platform used by AMAAN LLC for fire protection, fire-fighting, security systems, and facility operations across Dubai and Ajman.

It brings everyday operational work into one place:

| Area | What you can do |
|------|-----------------|
| **Inspections** | Digital fire-system inspections with photos, signatures, and multi-stage approval |
| **HR** | Leave, appraisals, visa/passport, clearance, and other staff request forms |
| **Service tickets** | Work orders from creation through site work, review, finance, and invoicing |
| **Store** | Materials catalog used on jobs and properties |
| **Operations** | Overtime, trading invoices, clients, and cheque preparation |
| **Finance** | Contracts, invoice queue, costing, and monthly reports |
| **Sales** | Project pipeline, follow-ups, and contacts |
| **DocHub** | Shared company document library |
| **Admin** | Users, access rights, devices, and email automation |

Branded PDF and Excel outputs are available across HR, inspections, work orders, invoices, cheques, and finance reports.

---

## 2. Getting Started

### 2.1 Access the application

1. Open the demo URL provided by your Amaan contact (or `http://localhost:5000` for a local demo).
2. You will be taken to the **Login** page.
3. Enter the credentials supplied for the demo session.
4. After login, you land on the **Home Dashboard**.

> **Note:** Module tiles and menu items depend on the access rights assigned to your account. Admin users see all modules; other users see only what they are permitted to use.

### 2.2 Home dashboard

The dashboard is your starting point. It shows:

- Personalized welcome and quick stats
- Module cards (HR, Inspection, Service Tickets, Operations, Finance, Store, Sales, DocHub, Admin, and more)
- Notifications and to-do items where configured

Click any module card to open that area of the system.

### 2.3 Main navigation

From the top navigation you can typically reach:

| Menu item | Purpose |
|-----------|---------|
| **Home** | Return to the dashboard |
| **Inspection Module** | Fire-system inspections and related tools |
| **HR Forms** | HR request forms and approval hubs |
| **Submitted forms** | Your submitted HR or inspection forms |
| **About** | Company information |
| **Profile** | Your account details |
| **Logout** | End the session |

Admin users may also see **Administrative** and **Email Automation**.

---

## 3. Suggested Demo Walkthrough

Use this order for a clear 20–40 minute client demo.

| Step | Module | Focus |
|------|--------|--------|
| 1 | Login & Dashboard | Role-based home screen |
| 2 | Inspection | Fire-system form → pending review |
| 3 | HR | One request form → HR / GM approval path |
| 4 | Service Tickets | Create a work order → materials → PDF |
| 5 | Operations | Trading invoice or cheque PDF |
| 6 | Finance | Contracts and monthly report |
| 7 | Store | Materials linked to work |
| 8 | Sales | Pipeline and follow-ups |
| 9 | DocHub & Admin | Documents and user access |
| 10 | About | Branding close |

---

## 4. Module Guides

### 4.1 Inspection

**Path:** Dashboard → **Inspection** → `/inspection/`

**Purpose:** Capture field inspections digitally, with evidence and approvals.

**What to show in a demo**

1. Open **Inspection**.
2. Select **Fire-System Inspection**.
3. Walk through checklist sections (alarms, sprinklers, pumps, extinguishers, emergency lighting, smoke control, and related systems).
4. Attach photos and capture signatures.
5. Submit the form.
6. Open **Pending Review** to show how supervisors and managers approve or reject.
7. Download the signed inspection / service-style PDF.

**Approval flow (typical)**

Supervisor → Operations Manager → Business Development & Procurement (in parallel) → General Manager

Also available from Inspection: **Civil Defense Notifications**.

---

### 4.2 HR Forms

**Path:** Dashboard → **HR Forms** → `/hr/`

**Purpose:** Digitize staff requests and HR processes with review and PDF/DOCX output.

**Common forms**

- Leave application  
- Commencement  
- Duty resumption  
- Contract renewal  
- Performance evaluation  
- Staff appraisal  
- Grievance / disciplinary  
- Interview assessment  
- Passport release / submission  
- Visa renewal  
- Station clearance  
- Asset handover / takeover  

**What to show in a demo**

1. Open the HR dashboard.
2. Choose a simple form (for example **Leave Application**).
3. Fill required fields, add signatures where prompted, and submit.
4. Show the workflow hubs:
   - **My Requests**
   - **Pending HR Review**
   - **GM Final Approval**
   - **Approved Forms**
5. Download a branded PDF (and DOCX where available).

---

### 4.3 Service Tickets (Work Orders)

**Path:** Dashboard → **Service Tickets** → `/tickets/`

**Purpose:** End-to-end job management — from request to site work, review, finance, and invoice.

**Typical ticket lifecycle**

Open → Assigned → Site Attended → Work In Progress → Work Completed → Supervisor Review → Pending GM Approval → Pending Finance → Closed  

Tickets may also be placed **On Hold** or **Cancelled**.

**What to show in a demo**

1. Open the ticketing dashboard (queue KPIs and open work).
2. Create a new work order (client/site, fault, assignment).
3. Assign supervisor / technician.
4. Add site notes, images, manpower, and materials from the store.
5. Progress the ticket through key statuses.
6. Generate:
   - Work order PDF  
   - Service report PDF  
   - Invoice PDF  
7. Optionally open **Analytics** and **Reports** (work orders, financial, projects, team, materials).

**Settings** (admin / authorized users): projects, locations, fault catalog.

---

### 4.4 Store

**Path:** Dashboard → **Store** → `/store/`

**Purpose:** Maintain materials used on properties and work orders.

**What to show in a demo**

1. Browse the materials catalog (quantities and pricing).
2. Show property / department assignment where configured.
3. Demonstrate Excel import/export if useful for the audience.
4. Link back to a ticket to show materials consumed on a job.

---

### 4.5 Operations Hub

**Path:** Dashboard → **Operations** → `/operations/`

| Sub-module | What it does |
|------------|--------------|
| **Over Time** | Log overtime; Excel import/export; cost calculation |
| **Trading Invoices** | Material sales invoices with branded PDF |
| **Clients** | Customer master data for invoicing |
| **Cheque Preparation** | Cheque request lifecycle with email alerts |
| **Email Automation** | Scheduled report emails (daily / weekly / monthly / custom) |

**What to show in a demo**

- Create or open a **trading invoice** and download the PDF, **or**
- Walk a **cheque** through request → verify → approve → prepare → submit.

---

### 4.6 Finance & Invoicing

**Path:** Dashboard → **Finance & Invoicing** → `/finance/`

**Purpose:** Commercial control for contracts, job costing, and monthly finance reporting.

**Sidebar areas**

- Invoice Queue  
- Contracts  
- Monthly Reports  
- Invoice Processing  
- Service Tickets  
- Settings  

**What to show in a demo**

1. Open **Contracts** (create/edit or Excel import).
2. Show the **Invoice Queue** and link to service tickets.
3. Run or open a **Monthly Report** and export PDF/Excel.
4. Briefly show costing / invoice processing if relevant to the audience.

---

### 4.7 Sales (Business Development)

**Path:** Dashboard → **Sales** → `/admin/bd`

**Purpose:** Track commercial opportunities and client engagement.

**What to show in a demo**

1. Open **All Projects** or the **Pipeline** view.
2. Create or open a deal and move it across stages.
3. Add a **follow-up** and a **contact**.
4. Mention proposals and Excel import where configured.
5. Highlight KPIs for leadership visibility.

---

### 4.8 DocHub

**Path:** Dashboard → **DocHub** → `/dochub`

**Purpose:** Central library for company documents and shared collections.

**What to show in a demo**

1. Browse collections.
2. Upload or open a shared document.
3. Explain that access can be granted per user.

---

### 4.9 Workflow & Submitted Forms

| Page | Purpose |
|------|---------|
| **Pending Review** | Queue of forms awaiting signature / approval |
| **Submitted forms** | Personal view of HR or Inspection submissions |

Use these pages to demonstrate that nothing is “lost in email” — every submission has a clear review path and history.

---

### 4.10 Administrative

**Path:** Dashboard → **Administrative** → `/admin/dashboard` *(admin only)*

**What administrators manage**

- Users and module access flags  
- Designations (e.g. Supervisor, Operations Manager, HR Manager, Finance, General Manager)  
- Team management and personal progress views  
- Device management  
- Email notifications  
- Knowledge base for the in-app assistant  

**What to show in a demo**

1. Open a user record.
2. Toggle module access (HR, Ticketing, Finance, Operations, etc.).
3. Explain that the dashboard only shows modules the user is allowed to use.

---

### 4.11 Amaan Live Assistant

Where enabled, the in-app assistant can answer common how-to questions and help users find the right screen or process using live context.

---

## 5. Roles & Access (Demo Talking Points)

| Concept | Client-friendly explanation |
|---------|-----------------------------|
| **Admin** | Full platform access and user/module configuration |
| **Standard user** | Access only to assigned modules |
| **Designations** | Control who reviews and approves (Supervisor, Ops Manager, BD, Procurement, GM, HR Manager, Finance) |
| **Module flags** | Fine-grained access: HR, Inspection, Tickets, Store, Operations, Finance, Sales, DocHub, Email Automation |

This means field staff, supervisors, HR, finance, and leadership each see a tailored, secure workspace.

---

## 6. Documents & Reports You Can Generate

| Domain | Typical outputs |
|--------|-----------------|
| **HR** | Form PDFs and DOCX downloads |
| **Inspection** | Inspection PDF; signed workflow PDF |
| **Service Tickets** | Work order, service report, and invoice PDFs; operational report packs |
| **Operations** | Trading invoice PDF; cheque PDF |
| **Finance** | Monthly finance report (PDF and Excel) |
| **Email Automation** | Scheduled Excel/email packages |

All major client-facing PDFs use Amaan branding.

---

## 7. Tips for a Smooth Demo

1. **Use a prepared account** with the modules you plan to show already enabled.
2. **Have sample data ready** — one open ticket, one pending inspection, one HR request, one contract.
3. **Show one full path end-to-end** (for example: ticket → materials → service report PDF) rather than opening every screen.
4. **Highlight approvals** — Pending Review and GM/Finance gates are strong differentiators versus paper or email processes.
5. **Download one PDF live** — clients remember branded documents.
6. **Keep Admin brief** — enough to show control and security, then return to operational value.

---

## 8. Support During the Demo

| Need | Action |
|------|--------|
| Cannot see a module | Confirm module access on the user in Admin |
| Form stuck in review | Check **Pending Review** and the user’s designation |
| PDF missing branding | Confirm you are on the Amaan application build |
| Login issues | Verify demo credentials and that the session has not expired |

For product questions outside the live demo, contact your Amaan representative or visit [www.amaan.ae](https://www.amaan.ae).

---

## 9. About Amaan

**AMAAN LLC** delivers fire protection, fire-fighting, and security systems solutions, with facility management and operations support across Dubai and Ajman.

This platform is the digital backbone for that work — inspections, workforce requests, field jobs, materials, finance, and sales — in one secure system.

---

*Document version: Client Demo User Guide — July 2026*  
*Product: Amaan Systems / Amaan Facility Management*
