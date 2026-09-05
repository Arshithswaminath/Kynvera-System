"""Stock math, access helpers, and catalog serialization for procurement."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import jsonify
from sqlalchemy import func

from app.models import Notification, Ticket, TicketMaterial, User, db
from module_procurement.models import (
    GM_APPROVAL_AED,
    TRADE_DEPARTMENTS,
    ProcCatalogItem,
    ProcGoodsReceipt,
    ProcGoodsReceiptLine,
    ProcMovement,
    ProcProperty,
    ProcPurchaseLine,
    ProcPurchaseRequest,
    ProcStock,
    ProcSupplier,
    _utcnow,
)


def new_public_id(prefix: str) -> str:
    return f'{prefix}-{uuid.uuid4().hex[:8].upper()}'


def _as_naive_utc(dt):
    """Normalize DB datetimes so sort/max never mix aware and naive values."""
    if not dt:
        return None
    if isinstance(dt, str):
        s = dt.strip().replace(' ', 'T').replace('Z', '+00:00')
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if getattr(dt, 'tzinfo', None) is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _iso_utc(dt):
    """UTC ISO-8601 with Z; milliseconds only so browsers can parse it."""
    dt = _as_naive_utc(dt)
    if not dt:
        return None
    ms = (getattr(dt, 'microsecond', 0) or 0) // 1000
    dt = dt.replace(microsecond=ms * 1000)
    try:
        s = dt.isoformat(timespec='milliseconds')
    except TypeError:
        s = dt.strftime('%Y-%m-%dT%H:%M:%S') + f'.{ms:03d}'
    if s.endswith('Z') or '+' in s[10:]:
        return s
    return s + 'Z'


def has_module_access(user) -> bool:
    if not user:
        return False
    return user.role == 'admin' or bool(getattr(user, 'access_procurement_module', False))


def deny_if_no_access(user, message='Access denied'):
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if not has_module_access(user):
        return jsonify({'error': message}), 403
    return None


def _norm_role(user) -> str:
    return (getattr(user, 'role', None) or '').strip().lower()


def _norm_designation(user) -> str:
    return (getattr(user, 'designation', None) or '').strip().lower()


def is_procurement_approver(user) -> bool:
    """Under-threshold PRs: admin or designation 'procurement' (not merely module access)."""
    if not user:
        return False
    if _norm_role(user) == 'admin':
        return True
    return _norm_designation(user) == 'procurement'


def is_gm_approver(user) -> bool:
    """Quotation / PR gate: general manager or system administrator."""
    if not user:
        return False
    if _norm_role(user) == 'admin':
        return True
    return _norm_designation(user) in ('general_manager', 'admin')


def notify_users(user_ids, title, message, notification_type='info', submission_id=None):
    seen = set()
    for uid in user_ids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        db.session.add(Notification(
            user_id=uid,
            title=title,
            message=message,
            notification_type=notification_type,
            submission_id=submission_id,
        ))


def procurement_user_ids():
    rows = User.query.filter(
        db.or_(User.role == 'admin', User.access_procurement_module == True),  # noqa: E712
        User.is_active == True,  # noqa: E712
    ).all()
    return [u.id for u in rows]


def gm_user_ids():
    rows = User.query.filter(
        db.or_(
            User.role == 'admin',
            User.designation == 'general_manager',
            User.designation == 'admin',
        ),
        User.is_active == True,  # noqa: E712
    ).all()
    return [u.id for u in rows]


def catalog_grouped(department='', query_str=''):
    q = ProcCatalogItem.query.filter_by(is_rate_card=True)
    department = (department or '').strip()
    query_str = (query_str or '').strip().lower()
    if department:
        q = q.filter_by(department=department)
    else:
        q = q.filter(ProcCatalogItem.department.in_(TRADE_DEPARTMENTS))
    result = {}
    for item in q.order_by(ProcCatalogItem.name.asc()).all():
        name = item.name or ''
        brand = item.brand or ''
        if query_str and query_str not in name.lower() and query_str not in brand.lower():
            continue
        result.setdefault(item.department, []).append(item.to_catalog_dict())
    departments = sorted(result.keys())
    return {
        'success': True,
        'departments': departments,
        'materials': result,
        'total': sum(len(v) for v in result.values()),
    }


SHARED_PROPERTY_NAME = 'Shared'


def ensure_shared_property():
    """One Shared store used as a company-wide pool on every ticket."""
    row = ProcProperty.query.filter_by(is_shared=True).first()
    if row:
        return row
    row = ProcProperty.query.filter(db.func.lower(ProcProperty.name) == 'shared').first()
    if row:
        row.is_shared = True
        return row
    row = ProcProperty(
        public_id=new_public_id('PROC-PROP'),
        name=SHARED_PROPERTY_NAME,
        description='Shared store — available on every service ticket',
        is_shared=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def link_ticket_property(row):
    """Match an existing ticketing location by name; do not create one."""
    if not row or row.ticket_property_id:
        return row
    from app.models import TicketProperty
    tp = TicketProperty.query.filter(
        db.func.lower(TicketProperty.name) == (row.name or '').strip().lower(),
        TicketProperty.is_active == True,  # noqa: E712
    ).first()
    if tp:
        row.ticket_property_id = tp.id
    return row


def find_property_for_ticket(ticket):
    """Resolve the ticket's site ProcProperty. Does not create a row."""
    if not ticket:
        return None
    pid = getattr(ticket, 'property_id', None)
    if pid:
        row = ProcProperty.query.filter_by(ticket_property_id=pid).first()
        if row:
            return row
    name = (getattr(ticket, 'property_name', None) or '').strip()
    if not name:
        return None
    return ProcProperty.query.filter(db.func.lower(ProcProperty.name) == name.lower()).first()


def get_or_create_property(name, address='', description='', public_id=None, link=True):
    name = (name or '').strip()
    if not name:
        return None
    row = ProcProperty.query.filter(db.func.lower(ProcProperty.name) == name.lower()).first()
    if row:
        if address and not row.address:
            row.address = address
        if description and not row.description:
            row.description = description
        if name.lower() == 'shared':
            row.is_shared = True
        if link:
            link_ticket_property(row)
        return row
    row = ProcProperty(
        public_id=public_id or new_public_id('PROC-PROP'),
        name=name,
        address=(address or '').strip(),
        description=(description or '').strip(),
        is_shared=(name.lower() == 'shared'),
    )
    db.session.add(row)
    db.session.flush()
    if link:
        link_ticket_property(row)
    return row


def get_or_create_catalog_item(*, department, name, brand='', uom='PCS', unit_price=0.0,
                               is_rate_card=False, min_qty=0.0, public_id=None, supplier=None):
    name = (name or '').strip()
    department = (department or 'General').strip() or 'General'
    if not name:
        return None
    q = ProcCatalogItem.query.filter(
        db.func.lower(ProcCatalogItem.name) == name.lower(),
        ProcCatalogItem.department == department,
    )
    row = q.first()
    if row:
        if unit_price and not row.unit_price:
            row.unit_price = float(unit_price)
        if brand and not row.brand:
            row.brand = brand
        if is_rate_card:
            row.is_rate_card = True
        return row
    row = ProcCatalogItem(
        public_id=public_id or new_public_id('CAT-MAT' if is_rate_card else 'CAT-INV'),
        department=department,
        name=name,
        brand=(brand or '').strip(),
        uom=(uom or 'PCS').strip() or 'PCS',
        unit_price=float(unit_price or 0),
        min_qty=float(min_qty or 0),
        is_rate_card=bool(is_rate_card),
        preferred_supplier=supplier,
    )
    db.session.add(row)
    db.session.flush()
    return row


def get_or_create_stock(property_row, catalog_item, public_id=None):
    row = ProcStock.query.filter_by(
        property_id=property_row.id, catalog_item_id=catalog_item.id,
    ).first()
    if row:
        return row
    row = ProcStock(
        public_id=public_id or new_public_id('PROC-MAT'),
        property_id=property_row.id,
        catalog_item_id=catalog_item.id,
        qty_on_hand=0,
    )
    db.session.add(row)
    db.session.flush()
    return row


def record_movement(*, movement_type, property_row=None, catalog_item=None, qty=0,
                    user=None, ticket_id=None, request_row=None, notes=''):
    db.session.add(ProcMovement(
        movement_type=movement_type,
        property_id=property_row.id if property_row else None,
        catalog_item_id=catalog_item.id if catalog_item else None,
        qty=float(qty or 0),
        user_id=user.id if user else None,
        ticket_id=ticket_id,
        request_id=request_row.id if request_row else None,
        notes=notes or '',
    ))


