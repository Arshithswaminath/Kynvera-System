"""
Admin-visible password helpers.

Passwords are stored as bcrypt hashes; existing hashes cannot be reversed.
We populate `User.admin_visible_password` by:
  - set_password() on create/reset/change
  - successful login (captures the password the user typed)
  - backfill: match known defaults/secrets against the hash (one-time / startup)
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def password_backfill_candidates():
    """Plaintext candidates to try against password_hash (env + app defaults)."""
    seen = set()
    out = []

    def add(value):
        v = (value or '').strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)

    for key in (
        'ADMIN_RESET_PASSWORD',
        'ADMIN_RESET_PASSWORD_DEFAULT',
        'SEED_TEAM_PASSWORD',
        'DEFAULT_ADMIN_PASSWORD',
        'HR_MANAGER_PASSWORD',
        'PROCUREMENT_MANAGER_PASSWORD',
    ):
        add(os.environ.get(key))

    add(os.environ.get('ADMIN_RESET_PASSWORD_DEFAULT', 'ChangeMeNow!@#'))
    add('DemoTech2026!')
    add('Injaaz@123')
    add('Admin@123')
    add('Arshith&Taha@2026')
    return out


def get_default_registration_password():
    """Default password for self-registration and admin-created accounts without an explicit password."""
    explicit = (os.environ.get('ADMIN_RESET_PASSWORD') or '').strip()
    if explicit:
        return explicit
    return os.environ.get('ADMIN_RESET_PASSWORD_DEFAULT', 'ChangeMeNow!@#')


def capture_admin_visible_password(user, plaintext: str) -> None:
    """Store plaintext for admin Manage profile when we know it (e.g. login)."""
    if not plaintext or not hasattr(user, 'admin_visible_password'):
        return
    user.admin_visible_password = plaintext


def backfill_admin_visible_passwords():
    """
    For users missing admin_visible_password, try known defaults against bcrypt hash.
    Returns counts: updated, skipped (no candidate matched).
    """
    from app.models import db, User

    if not hasattr(User, 'admin_visible_password'):
        return {'updated': 0, 'skipped': 0}

    candidates = password_backfill_candidates()
    updated = 0
    skipped = 0

    rows = User.query.filter(
        (User.admin_visible_password.is_(None)) | (User.admin_visible_password == '')
    ).all()

    for user in rows:
        matched = False
        for pw in candidates:
            try:
                if user.check_password(pw):
                    user.admin_visible_password = pw
                    updated += 1
                    matched = True
                    break
            except Exception:
                continue
        if not matched:
            skipped += 1

    if updated:
        db.session.commit()
        logger.info('Backfilled admin_visible_password for %s user(s)', updated)

    return {'updated': updated, 'skipped': skipped}
