"""
Analytics engine for the ticketing module.

Pure, dependency-free computations over already-visibility-filtered Ticket rows
(plus their status-change notes and manpower logs). No ML and no new columns:
the "probability" is empirical — derived from the resolution-time distribution of
the team's own historical tickets.

Mirrors the report_builders.py separation of concerns: routes fetch + scope the
data, this module crunches the numbers, the template renders them.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone


# SLA targets in hours, by priority. Hard-coded for v1; a later iteration can make
# these configurable / auto-calibrated from history (see plan "Notes / future").
SLA_TARGET_HOURS = {
    'critical': 4,
    'high': 24,
    'medium': 72,
    'low': 168,
}
DEFAULT_SLA_HOURS = 72

# Canonical working stages, in lifecycle order, used for the stage-duration funnel.
# Terminal states (closed/cancelled/resolved) are intentionally excluded — we only
# measure time a ticket spends *waiting to be finished*.
STAGE_ORDER = [
    'open', 'assigned', 'site_attended', 'work_started',
    'work_completed', 'verification', 'pending_gm_approval', 'pending_finance',
]

# Legacy → canonical, so historical tickets fold into the same buckets.
_LEGACY_STAGE = {
    'in_progress': 'work_started',
    'pending_parts': 'work_started',
    'pending_supervisor': 'open',
    'pending_verification': 'verification',
}

_TERMINAL = {'closed', 'cancelled', 'resolved'}

_STATUS_CHANGE_RE = re.compile(r'from\s+"(?P<from>[^"]*)"\s+to\s+"(?P<to>[^"]*)"', re.I)


# ---------------------------------------------------------------------------
# Small numeric / datetime helpers
# ---------------------------------------------------------------------------

def _as_dt(value):
    """Coerce a stored timestamp (datetime or ISO string) to a naive UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None
    return None


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hours_between(a, b):
    a, b = _as_dt(a), _as_dt(b)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


