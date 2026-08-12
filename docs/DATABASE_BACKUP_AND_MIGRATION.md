# Database backup and local → live migration

Operational guide for keeping a **local** database, backing it up, backing up **live** (production) PostgreSQL, and moving selected local data into live in a controlled way.

This app expects **PostgreSQL** in production via `DATABASE_URL` (`FLASK_ENV=production`). Local development may use PostgreSQL (preferred) or SQLite (`injaaz.db`).

---

## 1. Recommended organization

Treat environments as **separate**, never point the local app at live `DATABASE_URL` during normal work.

| Environment | Purpose | Connection |
|-------------|---------|------------|
| **Local** | Day-to-day development / data prep | Local Postgres or `injaaz.db` |
| **Live** | Production | Hosted Postgres (`DATABASE_URL` on Render / OCI / managed provider) |

**Golden rules**

1. **Backup before every write** to live (dump or provider snapshot).
2. **Export → review → import** — never “wing it” with a one-shot `INSERT` against live.
3. Prefer **table / module scoped** imports (e.g. HR trackers) over dumping the whole local DB into live.
4. Keep credentials only in `.env` (gitignored) or the host’s secret store — never in the repo.
5. Store backups **outside** the git tree (or under a gitignored folder such as `backups/`).

Suggested folder layout on your machine:

```text
~/injaaz-db-backups/
  local/
    injaaz_local_YYYYMMDD_HHMM.sql.gz   # or .db.copy for SQLite
  live/
    injaaz_live_YYYYMMDD_HHMM.dump
  exports/                               # JSON/CSV/Excel staging before push
    hr_tracker_data_export.json
    Leave_Tracker_Export.xlsx
    Manpower_Tracker_Export.xlsx
    Hiring_Document_Tracker_Export.xlsx
```

Add to `.gitignore` if you keep backups next to the repo:

```gitignore
backups/
*.sql
*.sql.gz
*.dump
injaaz.db
injaaz.db-*
```

---

## 2. Local database

### 2.1 Preferred: local PostgreSQL

Matches production and avoids SQLite quirks on migrate.

```bash
# Create DB once (example)
createdb injaaz

# In .env (local only)
FLASK_ENV=development
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/injaaz
```

Start the app as usual; schema comes from app init / `flask db upgrade` as you use in this project.

### 2.2 Alternative: SQLite

If `DATABASE_URL` is unset or points at SQLite, the file is typically `./injaaz.db` in the project root (see `SETUP.md`). Fine for light local work; for serious migration to live, prefer Postgres locally or export via scripts (see §4).

### 2.3 Backup local DB

**PostgreSQL (custom format — best for restore):**

```bash
mkdir -p ~/injaaz-db-backups/local
pg_dump "$DATABASE_URL" -Fc -f ~/injaaz-db-backups/local/injaaz_local_$(date +%Y%m%d_%H%M).dump
```

**PostgreSQL (plain SQL, gzipped):**

```bash
pg_dump "$DATABASE_URL" | gzip > ~/injaaz-db-backups/local/injaaz_local_$(date +%Y%m%d_%H%M).sql.gz
```

**SQLite:**

```bash
mkdir -p ~/injaaz-db-backups/local
# Consistent copy while DB may be open
sqlite3 injaaz.db ".backup '~/injaaz-db-backups/local/injaaz_local_$(date +%Y%m%d_%H%M).db'"
# Or simple file copy when the app is stopped:
# cp injaaz.db ~/injaaz-db-backups/local/injaaz_local_$(date +%Y%m%d_%H%M).db
```

**Cadence:** before risky local experiments, and at least weekly if the local DB holds real business data you care about.

### 2.4 Restore local from backup

```bash
# From custom dump
pg_restore --clean --if-exists -d "$DATABASE_URL" ~/injaaz-db-backups/local/injaaz_local_YYYYMMDD_HHMM.dump

# From gzipped SQL
gunzip -c ~/injaaz-db-backups/local/injaaz_local_YYYYMMDD_HHMM.sql.gz | psql "$DATABASE_URL"

# SQLite
cp ~/injaaz-db-backups/local/injaaz_local_YYYYMMDD_HHMM.db ./injaaz.db
```

---

## 3. Live (production) database backups

Live data is the source of truth. Back it up **before any import**, and on a schedule.

### 3.1 Provider / platform backups (primary)

