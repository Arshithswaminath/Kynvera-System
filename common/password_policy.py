"""
Password age / temp-password policy helpers.

- Temp passwords: soft reminder for TEMP_REMIND_DAYS (no lockout for this rule).
- Max age: PASSWORD_MAX_AGE_DAYS; warn when ≤ PASSWORD_WARN_DAYS remain;
  lock login when age > PASSWORD_MAX_AGE_DAYS (from day 66).
"""
from __future__ import annotations

from datetime import datetime, timezone

PASSWORD_MAX_AGE_DAYS = 65
PASSWORD_WARN_DAYS = 5
TEMP_REMIND_DAYS = 3


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive(dt):
    if dt is None:
        return None
    if getattr(dt, 'tzinfo', None) is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def password_reference_at(user):
    """Clock for 65-day expiry — only password_changed_at (no created_at fallback)."""
    return _as_naive(getattr(user, 'password_changed_at', None))


def temp_password_reference_at(user):
    """Clock for 3-day temp reminder — password_changed_at, else created_at."""
    ref = getattr(user, 'password_changed_at', None) or getattr(user, 'created_at', None)
    return _as_naive(ref)


def password_age_days(user, now=None):
    """Days since last password set. None if policy clock has not started."""
    ref = password_reference_at(user)
    if not ref:
        return None
    now = _as_naive(now) or _utcnow_naive()
    delta = now - ref
    return max(0, int(delta.total_seconds() // 86400))


def password_days_remaining(user, now=None):
    age = password_age_days(user, now=now)
    if age is None:
        return None
    return max(0, PASSWORD_MAX_AGE_DAYS - age)


def should_warn_password_expiry(user, now=None):
    remaining = password_days_remaining(user, now=now)
    if remaining is None:
        return False
    return 0 < remaining <= PASSWORD_WARN_DAYS


def should_lock_for_password_age(user, now=None):
    age = password_age_days(user, now=now)
    if age is None:
        return False
    return age > PASSWORD_MAX_AGE_DAYS


def should_remind_temp_password(user, now=None):
    if getattr(user, 'password_changed', True):
        return False
    ref = temp_password_reference_at(user)
    if not ref:
        return True
    now = _as_naive(now) or _utcnow_naive()
    age = max(0, int((now - ref).total_seconds() // 86400))
    return age <= TEMP_REMIND_DAYS


def password_policy_flags(user, now=None):
    """Soft flags for login /me / client payloads (no plaintext)."""
    remaining = password_days_remaining(user, now=now)
    locked = bool(getattr(user, 'password_locked', False)) or should_lock_for_password_age(user, now=now)
    ref = password_reference_at(user)
    return {
        'password_changed_at': ref.isoformat() if ref else None,
        'password_locked': locked,
        'password_days_remaining': remaining if remaining is not None else PASSWORD_MAX_AGE_DAYS,
        'password_expiry_warning': should_warn_password_expiry(user, now=now) and not locked,
        'temp_password_reminder': should_remind_temp_password(user, now=now) and not locked,
    }


def assign_user_password(user, password, *, is_temp=True):
    """
    Hash password, stamp password_changed_at, and set visibility / changed flags.

    is_temp=True  → admin-issued / default temp (store admin_visible_password, password_changed=False)
    is_temp=False → user (or explicit permanent) password (clear admin_visible_password)
    """
    user.set_password(password)
    user.password_changed_at = _utcnow_naive()
    user.password_locked = False
    if is_temp:
        user.password_changed = False
        user.admin_visible_password = password
    else:
        user.password_changed = True
        user.admin_visible_password = None
