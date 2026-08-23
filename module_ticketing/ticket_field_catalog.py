"""DB-backed ticket field catalogs (classification, priorities, hold/cancel reasons)."""

from __future__ import annotations

import logging
import re

from app.models import (
    db, Ticket, TicketServiceGroup, TicketFaultCategory, TicketFaultCode,
    TicketPriority, TicketHoldReason, TicketCancelReason,
)

logger = logging.getLogger(__name__)

DEFAULT_PRIORITIES = [
    {'value': 'low', 'label': 'Low', 'sla_hint': '72h+', 'sort_order': 10,
     'hint': 'Scheduled in normal order — good for preventative or low-impact jobs.'},
    {'value': 'medium', 'label': 'Medium', 'sla_hint': '24–48h', 'sort_order': 20,
     'hint': 'Typical urgency — supervisors route in standard queue sequence.'},
    {'value': 'high', 'label': 'High', 'sla_hint': '8–24h', 'sort_order': 30,
     'hint': 'Supervisors should prioritise assignment and milestone follow-up.'},
    {'value': 'critical', 'label': 'Critical', 'sla_hint': 'ASAP', 'sort_order': 40,
     'hint': 'Urgent safety or severe service impact — treat as immediate attention.'},
]

DEFAULT_HOLD_REASONS = [
    {'key': 'pending_materials', 'label': 'Waiting for Materials', 'sort_order': 10},
    {'key': 'pending_approval', 'label': 'Pending Approval', 'sort_order': 20},
    {'key': 'awaiting_client', 'label': 'Awaiting Client Response', 'sort_order': 30},
    {'key': 'other', 'label': 'Other', 'sort_order': 90},
]

DEFAULT_CANCEL_REASONS = [
    {'key': 'duplicate', 'label': 'Duplicate ticket', 'sort_order': 10},
    {'key': 'wrong_assignment', 'label': 'Wrong assignment', 'sort_order': 20},
    {'key': 'client_request', 'label': 'Client request', 'sort_order': 30},
    {'key': 'out_of_scope', 'label': 'Out of scope', 'sort_order': 40},
    {'key': 'resolved_elsewhere', 'label': 'Resolved elsewhere', 'sort_order': 50},
    {'key': 'no_site_access', 'label': 'No site access', 'sort_order': 60},
    {'key': 'other', 'label': 'Other', 'sort_order': 90},
]


def slugify_key(raw: str, *, fallback: str = 'item') -> str:
    s = re.sub(r'[^a-z0-9]+', '_', (raw or '').strip().lower()).strip('_')
    return s[:60] or fallback


def seed_priority_and_reason_defaults() -> None:
    if TicketPriority.query.count() == 0:
        for row in DEFAULT_PRIORITIES:
            db.session.add(TicketPriority(**row, is_active=True))
    if TicketHoldReason.query.count() == 0:
        for row in DEFAULT_HOLD_REASONS:
            db.session.add(TicketHoldReason(**row, is_active=True))
    if TicketCancelReason.query.count() == 0:
        for row in DEFAULT_CANCEL_REASONS:
            db.session.add(TicketCancelReason(**row, is_active=True))


def seed_classification_from_json_if_empty() -> int:
    """Import bundled fault_codes.json into DB tables once, if classification is empty."""
    import os
    if os.environ.get('TESTING') == 'true' or os.environ.get('FLASK_ENV') == 'testing':
        return 0
    if TicketServiceGroup.query.count() > 0:
        return 0
    try:
        from module_ticketing import fault_catalog as fc
    except ImportError:
        return 0
    bundle = fc.load_bundle()
    if not bundle or not bundle.get('fault_catalog'):
        return 0
    return upsert_fault_bundle(bundle, deactivate_missing=False)