def adjust_stock(stock_row, delta, *, user=None, movement_type='adjust', ticket_id=None,
                 request_row=None, notes=''):
    new_qty = float(stock_row.qty_on_hand or 0) + float(delta)
    if new_qty < 0:
        raise ValueError('Insufficient stock')
    stock_row.qty_on_hand = new_qty
    record_movement(
        movement_type=movement_type,
        property_row=stock_row.property,
        catalog_item=stock_row.catalog_item,
        qty=delta,
        user=user,
        ticket_id=ticket_id,
        request_row=request_row,
        notes=notes,
    )
    return stock_row


def add_inventory_material(*, user, material_name, property_name='Unassigned', category='General',
                           description='', unit='pcs', quantity=0, unit_price=0, supplier_name='',
                           notes='', public_id=None, imported_from_excel=False, distribute='site'):
    property_row = get_or_create_property(property_name or 'Unassigned')
    supplier = None
    if (supplier_name or '').strip():
        supplier = ProcSupplier.query.filter(
            db.func.lower(ProcSupplier.name) == supplier_name.strip().lower()
        ).first()
    is_rate = (category or '') in TRADE_DEPARTMENTS
    item = get_or_create_catalog_item(
        department=category or 'General',
        name=material_name,
        uom=unit or 'PCS',
        unit_price=unit_price,
        is_rate_card=is_rate,
        supplier=supplier,
    )
    stock = get_or_create_stock(property_row, item, public_id=public_id)
    stock.notes = (description or notes or stock.notes or '')
    stock.added_by = (user.full_name or user.username) if user else stock.added_by
    if imported_from_excel:
        stock.imported_from_excel = True
    qty = float(quantity or 0)
    mode = (distribute or 'site').strip().lower()
    if mode in ('equal', 'split', 'even') and qty:
        dests = properties_sharing_sku(item, extra=property_row)
        if len(dests) <= 1:
            dests = [
                p for p in ProcProperty.query.all()
                if p and not p.is_shared
            ]
            if property_row and not property_row.is_shared:
                dests = [property_row] + [p for p in dests if p.id != property_row.id]
        dests = [p for p in dests if p and not p.is_shared]
        if not dests and property_row:
            dests = [property_row]
        if dests:
            parts = split_qty(qty, len(dests))
            last = stock
            for prop, part in zip(dests, parts):
                if part <= 0:
                    continue
                row = get_or_create_stock(prop, item)
                last = adjust_stock(row, part, user=user, movement_type='adjust', notes='Inventory add (shared equally)')
            return last
    if qty:
        adjust_stock(stock, qty, user=user, movement_type='adjust', notes='Inventory add')
    else:
        record_movement(
            movement_type='adjust',
            property_row=property_row,
            catalog_item=item,
            qty=0,
            user=user,
            notes='Inventory add',
        )
    return stock


def list_stock_elsewhere(exclude_property_name=''):
    """Site stock that can be shared into the company pool (excludes Shared)."""
    exclude = (exclude_property_name or '').strip()
    dest = None
    if exclude:
        dest = ProcProperty.query.filter(
            db.func.lower(ProcProperty.name) == exclude.lower()
        ).first()
    q = ProcStock.query.join(ProcProperty).filter(ProcStock.qty_on_hand > 0)
    rows = q.all()
    holder_ids = {}
    for row in rows:
        prop = row.property
        if not prop or prop.is_shared or not row.catalog_item_id:
            continue
        holder_ids.setdefault(row.catalog_item_id, set()).add(prop.id)
    by_prop = {}
    for row in rows:
        prop = row.property
        if not prop or prop.is_shared:
            continue
        if dest and row.property_id == dest.id:
            continue
        bucket = by_prop.get(prop.id)
        if not bucket:
            bucket = {
                'property': prop.name,
                'display_name': display_name_for_proc_property(prop) or prop.name,
                'is_shared': bool(prop.is_shared),
                'property_id': prop.public_id,
                'materials': [],
            }
            by_prop[prop.id] = bucket
        item = row.to_material_dict()
        item['is_shared'] = bool(prop.is_shared)
        item['source_display'] = bucket['display_name']
        sites = set(holder_ids.get(row.catalog_item_id) or ())
        if dest:
            sites.add(dest.id)
        item['equal_site_count'] = max(len(sites), 1)
        bucket['materials'].append(item)
    groups = list(by_prop.values())
    for group in groups:
        group['materials'].sort(key=lambda m: (m.get('material_name') or '').lower())
    groups.sort(key=lambda g: (0 if g['is_shared'] else 1, (g.get('display_name') or '').lower()))
    return groups


def _parse_positive_qty(qty):
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        raise ValueError('Quantity is required')
    if qty <= 0:
        raise ValueError('Quantity must be greater than zero')
    return qty


def split_qty(qty, n):
    """Split qty across n sites in 0.01 units. Remainder goes to the first site."""
    n = int(n)
    if n <= 0:
        raise ValueError('No sites to share with')
    cents = int(round(float(qty) * 100))
    if cents <= 0:
        raise ValueError('Quantity must be greater than zero')
    base, rem = divmod(cents, n)
    return [(base + (1 if i < rem else 0)) / 100.0 for i in range(n)]


def properties_sharing_sku(catalog_item, extra=None):
    """Non-shared sites that already hold this SKU, plus the current project."""
    seen = {}
    if catalog_item:
        rows = ProcStock.query.filter(
            ProcStock.catalog_item_id == catalog_item.id,
            ProcStock.qty_on_hand > 0,
        ).all()
        for row in rows:
            prop = row.property
            if prop and not prop.is_shared:
                seen[prop.id] = prop
    if extra and not extra.is_shared:
        seen[extra.id] = extra
    return list(seen.values())


def transfer_stock(*, user, source_stock, dest_property, qty):
    """Move quantity from one site's stock row onto another (Shared included)."""
    qty = _parse_positive_qty(qty)
    if not source_stock:
        raise ValueError('Material not found')
    if not dest_property:
        raise ValueError('Destination site is required')
    if source_stock.property_id == dest_property.id:
        raise ValueError('Choose a different site')
    src_label = display_name_for_proc_property(source_stock.property) or (
        source_stock.property.name if source_stock.property else 'source'
    )
    dest_label = display_name_for_proc_property(dest_property) or dest_property.name
    dest_stock = get_or_create_stock(dest_property, source_stock.catalog_item)
    adjust_stock(
        source_stock, -qty, user=user, movement_type='transfer',
        notes=f'Reallocated to {dest_label}',
    )
    adjust_stock(
        dest_stock, qty, user=user, movement_type='transfer',
        notes=f'From {src_label}',
    )
    return dest_stock


def set_stock_on_hand(stock_row, qty, *, user=None, notes=''):
    """Set on-hand to qty (increase or decrease)."""
    qty = float(qty)
    current = float(stock_row.qty_on_hand or 0)
    delta = round(qty - current, 2)
    if delta == 0:
        return stock_row
    return adjust_stock(
        stock_row, delta, user=user, movement_type='adjust', notes=notes,
    )


def _share_equal_dests(source_stock, dest_property):
    dests = properties_sharing_sku(source_stock.catalog_item, extra=dest_property)
    if dest_property and not dest_property.is_shared:
        dests = [dest_property] + [p for p in dests if p.id != dest_property.id]
    if source_stock.property and not source_stock.property.is_shared:
        dests = [source_stock.property] + [p for p in dests if p.id != source_stock.property.id]
    return [p for p in dests if p and not p.is_shared]