| Host | What to do |
|------|------------|
| **Render Postgres** | Use a plan with **automatic backups** / point-in-time recovery if available. From the DB dashboard: download or create a logical backup when offered. Keep the **External Database URL** only for admin machines. |
| **OCI / self-hosted Postgres** | Enable volume **snapshots** of the DB disk **and** run `pg_dump` (below). Snapshots alone are not a substitute for portable logical dumps. |
| **Managed Postgres** (Neon, Supabase, etc.) | Turn on provider backups; still take an occasional `pg_dump` you control. |

### 3.2 Manual logical backup of live (do this before migration)

From a trusted machine (not committed to git):

```bash
# Use the External / admin URL with SSL when required
export LIVE_DATABASE_URL='postgresql://USER:PASS@HOST:5432/DBNAME?sslmode=require'

mkdir -p ~/injaaz-db-backups/live
pg_dump "$LIVE_DATABASE_URL" -Fc \
  -f ~/injaaz-db-backups/live/injaaz_live_$(date +%Y%m%d_%H%M).dump
```

Verify the file is non-empty and store it somewhere durable (encrypted disk, company backup share, object storage). Do **not** commit dumps.

### 3.3 Restore live (emergency only)

1. Stop or put the app in maintenance if possible (avoid writes during restore).
2. Restore into a **new** database when you can, then switch `DATABASE_URL` — safer than overwrite-in-place.
3. If overwrite-in-place is required:

```bash
pg_restore --clean --if-exists -d "$LIVE_DATABASE_URL" \
  ~/injaaz-db-backups/live/injaaz_live_YYYYMMDD_HHMM.dump
```

Test restore on a **staging** DB periodically so you know the dump is usable.

### 3.4 Suggested live backup cadence

| When | Action |
|------|--------|
| **Daily** (automated) | Provider backup or cron `pg_dump` |
| **Before any data import / migration** | Fresh `pg_dump` to `~/injaaz-db-backups/live/` |
| **After major schema change** | Extra dump + note the app/git commit |

---

## 4. Migrating / adding local data to live (best order of work)

Do **not** replace the entire live database with local unless live is empty and you intend a full cutover. Prefer **scoped** data moves.

### Decision tree

```text
Is live empty (new deploy)?
  YES → Option A: full schema on live, then selective data import
  NO  → Option B: export only the tables/modules you need, upsert into live
```

### Option A — First-time live (empty or disposable)

1. Deploy app so schema exists (`create_all` / `flask db upgrade` as you already use).
2. Take a live dump anyway (baseline).
3. Import only business data you need (users carefully — passwords/roles; HR trackers; reference tables). Prefer scripts over blind `pg_restore` of a whole local dump (IDs, secrets, and env-specific rows often conflict).

### Option B — Live already has users / production data (usual case)

Use a **three-stage pipeline**: **Export → Stage → Push**.

#### Stage 1 — Export from local

Example already in the repo for HR Leave / Manpower trackers:

```bash
# From repo root — exports selected tables from local SQLite (default ./injaaz.db)
python scripts/push_hr_tracker_data.py export
# → tmp/hr_tracker_data_export.json
```

For other modules, follow the same pattern: dump specific tables to JSON/CSV under `tmp/` or `~/injaaz-db-backups/exports/`, never push unreviewed SQL.

#### Stage 2 — Review the export

- Open the JSON/CSV; check row counts and sensitive fields.
- Confirm you are not about to wipe live users or overwrite live IDs unintentionally.
- Copy the reviewed file into `~/injaaz-db-backups/exports/` with a dated name.

#### Stage 3 — Backup live, then push

```bash
# 1) Backup live first
pg_dump "$LIVE_DATABASE_URL" -Fc \
  -f ~/injaaz-db-backups/live/injaaz_live_pre_import_$(date +%Y%m%d_%H%M).dump

# 2) Point only this shell at live (do not put live URL in your normal .env)
export DATABASE_URL="$LIVE_DATABASE_URL"

# 3) Upsert (HR trackers example)
python scripts/push_hr_tracker_data.py push
# Destructive wipe of those HR tables on live — only if intentional:
# python scripts/push_hr_tracker_data.py push --replace
```

Unset `DATABASE_URL` / restore local `.env` when finished so the next app run does not hit live.

#### Stage 4 — Verify

- Spot-check counts in live (SQL shell, Render shell, or `scripts/inspect_postgres.py` with live URL set carefully).
- Smoke-test the affected UI modules.
- Keep the pre-import dump until you are confident (e.g. 7–30 days).

---

## 5. Full dump local → live (only when intentional)

Use when live is empty **or** you explicitly replace live with a local Postgres clone.

