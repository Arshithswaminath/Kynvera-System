#!/usr/bin/env python3
"""
Push local Leave Tracker + Manpower Tracker rows to a Postgres DATABASE_URL (e.g. Render).

Usage (from repo root):

  # 1) Export from local SQLite (default ./injaaz.db)
  python scripts/push_hr_tracker_data.py export

  # 2) Set production URL (External Database URL from Render → Connect)
  export DATABASE_URL='postgresql://USER:PASS@HOST/DB?sslmode=require'

  # 3) Upsert into that database
  python scripts/push_hr_tracker_data.py push

Optional:
  python scripts/push_hr_tracker_data.py push --file tmp/hr_tracker_data_export.json
  python scripts/push_hr_tracker_data.py push --replace   # wipe target HR tracker tables first
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = ROOT / "injaaz.db"
DEFAULT_EXPORT = ROOT / "tmp" / "hr_tracker_data_export.json"

TABLE_ORDER = [
    "manpower_trades",
    "manpower_projects",
    "leave_employees",
    "hiring_candidates",
    "hiring_documents",
    "manpower_vacancies",
    "leave_logs",
    "leave_monthly_usage",
    "leave_plans",
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def export_sqlite(sqlite_path: Path, out_path: Path) -> dict:
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite not found: {sqlite_path}")
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    payload = {"exported_at": _utcnow_iso(), "source": str(sqlite_path), "tables": {}}
    for table in TABLE_ORDER:
        try:
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        except sqlite3.OperationalError as e:
            print(f"skip {table}: {e}")
            rows = []
        payload["tables"][table] = rows
        print(f"export {table}: {len(rows)}")
    conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return payload


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _parse_dt(val):
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    # SQLite often stores "2026-08-01 12:00:00.123456"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return s


def _parse_date(val):
    if val is None or val == "":
        return None
    s = str(val).strip()[:10]
    if not s:
        return None
    from datetime import date

    return date.fromisoformat(s)


DATE_COLS = {
    "leave_logs": {"leave_date", "end_date"},
    "leave_plans": {"start_date", "end_date"},
    "manpower_vacancies": {"date_joined", "needed_by"},
}
DT_COLS = {
    "leave_employees": {"created_at", "updated_at"},
    "leave_logs": {"created_at", "updated_at"},
    "leave_monthly_usage": {"updated_at"},
    "leave_plans": {"created_at", "updated_at"},
    "manpower_trades": {"created_at", "updated_at"},
    "manpower_projects": {"created_at", "updated_at"},
    "manpower_vacancies": {"created_at", "updated_at"},
    "hiring_candidates": {"created_at", "updated_at"},
    "hiring_documents": {"uploaded_at"},
}
BOOL_COLS = {
    "leave_employees": {"active"},
    "manpower_trades": {"active"},
    "manpower_projects": {"active"},
}
# Drop FKs that point at rows not present on the target DB
OPTIONAL_FKS = {
    "manpower_vacancies": (("hiring_candidate_id", "hiring_candidates"), ("created_by", "users")),
    "leave_logs": (("created_by", "users"),),
    "leave_plans": (("created_by", "users"),),
    "manpower_trades": (("created_by", "users"),),
    "manpower_projects": (("created_by", "users"),),
    "hiring_candidates": (("created_by", "users"),),
    "hiring_documents": (("uploaded_by", "users"),),
}


def _coerce_row(table: str, row: dict) -> dict:
    out = dict(row)
    for col in DATE_COLS.get(table, ()):
        if col in out:
            out[col] = _parse_date(out[col])
    for col in DT_COLS.get(table, ()):
        if col in out:
            out[col] = _parse_dt(out[col])
    for col in BOOL_COLS.get(table, ()):
        if col in out and out[col] is not None:
            out[col] = bool(out[col])
    return out


def push_postgres(payload: dict, database_url: str, *, replace: bool) -> None:
    from sqlalchemy import create_engine, inspect, text

    url = normalize_url(database_url)
    engine = create_engine(url)
    insp = inspect(engine)

    with engine.begin() as conn:
        conn.execute(text("SELECT 1"))
        print("Postgres connection OK")

        existing = set(insp.get_table_names())
        missing = [t for t in TABLE_ORDER if t not in existing]
        if missing:
            raise SystemExit(
                "Target DB is missing tables (deploy the latest app first so create_all / "
                f"migrations run): {', '.join(missing)}"
            )

        if replace:
            # Children first
            for table in reversed(TABLE_ORDER):
                n = conn.execute(text(f"DELETE FROM {table}")).rowcount
                print(f"cleared {table}: {n}")

        # Seed optional FK caches; refresh after each table that is a target
        fk_ok: dict[str, set[int]] = {}

        def _load_fk_ids(ref_table: str) -> set[int]:
            if ref_table not in existing:
                fk_ok[ref_table] = set()
                return fk_ok[ref_table]
            ids = conn.execute(text(f"SELECT id FROM {ref_table}")).fetchall()
            fk_ok[ref_table] = {int(r[0]) for r in ids}
            return fk_ok[ref_table]

        for _table, fks in OPTIONAL_FKS.items():
            for _col, ref_table in fks:
                if ref_table not in fk_ok:
                    _load_fk_ids(ref_table)

        for table in TABLE_ORDER:
            rows = payload.get("tables", {}).get(table) or []
            if not rows:
                print(f"push {table}: 0 (skip)")
                continue
            cols = [c["name"] for c in insp.get_columns(table)]
            pk = "id"
            upserted = 0
            cleared_fk = 0
            for raw in rows:
                row = _coerce_row(table, raw)
                data = {k: row.get(k) for k in cols if k in row}
                if not data or pk not in data:
                    continue
                for col, ref_table in OPTIONAL_FKS.get(table, ()):
                    val = data.get(col)
                    if val is None:
                        continue
                    try:
                        ival = int(val)
                    except (TypeError, ValueError):
                        data[col] = None
                        cleared_fk += 1
                        continue
                    if ival not in fk_ok.get(ref_table, set()):
                        data[col] = None
                        cleared_fk += 1
                col_names = list(data.keys())
                placeholders = ", ".join(f":{c}" for c in col_names)
                insert_cols = ", ".join(col_names)
                updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in col_names if c != pk)
                sql = (
                    f"INSERT INTO {table} ({insert_cols}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({pk}) DO UPDATE SET {updates}"
                )
                conn.execute(text(sql), data)
                upserted += 1
            # Keep sequences in sync with imported ids
            max_id = conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table}")).scalar()
            try:
                conn.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence(:tbl, 'id'), :val, true)"
                    ),
                    {"tbl": table, "val": int(max_id or 1)},
                )
            except Exception:
                pass
            # Refresh cache if this table is referenced by later OPTIONAL_FKS
            if any(ref == table for fks in OPTIONAL_FKS.values() for _c, ref in fks):
                _load_fk_ids(table)
            extra = f" (cleared {cleared_fk} orphan FKs)" if cleared_fk else ""
            print(f"push {table}: {upserted}{extra}")

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export/push Leave + Manpower tracker data")
    parser.add_argument("command", choices=("export", "push"))
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    parser.add_argument("--file", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing rows in target HR tracker tables before upsert",
    )
    args = parser.parse_args()

    if args.command == "export":
        export_sqlite(args.sqlite, args.file)
        return

    if not args.file.is_file():
        print(f"Export file missing; creating from {args.sqlite} …")
        export_sqlite(args.sqlite, args.file)

    payload = json.loads(args.file.read_text(encoding="utf-8"))
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url or "sqlite" in url.lower():
        raise SystemExit(
            "Set DATABASE_URL to the Render Postgres External URL, e.g.\n"
            "  export DATABASE_URL='postgresql://USER:PASS@HOST/DB?sslmode=require'\n"
            "Then re-run: python scripts/push_hr_tracker_data.py push"
        )
    push_postgres(payload, url, replace=args.replace)


if __name__ == "__main__":
    main()