def share_stock(*, user, source_stock, qty, mode='shared', dest_property=None):
    """Share or reallocate stock onto the current site.

    copy: dest also gets qty; source keeps its count.
    add: reallocate — deduct qty from source, add it here.
    Above on-hand: this project only sets dest to qty; equal sets every site
    that already holds the SKU to qty.
    """
    qty = _parse_positive_qty(qty)
    if not source_stock:
        raise ValueError('Material not found')
    mode = (mode or 'shared').strip().lower()
    if mode in ('this', 'this_project', 'project', 'site'):
        mode = 'site'
    elif mode in ('equal', 'split', 'even'):
        mode = 'equal'
    elif mode in ('add', 'transfer', 'move', 'reallocate'):
        mode = 'add'
    elif mode in ('copy', 'keep', 'duplicate'):
        mode = 'copy'
    if source_stock.property and source_stock.property.is_shared and mode not in (
        'site', 'add', 'copy',
    ):
        raise ValueError('This item is already in Shared')
    if mode == 'copy':
        if not dest_property:
            raise ValueError('Destination site is required')
        if source_stock.property_id == dest_property.id:
            raise ValueError('Choose a different site')
        dest_stock = get_or_create_stock(dest_property, source_stock.catalog_item)
        src_label = display_name_for_proc_property(source_stock.property) or (
            source_stock.property.name if source_stock.property else 'source'
        )
        return adjust_stock(
            dest_stock, qty, user=user, movement_type='adjust',
            notes=f'Shared from {src_label} (source unchanged)',
        )
    if mode == 'add':
        if not dest_property:
            raise ValueError('Destination site is required')
        return transfer_stock(
            user=user, source_stock=source_stock, dest_property=dest_property, qty=qty,
        )
    if mode == 'site':
        if not dest_property:
            raise ValueError('Destination site is required')
        dest_stock = get_or_create_stock(dest_property, source_stock.catalog_item)
        return set_stock_on_hand(
            dest_stock, qty, user=user,
            notes=f'Count set for this project (from {display_name_for_proc_property(source_stock.property) or "source"})',
        )
    if mode == 'equal':
        dests = _share_equal_dests(source_stock, dest_property)
        if not dests:
            raise ValueError('No sites to share with')
        last = source_stock
        for prop in dests:
            row = get_or_create_stock(prop, source_stock.catalog_item)
            last = set_stock_on_hand(
                row, qty, user=user,
                notes=f'Shared count set to {qty}',
            )
        return last
    shared = ensure_shared_property()
    return transfer_stock(
        user=user, source_stock=source_stock, dest_property=shared, qty=qty,
    )


def _stock_view_dict(row, *, pool='site'):
    item = row.to_material_dict()
    prop = row.property
    item['pool'] = pool
    item['is_shared_pool'] = pool == 'shared' or bool(prop and prop.is_shared)
    item['property_id'] = prop.public_id if prop else None
    item['source_display'] = (
        'Shared' if pool == 'shared' or (prop and prop.is_shared)
        else (display_name_for_proc_property(prop) or (prop.name if prop else ''))
    )
    return item


def materials_for_property_view(property_name):
    """Site stock plus Shared pool rows, so every property page stays in sync."""
    name = (property_name or '').strip()
    row = ProcProperty.query.filter(ProcProperty.name == name).first()
    if not row and name:
        row = ProcProperty.query.filter(db.func.lower(ProcProperty.name) == name.lower()).first()
    out = []
    if row:
        pool = 'shared' if row.is_shared else 'site'
        for stock in ProcStock.query.filter_by(property_id=row.id).all():
            out.append(_stock_view_dict(stock, pool=pool))
        if row.is_shared:
            return out, row
    shared = ProcProperty.query.filter_by(is_shared=True).first()
    if shared:
        for stock in ProcStock.query.filter_by(property_id=shared.id).all():
            if float(stock.qty_on_hand or 0) <= 0:
                continue
            out.append(_stock_view_dict(stock, pool='shared'))
    return out, row


def ticket_site_display_name(tp):
    """Label people see in procurement: the project when that project is one site."""
    if not tp:
        return ''
    project = getattr(tp, 'project', None)
    if project and (project.name or '').strip():
        sibling_count = project.properties.filter_by(is_active=True).count()
        if sibling_count <= 1:
            return project.name.strip()
    label = (tp.display_label() or tp.name or '').strip()
    return label


def display_name_for_proc_property(row):
    if not row:
        return ''
    from app.models import TicketProperty
    tp = None
    if row.ticket_property_id:
        tp = db.session.get(TicketProperty, row.ticket_property_id)
    if not tp:
        hits = TicketProperty.query.filter(
            db.func.lower(TicketProperty.name) == (row.name or '').strip().lower(),
            TicketProperty.is_active == True,  # noqa: E712
        ).all()
        if hits:
            tp = hits[0]
    shown = ticket_site_display_name(tp)
    if shown:
        return shown
    return (row.name or '').strip()


PROP_COLOR_THEMES = (
    {'from': '#6366f1', 'to': '#4f46e5', 'solid': '#4f46e5', 'icon': '🏢'},
    {'from': '#ec4899', 'to': '#be185d', 'solid': '#be185d', 'icon': '🏠'},
    {'from': '#f59e0b', 'to': '#d97706', 'solid': '#d97706', 'icon': '🏗️'},
    {'from': '#3b82f6', 'to': '#1d4ed8', 'solid': '#1d4ed8', 'icon': '🏭'},
    {'from': '#8b5cf6', 'to': '#6d28d9', 'solid': '#6d28d9', 'icon': '🏛️'},
    {'from': '#14b8a6', 'to': '#0d9488', 'solid': '#0d9488', 'icon': '🏨'},
    {'from': '#f43f5e', 'to': '#e11d48', 'solid': '#e11d48', 'icon': '🏪'},
    {'from': '#10b981', 'to': '#047857', 'solid': '#047857', 'icon': '🏬'},
)


def _theme_index(name):
    h = 0
    for ch in (name or '').strip().lower():
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % len(PROP_COLOR_THEMES)


def property_card_theme(name, *, is_shared=False):
    key = (name or '').strip().lower()
    if is_shared or key == 'shared':
        return {
            'from': '#0ea5e9', 'to': '#0369a1', 'solid': '#0369a1',
            'gradient': 'linear-gradient(135deg,#0ea5e9,#0369a1)',
            'icon': '📦',
        }
    if key == 'unassigned':
        return {
            'from': '#94a3b8', 'to': '#64748b', 'solid': '#64748b',
            'gradient': 'linear-gradient(135deg,#94a3b8,#64748b)',
            'icon': '📦',
        }
    t = PROP_COLOR_THEMES[_theme_index(name)]
    return {
        'from': t['from'], 'to': t['to'], 'solid': t['solid'],
        'gradient': f"linear-gradient(135deg,{t['from']},{t['to']})",
        'icon': t['icon'],
    }


PROPERTY_ICONS = (
    {'icon': '🏢', 'label': 'Office'},
    {'icon': '🏠', 'label': 'Villa'},
    {'icon': '🏘️', 'label': 'Compound'},
    {'icon': '🏛️', 'label': 'Headquarters'},
    {'icon': '🏭', 'label': 'Plant'},
    {'icon': '🏗️', 'label': 'Construction'},
    {'icon': '🏨', 'label': 'Hotel'},
    {'icon': '🏪', 'label': 'Retail'},
    {'icon': '🏬', 'label': 'Mall'},
    {'icon': '📦', 'label': 'Warehouse'},
    {'icon': '🏫', 'label': 'School'},
    {'icon': '🏥', 'label': 'Clinic'},
    {'icon': '🕌', 'label': 'Community'},
    {'icon': '🏟️', 'label': 'Sports'},
    {'icon': '🌳', 'label': 'Landscape'},
    {'icon': '🅿️', 'label': 'Parking'},
    {'icon': '🔧', 'label': 'Workshop'},
    {'icon': '⚡', 'label': 'Utilities'},
    {'icon': '🌊', 'label': 'Pool'},
    {'icon': '🚧', 'label': 'Site'},
)

_ALLOWED_PROPERTY_ICONS = {item['icon'] for item in PROPERTY_ICONS}


def property_icon_choices():
    return [dict(item) for item in PROPERTY_ICONS]


def set_property_icon(*, icon, public_id=None, name='', ticket_property_id=None):
    icon = (icon or '').strip()
    if icon not in _ALLOWED_PROPERTY_ICONS:
        raise ValueError('Choose an icon from the list')
    row = None
    if public_id:
        row = ProcProperty.query.filter_by(public_id=(public_id or '').strip()).first()
    if not row:
        row = get_or_create_property(name, link=False)
        if row and ticket_property_id not in (None, ''):
            apply_ticket_property_link(row, ticket_property_id)
    if not row:
        raise ValueError('Property not found')
    row.icon = icon
    return row


