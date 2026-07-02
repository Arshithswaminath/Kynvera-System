# Branch Difference Report: `Test-Case` vs `scaffold/init`

**Repository:** Injaaz-App  
**Report date:** 25 June 2026  
**Primary branch:** `Test-Case`  
**Comparison targets:** local `scaffold/init` and `origin/scaffold/init` (GitHub)

---

## 1. Executive summary

| | **Test-Case** | **scaffold/init (local)** | **scaffold/init (GitHub)** |
|---|---|---|---|
| **Role** | Active development branch | Older baseline + 1 MMR commit | Partially synced via PR merges |
| **Tip commit** | `1a9d397` | `cce8e42` | `15b8250` |
| **Commits vs common base** | **+42** ahead | **+1** ahead | Mixed merge history |
| **App code delta** | Superset | Subset | ~same as local + merge commits |
| **Merge risk into Test-Case** | — | 1 conflict possible | **No conflicts** |

**Conclusion:** `Test-Case` is the fuller branch. `scaffold/init` does not add major features that `Test-Case` lacks. The only unique `scaffold/init` change (MMR upload reminder removal) is already reflected in `Test-Case` behavior.

---

## 2. Branch relationship

```
                    f390119 (common ancestor)
                   /                        \
                  /                          \
    scaffold/init (cce8e42)              Test-Case (1a9d397)
    "MMR reminder removed"               +42 feature commits
                  \                          /
                   \                        /
              origin/scaffold/init (15b8250)
              merged Test-Case PRs #50–#57
```

### Commit counts

| Comparison | Commits only on first branch | Commits only on second branch |
|------------|------------------------------|-------------------------------|
| **Test-Case vs local scaffold/init** | 42 on Test-Case | 1 on scaffold (`cce8e42`) |
| **Test-Case vs origin/scaffold/init** | 8 on Test-Case | 5 on scaffold |

---

## 3. Commits only on `scaffold/init`

### Local `scaffold/init` — 1 commit not in `Test-Case`

| Commit | Message |
|--------|---------|
| `cce8e42` | MMR: remove scheduled upload reminder email (keep daily report job only) |

**Effect:** Removes the 1-hour-before `[MMR Reminder] Upload today's Excel` APScheduler job. Keeps the daily report cron only. Still unregisters legacy job id `mmr_upload_reminder` on config save.

**On Test-Case:** Reminder is already removed; only legacy job-id cleanup remains. Functionally equivalent.

### `origin/scaffold/init` — 5 commits not in `Test-Case`

| Commit | Message |
|--------|---------|
| `cce8e42` | MMR upload reminder removal (same as above) |
| `59e6eea` | Merge PR #50 from Test-Case |
| `e0dfd71` | Merge PR #51 from Test-Case |
| `1777735` | Merge PR #56 from Test-Case |
| `15b8250` | Merge PR #57 from Test-Case |

These are mostly **merge commits**, not new application features.

---

## 4. Commits only on `Test-Case`

### vs local `scaffold/init` — 42 commits

| Area | Representative commits |
|------|------------------------|
| **Assistant** | `da494cb` — Implement Injaaz Assistant and Knowledge Base |
| **Documents / submissions** | `1a9d397`, `a2557af` — submission & document management |
| **Email / LLM** | `ed1213d` — Refactor email service + LLM context |
| **QHSI** | `2611330` — QHSI dashboard and About page |
| **Admin / users** | `f854cfe`, `27e354e` — user management, profile UI |
| **Ticketing** | `dc72e1b` — Ticketing module integration |
| **HR workflow** | `17458ae`, `6417a3e` — HR forms, submission trail |
| **Mobile UI** | `1f39f04`, `8ee58b6`, `0b6b1b2` — responsive redesign |
| **MMR** | `1c58c4c`, `6bc5bb8`, `a7576a7` — scheduler, chargeability, automation |
| **Device management** | `2717541` — device management features |
| **Dev / security** | `c03803a` — stop tracking secrets & `injaaz.db` |

### vs `origin/scaffold/init` — 8 commits not yet on GitHub scaffold

| Commit | Message |
|--------|---------|
| `f854cfe` | Enhance user management and registration process |
| `27e354e` | Refactor admin profile UI and quick action buttons |
| `a2557af` | Enhance submission management and activity tracking |
| `da494cb` | Implement Injaaz Assistant and Knowledge Base |
| `2611330` | Update styles and content for QHSI dashboard and About page |
| `140a1bf` | New work — rechecked |
| `ed1213d` | Refactor email service and enhance context retrieval for LLM |
| `1a9d397` | Enhance submission and document management features |

---

## 5. Code volume difference

Excluding `test_output/`, `node_modules/`, `screenshots/`, `generated/`, and markdown docs:

| Metric | Value |
|--------|-------|
| **Files changed** | ~464 |
| **Insertions** | ~206,656 |
| **Deletions** | ~113,356 |

