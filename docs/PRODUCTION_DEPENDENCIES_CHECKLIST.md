# Production dependencies checklist

Use this before and after each production deploy (e.g. Render). Mark items when verified.

**Related:** `.env.example` (all variables), `docs/EMAIL_SMTP_OPTIONS.md` (mail), `render.yaml` (example service wiring).

---

## 1. Hosting & application secrets

| Done | Item |
|------|------|
| ☐ | **Web host** (e.g. Render Web Service) is running and `PORT` / start command match `wsgi:app` (or your entrypoint). |
| ☐ | **`FLASK_ENV=production`** (or equivalent) so production validation runs. |
| ☐ | **`SECRET_KEY`** set to a long random value (min 32 chars; not a default from repo). |
| ☐ | **`JWT_SECRET_KEY`** set to a different long random value. |
| ☐ | **`DEBUG`** is not enabled in production. |
| ☐ | **`APP_BASE_URL`** = public HTTPS base URL of the app (e.g. `https://your-service.onrender.com`) — used for links and some absolute URLs. |
| ☐ | **`SESSION_COOKIE_SECURE=true`** when the site is only served over HTTPS. |

---

## 2. Database (required)

| Done | Item |
|------|------|
| ☐ | **PostgreSQL** provisioned (e.g. Render PostgreSQL or other managed Postgres). |
| ☐ | **`DATABASE_URL`** set and points to that Postgres (not SQLite). `postgres://` is OK; the app rewrites to `postgresql://` for SQLAlchemy. |
| ☐ | After first deploy or model changes: run **`flask db upgrade`** (if you use Alembic) or confirm **`db.create_all()`** + migrations cover required tables. |
| ☐ | Smoke test: app starts, can log in, at least one write/read path hits the DB. |

---

## 3. File storage — Cloudinary (required in production)

The app’s production config validator requires Cloudinary for cloud file storage.

| Done | Item |
|------|------|
| ☐ | **Cloudinary** account created. |
| ☐ | **`CLOUDINARY_CLOUD_NAME`**, **`CLOUDINARY_API_KEY`**, **`CLOUDINARY_API_SECRET`** set in production env. |
| ☐ | **`CLOUDINARY_UPLOAD_PRESET`** matches an unsigned (or signed, per your app) upload preset in Cloudinary, if the client uses direct upload. |
| ☐ | Smoke test: upload a photo/signature in a form and confirm it appears in Cloudinary and in the app. |

---

## 4. Redis (strongly recommended)

| Done | Item |
|------|------|
| ☐ | **Redis** available (e.g. Upstash **Redis** — use `rediss://` if TLS). |
| ☐ | **`REDIS_URL`** set (no extra spaces; copy from dashboard carefully). |
| ☐ | Optional: **`RATELIMIT_STORAGE_URL`** = same as `REDIS_URL` if your deployment expects it. |
| ☐ | Confirm logs: rate limiting **enabled** (not “disabled (no Redis URL)”). |

If Redis is missing, the app may still run, but **API rate limits** and **any Redis-dependent behavior** are degraded.

---

## 5. Email (at least one path when you need mail)

Pick **one** primary method and configure. Render often blocks raw SMTP; **Brevo HTTPS API** is documented in `.env.example`.

| Done | Item |
|------|------|
| ☐ | **Brevo API:** `BREVO_API_KEY` (or `SENDINBLUE_API_KEY`) + **`MAIL_DEFAULT_SENDER`** (verified domain/sender in Brevo). |
| ☐ | **OR Mailjet REST/SMTP:** `MAILJET_API_KEY` + `MAILJET_SECRET_KEY` + sender. |
| ☐ | **OR SMTP (if allowed):** `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`. |
| ☐ | Smoke test: password reset, workflow notification, or MMR/report email (whichever you use) sends and is received. |

Details: `docs/EMAIL_SMTP_OPTIONS.md`.

---

## 6. Optional / module-specific

| Done | Item |
|------|------|
| ☐ | **MMR scheduled reports:** if the schedule config must survive redeploys, set **`MMR_*`** env vars and/or a **persistent `GENERATED_DIR`** on a mounted disk (see `render.yaml` / `config.py` comments). |
| ☐ | **Persistent files:** if you store files only on local disk, attach a **disk** and set **`GENERATED_DIR`**; otherwise use Cloudinary and/or accept ephemeral local storage. |

---

## 7. Client-side / browser (not env vars, but real dependencies)

| Done | Item |
|------|------|
| ☐ | **Google Fonts** — pages that use `caveat_font.html` load fonts from `fonts.googleapis.com` / `fonts.gstatic.com`. If blocked (corporate proxy), the footer “author” font falls back. |
| ☐ | **jsDelivr / Bootstrap** — some templates load CSS/JS from `cdn.jsdelivr.net`. |

No server “subscription” is required, but **firewall / CSP** must allow these if you want identical UI to local dev.

---

## 8. Post-deploy smoke tests (quick)

| Done | Item |
|------|------|
| ☐ | HTTPS loads; login works. |
| ☐ | One form submission with upload works (Cloudinary). |
| ☐ | One API path that should be rate-limited behaves as expected (if Redis on). |
| ☐ | Optional: one email event works. |

---

## Reference: what fails fast at startup (production)

If misconfigured, `common/config_validator.validate_config` can **abort** startup. In production it checks among other things:

- Strong **SECRET_KEY** / **JWT_SECRET_KEY**
- **DATABASE_URL** present and not SQLite
- **Cloudinary** name + API key + secret
- **DEBUG** not on

Warnings (non-fatal) include missing **REDIS_URL** and bad/missing **APP_BASE_URL**.

---

*Last aligned with `config.py`, `common/config_validator.py`, and `.env.example`.*
