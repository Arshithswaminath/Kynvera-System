# Kynvera Hub — three apps, three URLs

Kynvera Home (`kynvera-main`) is a **portal**. The public main page is the **marketing landing** at `/` with **two applications**: Fire System and Ajman Municipality. Each product stays on its own branch and URL. One login on the portal opens either app via SSO.

## Branch → service map

| Git branch | Role | Example service | Example URL env |
|------------|------|-----------------|-----------------|
| `kynvera-main` | Portal (landing + login + launch) | `kynvera-home` | `KYNVERA_HOME_URL` |
| `kynvera-fire-system-application` | Fire System product | `kynvera-fire` | `KYNVERA_FIRE_APP_URL` |
| `ajman-municipality` | Municipality product | `kynvera-muni` | `KYNVERA_MUNICIPALITY_APP_URL` |

Do **not** merge product feature sets into one homepage. Keep product modules inside their own apps.

## Public landing (`/`)

- Template: `templates/landing.html` (+ `partials/landing_head.html`, `partials/landing_nav.html`, `partials/landing_footer.html`, `partials/landing_app_mock.html`, `static/css/landing.css`, `static/js/landing.js`)
- App grid: **Fire System** → `/launch/fire`, **Ajman Municipality** → `/launch/municipality`
- **Sign in** → `/login` as usual. The primary CTA is now **Explore applications** → `/applications`, and pricing/closing CTAs point at `/applications#contact` (the landing page sells; account creation happens after contact). `/register` is still linked from the footer.
- Post-login `/dashboard` remains a slim hub with the same two launchers

## Product showcase (`/applications`)

Public sales page for the two products, in the same landing theme.

- Template: `templates/applications.html` (+ `static/css/applications.css`, `static/js/applications.js`, `partials/landing_icons.html`)
- Copy, capability bullets, module tiles, stats and screenshot manifests live in **`common/showcase.py`** — the single place to edit page content. `CONTACT` there holds the sales email, phone and meeting link (placeholders until the real ones are set).
- Screenshots are served from `static/images/kynvera/showcase/` as WebP, built from `screenshots/` captures:

```bash
# Operations Suite — build from an existing capture in this repo
python scripts/build_showcase_images.py --set ops \
    --source screenshots/full_pages/desktop_1920x1080_20260729_1713
```

Fire System runs on its own branch, and `capture_full_page_screenshots.py` enumerates routes from the Flask app it imports locally. So capture **from the Fire worktree** (not from the portal), then copy the folder over and build:

```bash
# in the kynvera-fire-system-application worktree, with that app running
python scripts/capture_full_page_screenshots.py --base-url http://127.0.0.1:5002 \
    --desktop --viewport 1920x1080 --zoom 100 --stamp fire_showcase \
    --login-user admin --login-password '<password>'

# back in kynvera-main
python scripts/build_showcase_images.py --set fire \
    --source <fire-worktree>/screenshots/full_pages/fire_showcase
```

The `fire` mapping in `scripts/build_showcase_images.py` guesses the Fire route file names; adjust the left-hand side of that dict to whatever the capture actually produced, or convert files one at a time with `--one <path> --as fire-dashboard.webp`.

`showcase_apps()` filters out screenshot entries whose file is missing, so a product with no captures falls back to the CSS mock in `partials/landing_app_mock.html` instead of rendering broken images. Drop the files in and they appear.

- The inquiry form has no backend yet: it composes a prefilled `mailto:` in `static/js/applications.js`. Swap that for a POST endpoint when one exists.

## Portal-only process (`KYNVERA_HUB_MODE=true`)

On `kynvera-main`, hub mode **does not import or register** product blueprints (HR, Store, Inspection, Ops, Finance, Ticketing, HVAC, MMR, Assistant, workflow, DocHub, reports). The portal process only needs:

- Landing, showcase + hub launch routes (`/`, `/applications`, `/launch/*`, `/api/hub/config`, `/dashboard`)
- Auth (`/login`, `/register`, `/api/auth`)
- Admin API + `/admin/dashboard` (user entitlements: `access_fire_app`, `access_municipality_app`)

