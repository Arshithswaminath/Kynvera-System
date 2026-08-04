# Full Render Deploy Guide — Kynvera (3 apps)

Deploy a **new Kynvera stack** on Render with custom domains.

| App | Render service | Git branch | Public URL |
|-----|----------------|------------|------------|
| Kynvera Home (portal) | `kynvera-home` | `kynvera-main` | `https://kynvera.net` |
| Fire System | `kynvera-fire` | `kynvera-fire-system-application` | `https://fire.kynvera.net` |
| Operations Suite | `kynvera-operations` | `ajman-municipality` | `https://operation-kynvera.net` |

| Item | Value |
|------|--------|
| GitHub repo | `arshithinjaaz/Injaaz-App` |
| Shared Postgres | `kynvera-db` |
| Portal blueprint (reference) | [`render.yaml`](../render.yaml) on `kynvera-main` |
| Hub / SSO architecture | [`docs/KYNVERA_HUB.md`](KYNVERA_HUB.md) |
| Local env template | [`.env.example`](../.env.example) |
| Render phases (disk, Redis, email) | [`RENDER_DEPLOYMENT_PHASES.md`](../RENDER_DEPLOYMENT_PHASES.md) |
| Email options | [`docs/EMAIL_SMTP_OPTIONS.md`](EMAIL_SMTP_OPTIONS.md) (if present) or `.env.example` email section |
| Production checklist | [`docs/PRODUCTION_DEPENDENCIES_CHECKLIST.md`](PRODUCTION_DEPENDENCIES_CHECKLIST.md) |

**Do not commit real secrets** to git. Put them only in Render → Environment (or a password manager).

---

## 1. Places to look (master directory)

Use this when you need a value and do not remember where it lives.

### 1.1 External dashboards & accounts

