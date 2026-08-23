# Local Load-Test Harness — 2026-08-21

A local-only load/stress-testing harness for finding real performance problems (slow
endpoints, N+1 queries, memory growth, cache/rate-limiter quirks) before they show up
as production incidents. Per scope, this runs against the app on a local machine only —
it is not a production capacity plan, and no run was made against any shared or
production system. See `docs/coverage-report-2026-08-21.md` for the test-coverage half
of this effort.

## What was built

**`scripts/seed_load_test_data.py`** — generates a synthetic dataset at volume, since
the real dev DB (`injaaz.db`) only has 33 tickets and 6 users, nowhere near enough to
stress list/filter/pagination code paths. Modeled on the existing
`scripts/seed_ticketing_data.py`'s get-or-create pattern. Configurable via env vars
(`LOADTEST_USERS`, `LOADTEST_TICKETS`, `LOADTEST_PROJECTS`, ...), defaults to a
dedicated `instance/loadtest.db` and refuses to run against `sqlite:///:memory:` or a
path literally named `injaaz.db` (override requires `LOADTEST_ALLOW_UNSAFE_DB=true`) —
so it can't accidentally clobber real dev or test data. Generates users across all four
roles with realistic `access_*` distributions, a location hierarchy an order of
magnitude larger than the demo seed, and thousands of tickets across the real status
set (`open/assigned/site_attended/work_started/work_completed/verification/
provider_closed/on_hold/cancelled/closed`) with correctly wired foreign keys.

**`loadtest/locustfile.py`** — three weighted Locust user classes mirroring real usage:

- `TechnicianUser` — polls/updates the tickets they're actually assigned to.
- `SupervisorUser` — reviews and approves via the workflow endpoints.
- `AdminUser` — browses dashboards and hits the CPU-heavy paths: PDF generation
  (`ticket_pdf_builder.py`), Excel exports (`ticket_excel.py`, `location_excel.py`) —
  weighted low (~1 in 11 tasks) since these are expected to be slower, but worth
  watching for *disproportionate* degradation under concurrency.

Geocoding (`/tickets/api/geocode`, backed by a real call to the public Nominatim API)
is deliberately excluded from the load test — there's no app-level kill switch for it,
and hammering the real OpenStreetMap service would be both wrong and likely to get the
app's IP banned. Documented prominently in the locustfile so nobody adds it back
without also adding a stub.

## Validation performed

This wasn't just written and left untested — the harness was actually run end-to-end:

1. Seed script run at small scale (`LOADTEST_USERS=10 LOADTEST_TICKETS=50`), verified
   via direct SQL: correct row counts, correct FK chains through the full location
   hierarchy, correct role/status distributions. Re-run twice more to confirm it's
   idempotent (no-op on a clean re-run) and tops up correctly when scale is increased.
2. The app was actually booted under `gunicorn -w 2` against the seeded DB, and a real
   headless Locust run was executed against it: 15 concurrent users, 174 requests,
   **0 failures** after fixing a bug found in the harness's own first draft (technician/
   supervisor detail-view tasks were falling back to the global ticket pool when a
   simulated user had no assigned tickets, which 403'd constantly since ticket
   visibility is a per-ticket ACL, not role-wide — fixed by scoping each role's
   candidate pool to what that identity can actually see).
3. Everything created during validation (throwaway DB, gunicorn processes, a throwaway
   venv needed to run Locust at all — see below) was cleaned up afterward;
   `git status` shows only the two intended new files.

## Two things you need to know before running this for real

### 1. The global rate limit will throttle the load test itself

`Injaaz.py`'s `default_limits=["100 per hour"]` (or whatever `RATELIMIT_DEFAULT` is set
to) applies to every route, keyed by source IP. Confirmed empirically: request #100 in
a rapid-fire test against one endpoint was the first to get a 429. Since Locust runs
from a single local IP, **you must raise this before load testing** or you'll just be
measuring the rate limiter, not the app:

