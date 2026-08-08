"""Unit tests for ticket manpower/material cost-entry gating."""
from types import SimpleNamespace

from module_ticketing.routes import _cost_entry_allowed


def test_cost_entry_allowed_after_work_started():
    assert _cost_entry_allowed(SimpleNamespace(status='work_started', previous_status=None))
    assert _cost_entry_allowed(SimpleNamespace(status='work_completed', previous_status=None))


def test_cost_entry_blocked_before_work_started():
    assert not _cost_entry_allowed(SimpleNamespace(status='open', previous_status=None))
    assert not _cost_entry_allowed(SimpleNamespace(status='assigned', previous_status=None))
    assert not _cost_entry_allowed(SimpleNamespace(status='site_attended', previous_status=None))
    assert not _cost_entry_allowed(SimpleNamespace(status='resolved', previous_status=None))


def test_on_hold_does_not_unlock_pre_work_costs():
    # Holding an assigned/open ticket must not unlock manpower/materials.
    assert not _cost_entry_allowed(SimpleNamespace(status='on_hold', previous_status='assigned'))
    assert not _cost_entry_allowed(SimpleNamespace(status='on_hold', previous_status='open'))
    assert not _cost_entry_allowed(SimpleNamespace(status='on_hold', previous_status='site_attended'))
    assert not _cost_entry_allowed(SimpleNamespace(status='on_hold', previous_status=None))


def test_on_hold_allows_costs_when_previous_was_work_started():
    assert _cost_entry_allowed(SimpleNamespace(status='on_hold', previous_status='work_started'))
    assert _cost_entry_allowed(SimpleNamespace(status='on_hold', previous_status='pending_parts'))
