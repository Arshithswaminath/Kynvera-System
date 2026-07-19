#!/usr/bin/env python3
"""
Seed script: Import fire & life-safety materials into the database
as catalog_material records.

Run from project root:
  python scripts/seed_materials_catalog.py
  python scripts/seed_materials_catalog.py --clear

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

# Starter fire & life-safety catalog (department, name, brand, uom, unit_price)
FIRE_CATALOG = [
    # Fire Alarm
    ("Fire Alarm", "Addressable Fire Alarm Control Panel 2-Loop", "Notifier", "PCS", 12500.0),
    ("Fire Alarm", "Conventional Fire Alarm Control Panel 4-Zone", "Morley", "PCS", 3200.0),
    ("Fire Alarm", "Addressable Optical Smoke Detector", "System Sensor", "PCS", 185.0),
    ("Fire Alarm", "Addressable Heat Detector Rate-of-Rise", "System Sensor", "PCS", 195.0),
    ("Fire Alarm", "Multi-Sensor Smoke/Heat Detector", "Apollo", "PCS", 245.0),
    ("Fire Alarm", "Beam Smoke Detector Transmitter/Receiver Set", "FireBeam", "SET", 1850.0),
    ("Fire Alarm", "Manual Call Point Break-Glass", "KAC", "PCS", 95.0),
    ("Fire Alarm", "Manual Call Point Resettable", "KAC", "PCS", 110.0),
    ("Fire Alarm", "Addressable Sounder Beacon Red", "System Sensor", "PCS", 165.0),
    ("Fire Alarm", "Wall Mount Strobe Red LED", "System Sensor", "PCS", 120.0),
    ("Fire Alarm", "Fire Alarm Cable 2-Core 1.5mm FR", "Prysmian", "M", 4.5),
    ("Fire Alarm", "Fire Alarm Cable 4-Core 1.5mm FR", "Prysmian", "M", 6.8),
    ("Fire Alarm", "Isolator Module Addressable", "Apollo", "PCS", 175.0),
    ("Fire Alarm", "Monitor Module Addressable", "Notifier", "PCS", 210.0),
    ("Fire Alarm", "Control Relay Module Addressable", "Notifier", "PCS", 225.0),
    ("Fire Alarm", "Gas Detector Carbon Monoxide", "Honeywell", "PCS", 480.0),
    ("Fire Alarm", "Detector Base Standard", "System Sensor", "PCS", 35.0),
    ("Fire Alarm", "Remote Indicator LED", "Generic", "PCS", 28.0),

    # Fire Suppression
    ("Fire Suppression", "Sprinkler Head Pendant 68°C Standard Response", "Tyco", "PCS", 28.0),
    ("Fire Suppression", "Sprinkler Head Upright 68°C", "Tyco", "PCS", 30.0),
    ("Fire Suppression", "Sprinkler Head Concealed 68°C", "Victaulic", "PCS", 85.0),
    ("Fire Suppression", "FM200 Cylinder 80 Ltr Complete", "Kidde", "PCS", 8500.0),
    ("Fire Suppression", "CO2 Suppression Cylinder 45kg", "ANSUL", "PCS", 4200.0),
    ("Fire Suppression", "Foam Concentrate AFFF 3% 20L", "National Foam", "CAN", 650.0),
    ("Fire Suppression", "Deluge Valve DN100", "Viking", "PCS", 3800.0),
    ("Fire Suppression", "Water Mist Nozzle High Pressure", "Marioff", "PCS", 320.0),
    ("Fire Suppression", "Suppression Control Panel", "Kidde", "PCS", 5600.0),
    ("Fire Suppression", "Solenoid Actuator Valve", "ASCO", "PCS", 450.0),
    ("Fire Suppression", "Pressure Switch Suppression", "Potter", "PCS", 280.0),
    ("Fire Suppression", "Flexible Sprinkler Drop Hose 1m", "Generic", "PCS", 55.0),
    ("Fire Suppression", "Pipe Coupling Grooved 2 inch", "Victaulic", "PCS", 42.0),
    ("Fire Suppression", "Gate Valve OS&Y DN80", "NIBCO", "PCS", 380.0),

    # Fire Safety
    ("Fire Safety", "ABC Dry Powder Extinguisher 6kg", "NAFFCO", "PCS", 120.0),
    ("Fire Safety", "ABC Dry Powder Extinguisher 9kg", "NAFFCO", "PCS", 165.0),
    ("Fire Safety", "CO2 Fire Extinguisher 5kg", "NAFFCO", "PCS", 185.0),
    ("Fire Safety", "Foam Extinguisher 9L", "NAFFCO", "PCS", 175.0),
    ("Fire Safety", "Fire Hose Reel 30m Swing Type", "NAFFCO", "PCS", 850.0),
    ("Fire Safety", "Fire Blanket 1.2x1.8m", "Generic", "PCS", 65.0),
    ("Fire Safety", "Dry Riser Landing Valve DN65", "Generic", "PCS", 420.0),
    ("Fire Safety", "Fire Hydrant Valve Outdoor", "Generic", "PCS", 780.0),
    ("Fire Safety", "Fire Cabinet Double Door", "Generic", "PCS", 550.0),
    ("Fire Safety", "Sand Bucket with Stand", "Generic", "SET", 95.0),
    ("Fire Safety", "Electric Firefighting Pump 500 GPM", "Grundfos", "PCS", 18500.0),
    ("Fire Safety", "Diesel Fire Pump Set 750 GPM", "Clarke", "PCS", 42000.0),
    ("Fire Safety", "Jockey Pump 50 GPM", "Grundfos", "PCS", 4800.0),
    ("Fire Safety", "Fire Extinguisher Wall Bracket", "Generic", "PCS", 18.0),
    ("Fire Safety", "Hose Reel Nozzle Jet/Spray", "Generic", "PCS", 85.0),

    # Emergency
    ("Emergency", "Emergency Exit Sign LED Maintained", "Thorn", "PCS", 145.0),
    ("Emergency", "Emergency Bulkhead Light 3hr", "Thorn", "PCS", 165.0),
    ("Emergency", "Self-Contained Emergency Luminaire", "Philips", "PCS", 210.0),
    ("Emergency", "Photoluminescent Exit Sign", "Generic", "PCS", 55.0),
    ("Emergency", "Directional Wayfinding Sign Set", "Generic", "SET", 120.0),
    ("Emergency", "Public Address Speaker Ceiling", "Bosch", "PCS", 185.0),
    ("Emergency", "Evacuation Alarm Sounder", "Generic", "PCS", 95.0),
    ("Emergency", "Fire Door Closer Heavy Duty", "Dorma", "PCS", 320.0),
    ("Emergency", "Fire Door Intumescent Strip Kit", "Generic", "SET", 45.0),
    ("Emergency", "Assembly Point Signage Board", "Generic", "PCS", 180.0),
    ("Emergency", "Break-Glass Door Release Green", "Generic", "PCS", 75.0),
    ("Emergency", "Emergency Lighting Test Key Switch", "Generic", "PCS", 38.0),
]


def seed(clear=False):
    from Injaaz import create_app
    app = create_app()

    with app.app_context():
        from app.models import db, Submission

        if clear:
            deleted = Submission.query.filter_by(module_type="catalog_material").delete()
            db.session.commit()
            print(f"  Cleared {deleted} existing catalog_material records.")

        # Remove legacy trade-department catalog rows even without --clear
        legacy = ("HVAC", "Cleaning", "Electrical", "Plumbing")
        legacy_rows = Submission.query.filter_by(module_type="catalog_material").all()
        removed = 0
        for sub in legacy_rows:
            dept = (sub.form_data or {}).get("department", "")
            if dept in legacy:
                db.session.delete(sub)
                removed += 1
        if removed:
            db.session.commit()
            print(f"  Removed {removed} legacy HVAC/Cleaning/Electrical/Plumbing catalog items.")

        total = 0
        by_dept = {}
        for dept, name, brand, uom, price in FIRE_CATALOG:
            # Skip if an identical name already exists in this department
            exists = False
            for sub in Submission.query.filter_by(module_type="catalog_material").all():
                fd = sub.form_data or {}
                if fd.get("department") == dept and (fd.get("material_name") or "").strip().lower() == name.lower():
                    exists = True
                    break
            if exists:
                continue

            sid = f"CAT-FA-{uuid.uuid4().hex[:8].upper()}"
            sub = Submission(
                submission_id=sid,
                user_id=1,
                module_type="catalog_material",
                site_name=name[:255],
                visit_date=datetime.now().date(),
                status="active",
                workflow_status="active",
                supervisor_id=1,
                form_data={
                    "material_name": name,
                    "department": dept,
                    "brand": brand,
                    "uom": uom,
                    "unit_price": price,
                    "source_file": "seed_fire_catalog",
                },
            )
            db.session.add(sub)
            total += 1
            by_dept[dept] = by_dept.get(dept, 0) + 1

        db.session.commit()
        for dept, count in by_dept.items():
            print(f"  [OK] Seeded {count} {dept} materials")
        print(f"\n[DONE] Total seeded: {total} fire & life-safety materials.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed fire & life-safety materials catalog.")
    parser.add_argument("--clear", action="store_true", help="Clear existing catalog before seeding")
    args = parser.parse_args()
    seed(clear=args.clear)
