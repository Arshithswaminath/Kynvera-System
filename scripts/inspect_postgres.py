"""
Read-only probe of a PostgreSQL database using DATABASE_URL from the environment.

Typical use (point at production or any Postgres):

1. Copy the connection string from your host (e.g. Render → PostgreSQL → credential / connection).
2. In the project root, set DATABASE_URL in a local `.env` (gitignored), e.g.:
   DATABASE_URL=postgresql://user:pass@host:5432/dbname
   Cloud hosts often require TLS — append to the URL, e.g. `?sslmode=require`
3. Keep FLASK_ENV=development while only inspecting — you do not need production Cloudinary keys.
4. Run from repo root:

   python scripts/inspect_postgres.py

Optional: python scripts/inspect_postgres.py --sample user 5
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def pg_quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def main() -> None:
    parser = argparse.ArgumentParser(description="List PostgreSQL tables and optional row samples.")
    parser.add_argument(
        "--sample",
        nargs=2,
        metavar=("TABLE", "LIMIT"),
        help="Print up to LIMIT rows from TABLE",
    )
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url or "sqlite" in url.lower():
        print(
            "Set DATABASE_URL to a PostgreSQL URL (not SQLite).\n"
            "Example: postgresql://user:pass@host:5432/db?sslmode=require",
            file=sys.stderr,
        )
        sys.exit(1)

    url = normalize_url(url)

    try:
        from sqlalchemy import create_engine, inspect, text
    except ImportError:
        print("Install SQLAlchemy (included with this app dependencies).", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(url)

    try:
        with engine.connect() as conn:
            one = conn.execute(text("SELECT 1")).scalar_one()
            if one != 1:
                print("Unexpected health check result", file=sys.stderr)
                sys.exit(1)
        print("Connection OK.\n")
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print(
            "\nTips: verify user/password/host/port. For managed Postgres (e.g. Render) use the "
            "external URL and append ?sslmode=require if the provider requires TLS.",
            file=sys.stderr,
        )
        sys.exit(1)

    insp = inspect(engine)
    names = insp.get_table_names()
    print(f"Tables ({len(names)}):\n")
    with engine.connect() as conn:
        for t in sorted(names):
            qi = pg_quote_ident(t)
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {qi}")).scalar_one()
            except Exception as e2:
                n = f"(count failed: {e2})"
            print(f"  {t}: {n} rows")

    if args.sample:
        raw_table, lim_s = args.sample
        lim = min(200, max(1, int(lim_s)))
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", raw_table):
            print("Table name must be a simple SQL identifier (letters, digits, underscore).", file=sys.stderr)
            sys.exit(1)
        print(f"\nSample from {raw_table} (limit {lim}):\n")
        qt = pg_quote_ident(raw_table)
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM {qt} LIMIT :lim"), {"lim": lim}).fetchall()
            cols = rows[0]._mapping.keys() if rows else []
            print(", ".join(cols))
            for row in rows:
                print(tuple(row))


if __name__ == "__main__":
    main()