def properties_with_counts():
    from app.models import TicketProject, TicketProperty

    stock_totals = {}
    for row in ProcStock.query.all():
        if not row.property_id:
            continue
        bucket = stock_totals.setdefault(row.property_id, {
            'materials_count': 0,
            'total_quantity': 0.0,
            'total_value': 0.0,
        })
        qty = float(row.qty_on_hand or 0)
        price = float(row.catalog_item.unit_price or 0) if row.catalog_item else 0
        bucket['materials_count'] += 1
        bucket['total_quantity'] += qty
        bucket['total_value'] += qty * price

    ticket_ids = [
        p.ticket_property_id for p in ProcProperty.query.filter(
            ProcProperty.ticket_property_id.isnot(None)
        ).all()
    ]
    tickets = {}
    if ticket_ids:
        for tp in TicketProperty.query.filter(TicketProperty.id.in_(ticket_ids)).all():
            tickets[tp.id] = tp

    common = (
        TicketProperty.query.filter_by(is_active=True)
        .order_by(TicketProperty.name.asc())
        .all()
    )
    by_name = {}
    for tp in common:
        key = (tp.name or '').strip().lower()
        by_name.setdefault(key, []).append(tp)

    out = []
    used_ticket_ids = set()
    used_names = set()
    for prop in ProcProperty.query.order_by(ProcProperty.created_at.desc()).all():
        counts = stock_totals.get(prop.id, {
            'materials_count': 0,
            'total_quantity': 0.0,
            'total_value': 0.0,
        })
        tp = tickets.get(prop.ticket_property_id) if prop.ticket_property_id else None
        if not tp:
            hits = by_name.get((prop.name or '').strip().lower()) or []
            if hits:
                tp = hits[0]
        if prop.ticket_property_id:
            used_ticket_ids.add(prop.ticket_property_id)
        used_names.add((prop.name or '').strip().lower())
        shown = ticket_site_display_name(tp) if tp else (prop.name or '')
        theme = property_card_theme(prop.name, is_shared=bool(prop.is_shared))
        if prop.icon:
            theme = {**theme, 'icon': prop.icon}
        out.append({
            'name': prop.name,
            'display_name': shown or prop.name,
            'id': prop.public_id,
            'is_shared': bool(prop.is_shared),
            'linked': bool(prop.ticket_property_id),
            'from_tickets': bool(prop.ticket_property_id),
            'needs_import': False,
            'ticket_property_id': prop.ticket_property_id,
            'ticket_property_name': (tp.name if tp else '') or '',
            'ticket_project_name': (tp.project.name if tp and tp.project else '') or '',
            'ticket_project_id': tp.project_id if tp else None,
            'materials_count': counts['materials_count'],
            'total_quantity': counts['total_quantity'],
            'total_value': counts['total_value'],
            'theme': theme,
            'needs_stock': False,
        })

    for tp in common:
        if tp.id in used_ticket_ids:
            continue
        key = (tp.name or '').strip().lower()
        if key in used_names:
            continue
        used_names.add(key)
        shown = ticket_site_display_name(tp)
        out.append({
            'name': tp.name,
            'display_name': shown or tp.name,
            'id': None,
            'is_shared': False,
            'linked': True,
            'from_tickets': True,
            'needs_import': True,
            'needs_stock': False,
            'ticket_property_id': tp.id,
            'ticket_property_name': tp.name,
            'ticket_project_name': (tp.project.name if tp.project else '') or '',
            'ticket_project_id': tp.project_id,
            'materials_count': 0,
            'total_quantity': 0.0,
            'total_value': 0.0,
            'theme': property_card_theme(tp.name),
        })

    tp_by_id = {tp.id: tp for tp in common}
    shown_project_ids = set()
    shown_keys = set()
    for item in out:
        shown_keys.add((item.get('name') or '').strip().lower())
        shown_keys.add((item.get('display_name') or '').strip().lower())
        tp = tp_by_id.get(item.get('ticket_property_id'))
        if tp and tp.project_id:
            shown_project_ids.add(tp.project_id)
    for proj in TicketProject.query.filter_by(is_active=True).order_by(TicketProject.name.asc()).all():
        key = (proj.name or '').strip().lower()
        if not key or key in shown_keys or proj.id in shown_project_ids:
            continue
        shown_keys.add(key)
        out.append({
            'name': proj.name,
            'display_name': proj.name,
            'id': None,
            'is_shared': False,
            'linked': True,
            'from_tickets': True,
            'needs_import': True,
            'needs_stock': True,
            'ticket_property_id': None,
            'ticket_property_name': '',
            'ticket_project_name': proj.name,
            'ticket_project_id': proj.id,
            'materials_count': 0,
            'total_quantity': 0.0,
            'total_value': 0.0,
            'theme': property_card_theme(proj.name),
        })
    return out


def ticket_properties_for_picker():
    from app.models import TicketProperty
    linked = {
        p.ticket_property_id: p.public_id
        for p in ProcProperty.query.filter(ProcProperty.ticket_property_id.isnot(None)).all()
    }
    out = []
    rows = (
        TicketProperty.query.filter_by(is_active=True)
        .order_by(TicketProperty.name.asc())
        .all()
    )
    for tp in rows:
        shown = ticket_site_display_name(tp)
        out.append({
            'id': tp.id,
            'name': tp.name,
            'display_name': shown or tp.name,
            'code': tp.code or '',
            'project_name': (tp.project.name if tp.project else '') or '',
            'linked': tp.id in linked,
            'proc_id': linked.get(tp.id),
        })
    return out


def apply_ticket_property_link(row, ticket_property_id):
    from app.models import TicketProperty
    if not row:
        raise ValueError('Property not found')
    if row.is_shared:
        raise ValueError('Shared store cannot be linked to a ticket site')
    try:
        tp_id = int(ticket_property_id)
    except (TypeError, ValueError):
        raise ValueError('ticket_property_id is required')
    tp = db.session.get(TicketProperty, tp_id)
    if not tp or not tp.is_active:
        raise ValueError('Ticketing property not found')
    other = ProcProperty.query.filter(
        ProcProperty.ticket_property_id == tp.id,
        ProcProperty.id != row.id,
    ).first()
    if other:
        raise ValueError('That ticketing site is already linked to another procurement property')
    row.ticket_property_id = tp.id
    return row


def low_stock_rows(limit=20):
    limit = max(1, int(limit or 20))
    rows = (
        ProcStock.query.join(ProcCatalogItem)
        .filter(
            ProcCatalogItem.min_qty > 0,
            ProcStock.qty_on_hand <= ProcCatalogItem.min_qty,
        )
        .order_by((ProcStock.qty_on_hand - ProcCatalogItem.min_qty).asc())
        .limit(limit)
        .all()
    )
    out = []
    for row in rows:
        item = row.catalog_item
        if not item:
            continue
        out.append({
            'catalog_id': item.public_id,
            'name': item.name,
            'property': row.property.name if row.property else '',
            'qty': float(row.qty_on_hand or 0),
            'min_qty': float(item.min_qty or 0),
            'department': item.department,
        })
    return out


def create_purchase_request(*, user, property_public_id=None, supplier_public_id=None,
                            notes='', lines=None, status='submitted'):
    property_row = None
    if property_public_id:
        property_row = ProcProperty.query.filter_by(public_id=property_public_id).first()
    supplier = None
    if supplier_public_id:
        supplier = ProcSupplier.query.filter_by(public_id=supplier_public_id).first()
    pr = ProcPurchaseRequest(
        public_id=new_public_id('PR'),
        status=status,
        property=property_row,
        supplier=supplier,
        requested_by=user,
        notes=notes or '',
    )
    db.session.add(pr)
    db.session.flush()
    total = 0.0
    for line in lines or []:
        cat_id = (line.get('catalog_id') or line.get('id') or '').strip()
        item = ProcCatalogItem.query.filter_by(public_id=cat_id).first()
        if not item:
            continue
        qty = float(line.get('qty') or line.get('quantity') or 1)
        price = float(line.get('unit_price') if line.get('unit_price') not in (None, '') else (item.unit_price or 0))
        db.session.add(ProcPurchaseLine(
            request=pr, catalog_item=item, qty=qty, unit_price=price,
        ))
        total += qty * price
    db.session.flush()
    if not pr.lines:
        raise ValueError('At least one valid catalog line is required')
    pr.total_aed = total
    pr.needs_gm = total >= GM_APPROVAL_AED
    if status == 'submitted':
        pr.status = 'procurement_review'
        notify_users(
            procurement_user_ids(),
            'Purchase request submitted',
            f'{pr.public_id} for AED {total:,.0f} needs procurement review.',
            'proc_pr',
            submission_id=pr.public_id,
        )
    return pr


