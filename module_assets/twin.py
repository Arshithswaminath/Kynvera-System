"""2D digital-twin helpers: live pin status from assets + open work orders."""
import json
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from app.models import (
    db, Asset, Ticket, TicketAsset, FloorPlan, TicketProject,
    TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit,
)

CLOSED_TICKET_STATUSES = frozenset({
    'closed', 'cancelled', 'draft', 'resolved',
})
_SEVERITY_RANK = {'crit': 3, 'warn': 2, 'ok': 1}
_SEVERITY_ALIASES = {
    'ok': 'ok', 'healthy': 'ok', 'good': 'ok',
    'warn': 'warn', 'warning': 'warn', 'medium': 'warn',
    'crit': 'crit', 'critical': 'crit', 'high': 'crit',
}
_ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}
DEFAULT_PLAN_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='960' height='560'%3E"
    "%3Crect fill='%230f1f18' width='100%25' height='100%25'/%3E"
    "%3Crect fill='none' stroke='%232d6a4f' stroke-width='3' x='40' y='36' width='880' height='488' rx='12'/%3E"
    "%3Ctext x='480' y='290' fill='%23cfe7d8' font-family='sans-serif' font-size='22' "
    "text-anchor='middle'%3EFloor plan%3C/text%3E%3C/svg%3E"
)


def ticket_is_open(ticket):
    return (ticket.status or '').strip().lower() not in CLOSED_TICKET_STATUSES


def parse_severity(raw):
    return _SEVERITY_ALIASES.get(str(raw or '').strip().lower())


def worse_severity(a, b):
    if _SEVERITY_RANK.get(a, 0) >= _SEVERITY_RANK.get(b, 0):
        return a or 'ok'
    return b or 'ok'


def asset_severity(asset, open_tickets):
    prios = {(t.priority or '').strip().lower() for t in open_tickets}
    health = asset.health_score
    status = (asset.status or '').strip().lower()
    if (
        status == 'critical'
        or (health is not None and health < 40)
        or 'critical' in prios
        or 'high' in prios
    ):
        return 'crit'
    if open_tickets or status == 'inactive' or (health is not None and health < 70):
        return 'warn'
    return 'ok'


def tickets_for_asset(asset):
    link_ids = [
        row.ticket_id
        for row in TicketAsset.query.filter_by(asset_pk=asset.id).all()
    ]
    clauses = [Ticket.asset_id == asset.id]
    if link_ids:
        clauses.append(Ticket.id.in_(link_ids))
    return (
        Ticket.query.filter(db.or_(*clauses))
        .order_by(Ticket.created_at.desc())
        .all()
    )


def normalize_hotspots(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = []
    if not isinstance(raw, list):
        return []
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            x = max(0.0, min(100.0, float(item.get('x_pct', 50))))
            y = max(0.0, min(100.0, float(item.get('y_pct', 50))))
        except (TypeError, ValueError):
            x, y = 50.0, 50.0
        ids = item.get('asset_ids') or []
        if isinstance(ids, str):
            ids = [part.strip() for part in ids.split(',') if part.strip()]
        ids = [str(code).strip() for code in ids if str(code).strip()]
        hid = str(item.get('id') or '').strip() or f'hs-{i + 1}'
        room = (item.get('room') or 'Room').strip() or 'Room'
        pin = {
            'id': hid,
            'room': room,
            'x_pct': round(x, 2),
            'y_pct': round(y, 2),
            'asset_ids': ids,
        }
        sev = parse_severity(item.get('severity'))
        if sev:
            pin['severity'] = sev
        out.append(pin)
    return out


def resolve_hotspot_assets(plan, hotspot):
    """Prefer explicit asset_ids (even across floors); else same building + room."""
    seen = set()
    assets = []
    codes = hotspot.get('asset_ids') or []
    if isinstance(codes, str):
        codes = [part.strip() for part in codes.split(',') if part.strip()]
    for code in codes:
        row = Asset.query.filter_by(asset_id=str(code).strip()).first()
        if row and row.id not in seen:
            seen.add(row.id)
            assets.append(row)
    if assets:
        return assets
    room = (hotspot.get('room') or '').strip().lower()
    if not room or not plan.building:
        return assets
    for row in Asset.query.filter(Asset.building == plan.building).all():
        if row.id in seen:
            continue
        if (row.room or '').strip().lower() == room:
            seen.add(row.id)
            assets.append(row)
    return assets


def plan_display_url(plan):
    url = plan.image_url or ''
    if url.startswith(('data:', 'http://', 'https://', '/static/', '/assets/')):
        return url
    if url:
        return f'/assets/api/floor-plans/{plan.id}/file'
    return DEFAULT_PLAN_SVG


def drawings_for_asset(asset_code):
    """Floor plans where this asset is ticked on a pin."""
    code = str(asset_code or '').strip().lower()
    if not code:
        return []
    links = []
    for plan in FloorPlan.query.order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name).all():
        for hs in normalize_hotspots(plan.hotspots):
            ids = [str(x).strip().lower() for x in (hs.get('asset_ids') or [])]
            if code not in ids:
                continue
            loc = plan.building or ''
            if plan.floor:
                loc = f'{loc} / {plan.floor}' if loc else plan.floor
            links.append({
                'plan_id': plan.id,
                'name': plan.name,
                'building': plan.building,
                'floor': plan.floor,
                'location': loc,
                'room': hs.get('room') or 'Pin',
                'pin_id': hs.get('id'),
                'display_url': plan_display_url(plan),
                'twin_url': f'/assets/twin/plan/{plan.id}?pin={hs.get("id") or ""}&asset={asset_code}',
            })
    return links


