#!/usr/bin/env python3
"""
Injaaz — Local Database Browser

Always connects to the local SQLite file (injaaz.db) in this project folder.
Ignores DATABASE_URL in .env — safe for dev teams; never touches cloud/production.

Prerequisites:
  python scripts/init_db.py    # create tables + admin user (first time)
  ./run                        # optional — run the app to generate local data

Usage:
  python db_browser_local.py
  Open: http://localhost:8766

Same UI as db_browser.py: browse tables, search, edit rows, run SQL, export CSV.
"""
import os

# Must be set before db_browser is imported (so .env DATABASE_URL is ignored)
os.environ["INJAAZ_DB_BROWSER_LOCAL"] = "1"
os.environ.setdefault("DB_BROWSER_PORT", "8766")

from db_browser import LOCAL_DB_PATH, main

if __name__ == "__main__":
    if not os.path.isfile(LOCAL_DB_PATH):
        print(f"Local database not found: {LOCAL_DB_PATH}")
        print("Create it with:  python scripts/init_db.py")
        raise SystemExit(1)
    main()