def receive_purchase_request(pr, *, user, line_qtys=None, notes=''):
    """Increase stock from an ordered/approved PR. line_qtys maps catalog public_id → qty."""
    if pr.status not in ('ordered', 'approved'):
        raise ValueError('Request must be approved or ordered before receiving')
    if not pr.property:
        raise ValueError('Request has no property to receive into')
    receipt = ProcGoodsReceipt(
        public_id=new_public_id('GRN'),
        request=pr,
        received_by=user,
        notes=notes or '',
    )
    db.session.add(receipt)
    db.session.flush()
    for line in pr.lines:
        qty = float(line.qty or 0)
        if line_qtys and line.catalog_item:
            raw = line_qtys.get(line.catalog_item.public_id)
            if raw is not None:
                qty = float(raw)
        if qty <= 0:
            continue
        db.session.add(ProcGoodsReceiptLine(
            receipt=receipt, catalog_item=line.catalog_item, qty=qty,
        ))
        stock = get_or_create_stock(pr.property, line.catalog_item)
        adjust_stock(
            stock, qty, user=user, movement_type='receipt',
            request_row=pr, notes=f'GRN {receipt.public_id}',
        )
    pr.status = 'received'
    pr.received_at = _utcnow()
    lows = low_stock_rows(limit=8)
    if lows:
        names = ', '.join(x['name'] for x in lows[:4])
        notify_users(
            procurement_user_ids(),
            'Low stock after goods received',
            f'Still below minimum: {names}',
            'proc_refill',
        )
    return receipt


def issue_to_ticket(*, user, property_public_id, catalog_public_id, qty, ticket, chargeable=False):
    property_row = ProcProperty.query.filter_by(public_id=property_public_id).first()
    item = ProcCatalogItem.query.filter_by(public_id=catalog_public_id).first()
    if not property_row or not item:
        raise ValueError('Property or catalog item not found')
    stock = ProcStock.query.filter_by(property_id=property_row.id, catalog_item_id=item.id).first()
    if not stock:
        raise ValueError('No stock at this property')
    return consume_on_ticket(
        user=user,
        ticket=ticket,
        catalog_public_id=catalog_public_id,
        qty=qty,
        chargeable=chargeable,
        stock_row=stock,
    )


def return_from_ticket(*, user, ticket_material, property_public_id=None):
    item = None
    if ticket_material.procurement_ref:
        item = ProcCatalogItem.query.filter_by(public_id=ticket_material.procurement_ref).first()
    if item is None and getattr(ticket_material, 'catalog_item_id', None):
        item = db.session.get(ProcCatalogItem, ticket_material.catalog_item_id)
    if not item:
        raise ValueError('Ticket material is not linked to the catalog')
    property_row = None
    if property_public_id:
        property_row = ProcProperty.query.filter_by(public_id=property_public_id).first()
    if property_row is None:
        move = (
            ProcMovement.query.filter_by(
                ticket_id=ticket_material.ticket_id,
                catalog_item_id=item.id,
                movement_type='issue',
            )
            .order_by(ProcMovement.id.desc())
            .first()
        )
        if move and move.property_id:
            property_row = db.session.get(ProcProperty, move.property_id)
    if property_row is None:
        ticket = db.session.get(Ticket, ticket_material.ticket_id)
        property_row = find_property_for_ticket(ticket) if ticket else None
    if property_row is None:
        property_row = ProcProperty.query.order_by(ProcProperty.id.asc()).first()
    if not property_row:
        raise ValueError('No property to return into')
    stock = get_or_create_stock(property_row, item)
    qty = float(ticket_material.quantity or 0)
    adjust_stock(
        stock, qty, user=user, movement_type='return',
        ticket_id=ticket_material.ticket_id, notes='Return from ticket',
    )
    db.session.delete(ticket_material)


def migrate_submissions_if_needed():
    """One-time backfill from Submission JSON blobs into dedicated tables."""
    from app.models import Submission
    if ProcCatalogItem.query.count() > 0 or ProcProperty.query.count() > 0 or ProcStock.query.count() > 0:
        return {'skipped': True}
    created = {'catalog': 0, 'properties': 0, 'stock': 0}
    for sub in Submission.query.filter_by(module_type='catalog_material').all():
        fd = sub.form_data or {}
        name = (fd.get('material_name') or fd.get('name') or sub.site_name or '').strip()
        if not name:
            continue
        dept = (fd.get('department') or 'General').strip()
        get_or_create_catalog_item(
            department=dept,
            name=name,
            brand=fd.get('brand') or '',
            uom=fd.get('uom') or 'PCS',
            unit_price=fd.get('unit_price') or 0,
            is_rate_card=dept in TRADE_DEPARTMENTS,
            public_id=sub.submission_id if (sub.submission_id or '').startswith('CAT-') else None,
        )
        created['catalog'] += 1
    for sub in Submission.query.filter_by(module_type='procurement_property').all():
        fd = sub.form_data or {}
        name = (fd.get('property_name') or sub.site_name or '').strip()
        if not name:
            continue
        get_or_create_property(
            name,
            address=fd.get('address') or '',
            description=fd.get('description') or '',
            public_id=sub.submission_id if (sub.submission_id or '').startswith('PROC-PROP') else None,
        )
        created['properties'] += 1
    for sub in Submission.query.filter_by(module_type='procurement_material').all():
        fd = sub.form_data or {}
        name = (fd.get('material_name') or sub.site_name or '').strip()
        if not name:
            continue
        add_inventory_material(
            user=None,
            material_name=name,
            property_name=fd.get('property') or 'Unassigned',
            category=fd.get('category') or 'General',
            description=fd.get('description') or '',
            unit=fd.get('unit') or 'pcs',
            quantity=fd.get('quantity') or 0,
            unit_price=fd.get('unit_price') or 0,
            supplier_name=fd.get('supplier') or '',
            notes=fd.get('notes') or '',
            public_id=sub.submission_id if (sub.submission_id or '').startswith('PROC-MAT') else None,
        )
        created['stock'] += 1
    db.session.commit()
    return created


# ---------------------------------------------------------------------------
# Ticket consumption, usage log, dashboard, refill
# ---------------------------------------------------------------------------

TRADE_CHART_ORDER = TRADE_DEPARTMENTS


def is_refill_needed(qty, min_qty) -> bool:
    qty = float(qty or 0)
    min_qty = float(min_qty or 0)
    if qty <= 0:
        return True
    return min_qty > 0 and qty <= min_qty


def stock_status_label(qty, min_qty, movement_type=None):
    if movement_type == 'return':
        return 'returned'
    qty = float(qty or 0)
    min_qty = float(min_qty or 0)
    if qty <= 0:
        return 'refill'
    if min_qty > 0 and qty <= min_qty:
        return 'low'
    return 'ok'


def suggested_refill_qty(qty, min_qty) -> float:
    qty = float(qty or 0)
    min_qty = float(min_qty or 0)
    if min_qty > 0:
        return max(min_qty - qty, min_qty)
    return 1.0 if qty <= 0 else 1.0


def _month_start(dt):
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_months(dt, months):
    index = dt.month - 1 + int(months)
    year = dt.year + index // 12
    month = index % 12 + 1
    return dt.replace(year=year, month=month)


def _month_end(dt):
    return _shift_months(_month_start(dt), 1) - timedelta(microseconds=1)


def _parse_year_month(key):
    parts = (key or '').split('-')
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        return None
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return None
    year, month = int(parts[0]), int(parts[1])
    if month < 1 or month > 12:
        return None
    return year, month


def period_bounds(range_key='month'):
    now = _utcnow()
    key = (range_key or 'month').strip().lower()
    custom = _parse_year_month(key)
    if custom:
        year, month = custom
        start = datetime(year, month, 1)
        if start > now:
            start = _month_start(now)
            key = start.strftime('%Y-%m')
        else:
            key = f'{year:04d}-{month:02d}'
        end = _month_end(start)
        prev_start = _shift_months(start, -1)
        prev_end = start
        label = start.strftime('%b %Y')
        return key, label, start, end, prev_start, prev_end
    if key in ('last_month', 'last', 'prev', 'previous_month', '30d', '30', 'last_30', 'last30'):
        start = _shift_months(_month_start(now), -1)
        end = _month_end(start)
        prev_start = _shift_months(start, -1)
        prev_end = start
        label = 'Last month'
        key = 'last_month'
        return key, label, start, end, prev_start, prev_end
    if key in ('year', 'yearly'):
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_start = start.replace(year=start.year - 1)
        prev_end = start
        label = 'This year'
        key = 'year'
        return key, label, start, now, prev_start, prev_end
    if key in ('3m', '3mo', '3months', 'last_3m', 'last3m'):
        start = _shift_months(_month_start(now), -2)
        end = _month_end(_month_start(now))
        prev_start = _shift_months(start, -3)
        prev_end = start
        label = 'Last 3 months'
        key = '3m'
        return key, label, start, end, prev_start, prev_end
    start = _month_start(now)
    end = _month_end(start)
    prev_start = _shift_months(start, -1)
    prev_end = start
    label = 'This month'
    key = 'month'
    return key, label, start, end, prev_start, prev_end


def _pct_delta(current, previous):
    current = float(current or 0)
    previous = float(previous or 0)
    if previous == 0:
        return 1.0 if current > 0 else 0.0
    return (current - previous) / previous