def _ticket_payload(ticket):
    return {
        'ticket_id': ticket.ticket_id,
        'title': ticket.title,
        'priority': ticket.priority,
        'status': ticket.status,
        'url': f'/tickets/{ticket.ticket_id}',
    }


def _asset_payload(asset, severity):
    return {
        'asset_id': asset.asset_id,
        'name': asset.name,
        'status': asset.status,
        'health_score': asset.health_score,
        'room': asset.room,
        'floor': asset.floor,
        'url': f'/assets/{asset.asset_id}',
        'severity': severity,
    }


def enrich_floor_plan(plan):
    counts = {'crit': 0, 'warn': 0, 'ok': 0}
    hotspots = []
    for stored in normalize_hotspots(plan.hotspots):
        assets = resolve_hotspot_assets(plan, stored)
        asset_payloads = []
        ticket_payloads = []
        seen_tickets = set()
        worst = 'ok'
        notes = []
        _prio = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        for asset in assets:
            opens = [t for t in tickets_for_asset(asset) if ticket_is_open(t)]
            opens.sort(key=lambda t: _prio.get((t.priority or '').lower(), 9))
            sev = asset_severity(asset, opens)
            worst = worse_severity(worst, sev)
            asset_payloads.append(_asset_payload(asset, sev))
            for ticket in opens:
                if ticket.id in seen_tickets:
                    continue
                seen_tickets.add(ticket.id)
                notes.append(ticket.title)
                if len(ticket_payloads) < 8:
                    ticket_payloads.append(_ticket_payload(ticket))
        if not notes and assets:
            top = assets[0]
            if top.health_score is not None:
                notes.append(f'Health {top.health_score}%')
            elif top.status and top.status != 'active':
                notes.append(f'Asset {top.status}')
        if notes:
            note = notes[0]
        elif assets:
            note = 'No open work orders'
        else:
            note = 'No assets linked'
        chosen = parse_severity(stored.get('severity'))
        pin_sev = chosen or worst
        counts[pin_sev] = counts.get(pin_sev, 0) + 1
        hotspots.append({
            **stored,
            'asset_ids': [a.asset_id for a in assets] or stored['asset_ids'],
            'severity': pin_sev,
            'live_severity': worst,
            'health_locked': bool(chosen),
            'note': note,
            'assets': asset_payloads,
            'open_tickets': ticket_payloads,
            'open_ticket_count': len(seen_tickets),
        })
    payload = plan.to_dict()
    payload['hotspots'] = hotspots
    payload['counts'] = counts
    payload['display_url'] = plan_display_url(plan)
    return payload


def _property_to_building(prop):
    key = (prop.name or '').strip()
    if not key:
        return None
    floors = {}
    for zone in prop.zones.filter_by(is_active=True).order_by(TicketZone.name):
        zname = (zone.name or '').strip()
        if not zname:
            continue
        floor = floors.setdefault(zname, {'name': zname, 'rooms': {}})
        for sz in zone.sub_zones.filter_by(is_active=True).order_by(TicketSubZone.name):
            for unit in sz.base_units.filter_by(is_active=True).order_by(TicketBaseUnit.name):
                rname = (unit.name or '').strip()
                if not rname:
                    continue
                prev = floor['rooms'].get(rname) or {}
                floor['rooms'][rname] = {
                    'name': rname,
                    'latitude': prev.get('latitude') if prev.get('latitude') is not None else unit.latitude,
                    'longitude': prev.get('longitude') if prev.get('longitude') is not None else unit.longitude,
                }
    return {
        'name': key,
        'latitude': prop.latitude,
        'longitude': prop.longitude,
        'floors': [
            {
                'name': f['name'],
                'rooms': sorted(f['rooms'].values(), key=lambda row: row['name'].lower()),
            }
            for f in sorted(floors.values(), key=lambda row: row['name'].lower())
        ],
    }


