"""
migrate_to_postgres.py
----------------------
Migrates all data from the local SQLite (injaaz.db) to the Render PostgreSQL.
Uses batch inserts (execute_values) for speed.

Usage:
    python migrate_to_postgres.py
"""

import sqlite3
import json
import sys
import os

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("psycopg2-binary not installed. Run: pip install psycopg2-binary")

# ── Config ────────────────────────────────────────────────────────────────────
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "injaaz.db")
# Prefer PROD_DATABASE_URL; fall back to DATABASE_URL. Never hard-code credentials.
PG_URL = os.environ.get("PROD_DATABASE_URL") or os.environ.get("DATABASE_URL")

BATCH_SIZE = 100  # rows per INSERT batch

# Tables in dependency order (parents before children). Covers full local demo DB.
TABLES = [
    "users",
    "sessions",
    "devices",
    "email_otps",
    "audit_logs",
    "submissions",
    "jobs",
    "files",
    "bd_projects",
    "bd_followups",
    "bd_contacts",
    "bd_activities",
    "admin_personal_projects",
    "admin_personal_progress_steps",
    "dochub_documents",
    "dochub_stars",
    "dochub_access",
    "knowledge_base_entries",
    "email_automation",
    "email_automation_attachment",
    "email_automation_run_log",
    "email_automation_defaults",
    "notification_config",
    "notifications",
    "inspection_notifications",
    "employees",
    "technicians",
    "clients",
    "overtime_settings",
    "overtime_records",
    "finance_settings",
    "finance_contracts",
    "finance_monthly_reports",
    "cheque_notification_config",
    "cheque_requests",
    "cheque_request_items",
    "cheque_status_logs",
    "trading_invoices",
    "trading_invoice_items",
    "ticket_projects",
    "ticket_properties",
    "ticket_zones",
    "ticket_sub_zones",
    "ticket_base_units",
    "ticket_title_templates",
    "ticket_supervisor_teams",
    "tickets",
    "ticket_notes",
    "ticket_images",
    "ticket_manpower",
    "ticket_materials",
    "device_handovers",
    "mmr_chargeable_config",
    "qhse_compliance_imports",
    "qhse_staff_compliance_rows",
    "qhsi_trainings",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_pg_bool_columns(pg_cur, table):
    """Return set of column names that are BOOLEAN type in PostgreSQL."""
    pg_cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s AND data_type = 'boolean'
        """,
        (table,),
    )
    return {row[0] for row in pg_cur.fetchall()}


def table_exists_in_sqlite(conn, table):
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    result = cur.fetchone()
    cur.close()
    return result is not None


def sqlite_rows(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return cols, rows


def convert_row(row, cols, bool_cols):
    out = []
    for col, val in zip(cols, row):
        if isinstance(val, (dict, list)):
            out.append(json.dumps(val))
        elif col in bool_cols:
            out.append(None if val is None else bool(val))
        else:
            out.append(val)
    return tuple(out)


def reset_sequences(pg_cur, table):
    pg_cur.execute(f"SELECT pg_get_serial_sequence('\"{table}\"', 'id')")
    seq = pg_cur.fetchone()
    if seq and seq[0]:
        pg_cur.execute(
            f"SELECT setval('{seq[0]}', COALESCE((SELECT MAX(id) FROM \"{table}\"), 1))"
        )


def pg_bulk_insert(pg_conn, pg_cur, table, cols, rows, bool_cols):
    if not rows:
        return 0

    col_list = ", ".join([f'"{c}"' for c in cols])
    sql = f'INSERT INTO "{table}" ({col_list}) VALUES %s ON CONFLICT DO NOTHING'

    converted = [convert_row(r, cols, bool_cols) for r in rows]
    total = 0

    for i in range(0, len(converted), BATCH_SIZE):
        batch = converted[i : i + BATCH_SIZE]
        try:
            psycopg2.extras.execute_values(pg_cur, sql, batch, page_size=BATCH_SIZE)
            pg_conn.commit()
            total += len(batch)
            pct = int((i + len(batch)) / len(converted) * 100)
            print(f"\r  [{table}] {pct}% ({i + len(batch)}/{len(converted)}) ...", end="", flush=True)
        except Exception as e:
            pg_conn.rollback()
            print(f"\n  WARNING  Batch {i}-{i+len(batch)} failed ({table}): {e}")

    return total


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Source: {SQLITE_PATH}")
    if not os.path.exists(SQLITE_PATH):
        sys.exit(f"SQLite file not found: {SQLITE_PATH}")
    if not PG_URL:
        sys.exit(
            "Set PROD_DATABASE_URL (or DATABASE_URL) to the Render External Database URL.\n"
            '  export PROD_DATABASE_URL="postgresql://USER:PASS@HOST/DBNAME"'
        )
    sqlite_conn = sqlite3.connect(SQLITE_PATH)

    print("Connecting to Render PostgreSQL ...")
    try:
        pg_conn = psycopg2.connect(PG_URL, sslmode="require")
    except Exception as e:
        sys.exit(f"Cannot connect to PostgreSQL: {e}")
    pg_cur = pg_conn.cursor()
    print("Connected.\n")

    total_inserted = 0

    for table in TABLES:
        if not table_exists_in_sqlite(sqlite_conn, table):
            print(f"  [skip] {table} -- not in SQLite")
            continue

        cols, rows = sqlite_rows(sqlite_conn, table)

        if not rows:
            print(f"  [{table}] empty, skipped.")
            continue

        bool_cols = get_pg_bool_columns(pg_cur, table)
        inserted = pg_bulk_insert(pg_conn, pg_cur, table, cols, rows, bool_cols)

        try:
            reset_sequences(pg_cur, table)
            pg_conn.commit()
        except Exception as e:
            pg_conn.rollback()

        print(f"\r  [{table}] DONE  {inserted}/{len(rows)} rows inserted.         ")
        total_inserted += inserted

    sqlite_conn.close()
    pg_cur.close()
    pg_conn.close()
    print(f"\nDone. {total_inserted} total rows migrated to Render PostgreSQL.")


if __name__ == "__main__":
    main()
