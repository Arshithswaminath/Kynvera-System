"""Priority SLA helpers for service tickets.

Client mapping (kickoff):
  P1 → high     → 24 hours
  P2 → medium   → 3 days (72 hours)
  P3 → low      → 1 week (168 hours)
  critical      → 4 hours (emergency; kept from analytics)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

SLA_TARGET_HOURS = {
    'critical': 4,
    'high': 24,
    'medium': 72,
    'low': 168,
}
DEFAULT_SLA_HOURS = 72

_TERMINAL = frozenset({'closed', 'cancelled', 'resolved'})


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sla_hours_for_priority(priority: Optional[str]) -> int:
    key = (priority or 'medium').strip().lower()
    return SLA_TARGET_HOURS.get(key, DEFAULT_SLA_HOURS)


def compute_sla_due_at(
    priority: Optional[str],
    *,
    from_dt: Optional[datetime] = None,
) -> datetime:
    base = from_dt or _utcnow_naive()
    if base.tzinfo is not None:
        base = base.astimezone(timezone.utc).replace(tzinfo=None)
    return base + timedelta(hours=sla_hours_for_priority(priority))


def sla_state_for_ticket(ticket) -> str:
    """Return on_track | due_soon | breached | n_a for UI badges."""
    status = (getattr(ticket, 'status', None) or '').lower()
    if status in _TERMINAL:
        if getattr(ticket, 'sla_breached_at', None):
            return 'breached'
        return 'n_a'
    due = getattr(ticket, 'sla_due_at', None)
    if not due:
        return 'n_a'
    if getattr(ticket, 'sla_breached_at', None) or _utcnow_naive() > due:
        return 'breached'
    remaining = due - _utcnow_naive()
    if remaining <= timedelta(hours=4):
        return 'due_soon'
    return 'on_track'


def is_ticket_open_for_sla(ticket) -> bool:
    status = (getattr(ticket, 'status', None) or '').lower()
    return status not in _TERMINAL and bool(getattr(ticket, 'sla_due_at', None))