def upsert_fault_bundle(bundle: dict, *, deactivate_missing: bool = True) -> int:
    """Upsert service groups / categories / fault codes from a catalog bundle."""
    rows = bundle.get('fault_catalog') or []
    if not rows:
        return 0

    groups = {g.name.strip().lower(): g for g in TicketServiceGroup.query.all() if g.name}
    cats = {}
    for c in TicketFaultCategory.query.all():
        sg = c.service_group
        if not sg or not c.name:
            continue
        cats[(sg.name.strip().lower(), c.name.strip().lower())] = c
    codes = {}
    for fc_row in TicketFaultCode.query.all():
        cat = fc_row.category
        sg = cat.service_group if cat else None
        if not cat or not sg:
            continue
        codes[(sg.name.strip().lower(), cat.name.strip().lower(), (fc_row.code or '').strip().lower())] = fc_row

    seen_group = set()
    seen_cat = set()
    seen_code = set()
    imported = 0
    sg_order = 0
    for row in rows:
        sg_name = (row.get('service_group') or '').strip()
        cat_name = (row.get('fault_category') or '').strip()
        code = (row.get('fault_code') or '').strip()
        name = (row.get('fault_code_name') or '').strip() or code
        if not sg_name or not cat_name or not code:
            continue
        sg_key = sg_name.lower()
        cat_key = (sg_key, cat_name.lower())
        code_key = (sg_key, cat_name.lower(), code.lower())

        sg = groups.get(sg_key)
        if sg is None:
            sg_order += 10
            sg = TicketServiceGroup(name=sg_name, sort_order=sg_order, is_active=True)
            db.session.add(sg)
            db.session.flush()
            groups[sg_key] = sg
        else:
            sg.is_active = True
            if sg.name != sg_name:
                sg.name = sg_name
        seen_group.add(sg.id)

        cat = cats.get(cat_key)
        if cat is None:
            cat = TicketFaultCategory(
                service_group_id=sg.id, name=cat_name,
                sort_order=len([k for k in cats if k[0] == sg_key]) * 10,
                is_active=True,
            )
            db.session.add(cat)
            db.session.flush()
            cats[cat_key] = cat
        else:
            cat.is_active = True
            if cat.name != cat_name:
                cat.name = cat_name
        seen_cat.add(cat.id)

        fc_row = codes.get(code_key)
        dur = row.get('duration_mins')
        try:
            dur_i = int(dur) if dur is not None and dur != '' else None
        except (TypeError, ValueError):
            dur_i = None
        payload = dict(
            name=name,
            duration_mins=dur_i,
            suggested_title=(row.get('suggested_title') or '')[:255] or None,
            suggested_work_description=row.get('suggested_work_description') or None,
            root_cause_applicability=(row.get('root_cause_applicability') or None),
            is_active=True,
        )
        if fc_row is None:
            fc_row = TicketFaultCode(
                category_id=cat.id,
                code=code,
                sort_order=imported,
                **payload,
            )
            db.session.add(fc_row)
            db.session.flush()
            codes[code_key] = fc_row
        else:
            for k, v in payload.items():
                setattr(fc_row, k, v)
        seen_code.add(fc_row.id)
        imported += 1

    if deactivate_missing:
        for g in TicketServiceGroup.query.all():
            if g.id not in seen_group:
                g.is_active = False
        for c in TicketFaultCategory.query.all():
            if c.id not in seen_cat:
                c.is_active = False
        for fc_row in TicketFaultCode.query.all():
            if fc_row.id not in seen_code:
                fc_row.is_active = False

    db.session.commit()
    return imported


def seed_ticket_field_catalogs() -> None:
    """Idempotent seed of priorities, reasons, and classification (from JSON if empty)."""
    try:
        seed_priority_and_reason_defaults()
        seed_classification_from_json_if_empty()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Ticket field catalog seed skipped: %s', exc)


def active_priorities() -> list[TicketPriority]:
    return (
        TicketPriority.query.filter_by(is_active=True)
        .order_by(TicketPriority.sort_order, TicketPriority.id)
        .all()
    )


def active_hold_reasons() -> list[TicketHoldReason]:
    return (
        TicketHoldReason.query.filter_by(is_active=True)
        .order_by(TicketHoldReason.sort_order, TicketHoldReason.id)
        .all()
    )


def active_cancel_reasons() -> list[TicketCancelReason]:
    return (
        TicketCancelReason.query.filter_by(is_active=True)
        .order_by(TicketCancelReason.sort_order, TicketCancelReason.id)
        .all()
    )


def hold_reason_map() -> dict[str, str]:
    rows = active_hold_reasons()
    if rows:
        return {r.key: r.label for r in rows}
    return {r['key']: r['label'] for r in DEFAULT_HOLD_REASONS}


def cancel_reason_map() -> dict[str, str]:
    rows = active_cancel_reasons()
    if rows:
        return {r.key: r.label for r in rows}
    return {r['key']: r['label'] for r in DEFAULT_CANCEL_REASONS}


def priority_values() -> set[str]:
    rows = active_priorities()
    if rows:
        return {r.value for r in rows}
    return {r['value'] for r in DEFAULT_PRIORITIES}


