#!/usr/bin/env python3
"""Seed procurement catalogs, properties, stock, suppliers, and sample PRs.

Usage (from project root):
  ./venv/bin/python scripts/seed_procurement.py
  ./venv/bin/python scripts/seed_procurement.py --clear
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

SEED_TAG = '[PROC-SEED]'

HVAC = [
    ('HEPA Filter 24x24', 'Camfil', 'PCS', 85, 4),
    ('Pleated Filter G4 20x20', 'Camfil', 'PCS', 28, 8),
    ('Bag Filter F7 592x592', 'Camfil', 'PCS', 145, 3),
    ('R410A Refrigerant 11.3kg', 'Honeywell', 'CYL', 420, 2),
    ('R134a Refrigerant 13.6kg', 'Honeywell', 'CYL', 310, 2),
    ('Compressor 1.5 Ton Scroll', 'Daikin', 'PCS', 1850, 1),
    ('Compressor 2.0 Ton Scroll', 'Daikin', 'PCS', 2420, 1),
    ('AHU Belt SPZ-1250', 'Gates', 'PCS', 45, 6),
    ('Thermostat Digital 24V', 'Honeywell', 'PCS', 190, 3),
    ('Copper Pipe 1/2 inch 15m', 'Mueller', 'COIL', 165, 4),
    ('Copper Pipe 3/8 inch 15m', 'Mueller', 'COIL', 128, 4),
    ('Insulation Tube 1/2 inch', 'Armaflex', 'M', 12, 20),
    ('Condensate Pump 230V', 'Sauermann', 'PCS', 275, 2),
    ('FCU Motor 1/8 HP', 'Siemens', 'PCS', 340, 2),
    ('Capacitor 35/5 MFD', 'Epcos', 'PCS', 38, 10),
    ('Contactor 3P 18A', 'Schneider', 'PCS', 95, 4),
    ('Expansion Valve 3/8', 'Danfoss', 'PCS', 210, 2),
    ('Pressure Gauge R410A', 'Refco', 'PCS', 72, 3),
    ('Air Filter Carbon 24x24', 'Camfil', 'PCS', 110, 3),
    ('Drain Pan Treatment Tabs', 'Nu-Calgon', 'BOX', 48, 6),
]
CLEANING = [
    ('Floor Cleaner Neutral 5L', 'Diversey', 'CAN', 42, 8),
    ('Disinfectant 5L', 'Diversey', 'CAN', 55, 6),
    ('Glass Cleaner 750ml', 'Taski', 'BTL', 18, 12),
    ('Toilet Bowl Cleaner 1L', 'Harpic', 'BTL', 14, 12),
    ('Mop Handle Aluminium', 'Vileda', 'PCS', 35, 6),
    ('Wet Mop Head Cotton', 'Vileda', 'PCS', 16, 10),
    ('Microfibre Cloth Pack 10', 'Vileda', 'PK', 22, 8),
    ('Yellow Dust Cloth Pack', 'Vileda', 'PK', 12, 8),
    ('Bucket Wringer 20L', 'Rubbermaid', 'PCS', 95, 3),
    ('Janitor Trolley', 'Rubbermaid', 'PCS', 420, 1),
    ('Garbage Bag 90L Black', 'Generic', 'RL', 28, 10),
    ('Garbage Bag 30L', 'Generic', 'RL', 16, 10),
    ('Hand Soap 5L', 'Deb', 'CAN', 38, 6),
    ('Paper Towel Roll', 'Tork', 'PCS', 9, 20),
    ('Toilet Tissue 2-Ply Case', 'Tork', 'CS', 48, 6),
    ('Air Freshener 300ml', 'Glade', 'CAN', 15, 8),
    ('Scrub Pad Heavy Duty', 'Scotch-Brite', 'PK', 11, 10),
    ('Floor Sign Wet Floor', 'Rubbermaid', 'PCS', 32, 4),
    ('Vacuum Bags Type H', 'Nilfisk', 'PK', 36, 4),
    ('Carpet Shampoo 5L', 'Taski', 'CAN', 64, 3),
]
ELECTRICAL = [
    ('MCB 1P 10A', 'ABB', 'PCS', 18, 12),
    ('MCB 1P 16A', 'ABB', 'PCS', 19, 12),
    ('MCB 1P 32A', 'ABB', 'PCS', 24, 8),
    ('RCCB 2P 40A 30mA', 'Schneider', 'PCS', 85, 4),
    ('LED Tube 18W 4ft', 'Philips', 'PCS', 22, 16),
    ('LED Downlight 12W', 'Philips', 'PCS', 28, 12),
    ('LED Bulkhead 20W', 'Philips', 'PCS', 45, 6),
    ('Switch 1-Gang 13A', 'MK', 'PCS', 14, 20),
    ('Socket 13A Twin', 'MK', 'PCS', 18, 16),
    ('Cable 2.5mm 100m', 'Ducab', 'RL', 210, 3),
    ('Cable 1.5mm 100m', 'Ducab', 'RL', 145, 3),
    ('Cable Tie 300mm Pack', 'Hellermann', 'PK', 12, 10),
    ('Junction Box 4x4', 'Generic', 'PCS', 8, 20),
    ('PVC Conduit 20mm 3m', 'Generic', 'PCS', 6, 24),
    ('Emergency Light Twin', 'Cooper', 'PCS', 95, 4),
    ('Exhaust Fan 6 inch', 'KDK', 'PCS', 85, 4),
    ('Ceiling Fan 56 inch', 'KDK', 'PCS', 165, 2),
    ('Timer Switch Digital', 'Theben', 'PCS', 72, 3),
    ('Photocell Street', 'Generic', 'PCS', 38, 4),
    ('LED Exit Sign', 'Cooper', 'PCS', 110, 3),
]
PLUMBING = [
    ('Mixer Basin Chrome', 'Grohe', 'PCS', 185, 3),
    ('Mixer Kitchen Chrome', 'Grohe', 'PCS', 245, 2),
    ('WC Pan Close Coupled', 'Roca', 'PCS', 420, 1),
    ('WC Seat Soft Close', 'Roca', 'PCS', 65, 3),
    ('Wash Basin White', 'Roca', 'PCS', 195, 2),
    ('Bottle Trap 32mm', 'McAlpine', 'PCS', 28, 8),
    ('P-Trap 40mm', 'McAlpine', 'PCS', 32, 6),
    ('Angle Valve 1/2', 'Grohe', 'PCS', 22, 12),
    ('Flexible Hose 50cm', 'Generic', 'PCS', 14, 16),
    ('Ball Valve 1/2 Brass', 'Pegler', 'PCS', 18, 10),
    ('Gate Valve 3/4', 'Pegler', 'PCS', 24, 6),
    ('PVC Pipe 110mm 3m', 'Generic', 'PCS', 35, 8),
    ('PVC Pipe 50mm 3m', 'Generic', 'PCS', 18, 10),
    ('uPVC Elbow 90 110mm', 'Generic', 'PCS', 8, 16),
    ('Silicone Sanitary White', 'Dow', 'TUBE', 16, 12),
    ('PTFE Tape 12mm', 'Generic', 'RL', 3, 24),
    ('Float Valve 1/2', 'Fluidmaster', 'PCS', 38, 4),
    ('Shower Head Chrome', 'Grohe', 'PCS', 95, 3),
    ('Floor Drain 100mm', 'Generic', 'PCS', 22, 6),
    ('Water Pump 0.5 HP', 'Grundfos', 'PCS', 480, 1),
]

PROPERTIES = [
    ('Tower A', 'Dubai Marina, Tower A', 'Main residential tower'),
    ('Tower B', 'Dubai Marina, Tower B', 'Second residential tower'),
    ('Podium', 'Dubai Marina podium', 'Retail and amenity levels'),
    ('Plant Room', 'Tower A basement B1', 'Chiller plant and tanks'),
]

SUPPLIERS = [
    ('Gulf Filters LLC', 'Aisha Rahman', 'sales@gulffilters.example', '+971 4 555 0101', 'HVAC'),
    ('Al Futtaim Engineering Supplies', 'Omar Haddad', 'omar.h@afeng.example', '+971 4 555 0202', 'HVAC, Electrical'),
    ('CleanCo Trading', 'Priya Nair', 'priya@cleanco.example', '+971 4 555 0303', 'Cleaning'),
    ('Emirates Sanitaryware', 'Youssef Mansour', 'y.mansour@ess.example', '+971 4 555 0404', 'Plumbing'),
    ('Ducab Distribution', 'James Cole', 'jcole@ducab.example', '+971 4 555 0505', 'Electrical'),
]


def _goc_user():
    from app.models import User
    return (
        User.query.filter_by(username='demo_procurement').first()
        or User.query.filter_by(role='admin').first()
        or User.query.first()
    )


def seed_procurement(clear=False):
    from app.models import db
    from module_procurement.models import (
        ProcCatalogItem, ProcProperty, ProcStock, ProcSupplier,
        ProcPurchaseRequest, ProcPurchaseLine, ProcMovement,
        ProcGoodsReceipt, ProcGoodsReceiptLine,
    )
    from module_procurement import service as svc

    if clear:
        ProcGoodsReceiptLine.query.delete()
        ProcGoodsReceipt.query.delete()
        ProcPurchaseLine.query.delete()
        ProcPurchaseRequest.query.delete()
        ProcMovement.query.delete()
        ProcStock.query.delete()
        ProcCatalogItem.query.delete()
        ProcProperty.query.delete()
        ProcSupplier.query.delete()
        db.session.commit()

    user = _goc_user()
    suppliers = {}
    for i, (name, contact, email, phone, trades) in enumerate(SUPPLIERS, 1):
        row = ProcSupplier.query.filter_by(name=name).first()
        if not row:
            row = ProcSupplier(
                public_id=f'SUP-SEED{i:02d}',
                name=name, contact_name=contact, contact_email=email,
                contact_phone=phone, trades=trades, notes=SEED_TAG, is_active=True,
            )
            db.session.add(row)
            db.session.flush()
        suppliers[trades.split(',')[0].strip()] = row

    props = {}
    for i, (name, address, desc) in enumerate(PROPERTIES, 1):
        row = svc.get_or_create_property(
            name, address=address, description=f'{SEED_TAG} {desc}',
            public_id=f'PROC-PROP-SEED{i}',
        )
        props[name] = row

    shared = svc.ensure_shared_property()
    props['Shared'] = shared

    catalog = {}
    for dept, items, supplier_key in (
        ('HVAC', HVAC, 'HVAC'),
        ('Cleaning', CLEANING, 'Cleaning'),
        ('Electrical', ELECTRICAL, 'Electrical'),
        ('Plumbing', PLUMBING, 'Plumbing'),
    ):
        for i, (name, brand, uom, price, min_qty) in enumerate(items, 1):
            item = svc.get_or_create_catalog_item(
                department=dept, name=name, brand=brand, uom=uom,
                unit_price=price, is_rate_card=True, min_qty=min_qty,
                public_id=f'CAT-{dept[:3].upper()}-S{i:02d}',
                supplier=suppliers.get(supplier_key),
            )
            catalog[(dept, name)] = item

    db.session.flush()

    # Stock: Tower A well stocked, Plant Room HVAC-heavy, some below min.
    stock_plan = [
        ('Tower A', 'HVAC', 'HEPA Filter 24x24', 2),       # below min 4
        ('Tower A', 'HVAC', 'Pleated Filter G4 20x20', 20),
        ('Tower A', 'Cleaning', 'Floor Cleaner Neutral 5L', 10),
        ('Tower A', 'Electrical', 'LED Tube 18W 4ft', 24),
        ('Tower A', 'Plumbing', 'Bottle Trap 32mm', 12),
        ('Tower B', 'HVAC', 'Thermostat Digital 24V', 6),
        ('Tower B', 'Cleaning', 'Garbage Bag 90L Black', 8),
        ('Tower B', 'Electrical', 'MCB 1P 16A', 18),
        ('Tower B', 'Plumbing', 'Angle Valve 1/2', 10),
        ('Podium', 'Cleaning', 'Janitor Trolley', 1),
        ('Podium', 'Electrical', 'LED Downlight 12W', 8),
        ('Podium', 'Plumbing', 'Mixer Basin Chrome', 2),
        ('Plant Room', 'HVAC', 'R410A Refrigerant 11.3kg', 1),  # below min 2
        ('Plant Room', 'HVAC', 'Compressor 1.5 Ton Scroll', 1),
        ('Plant Room', 'Electrical', 'Cable 2.5mm 100m', 2),
        ('Plant Room', 'Plumbing', 'Water Pump 0.5 HP', 1),
        ('Shared', 'HVAC', 'HEPA Filter 24x24', 8),
        ('Shared', 'Electrical', 'Cable Tie 300mm Pack', 40),
        ('Shared', 'Plumbing', 'PTFE Tape 12mm', 30),
    ]
    for prop_name, dept, item_name, qty in stock_plan:
        item = catalog.get((dept, item_name))
        prop = props[prop_name]
        if not item:
            continue
        slug = prop_name.replace(' ', '')[:8]
        stock = svc.get_or_create_stock(
            prop, item, public_id=f'PROC-MAT-{dept[:3]}-{slug}-{item.id}',
        )
        if float(stock.qty_on_hand or 0) == 0:
            svc.adjust_stock(stock, qty, user=user, movement_type='adjust', notes=SEED_TAG)

    # Sample PRs
    hepa = catalog[('HVAC', 'HEPA Filter 24x24')]
    r410 = catalog[('HVAC', 'R410A Refrigerant 11.3kg')]
    compressor = catalog[('HVAC', 'Compressor 1.5 Ton Scroll')]

    def _pr(pid, status, prop, supplier, lines, notes, needs_gm=False):
        existing = ProcPurchaseRequest.query.filter_by(public_id=pid).first()
        if existing:
            return existing
        total = sum(q * p for _, q, p in lines)
        pr = ProcPurchaseRequest(
            public_id=pid, status=status, property=prop, supplier=supplier,
            requested_by=user, notes=f'{SEED_TAG} {notes}',
            total_aed=total, needs_gm=needs_gm or total >= 1000,
        )
        db.session.add(pr)
        db.session.flush()
        for item, qty, price in lines:
            db.session.add(ProcPurchaseLine(request=pr, catalog_item=item, qty=qty, unit_price=price))
        return pr

    _pr('PR-SEED-001', 'procurement_review', props['Tower A'], suppliers.get('HVAC'),
        [(hepa, 12, 85)], 'Reorder HEPA filters for Tower A AHUs')
    _pr('PR-SEED-002', 'approved', props['Plant Room'], suppliers.get('HVAC'),
        [(r410, 2, 420)], 'Refrigerant top-up for CH-01')
    _pr('PR-SEED-003', 'gm_review', props['Plant Room'], suppliers.get('HVAC'),
        [(compressor, 1, 1850)], 'Spare scroll compressor — over GM threshold', needs_gm=True)

    activity = _seed_demo_activity(user, catalog, props, suppliers)
    daily_issues = _seed_daily_rhythm(user, catalog, props)

    db.session.commit()
    return {
        'catalog': ProcCatalogItem.query.filter_by(is_rate_card=True).count(),
        'properties': ProcProperty.query.count(),
        'stock': ProcStock.query.count(),
        'suppliers': ProcSupplier.query.count(),
        'prs': ProcPurchaseRequest.query.count(),
        'issues': activity.get('issues', 0),
        'received_prs': activity.get('received_prs', 0),
        'daily_issues': daily_issues,
    }


def _shift_months(dt, months):
    year = dt.year
    month = dt.month - months
    while month <= 0:
        month += 12
        year -= 1
    return dt.replace(year=year, month=month, day=min(dt.day, 28))


def _seed_demo_activity(user, catalog, props, suppliers):
    """Backdated ticket issues + received PRs so the dashboard charts have life."""
    from datetime import timedelta

    from app.models import Ticket, TicketMaterial, db
    from module_procurement.models import ProcMovement, ProcPurchaseLine, ProcPurchaseRequest, _utcnow

    already = ProcMovement.query.filter(
        ProcMovement.movement_type == 'issue',
        ProcMovement.notes.like(f'{SEED_TAG}%'),
    ).count()
    if already:
        return {'issues': already, 'received_prs': 0}

    now = _utcnow()
    reporter_id = user.id if user else 1

    ticket_specs = [
        ('TKT-PROC-01', 'Tower A', 'HVAC', 'AHU filter change — Tower A L12'),
        ('TKT-PROC-02', 'Tower B', 'Electrical', 'Lighting fault — Tower B lobby'),
        ('TKT-PROC-03', 'Podium', 'Cleaning', 'Deep clean — podium washrooms'),
        ('TKT-PROC-04', 'Plant Room', 'Plumbing', 'Condensate leak — plant room'),
        ('TKT-PROC-05', 'Tower A', 'Electrical', 'MCB trip — apartment riser'),
        ('TKT-PROC-06', 'Tower B', 'HVAC', 'FCU no cooling — Tower B 804'),
    ]
    tickets = []
    for code, prop_name, trade, title in ticket_specs:
        row = Ticket.query.filter_by(ticket_id=code).first()
        if not row:
            row = Ticket(
                ticket_id=code,
                reporter_id=reporter_id,
                title=title,
                project='Marina',
                service_group=trade,
                category=trade,
                fault_type='Maintenance',
                priority='medium',
                work_description=f'{SEED_TAG} Demo ticket for procurement usage history.',
                status='work_started',
                property_name=prop_name,
            )
            db.session.add(row)
            db.session.flush()
        tickets.append(row)

    by_dept = {}
    for (dept, _name), item in catalog.items():
        by_dept.setdefault(dept, []).append(item)

    monthly = {
        'HVAC':       [12, 14, 18, 22, 16, 11, 9, 13, 19, 24, 21, 28],
        'Cleaning':   [8, 9, 11, 13, 12, 9, 8, 10, 14, 16, 13, 18],
        'Electrical': [7, 10, 12, 15, 17, 12, 10, 11, 14, 18, 16, 20],
        'Plumbing':   [4, 6, 7, 9, 8, 6, 5, 6, 9, 11, 10, 14],
    }
    prop_cycle = ['Tower A', 'Tower B', 'Podium', 'Plant Room']
    issues = 0
    for back in range(11, -1, -1):
        when = _shift_months(now.replace(hour=10, minute=15, second=0, microsecond=0), back)
        month_idx = 11 - back
        for dept, series in monthly.items():
            qty_left = series[month_idx]
            items = by_dept.get(dept) or []
            if not items:
                continue
            chunk = 0
            while qty_left > 0:
                item = items[chunk % len(items)]
                take = min(qty_left, 2 + (chunk % 3))
                ticket = tickets[(chunk + month_idx) % len(tickets)]
                prop = props[prop_cycle[chunk % len(prop_cycle)]]
                db.session.add(ProcMovement(
                    movement_type='issue',
                    property_id=prop.id,
                    catalog_item_id=item.id,
                    qty=-float(take),
                    user_id=reporter_id,
                    ticket_id=ticket.id,
                    notes=f'{SEED_TAG} Issue to {ticket.ticket_id}',
                    created_at=when.replace(hour=9 + (chunk % 8), minute=10 + chunk),
                ))
                issues += 1
                qty_left -= take
                chunk += 1

    week_qtys = [6, 8, 11, 7, 14, 10, 13, 16]
    for w, wqty in enumerate(week_qtys):
        when = now - timedelta(days=7 * (7 - w), hours=3)
        dept = ('HVAC', 'Cleaning', 'Electrical', 'Plumbing')[w % 4]
        items = by_dept.get(dept) or []
        if not items:
            continue
        item = items[w % len(items)]
        ticket = tickets[w % len(tickets)]
        prop = props.get(ticket.property_name) or props['Tower A']
        db.session.add(ProcMovement(
            movement_type='issue',
            property_id=prop.id,
            catalog_item_id=item.id,
            qty=-float(wqty),
            user_id=reporter_id,
            ticket_id=ticket.id,
            notes=f'{SEED_TAG} Issue to {ticket.ticket_id}',
            created_at=when,
        ))
        issues += 1
        if TicketMaterial.query.filter_by(ticket_id=ticket.id, material_name=item.name).count() == 0:
            db.session.add(TicketMaterial(
                ticket_id=ticket.id,
                material_name=item.name,
                quantity=float(wqty),
                unit=item.uom or 'PCS',
                unit_price=float(item.unit_price or 0),
                total_price=round(float(wqty) * float(item.unit_price or 0), 2),
                from_procurement=True,
                procurement_ref=item.public_id,
                catalog_item_id=item.id,
                notes=SEED_TAG,
            ))

    hepa = catalog[('HVAC', 'HEPA Filter 24x24')]
    g4 = catalog[('HVAC', 'Pleated Filter G4 20x20')]
    cleaner = catalog[('Cleaning', 'Floor Cleaner Neutral 5L')]
    disinfectant = catalog[('Cleaning', 'Disinfectant 5L')]
    led = catalog[('Electrical', 'LED Tube 18W 4ft')]
    mcb = catalog[('Electrical', 'MCB 1P 16A')]
    trap = catalog[('Plumbing', 'Bottle Trap 32mm')]

    received_specs = [
        ('PR-SEED-004', 'Tower A', 'HVAC',
         [(hepa, 12, 85), (g4, 20, 28)],
         'Received HEPA + G4 restock', timedelta(days=6)),
        ('PR-SEED-005', 'Podium', 'Cleaning',
         [(cleaner, 16, 42), (disinfectant, 10, 55)],
         'Podium chemicals received', timedelta(days=3)),
        ('PR-SEED-006', 'Tower B', 'Electrical',
         [(led, 40, 22), (mcb, 24, 19)],
         'Lighting and MCB restock', timedelta(days=1)),
        ('PR-SEED-007', 'Plant Room', 'Plumbing',
         [(trap, 20, 28)],
         'Previous-month traps (for period delta)', None),
    ]
    received_count = 0
    for pid, prop_name, supplier_key, lines, notes, ago in received_specs:
        existing = ProcPurchaseRequest.query.filter_by(public_id=pid).first()
        if existing:
            received_count += 1
            continue
        if ago is None:
            received_at = _shift_months(now.replace(day=18, hour=11, minute=0, second=0, microsecond=0), 1)
        else:
            received_at = now - ago
        total = sum(q * p for _, q, p in lines)
        pr = ProcPurchaseRequest(
            public_id=pid, status='received', property=props[prop_name],
            supplier=suppliers.get(supplier_key), requested_by=user,
            notes=f'{SEED_TAG} {notes}', total_aed=total, needs_gm=False,
            approved_at=received_at - timedelta(days=2),
            ordered_at=received_at - timedelta(days=1),
            received_at=received_at,
        )
        db.session.add(pr)
        db.session.flush()
        for item, qty, price in lines:
            db.session.add(ProcPurchaseLine(request=pr, catalog_item=item, qty=qty, unit_price=price))
            db.session.add(ProcMovement(
                movement_type='receipt',
                property_id=props[prop_name].id,
                catalog_item_id=item.id,
                qty=float(qty),
                user_id=reporter_id,
                request_id=pr.id,
                notes=f'{SEED_TAG} GRN {pid}',
                created_at=received_at,
            ))
        received_count += 1

    db.session.flush()
    return {'issues': issues, 'received_prs': received_count}


SEED_DAYS_TAG = '[PROC-SEED-DAYS]'


def _seed_daily_rhythm(user, catalog, props):
    """Spread ticket issues across recent days so the breakdown needle chart has life."""
    from datetime import timedelta

    from app.models import Ticket, db
    from module_procurement.models import ProcMovement, _utcnow

    already = ProcMovement.query.filter(
        ProcMovement.movement_type == 'issue',
        ProcMovement.notes.like(f'{SEED_DAYS_TAG}%'),
    ).count()
    if already:
        return already

    now = _utcnow()
    reporter_id = user.id if user else 1
    tickets = Ticket.query.filter(Ticket.ticket_id.like('TKT-PROC-%')).order_by(Ticket.id).all()
    if not tickets:
        return 0

    by_dept = {}
    for (dept, _name), item in catalog.items():
        by_dept.setdefault(dept, []).append(item)
    trades = ('HVAC', 'Cleaning', 'Electrical', 'Plumbing')
    wave = [4, 7, 11, 5, 13, 8, 6, 15, 9, 12, 4, 10, 8, 18, 7, 14, 6, 11, 9, 16, 5, 12, 8, 14, 10, 7, 19, 8]
    created = 0
    for ago in range(55, -1, -1):
        qty = max(2, wave[ago % len(wave)] - (ago % 4))
        when = (now - timedelta(days=ago)).replace(hour=8 + (ago % 9), minute=12 + (ago % 40), second=0, microsecond=0)
        dept = trades[ago % 4]
        items = by_dept.get(dept) or []
        if not items:
            continue
        item = items[ago % len(items)]
        ticket = tickets[ago % len(tickets)]
        prop = props.get(ticket.property_name) or next(iter(props.values()))
        db.session.add(ProcMovement(
            movement_type='issue',
            property_id=prop.id,
            catalog_item_id=item.id,
            qty=-float(qty),
            user_id=reporter_id,
            ticket_id=ticket.id,
            notes=f'{SEED_DAYS_TAG} Issue to {ticket.ticket_id}',
            created_at=when,
        ))
        created += 1
    db.session.flush()
    return created


def main():
    parser = argparse.ArgumentParser(description='Seed procurement store-keeping data.')
    parser.get_default = getattr(parser, 'get_default', lambda k: None)
    parser.add_argument('--clear', action='store_true', help='Remove prior procurement rows first')
    args = parser.parse_args()
    from Injaaz import create_app
    from app.models import db
    app = create_app()
    with app.app_context():
        db.create_all()
        counts = seed_procurement(clear=args.clear)
        print('[PROC-SEED]', counts)


if __name__ == '__main__':
    main()