Full pre-slim tree is preserved on branch `kynvera-main-backup`. Product modules run on their own branches/services.

## Environment variables

Shared across portal + products that use SSO:

| Variable | Where | Purpose |
|----------|--------|---------|
| `JWT_SECRET_KEY` | All three | **Must match** for SSO handoff |
| `DATABASE_URL` | Usually shared for one login | Same user table so tokens resolve |
| `KYNVERA_HUB_MODE` | Portal: `true` (default on `kynvera-main`). Products: `false` | Portal hub behavior |
| `KYNVERA_HOME_URL` | Fire + Municipality | Navbar “Kynvera Home” back-link |
| `KYNVERA_FIRE_APP_URL` | Portal | Launcher target for Fire |
| `KYNVERA_MUNICIPALITY_APP_URL` | Portal | Launcher target for Municipality |
| `APP_BASE_URL` | Each service | That service’s own public URL |

## Launch + SSO flow

1. User opens `/` (landing) and clicks **Fire System** or **Ajman Municipality**.
2. Browser hits `/launch/fire` or `/launch/municipality`.
3. If not logged in → `/login?next=/launch/...` (login honors `next`).
4. After login → launch page reads JWT from `localStorage`, checks entitlement, redirects to `{APP_URL}/sso/consume?token=...&next=/dashboard`.
5. Product app validates JWT, stores token, opens its dashboard.
6. Product navbar **Kynvera Home** → `KYNVERA_HOME_URL` (usually the portal `/`).

If the product has a different user database, SSO will fail against `/api/auth/me`; the user can still sign in on that app’s `/login`.

## Entitlements (portal)

Admin → user profile → Module access:

- **Fire System Application** → `access_fire_app`
- **Municipality Application** → `access_municipality_app`

Admins can launch both. Users without a flag see a “no access” message on `/launch/...`. Product-internal flags (`access_hvac`, HR, etc.) still apply **inside** each product app.

Migration: `migrations/versions/20260729_hub_apps.py` (also added via inline DDL unless `FLASK_SKIP_INLINE_DDL=1`).

## Local smoke test (three ports)

```bash
# Terminal A — portal (kynvera-main)
export KYNVERA_HUB_MODE=true
export KYNVERA_FIRE_APP_URL=http://127.0.0.1:5002
export KYNVERA_MUNICIPALITY_APP_URL=http://127.0.0.1:5003
export JWT_SECRET_KEY=dev-shared-jwt
./run   # typically :5001 — open http://127.0.0.1:5001/

# Terminal B — Fire (worktree of kynvera-fire-system-application)
export KYNVERA_HUB_MODE=false
export KYNVERA_HOME_URL=http://127.0.0.1:5001
export JWT_SECRET_KEY=dev-shared-jwt
PORT=5002 ./run

# Terminal C — Municipality (worktree of ajman-municipality)
export KYNVERA_HUB_MODE=false
export KYNVERA_HOME_URL=http://127.0.0.1:5001
export JWT_SECRET_KEY=dev-shared-jwt
PORT=5003 ./run
```

Checklist:

1. Open portal `/` → see only Fire System + Ajman Municipality tiles.
2. Click Fire → sign in if needed → lands on Fire `/dashboard` without a second login.
3. Click **Kynvera Home** on the product → back to portal landing.
4. Same for Municipality.

## Render

Create three web services, each pinned to its branch, with the env vars above.

- Portal (`kynvera-main` / `render.yaml` service `kynvera-home`): `KYNVERA_HUB_MODE=true`, set `KYNVERA_FIRE_APP_URL` and `KYNVERA_MUNICIPALITY_APP_URL` to the public product URLs. No RQ/MMR worker is required on the portal.
- Fire + Municipality: `KYNVERA_HUB_MODE=false`, `KYNVERA_HOME_URL` → portal public URL, shared `JWT_SECRET_KEY` / usually shared `DATABASE_URL`.

Point portal `KYNVERA_*_APP_URL` at the public Render URLs of the product services.
