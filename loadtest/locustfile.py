"""Locust load/stress test for the Injaaz app — LOCAL MACHINE ONLY.

This exists to find real problems under concurrency on your own laptop/dev
box (slow endpoints, N+1 queries, memory growth, cache/rate-limiter quirks)
— it is NOT for staging or production, and it is NOT literal capacity
planning. Never point --host at anything but a server you started locally
for this purpose.


HOW TO RUN
==========

1. Seed a dedicated load-test database (never the real dev DB — see
   scripts/seed_load_test_data.py's own docstring for the full safety
   rationale):

       DATABASE_URL=sqlite:////absolute/path/to/instance/loadtest.db \\
           python scripts/seed_load_test_data.py
       # or, to accept the built-in default (instance/loadtest.db):
       python scripts/seed_load_test_data.py

   Bump volume with env vars as needed, e.g.:
       LOADTEST_USERS=500 LOADTEST_TICKETS=8000 python scripts/seed_load_test_data.py

2. Start the app under gunicorn, multi-worker (matches production's
   assumption), pointed at the SAME database you just seeded:

       SECRET_KEY=loadtest-secret-not-for-prod \\
       JWT_SECRET_KEY=loadtest-jwt-secret-not-for-prod \\
       DATABASE_URL=sqlite:////absolute/path/to/instance/loadtest.db \\
       ASSISTANT_LLM_ENABLED=false \\
       GOOGLE_DRIVE_ENABLED=false \\
       RATELIMIT_DEFAULT="100000 per hour" \\
       gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app

   config.py only hard-requires DATABASE_URL when FLASK_ENV=production (it
   defaults to development, where SECRET_KEY/JWT_SECRET_KEY fall back to
   insecure defaults) — but set all three explicitly above anyway, matching
   what .github/workflows/ci.yml sets for the test suite. Do NOT set
   FLASK_ENV=production for this — that flips on config.py's production
   validator, which hard-requires Cloudinary credentials this harness has
   no reason to configure.

   RATELIMIT_DEFAULT is not optional for a meaningful run — see "RATE
   LIMITING" below; without it the app caps at ~100 requests/hour from your
   IP, full stop, and Locust will drown in 429s almost immediately.

3. Run Locust against it — web UI:

       locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000
       # then open http://localhost:8089

   or headless:

       locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 \\
           --headless -u 25 -r 5 -t 3m

4. Recommended ramp profile — three stages, each held ~2-3 minutes so you
   can watch p95/p99 latency and error rate stabilize before stepping up:

       1 → 25 → 100 concurrent users, spawn rate ~5/s per stage.

   Easiest as three sequential headless runs:
       locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 --headless -u 1   -r 1 -t 2m
       locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 --headless -u 25  -r 5 -t 3m
       locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 --headless -u 100 -r 5 -t 3m


THIRD-PARTY NETWORK CALLS — READ BEFORE YOU RUN THIS
======================================================

This file must never cause a request to a real third-party service:

  * LLM (Kynvera Assistant): start the server with ASSISTANT_LLM_ENABLED=false
    (config.py honours this) so the assistant module never calls Claude/OpenAI.
  * Google Drive: start the server with GOOGLE_DRIVE_ENABLED=false so the
    Files-module Drive sync path never fires.
  * Email: do NOT set BREVO_API_KEY / MAILJET_API_KEY / MAIL_* SMTP
    credentials when starting the server for this. Checked common/email_service.py
    directly — `send_email()` -> `_deliver_email()` returns False and logs a
    warning ("Mail not configured...") when no provider is configured; it
    never raises and never attempts a socket/HTTP call. So it's safe to leave
    unconfigured — any code path a Locust task happens to hit that tries to
    send an email (e.g. ticket-assignment notifications) will just no-op.
  * Geocoding: module_ticketing/routes.py's `/tickets/api/geocode` endpoint
    (backed by `_geocode_site_query`) calls `requests.get('https://nominatim.
    openstreetmap.org/...')` directly — there is NO app-level kill switch for
    it. This file deliberately does NOT include a geocode task anywhere,
    for any user class. If you want geocode coverage, stand up your own
    local stub that returns canned Nominatim-shaped JSON and repoint it via
    /etc/hosts or a config override — out of scope here on purpose.


RATE LIMITING — THIS WILL SURPRISE YOU (verified empirically, not just read
from source — see below)
============================================================================

Flask-Limiter is wired up in Injaaz.py with:

    default_limits=[os.environ.get('RATELIMIT_DEFAULT', '100 per hour')]
    key_func=get_remote_address

`default_limits` applies to EVERY route in the app, not just auth — so by
default, a single source IP (which is all of them, since Locust runs
locally against 127.0.0.1) is capped at ~100 requests/hour ACROSS THE WHOLE
APPLICATION. Confirmed by hand: with RATELIMIT_DEFAULT unset, hammering a
single endpoint from one gunicorn worker returned 200 for requests 1-99 and
429 from request 100 onward, exactly as the default implies. A real Locust
run blows through 100 requests in well under a minute. Set RATELIMIT_DEFAULT
to something enormous (see step 2 above) before running this, or every task
class here will spend the whole run failing with 429s — which tells you
nothing about the app's actual performance.

Separately, POST /api/auth/login is *decorated* with its own
`@rate_limit_if_available('5 per minute')` — intended as tighter brute-force
protection on top of the global default. In manual testing against this
build (15 rapid-fire login attempts, single worker, well within one minute)
it never returned 429 — only the global default eventually kicks in. Reading
`rate_limit_if_available()` in app/auth/routes.py explains why: it calls
`current_app.limiter` and applies `limiter.limit(...)` to `login` ONCE, at
blueprint import time (when the decorator runs), not per-request. If no Flask
application context is pushed yet at that point in `create_app()`'s import
sequence, `current_app` raises and `get_limiter()` returns None, so the
decorator silently returns the *undecorated* view — permanently, for the
life of the process. That looks like exactly what's happening here: the
per-route 5/minute limit on login appears to never actually engage, and only
the global default_limits protect it. This is an app bug worth a look
independent of load testing (not fixed here — out of this script's scope,
and app/auth/routes.py isn't one of the files this task touches) but it does
mean the aggressive login-retry/backoff/token-caching machinery below is
currently more defensive than strictly necessary in this build. It's kept
anyway: it's cheap, correct regardless of whether that bug is ever fixed,
and still meaningfully cuts login volume against the global default limit
(see next paragraph).

Whether or not the per-route login limit engages, caching one access token
per seeded username (below) and reusing it for the whole Locust run is still
the right call — it means N simulated Locust users sharing a smaller pool of
seeded identities cost only as many logins as there are distinct identities,
not N, which also helps keep total request volume under the global
100/hour-by-default ceiling during ramp-up.

Also worth knowing: with no REDIS_URL set, the limiter falls back to
in-memory storage, which is per-process — under `gunicorn -w 4`, each worker
keeps its own independent counter for the global default, so the effective
ceiling under multi-worker gunicorn is actually up to ~4x the nominal limit,
unevenly, depending on which worker a given request lands on. That
inconsistency is itself worth knowing about if you're trying to reason about
rate-limit behavior from Locust's aggregate stats.


WHAT THIS FILE ASSUMES
=======================

* The seeded DB (scripts/seed_load_test_data.py) created deterministic
  users named `loadtest_technician_N` / `loadtest_supervisor_N` /
  `loadtest_admin_N`, all sharing one password (default "LoadTest#2024",
  override via LOADTEST_PASSWORD — must match what you seeded with).
* This file reads the SAME DATABASE_URL (or the same instance/loadtest.db
  default) directly, once, to pull candidate usernames and ticket_ids —
  it is a read-only lookup via SQLAlchemy `create_engine`, not the Flask app
  itself, so `locust -f loadtest/locustfile.py --list` works even before
  you've seeded anything (the DB query is lazy; empty pools just mean
  affected tasks quietly skip themselves instead of erroring).
"""
import itertools
import logging
import os
import random
import time

