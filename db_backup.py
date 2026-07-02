"""
Amaan App — Database Backup (safety net before touching data)

Takes a full, read-only snapshot of every table into a timestamped folder under
./backups/. Pure-Python — no pg_dump required. Use this BEFORE any manual data
edit so a mistake is always reversible.

Local SQLite (default):
    python db_backup.py

Production Postgres (Render):
    export PROD_DATABASE_URL="postgresql://USER:PASS@HOST/DBNAME"   # from Render
    python db_backup.py --prod

Output: backups/<timestamp>/<table>.json  (one file per table)
        backups/<timestamp>/_manifest.json (row counts + metadata)

Notes
-----
* This is a SELECT-only operation; it never modifies the database.
* Render's managed Postgres also keeps its own automatic backups — this script is
  an extra, on-demand snapshot you control and can read/restore field-by-field.
* For a fully restorable SQL dump, install the Postgres client tools
  (`brew install libpq` then add its bin to PATH) and run `pg_dump "$PROD_DATABASE_URL"`.
"""

import argparse
import json
import os
import sys
from datetime import datetime, date
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "injaaz.db")
BACKUP_ROOT = os.path.join(BASE_DIR, "backups")


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


def _connect(use_prod):
    """Return (conn, backend, label)."""
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


def _table_names(cur, backend):
    if backend == "postgres":
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_type='BASE TABLE' "
                    "ORDER BY table_name")
    else:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser(description="Amaan database backup")
    parser.add_argument("--prod", action="store_true",
                        help="Back up production Postgres (PROD_DATABASE_URL) instead of local SQLite.")
    args = parser.parse_args()

    conn, backend, label = _connect(args.prod)
    cur = conn.cursor()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BACKUP_ROOT, f"{'prod' if args.prod else 'local'}_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print(f"  Backing up {label}")
    print(f"  → {out_dir}")
    print("=" * 60)

    tables = _table_names(cur, backend)
    manifest = {"backend": backend, "label": label, "taken_at": stamp, "tables": {}}
    total_rows = 0

    for t in tables:
        try:
            cur.execute(f'SELECT * FROM "{t}"')
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            conn.rollback()
            print(f"  ⚠  {t}: skipped ({e})")
            manifest["tables"][t] = {"rows": None, "error": str(e)}
            continue
        with open(os.path.join(out_dir, f"{t}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, default=_json_default, ensure_ascii=False, indent=2)
        manifest["tables"][t] = {"rows": len(rows)}
        total_rows += len(rows)
        print(f"  ✅ {t:<34} {len(rows):>7} rows")

    with open(os.path.join(out_dir, "_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, default=_json_default, ensure_ascii=False, indent=2)

    conn.close()
    print("-" * 60)
    print(f"  Done: {len(tables)} tables, {total_rows} rows total.")
    print(f"  Snapshot saved to: {out_dir}")


if __name__ == "__main__":
    main()
