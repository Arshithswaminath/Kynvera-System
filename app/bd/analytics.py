"""
Analytics helpers for the Business Development dashboard.

Pure functions over already-fetched ORM lists (BDProject / BDFollowUp /
TicketProject). No ML: the "probability" is a simple stage-based win
likelihood applied to deal value (weighted forecast), with win rates and
the conversion funnel read straight from history.
"""
from __future__ import annotations

from datetime import datetime, timezone, date


STAGE_WIN_PROB = {
    'prospecting': 0.10,
    'qualifying': 0.25,
    'proposal': 0.50,
    'negotiation': 0.70,
    'closing': 0.90,
}
STAGE_ORDER = ['prospecting', 'qualifying', 'proposal', 'negotiation', 'closing']

_OPEN_STATUSES = {'active', 'prospect', 'proposal', 'under_renewal'}

STALL_DAYS = 30


def _as_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None
    return None


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stage(p):
    return (p.stage or '').strip().lower()


def _is_open(p):
    return (p.status or '').strip().lower() in _OPEN_STATUSES


def weighted_forecast(projects):
    """Probable revenue = Σ(deal value × that stage's win probability) over live deals."""
    raw = 0.0
    weighted = 0.0
    for p in projects:
        if not _is_open(p):
            continue
        val = float(p.value_amount or 0)
        raw += val
        weighted += val * STAGE_WIN_PROB.get(_stage(p), 0.0)
    return {
        'raw_pipeline': round(raw, 2),
        'weighted_forecast': round(weighted, 2),
        'confidence_pct': int(round(100 * weighted / raw)) if raw else 0,
    }


def conversion_funnel(projects):
    """Per-stage counts/value for live deals + overall won/lost win rate."""
    won = sum(1 for p in projects if (p.status or '').lower() == 'won')
    lost = sum(1 for p in projects if (p.status or '').lower() == 'lost')
    win_rate = int(round(100 * won / (won + lost))) if (won + lost) else 0

    stages = []
    for st in STAGE_ORDER:
        items = [p for p in projects if _stage(p) == st and _is_open(p)]
        stages.append({
            'stage': st,
            'count': len(items),
            'value': round(sum(float(p.value_amount or 0) for p in items), 2),
            'win_prob': STAGE_WIN_PROB.get(st, 0.0),
        })
    return {
        'stages': stages,
        'won': won,
        'lost': lost,
        'win_rate': win_rate,
    }


def stalled_deals(projects, limit=12):
    """Live deals gone quiet (>STALL_DAYS without update) or past expected close date."""
    now = _now()
    today = date.today()
    out = []
    for p in projects:
        if not _is_open(p):
            continue
        updated = _as_dt(p.updated_at)
        idle_days = int((now - updated).days) if updated else None
        overdue = bool(p.expected_close_date and p.expected_close_date < today)
        stale = bool(idle_days is not None and idle_days >= STALL_DAYS)
        if not (overdue or stale):
            continue
        reasons = []
        if overdue:
            reasons.append('past expected close')
        if stale:
            reasons.append(f'{idle_days}d no activity')
        out.append({
            'id': p.id,
            'name': p.name,
            'company': p.company,
            'stage': _stage(p),
            'value': round(float(p.value_amount or 0), 2),
            'idle_days': idle_days,
            'overdue': overdue,
            'reason': ', '.join(reasons),
        })
    out.sort(key=lambda d: (-(d['idle_days'] or 0), -d['value']))
    return {'count': len(out), 'rows': out[:limit]}


def outcome_loop(ticket_projects):
    """BD-win → ticketing realised value."""
    linked = [tp for tp in ticket_projects if getattr(tp, 'bd_project_id', None)]
    realised_value = round(sum(float(tp.project_value or 0) for tp in linked), 2)
    return {
        'bd_converted': len(linked),
        'bd_realised_value': realised_value,
    }