def _percentile(sorted_vals, pct):
    """Linear-interpolated percentile of an already-sorted list."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _is_closed(t):
    return t.status in ('closed', 'resolved') and t.closed_at is not None


# ---------------------------------------------------------------------------
# 1. Resolution-time statistics
# ---------------------------------------------------------------------------

def compute_resolution_stats(tickets):
    """Median / p90 / avg resolution time, overall and by priority / service group."""

    def _summary(rows):
        hrs = sorted(
            h for h in (_hours_between(t.created_at, t.closed_at) for t in rows)
            if h is not None and h >= 0
        )
        if not hrs:
            return {'count': 0, 'median_days': None, 'p90_days': None, 'avg_days': None}
        return {
            'count': len(hrs),
            'median_days': round(_percentile(hrs, 50) / 24, 1),
            'p90_days': round(_percentile(hrs, 90) / 24, 1),
            'avg_days': round((sum(hrs) / len(hrs)) / 24, 1),
        }

    closed = [t for t in tickets if _is_closed(t)]
    by_priority = {
        p: _summary([t for t in closed if (t.priority or '').lower() == p])
        for p in ('critical', 'high', 'medium', 'low')
    }
    by_service = {
        sg: _summary([t for t in closed if (t.service_group or '—') == sg])
        for sg in sorted({(t.service_group or '—') for t in closed})
    }
    return {
        'overall': _summary(closed),
        'by_priority': by_priority,
        'by_service_group': by_service,
    }


# ---------------------------------------------------------------------------
# 2. Stage durations / bottleneck (reconstructed from status-change notes)
# ---------------------------------------------------------------------------

def compute_stage_durations(tickets, status_notes):
    """Average time-in-stage (hours), reconstructed from status-change notes.

    For each ticket we order its status_change notes by time; the gap between
    consecutive transitions is how long the ticket sat in the stage it was leaving.
    Durations are bucketed by canonical stage and averaged across all tickets, so
    the slowest stage (the bottleneck) is visible without any new schema.
    """
    notes_by_ticket = {}
    for n in status_notes:
        notes_by_ticket.setdefault(n.ticket_id, []).append(n)

    totals = {}  # stage -> [sum_hours, count]
    for t in tickets:
        notes = sorted(
            notes_by_ticket.get(t.id, []),
            key=lambda n: _as_dt(n.created_at) or datetime.min,
        )
        if not notes:
            continue

        m0 = _STATUS_CHANGE_RE.search(notes[0].content or '')
        cur_status = (m0.group('from') if m0 else 'open') or 'open'
        cur_start = _as_dt(t.created_at) or _as_dt(notes[0].created_at)

        for n in notes:
            ended = _as_dt(n.created_at)
            if ended and cur_start and cur_status not in _TERMINAL:
                stage = _LEGACY_STAGE.get(cur_status, cur_status)
                if stage in STAGE_ORDER:
                    dur = (ended - cur_start).total_seconds() / 3600.0
                    if dur >= 0:
                        bucket = totals.setdefault(stage, [0.0, 0])
                        bucket[0] += dur
                        bucket[1] += 1
            m = _STATUS_CHANGE_RE.search(n.content or '')
            cur_status = (m.group('to') if m else cur_status) or cur_status
            cur_start = ended

    stages = []
    for stage in STAGE_ORDER:
        s = totals.get(stage)
        stages.append({
            'stage': stage,
            'avg_hours': round(s[0] / s[1], 1) if (s and s[1]) else None,
            'samples': s[1] if s else 0,
        })
    ranked = [s for s in stages if s['avg_hours'] is not None]
    bottleneck = max(ranked, key=lambda s: s['avg_hours'])['stage'] if ranked else None
    return {'stages': stages, 'bottleneck': bottleneck}


# ---------------------------------------------------------------------------
# 3. SLA + empirical breach-risk board
# ---------------------------------------------------------------------------

def compute_breach_risk(open_tickets, closed_history):
    """For each open ticket: SLA target, current age, and empirical breach probability.

    The probability is conditional and explainable: of past same-priority tickets
    that were *still open at this ticket's current age*, what fraction went on to
    exceed the SLA target. A ticket already past its target counts as breached (1.0).
    Buckets: breached → over SLA · at_risk → breach probability >= 0.5 · on_track.
    """
    hist = {}
    for t in closed_history:
        if not _is_closed(t):
            continue
        h = _hours_between(t.created_at, t.closed_at)
        if h is not None and h >= 0:
            hist.setdefault((t.priority or 'medium').lower(), []).append(h)
    for k in hist:
        hist[k].sort()

    now = _now()
    rows = []
    counts = {'breached': 0, 'at_risk': 0, 'on_track': 0}

    for t in open_tickets:
        prio = (t.priority or 'medium').lower()
        target = SLA_TARGET_HOURS.get(prio, DEFAULT_SLA_HOURS)
        created = _as_dt(t.created_at)
        age = (now - created).total_seconds() / 3600.0 if created else 0.0
        samples = hist.get(prio, [])

        if age >= target:
            tier, breach_prob = 'breached', 1.0
        else:
            still_open = [h for h in samples if h > age]
            if still_open:
                breach_prob = sum(1 for h in still_open if h > target) / len(still_open)
            elif samples:
                # Already older than every comparable ticket in history → outlier.
                breach_prob = 0.95
            else:
                # No history for this priority — fall back to budget consumed.
                breach_prob = min(0.99, age / target) if target else 0.0
            tier = 'at_risk' if breach_prob >= 0.5 else 'on_track'

        counts[tier] += 1
        rows.append({
            'ticket_id': t.ticket_id,
            'title': t.title,
            'priority': prio,
            'status': t.status,
            'age_hours': round(age, 1),
            'target_hours': target,
            'breach_prob': round(breach_prob, 2),
            'tier': tier,
        })

    tier_rank = {'breached': 0, 'at_risk': 1, 'on_track': 2}
    rows.sort(key=lambda r: (tier_rank[r['tier']], -r['breach_prob'], -r['age_hours']))
    return {'rows': rows, 'counts': counts}


# ---------------------------------------------------------------------------
# 4. Team performance
# ---------------------------------------------------------------------------

def compute_team_perf(tickets, manpower, user_lookup):
    """Per-person workload from supervisor/technician assignment + logged hours."""
    hours_by_user = {}
    for m in manpower:
        if m.worker_user_id:
            hours_by_user[m.worker_user_id] = (
                hours_by_user.get(m.worker_user_id, 0.0) + float(m.hours or 0)
            )

    agg = {}

    def _bucket(uid, role):
        if not uid:
            return None
        if uid not in agg:
            u = user_lookup.get(uid)
            agg[uid] = {
                'name': (u.full_name or u.username) if u else f'User {uid}',
                'roles': set(),
                'handled': 0,
                'completed': 0,
                'close_hours': [],
                'hours': hours_by_user.get(uid, 0.0),
            }
        agg[uid]['roles'].add(role)
        return agg[uid]

    for t in tickets:
        for uid, role in ((t.supervisor_id, 'supervisor'), (t.technician_id, 'technician')):
            b = _bucket(uid, role)
            if b is None:
                continue
            b['handled'] += 1
            if _is_closed(t):
                b['completed'] += 1
                h = _hours_between(t.created_at, t.closed_at)
                if h is not None and h >= 0:
                    b['close_hours'].append(h)

    rows = []
    for b in agg.values():
        ch = b['close_hours']
        rows.append({
            'name': b['name'],
            'roles': ', '.join(sorted(b['roles'])),
            'handled': b['handled'],
            'completed': b['completed'],
            'completion_pct': int(round(100 * b['completed'] / b['handled'])) if b['handled'] else 0,
            'avg_close_days': round((sum(ch) / len(ch)) / 24, 1) if ch else None,
            'hours': round(b['hours'], 1),
        })
    rows.sort(key=lambda r: (-r['handled'], r['name']))
    return rows


# ---------------------------------------------------------------------------
# 5. Fault-type Pareto
# ---------------------------------------------------------------------------

def compute_fault_pareto(tickets, include_cost=False, top_n=12):
    """Counts (and optional cost) grouped by fault type, sorted descending."""
    agg = {}
    for t in tickets:
        key = (t.fault_type or t.category or '—').strip() or '—'
        a = agg.setdefault(key, {'fault': key, 'count': 0, 'cost': 0.0})
        a['count'] += 1
        if include_cost:
            a['cost'] += float(t.selling_price or t.total_cost or 0)

    rows = sorted(agg.values(), key=lambda r: -r['count'])
    total = sum(r['count'] for r in rows) or 1
    cum = 0
    for r in rows:
        cum += r['count']
        r['pct'] = round(100 * r['count'] / total, 1)
        r['cum_pct'] = round(100 * cum / total, 1)
        r['cost'] = round(r['cost'], 2)
    return {'rows': rows[:top_n], 'total': total}
