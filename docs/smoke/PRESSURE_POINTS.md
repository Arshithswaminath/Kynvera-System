# Pressure points

Latest run is **production** ([LAST_RUN.md](LAST_RUN.md)): `https://operations.kynvera.net` — **114 passed, 0 failed, 3 warnings**. Artifacts: `smoke_artifacts/20260821_135721/`.

Local laptop run earlier the same day: `http://127.0.0.1:5002` — **117 passed, 0 failed, 0 warnings** (`smoke_artifacts/20260821_124733/`).

This file ranks **what to address now** vs **later**. Rankings use measured FAIL/WARN/slow rows plus duplication found while wiring the smoke runner.

## Live vs local (2026-08-21)

Production is behind local on ticketing Excel. These three routes **200 on local, 404 HTML on live**:

- `GET /tickets/api/tickets/export`
- `GET /tickets/api/settings/locations/excel-template`
- `GET /tickets/api/settings/projects/<id>/locations/export`

**Fix:** deploy the current branch (the `ticket_excel` / `location_excel` work) to Render. Until then live cannot export the ticket register or location workbooks.

Live was also slower (expected): ticket triage **12.2s**, MMR upload **8.4s**, MMR download **5.8s**. Login **2.3s**. Local had no check over 5s.

The smoke **wrote** on live: leave `HR-LEAVE_APPLICATION-424F79B1`, ticket `TKT-649A28A5`, an MMR CAFM upload, and a Files leave-template save. Safe to close/delete those records.

Canonical runner: [`scripts/module_functional_smoke.py`](../../scripts/module_functional_smoke.py).

## Fix now

Status after 2026-08-21 follow-up: the five items below are **implemented** (scripts, health check, pytest magic-bytes, inspection HTTP download, MMR fixture). None of the product PDF/Excel builders were rewritten.

### 1. Stale parallel QA scripts will fail independently

The new runner is green. The older scripts are not equivalent and already drift:

| Script | Problem |
|--------|---------|
| [`scripts/operational_smoke_test.py`](../../scripts/operational_smoke_test.py) | Creates tickets with `priority: "P3"`. Live API only accepts `low` / `medium` / `high` / `critical`. First smoke run failed ticket create with `Invalid priority` until this runner was fixed. |
| [`scripts/admin_full_app_qa.py`](../../scripts/admin_full_app_qa.py) | HR Excel paths are wrong (`/hr/hiring/api/export`, `/hr/leave-tracker/api/export`). Real routes are `/hr/api/hiring/export`, `/hr/api/leave-tracker/export`, `/hr/api/manpower/export`. |

**Do now:** Point both scripts at the same routes/priorities as this runner, or delete/alias them so people do not trust a red run from a stale path.

### 2. CI does not exercise most export pipelines

Pytest in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) is `pytest tests/ -q --maxfail=5`. There are **no dedicated tests** for inspection, QHSI, MMR, procurement, or files exports. HR and ticketing have coverage; those five modules only proved green because we hit a live server.

**Do now:** Add thin pytest cases that call the builders (same as this smoke’s fallback) and assert `%PDF` / `PK` magic bytes. That catches builder breakages without a running server.

### 3. Inspection / QHSI HTTP download path is untested

This run generated HVAC/Civil/Cleaning and QHSI PDF+Excel **via builders**, not `GET /inspection/download/...` or job regenerate. Those HTTP routes need a completed report job (photos, Cloudinary in prod). A builder-green run can still hide a broken download/job pipeline.

**Do now:** One pytest or smoke step that submits a minimal inspection (or uses an existing job id) and downloads PDF+Excel over HTTP.

### 4. Local SQLite is fragile under live use

During this session the live `injaaz.db` answered `GET /health` as healthy, then `POST /api/auth/login` returned 500 `no such table: users`. Restarting `./run` re-seeded an empty schema (`ticketing: seeded`, `fm_assets: seeded`). WAL files (`injaaz.db-wal`) were present.

**Do now:** Treat local SQLite as a smoke-only store. Do not rely on it as durable data. Add a backup before long smoke/MMR uploads, or document “restart `./run` re-seeds if tables vanish.”

### 5. MMR has no in-repo fixture

MMR Excel generation depends on a local CAFM file (`HR Documents/RM Deatils MMR (4).xlsx`). If that file is missing, download-report warns and you get no MMR artifact. The first run found it; CI will not.

