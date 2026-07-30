# Injaaz App — Security & Scalability Audit Report

**Date:** 2026-07-19 · **Branch audited:** `amaan-test-case` · **Scope:** full codebase (~70,900 lines Python, ~415 routes, 15 blueprints, 48 models)

> ⚠️ This document references the locations of leaked credentials. Rotate those credentials before sharing this repo or this document outside the team.

---

## Verdict

The codebase fundamentals are solid — SQLAlchemy ORM throughout (no SQL injection found), bcrypt password hashing, near-complete route authentication, gunicorn/Docker deployment, and a production config validator. However, **two critical secret leaks in git history and a hard scaling ceiling (single worker, synchronous heavy work) must be fixed before organizational deployment.**

---

## Security Findings

### Critical

| # | Finding | Evidence |
|---|---------|----------|
| C1 | Live secrets committed to git: `SECRET_KEY`, Upstash Redis password, Cloudinary API key/secret | `.env.production` lines 5, 12, 16–17 (tracked in git) |
| C2 | Production database committed with real user data: 14 users' emails, roles, and bcrypt password hashes | `injaaz.db`, `instance/injaaz.db` (tracked in git) |

**Required action:** rotate all three credential sets (Render/Upstash/Cloudinary dashboards), force password reset for affected users, then purge both files from git history (see remediation Phase 0).

### High

| # | Finding | Evidence |
|---|---------|----------|
| H1 | Login rate limiting silently disabled when Redis is unavailable — no in-memory fallback, so brute-force protection is a no-op in Redis-less deployments | `Injaaz.py:630-656`, `Amaan.py:699-719`, `app/auth/routes.py:26-33` |
| H2 | Unauthenticated file-download routes expose generated business reports (Excel/PDF) to anyone who guesses a filename | `module_civil/routes.py:580,566` · `module_cleaning/routes.py:53` · `module_hvac_mep/routes.py:820,807` |
| H3 | Cleartext password written to application logs on every login (raw request body logged at INFO) | `app/auth/routes.py:212-213` |

### Medium

| # | Finding | Evidence |
|---|---------|----------|
| M1 | Hardcoded default registration password `Amaan@123`; open self-registration creates immediately-usable accounts seeded with it | `common/password_admin.py:15`, `app/auth/routes.py:97,175` |
| M2 | Registration API returns the default password in cleartext JSON | `app/auth/routes.py:193` |
| M3 | CSRF not enforced on the cookie-JWT path (`JWT_COOKIE_CSRF_PROTECT` defaults to false; API routes CSRF-exempt) | `config.py:88`, `Injaaz.py:220,675` |
| M4 | Authorization is module/role-level only — no per-record ownership checks; any module-enabled user can edit/delete any record by id | e.g. `module_operations/routes.py:326,385` (pattern repeats in finance/store/hr) |

### Low / Informational

- L1 — Generated admin password logged at CRITICAL level (`Injaaz.py:502,511`; also `Amaan.py`).
- L2 — Debug error internals leaked when debug is on (`app/auth/routes.py:298`, `app/middleware.py:91`); blocked in prod by the config validator.
- L3 — Fallback secrets `change-me-in-production` in `config.py:31-32`; mitigated — `common/config_validator.py:29-36` hard-fails production startup on them.
- L4 — Dependencies pinned but dated: Flask 2.2.5, Werkzeug 2.2.3, flask-jwt-extended 4.4.4, rq 1.1.0 (`requirements-prods.txt`).
- L5 — AI assistant sends internal business context to external LLM providers (`module_assistant/llm.py`); keys env-sourced, route JWT-protected — data-residency consideration only.

### What is done well (verified)

- **No SQL injection:** SQLAlchemy ORM everywhere; the only string-built SQL is static startup DDL with no user input.
- **Passwords bcrypt-hashed** (cost 12) with strength validation; never stored or compared in plaintext.
- **XSS surface minimal:** no `|safe`, `render_template_string`, or `Markup()`; Jinja2 autoescape intact.
- **Route protection near-complete:** sampled decorator coverage — HR 48/49, finance 15/15, operations 38/38, inspection 9/9, store 24/24, workflow 21/21; centralized decorators in `app/middleware.py`; JWT revocation blocklist.
- **Path traversal mitigated** on downloads (`send_from_directory` + explicit path checks); **SSRF guard** on the assistant URL fetcher (`module_assistant/fetch_url.py:62-69`).
- **Deployment hygiene:** gunicorn in prod (`render.yaml`, `Dockerfile`), non-root container user, server-generated secrets on Render, session cookies HttpOnly/SameSite=Lax, admin seeded with random password + forced first-login change.

---

## Scalability Findings

**Current architecture:** monolithic Flask app-factory, gunicorn **1 worker × 4 gthreads** on Render, Postgres in prod / SQLite in dev, JWT auth with a per-request DB revocation lookup, Cloudinary for files, in-process `ThreadPoolExecutor(1)` + APScheduler for background work, and synchronous PDF/DOCX/LLM/email inside request handlers.

