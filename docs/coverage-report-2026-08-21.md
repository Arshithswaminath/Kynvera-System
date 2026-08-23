# Test Coverage Report — 2026-08-21

Full-suite results, coverage gains, and real bugs found while closing the test-coverage
gap across all ~530 routes. Scope was phased and gap-first: close the five modules with
zero route-level tests, add auth/session edge-case coverage, then deepen the ticketing
settings sub-tree. See `docs/load-test-report-2026-08-21.md` for the local load-testing
half of this effort.

## Headline numbers

| | Before | After |
|---|---|---|
| Tests passing | 273 | 711 |
| Tests failing | 31 | 13 (all pre-existing, none introduced — see below) |
| Test errors | 49 | 0 |
| Whole-app statement coverage | 28% | 44% |
| Full suite runtime | ~4 min (with cascading failures) | ~7.5 min (clean) |

The suite grew by 371 tests across 8 new files, all passing standalone and as part of
the full run.

## Coverage by module

| Module | Before | After | Test file |
|---|---|---|---|
| `module_procurement/routes.py` | 17% | **87%** | `tests/test_procurement.py` (84 tests) |
| `module_files/routes.py` | 21% | **84%** | `tests/test_files_module.py` (82 tests) |
| `module_qhsi/routes.py` | 26% | **82%** | `tests/test_qhsi.py` (53 tests) |
| `module_mmr/routes.py` | 14% | **71%** | `tests/test_mmr.py` (68 tests) |
| `app/middleware.py` | 36% | **64%** | `tests/test_auth_edge_cases.py` (17 tests) |
| `module_ticketing/routes.py` | 22% | **52%** | `tests/test_ticket_settings_crud.py` (44 tests, layered on existing coverage) |
| `module_inspection/routes.py` | 10% | **39%** | `tests/test_inspection.py` (24 tests) |

`module_inspection/routes.py` lands lower than the others because its two big
uncovered blocks — a 300-line role/permission matrix in the dashboard view and the
Cloudinary-fetch branch of file download — were out of scope for a first coverage pass
per the test file's own report; they're good targets for a follow-up.

## Real bugs found

These were found empirically while writing tests (not by inspection) and were **not
fixed** — app-code changes are outside what this pass was authorized to do. Each is
pinned down by a passing regression test that documents the *current* (buggy) behavior.

### 1. Missing `redirect` import → 500 instead of a redirect (two modules, same bug class)

- **`module_procurement/routes.py:653`** — `catalog_department()` calls
  `redirect('/procurement/')` for an unrecognized department, but `redirect` is never
  imported anywhere in the file. Raises `NameError`, surfaced to the client as a bare 500.
- **`module_inspection/routes.py`, `inspection_dashboard()` (~line 184-194)** — same
  class of bug: calls `redirect(...)` for a no-access user, but `redirect` is only
  imported *locally* inside two other functions in the same file (lines 201, 951), not
  this one. Same `NameError` → 500 outcome.

Checked the rest of the app for the same pattern (`module_assets`, `module_files`,
`module_ticketing` all call `redirect()` too) — those three all import it correctly at
the top of the file. This is isolated to exactly these two call sites, not systemic.

### 2. Login/register rate limiting is a silent no-op (production security gap)

`app/auth/routes.py`'s `rate_limit_if_available()` decorator resolves
`current_app.limiter` **at blueprint-import time** (when Python evaluates the
`@rate_limit_if_available('5 per minute')` decorator above `login()`/`register()`), before
any Flask app context exists. `get_limiter()` always returns `None` at that point, so the
decorator permanently no-ops — confirmed empirically: 15 rapid-fire login attempts hit 0
of the intended 5/minute limit.

Login and register instead fall back to the app-wide `default_limits` (100/hour by
default, keyed by IP, shared across every route). That's real but much looser
brute-force protection than the "5 per minute on login" the code visibly intends. Worth
fixing — the fix is to resolve the limiter lazily, inside the wrapped view function, not
at decoration time.