def _stock_lookup():
    """Map (property_id, catalog_item_id) → qty_on_hand."""
    out = {}
    for row in ProcStock.query.all():
        out[(row.property_id, row.catalog_item_id)] = float(row.qty_on_hand or 0)
    return out


def movement_to_log_dict(move, *, tickets_by_id=None, stock_by_key=None):
    item = move.catalog_item
    prop = move.property
    ticket = None
    if move.ticket_id:
        if tickets_by_id is not None:
            ticket = tickets_by_id.get(move.ticket_id)
        else:
            ticket = db.session.get(Ticket, move.ticket_id)
    qty_on_hand = None
    min_qty = float(item.min_qty or 0) if item else 0.0
    if stock_by_key is not None and move.property_id and move.catalog_item_id:
        qty_on_hand = stock_by_key.get((move.property_id, move.catalog_item_id))
    elif move.property_id and move.catalog_item_id:
        stock = ProcStock.query.filter_by(
            property_id=move.property_id, catalog_item_id=move.catalog_item_id,
        ).first()
        qty_on_hand = float(stock.qty_on_hand or 0) if stock else 0.0
    if qty_on_hand is None:
        qty_on_hand = 0.0
    who = ''
    if move.user:
        who = move.user.full_name or move.user.username or ''
    ticket_public = ticket.ticket_id if ticket else ''
    status = stock_status_label(qty_on_hand, min_qty, move.movement_type)
    used_qty = abs(float(move.qty or 0))
    return {
        'id': move.id,
        'log_id': f'LOG-{move.id:05d}',
        'movement_type': move.movement_type,
        'material_name': item.name if item else (move.notes or 'Stock movement'),
        'catalog_id': item.public_id if item else None,
        'department': item.department if item else '',
        'uom': (item.uom if item else 'PCS') or 'PCS',
        'qty': used_qty,
        'qty_on_hand': qty_on_hand,
        'min_qty': min_qty,
        'property': prop.name if prop else '',
        'property_id': prop.public_id if prop else None,
        'ticket_id': ticket_public,
        'ticket_pk': move.ticket_id,
        'ticket_title': (ticket.title or '') if ticket else '',
        'ticket_status': (ticket.status or '') if ticket else '',
        'submitted_by': who or 'System',
        'created_at': move.created_at.isoformat() if move.created_at else None,
        'status': status,
        'needs_refill': status in ('refill', 'low'),
        'notes': move.notes or '',
    }


def usage_log_rows(*, movement_type='', property_name='', property_id='', department='', status='',
                   search='', date_from=None, date_to=None, limit=200):
    q = ProcMovement.query.order_by(ProcMovement.created_at.desc(), ProcMovement.id.desc())
    if movement_type:
        q = q.filter(ProcMovement.movement_type == movement_type)
    if date_from is not None:
        q = q.filter(ProcMovement.created_at >= date_from)
    if date_to is not None:
        q = q.filter(ProcMovement.created_at <= date_to)
    rows = q.limit(800).all()
    ticket_ids = {m.ticket_id for m in rows if m.ticket_id}
    tickets_by_id = {}
    if ticket_ids:
        for t in Ticket.query.filter(Ticket.id.in_(ticket_ids)).all():
            tickets_by_id[t.id] = t
    stock_by_key = _stock_lookup()
    search = (search or '').strip().lower()
    property_name = (property_name or '').strip().lower()
    property_id = (property_id or '').strip()
    department = (department or '').strip()
    status = (status or '').strip().lower()
    out = []
    for m in rows:
        d = movement_to_log_dict(m, tickets_by_id=tickets_by_id, stock_by_key=stock_by_key)
        if property_id and (d.get('property_id') or '') != property_id:
            continue
        if property_name and property_name not in (d.get('property') or '').lower():
            continue
        if department and d.get('department') != department:
            continue
        if status == 'refill' and d['status'] not in ('refill', 'low'):
            continue
        if status and status not in ('refill',) and d['status'] != status:
            continue
        if search:
            blob = ' '.join([
                d.get('material_name') or '',
                d.get('ticket_id') or '',
                d.get('ticket_title') or '',
                d.get('property') or '',
                d.get('log_id') or '',
                d.get('submitted_by') or '',
            ]).lower()
            if search not in blob:
                continue
        out.append(d)
        if len(out) >= limit:
            break
    return out


REFILL_OPEN_PR_STATUSES = (
    'draft', 'submitted', 'procurement_review', 'awaiting_quotation',
    'gm_review', 'approved', 'ordered',
)
REFILL_MOVE_LABELS = {
    'issue': 'Used on a ticket',
    'receipt': 'Goods received',
    'return': 'Returned to stock',
    'adjust': 'Stock edited',
    'transfer': 'Stock moved',
}


def _refill_last_moves(rows):
    """Latest stock movement per (property, catalog item)."""
    last = {}
    needed = {(row.property_id, row.catalog_item_id) for row in rows if row.catalog_item}
    if not needed:
        return last
    cat_ids = {cat for _, cat in needed}
    prop_ids = {prop for prop, _ in needed}
    moves = (
        ProcMovement.query
        .filter(
            ProcMovement.catalog_item_id.in_(cat_ids),
            ProcMovement.property_id.in_(prop_ids),
        )
        .order_by(ProcMovement.created_at.desc(), ProcMovement.id.desc())
        .all()
    )
    for move in moves:
        key = (move.property_id, move.catalog_item_id)
        if key not in needed or key in last:
            continue
        last[key] = move
        if len(last) == len(needed):
            break
    return last


def _open_prs_for_refill(rows):
    """Newest in-progress purchase request per (property, catalog item)."""
    out = {}
    cat_ids = {row.catalog_item_id for row in rows if row.catalog_item}
    prop_ids = {row.property_id for row in rows}
    if not cat_ids or not prop_ids:
        return out
    pairs = (
        db.session.query(ProcPurchaseLine, ProcPurchaseRequest)
        .join(ProcPurchaseRequest, ProcPurchaseLine.request_id == ProcPurchaseRequest.id)
        .filter(
            ProcPurchaseLine.catalog_item_id.in_(cat_ids),
            ProcPurchaseRequest.property_id.in_(prop_ids),
            ProcPurchaseRequest.status.in_(REFILL_OPEN_PR_STATUSES),
        )
        .order_by(ProcPurchaseRequest.updated_at.desc(), ProcPurchaseRequest.id.desc())
        .all()
    )
    for line, pr in pairs:
        key = (pr.property_id, line.catalog_item_id)
        if key in out:
            continue
        out[key] = {
            'id': pr.public_id,
            'status': pr.status,
            'qty': float(line.qty or 0),
            'updated_at': _iso_utc(_as_naive_utc(pr.updated_at or pr.created_at)),
        }
    return out


def _refill_stock_query():
    return (
        ProcStock.query.join(ProcCatalogItem)
        .filter(
            db.or_(
                ProcStock.qty_on_hand <= 0,
                db.and_(
                    ProcCatalogItem.min_qty > 0,
                    ProcStock.qty_on_hand <= ProcCatalogItem.min_qty,
                ),
            )
        )
    )


def refill_queue_summary():
    """Cheap sidebar counts: queue size, out-of-stock, latest flagged time."""
    q = _refill_stock_query()
    total = q.count()
    out_of_stock = q.filter(ProcStock.qty_on_hand <= 0).count() if total else 0
    newest = None
    if total:
        newest_updated, newest_created = q.with_entities(
            func.max(ProcStock.updated_at),
            func.max(ProcStock.created_at),
        ).first()
        newest = max(
            (t for t in (_as_naive_utc(newest_updated), _as_naive_utc(newest_created)) if t),
            default=None,
        )
    return {
        'total': total,
        'out_of_stock': out_of_stock,
        'newest_at': _iso_utc(newest),
    }