**Do now:** Check a small anonymized CAFM xlsx into `tests/fixtures/mmr/` (or skip MMR in CI with an explicit reason).

## Later (duplication / maintenance cost)

These did **not** fail the smoke. They are the repetition that will keep hurting.

### HR PDF and DOCX are parallel hotspots

[`module_hr/hr_pdf_builder.py`](../../module_hr/hr_pdf_builder.py) is ~2.7k lines with 12 `_BUILDERS` (plus a `leave` alias). [`module_hr/docx_builder.py`](../../module_hr/docx_builder.py) mirrors the same forms. Sample data for `asset_handover` was missing from [`scripts/auto_test_hr_forms.py`](../../scripts/auto_test_hr_forms.py); the runner had to supply a fallback.

Highest long-term cost when a form field changes.

### Shared brand, still layered

`common.kynvera_pdf_brand` is used by HR, ticket work order, ticket invoice, QHSI, inspection (via `professional_pdf_service`), and asset QR. Inspection Excel goes through `professional_excel_service` (~165KB workbooks) while QHSI Excel is a thin openpyxl sheet (~5KB). Same “report” idea, two stacks.

### Files module re-wraps every export

[`module_files/service.py`](../../module_files/service.py) `_build_*_bytes` calls the same HR/MMR/procurement/QHSI/admin builders. Smoke `POST /files/api/save-from-module` (leave template) worked. Every new export needs a second wiring in Files.

### Two ticketing PDFs

Work order: [`ticket_pdf_builder.py`](../../module_ticketing/ticket_pdf_builder.py). Invoice: [`ticket_invoice_builder.py`](../../module_ticketing/ticket_invoice_builder.py). Both branded separately. This run’s invoice was **3681 bytes** (empty commercial content on a just-created ticket) vs **13324 bytes** for the work-order PDF — expected, but easy to mistake for a broken invoice.

### Three overlapping smoke/QA entrypoints

`operational_smoke_test.py`, `admin_full_app_qa.py`, `generate_all_sample_pdfs.py`, plus this runner. Keep this one as canonical; fold or document the others as subset tools.

### Hardcoded admin passwords in old QA scripts

This runner reads `CHECK_*` / `DEFAULT_ADMIN_*` from `.env`. `admin_full_app_qa.py` still embeds credentials in source.

### Large HTML shells (not slow, but heavy)

No check crossed 5s. Notable payloads:

| Page | Bytes |
|------|------:|
| `/admin/mmr/` | 247217 |
| `/inspection/form` | 238665 |
| `/admin/dashboard` | 237694 |
| `/tickets/new` | 206586 |
| `/tickets/TKT-…` | 179730 |
| `/tickets/settings` | 145240 |

Worth splitting only if field UX or mobile load becomes a complaint.

## Measured latency (this run)

Nothing hit the 5s “slow” flag. Closest:

| Check | ms | Why it matters |
|-------|---:|----------------|
| `POST /tickets/api/tickets/triage-preview` | 2685 | Live LLM round-trip |
| HR PDF builders (12 forms) | 1185 | CPU in ReportLab; fine offline |
| `POST /api/assistant/chat` | 809 | Live LLM |
| `GET /admin/mmr/api/current-upload` | 497 | Parses last CAFM upload |
| `GET /admin/mmr/api/download-report` | 411 | Regenerates the chargeable workbook |
| `GET /tickets/TKT-…` | 169 | Heavy detail page |
| `GET /inspection/form` | 144 | Heavy form shell |
| `GET /assets/api/qr-labels.pdf` | 126 | Bulk QR PDF |

LLM calls are the only user-facing waits. Guard them with timeouts and a non-LLM fallback (already WARN-capable in older smokes).

## What this smoke did not prove

- Email send, Google Drive, Cloudinary uploads
- Ticket supervisor-close / verification workflow
- Inspection/QHSI **job** download URLs
- DocHub DOCX→PDF (LibreOffice)
- Concurrent multi-user load

## Suggested next slices (after you review the PDFs/Excel)

1. Align or retire `operational_smoke_test.py` and `admin_full_app_qa.py`.
2. Pytest magic-byte tests for inspection, QHSI, MMR, procurement, files builders.
3. One HTTP inspection download after a real submit.
4. SQLite backup note (or Postgres for anything you care about keeping).
