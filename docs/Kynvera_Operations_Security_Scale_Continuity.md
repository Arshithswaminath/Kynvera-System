# Kynvera Operations — Security, Scale & Continuity

**Kynvera Operations Application**  
How the system is protected, how it grows with more people and more work, and how it is restored if something fails.

Companion documents:

- [Overview](Kynvera_Operations_Overview.md) — what the application is
- [Module Architecture](Kynvera_Operations_Architecture.md) — how modules are designed

The last section of this document is a **prepared Q&A**: the kind of questions a client typically asks in a review meeting, with answers you can stand behind. The questions are surface-level (business and operations), not a penetration-test script.

---

## 1. Security — what we actually do

Security here is not a slogan. It is a set of controls that match how facilities work is really used: many people, mixed seniority, photos from site, HR files, and commercial figures that must not leak sideways.

### 1.1 Who can get in

- People sign in with **their own account** (username or email and password).
- Passwords are **hashed** (not stored as readable text).
- After sign-in, the browser holds a **session**. Logging out **ends that session** so a leftover tab or stolen cookie is not enough to keep working.
- Login is **rate-limited** so password guessing is slow and noisy, not unlimited.
- Production traffic is expected to run over **HTTPS** (TLS at the reverse proxy), with **HSTS** so browsers keep using HTTPS.

### 1.2 Who can see what

Access is layered on purpose:

| Layer | Meaning in practice |
|-------|---------------------|
| **Account** | You must be a signed-in user. |
| **Module flags** | HR, tickets, procurement, reports, and so on are switched on **per person**. |
| **Designation** | Supervisor, operations manager, HR, GM, and others see the **right queues**. |
| **Record rules** | A ticket is not visible to “everyone in Ticketing.” It is visible to the people on that ticket or project. DocHub can be limited per person. |
| **Admin** | Administrators manage users and flags. That is an application role — not Global Admin on Microsoft 365. |

Revoking a module flag **immediately** stops new access to that module. There is no overnight “sync to five other products.”

The in-app assistant is **not** a back door. It only reads what the signed-in person can already see. If it wants to create a ticket or a leave draft, it **asks for Confirm**. It cannot approve forms, close tickets, send email, or touch payroll.

### 1.3 How data is handled in transit and at rest

- Pages and APIs travel over **TLS** in production.
- Browser **security headers** reduce common web risks (clickjacking, content-type sniffing, referrer leakage, unnecessary browser features). Content Security Policy can be tightened to enforce mode after a clean report-only period.
- Authenticated HTML is **not cached** in a way that the Back button can restore a logged-in page after logout.
- **Secrets** (database URL, JWT keys, mail keys) live in the host’s environment or secret store — **never in git**.
- Uploaded file names are **sanitised** so a file cannot walk out of its folder.
- Production **photos and signatures** go to a contracted media service (Cloudinary) or stay on disk in development. Highly sensitive HR and commercial files are intended to stay **in-app / DocHub** unless policy explicitly allows Drive.

### 1.4 What leaves the organisation (and what does not)

Kynvera Operations is designed so **operational records stay in your database and approved stores**.

Cloud services are **named, optional or required, and allow-listed** — not a silent dump of the whole estate:

| Path | What goes out | What does not |
|------|----------------|---------------|
| **Email** | Notifications, MMR packs, automation attachments you configured | The whole ticket table, password hashes |
| **Media host** | Photos / signatures for that upload | HR tracker databases |
| **Optional Drive** | Files **this application created** in its own folder | The user’s entire Google Drive |
| **Optional AI model** | That question plus the **snippets** retrieved for it | Bulk HR, full CAFM workbooks, secrets |

The organisation **chooses** the model: approved cloud, a private compatible endpoint, or **off**. With the model off, inspections, tickets, HR, and workflow continue.

### 1.5 How we build and run it

- Dependencies are **pinned** for production.
- The container runs as a **non-root** user where Docker is used.
- Material actions (login, approvals, ticket close, and similar) can be **audited**.
- We do **not** claim a default ISO or SOC 2 certificate or a packaged third-party pen-test report. A **VAPT under the client’s process** is a reasonable production gate; findings are fixed by severity and retested.