from locust import HttpUser, between, task

logger = logging.getLogger("loadtest")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATABASE_URL = f"sqlite:///{os.path.join(_REPO_ROOT, 'instance', 'loadtest.db')}"
LOADTEST_PASSWORD = os.environ.get("LOADTEST_PASSWORD", "LoadTest#2024")

# username -> access_token, shared across every simulated user for the whole
# Locust run. See "RATE LIMITING" above for why this matters.
_token_cache = {}
_pools = None


def _load_pools():
    """One-time, lazy read of the seeded DB for candidate usernames/ticket_ids.

    Lazy on purpose: importing this module (e.g. for `locust --list`) must
    not require the DB to exist yet.
    """
    global _pools
    if _pools is not None:
        return _pools

    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            technicians = [r[0] for r in conn.execute(text(
                "SELECT username FROM users WHERE username LIKE 'loadtest_technician_%' ORDER BY username"
            ))]
            supervisors = [r[0] for r in conn.execute(text(
                "SELECT username FROM users WHERE username LIKE 'loadtest_supervisor_%' ORDER BY username"
            ))]
            admins = [r[0] for r in conn.execute(text(
                "SELECT username FROM users WHERE username LIKE 'loadtest_admin_%' ORDER BY username"
            ))]
            all_tickets = [r[0] for r in conn.execute(text(
                "SELECT ticket_id FROM tickets WHERE project LIKE 'LoadTest%' ORDER BY id"
            ))]
            # Tickets a technician may open the detail page for: assigned to them
            # (as technician or fallback assignee) or reported by them — matches
            # module_ticketing/routes.py::_can_user_view_ticket. Any status.
            tech_view_rows = conn.execute(text(
                """
                SELECT DISTINCT t.ticket_id, u.username
                FROM tickets t
                JOIN users u
                  ON u.id = t.technician_id OR u.id = t.assigned_to_id OR u.id = t.reporter_id
                WHERE t.project LIKE 'LoadTest%' AND u.username LIKE 'loadtest_technician_%'
                """
            )).fetchall()
            # Narrower subset: technician-owned tickets still in a status the
            # technician-facing /advance endpoint will accept.
            tech_advance_rows = conn.execute(text(
                """
                SELECT t.ticket_id, u.username
                FROM tickets t
                JOIN users u ON u.id = t.technician_id
                WHERE t.project LIKE 'LoadTest%'
                  AND t.status IN ('assigned', 'site_attended', 'work_started', 'in_progress', 'pending_parts')
                  AND u.username LIKE 'loadtest_technician_%'
                """
            )).fetchall()
            # Tickets a supervisor may open: they're the ticket's supervisor_id,
            # or it's sitting in the shared open/pending_supervisor queue (visible
            # to every supervisor-pool member per _user_in_supervisor_pool()).
            sup_view_rows = conn.execute(text(
                """
                SELECT t.ticket_id, u.username
                FROM tickets t
                JOIN users u ON u.id = t.supervisor_id
                WHERE t.project LIKE 'LoadTest%' AND u.username LIKE 'loadtest_supervisor_%'
                """
            )).fetchall()
            open_queue_tickets = [r[0] for r in conn.execute(text(
                "SELECT ticket_id FROM tickets WHERE project LIKE 'LoadTest%' "
                "AND status IN ('open', 'pending_supervisor')"
            ))]
    except Exception:
        logger.exception(
            "Could not read the load-test DB at %s — has scripts/seed_load_test_data.py "
            "been run, and does DATABASE_URL here match what you seeded? Falling back to "
            "empty pools; every task will skip itself.", db_url,
        )
        technicians = supervisors = admins = all_tickets = []
        tech_view_rows = tech_advance_rows = sup_view_rows = []
        open_queue_tickets = []

    tech_view_tickets = {}
    for ticket_id, username in tech_view_rows:
        tech_view_tickets.setdefault(username, []).append(ticket_id)

    tech_tickets = {}
    for ticket_id, username in tech_advance_rows:
        tech_tickets.setdefault(username, []).append(ticket_id)

    sup_view_tickets = {}
    for ticket_id, username in sup_view_rows:
        sup_view_tickets.setdefault(username, []).append(ticket_id)
    for sup_username in supervisors:
        # Every supervisor can also see the shared open/pending_supervisor queue.
        sup_view_tickets.setdefault(sup_username, []).extend(open_queue_tickets)

    if not (technicians and supervisors and admins and all_tickets):
        logger.warning(
            "loadtest DB has no loadtest_* users/tickets yet (or DATABASE_URL points "
            "somewhere unseeded) — run scripts/seed_load_test_data.py against the same "
            "DATABASE_URL you're starting the server with."
        )

    _pools = {
        "technicians": technicians,
        "supervisors": supervisors,
        "admins": admins,
        "all_tickets": all_tickets,
        "tech_view_tickets": tech_view_tickets,
        "tech_tickets": tech_tickets,
        "sup_view_tickets": sup_view_tickets,
        "tech_cycle": itertools.cycle(technicians) if technicians else None,
        "sup_cycle": itertools.cycle(supervisors) if supervisors else None,
        "admin_cycle": itertools.cycle(admins) if admins else None,
    }
    return _pools