```bash
# Backup live first if it has anything worth keeping
pg_dump "$LIVE_DATABASE_URL" -Fc -f ~/injaaz-db-backups/live/injaaz_live_before_replace_$(date +%Y%m%d_%H%M).dump

# Dump local
pg_dump "$LOCAL_DATABASE_URL" -Fc -f /tmp/injaaz_local_for_live.dump

# Restore into live (destructive)
pg_restore --clean --if-exists -d "$LIVE_DATABASE_URL" /tmp/injaaz_local_for_live.dump
```

**Caveats**

- SQLite dumps are **not** drop-in for Postgres; convert via app scripts or recreate schema on Postgres and migrate row data.
- Local admin passwords, test users, and `GENERATED_DIR` / Cloudinary URLs may not match production.
- After restore, confirm env vars (`APP_BASE_URL`, Cloudinary, mail) still match the live host.

---

## 6. Excel export (local) → import (live) without errors

Use the app’s own **Export** / **Template** buttons on local, then upload those files on live. Do **not** invent sheet layouts. Imports are designed to skip bad rows and keep good ones — follow the prep steps below so you get **zero skipped rows** and no hard failures.

### 6.1 Rules that prevent import errors

1. **Same app version** on local and live (same column aliases / sheet names). Deploy live first if local is ahead.
2. **Backup live** (`pg_dump`) before any Excel upload.
3. **Import in dependency order** (below). Never import Leave Log before Staff exists on live.
4. **Strip environment-specific IDs** that only exist on local (or leave them blank). Local numeric PKs usually do **not** match live.
5. Prefer **business keys** over DB ids: Emp ID, email, Full Name + Role, Contract/Client name, Material Name.
6. After export on local, open the file in Excel once and **Save** (so formula-cached cells are written — especially Manpower project/trade columns).
7. Upload **`.xlsx`** unless a feature explicitly requires SpreadsheetML `.xls` (ticketing fault catalog).

### 6.2 Safe import order on live

Do only the modules you need, but respect this order when several apply:

| Step | Module | How you get the file on local | Import on live |
|------|--------|-------------------------------|----------------|
| 1 | Users / login | (manual or admin) | Ensure accounts that own data exist; Excel cannot create app users |
| 2 | Admin — BD projects | Export/sample → fill | `/api/admin/bd/projects/import-excel` |
| 3 | Admin — Devices | Sample Excel | `/api/admin/devices/import-excel` (assigned user = **email** that exists on live) |
| 4 | Admin — Technicians | Template export | Clear or remap **`supervisor_user_id`** to a live User id |
| 5 | HR Hiring | `/hr/api/hiring/export` | Hiring import (match by **email** if Candidate ID is from local) |
| 6 | HR Manpower | `/hr/api/manpower/export` | Import **without** `replace` unless you intend to wipe live vacancies |
| 7 | HR Leave | Leave Tracker export (must include **Staff** + **Leave Log**) | Leave import (Staff creates Emp IDs first) |
| 8 | QHSE staff compliance | Template / filled workbook | Staff-compliance import |
| 9 | Procurement materials | Export / sample | Import (always **inserts**; expect duplicates if re-run) |
| 10 | MMR CAFM workbook | Your CAFM / saved report `.xlsx` | Re-upload on live (file is **not** in Postgres) |
| 11 | Ticketing fault catalog | Official SpreadsheetML `.xls` | Rebuild from path / settings UI |

### 6.3 Prep each export so live import stays clean

#### HR Leave Tracker

- Export the full tracker (sheets: **Staff**, **Leave Log**, Sick/Annual as needed).
- On live, import that **same** workbook once — Staff rows create/update employees, then Leave Log attaches by **Emp ID**.
- Dates must fall inside the tracker window (Aug–Dec of the configured year) or those log rows are rejected.
- If you only have a Leave Log sheet, seed Staff first (or use seed-staff / a Staff sheet) so Emp IDs exist.

#### HR Hiring

- Export includes **Candidate ID** from local. Live will:
  - update if that id exists on live, else
  - match by **email**, else
  - create from Full Name + Role.
- To avoid wrong merges: ensure every candidate has a stable **email** before export, or clear Candidate ID / Vacancy ID columns when live is empty.
- Document columns are status only (✓/✗); they do **not** upload passport files. Re-upload files on live if needed.
- Blank document cells leave live status unchanged (safe).

#### HR Manpower