def classification_options() -> dict | None:
    """Return options dict from DB, or None if classification tables are empty."""
    groups = (
        TicketServiceGroup.query.filter_by(is_active=True)
        .order_by(TicketServiceGroup.sort_order, TicketServiceGroup.name)
        .all()
    )
    if not groups:
        return None

    catalog = []
    categories_by_sg: dict[str, list[str]] = {}
    service_groups = []
    for g in groups:
        service_groups.append(g.name)
        cats = (
            TicketFaultCategory.query.filter_by(service_group_id=g.id, is_active=True)
            .order_by(TicketFaultCategory.sort_order, TicketFaultCategory.name)
            .all()
        )
        cat_names = []
        for c in cats:
            cat_names.append(c.name)
            for fc_row in (
                TicketFaultCode.query.filter_by(category_id=c.id, is_active=True)
                .order_by(TicketFaultCode.sort_order, TicketFaultCode.code)
                .all()
            ):
                catalog.append(fc_row.to_dict())
        categories_by_sg[g.name] = cat_names

    return {
        'service_groups': service_groups,
        'categories': categories_by_sg,
        'fault_catalog': catalog,
        'use_fault_catalog': bool(catalog),
        'fault_catalog_meta': {
            'count': len(catalog),
            'source_file': 'database',
            'version': 1,
        },
    }


def classification_tree(*, include_inactive: bool = False) -> list[dict]:
    q = TicketServiceGroup.query
    if not include_inactive:
        q = q.filter_by(is_active=True)
    groups = q.order_by(TicketServiceGroup.sort_order, TicketServiceGroup.name).all()
    out = []
    for g in groups:
        cq = TicketFaultCategory.query.filter_by(service_group_id=g.id)
        if not include_inactive:
            cq = cq.filter_by(is_active=True)
        cats = cq.order_by(TicketFaultCategory.sort_order, TicketFaultCategory.name).all()
        cat_payload = []
        for c in cats:
            fq = TicketFaultCode.query.filter_by(category_id=c.id)
            if not include_inactive:
                fq = fq.filter_by(is_active=True)
            faults = fq.order_by(TicketFaultCode.sort_order, TicketFaultCode.code).all()
            cd = c.to_dict()
            cd['fault_codes'] = [f.to_dict() for f in faults]
            cat_payload.append(cd)
        gd = g.to_dict()
        gd['categories'] = cat_payload
        out.append(gd)
    return out


def dropdown_tail() -> dict:
    prios = active_priorities()
    if not prios:
        priorities = [{'value': r['value'], 'label': r['label']} for r in DEFAULT_PRIORITIES]
        sla = {r['value']: r['sla_hint'] for r in DEFAULT_PRIORITIES}
        hints = {r['value']: r['hint'] for r in DEFAULT_PRIORITIES}
    else:
        priorities = [{'value': r.value, 'label': r.label} for r in prios]
        sla = {r.value: (r.sla_hint or '') for r in prios}
        hints = {r.value: (r.hint or '') for r in prios}
    return {
        'priorities': priorities,
        'priority_sla_targets': sla,
        'priority_hints': hints,
        'hold_reasons': [r.to_dict() for r in active_hold_reasons()] or [
            {'key': r['key'], 'label': r['label']} for r in DEFAULT_HOLD_REASONS
        ],
        'cancel_reasons': [r.to_dict() for r in active_cancel_reasons()] or [
            {'key': r['key'], 'label': r['label']} for r in DEFAULT_CANCEL_REASONS
        ],
        'manpower_hours': [
            {'value': '0.25', 'label': '15 minutes'},
            {'value': '0.5', 'label': '30 minutes'},
            {'value': '0.75', 'label': '45 minutes'},
            {'value': '1', 'label': '1 hour'},
            {'value': '2', 'label': '2 hours'},
            {'value': '3', 'label': '3+ hours'},
            {'value': '4', 'label': '4 hours'},
            {'value': '6', 'label': '6 hours'},
            {'value': '8', 'label': '8 hours (full day)'},
        ],
    }


def ticket_uses_priority(value: str) -> bool:
    return Ticket.query.filter(Ticket.priority == value).first() is not None


def ticket_uses_hold_reason(key: str) -> bool:
    return Ticket.query.filter(Ticket.on_hold_reason == key).first() is not None


def ticket_uses_cancel_reason(key: str) -> bool:
    return Ticket.query.filter(Ticket.cancelled_reason == key).first() is not None


def ticket_uses_service_group(name: str) -> bool:
    return Ticket.query.filter(Ticket.service_group == name).first() is not None


def ticket_uses_category(name: str) -> bool:
    return Ticket.query.filter(Ticket.category == name).first() is not None


def ticket_uses_fault(row: TicketFaultCode) -> bool:
    pick = row.fault_pick_value()
    return Ticket.query.filter(
        db.or_(Ticket.fault_type == pick, Ticket.fault_type == row.name, Ticket.fault_type == row.code)
    ).first() is not None