```bash
RATELIMIT_DEFAULT="100000 per hour"
```

### 2. The shared repo `venv/` cannot run Locust at all

`requirements-prods.txt` pins `botocore==1.29.165`, which requires `urllib3<1.27`.
Locust `2.46.3` requires `urllib3>=2`. These are incompatible in the same environment —
installing Locust into the existing venv breaks `botocore`'s import (`create_urllib3_context`
missing), which likely breaks anything using AWS/boto in that venv too. Validation for
this task used a separate throwaway venv (not committed). **This is a real,
pre-existing dependency conflict**, worth a decision: either give load testing its own
venv/requirements file, or find a `botocore`/Locust version pair that coexists, before
anyone tries to run this from the main environment.

## How to run it

```bash
# 1. Seed a local database with volume (never injaaz.db — refuses to run against it)
DATABASE_URL=sqlite:////absolute/path/to/instance/loadtest.db python scripts/seed_load_test_data.py

# 2. Boot the app under gunicorn (multi-worker, matching production's assumption),
#    with external integrations off and the rate limit raised
SECRET_KEY=... JWT_SECRET_KEY=... DATABASE_URL=sqlite:////absolute/path/to/instance/loadtest.db \
  ASSISTANT_LLM_ENABLED=false GOOGLE_DRIVE_ENABLED=false RATELIMIT_DEFAULT="100000 per hour" \
  gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app

# 3. Run Locust against it — web UI:
locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000

# ...or headless, following the recommended ramp (1 -> 25 -> 100 users, ~2-3 min per stage):
locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 --headless -u 25 -r 5 -t 3m
locust -f loadtest/locustfile.py --host=http://127.0.0.1:8000 --headless -u 100 -r 5 -t 3m
```

`common/email_service.py` was confirmed to safely no-op (returns `False`, never raises)
when no mail credentials are configured, so no separate flag is needed to keep it quiet.

## What to watch during a real run

- Per-endpoint p95 latency and error rate (Locust's built-in stats).
- Gunicorn worker memory over the run — repeated PDF/Excel generation
  (`ticket_pdf_builder.py`, `hr_pdf_builder.py`) is the likely leak suspect.
- DB connection-pool exhaustion under concurrent writes (`SQLALCHEMY_ENGINE_OPTIONS`
  pool settings in `config.py`).
- The geocode endpoint's in-process cache (`_SITE_GEOCODE_CACHE` in
  `module_ticketing/routes.py`) clears itself entirely once it hits 200 entries, with
  no LRU eviction — and since it's excluded from the load test, its behavior under real
  concurrent traffic (each gunicorn worker has its own copy, same class of issue as the
  in-memory rate limiter below) is untested by this harness and worth a manual look.
- Cross-worker inconsistency: the in-memory rate-limiter fallback (`storage_uri="memory://"`)
  is per-process, not shared across gunicorn workers. Worth one run with `REDIS_URL` unset
  and one with a local Redis, to directly compare — a request that happens to land on a
  "fresh" worker sees a different effective rate limit than one that doesn't.

## Success criteria for a first pass

No hard SLA was specified — these are sensible defaults for finding real problems, not
a production capacity claim:

- Simple list/detail reads: p95 well under ~500ms at 100 concurrent users.
- Write endpoints (ticket create/update): p95 under ~1s.
- Export/PDF endpoints: expected to be slower, but watch for *disproportionate*
  degradation as concurrency rises (a route going from 1s at 1 user to 30s at 25 users
  is the real signal, more than any absolute number).
- Error rate: effectively 0% outside deliberately-invalid-input tasks. Any 5xx under
  load is a bug to chase, not an expected outcome of concurrency.

## Status

The harness is built, validated at small scale, and ready to run. The actual 1 -> 25 ->
100-user ramp against a full-size seeded dataset has **not** been run yet as part of
this session — that's the natural next step once the rate-limit and venv issues above
are resolved.