def ticket_location_catalog():
    """Service Tickets locations: project → building → floor → room.

    Project = TicketProject, property = building, zone = floor, base unit = room.
    """
    projects = []
    for proj in TicketProject.query.filter_by(is_active=True).order_by(TicketProject.name):
        buildings = []
        for prop in proj.properties.filter_by(is_active=True).order_by(TicketProperty.name):
            building = _property_to_building(prop)
            if building:
                buildings.append(building)
        projects.append({
            'id': proj.id,
            'name': proj.name,
            'buildings': buildings,
        })
    standalone = []
    for prop in (
        TicketProperty.query.filter_by(project_id=None, is_active=True)
        .order_by(TicketProperty.name)
    ):
        building = _property_to_building(prop)
        if building:
            standalone.append(building)
    if standalone:
        projects.append({'id': None, 'name': 'Unassigned', 'buildings': standalone})
    return projects


def catalog_buildings_for_project(project_id):
    if not project_id:
        return []
    for row in ticket_location_catalog():
        if row.get('id') == project_id:
            return row.get('buildings') or []
    return []


def project_location_assets(project_id, building_names=None):
    """FM assets fed for this ticket project (by project_id or matching building)."""
    filters = []
    if project_id:
        filters.append(Asset.project_id == project_id)
    names = [str(n).strip() for n in (building_names or []) if str(n).strip()]
    if names:
        filters.append(Asset.building.in_(names))
    if not filters:
        return []
    return (
        Asset.query.filter(db.or_(*filters))
        .order_by(Asset.building, Asset.floor, Asset.name)
        .all()
    )


def plan_pin_stats(plan):
    """Pin counts + thumbnail for hub and project floor cards."""
    enriched = enrich_floor_plan(plan)
    counts = enriched.get('counts') or {}
    crit = int(counts.get('crit') or 0)
    warn = int(counts.get('warn') or 0)
    ok = int(counts.get('ok') or 0)
    return {
        'id': plan.id,
        'name': plan.name,
        'building': plan.building,
        'floor': plan.floor,
        'project_id': getattr(plan, 'project_id', None),
        'display_url': enriched.get('display_url') or plan_display_url(plan),
        'pin_count': crit + warn + ok,
        'crit': crit,
        'warn': warn,
        'ok': ok,
    }


def recommend_fallback(enriched):
    recs = []
    counts = enriched.get('counts') or {}
    crit = int(counts.get('crit') or 0)
    warn = int(counts.get('warn') or 0)
    for pin in enriched.get('hotspots') or []:
        sev = pin.get('severity') or 'ok'
        tickets = pin.get('open_tickets') or []
        if sev == 'ok' and not tickets:
            continue
        if tickets:
            extra = f' and {len(tickets) - 1} more' if len(tickets) > 1 else ''
            action = f"Follow up {tickets[0].get('ticket_id')}{extra}"
        elif sev == 'crit':
            action = 'Raise a work order now'
        else:
            action = 'Inspect and schedule follow-up'
        recs.append({
            'room': pin.get('room') or 'Room',
            'severity': sev,
            'action': action,
            'reason': pin.get('note') or '',
        })
    if recs:
        summary = (
            f'{crit} critical and {warn} warning room(s) on this plan. '
            'Start with red pins.'
        )
    else:
        summary = 'No open issues on this floor — pins are healthy.'
    return {
        'summary': summary,
        'recommendations': recs,
        'method': 'live_status',
    }


def _upload_dir():
    dest = os.path.join(current_app.root_path, 'static', 'uploads', 'floor-plans')
    os.makedirs(dest, exist_ok=True)
    return dest


def save_plan_image(plan, file_storage):
    filename = secure_filename(file_storage.filename or '') or 'plan.png'
    ext = os.path.splitext(filename)[1].lower() or '.png'
    if ext not in _ALLOWED_IMAGE_EXT:
        return None, 'Use a PNG, JPG, WEBP, GIF, or SVG image'
    name = f'plan-{plan.id}-{uuid.uuid4().hex[:10]}{ext}'
    path = os.path.join(_upload_dir(), name)
    file_storage.save(path)
    plan.image_url = f'/static/uploads/floor-plans/{name}'
    return plan.image_url, None