### Core application areas (line-level diff)

| Path | Change scale | Notes |
|------|--------------|-------|
| `module_ticketing/` | **+~26k lines** | **New module** — not on scaffold |
| `module_assistant/` | **+~2.8k lines** | **New module** — not on scaffold |
| `module_qhsi/` | **+~1.8k lines** | **New module** — not on scaffold |
| `app/admin/routes.py` | ~6.8k lines changed | Admin dashboard, devices, notifications |
| `app/workflow/routes.py` | ~6.8k lines changed | Workflow & approvals |
| `app/models.py` | ~2.3k lines changed | New models (ticketing, assistant, etc.) |
| `Injaaz.py` | ~2.2k lines changed | Blueprint registration, app factory |
| `module_mmr/` | All 4 core files heavily changed | Scheduler, chargeability, dashboard |
| `module_hr/routes.py` | ~2.7k lines changed | HR workflow enhancements |
| `common/workflow_notifications.py` | 84 → 508 lines | Full notification system |
| `tests/` | 16 test files expanded/added | Assistant, HR, workflow tests |

### Top directories by changed file count

| Directory | Files changed |
|-----------|---------------|
| `scripts/` | 61 |
| `static/css/` | 33 |
| `static/js/` | 32 |
| `templates/` | 28 |
| `module_hr/templates/` | 25 |
| `common/` | 17 |
| `tests/` | 16 |
| `module_hr/` | 13 |
| `module_assistant/` | 10 |
| `module_ticketing/` | 6 |
| `module_qhsi/` | 5 |
| `module_mmr/` | 4 |

---

## 6. Feature comparison

### Modules present on each branch

| Module / component | scaffold/init | Test-Case |
|--------------------|:-------------:|:---------:|
| HVAC / Civil / Cleaning | Yes | Yes |
| HR | Yes | Yes (enhanced) |
| MMR | Yes | Yes (enhanced) |
| **Ticketing** | **No** | **Yes** |
| **Injaaz Assistant** | **No** | **Yes** |
| **QHSI / QHSE** | **No** | **Yes** |
| Device management (admin) | Basic | Full UI + backend |
| CI workflow (`.github/workflows/ci.yml`) | No | Yes |

---

## 7. Email setup comparison

| Item | scaffold/init | Test-Case |
|------|:-------------:|:---------:|
| Env vars (`MAIL_*`, `BREVO_API_KEY`, `MAILJET_*`) | Same | Same |
| `common/email_service.py` (Brevo / Mailjet / SMTP) | Same core | Same core |
| `app/services/email_service.py` | **Mock** (pretend send) | **Real** send via shared service |
| Workflow emails | Designation-based team notify (~84 lines) | Admin-configured per stage (~508 lines) |
| Admin notification settings UI | No | Yes (`NotificationConfig` in DB) |
| HR routed sign-off emails | No | Yes (`module_hr/hr_routed_signoffs.py`) |
| Ticketing emails | No | Yes |
| MMR daily report | Yes | Yes (+ approval gate) |
| MMR upload reminder | Removed on scaffold | Removed on Test-Case |
| Background report jobs (`app/tasks/generate_report.py`) | Mock | Real |

### Email send order (both branches — `common/email_service.py`)

1. **Brevo REST** — if `BREVO_API_KEY` is set (recommended on Render free tier)
2. **Mailjet REST** — if Mailjet API keys are set (auto on Render when using Mailjet SMTP host)
3. **SMTP fallback** — `MAIL_SERVER` + credentials (IPv4-only for cloud hosts)

### Email credentials when switching branches

**No change required.** Same `.env` / Render env vars work on both branches.

### New requirement on Test-Case

Configure **Admin → Notification Settings** (To/CC per inspection and HR module, optional include-submitter toggle). Without this, workflow emails may not reach anyone even if SMTP/Brevo is configured.

See also: `docs/EMAIL_SMTP_OPTIONS.md`, `.env.example`.

---

## 8. MMR automation comparison

| Feature | scaffold/init | Test-Case |
|---------|:-------------:|:---------:|
| Daily scheduled report email | Yes | Yes |
| Manual “Send now” | Yes | Yes |
| Upload reminder email (`[MMR Reminder] Upload today's Excel`) | Removed (`cce8e42`) | Removed |
| Legacy job cleanup (`mmr_upload_reminder` id) | Yes | Yes |
| Approval required before send | No | **Yes** |
| 30-min approval timeout auto-stop | No | **Yes** |
| Approval watchdog job (every 5 min) | No | **Yes** |
| Chargeable rules admin UI | Basic | Enhanced |
| Save report to network path (`MMR_EMAIL_SAVE_PATH`) | Yes | Yes |

### Scheduler file size

| Branch | `module_mmr/scheduler.py` lines | Notes |
|--------|--------------------------------|-------|
| scaffold/init | ~246 | Daily cron only |
| Test-Case | ~297 | Daily cron + approval watchdog |

