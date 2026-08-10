"""Seed sample FM Assets data for demos: assets, floor plans, predictions, linked tickets.

Usage:
  ./venv/bin/python scripts/seed_fm_assets.py
  ./venv/bin/python scripts/seed_fm_assets.py --clear   # remove prior seed rows first
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from app.models import (
    db, User, Asset, AssetPrediction, FloorPlan, Ticket,
)

SEED_TAG = '[FM-SEED]'
# Deterministic codes so re-runs are idempotent without --clear
SEED_ASSET_CODES = [f'AST-{i:04d}' for i in range(1, 13)]


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ticket_id():
    return 'TKT-' + uuid.uuid4().hex[:8].upper()


# Dubai Marina / DIFC-ish coords for map pins (spread slightly)
SAMPLE_ASSETS = [
    {
        'asset_id': 'AST-0001',
        'qr_code': 'QR-AST-0001',
        'name': 'Chiller Plant CH-01',
        'asset_type': 'chiller',
        'building': 'Tower A',
        'floor': 'B1',
        'room': 'Plant Room 1',
        'manufacturer': 'Carrier',
        'model': '30XA-1002',
        'serial_number': 'CR-CH-88421',
        'installation_date': date(2019, 3, 15),
        'warranty_expiry': date(2026, 9, 1),  # expiring soon
        'purchase_cost': 420000.0,
        'maintenance_cost_total': 48500.0,
        'status': 'critical',
        'health_score': 32,
        'latitude': 25.0805,
        'longitude': 55.1402,
        'notes': f'{SEED_TAG} Primary chilled-water plant — vibration and high condenser pressure.',
    },
    {
        'asset_id': 'AST-0002',
        'qr_code': 'QR-AST-0002',
        'name': 'AHU-A-L3-01',
        'asset_type': 'AHU',
        'building': 'Tower A',
        'floor': 'L3',
        'room': '2.105',
        'manufacturer': 'Trane',
        'model': 'CLCP-040',
        'serial_number': 'TR-AHU-33102',
        'installation_date': date(2020, 6, 1),
        'warranty_expiry': date(2025, 6, 1),  # expired
        'purchase_cost': 85000.0,
        'maintenance_cost_total': 12200.0,
        'status': 'critical',
        'health_score': 28,
        'latitude': 25.0810,
        'longitude': 55.1408,
        'notes': f'{SEED_TAG} Supply fan bearing noise; filter differential high.',
    },
    {
        'asset_id': 'AST-0003',
        'qr_code': 'QR-AST-0003',
        'name': 'Chilled Water Pump P-01',
        'asset_type': 'pump',
        'building': 'Tower A',
        'floor': 'B1',
        'room': 'Plant Room 1',
        'manufacturer': 'Grundfos',
        'model': 'CR 64-2',
        'serial_number': 'GF-P-11098',
        'installation_date': date(2019, 3, 20),
        'warranty_expiry': date(2027, 3, 20),
        'purchase_cost': 28000.0,
        'maintenance_cost_total': 4100.0,
        'status': 'active',
        'health_score': 74,
        'latitude': 25.0806,
        'longitude': 55.1403,
        'notes': f'{SEED_TAG} Duty pump for CH-01 circuit.',
    },
    {
        'asset_id': 'AST-0004',
        'qr_code': 'QR-AST-0004',
        'name': 'Fire Pump FP-01',
        'asset_type': 'fire_pump',
        'building': 'Tower A',
        'floor': 'B2',
        'room': 'Fire Pump Room',
        'manufacturer': 'Armstrong',
        'model': '4300',
        'serial_number': 'AR-FP-55201',
        'installation_date': date(2018, 11, 10),
        'warranty_expiry': date(2028, 11, 10),
        'purchase_cost': 95000.0,
        'maintenance_cost_total': 8600.0,
        'status': 'active',
        'health_score': 88,
        'latitude': 25.0804,
        'longitude': 55.1399,
        'notes': f'{SEED_TAG} Weekly test OK.',
    },
    {
        'asset_id': 'AST-0005',
        'qr_code': 'QR-AST-0005',
        'name': 'Elevator EL-A1',
        'asset_type': 'elevator',
        'building': 'Tower A',
        'floor': 'G',
        'room': 'Lobby Lift Lobby',
        'manufacturer': 'Otis',
        'model': 'Gen2-MR',
        'serial_number': 'OT-EL-90112',
        'installation_date': date(2018, 8, 1),
        'warranty_expiry': date(2026, 8, 20),  # expiring ~soon depending on today
        'purchase_cost': 210000.0,
        'maintenance_cost_total': 34000.0,
        'status': 'active',
        'health_score': 71,
        'latitude': 25.0811,
        'longitude': 55.1405,
        'notes': f'{SEED_TAG} Passenger elevator bank A.',
    },
    {
        'asset_id': 'AST-0006',
        'qr_code': 'QR-AST-0006',
        'name': 'Generator DG-01',
        'asset_type': 'generator',
        'building': 'Tower B',
        'floor': 'B1',
        'room': 'Generator Room',
        'manufacturer': 'Caterpillar',
        'model': 'C18',
        'serial_number': 'CAT-DG-77801',
        'installation_date': date(2017, 5, 12),
        'warranty_expiry': date(2024, 5, 12),
        'purchase_cost': 380000.0,
        'maintenance_cost_total': 52000.0,
        'status': 'active',
        'health_score': 65,
        'latitude': 25.0792,
        'longitude': 55.1415,
        'notes': f'{SEED_TAG} 1 MVA standby set — last load bank test 3 months ago.',
    },
    {
        'asset_id': 'AST-0007',
        'qr_code': 'QR-AST-0007',
        'name': 'AHU-B-L5-02',
        'asset_type': 'AHU',
        'building': 'Tower B',
        'floor': 'L5',
        'room': '5.210',
        'manufacturer': 'York',
        'model': 'YMAA-036',
        'serial_number': 'YK-AHU-22041',
        'installation_date': date(2021, 2, 18),
        'warranty_expiry': date(2027, 2, 18),
        'purchase_cost': 72000.0,
        'maintenance_cost_total': 5800.0,
        'status': 'active',
        'health_score': 82,
        'latitude': 25.0795,
        'longitude': 55.1418,
        'notes': f'{SEED_TAG} Office floor AHU.',
    },
    {
        'asset_id': 'AST-0008',
        'qr_code': 'QR-AST-0008',
        'name': 'Cooling Tower CT-01',
        'asset_type': 'cooling_tower',
        'building': 'Tower B',
        'floor': 'Roof',
        'room': 'Roof Plant',
        'manufacturer': 'BAC',
        'model': 'VTL-166',
        'serial_number': 'BAC-CT-44102',
        'installation_date': date(2019, 4, 2),
        'warranty_expiry': date(2026, 4, 2),
        'purchase_cost': 145000.0,
        'maintenance_cost_total': 29100.0,
        'status': 'critical',
        'health_score': 38,
        'latitude': 25.0793,
        'longitude': 55.1416,
        'notes': f'{SEED_TAG} Fill media fouling; basin level sensor intermittent.',
    },
    {
        'asset_id': 'AST-0009',
        'qr_code': 'QR-AST-0009',
        'name': 'Main LV Switchgear MSB-01',
        'asset_type': 'switchgear',
        'building': 'Tower B',
        'floor': 'B1',
        'room': 'Electrical Room',
        'manufacturer': 'Schneider',
        'model': 'Prisma P',
        'serial_number': 'SC-MSB-10001',
        'installation_date': date(2018, 9, 1),
        'warranty_expiry': date(2029, 9, 1),
        'purchase_cost': 260000.0,
        'maintenance_cost_total': 15500.0,
        'status': 'active',
        'health_score': 91,
        'latitude': 25.0791,
        'longitude': 55.1414,
        'notes': f'{SEED_TAG} Thermography clear last quarter.',
    },
    {
        'asset_id': 'AST-0010',
        'qr_code': 'QR-AST-0010',
        'name': 'Domestic Water Pump DW-01',
        'asset_type': 'pump',
        'building': 'Retail Podium',
        'floor': 'B1',
        'room': 'Pump Room',
        'manufacturer': 'Wilo',
        'model': 'Helix V 2202',
        'serial_number': 'WI-DW-33011',
        'installation_date': date(2022, 1, 10),
        'warranty_expiry': date(2027, 1, 10),
        'purchase_cost': 18500.0,
        'maintenance_cost_total': 2100.0,
        'status': 'active',
        'health_score': 86,
        'latitude': 25.0800,
        'longitude': 55.1425,
        'notes': f'{SEED_TAG} Soft-start booster set.',
    },
    {
        'asset_id': 'AST-0011',
        'qr_code': 'QR-AST-0011',
        'name': 'FAHU-Retail-01',
        'asset_type': 'FAHU',
        'building': 'Retail Podium',
        'floor': 'G',
        'room': 'Mall Mech Room',
        'manufacturer': 'Daikin',
        'model': 'UATYQ-C',
        'serial_number': 'DK-FAHU-88102',
        'installation_date': date(2022, 3, 22),
        'warranty_expiry': date(2027, 3, 22),
        'purchase_cost': 98000.0,
        'maintenance_cost_total': 7400.0,
        'status': 'active',
        'health_score': 79,
        'latitude': 25.0802,
        'longitude': 55.1427,
        'notes': f'{SEED_TAG} Fresh air handling for retail atrium.',
    },
    {
        'asset_id': 'AST-0012',
        'qr_code': 'QR-AST-0012',
        'name': 'Old Package Unit PAC-01',
        'asset_type': 'package_unit',
        'building': 'Tower A',
        'floor': 'Roof',
        'room': 'Roof PAC Bay',
        'manufacturer': 'Carrier',
        'model': '50TC',
        'serial_number': 'CR-PAC-19901',
        'installation_date': date(2012, 4, 1),
        'warranty_expiry': date(2017, 4, 1),
        'purchase_cost': 45000.0,
        'maintenance_cost_total': 61000.0,
        'status': 'decommissioned',
        'health_score': 10,
        'latitude': 25.0812,
        'longitude': 55.1401,
        'notes': f'{SEED_TAG} Decommissioned — replaced by VRF zone. Kept for history.',
    },
]

# Sample predictions keyed by asset_id (cached llm_estimate style)
SAMPLE_PREDICTIONS = {
    'AST-0001': {
        'failure_probability_pct': 68.0,
        'rul_days': 45,
        'predicted_maintenance_cost': 22000.0,
        'recommendation': 'maintain',
        'justification': f'{SEED_TAG} High condenser pressure + rising vibration trend; schedule tube cleaning and alignment within 2 weeks.',
    },
    'AST-0002': {
        'failure_probability_pct': 74.0,
        'rul_days': 21,
        'predicted_maintenance_cost': 8500.0,
        'recommendation': 'replace',
        'justification': f'{SEED_TAG} Bearing wear and expired warranty; replacement fan motor assembly recommended over repeated repairs.',
    },
    'AST-0008': {
        'failure_probability_pct': 55.0,
        'rul_days': 60,
        'predicted_maintenance_cost': 14000.0,
        'recommendation': 'maintain',
        'justification': f'{SEED_TAG} Fouling and sensor faults; clean fill and replace basin level probe.',
    },
}

# Simple SVG floor-plan data URL (no external dependency)
FLOOR_PLAN_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='800' height='500'>"
    "<rect width='800' height='500' fill='%231a2e24'/>"
    "<rect x='40' y='40' width='340' height='200' fill='%232a4a3a' stroke='%2388c9a0' stroke-width='2'/>"
    "<text x='60' y='80' fill='%23cfe7d8' font-family='sans-serif' font-size='18'>Plant Room 1</text>"
    "<rect x='420' y='40' width='340' height='200' fill='%232a4a3a' stroke='%2388c9a0' stroke-width='2'/>"
    "<text x='440' y='80' fill='%23cfe7d8' font-family='sans-serif' font-size='18'>Room 2.105</text>"
    "<rect x='40' y='280' width='720' height='180' fill='%232a4a3a' stroke='%2388c9a0' stroke-width='2'/>"
    "<text x='60' y='320' fill='%23cfe7d8' font-family='sans-serif' font-size='18'>Corridor / Lift Lobby</text>"
    "</svg>"
)

SAMPLE_FLOOR_PLANS = [
    {
        'name': f'{SEED_TAG} Tower A — L3 Mechanical',
        'building': 'Tower A',
        'floor': 'L3',
        'image_url': FLOOR_PLAN_SVG,
        'hotspots': [
            {'room': 'Plant Room 1', 'x_pct': 22, 'y_pct': 28, 'asset_ids': ['AST-0001', 'AST-0003']},
            {'room': '2.105', 'x_pct': 68, 'y_pct': 28, 'asset_ids': ['AST-0002']},
            {'room': 'Lobby Lift Lobby', 'x_pct': 50, 'y_pct': 72, 'asset_ids': ['AST-0005']},
        ],
    },
    {
        'name': f'{SEED_TAG} Tower B — Roof Plant',
        'building': 'Tower B',
        'floor': 'Roof',
        'image_url': FLOOR_PLAN_SVG,
        'hotspots': [
            {'room': 'Roof Plant', 'x_pct': 45, 'y_pct': 40, 'asset_ids': ['AST-0008']},
            {'room': '5.210', 'x_pct': 70, 'y_pct': 30, 'asset_ids': ['AST-0007']},
        ],
    },
]

# Tickets that demonstrate asset linking (integration with ticketing)
SAMPLE_TICKETS = [
    {
        'title': f'{SEED_TAG} Chiller CH-01 high condenser pressure',
        'work_description': 'Alarm: high condenser pressure on CH-01. Ops report rising chilled-water supply temp.',
        'asset_code': 'AST-0001',
        'project': 'Marina Towers',
        'service_group': 'HVAC',
        'category': 'Chiller',
        'fault_type': 'Performance',
        'priority': 'critical',
        'status': 'open',
        'property_name': 'Tower A',
        'zone': 'Basement Levels',
        'sub_zone': 'B1 – Plant',
        'sla_hours': 4,
        'projected_cost': 3500.0,
        'days_ago': 2,
    },
    {
        'title': f'{SEED_TAG} AHU-A-L3-01 supply fan bearing noise',
        'work_description': 'Loud bearing noise from supply fan; filter DP above setpoint.',
        'asset_code': 'AST-0002',
        'project': 'Marina Towers',
        'service_group': 'HVAC',
        'category': 'AHU',
        'fault_type': 'Mechanical',
        'priority': 'high',
        'status': 'in_progress',
        'property_name': 'Tower A',
        'zone': 'L3',
        'sub_zone': 'Mech',
        'sla_hours': 24,
        'projected_cost': 1800.0,
        'days_ago': 5,
    },
    {
        'title': f'{SEED_TAG} Cooling tower CT-01 basin sensor fault',
        'work_description': 'Basin level sensor intermittent; risk of dry-run on CT-01.',
        'asset_code': 'AST-0008',
        'project': 'Marina Towers',
        'service_group': 'HVAC',
        'category': 'Cooling Tower',
        'fault_type': 'Sensor',
        'priority': 'high',
        'status': 'open',
        'property_name': 'Tower B',
        'zone': 'Roof',
        'sla_hours': 12,
        'projected_cost': 900.0,
        'days_ago': 1,
    },
    {
        'title': f'{SEED_TAG} CH-01 quarterly tube cleaning (closed)',
        'work_description': 'Completed condenser tube cleaning and chemical treatment.',
        'asset_code': 'AST-0001',
        'project': 'Marina Towers',
        'service_group': 'HVAC',
        'category': 'Chiller',
        'fault_type': 'Preventive',
        'priority': 'medium',
        'status': 'closed',
        'property_name': 'Tower A',
        'zone': 'Basement Levels',
        'sla_hours': 48,
        'total_cost': 6200.0,
        'days_ago': 40,
    },
]


def clear_seed():
    """Remove previously seeded tickets / predictions / plans / assets."""
    # Tickets first (FK to assets)
    tickets = Ticket.query.filter(Ticket.title.like(f'{SEED_TAG}%')).all()
    for t in tickets:
        db.session.delete(t)
    print(f'  cleared {len(tickets)} seed tickets')

    preds = AssetPrediction.query.filter(
        AssetPrediction.justification.like(f'{SEED_TAG}%')
    ).all()
    for p in preds:
        db.session.delete(p)
    print(f'  cleared {len(preds)} seed predictions')

    plans = FloorPlan.query.filter(FloorPlan.name.like(f'{SEED_TAG}%')).all()
    for p in plans:
        db.session.delete(p)
    print(f'  cleared {len(plans)} seed floor plans')

    assets = Asset.query.filter(Asset.asset_id.in_(SEED_ASSET_CODES)).all()
    # Also catch by notes tag in case codes were reused
    tagged = Asset.query.filter(Asset.notes.like(f'{SEED_TAG}%')).all()
    by_id = {a.id: a for a in assets + tagged}
    for a in by_id.values():
        # null any non-seed tickets pointing at this asset
        Ticket.query.filter_by(asset_id=a.id).update({'asset_id': None})
        db.session.delete(a)
    print(f'  cleared {len(by_id)} seed assets')
    db.session.commit()


def seed():
    reporter = User.query.filter_by(role='admin').first() or User.query.first()
    if not reporter:
        print('ERROR: no users in DB — create an admin first.')
        return

    created_assets = 0
    updated_assets = 0
    asset_by_code = {}

    for row in SAMPLE_ASSETS:
        existing = Asset.query.filter_by(asset_id=row['asset_id']).first()
        if existing:
            for k, v in row.items():
                if k != 'asset_id':
                    setattr(existing, k, v)
            existing.updated_at = _utcnow()
            asset_by_code[row['asset_id']] = existing
            updated_assets += 1
        else:
            a = Asset(**row, created_at=_utcnow(), updated_at=_utcnow())
            db.session.add(a)
            db.session.flush()
            asset_by_code[row['asset_id']] = a
            created_assets += 1
    db.session.commit()
    print(f'Assets: {created_assets} created, {updated_assets} updated')

    # Predictions (one latest per asset — skip if seed prediction already present)
    pred_created = 0
    for code, pdata in SAMPLE_PREDICTIONS.items():
        asset = asset_by_code.get(code) or Asset.query.filter_by(asset_id=code).first()
        if not asset:
            continue
        already = AssetPrediction.query.filter_by(asset_pk=asset.id).filter(
            AssetPrediction.justification.like(f'{SEED_TAG}%')
        ).first()
        if already:
            for k, v in pdata.items():
                setattr(already, k, v)
            already.method = 'llm_estimate'
        else:
            db.session.add(AssetPrediction(
                asset_pk=asset.id,
                method='llm_estimate',
                created_at=_utcnow(),
                **pdata,
            ))
            pred_created += 1
    db.session.commit()
    print(f'Predictions: {pred_created} created/refreshed')

    # Floor plans
    plan_created = 0
    for prow in SAMPLE_FLOOR_PLANS:
        existing = FloorPlan.query.filter_by(name=prow['name']).first()
        if existing:
            existing.building = prow['building']
            existing.floor = prow['floor']
            existing.image_url = prow['image_url']
            existing.hotspots = prow['hotspots']
            existing.updated_at = _utcnow()
        else:
            db.session.add(FloorPlan(
                created_at=_utcnow(),
                updated_at=_utcnow(),
                **prow,
            ))
            plan_created += 1
    db.session.commit()
    print(f'Floor plans: {plan_created} created')

    # Linked tickets (integration demo)
    ticket_created = 0
    for trow in SAMPLE_TICKETS:
        exists = Ticket.query.filter_by(title=trow['title']).first()
        if exists:
            continue
        asset = asset_by_code.get(trow['asset_code']) or Asset.query.filter_by(
            asset_id=trow['asset_code']
        ).first()
        created = _utcnow() - timedelta(days=trow.get('days_ago', 1))
        ticket = Ticket(
            ticket_id=_ticket_id(),
            reporter_id=reporter.id,
            title=trow['title'],
            work_description=trow['work_description'],
            project=trow['project'],
            service_group=trow['service_group'],
            category=trow['category'],
            fault_type=trow['fault_type'],
            priority=trow['priority'],
            status=trow['status'],
            property_name=trow.get('property_name'),
            zone=trow.get('zone'),
            sub_zone=trow.get('sub_zone'),
            asset_id=asset.id if asset else None,
            sla_hours=trow.get('sla_hours'),
            projected_cost=trow.get('projected_cost'),
            total_cost=trow.get('total_cost'),
            created_at=created,
            updated_at=created,
            closed_at=created if trow['status'] == 'closed' else None,
            source='manual',
        )
        db.session.add(ticket)
        ticket_created += 1
    db.session.commit()
    print(f'Tickets (asset-linked): {ticket_created} created')

    print('\nDone. Open http://127.0.0.1:5002/assets/ to see the dashboard.')
    print('Try: list, map, twin, AST-0001 detail, and tickets linked to assets.')


def main():
    parser = argparse.ArgumentParser(description='Seed FM Assets sample data')
    parser.add_argument('--clear', action='store_true', help='Remove prior seed data first')
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from Injaaz import create_app

    app = create_app()
    with app.app_context():
        db.create_all()
        if args.clear:
            print('Clearing previous FM seed data…')
            clear_seed()
        print('Seeding FM Assets sample data…')
        seed()


if __name__ == '__main__':
    main()
