"""
Amaan App — Database Health Check (read-only)

Verifies the database is "on point" regardless of what the UI shows. Runs a set
of safe, SELECT-only checks (user accounts, duplicates, orphaned rows, contracts)
and prints a clear PASS / WARN report. It never modifies anything.

Local SQLite (default):
    python db_healthcheck.py

Production Postgres (Render):
    export PROD_DATABASE_URL="postgresql://USER:PASS@HOST/DBNAME"   # from Render
    python db_healthcheck.py --prod

Each check tolerates a missing table/column (shown as "skipped"), so the same
script works across schema differences between local and production.
"""

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "injaaz.db")


def _connect(use_prod):
    if use_prod:
        url = os.getenv("PROD_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not url:
            sys.exit('No production URL. Set PROD_DATABASE_URL first, e.g.:\n'
                     '  export PROD_DATABASE_URL="postgresql://USER:PASS@HOST/DBNAME"')
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        try:
            import psycopg2
        except ImportError:
            sys.exit("psycopg2 not installed. Run: pip install psycopg2-binary")
        host = url.split("@")[-1].split("/")[0]
        return psycopg2.connect(url), "postgres", f"PRODUCTION ({host})"
    import sqlite3
    if not os.path.exists(SQLITE_PATH):
        sys.exit(f"Local database not found at {SQLITE_PATH}")
    return sqlite3.connect(SQLITE_PATH), "sqlite", "LOCAL (injaaz.db)"


# A check is (label, kind, sql).
#   kind 'info'  → always printed as a neutral metric
#   kind 'warn'  → a count > 0 is a problem (WARN), 0 is PASS
# SQL is written to work on both SQLite and Postgres (no params, no booleans
# compared to integers — `WHERE is_active` works in both).
CHECKS = [
    ("Total users",                  "info", "SELECT COUNT(*) FROM users"),
    ("Active users",                 "info", "SELECT COUNT(*) FROM users WHERE is_active"),
    ("Admin users",                  "info", "SELECT COUNT(*) FROM users WHERE role = 'admin'"),
    ("Duplicate usernames",          "warn",
     "SELECT COUNT(*) FROM (SELECT username FROM users GROUP BY username HAVING COUNT(*) > 1) d"),
    ("Duplicate emails",             "warn",
     "SELECT COUNT(*) FROM (SELECT email FROM users WHERE email IS NOT NULL AND email <> '' "
     "GROUP BY email HAVING COUNT(*) > 1) d"),
    ("Users with no email",          "warn",
     "SELECT COUNT(*) FROM users WHERE email IS NULL OR email = ''"),
    ("Users with no password set",   "warn",
     "SELECT COUNT(*) FROM users WHERE password_hash IS NULL OR password_hash = ''"),

    ("Total work orders (tickets)",  "info", "SELECT COUNT(*) FROM tickets"),
    ("Tickets with blank status",    "warn",
     "SELECT COUNT(*) FROM tickets WHERE status IS NULL OR status = ''"),
    ("Orphaned tickets (reporter missing)", "warn",
     "SELECT COUNT(*) FROM tickets t LEFT JOIN users u ON t.reporter_id = u.id "
     "WHERE t.reporter_id IS NOT NULL AND u.id IS NULL"),

    ("Total BD deals",               "info", "SELECT COUNT(*) FROM bd_projects"),
    ("Open BD deals",                "info",
     "SELECT COUNT(*) FROM bd_projects WHERE status IN ('active','prospect','proposal')"),
    ("Orphaned BD follow-ups",       "warn",
     "SELECT COUNT(*) FROM bd_followups f LEFT JOIN bd_projects p ON f.project_id = p.id "
     "WHERE f.project_id IS NOT NULL AND p.id IS NULL"),

    ("Clients on record",            "info", "SELECT COUNT(*) FROM clients"),
    ("Civil Defense notifications",  "info", "SELECT COUNT(*) FROM inspection_notifications"),
]


def main():
    parser = argparse.ArgumentParser(description="Amaan database health check (read-only)")
    parser.add_argument("--prod", action="store_true",
                        help="Check production Postgres (PROD_DATABASE_URL) instead of local SQLite.")
    args = parser.parse_args()

    conn, backend, label = _connect(args.prod)
    cur = conn.cursor()

    print("=" * 60)
    print(f"  Database health check — {label}")
    print("=" * 60)

    warnings = 0
    skipped = 0
    for label_text, kind, sql in CHECKS:
        try:
            cur.execute(sql)
            value = cur.fetchone()[0]
        except Exception:
            conn.rollback()  # Postgres aborts the txn on error; reset for next check
            print(f"  ⤷  {label_text:<38} skipped (table/column not found)")
            skipped += 1
            continue
        if kind == "info":
            print(f"  •  {label_text:<38} {value}")
        else:  # warn
            if value and int(value) > 0:
                print(f"  ⚠  {label_text:<38} {value}   ← needs attention")
                warnings += 1
            else:
                print(f"  ✅ {label_text:<38} OK")

    conn.close()
    print("-" * 60)
    if warnings == 0:
        print(f"  Result: ALL CLEAR ✅   ({skipped} checks skipped)")
    else:
        print(f"  Result: {warnings} warning(s) ⚠   ({skipped} checks skipped)")
        print("  Review the flagged rows before going live.")
    sys.exit(1 if warnings else 0)


if __name__ == "__main__":
    main()