- Use the official export (`All Trades` layout). Open + Save in Excel before upload.
- Do **not** tick replace/wipe on live unless you mean to delete all live vacancies first.
- **Hiring Candidate ID** is optional; missing ids become warnings, not a failed import. Clear that column if candidates are not on live yet (import Hiring first if you want links).

#### Admin technicians

- Required: `employee_id`, `full_name`.
- Clear **`supervisor_user_id`** before live import, or set it to a supervisor’s **live** User id. Local ids cause row skips.

#### Admin devices

- Required: Device Name.
- Assigned user must be an **email that already exists** on live; otherwise the device imports unassigned (no crash).

#### Admin BD projects

- Need Contract **or** Client. Dedupes on `name|company` — safe to re-import.

#### Procurement

- Required: Material Name. Every import **adds** rows (no upsert). Import once, or accept duplicates.

#### QHSE staff compliance

- Use the app template (long or wide format). No FK to other modules — low conflict risk.

#### MMR

- Not a DB row import: upload the CAFM / report Excel on the **live** server so it sits under live `GENERATED_DIR` (or Cloudinary flow as configured). A local path will not appear on live after deploy.

#### Ticketing fault catalog

- Must be SpreadsheetML **`.xls`** with Fault Code / Name / Category / Service Group. `.xlsx` is rejected by design — convert or use the official catalog file.

### 6.4 Pre-flight checklist (Excel → live)

- [ ] Live DB backup taken.
- [ ] Live app version ≥ local (or same).
- [ ] Users/emails that Excel references already exist on live (devices, supervisors).
- [ ] Leave: Staff sheet present (or staff already seeded).
- [ ] Hiring: emails filled; local-only Candidate/Vacancy IDs cleared or accepted as create/match-by-email.
- [ ] Manpower: file saved in Excel; `replace` off unless intentional.
- [ ] Technicians: `supervisor_user_id` blank or remapped.
- [ ] Procurement: aware of insert-only (no accidental double import).
- [ ] After import: open the module on live and confirm counts; note any row-level error list the UI returns (fix those rows and re-import only the fix).

### 6.5 If a row still errors

Imports usually **do not abort the whole file** — they report row errors and commit the rest.

1. Download / note the error list from the UI response.
2. Fix those rows in a copy of the Excel (missing Emp ID, bad date, missing Full Name/Role, bad supervisor id).
3. Re-import **only the fixed rows** (or the full file where upsert/dedupe is safe: Hiring, BD, Devices, Leave Staff).
4. Avoid re-importing Procurement or Manpower-without-replace blindly (duplicates / extra vacancies).

---

## 7. Safety checklist (print before every live import)

- [ ] Local backup exists and was verified (file size / restore test).
- [ ] Fresh **live** `pg_dump` saved under `~/injaaz-db-backups/live/`.
- [ ] Import scope is known (which tables / which Excel / which script).
- [ ] Excel prep from §6 done (IDs, Staff sheet, Save in Excel).
- [ ] Live URL used only in a one-off shell session (not left in local `.env`) when using scripts.
- [ ] `--replace` / `--clean` only if you mean to wipe those tables.
- [ ] Post-import smoke test on live UI.
- [ ] Live `DATABASE_URL` unset from laptop when done.

---

## 8. Quick reference

| Goal | Command / action |
|------|------------------|
| Backup local Postgres | `pg_dump "$DATABASE_URL" -Fc -f ~/injaaz-db-backups/local/...dump` |
| Backup local SQLite | `sqlite3 injaaz.db ".backup '.../injaaz_local_....db'"` |
| Backup live | `pg_dump "$LIVE_DATABASE_URL" -Fc -f ~/injaaz-db-backups/live/...dump` |
| Export HR trackers (local DB script) | `python scripts/push_hr_tracker_data.py export` |
| Push HR trackers to live (script) | Backup live → `DATABASE_URL=$LIVE... python scripts/push_hr_tracker_data.py push` |
| Excel path (UI) | Export on local → prep §6 → Backup live → Import on live in §6.2 order |
| Inspect Postgres | `python scripts/inspect_postgres.py` (with `DATABASE_URL` set) |

---

## Related docs

- `SETUP.md` — local app setup  
- `CLOUD_ONLY_SETUP.md` — production Postgres + Cloudinary requirements  
- `RENDER_DATABASE_SETUP.md` / `RENDER_DEPLOYMENT_PHASES.md` — Render DB  
- `docs/OCI_DEPLOYMENT.md` — OCI VM + Postgres options  
- `scripts/push_hr_tracker_data.py` — scoped HR data export/push  