### 1.6 What we do not do

- We do **not** ask for Microsoft 365 Global Administrator or Graph-wide mail/files access.
- We do **not** put WhatsApp in the product.
- We do **not** let the assistant invent costs, SLA hours, or ticket IDs.
- We do **not** train a private copy of the client’s data into a foundation model as part of this product. Knowledge lives in **your** database (FAQs, DocHub, live records).

---

## 2. Scale — more people, more sites, more traffic

“More manpower” in this product means **more signed-in users, more tickets, more photos, more reports** — not a wider grant of someone else’s cloud tenant.

### 2.1 What the current shape is built for

Kynvera Operations is a **single application** with parts that can be sized independently:

| Part | Role when load grows |
|------|----------------------|
| **Web workers** | More Gunicorn workers / threads for more simultaneous clicks |
| **PostgreSQL** | Managed or larger instance as records and concurrent queries grow |
| **Redis** | Rate limits and optional job queue — keeps abuse and bursts in check |
| **Job worker** | PDF, Excel, MMR, and photo-heavy work off the interactive web process |
| **Media** | Cloudinary (or equivalent) so the app server is not the photo CDN |
| **Disk** | Persistent volume for generated reports (`GENERATED_DIR`) |

A **reference** production host is on the order of **2–4 vCPU, 8 GB RAM minimum / 16 GB recommended, 100 GB+ SSD** for generated files. **No GPU** is required. The language model, if used, runs at the approved API or at the organisation’s own endpoint.

On that class of machine, a **typical FM operations team** (tens of people using the app at once) is the honest working assumption. Heavy PDF/Excel generation and large photo packs are the first things to size up — not “the chatbot.”

### 2.2 How we grow without a rewrite

Scale is **staged**, not “one giant prompt”:

1. **More people on the same site** — add users, flags, and projects in Administration. The application already isolates tickets and modules.
2. **More concurrent use** — raise web workers; keep Redis in front of login and API budgets.
3. **More documents and photos** — persistent disk + media host; report jobs with retries rather than one request that times out.
4. **More sites / contracts** — more projects, properties, and location trees in Ticketing and Assets; same product.
5. **Heavier reporting** — dedicated worker for MMR and Excel; do not run month-end packs on the only web process.

Local load testing exists as a **harness** (synthetic users and tickets). It is for finding slow lists and N+1 queries before go-live. **Production capacity is confirmed in a scoped pilot** on the real host, because photo volume and report jobs dominate more than “page views.”

### 2.3 What happens when something is busy or down

The product is designed to **degrade**, not freeze the whole operation:

| If this fails | People can still |
|---------------|------------------|
| AI model | Use forms, tickets, HR, workflow. Assistant says it is unavailable or uses a simple fallback. |
| Media host | Existing records remain. New photo uploads fail until it returns. |
| Email | Work continues in the app. Notifications and scheduled packs are delayed; failures are visible. |
| Drive | **Files in the app still work.** Sync waits. |
| Redis | Application can still run; rate limiting is weaker. |
| One module | Other modules can still load (fail-soft import). Fix the broken module; do not wait for a full outage. |
| Application VM | Redeploy the same release and restore the database + disk (see below). |

### 2.4 Manpower in the *business* sense

Adding technicians and supervisors is an **administration task**: create the account, set designation, tick the modules, put them on the right project or supervisor team. The architecture does not require a new server per extra person. What *does* grow with headcount is **ticket volume, photo volume, and concurrent sessions** — which is why workers, Postgres, and the job process are the knobs, not a new product per crew.

---

## 3. Backup and the recovery plan

There is **no separate “trained AI brain”** to back up. Memory of the operation is **PostgreSQL** (users, tickets, forms, knowledge, audit, pending assistant actions) plus **files on disk** and **media in Cloudinary**. Restore those, and the application is the organisation again.

### 3.1 What must be backed up