def refill_rows():
    rows = _refill_stock_query().all()
    last_moves = _refill_last_moves(rows)
    open_prs = _open_prs_for_refill(rows)
    out = []
    for row in rows:
        item = row.catalog_item
        if not item:
            continue
        qty = float(row.qty_on_hand or 0)
        min_qty = float(item.min_qty or 0)
        suggested = suggested_refill_qty(qty, min_qty)
        key = (row.property_id, row.catalog_item_id)
        move = last_moves.get(key)
        move_at = _as_naive_utc(move.created_at) if move else None
        stock_at = _as_naive_utc(row.updated_at or row.created_at)
        cat_at = _as_naive_utc(item.updated_at or item.created_at)
        flagged_at = max((t for t in (move_at, stock_at) if t), default=None) or cat_at
        last_event = REFILL_MOVE_LABELS.get(move.movement_type) if move else 'Below minimum'
        open_pr = open_prs.get(key)
        out.append({
            'stock_id': row.public_id,
            'catalog_id': item.public_id,
            'name': item.name,
            'brand': item.brand or '',
            'department': item.department,
            'uom': item.uom or 'PCS',
            'unit_price': float(item.unit_price or 0),
            'property': row.property.name if row.property else '',
            'property_id': row.property.public_id if row.property else None,
            'qty': qty,
            'min_qty': min_qty,
            'suggested_qty': suggested,
            'status': stock_status_label(qty, min_qty),
            'updated_at': _iso_utc(flagged_at),
            'edited_at': _iso_utc(stock_at),
            'last_event': last_event,
            'last_event_at': _iso_utc(move_at or flagged_at),
            'open_pr': open_pr,
        })
    out.sort(key=lambda x: (x['name'] or '').lower())
    out.sort(key=lambda x: x.get('updated_at') or '', reverse=True)
    return out


def _stock_row_for_pool(property_row, catalog_item):
    if not property_row or not catalog_item:
        return None
    return ProcStock.query.filter_by(
        property_id=property_row.id, catalog_item_id=catalog_item.id,
    ).first()


def resolve_consume_stock(ticket, catalog_item, *, stock_id=None, pool=None):
    """Stock must already sit on the ticket site or Shared. Never creates a row."""
    site = find_property_for_ticket(ticket)
    shared = ProcProperty.query.filter_by(is_shared=True).first()
    allowed_ids = set()
    if site:
        allowed_ids.add(site.id)
    if shared:
        allowed_ids.add(shared.id)

    stock_id = (stock_id or '').strip() or None
    if stock_id:
        stock = ProcStock.query.filter_by(public_id=stock_id).first()
        if (
            stock
            and stock.catalog_item_id == catalog_item.id
            and stock.property_id in allowed_ids
        ):
            return stock
        return None

    pool = (pool or '').strip().lower()
    if pool == 'shared':
        return _stock_row_for_pool(shared, catalog_item)
    if pool == 'site':
        return _stock_row_for_pool(site, catalog_item)

    site_stock = _stock_row_for_pool(site, catalog_item)
    if site_stock:
        return site_stock
    return _stock_row_for_pool(shared, catalog_item)


def ticket_catalog_materials(ticket):
    """Site-assigned stock plus Shared store rows for the ticket picker."""
    shared = ensure_shared_property()
    site = find_property_for_ticket(ticket)
    materials = []

    def _append(prop, pool):
        if not prop:
            return
        rows = ProcStock.query.filter_by(property_id=prop.id).all()
        for row in rows:
            item = row.catalog_item
            if not item:
                continue
            materials.append({
                'catalog_id': item.public_id,
                'stock_id': row.public_id,
                'pool': pool,
                'qty_on_hand': float(row.qty_on_hand or 0),
                'name': item.name,
                'brand': item.brand or '',
                'uom': (item.uom or 'PCS'),
                'unit_price': float(item.unit_price or 0),
                'category': item.department or 'General',
            })

    _append(site, 'site')
    _append(shared, 'shared')
    return {
        'property': (
            {'name': site.name, 'id': site.public_id, 'matched': True}
            if site else None
        ),
        'shared': {'name': shared.name, 'id': shared.public_id},
        'materials': materials,
    }


def consume_on_ticket(*, user, ticket, catalog_public_id, qty, chargeable=False,
                      unit_price=None, notes=None, uom=None, material_name=None,
                      stock_id=None, pool=None, stock_row=None):
    """Log catalog usage on a ticket without blocking the technician.

    Deducts min(requested, on-hand), logs the deducted qty, and records any
    shortage on the ticket line. Does not create a property or stock row
    for unmatched sites.
    """
    try:
        requested = float(qty or 0)
    except (TypeError, ValueError):
        requested = 0.0
    if requested <= 0:
        requested = 1.0
    item = ProcCatalogItem.query.filter_by(public_id=(catalog_public_id or '').strip()).first()
    if not item:
        mat = TicketMaterial(
            ticket_id=ticket.id,
            material_name=(material_name or notes or 'Material')[:255],
            quantity=requested,
            unit=(uom or 'PCS'),
            unit_price=float(unit_price or 0),
            total_price=round(requested * float(unit_price or 0), 2),
            from_procurement=True,
            procurement_ref=(catalog_public_id or '').strip() or None,
            notes=notes,
            qty_short=0.0,
        )
        db.session.add(mat)
        return mat

    stock = stock_row or resolve_consume_stock(ticket, item, stock_id=stock_id, pool=pool)
    if not stock:
        raise ValueError(
            'This material is not assigned to this property or Shared stock.'
        )
    property_row = stock.property
    on_hand = float(stock.qty_on_hand or 0)
    deducted = round(min(requested, max(0.0, on_hand)), 2)
    short = round(max(0.0, requested - deducted), 2)
    stock.qty_on_hand = round(on_hand - deducted, 2)
    if deducted:
        record_movement(
            movement_type='issue',
            property_row=property_row,
            catalog_item=item,
            qty=-deducted,
            user=user,
            ticket_id=ticket.id,
            notes=f'Issue to {ticket.ticket_id}',
        )
    price = float(item.unit_price or 0)
    if unit_price not in (None, ''):
        try:
            price = float(unit_price)
        except (TypeError, ValueError):
            pass
    mat = TicketMaterial(
        ticket_id=ticket.id,
        material_name=item.name,
        quantity=deducted,
        unit=(uom or item.uom or 'PCS'),
        unit_price=price,
        total_price=round(deducted * price, 2),
        from_procurement=True,
        procurement_ref=item.public_id,
        notes=(notes or ('chargeable' if chargeable else '')) or None,
        qty_short=short,
    )
    if hasattr(mat, 'catalog_item_id'):
        mat.catalog_item_id = item.id
    db.session.add(mat)

    min_qty = float(item.min_qty or 0)
    after = float(stock.qty_on_hand or 0)
    crossed_min = is_refill_needed(after, min_qty) and not is_refill_needed(on_hand, min_qty)
    drained = deducted > 0 and after <= 0
    if deducted > 0 and (crossed_min or drained) and is_refill_needed(after, min_qty):
        notify_users(
            procurement_user_ids(),
            'Refill needed',
            f'{item.name} at {property_row.name} dropped to {after:g} (min {min_qty:g}).',
            'proc_refill',
        )
    return mat


def restore_ticket_material(*, user, ticket_material, property_public_id=None):
    """Return catalog-linked ticket materials to stock; otherwise just delete."""
    linked = (
        ticket_material.from_procurement
        or ticket_material.procurement_ref
        or getattr(ticket_material, 'catalog_item_id', None)
    )
    if not linked:
        db.session.delete(ticket_material)
        return
    try:
        return_from_ticket(
            user=user,
            ticket_material=ticket_material,
            property_public_id=property_public_id,
        )
    except ValueError:
        db.session.delete(ticket_material)


def _issue_qty_in_range(start, end):
    total = db.session.query(
        func.coalesce(func.sum(func.abs(ProcMovement.qty)), 0.0)
    ).filter(
        ProcMovement.movement_type == 'issue',
        ProcMovement.created_at >= start,
        ProcMovement.created_at <= end,
    ).scalar()
    return float(total or 0)


def _spend_in_range(start, end):
    total = db.session.query(
        func.coalesce(func.sum(ProcPurchaseRequest.total_aed), 0.0)
    ).filter(
        ProcPurchaseRequest.status.in_(('received', 'closed')),
        ProcPurchaseRequest.received_at.isnot(None),
        ProcPurchaseRequest.received_at >= start,
        ProcPurchaseRequest.received_at <= end,
    ).scalar()
    return float(total or 0)


def _stock_value():
    total = db.session.query(
        func.coalesce(func.sum(ProcStock.qty_on_hand * ProcCatalogItem.unit_price), 0.0)
    ).join(
        ProcCatalogItem, ProcStock.catalog_item_id == ProcCatalogItem.id
    ).scalar()
    return float(total or 0)


class _IssueSnap:
    __slots__ = ('created_at', 'qty', 'department')

    def __init__(self, created_at, qty, department):
        self.created_at = created_at
        self.qty = qty
        self.department = department or 'Other'


def _issue_snaps(start, end):
    rows = (
        db.session.query(
            ProcMovement.created_at,
            ProcMovement.qty,
            ProcCatalogItem.department,
        )
        .outerjoin(ProcCatalogItem, ProcMovement.catalog_item_id == ProcCatalogItem.id)
        .filter(
            ProcMovement.movement_type == 'issue',
            ProcMovement.created_at >= start,
            ProcMovement.created_at <= end,
        )
        .all()
    )
    return [_IssueSnap(created_at, qty, dept) for created_at, qty, dept in rows]


