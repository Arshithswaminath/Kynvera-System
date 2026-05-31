"""
Password helpers for self-registration and admin-created accounts.

Passwords are stored as bcrypt hashes and cannot be reversed. New self-service
signups (and admin-created accounts without an explicit password) receive a
default password that the user is expected to change on first login
(`User.password_changed = False`).
"""
from __future__ import annotations

import os

# Amaan default for self-registration. Override per environment with
# ADMIN_RESET_PASSWORD (exact) or ADMIN_RESET_PASSWORD_DEFAULT (fallback).
DEFAULT_REGISTRATION_PASSWORD = 'Amaan@123'


def get_default_registration_password():
    """Default password assigned to accounts created without an explicit one."""
    explicit = (os.environ.get('ADMIN_RESET_PASSWORD') or '').strip()
    if explicit:
        return explicit
    return os.environ.get('ADMIN_RESET_PASSWORD_DEFAULT', DEFAULT_REGISTRATION_PASSWORD)