---

## 9. Workflow & HR comparison

| Feature | scaffold/init | Test-Case |
|---------|:-------------:|:---------:|
| Inspection GM workflow | Yes | Yes |
| HR approval sidebar / submission trail | Basic | Full |
| Management chain sign-offs | Limited | Full |
| HR routed sign-off assignment emails | No | Yes |
| Mobile-responsive forms | Partial | Comprehensive |
| Workflow notification per stage | No | Yes (inspection + HR) |

### Workflow notifications detail

**scaffold/init:** `send_team_notification()` emails users with designations: supervisor, operations_manager, business_development, procurement.

**Test-Case:** Loads recipients from `NotificationConfig` DB table. Sends at each workflow stage with Outlook-safe HTML templates, optional submitter copy, and deep links to pending reviews.

---

## 10. Merge assessment

| Merge direction | Conflicts | Code impact | Recommendation |
|-----------------|-----------|-------------|----------------|
| `origin/scaffold/init` → `Test-Case` | **None** | Merge commit only; no file changes | Safe; optional |
| Local `scaffold/init` → `Test-Case` | **1 file:** `module_mmr/scheduler.py` | Resolve by keeping Test-Case version | Safe after resolve |
| `Test-Case` → `scaffold/init` | Usually clean | Brings 8–42 commits to scaffold | Good way to sync scaffold |
| `Test-Case` → `main` | Depends on `main` state | Full Test-Case feature set | Plan deploy + admin config |

### Resolving `module_mmr/scheduler.py` conflict

Keep the **Test-Case** side. It includes:

- Approval gate before scheduled send
- `_run_approval_watchdog` / `mmr_cycle_approval_watchdog` job
- `auto_stop_stale_cycle` integration

The scaffold-only change (removing upload reminder) is already present on Test-Case.

---

## 11. Deployment impact

If production currently runs from `scaffold/init` and switches to `Test-Case`:

| Category | Impact |
|----------|--------|
| **New modules live** | Assistant, Ticketing, QHSI |
| **Email** | Same env vars; configure Admin → Notification Settings |
| **MMR** | Stricter — requires cycle approval before send; 30-min timeout stops automation |
| **Database** | New tables/models for ticketing, assistant, `notification_config`, etc. |
| **Render** | Consider persistent `GENERATED_DIR` for `mmr_email_config.json` |
| **Risk level** | **Moderate** — mostly additive; MMR approval gate is the main behavior change |

### Render env vars (unchanged for email)

```env
# Option A — Render free tier (HTTPS, SMTP ports blocked)
BREVO_API_KEY=xkeysib-...
MAIL_DEFAULT_SENDER=noreply@injaaz.ae

# Option B — SMTP (local or paid Render)
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=...
MAIL_PASSWORD=...
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

Optional MMR schedule fallbacks if config JSON is lost on redeploy:

```env
MMR_SCHEDULE_ENABLED=true
MMR_SCHEDULE_HOUR=10
MMR_SCHEDULE_MINUTE=0
GENERATED_DIR=/var/data/generated   # if using a Render disk
```

---

## 12. Recommended actions

| Goal | Action |
|------|--------|
| Continue development | Stay on **`Test-Case`** |
| Sync `scaffold/init` with latest | Merge **`Test-Case` → `scaffold/init`**, push |
| Merge for history only | Merge **`origin/scaffold/init` → `Test-Case`** (no code delta) |
| Skip unnecessary work | Do **not** merge local `scaffold/init` unless you need the merge commit — adds scheduler conflict for no functional gain |
| Deploy to production | Use **`Test-Case`**, configure notification settings, verify MMR approval workflow |

---

## 13. Regenerating this report

Run from the repo root:

```bash
# Branch tips
git log -1 --oneline Test-Case scaffold/init origin/scaffold/init

# Commits unique to each side
git log --oneline scaffold/init..Test-Case
git log --oneline Test-Case..scaffold/init

# File diff (excluding artifacts)
git diff --stat scaffold/init Test-Case -- ':!test_output' ':!node_modules' ':!screenshots' ':!generated' ':!.neat-ref' ':!*.md'

# Dry-run merge
git merge --no-commit --no-ff origin/scaffold/init   # on Test-Case — expect clean
```

---

## 14. Bottom line

| Question | Answer |
|----------|--------|
| Is `Test-Case` ahead? | **Yes — significantly (42 commits vs local scaffold)** |
| Does `scaffold/init` have must-have code missing from Test-Case? | **No** |
| Will merging cause big issues? | **No** — at most 1 scheduler conflict |
| Is email setup different? | **Same credentials**; Test-Case sends **more** emails with **admin config** |
| Which branch should be primary? | **`Test-Case`** |

---

*This report compares committed branch tips. Uncommitted local changes are not included unless noted separately at generation time.*