Bottlenecks ranked by impact for 50–500 concurrent users:

1. **Single gunicorn worker (GIL-bound)** — roughly one CPU-heavy request at a time (`render.yaml`, `Dockerfile`). Cannot be raised until items 2–3 are fixed.
2. **Synchronous heavy work in request handlers** — HR PDF/DOCX (`module_hr/routes.py:56`, `hr_pdf_builder.py` 2,729 lines), HVAC report generation, blocking LLM calls (`module_assistant/routes.py:117`), synchronous email — each occupies a thread for seconds to minutes (hence the 300 s gunicorn timeout).
3. **In-process background primitives** — `ThreadPoolExecutor(max_workers=1)` (`Injaaz.py:143`) and APScheduler (`module_mmr/scheduler.py`) live inside the web worker; scaling to N workers duplicates scheduled emails and loses jobs. This is why the deployment is pinned to 1 worker.
4. **Local-filesystem state** — `generated/`, `jobs/`, `mmr_email_config.json` are ephemeral on Render and not shared across instances.
5. **Per-request auth DB round-trip** — JWT blocklist query on every authenticated request (`Injaaz.py:268`); many `lazy='dynamic'` relationships risk N+1 on dashboards.
6. **Ad-hoc schema management** — inline `ALTER TABLE` blocks run on every boot (`Injaaz.py:340-476`); Flask-Migrate installed but no real Alembic versions.
7. **No CI; 14 test files for ~415 routes.**

**Maintainability:** `Injaaz.py` (1,076 lines) and `Amaan.py` (1,163 lines) are near-identical duplicate bootstraps; three ~4,000-line route files (`app/admin/routes.py`, `module_ticketing/routes.py`, `app/workflow/routes.py`) mix HTTP, business logic, DB, and document generation.

**Reusable building blocks already present:** a working RQ + Redis queue scaffold (`app/tasks.py`, `app/extensions.py:get_rq_queue`, `app/tasks/worker.py`, wired into `app/modules/site_visit`), Cloudinary integration, Flask-Migrate initialized, Flask-Limiter, health check endpoint, and the config validator.

---

## Remediation Plan

### Phase 0 — Secret purge (runbook; requires credential rotation first)

1. Rotate in dashboards: Render SECRET_KEY/JWT keys, Upstash Redis credentials, Cloudinary API secret. Force password reset for the 14 exposed users.
2. Add `.env.production`, `injaaz.db`, `instance/*.db` to `.gitignore`.
3. Purge from history with `git-filter-repo` (strips the files from all commits), coordinate a force-push, and have all collaborators re-clone.

### Phase 1 — Security code fixes

4. Delete the request-body log at login (H3).
5. Add auth decorators to the `/generated/` and `/status/` routes in civil, cleaning, and HVAC modules (H2).
6. Fall back to in-memory Flask-Limiter storage when Redis is absent (H1).
7. Replace the fixed default password with per-user random values; remove it from the register API response; gate login until first password change (M1/M2).
8. Enable `JWT_COOKIE_CSRF_PROTECT` (M3).
9. Add owner-or-admin checks on record update/delete endpoints where a `created_by` column exists (M4).

### Phase 2 — Unlock scaling

10. Generalize the existing RQ queue: move HR PDF/DOCX, HVAC reports, admin doc regen, and email sends onto it (synchronous inline fallback when Redis is absent, for dev); add an RQ worker service to `render.yaml`/`Dockerfile`; upgrade `rq`.
11. Gate the MMR APScheduler behind an env flag set only on the worker service (prevents duplicate emails at >1 worker).
12. Remove the global `ThreadPoolExecutor` once its users are on RQ.
13. Persist `mmr_email_config.json` to the database.
14. Raise `WEB_CONCURRENCY` to 2+ and drop gunicorn `--timeout` from 300 s to 60 s.
15. Add a short-TTL cache for the JWT blocklist check.

### Phase 3 — Hygiene

16. Create a real Alembic migration baseline (keep inline DDL temporarily, marked deprecated).
17. Add GitHub Actions CI: pytest + flake8.
18. Follow-ups (separate efforts): Flask 2.2 → 3.x upgrade, consolidate `Injaaz.py`/`Amaan.py`, split the 4,000-line route files behind a service layer.

---

## Verification checklist

- [ ] App boots; `/health` returns OK; every touched route responds.
- [ ] 6 rapid failed logins → HTTP 429, with no Redis configured.
- [ ] Unauthenticated GET on a `/generated/` route → 401; authenticated → 200.
- [ ] Log grep after a login: no request body or password present.
- [ ] Registration response contains no password; seeded account forces password change.
- [ ] HR PDF generation completes end-to-end via RQ worker (and via inline fallback without Redis).
- [ ] With 2 workers, MMR scheduler starts exactly once (on the worker service only).
- [ ] `pytest tests/` green; CI workflow runs on push.