| What you need | Where to look | Exact path / action |
|---------------|---------------|---------------------|
| Render account / services | [dashboard.render.com](https://dashboard.render.com) | Left sidebar → your workspace → Web Services / PostgreSQL |
| `DATABASE_URL` | Render → Postgres `kynvera-db` | Open DB → **Info** / **Connect** → **Internal Database URL** (prefer Internal when web services are on Render). Or when creating a Web Service, **Link Database** so Render injects `DATABASE_URL`. |
| Service env vars (edit later) | Render → each Web Service | Service → **Environment** tab |
| Deploy logs / errors | Render → each Web Service | Service → **Logs** (and **Events** for deploy status) |
| Custom domain DNS targets | Render → each Web Service | Service → **Settings** → **Custom Domains** → copy CNAME / apex instructions Render shows |
| Health after deploy | Browser | `https://<service>.onrender.com/health` then custom domain `/health` |
| GitHub repo / branches | [github.com/arshithinjaaz/Injaaz-App](https://github.com/arshithinjaaz/Injaaz-App) | Branches: `kynvera-main`, `kynvera-fire-system-application`, `ajman-municipality` |
| Cloudinary cloud name / keys | [console.cloudinary.com](https://console.cloudinary.com) | Dashboard home → **Cloud name**, **API Key**, **API Secret**. Upload preset: **Settings** → **Upload** → **Upload presets**. |
| Brevo API key (email on free Render) | [app.brevo.com](https://app.brevo.com) | **SMTP & API** → **API keys** → create key (`xkeysib-...`). Verify sender under **Senders**. |
| Mailjet keys (optional email) | [app.mailjet.com](https://app.mailjet.com) | **Account settings** → **SMTP and SEND API settings** → API Key + Secret Key |
| Redis (optional) | [console.upstash.com](https://console.upstash.com) | Create Redis → copy **Redis URL** with TLS (`rediss://...`) — no leading/trailing spaces |
| DNS for `kynvera.net` | Your domain registrar / DNS host | Wherever the domain was bought or DNS is managed (Cloudflare, GoDaddy, Namecheap, Google Domains, etc.) → DNS / Zone records |
| DNS for `operation-kynvera.net` | Registrar for that domain | Separate DNS zone if it is a different apex domain |
| Anthropic / OpenAI (optional Assistant) | [console.anthropic.com](https://console.anthropic.com) / [platform.openai.com](https://platform.openai.com) | API keys pages — only needed if Assistant LLM is enabled on a product |

### 1.2 Repo files (documentation & templates — no live secrets)

| File | What to look for |
|------|------------------|
| [`.env.example`](../.env.example) | Full list of common env keys + comments on how to generate / where to sign up |
| Local `.env` (gitignored) | Your machine’s current values — copy Cloudinary/email if already working locally; **never commit** |
| [`docs/KYNVERA_HUB.md`](KYNVERA_HUB.md) | Hub modes, SSO flow, launch URLs, local three-port smoke test |
| [`render.yaml`](../render.yaml) | Portal service shape on `kynvera-main` (`kynvera-home`, linked DB name, env keys) |
| [`build.sh`](../build.sh) | Exact build command Render should run |
| [`wsgi.py`](../wsgi.py) | Gunicorn entry (`wsgi:app`) |
| [`config.py`](../config.py) | Which env vars the app reads and defaults |
| [`RENDER_DEPLOYMENT_PHASES.md`](../RENDER_DEPLOYMENT_PHASES.md) | Disk, Redis, MMR, free-tier email limits |
| [`RENDER_DATABASE_SETUP.md`](../RENDER_DATABASE_SETUP.md) | Postgres / migration notes |
| Old Render service (e.g. `injaaz-app`) | **Environment** tab — reuse Cloudinary / Brevo / Redis if you want the same vendors |

### 1.3 Values you create yourself (not in a vendor dashboard)

| Variable | How to create | Notes |
|----------|---------------|--------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | One per service is fine |
| `JWT_SECRET_KEY` | Same command, **once** | **Must be identical** on portal + Fire + Operations |
| `DEFAULT_ADMIN_PASSWORD` | Choose a strong password | Used on first portal boot to seed admin |
| Hub / app URLs | Fixed for this project | See domain table at top of this doc |

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"
```

Save `JWT_SECRET_KEY` in a password manager — paste into **all three** Render services.

---

## 2. Complete env reference (every key + where + which services)

| Variable | Portal | Fire | Ops | Where to get / what to set |
|----------|:------:|:----:|:---:|----------------------------|
| `PYTHON_VERSION` | ✓ | ✓ | ✓ | Set manually: `3.11.0` |
| `FLASK_ENV` | ✓ | ✓ | ✓ | Set manually: `production` |
| `SECRET_KEY` | ✓ | ✓ | ✓ | Generate locally (section 1.3). Can differ per service |
| `JWT_SECRET_KEY` | ✓ | ✓ | ✓ | Generate once (1.3). **Same value on all three** |
| `DATABASE_URL` | ✓ | ✓ | ✓ | Render → `kynvera-db` → Connect → Internal URL (**same DB**) |
| `KYNVERA_HUB_MODE` | `true` | `false` | `false` | Set manually |
| `RUN_MMR_SCHEDULER` | `false` | — | — | Portal only — no MMR on hub |
| `APP_BASE_URL` | ✓ | ✓ | ✓ | That service’s public HTTPS URL (table at top) |
| `KYNVERA_HOME_URL` | ✓ | ✓ | ✓ | `https://kynvera.net` |
| `KYNVERA_FIRE_APP_URL` | ✓ | — | — | `https://fire.kynvera.net` (portal only) |
| `KYNVERA_MUNICIPALITY_APP_URL` | ✓ | — | — | `https://operation-kynvera.net` (portal only; env name still “municipality”) |
| `DEFAULT_ADMIN_PASSWORD` | ✓ | opt | opt | You choose; strongly recommended on portal |
| `SESSION_COOKIE_SECURE` | ✓ | ✓ | ✓ | Set `true` for HTTPS |
| `CLOUDINARY_CLOUD_NAME` | ✓ | ✓ | ✓ | Cloudinary Console → Dashboard |
| `CLOUDINARY_API_KEY` | ✓ | ✓ | ✓ | Cloudinary Console → Dashboard |
| `CLOUDINARY_API_SECRET` | ✓ | ✓ | ✓ | Cloudinary Console → Dashboard |
| `CLOUDINARY_UPLOAD_PRESET` | opt | opt | opt | Cloudinary → Settings → Upload → presets |
| `BREVO_API_KEY` | opt* | opt* | opt* | Brevo → SMTP & API → API keys (*required if you need email on free Render) |
| `MAIL_DEFAULT_SENDER` | with Brevo | with Brevo | with Brevo | Address verified in Brevo (e.g. `noreply@kynvera.net`) |
| `MAILJET_API_KEY` | opt | opt | opt | Mailjet SMTP & API (alternative to Brevo) |
| `MAILJET_SECRET_KEY` | opt | opt | opt | Mailjet |
| `REDIS_URL` | opt | opt | opt | Upstash → Redis URL (`rediss://...`) |
| `GENERATED_DIR` | rare | Phase 2 | Phase 2 | After Render Disk mount `/var/data` → set `/var/data/generated` |
| `MMR_SCHEDULE_ENABLED` | — | opt | opt | `true` / `false` — see `RENDER_DEPLOYMENT_PHASES.md` |
| `MMR_SCHEDULE_HOUR` | — | opt | opt | `0`–`23` (UTC / server time — confirm in MMR docs) |
| `MMR_SCHEDULE_MINUTE` | — | opt | opt | `0`–`59` |
| `WEB_CONCURRENCY` | opt | opt | opt | e.g. `2` on portal; products often `1` with disk |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | opt | opt | Vendor consoles — only if Assistant LLM enabled |

### Reusing an old Injaaz Render service

If `injaaz-app` (or similar) already exists:

1. Render → that service → **Environment**
2. Copy: `CLOUDINARY_*`, `BREVO_API_KEY` / Mailjet, `REDIS_URL`, `MAIL_DEFAULT_SENDER`
3. Prefer a **new** Postgres `kynvera-db` for the Kynvera hub
4. Set a **new shared** `JWT_SECRET_KEY` for the three Kynvera services (do not mix with unrelated apps unless they must SSO together)

---

## 3. Before you start

- [ ] Render account
- [ ] GitHub access to `arshithinjaaz/Injaaz-App`
- [ ] Branches exist on remote: `kynvera-main`, `kynvera-fire-system-application`, `ajman-municipality`
- [ ] DNS control for `kynvera.net` and `operation-kynvera.net`
- [ ] Cloudinary account (or keys copied from old Render)
- [ ] Brevo (or Mailjet) if you need email
- [ ] Generated `JWT_SECRET_KEY` saved somewhere safe
- [ ] Chosen `DEFAULT_ADMIN_PASSWORD`

---

## 4. Phase 1 — Create the database

**Where:** [dashboard.render.com](https://dashboard.render.com) → **New** → **PostgreSQL**

1. Settings:
   - **Name:** `kynvera-db`
   - **Database:** `kynvera`
   - **User:** `kynvera_user`
   - Region: pick one and reuse for all web services
   - Plan: free for testing, paid for production
2. Create → wait until **Available**
3. Open the DB → **Connect** → copy **Internal Database URL**  
   This becomes `DATABASE_URL` on all three web services (or use **Link Database** in the UI).

---

## 5. Phase 2 — Deploy Kynvera Home (portal)

**Where:** Render → **New** → **Web Service** → connect GitHub repo `Injaaz-App`

### 5.1 Service settings

| Field | Value |
|-------|--------|
| Name | `kynvera-home` |
| Region | same as `kynvera-db` |
| Branch | `kynvera-main` |
| Runtime | Python |
| Build Command | `bash build.sh` |
| Start Command | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --worker-class gthread` |
| Health Check Path | `/health` |
| Auto-Deploy | Yes |
| Instance type | Starter (or Free for test) |

Reference in repo: [`render.yaml`](../render.yaml).

### 5.2 Portal environment (copy into Render → Environment)

| Key | Value | Where / notes |
|-----|--------|----------------|
| `PYTHON_VERSION` | `3.11.0` | Manual |
| `FLASK_ENV` | `production` | Manual |
| `KYNVERA_HUB_MODE` | `true` | Manual |
| `RUN_MMR_SCHEDULER` | `false` | Manual |
| `SECRET_KEY` | *(generated)* | Section 1.3 |
| `JWT_SECRET_KEY` | *(shared)* | Section 1.3 — same on all 3 |
| `DATABASE_URL` | from `kynvera-db` | Section 1.1 |
| `DEFAULT_ADMIN_PASSWORD` | *(your password)* | You choose |
| `SESSION_COOKIE_SECURE` | `true` | Manual |
| `APP_BASE_URL` | `https://kynvera.net` | Final domain (use onrender URL temporarily until DNS) |
| `KYNVERA_HOME_URL` | `https://kynvera.net` | Final domain |
| `KYNVERA_FIRE_APP_URL` | `https://fire.kynvera.net` | Final domain |
| `KYNVERA_MUNICIPALITY_APP_URL` | `https://operation-kynvera.net` | Final domain |
| `CLOUDINARY_CLOUD_NAME` | … | Cloudinary Console |
| `CLOUDINARY_API_KEY` | … | Cloudinary Console |
| `CLOUDINARY_API_SECRET` | … | Cloudinary Console |
| `BREVO_API_KEY` | … | Brevo (if email) |
| `MAIL_DEFAULT_SENDER` | e.g. `noreply@kynvera.net` | Verified in Brevo |

Create → wait for green deploy.

### 5.3 Quick check

- Logs: Render → `kynvera-home` → **Logs**
- Health: `https://kynvera-home.onrender.com/health`
- Site: `https://kynvera-home.onrender.com/`

---

## 6. Phase 3 — Deploy Fire System

**Where:** Render → **New** → **Web Service** → same repo

| Field | Value |
|-------|--------|
| Name | `kynvera-fire` |
| Branch | `kynvera-fire-system-application` |
| Build | `bash build.sh` |
| Start | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 300 --worker-class gthread` |
| Health | `/health` |

| Key | Value | Where / notes |
|-----|--------|----------------|
| `PYTHON_VERSION` | `3.11.0` | Manual |
| `FLASK_ENV` | `production` | Manual |
| `KYNVERA_HUB_MODE` | `false` | Manual |
| `SECRET_KEY` | *(new random OK)* | Section 1.3 |
| `JWT_SECRET_KEY` | **same as portal** | Must match |
| `DATABASE_URL` | **same `kynvera-db`** | Must match |
| `SESSION_COOKIE_SECURE` | `true` | Manual |
| `APP_BASE_URL` | `https://fire.kynvera.net` | Final domain |
| `KYNVERA_HOME_URL` | `https://kynvera.net` | Portal URL |
| `CLOUDINARY_*` | same as portal | Cloudinary / old Render |
| `BREVO_API_KEY` / `MAIL_DEFAULT_SENDER` | if needed | Brevo |
| `REDIS_URL` | optional | Upstash |

Check: `https://kynvera-fire.onrender.com/health`

---

## 7. Phase 4 — Deploy Operations Suite

**Where:** Render → **New** → **Web Service** → same repo

| Field | Value |
|-------|--------|
| Name | `kynvera-operations` |
| Branch | `ajman-municipality` |
| Build | `bash build.sh` |
| Start | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 300 --worker-class gthread` |
| Health | `/health` |

| Key | Value | Where / notes |
|-----|--------|----------------|
| `PYTHON_VERSION` | `3.11.0` | Manual |
| `FLASK_ENV` | `production` | Manual |
| `KYNVERA_HUB_MODE` | `false` | Manual |
| `SECRET_KEY` | *(new random OK)* | Section 1.3 |
| `JWT_SECRET_KEY` | **same as portal** | Must match |
| `DATABASE_URL` | **same `kynvera-db`** | Must match |
| `SESSION_COOKIE_SECURE` | `true` | Manual |
| `APP_BASE_URL` | `https://operation-kynvera.net` | Final domain |
| `KYNVERA_HOME_URL` | `https://kynvera.net` | Portal URL |
| `CLOUDINARY_*` | same as portal | Cloudinary / old Render |
| `BREVO_API_KEY` / `MAIL_DEFAULT_SENDER` | if needed | Brevo |
| `REDIS_URL` | optional | Upstash |

Check: `https://kynvera-operations.onrender.com/health`

---

## 8. Phase 5 — Custom domains in Render

**Where for each service:** Service → **Settings** → **Custom Domains**

| Service | Domains to add |
|---------|----------------|
| `kynvera-home` | `kynvera.net`, `www.kynvera.net` |
| `kynvera-fire` | `fire.kynvera.net` |
| `kynvera-operations` | `operation-kynvera.net` (+ `www.operation-kynvera.net` optional) |

Copy the **exact** CNAME / apex target Render displays for each domain (do not guess).

---

## 9. Phase 6 — DNS at your registrar(s)

**Where:** DNS panel for each domain (Cloudflare / GoDaddy / Namecheap / etc.)

### A. Zone: `kynvera.net`

| Type | Host / Name | Value / Target | Looks like |
|------|-------------|----------------|------------|
| ALIAS / ANAME / apex method | `@` | value Render shows for portal | Render Custom Domains UI |
| CNAME | `www` | portal target from Render | often `kynvera-home.onrender.com` |
| CNAME | `fire` | Fire target from Render | often `kynvera-fire.onrender.com` |

### B. Zone: `operation-kynvera.net` (separate domain)

| Type | Host / Name | Value / Target |
|------|-------------|----------------|
| ALIAS / ANAME / apex | `@` | value Render shows for `kynvera-operations` |
| CNAME | `www` | same service target (optional) |

Notes:

- Prefer exact targets from Render UI.
- DNS can take minutes to hours.
- In Render, wait until each domain is **Verified** and certificate issued.
- If apex `kynvera.net` is hard: point apex → `www`, then set portal URL env vars to `https://www.kynvera.net`.

---

## 10. Phase 7 — Final env URLs + redeploy

**Where:** each service → **Environment** → save → **Manual Deploy**

After certificates are green:

**`kynvera-home`**

```text
APP_BASE_URL=https://kynvera.net
KYNVERA_HOME_URL=https://kynvera.net
KYNVERA_FIRE_APP_URL=https://fire.kynvera.net
KYNVERA_MUNICIPALITY_APP_URL=https://operation-kynvera.net
JWT_SECRET_KEY=<shared>
DATABASE_URL=<shared>
KYNVERA_HUB_MODE=true
```

**`kynvera-fire`**

```text
APP_BASE_URL=https://fire.kynvera.net
KYNVERA_HOME_URL=https://kynvera.net
JWT_SECRET_KEY=<shared>
DATABASE_URL=<shared>
KYNVERA_HUB_MODE=false
```

**`kynvera-operations`**

```text
APP_BASE_URL=https://operation-kynvera.net
KYNVERA_HOME_URL=https://kynvera.net
JWT_SECRET_KEY=<shared>
DATABASE_URL=<shared>
KYNVERA_HUB_MODE=false
```

If any service used “Generate” for `JWT_SECRET_KEY`, replace all three with the same value.

---

## 11. Phase 8 — First login & entitlements

**Where:** browser → `https://kynvera.net/login`  
**Admin password:** the value you set as `DEFAULT_ADMIN_PASSWORD` on portal  
**Entitlements UI:** portal Admin → user profile → Module access

Enable:

- **Fire System Application** → `access_fire_app`
- **Municipality / Operations Application** → `access_municipality_app`

Code / migration reference: `migrations/versions/20260729_hub_apps.py` (see [`KYNVERA_HUB.md`](KYNVERA_HUB.md)).

---

## 12. Phase 9 — End-to-end smoke test

On **custom domains**:

1. `https://kynvera.net` → landing loads  
2. `https://kynvera.net/health` → OK  
3. Sign in on portal  
4. Launch Fire → `https://fire.kynvera.net/...` without second login  
5. **Kynvera Home** → back to `https://kynvera.net`  
6. Launch Operations → `https://operation-kynvera.net/...` without second login  
7. User without Fire access → “no access”  
8. Spot-check one module in Fire and one in Operations  

If SSO fails, first check (Render → Environment on all three):

1. Identical `JWT_SECRET_KEY`
2. Identical `DATABASE_URL`
3. Portal launch URLs match real product domains

---

## 13. Phase 10 — Future code deploys

**Where code lives:** GitHub branches above  
**Where deploy happens:** Render auto-deploy on push (if enabled), or **Manual Deploy**

```bash
# Portal
git checkout kynvera-main
git push origin kynvera-main

# Fire
git checkout kynvera-fire-system-application
git push origin kynvera-fire-system-application

# Operations
git checkout ajman-municipality
git push origin ajman-municipality
```

Watch that service’s **Logs** until deploy finishes.

---

## 14. Phase 11 — Production hardening (recommended)

**Where:** Render → product service → **Disks** / plan upgrade  
**Docs:** [`RENDER_DEPLOYMENT_PHASES.md`](../RENDER_DEPLOYMENT_PHASES.md)

For Fire and Operations:

1. Upgrade to a plan that supports **Persistent Disk**
2. Mount disk at `/var/data`
3. Set `GENERATED_DIR=/var/data/generated`
4. Optional: Upstash → `REDIS_URL`
5. Upgrade Postgres when you need backups / higher limits
6. Portal can stay lighter (no MMR/RQ required)

---

## 15. Checklist

- [ ] `kynvera-db` created  
- [ ] `kynvera-home` on `kynvera-main` live  
- [ ] `kynvera-fire` on `kynvera-fire-system-application` live  
- [ ] `kynvera-operations` on `ajman-municipality` live  
- [ ] Same `DATABASE_URL` on all three  
- [ ] Same `JWT_SECRET_KEY` on all three  
- [ ] Custom domains verified + HTTPS  
- [ ] DNS for `kynvera.net`, `fire.kynvera.net`, `operation-kynvera.net`  
- [ ] Hub URL env vars set to final domains  
- [ ] Admin login works  
- [ ] Entitlements set  
- [ ] SSO Fire works  
- [ ] SSO Operations works  
- [ ] Home link from products works  

---

## 16. Common failures (symptom → where to look → fix)

| Symptom | Where to look | Fix |
|---------|---------------|-----|
| Deploy fails on pip | Service → **Logs** (build) | Ensure `requirements-prods.txt` + `build.sh` exist on that branch |
| App boots then 502 | Service → **Logs** (runtime) | Check `wsgi:app` import errors; confirm start command |
| SSO opens product then login again | All 3 → **Environment** | Match `JWT_SECRET_KEY` and `DATABASE_URL` |
| Launch goes to wrong host | Portal → **Environment** | Fix `KYNVERA_FIRE_APP_URL` / `KYNVERA_MUNICIPALITY_APP_URL` |
| Cookies / login weird on HTTPS | Service → **Environment** | `SESSION_COOKIE_SECURE=true`; all URLs use `https://` |
| Email fails on free Render | Brevo dashboard + env | Use `BREVO_API_KEY`, not Gmail SMTP |
| Uploads disappear after redeploy | Service → Disks + env | Attach disk; set `GENERATED_DIR` |
| “No access” on launch | Portal Admin UI | Grant `access_fire_app` / `access_municipality_app` |
| Domain not securing | Render Custom Domains + registrar DNS | Fix CNAME/ALIAS; wait for Verified + cert |
| Wrong branch deployed | Service → **Settings** → Build & Deploy | Confirm branch name |

---

## 17. Shortest click order

1. Create `kynvera-db`  
2. Create + deploy `kynvera-home`  
3. Create + deploy `kynvera-fire`  
4. Create + deploy `kynvera-operations`  
5. Add custom domains (Render Settings)  
6. Set DNS (registrar)  
7. Fix env URLs + shared JWT  
8. Redeploy all three  
9. Login → entitlements → SSO test  
