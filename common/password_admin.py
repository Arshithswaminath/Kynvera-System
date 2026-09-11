"""
Password helpers for admin-created accounts and first-time login.

Passwords are stored only as bcrypt hashes. We never persist plaintext.
Admin reset / registration issues a one-time temporary password in the API
response and (when mail is configured) by email; the user must change it.
"""
from __future__ import annotations

import logging
import os
import secrets
import string

logger = logging.getLogger(__name__)


def generate_temporary_password(length: int = 16) -> str:
    """Random password that satisfies validate_password (8+, upper, lower, digit)."""
    if length < 12:
        length = 12
    alphabet = string.ascii_letters + string.digits
    while True:
        chars = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits),
        ]
        chars.extend(secrets.choice(alphabet) for _ in range(length - 3))
        secrets.SystemRandom().shuffle(chars)
        return ''.join(chars)


def require_env_password(name: str = 'DEFAULT_ADMIN_PASSWORD') -> str:
    """Return a required password env var, or raise. Never falls back to a source default."""
    value = (os.environ.get(name) or '').strip()
    if not value:
        raise RuntimeError(
            f'{name} must be set. Refusing to use a password embedded in source.'
        )
    return value


def get_default_registration_password():
    """One-time password for self-registration when the client does not supply one."""
    explicit = (os.environ.get('ADMIN_RESET_PASSWORD') or '').strip()
    if explicit:
        return explicit
    return generate_temporary_password()


def capture_admin_visible_password(user, plaintext: str) -> None:
    """No-op keeper for call sites. Plaintext is never stored."""
    if user is not None and hasattr(user, 'admin_visible_password'):
        user.admin_visible_password = None


def wipe_admin_visible_passwords():
    """Clear any leftover plaintext copies. Returns how many rows were cleared."""
    from app.models import db, User

    if not hasattr(User, 'admin_visible_password'):
        return {'cleared': 0}

    rows = User.query.filter(
        User.admin_visible_password.isnot(None),
        User.admin_visible_password != '',
    ).all()
    for user in rows:
        user.admin_visible_password = None
    if rows:
        db.session.commit()
        logger.info('Cleared leftover admin_visible_password for %s user(s)', len(rows))
    return {'cleared': len(rows)}


def backfill_admin_visible_passwords():
    """Legacy name: wipe plaintext copies instead of filling them from known defaults."""
    stats = wipe_admin_visible_passwords()
    return {'updated': 0, 'skipped': 0, 'cleared': stats.get('cleared', 0)}
