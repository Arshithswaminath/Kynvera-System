"""
Timed unlock tokens for editing protected admin accounts.

Issued after the signed-in admin verifies their protect PIN. Clients send the
token as X-Admin-Protect-Unlock on protected mutations.
"""
from __future__ import annotations

import re
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

UNLOCK_MAX_AGE_SECONDS = 1800  # 30 minutes
UNLOCK_HEADER = 'X-Admin-Protect-Unlock'
PIN_RE = re.compile(r'^\d{4,8}$')
_SALT = 'admin-protect-unlock'


def validate_protect_pin_format(pin):
    """Return (ok, error_message)."""
    if not pin or not isinstance(pin, str):
        return False, 'PIN is required'
    pin = pin.strip()
    if not PIN_RE.match(pin):
        return False, 'PIN must be 4–8 digits'
    return True, ''


def _serializer(secret_key):
    return URLSafeTimedSerializer(secret_key, salt=_SALT)


def issue_unlock_token(secret_key, admin_id, *, max_age=UNLOCK_MAX_AGE_SECONDS):
    """Return (token, expires_in_seconds)."""
    token = _serializer(secret_key).dumps({'admin_id': str(admin_id)})
    return token, int(max_age)


def verify_unlock_token(secret_key, token, admin_id, *, max_age=UNLOCK_MAX_AGE_SECONDS):
    """True when token is valid, unexpired, and matches admin_id."""
    if not token or admin_id is None:
        return False
    try:
        payload = _serializer(secret_key).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return str(payload.get('admin_id')) == str(admin_id)
