#!/usr/bin/env python3
"""
Seed script: Import HVAC, Cleaning, Plumbing, and Electrical materials
from the Excel price lists into the database as catalog_material records.

Run from project root:
  python scripts/seed_materials_catalog.py

Options:
  --clear    Delete existing catalog_material records before seeding
"""

import os
import sys
import argparse
import uuid
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

MATERIALS_DIR = r"D:\Materials List"

EXCEL_SOURCES = [
    {
        "department": "HVAC",
        "file": "HVAC.xlsx",
        "sheet": "HVAC",
        "header_row": 2,      # 0-indexed: row 3 in Excel
        "col_sno": 0,
        "col_name": 1,
        "col_brand": 2,
        "col_uom": 3,
        "col_price": 5,
    },
    {
        "department": "Cleaning",
        "file": "CLEANING.xlsx",
        "sheet": "Sheet1",
        "header_row": 1,      # 0-indexed: row 2 in Excel
        "col_sno": 0,
        "col_name": 1,
        "col_brand": None,
        "col_uom": None,
        "col_price": 3,
    },
    {
        "department": "Plumbing",
        "file": "PLUMBING.xlsx",
        "sheet": "Sheet1",
        "header_row": 1,
        "col_sno": 0,
        "col_name": 1,
        "col_brand": 2,
        "col_uom": None,
        "col_price": 4,
    },
    {
        "department": "Electrical",
        "file": "Electrical Materials Price Comparison.xlsx",
        "sheet": "INJAAZ COMPARISON",
        "header_row": 2,
        "col_sno": 0,
        "col_name": 1,
        "col_brand": 2,
        "col_uom": None,
        "col_price": 3,
    },
]


def safe_str(val):
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("none", "nan", "-") else s


def safe_price(val):
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def parse_excel(source):
    import openpyxl

    path = os.path.join(MATERIALS_DIR, source["file"])
    if not os.path.exists(path):
        print(f"  [SKIP] File not found: {path}")
        return []

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[source["sheet"]]

    rows = list(ws.iter_rows(values_only=True))
    data_start = source["header_row"] + 1  # skip header row

    materials = []
    for row in rows[data_start:]:
        # Skip empty rows
        if all(c is None for c in row):
            continue

        sno = row[source["col_sno"]] if source["col_sno"] is not None else None
        # Stop at footer / blank name rows
        if sno is None and (source["col_name"] >= len(row) or row[source["col_name"]] is None):
            continue

        name = safe_str(row[source["col_name"]]) if source["col_name"] < len(row) else ""
        if not name:
            continue

        brand = safe_str(row[source["col_brand"]]) if source["col_brand"] is not None and source["col_brand"] < len(row) else ""
        uom = safe_str(row[source["col_uom"]]) if source["col_uom"] is not None and source["col_uom"] < len(row) else "PCS"
        price = safe_price(row[source["col_price"]]) if source["col_price"] < len(row) else 0.0

        if not uom:
            uom = "PCS"

        materials.append({
            "name": name,
            "brand": brand,
            "uom": uom,
            "unit_price": price,
        })

    wb.close()
    return materials


def seed(clear=False):
    from Injaaz import create_app
    app = create_app()

    with app.app_context():
        from app.models import db, Submission

        if clear:
            deleted = Submission.query.filter_by(module_type="catalog_material").delete()
            db.session.commit()
            print(f"  Cleared {deleted} existing catalog_material records.")

        total = 0
        for source in EXCEL_SOURCES:
            dept = source["department"]
            print(f"\nProcessing {dept} ({source['file']})...")
            materials = parse_excel(source)
            print(f"  Parsed {len(materials)} materials")

            for mat in materials:
                sid = f"CAT-{dept[:3].upper()}-{uuid.uuid4().hex[:8].upper()}"
                sub = Submission(
                    submission_id=sid,
                    user_id=1,          # system / admin
                    module_type="catalog_material",
                    site_name=mat["name"][:255],
                    visit_date=datetime.now().date(),
                    status="active",
                    workflow_status="active",
                    supervisor_id=1,
                    form_data={
                        "material_name": mat["name"],
                        "department": dept,
                        "brand": mat["brand"],
                        "uom": mat["uom"],
                        "unit_price": mat["unit_price"],
                        "source_file": source["file"],
                    },
                )
                db.session.add(sub)
                total += 1

            db.session.commit()
            print(f"  [OK] Seeded {len(materials)} {dept} materials")

        print(f"\n[DONE] Total seeded: {total} materials across {len(EXCEL_SOURCES)} departments.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed materials catalog from Excel files.")
    parser.add_argument("--clear", action="store_true", help="Clear existing catalog before seeding")
    args = parser.parse_args()
    seed(clear=args.clear)