*(This is also what fully explained a confusing intermediate finding — see "How the
baseline failures were diagnosed" below.)*

### 3. Database-admin browser has no `read_only` protection for the `users` table

`app/database_admin.py:544-545` hardcodes `'read_only': False` and
`'can_edit': bool(pk_cols)` for **every** table the generic DB browser exposes, with no
special-casing. An existing test (`tests/test_database_admin.py::test_browse_users_read_only`)
expects the `users` table specifically to come back `read_only: True` — it still fails.

To be clear about the actual exposure: `password_hash`, `mfa_secret`,
`refresh_token_enc`, `key_hash`, and `secret`-named columns *are* protected via a
`_HIDDEN_COLUMNS` set. But `role`, `is_active`, `access_*` permission flags, `email`, and
`username` are not — an admin can edit those directly through the generic table editor,
bypassing the dedicated `/api/admin/users/*` endpoints and whatever audit logging they
do. This is already admin-gated (not a privilege-escalation hole), but it is an
auditability/defense-in-depth gap worth a decision: either the test is aspirational and
the team should implement the intended read-only guard, or the guard was deliberately
dropped and the test should be deleted.

### 4. Dead code in fault-code deletion

`module_ticketing/routes.py:5014-5017`:
```python
if tkt_fields.ticket_uses_fault(row):
    row.is_active = False
else:
    row.is_active = False
```
Both branches do the same thing. Reads like the intent was "hard-delete when unused,
soft-deactivate when a ticket references it," but the differentiation was never
implemented — fault codes always soft-deactivate regardless of usage.

### 5. Open question: Kynvera vs. Injaaz branding

All PDF/DOCX generation (HR forms, QHSI reports, ticket invoices) is branded "Kynvera"
(`common/kynvera_pdf_brand.py`, `COMPANY_NAME = "Kynvera"`), which is why 10 tests in
`tests/test_hr_forms_pdf_suite.py` and 2 in `tests/test_hr_leave_application_template.py`
fail — they still assert the old "Injaaz"/"INJAAZ" branding strings.

New evidence found while writing this report: `docs/KYNVERA_DESIGN.md` is a full,
deliberate design-system document ("Kynvera Design System, Version 2.0 — Coral theme")
covering the whole app's UI, not just PDFs — logo assets, color tokens, typography, the
works. This makes it look like "Kynvera" is the app's actual current product identity
on this branch, not a stray leftover from a different project. That said, the branch is
named `ajman-municipality` and the repo is `Injaaz-App-muni` — so it's genuinely
plausible this is either (a) the correct, intended current brand, or (b) branding meant
for a different deployment that leaked into municipality-facing documents. Per your
choice, this is left undecided and untouched — the 12 tests remain failing as an honest
signal until you weigh in. If (a): update the 12 assertions to check
`brand.COMPANY_NAME`/`COMPANY_NAME_UPPER` instead of hardcoded strings. If (b): the fix
is in `common/kynvera_pdf_brand.py`, not the tests.

## Test-infrastructure fix (applied, not just found)

**A pre-existing test-collection bug was silently capping the suite's real failure count
at whatever CI's `--maxfail=5` happened to catch first**, and made the first full local
run of the whole suite look far worse than the app actually is. Root cause:

`tests/test_hr_forms_pdf_suite.py` does `@pytest.mark.parametrize("form_type",
__import__("module_hr.pdf_service", fromlist=[...]).get_supported_pdf_forms())` — an
eager import as a *decorator argument*, which Python evaluates at pytest's **collection**
time, before any fixture (including `tests/conftest.py`'s `app` fixture, which sets
testing-mode environment variables) has run. That import chain pulls in `config.py`,
whose module-level `os.getenv(...)` reads only execute once and get cached — so
`config.py` froze in production defaults (crucially, `RATELIMIT_ENABLED=True`) for the
rest of the process, no matter what the `app` fixture set afterward.

The practical effect: running the full suite (hundreds of tests, each independently
calling `/api/auth/login` via the `auth_headers`/`admin_auth_headers` fixtures) blew
through the rate limiter mid-run. Login started silently returning no `access_token`
(`{'error': 'Rate limit exceeded...'}`), test fixtures built headers like `{'Authorization':
'Bearer None'}`, and every subsequent authenticated request cascaded into unrelated 401s
— **80 failures/errors** in the first full run, ballooning to **324** once the new test
files added more login volume, all downstream of this one root cause. (A one-off
`NOT NULL constraint failed: tickets.reporter_id` teardown crash seen in that broken run
also stopped reproducing once this was fixed — it was very likely a further downstream
artifact of the same cascade, not an independent bug; noted here for the record since it
looked alarming in isolation.)

**Fix applied**: moved the environment-variable setup in `tests/conftest.py` from inside
the `app` fixture function to module level, so it executes the moment pytest imports
`conftest.py` — which pytest always does before collecting any test file in the same
directory, regardless of what any individual test file's decorators do. Added a
`RATELIMIT_ENABLED` config key to `config.py` (defaults on in production, off only when
explicitly set) so `tests/conftest.py` has something to actually flip.

This fix is why the "before" failure/error counts in this report look dramatically
better than the two broken intermediate runs — it's a real, durable fix, not a lucky
run.

## Files changed

**Test infrastructure**: `pytest.ini`, `.coveragerc` (new), `requirements-dev.txt`
(added `pytest-cov`, `locust`), `tests/factories.py` (new, shared `make_user`/
`make_admin`/`make_location_hierarchy` helpers), `tests/conftest.py` (rate-limit fix),
`config.py` (`RATELIMIT_ENABLED` key), `.github/workflows/ci.yml` (coverage gate at
25%, room to ratchet up).

**New test files**: `tests/test_procurement.py`, `tests/test_files_module.py`,
`tests/test_inspection.py`, `tests/test_mmr.py`, `tests/test_qhsi.py`,
`tests/test_auth_edge_cases.py`, `tests/test_ticket_settings_crud.py`.

## Recommended next steps

1. Decide the Kynvera/Injaaz branding question (item 5 above) — it's the only thing
   blocking a fully green suite.
2. Fix the login rate-limiter no-op (item 2) — genuine, if modest, security gap.
3. Fix the two `redirect` NameErrors (item 1) — trivial one-line import fixes.
4. Decide on the `users` table read-only question (item 3) and either implement the
   guard or delete the aspirational test.
5. Raise the CI coverage gate (`--cov-fail-under`) incrementally as more modules get
   covered — currently set to 25%, actual is 44%, so there's room to raise it now
   without breaking CI.
6. `module_hr/` (the largest module, 16K+ lines including a 2,745-line PDF builder) and
   the remainder of `module_ticketing/routes.py`'s non-settings routes are the next
   biggest coverage gaps by line count.