| What | Why it matters | Typical method |
|------|----------------|----------------|
| **PostgreSQL** | The system of record | Provider automatic backups / point-in-time recovery **and** periodic `pg_dump` you control |
| **Generated files / local uploads** | MMR packs, exports, some uploads | Persistent disk or block-volume **snapshots** |
| **Cloudinary (production media)** | Site photos and signatures | Provider redundancy + the contracted account |
| **Application release** | Code and prompts | Git tag / container image — **redeploy**, do not “restore from memory” |
| **Secrets** | Database URL, JWT keys, mail, media | Host secret store — never from a zip in email |

The in-app **Administration → Database → Download a copy** is a **convenience** for admins. It is not the disaster-recovery plan.

### 3.2 Cadence we recommend

- **Before any import or migration into live:** take a dump or snapshot first. Always.
- **Live database:** follow the host’s backup schedule (daily at minimum; PITR where the plan allows). Keep an extra logical dump you can restore elsewhere.
- **Disk:** snapshot on the same rhythm as the database, or immediately before a major release.
- **After a release:** confirm the app version in git/image so you can redeploy that exact build.

Environments stay **separate**. The laptop must not point at the live database for everyday work.

### 3.3 If the application server dies

1. Provision or reboot the host (or roll the container).
2. Restore **PostgreSQL** from the latest good backup (or PITR).
3. Attach or restore the **persistent disk** for generated files.
4. Put **secrets** back from the secret store.
5. Redeploy the **known application version**.
6. Confirm login, a ticket, an HR form, and a generated file path.

Configuration and “what the assistant knows” come back with the **database**. Agent behaviour comes back with the **code**. There are no model weights of client data to reload.

### 3.4 If a person deletes the “only Excel”

HR leave, manpower, and hiring boards are **in the application**. Automations are built to drop **daily Excel copies** into Files (and email / Drive if configured). That is the operational backup for tracker workbooks — still secondary to PostgreSQL.

### 3.5 Ownership

**You own the backups.** Knowledge, FAQs, audit logs, and pending actions are in your database. There is no vendor-side fine-tune of the estate that you would have to beg back.

---

## 4. Questions a client may ask — and the answers

These are **surface-level** questions: the ones that come up in a steering meeting, an IT intro call, or a go-live review. Answers are written so they can be spoken as-is.

### Q1. What is Kynvera Operations, in one sentence?

It is the operations application where your people capture inspections and work orders, run HR and procurement, file documents, and produce reports — with one sign-in, clear permissions, and a record of who approved what.

### Q2. Are we replacing our finance system / CAFM / Microsoft 365?

No. Kynvera Operations is the **operations backbone**. It works **with** CAFM file exports, email, and (optionally) Google Drive. Payroll, ERP, and Microsoft 365 stay yours. We do not ask for Global Admin on Microsoft.

### Q3. Will our staff data and site photos sit on a public chatbot?

No. Records live in **your** database and approved file stores. If you use a language model, only **that question and the short excerpts needed to answer it** are sent — never a bulk dump of HR or tickets. You can also turn the model **off**; the rest of the application keeps running.

### Q4. Who can see a ticket or an HR form?

Only people who are **signed in**, have the **right module**, and (for tickets) are **on that ticket or project**. HR follows the HR / GM chain. Administrators set this in Administration. The assistant cannot see what the person cannot see.

### Q5. Can someone accidentally send a client letter or close a job from the chat?

No. The assistant may **propose** a ticket or a leave draft. A person must **Confirm**. Approvals, signatures, ticket close, markup, and client email are **human actions**.

### Q6. We have more sites and more technicians next year. Do we buy a new system?

No. You add **users, projects, and flags**. If usage grows, we **size the server, database, and report worker** — same product. Extra people do not require a new Microsoft tenant grant.

### Q7. What if the internet AI is slow or down on a busy day?

Field work **does not depend on it**. Forms, tickets, and approvals continue. The assistant will say it is unavailable or use a simple fallback until the model returns.

### Q8. What if email is down?

