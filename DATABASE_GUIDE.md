# Database Guide — operating Amaan safely (local + Render)

A plain-English playbook for viewing and fixing data **without writing SQL**, and
for not breaking the live database. Read the "Golden rules" once; use the rest as
a reference.

---

## 0. 🚨 Do this first — rotate the leaked password

`migrate_to_postgres.py` currently has the **production database username and
password written in plain text**, and that file is committed to git. Anyone who
can see the repo can control the live database.

Fix it before launch:

1. **Render dashboard → your Postgres → "Recovery"/"Reset password"** (or rotate the
   instance). This invalidates the leaked password.
2. Copy the **new** connection string and keep it only in an environment variable
   (see §2) — never paste it back into a file.
3. Edit `migrate_to_postgres.py` so `PG_URL = os.environ["DATABASE_URL"]` instead of
   the hard-coded string. (All the new tools below already read from the env var.)

Even after rotating, the old password stays in git history — rotating makes it
useless, which is what matters.

---

## 1. The mental model (this removes 90% of the fear)

You have **two separate databases**:

| | Local (your Mac) | Production (Render) |
|---|---|---|
| Engine | SQLite — the `injaaz.db` file | Postgres (managed by Render) |
| Data | fake / practice | **real customers — sacred** |

Two different things live in a database — keep them separate in your head:

- **Schema** = the *shape* (tables and columns). This must be **identical** on both.
  You change it only through **migrations** (§6), never by hand on production.
- **Data** = the *rows* (a contract, a user). Local and prod data are **different
  and independent**. You never copy local data onto prod — that would erase real
  records. `migrate_to_postgres.py` is a *one-time* seeding tool, not a sync button.

So "fix one contract the UI won't let me fix" = a **data** edit on prod. That's
safe if you follow the golden rules.

---

## 2. Get the production connection string (once)

1. Render dashboard → your Postgres instance → **"Connect" → "External Database URL"**.
2. In your terminal, set it as an environment variable (this lasts for that terminal
   window only — nothing is saved to a file):

   ```bash
   export PROD_DATABASE_URL="postgresql://USER:PASS@HOST/DBNAME"
   ```

Every tool below reads `PROD_DATABASE_URL` automatically. Do this in a fresh
terminal each time you work on prod.

---

## 3. Golden rules for changing live data

1. **Back up first** — `python db_backup.py --prod` (takes seconds, §5).
2. **Practice on local first** — make the same change on `injaaz.db` and confirm the
   app still behaves.
3. **Edit through a GUI**, one row at a time, and read the row before you save.
4. **Verify after** — `python db_healthcheck.py --prod` (§5).
5. When in doubt, prefer fixing it **in the app** (or asking for an admin button to
   be added) over editing the database directly.

---

## 4. Viewing / editing data without SQL — two tools

### Option A — TablePlus or DBeaver (recommended for real edits)

Polished desktop apps built exactly for this. **TablePlus** (Mac, free tier) is the
easiest; **DBeaver** (free, Windows/Mac/Linux) is the all-rounder.

**TablePlus:**
1. Download from tableplus.com, open it.
2. **Create a new connection → PostgreSQL**.
3. Click **"Import from URL"** and paste the Render External Database URL — it fills
   host/user/password/database for you. (Tick **SSL/Use SSL** — Render requires it.)
4. **Test** → **Connect**.
5. Left sidebar = your tables. Click `clients` or `tickets`, double-click a cell to
   edit, then **Cmd+S** to commit. A red dot marks unsaved changes until you save.

**DBeaver:** New Connection → PostgreSQL → paste host/db/user/password from the URL →
in **SSL** tab tick *Use SSL* → Finish. Double-click a table → **Data** tab → edit
cells → **Ctrl+S**.

> Tip: both let you **filter** (e.g. `client_name = 'Acme'`) without SQL, and show a
> preview of exactly what will change before you save.

### Option B — your own db_browser (quick checks, read-only on prod)

The familiar browser you already use locally now also connects to prod.

```bash
python db_browser.py                       # local SQLite, fully editable
python db_browser.py --prod                # PRODUCTION, READ-ONLY (safe to browse)
python db_browser.py --prod --allow-edit   # PRODUCTION, editing enabled (careful!)
```

On `--prod` it opens the same UI at http://localhost:8765 but **blocks edits,
deletes, and write-queries by default** — you can look without any risk of changing
anything. Add `--allow-edit` only after you've taken a backup.

---

## 5. The safety-net scripts

| Command | What it does |
|---|---|
| `python db_backup.py` | Snapshot **local** DB → `backups/local_<timestamp>/` (one JSON file per table). |
| `python db_backup.py --prod` | Snapshot **production** the same way. Run before any edit. |
| `python db_healthcheck.py` | Read-only checks on **local**: user counts, duplicate usernames/emails, missing passwords, orphaned tickets/follow-ups, etc. |
| `python db_healthcheck.py --prod` | Same checks against **production** — confirms the DB is "on point" no matter what the UI shows. |

Both are **read-only except db_backup writes files to disk**; neither ever changes
the database. Backups land in `backups/` which is git-ignored (it contains real
data — never commit it).

Render also keeps its **own automatic backups** of managed Postgres — these scripts
are an extra layer you control.

---

## 6. Changing the database *shape* (schema) — use migrations

When you add/rename a column or table in the code (`app/models.py`), do **not** edit
production by hand. Use Flask-Migrate so local and prod stay identical:

```bash
flask db migrate -m "describe the change"   # generates a migration file (review it)
flask db upgrade                            # applies it to your LOCAL database
```

Commit the generated file in `migrations/versions/`. On deploy, run `flask db upgrade`
against production (Render shell or a release command) to apply the *same* change.
This is the bridge that keeps the two databases in sync.

---

## 7. Quick "is prod healthy?" routine before/after a change

```bash
export PROD_DATABASE_URL="postgresql://...he real url..."
python db_backup.py --prod        # 1. snapshot
python db_healthcheck.py --prod   # 2. baseline
#    ...make your edit in TablePlus / db_browser --prod --allow-edit...
python db_healthcheck.py --prod   # 3. confirm no new warnings
```

If step 3 shows a problem you didn't expect, the JSON snapshot from step 1 has the
original values to restore.
