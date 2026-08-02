"""
Password helpers for self-registration and admin-created accounts.

Passwords are stored as bcrypt hashes and cannot be reversed. New self-service
signups (and admin-created accounts without an explicit password) receive a
per-user random temporary password that the user must change on first login
(`User.password_changed = False`). Prefer delivering it via welcome email —
never return it in API JSON responses.
"""
from __future__ import annotations

import secrets
import string


def generate_temporary_password(length: int = 14) -> str:
    """
    Generate a random password that satisfies app strength rules
    (upper, lower, digit; length >= 8).
    """
    length = max(12, int(length or 14))
    alphabet = string.ascii_letters + string.digits
    # Guarantee complexity, then fill the rest randomly.
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
    ]
    rest = [secrets.choice(alphabet) for _ in range(length - len(required))]
    chars = required + rest
    # Fisher–Yates via secrets
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return ''.join(chars)


def get_default_registration_password():
    """
    Temporary password for accounts created without an explicit one.

    Always returns a fresh random value (not a shared static default).
    """
    return generate_temporary_password()