People still work in the application. Notifications and scheduled reports wait or fail **visibly**. Nothing is silently lost into an unlogged void; inbound ticket mail that cannot be parsed is still **logged** for follow-up.

### Q9. What if Google Drive is not allowed in our organisation?

That is fine. **Files inside Kynvera Operations work without Drive.** Drive is optional, per user, and only for folders this application created.

### Q10. How do we get work in from a client email without typing it all again?

Clients (or anyone) can mail a dedicated intake address. The system creates a **draft** ticket. A **supervisor converts** it to live work. It does not auto-assign or auto-close.

### Q11. How do we know chargeable vs non-chargeable is not “the AI guessing”?

MMR classification follows **written business rules** on the CAFM file (service group, location, client, and so on). People own the policy. The assistant does not rewrite the rate card.

### Q12. Can we have this on our own servers?

Yes. It is designed to run in **your** environment (container or a Linux host with a reverse proxy), with **your** PostgreSQL. Cloud services you enable are explicit. GPU is not required.

### Q13. What happens if the server fails on a Friday?

You **redeploy** the same application version and **restore the database and file disk** from backup. There is no special “AI memory” machine. Standard backup discipline (database + disk + secrets) is the recovery plan.

### Q14. Who owns our data if we stop using a cloud model tomorrow?

You do. Switch the model off or point it at an endpoint you control. FAQs, documents, tickets, and forms stay in **your** database.

### Q15. Will this slow down if everyone is on site after a storm (many tickets, many photos)?

The application is built so **heavy work (PDF, Excel, photo packs) runs as jobs**, not as one frozen page. For a real surge, we scale **workers, database, and media** — which is why a pilot on your host is part of go-live, not a guess from a brochure.

### Q16. How do new joiners get access without seeing everything?

An administrator creates the account, sets their **designation**, and ticks **only the modules they need**. They will not see HR, commercial reports, or other sites’ tickets unless those flags and record rules allow it.

### Q17. Is there a paper trail if someone challenges an approval?

Yes. Submissions and tickets keep **status, people, and history**. Documents (PDF, DOCX, Excel) are generated from those records. That is the operational evidence pack — not a chat transcript.

### Q18. Do we need to train staff on a complicated AI?

No. Day-to-day work is **forms, queues, and tickets** they already understand. The assistant is optional help. Supervisors keep the same sign-off habits they have on paper, with less chasing of files.

### Q19. Can your team, or a vendor, read our live HR and pricing?

Not by design of the product. Access is **your administrators’** to grant. Cloud vendors receive only what that integration is for (for example a photo, or a prompt snippet). We recommend **your** VAPT and **your** access review before go-live if policy requires it.

### Q20. What do we need from our IT team to go live?

A host (or container platform), **PostgreSQL**, TLS, a **persistent disk** for reports, environment secrets, and decisions on **email**, **media storage**, and whether **Drive** or a **language model** are in scope. Optional: Redis. Optional: VAPT as a gate. Your IT does **not** need to open Microsoft Graph or WhatsApp.

### Q21. How do we keep running after handover?

The stack is meant to be **operable by your IT**: same release, same backups, same env files. Warranty and further development are as **contracted** — this is not a per-seat chatbot subscription hiding the operations system.

### Q22. If we double our workforce, what should we plan for?

Plan for **more accounts and more tickets**, then check **report-generation and photo** load. Budget a larger database and a dedicated job worker before you budget a new product. Kynvera Operations already separates “who may enter a module” from “who may see this one record,” which is what makes headcount growth safe.

---

## 5. How to use this pack in a client meeting

1. Start with the [Overview](Kynvera_Operations_Overview.md) so everyone shares the same picture of modules.
2. Use [Module Architecture](Kynvera_Operations_Architecture.md) only if they ask “how does a ticket actually move?”
3. Stay on this document for **security, growth, backup, and the questions above**.
4. Offer a **pilot on their host** as the honest way to confirm concurrent users and report load.
5. Treat **VAPT** as their gate if their policy says so — not as a claim we already hold a certificate we do not.

---

*Kynvera Operations — Operations Application*  
*August 2026*