def _login(client, username):
    """Log in as `username`, caching the token so repeat calls (across every
    simulated user that happens to share this seeded identity) are free.

    Retries POST /api/auth/login with backoff on 429 — expected under local
    single-IP testing (see module docstring's RATE LIMITING section) — and
    marks those 429s as non-failures precisely because they're an artifact
    of this test setup, not a bug in the app.
    """
    cached = _token_cache.get(username)
    if cached:
        return cached

    deadline = time.time() + 180  # give the shared login limiter time to free up
    backoff = 2.0
    while True:
        with client.post(
            "/api/auth/login",
            json={"username": username, "password": LOADTEST_PASSWORD},
            name="/api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                token = body.get("access_token")
                if token:
                    _token_cache[username] = token
                    resp.success()
                    return token
                resp.failure("login returned 200 but no access_token in body")
                return None
            if resp.status_code == 429:
                resp.success()  # expected — see RATE LIMITING in the module docstring
            else:
                resp.failure(f"login failed: {resp.status_code} {resp.text[:200]}")
                return None
        if time.time() > deadline:
            logger.warning("Giving up logging in as %s — still 429ing after 180s", username)
            return None
        time.sleep(backoff + random.random())
        backoff = min(backoff * 1.6, 20.0)


def _auth_get(user, path, name=None, ok_statuses=(200,)):
    """GET with the cached bearer token. Evicts the token on 401 (next task
    will re-login) and treats a real 429 here as a genuine failure — this is
    NOT the login endpoint, so if you're seeing these, RATELIMIT_DEFAULT
    wasn't raised on the server (see module docstring)."""
    if not user.token:
        return None
    with user.client.get(
        path, headers={"Authorization": f"Bearer {user.token}"},
        name=name or path, catch_response=True,
    ) as resp:
        _resolve(user, resp, ok_statuses)
        return resp


def _auth_post(user, path, name=None, json_body=None, ok_statuses=(200,)):
    if not user.token:
        return None
    with user.client.post(
        path, json=(json_body or {}), headers={"Authorization": f"Bearer {user.token}"},
        name=name or path, catch_response=True,
    ) as resp:
        _resolve(user, resp, ok_statuses)
        return resp


def _resolve(user, resp, ok_statuses):
    if resp.status_code in ok_statuses:
        resp.success()
    elif resp.status_code == 401:
        _token_cache.pop(user.username, None)
        user.token = None
        resp.failure("401 — token invalidated, will re-login before the next task")
    elif resp.status_code == 429:
        resp.failure("429 — rate limited; raise RATELIMIT_DEFAULT on the server (see module docstring)")
    else:
        resp.failure(f"unexpected status {resp.status_code}")


# ---------------------------------------------------------------------------
# Technician — polls their queue, opens ticket detail, advances work they own.
# ---------------------------------------------------------------------------

class TechnicianUser(HttpUser):
    weight = 6
    wait_time = between(2, 6)

    def on_start(self):
        pools = _load_pools()
        if not pools["technicians"]:
            self.username = None
            self.token = None
            self.viewable_tickets = []
            self.my_tickets = []
            return
        self.username = next(pools["tech_cycle"])
        self.token = _login(self.client, self.username)
        # Tickets this technician is actually allowed to open (reporter/assigned/
        # technician on it) — NOT the global all_tickets pool, which would 403
        # for most random picks since _can_user_view_ticket() is per-ticket ACL,
        # not role-wide visibility, for a plain technician.
        self.viewable_tickets = list(pools["tech_view_tickets"].get(self.username, []))
        # Narrower subset still in an /advance-eligible status.
        self.my_tickets = list(pools["tech_tickets"].get(self.username, []))

    @task(8)
    def view_ticket_detail(self):
        if not self.token or not self.viewable_tickets:
            return
        ticket_id = random.choice(self.viewable_tickets)
        _auth_get(self, f"/tickets/{ticket_id}", name="/tickets/[ticket_id]")

    @task(5)
    def list_tickets(self):
        if not self.token:
            return
        _auth_get(self, "/tickets/list", name="/tickets/list")

    @task(3)
    def advance_my_ticket(self):
        if not self.token or not self.my_tickets:
            return
        ticket_id = random.choice(self.my_tickets)
        # 400 = "Cannot advance from status X" — expected once concurrent
        # advances (or an earlier iteration on this same ticket) have already
        # moved it past the technician-advanceable stages. Not a failure.
        _auth_post(
            self, f"/tickets/api/tickets/{ticket_id}/advance",
            name="/tickets/api/tickets/[ticket_id]/advance",
            ok_statuses=(200, 400),
        )


# ---------------------------------------------------------------------------
# Supervisor — reviews the pending-approvals queue, checks ticket dashboards.
# ---------------------------------------------------------------------------

class SupervisorUser(HttpUser):
    weight = 3
    wait_time = between(2, 6)

    def on_start(self):
        pools = _load_pools()
        if not pools["supervisors"]:
            self.username = None
            self.token = None
            self.viewable_tickets = []
            return
        self.username = next(pools["sup_cycle"])
        self.token = _login(self.client, self.username)
        # Tickets where this user is the supervisor, plus the shared open/
        # pending_supervisor queue every supervisor-pool member can see — NOT
        # the global all_tickets pool (would 403 for most random picks; a plain
        # 'supervisor' designation only grants role-wide visibility for that
        # shared queue, not every ticket in the system).
        self.viewable_tickets = list(pools["sup_view_tickets"].get(self.username, []))

    @task(5)
    def dashboard(self):
        if not self.token:
            return
        _auth_get(self, "/tickets/", name="/tickets/ (dashboard)")

    @task(5)
    def ticket_list(self):
        if not self.token:
            return
        _auth_get(self, "/tickets/list", name="/tickets/list")

    @task(6)
    def pending_submissions(self):
        if not self.token:
            return
        _auth_get(self, "/api/workflow/submissions/pending", name="/api/workflow/submissions/pending")

    @task(3)
    def dashboard_stats(self):
        if not self.token:
            return
        _auth_get(self, "/api/workflow/dashboard-stats", name="/api/workflow/dashboard-stats")

    @task(2)
    def ticket_detail(self):
        if not self.token or not self.viewable_tickets:
            return
        ticket_id = random.choice(self.viewable_tickets)
        _auth_get(self, f"/tickets/{ticket_id}", name="/tickets/[ticket_id]")


# ---------------------------------------------------------------------------
# Admin — dashboards plus the CPU-heavy export/PDF endpoints. Those are
# weighted low (~1 in 11 tasks in this class) so they get real coverage
# without dominating every request, per the brief.
# ---------------------------------------------------------------------------

class AdminUser(HttpUser):
    weight = 1
    wait_time = between(3, 8)

    def on_start(self):
        pools = _load_pools()
        self.all_tickets = pools["all_tickets"]
        if not pools["admins"]:
            self.username = None
            self.token = None
            return
        self.username = next(pools["admin_cycle"])
        self.token = _login(self.client, self.username)

    @task(14)
    def dashboard(self):
        if not self.token:
            return
        _auth_get(self, "/tickets/", name="/tickets/ (dashboard)")

    @task(10)
    def ticket_list(self):
        if not self.token:
            return
        _auth_get(self, "/tickets/list", name="/tickets/list")

    @task(6)
    def admin_dashboard_page(self):
        if not self.token:
            return
        _auth_get(self, "/admin/dashboard", name="/admin/dashboard")

    @task(1)
    def download_ticket_pdf(self):
        if not self.token or not self.all_tickets:
            return
        ticket_id = random.choice(self.all_tickets)
        _auth_get(self, f"/tickets/{ticket_id}/pdf", name="/tickets/[ticket_id]/pdf")

    @task(1)
    def export_tickets_excel(self):
        if not self.token:
            return
        _auth_get(self, "/tickets/api/tickets/export", name="/tickets/api/tickets/export")

    @task(1)
    def export_locations_excel(self):
        if not self.token:
            return
        _auth_get(
            self, "/tickets/api/settings/standalone/locations/export",
            name="/tickets/api/settings/standalone/locations/export",
        )