def _spark_weekly_issues(weeks=8):
    now = _utcnow()
    start_all = now - timedelta(days=7 * weeks)
    moves = _issue_snaps(start_all, now)
    series = [0.0] * weeks
    for m in moves:
        if not m.created_at:
            continue
        delta = (now - m.created_at).days
        idx = weeks - 1 - min(weeks - 1, max(0, delta // 7))
        series[idx] += abs(float(m.qty or 0))
    return series


def _empty_trade_series(n):
    series = {dept: [0.0] * n for dept in TRADE_CHART_ORDER}
    series['Other'] = [0.0] * n
    return series


def _trade_of(move):
    dept = getattr(move, 'department', None)
    if not dept and getattr(move, 'catalog_item', None):
        dept = move.catalog_item.department
    return dept if dept in TRADE_CHART_ORDER else 'Other'


def _week_monday(dt):
    d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())


def _clip_moves(moves, start=None, end=None):
    out = []
    for m in moves:
        if not m.created_at:
            continue
        if start is not None and m.created_at < start:
            continue
        if end is not None and m.created_at > end:
            continue
        out.append(m)
    return out


def _bucket_moves(moves, key_fn, keys):
    series = _empty_trade_series(len(keys))
    index = {k: i for i, k in enumerate(keys)}
    for m in moves:
        if not m.created_at:
            continue
        k = key_fn(m.created_at)
        idx = index.get(k)
        if idx is None:
            continue
        series[_trade_of(m)][idx] += abs(float(m.qty or 0))
    return series


def _utilization_monthly(moves, now, months_n=12, start=None, end=None):
    months = []
    if start is not None and end is not None:
        cursor = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        guard = 0
        while cursor >= first and guard < 36:
            months.append(cursor)
            if cursor.month == 1:
                cursor = cursor.replace(year=cursor.year - 1, month=12)
            else:
                cursor = cursor.replace(month=cursor.month - 1)
            guard += 1
        months.reverse()
        if not months:
            months = [first]
    else:
        cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for _ in range(months_n):
            months.append(cursor)
            if cursor.month == 1:
                cursor = cursor.replace(year=cursor.year - 1, month=12)
            else:
                cursor = cursor.replace(month=cursor.month - 1)
        months.reverse()
    keys = [(d.year, d.month) for d in months]
    series = _bucket_moves(moves, lambda dt: (dt.year, dt.month), keys)
    return {'labels': [d.strftime('%b') for d in months], 'series': series}


def _utilization_weekly(moves, now, weeks=12, start=None, end=None):
    if start is not None and end is not None:
        first_monday = _week_monday(start)
        last_monday = _week_monday(end)
        weeks_n = max(1, int((last_monday - first_monday).days // 7) + 1)
        starts = [first_monday + timedelta(weeks=i) for i in range(weeks_n)]
    else:
        this_monday = _week_monday(now)
        starts = [this_monday - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    keys = [(d.isocalendar()[0], d.isocalendar()[1]) for d in starts]
    series = _bucket_moves(moves, lambda dt: (dt.isocalendar()[0], dt.isocalendar()[1]), keys)
    labels = []
    for d in starts:
        label_dt = d
        if start is not None and start > d:
            label_dt = start
        labels.append(f"{label_dt.day} {label_dt.strftime('%b')}")
    return {'labels': labels, 'series': series}


def _utilization_yearly(moves, now, years_n=4, start=None, end=None):
    if start is not None and end is not None:
        years = list(range(start.year, end.year + 1)) or [end.year]
    else:
        years = [now.year - years_n + 1 + i for i in range(years_n)]
    series = _bucket_moves(moves, lambda dt: dt.year, years)
    return {'labels': [str(y) for y in years], 'series': series}


def _series_totals(series):
    n = 0
    for vals in (series or {}).values():
        n = max(n, len(vals or []))
    totals = [0.0] * n
    for vals in (series or {}).values():
        for i, v in enumerate(vals or []):
            totals[i] += float(v or 0)
    return totals


def _as_date(dt):
    if dt is None:
        return None
    return dt.date() if hasattr(dt, 'date') else dt


def _utilization_daily(moves, start, end, clip_midnight_end=False):
    start_d = _as_date(start)
    end_d = _as_date(end)
    if (
        clip_midnight_end
        and end_d
        and start_d
        and end_d > start_d
        and getattr(end, 'hour', 1) == 0
        and getattr(end, 'minute', 0) == 0
        and getattr(end, 'second', 0) == 0
    ):
        end_d = end_d - timedelta(days=1)
    n = max(1, (end_d - start_d).days + 1)
    days = [start_d + timedelta(days=i) for i in range(n)]
    series = _bucket_moves(moves, lambda dt: _as_date(dt), days)
    totals = _series_totals(series)
    return {
        'labels': [f"{d.day} {d.strftime('%b')}" for d in days],
        'series': series,
        'issued': totals,
    }


def dashboard_payload(range_key='month', break_key=None):
    key, label, start, end, prev_start, prev_end = period_bounds(range_key)
    b_raw = (break_key or '').strip()
    bk, blabel, bstart, bend, bprev_start, bprev_end = period_bounds(b_raw or range_key)
    below = refill_rows()
    issued = _issue_qty_in_range(start, end)
    issued_prev = _issue_qty_in_range(prev_start, prev_end)
    spend = _spend_in_range(start, end)
    spend_prev = _spend_in_range(prev_start, prev_end)
    stock_value = _stock_value()
    spark = _spark_weekly_issues(8)

    now = _utcnow()
    lookback = now.replace(year=now.year - 4, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    moves = _issue_snaps(lookback, now)
    period_moves = _clip_moves(moves, start, end)

    weekly = _utilization_weekly(period_moves, now, start=start, end=end)
    monthly = _utilization_monthly(period_moves, now, start=start, end=end)
    yearly = _utilization_yearly(period_moves, now, start=start, end=end)
    daily = _utilization_daily(moves, bstart, bend)
    prev_daily = _utilization_daily(moves, bprev_start, bprev_end, clip_midnight_end=True)
    prev_issued = prev_daily.get('issued') or []
    n = len(daily.get('issued') or [])
    daily['compare'] = (prev_issued + [0.0] * n)[:n]

    breakdown_map = defaultdict(float)
    for m in moves:
        if not m.created_at or m.created_at < bstart or m.created_at > bend:
            continue
        breakdown_map[_trade_of(m)] += abs(float(m.qty or 0))
    breakdown = [{'label': dept, 'qty': breakdown_map.get(dept, 0.0)} for dept in TRADE_CHART_ORDER]
    extra = [(k, v) for k, v in breakdown_map.items() if k not in TRADE_CHART_ORDER]
    breakdown.extend({'label': k, 'qty': v} for k, v in extra)

    recent = usage_log_rows(limit=10)

    return {
        'success': True,
        'period': key,
        'period_label': label,
        'period_start': start.strftime('%Y-%m-%d'),
        'period_end': end.strftime('%Y-%m-%d'),
        'break_period': bk,
        'break_period_label': blabel,
        'break_period_start': bstart.strftime('%Y-%m-%d'),
        'break_period_end': bend.strftime('%Y-%m-%d'),
        'kpis': {
            'below_threshold': {
                'value': len(below),
                'delta': 0,
                'spark': spark,
            },
            'issued': {
                'value': issued,
                'delta': _pct_delta(issued, issued_prev),
                'spark': spark,
            },
            'spend': {
                'value': spend,
                'delta': _pct_delta(spend, spend_prev),
                'spark': spark,
            },
            'stock_value': {
                'value': stock_value,
                'delta': 0,
                'spark': spark,
            },
        },
        'utilization': monthly,
        'charts': {
            'week': weekly,
            'month': monthly,
            'year': yearly,
        },
        'daily': daily,
        'breakdown': breakdown,
        'recent': recent,
    }


def usage_log_csv_rows(rows):
    out = [['ID', 'Ticket', 'Material', 'Property', 'Department', 'Qty', 'UOM', 'Status', 'Issued by', 'Date']]
    for d in rows:
        out.append([
            d.get('log_id') or '',
            d.get('ticket_id') or '',
            d.get('material_name') or '',
            d.get('property') or '',
            d.get('department') or '',
            d.get('qty') or 0,
            d.get('uom') or '',
            d.get('status') or '',
            d.get('submitted_by') or '',
            (d.get('created_at') or '')[:19],
        ])
    return out
