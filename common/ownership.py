"""Record ownership helpers for update/delete endpoints."""
from __future__ import annotations

from common.error_responses import error_response


def _user_is_elevated(user) -> bool:
    if not user:
        return False
    if getattr(user, 'role', None) == 'admin':
        return True
    # Operations "full access" managers may mutate team records
    if bool(getattr(user, 'access_operations_manage', False)):
        return True
    role = (getattr(user, 'role', None) or '').lower()
    if role in ('gm', 'general_manager'):
        return True
    if getattr(user, 'designation', None) == 'general_manager':
        return True
    return False


def user_owns_or_elevated(user, record, owner_attr: str = 'created_by_id') -> bool:
    """True if user is elevated or owns the record (by created_by_id)."""
    if not user or record is None:
        return False
    if _user_is_elevated(user):
        return True
    owner_id = getattr(record, owner_attr, None)
    if owner_id is None:
        # Legacy rows without owner — allow module-access users (caller still checks ACL)
        return True
    try:
        return int(owner_id) == int(user.id)
    except (TypeError, ValueError):
        return owner_id == user.id


def forbid_unless_owner_or_elevated(user, record, owner_attr: str = 'created_by_id'):
    """
    Return an error Flask response if user may not mutate record; else None.
    """
    if user_owns_or_elevated(user, record, owner_attr=owner_attr):
        return None
    return error_response(
        'You can only modify records you created',
        status_code=403,
        error_code='OWNERSHIP_REQUIRED',
    )
