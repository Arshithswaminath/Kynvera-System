"""
Shared test-data factories.

Extracted from the hand-rolled `_make_user`/`_make_ticket`-style helpers that
were duplicated across individual test files. New test files should prefer
these over redefining their own; existing files are migrated opportunistically
when touched, not in a big-bang rewrite.

All factories must be called inside an `app.app_context()` (or with a request
context that implies one) since they touch `db.session`.
"""
from datetime import datetime, timezone

from app.models import (
    db, User, TicketProject, TicketProperty, TicketZone,
    TicketSubZone, TicketBaseUnit,
)

_COUNTER = {'n': 0}


def _unique(prefix):
    _COUNTER['n'] += 1
    return f'{prefix}{_COUNTER["n"]}'


def make_user(role='user', designation=None, password='TestPass123', **overrides):
    """Create and commit a User row. Caller owns cleanup (delete via db.session)."""
    uname = overrides.pop('username', None) or _unique('user')
    email = overrides.pop('email', None) or f'{uname}@example.com'
    defaults = dict(
        username=uname,
        email=email,
        full_name=overrides.pop('full_name', uname),
        role=role,
        designation=designation,
        is_active=True,
        password_changed=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, password


def make_admin(**overrides):
    return make_user(role='admin', **overrides)


def make_location_hierarchy(project_name=None, property_name=None,
                             zone_name=None, sub_zone_name=None,
                             base_unit_name=None):
    """Create a full Project -> Property -> Zone -> SubZone -> BaseUnit chain."""
    project = TicketProject(name=project_name or _unique('Project '))
    db.session.add(project)
    db.session.flush()

    prop = TicketProperty(name=property_name or _unique('Property '), project_id=project.id,
                           is_active=True)
    db.session.add(prop)
    db.session.flush()

    zone = TicketZone(name=zone_name or _unique('Zone '), property_id=prop.id)
    db.session.add(zone)
    db.session.flush()

    sub_zone = TicketSubZone(name=sub_zone_name or _unique('SubZone '), zone_id=zone.id)
    db.session.add(sub_zone)
    db.session.flush()

    base_unit = TicketBaseUnit(name=base_unit_name or _unique('Unit '), sub_zone_id=sub_zone.id)
    db.session.add(base_unit)
    db.session.commit()

    return {
        'project': project,
        'property': prop,
        'zone': zone,
        'sub_zone': sub_zone,
        'base_unit': base_unit,
    }


def utcnow():
    return datetime.now(timezone.utc)
