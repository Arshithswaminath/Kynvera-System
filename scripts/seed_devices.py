"""Seed a demo Device Management fleet so the overview widgets look populated.

Usage:
  ./venv/bin/python scripts/seed_devices.py
  ./venv/bin/python scripts/seed_devices.py --clear
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SEED_PREFIX = 'DEV-OV-'


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _at(days_ago, hour, minute=12):
    now = _utcnow()
    day = (now - timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return day


def _months_back(months, hour, minute=12):
    now = _utcnow()
    month = now.month - months
    year = now.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(now.day, 28)
    return datetime(year, month, day, hour, minute, 0)


# last_active hours: 15=2pm, 13=1pm, 10=12pm, 21=11pm band
DEVICES = [
    # Recent last-seen mosaic (heatmap) + mixed status
    ('01', 'Ops Laptop — Fatima', 'Laptop', 'Windows 11', 'online', 96, 'Tower A', 0, 15, True, True),
    ('02', 'Ops Laptop — Ahmed', 'Laptop', 'macOS', 'online', 92, 'Tower A', 0, 13, True, True),
    ('03', 'Site Tablet — Gate 2', 'Tablet', 'iPadOS', 'online', 88, 'Tower B', 0, 10, True, True),
    ('04', 'Duty Phone — Night desk', 'Mobile', 'iOS', 'idle', 81, 'HQ', 0, 21, True, True),
    ('05', 'Helpdesk Desktop', 'Desktop', 'Windows 11', 'online', 90, 'HQ', 1, 15, True, True),
    ('06', 'Clinic Laptop — Noura', 'Laptop', 'Windows 11', 'online', 94, 'Clinic', 1, 13, True, True),
    ('07', 'Warehouse Handheld', 'Mobile', 'Android', 'idle', 72, 'Tower B', 1, 10, False, True),
    ('08', 'Reception iPad', 'Tablet', 'iPadOS', 'online', 86, 'HQ', 2, 15, True, True),
    ('09', 'Finance Laptop', 'Laptop', 'macOS', 'online', 91, 'Tower A', 2, 13, True, True),
    ('10', 'Facilities Desktop', 'Desktop', 'Windows 11', 'update', 64, 'Tower A', 2, 10, True, True),
    ('11', 'Security Console', 'Desktop', 'Windows 11', 'online', 84, 'HQ', 2, 21, True, True),
    ('12', 'Project Laptop — Khalid', 'Laptop', 'Windows 11', 'online', 89, 'Tower B', 3, 15, True, True),
    ('13', 'Site Tablet — Roof', 'Tablet', 'Android', 'idle', 77, 'Tower B', 3, 15, True, True),
    ('14', 'HR Laptop', 'Laptop', 'macOS', 'online', 93, 'HQ', 3, 13, True, True),
    ('15', 'Stores Handheld', 'Mobile', 'Android', 'online', 80, 'Clinic', 3, 10, False, True),
    ('16', 'Backup Laptop', 'Laptop', 'Windows 11', 'update', 58, 'Tower A', 3, 21, True, True),
    ('17', 'GM Laptop', 'Laptop', 'macOS', 'online', 97, 'HQ', 4, 15, True, True),
    ('18', 'Drafting Desktop', 'Desktop', 'Windows 11', 'online', 85, 'Tower A', 4, 15, True, True),
    ('19', 'Nurse Station Tablet', 'Tablet', 'iPadOS', 'online', 82, 'Clinic', 4, 13, True, True),
    ('20', 'Guard Phone', 'Mobile', 'Android', 'idle', 70, 'Tower B', 4, 21, False, True),
    ('21', 'Lab Laptop', 'Laptop', 'Windows 11', 'online', 87, 'Clinic', 5, 15, True, True),
    ('22', 'Workshop Tablet', 'Tablet', 'Android', 'online', 79, 'Tower B', 5, 13, True, True),
    ('23', 'Lobby Kiosk', 'Desktop', 'Windows 11', 'online', 83, 'HQ', 5, 10, True, True),
    ('24', 'On-call Phone', 'Mobile', 'iOS', 'idle', 74, 'HQ', 5, 21, True, True),
    ('25', 'New starter laptop', 'Laptop', 'Windows 11', 'online', 95, 'Tower A', 6, 15, True, True),
    ('26', 'Loaner Tablet', 'Tablet', 'iPadOS', 'idle', 68, 'HQ', 6, 13, False, True),
    # Follow-up pressure: offline / critical / unassigned / stale
    ('27', 'Spare Desktop — Store', 'Desktop', 'Windows 11', 'offline', 48, 'Tower A', 18, 11, False, False),
    ('28', 'Retired Laptop — IT cage', 'Laptop', 'Windows 10', 'offline', 31, None, 21, 9, False, False),
    ('29', 'Broken Phone — Repair', 'Mobile', 'Android', 'offline', 22, 'HQ', 16, 16, True, False),
    ('30', 'Patch queue laptop', 'Laptop', 'Windows 11', 'update', 51, 'Tower B', 2, 16, True, True),
    ('31', 'Unassigned Surface', 'Tablet', 'Windows 11', 'idle', 76, 'HQ', 3, 11, False, True),
    ('32', 'File server', 'Server', 'Ubuntu', 'online', 90, 'HQ', 1, 14, True, True),
]


def clear_seed():
    from app.models import db, Device
    rows = Device.query.filter(Device.device_id.like(SEED_PREFIX + '%')).all()
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    print(f'Cleared {len(rows)} seed devices')


def seed():
    from app.models import db, Device, User

    admin = User.query.filter_by(role='admin').first() or User.query.first()
    admin_id = admin.id if admin else None
    existing = {
        row.device_id: row
        for row in Device.query.filter(Device.device_id.like(SEED_PREFIX + '%')).all()
    }

    enroll_days = {
        '08': 2, '10': 2,
        '12': 3,
        '17': 4, '18': 4,
        '21': 5, '22': 5, '23': 5, '24': 5,
        '25': 6, '30': 6,
    }
    # Keep most last-seen recent for Weekly; park a few across the year for Monthly.
    year_seen = {
        '08': 8, '10': 7, '12': 6, '16': 5,
        '18': 4, '20': 3, '22': 2, '26': 1,
    }
    year_enroll = {
        '08': 8, '10': 7, '12': 6, '16': 5,
        '18': 4, '20': 3, '22': 2, '26': 1,
        '27': 8, '28': 7, '29': 6,
    }

    created = 0
    updated = 0
    for spec in DEVICES:
        code, name, dtype, os_name, status, health, building, days_ago, hour, assigned, has_serial = spec
        device_id = f'{SEED_PREFIX}{code}'
        when = _months_back(year_seen[code], hour) if code in year_seen else _at(days_ago, hour)
        row = existing.get(device_id) or Device(device_id=device_id)
        row.name = name
        row.device_type = dtype
        row.os = os_name
        row.status = status
        row.health = health
        row.building = building
        row.assigned_user_id = admin_id if assigned and admin_id else None
        row.serial_or_asset_tag = f'SN-OV-{code}' if has_serial else None
        row.last_active_at = when
        if code in year_enroll:
            row.created_at = _months_back(year_enroll[code], 9, 40)
        elif code in enroll_days:
            row.created_at = _at(enroll_days[code], 9, 40)
        else:
            row.created_at = _at(min(days_ago + 28, 80), 11)
        row.updated_at = when
        if device_id in existing:
            updated += 1
        else:
            db.session.add(row)
            created += 1
    db.session.commit()
    print(f'Device overview seed: {created} created, {updated} updated ({len(DEVICES)} total)')
    print('Open http://127.0.0.1:5002/admin/devices/')


def main():
    parser = argparse.ArgumentParser(description='Seed Device Management demo fleet')
    parser.add_argument('--clear', action='store_true', help='Remove DEV-OV-* rows first')
    args = parser.parse_args()
    from Injaaz import create_app
    from app.models import db

    app = create_app()
    with app.app_context():
        db.create_all()
        if args.clear:
            clear_seed()
        seed()


if __name__ == '__main__':
    main()
