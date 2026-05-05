# Render deployment — Phase 1 (testing) and Phase 2 (production)

This document describes how to run Injaaz on [Render](https://render.com/) in two stages: **Phase 1** for low-cost validation on free (or minimal) resources, and **Phase 2** for production-style durability and operations. TrueNAS and office network paths are out of scope here.

---

## Shared concepts

- **Web service** — Runs `gunicorn` (see `render.yaml` `startCommand`). The Flask app loads configuration from environment variables (see root `config.py` and `Injaaz.py`).
- **`GENERATED_DIR`** — Root directory for generated Excel/PDF, DocHub cache, MMR uploads and JSON config, module uploads under `uploads/`, and job folders. On Render’s default filesystem this path is **ephemeral** unless you attach a persistent disk (Phase 2).
- **Database** — Production expects **PostgreSQL** via `DATABASE_URL` (SQLite is not used when `FLASK_ENV` is production and `DATABASE_URL` is required).
- **Outbound email** — Render **free** web services **block SMTP** (ports 25, 465, 587). Use **`BREVO_API_KEY`** + **`MAIL_DEFAULT_SENDER`** (Brevo HTTPS API). Paid Render instances can use SMTP (e.g. Gmail) again.

---

## Phase 1 — Testing (free / minimal spend)

**Goal:** Deploy the app, run smoke tests, and validate integrations without paying for Render disks or higher instance tiers.

### 1. Prerequisites

- Git repository connected to Render (GitHub, GitLab, or Bitbucket).
- A **Cloudinary** account (free tier is enough for testing uploads that use Cloudinary).
- Optional: an **Upstash** Redis instance (free tier) if you want to test rate limiting, Redis-backed cache helpers, or RQ-related behavior.

### 2. Create a PostgreSQL database on Render

1. In the Render Dashboard, create a **PostgreSQL** instance (use the free tier if available in your region).
2. Copy the **Internal Database URL** or **External Database URL** connection string.  
3. Ensure the URL uses the `postgresql://` scheme (Render often provides `postgres://`; SQLAlchemy is fine with either after the app normalizes it — see `config.py`).

Link the database to your web service when you create it (below), or add `DATABASE_URL` manually from the database’s **Connect** panel.

### 3. Create the web service

1. **New** → **Web Service** → select this repository.
2. **Runtime:** Python.
3. **Build command:** `bash build.sh` (matches `render.yaml`).
4. **Start command:**  
   `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 300 --worker-class gthread`
5. **Instance type:** Free (or the smallest paid type if free web services are unavailable).

Do **not** rely on database initialization during the **build** phase (no `DATABASE_URL` there). The app initializes the database at **runtime** when the service starts.

### 4. Environment variables (Phase 1 minimum)

Set these in the web service **Environment** tab (or via Blueprint / `render.yaml` with `sync: false` for secrets).

| Variable | Required | Notes |
|----------|----------|--------|
| `DATABASE_URL` | Yes | From Render Postgres. |
| `SECRET_KEY` | Yes | Strong random string; do not reuse dev defaults. |
| `JWT_SECRET_KEY` | Yes | Strong random string, distinct from `SECRET_KEY`. |
| `FLASK_ENV` | Yes | `production` |
| `CLOUDINARY_CLOUD_NAME` | Yes | From Cloudinary dashboard. |
| `CLOUDINARY_API_KEY` | Yes | |
| `CLOUDINARY_API_SECRET` | Yes | |
| `APP_BASE_URL` | Recommended | Your public URL, e.g. `https://<service-name>.onrender.com` — used for absolute links. |
| `REDIS_URL` | Optional | Upstash **TLS** URL (`rediss://...`). Paste exactly; no leading/trailing spaces. Improves parity with local Redis usage (rate limiting, cache, HVAC state). RQ workers still need a separate process if you require queue workers in production (Phase 2). |
| `MMR_SCHEDULE_ENABLED` | Optional | `true` or `false` — keeps MMR **schedule intent** across redeploys when JSON on disk is wiped. |
| `MMR_SCHEDULE_HOUR` | Optional | `0`–`23` (UTC matches server; scheduler uses server local time — confirm behavior in `module_mmr/scheduler.py`). |
| `MMR_SCHEDULE_MINUTE` | Optional | `0`–`59` |
| `BREVO_API_KEY` | **Yes for email on free Render** | Brevo API key (`xkeysib-...`). Render free blocks SMTP; Gmail will not work. |
| `MAIL_DEFAULT_SENDER` | With Brevo | Address verified in Brevo (e.g. `noreply@injaaz.ae` or your domain). |
| `MAIL_*` | Optional (local / paid Render) | SMTP: Gmail, Office 365, etc. Not on Render free. |

**Session / cookies:** If you use HTTPS on Render, set `SESSION_COOKIE_SECURE=true` (and JWT cookie settings as your security model requires).

### 5. Deploy and verify

1. Trigger a deploy and watch **Logs** for startup errors.
2. Confirm lines such as database initialization and blueprint registration appear (see application logging).
3. Open `APP_BASE_URL`, log in, and run a **short smoke test** on the modules you care about (auth, one module report, DocHub if used, MMR upload if used).

### 6. What to expect on Phase 1 (limitations)

- **Ephemeral disk:** Anything stored only under default `GENERATED_DIR` (e.g. `/app/generated`) may **disappear** after redeploy, restart, or instance recycle. Re-upload MMR Excel, regenerate reports, or re-save settings as needed during testing.
- **MMR automation:** Schedule can be pinned with `MMR_*` env vars; the **uploaded workbook** may still be missing after a wipe until you upload again.
- **Rate limiting:** Without `REDIS_URL`, the app disables Redis-backed rate limiting (see logs).
- **RQ / background queues:** Code paths that enqueue RQ jobs expect a reachable Redis. Running a **worker** is a separate process; Phase 1 web-only deploy may not process queued jobs unless you run a worker elsewhere or add Phase 2 worker service.

### 7. Optional: Redis (Upstash) for Phase 1

1. Create a Redis database in Upstash (TLS enabled).
2. Copy the **full** connection string (`rediss://...`).
3. Set `REDIS_URL` on Render to that value exactly.
4. Redeploy and confirm logs show a successful Redis connection test (or absence of DNS errors).

---

## Phase 2 — Production (draft runbook)

**Goal:** Durable filesystem behavior closer to a local machine, stable operations, and room to grow. Exact SKUs and prices change on Render’s site — verify before purchasing.

### 1. When to move to Phase 2

- You need **generated files, uploads, DocHub artifacts, and MMR data** to **survive deploys and restarts** without manual re-upload.
- You need **consistent rate limiting**, **Redis-backed caching**, or **background job workers** in production.
- You outgrow **free Postgres** limits (connections, storage, or support expectations).

### 2. Web service: instance type and disk

1. **Upgrade** the web service to a plan that supports **Persistent Disks** (Render documents this under paid instance types; the dashboard may prompt similarly to “Enable Jobs” / Starter features).
2. **Add a disk** on the **same** web service:
   - Choose a **mount path**, for example `/var/data`.
   - Size: start small; disks can often grow but not shrink.
3. Set **`GENERATED_DIR`** to a directory **under** that mount, for example:  
   **`GENERATED_DIR=/var/data/generated`**
4. Redeploy. Confirm logs show `GENERATED_DIR` pointing at the mounted path.

**Important:** A service with an attached disk is typically **limited to a single instance** (no horizontal scaling on that service). Deploys may incur **brief downtime** when Render swaps instances — plan maintenance windows accordingly.

### 3. Database

- Move to a **production-appropriate** Render Postgres plan (or external managed Postgres) with backups enabled.
- Rotate credentials if they were shared broadly during Phase 1.
- Keep `DATABASE_URL` in sync with the active database.

### 4. Redis (production)

- Use a managed Redis compatible with your client (**TLS** `rediss://` for Upstash).
- Store `REDIS_URL` only in Render **secrets** / environment groups.
- Monitor connection errors and adjust timeouts if you see intermittent network issues.

### 5. Background workers (optional)

If you rely on **RQ** (`app/tasks.py`, `app/forms.py` enqueue paths, etc.) for production:

1. Add a **Background Worker** service on Render (same repo, same `REDIS_URL`).
2. Start command example (adjust for your layout):  
   `rq worker default --url $REDIS_URL`
3. Ensure only one logical consumer pattern matches your queue names.

If you do **not** need RQ in production, document that decision and test the fallback paths (e.g. threaded fallbacks where implemented).

### 6. Secrets and configuration hygiene

- Use **Environment Groups** on Render for shared variables across services (web + worker).
- Never commit secrets; use `sync: false` or the dashboard for sensitive keys.
- Set `APP_BASE_URL` to your **canonical** public URL (custom domain when ready).

### 7. Backups and recovery

- **Postgres:** Use Render’s backup features or external dumps on a schedule.
- **Disk:** Render documents **disk snapshots** — understand retention and restore procedures before you rely on them.
- **Cloudinary:** Rely on Cloudinary’s asset retention and your own export policy for long-term archives if required.

### 8. Monitoring and alerts

- Enable Render **notifications** for deploy failures and instance issues.
- Watch application logs for repeated Redis, database, or migration errors.

### 9. Pre–go-live checklist (Phase 2)

- [ ] `GENERATED_DIR` is on a **persistent disk** mount.
- [ ] `DATABASE_URL` points to production Postgres; migrations applied (`flask db upgrade` or your documented process).
- [ ] `SECRET_KEY` and `JWT_SECRET_KEY` are strong and unique.
- [ ] Cloudinary and mail credentials are production accounts.
- [ ] `REDIS_URL` works from the web service (and worker if used).
- [ ] `APP_BASE_URL` and HTTPS / cookie flags match your domain.
- [ ] Smoke test: auth, critical modules, MMR upload + schedule, DocHub if used.

---

## Related documents

- **[DEPLOYMENT_TROUBLESHOOTING.md](DEPLOYMENT_TROUBLESHOOTING.md)** — Common Render build and startup issues.
- **[render.yaml](render.yaml)** — Blueprint-style service and database definitions (adjust names as needed).
- **[CLOUD_ONLY_SETUP.md](CLOUD_ONLY_SETUP.md)** — Broader “cloud-only” assumptions (some ideals may differ from current on-disk usage; this phases doc reflects Render + `GENERATED_DIR` behavior).

---

## MMR scheduler and time zone

The MMR cron uses APScheduler’s default (no explicit timezone in `module_mmr/scheduler.py`), which follows the **process local time**. On Render’s Linux runtime that is **usually UTC**. Set `schedule_hour` / `schedule_minute` in the MMR UI or env vars to match the **UTC** clock you want (or adjust for Dubai time by offset, e.g. 06:00 UTC for 10:00 GST depending on DST rules you apply).
