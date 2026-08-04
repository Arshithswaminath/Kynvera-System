"""
Ensure the default admin account exists / is aligned.

Used at app startup so production (Postgres) can be fixed by redeploy
without Render Shell access.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_USERNAME = "Kynvera"
DEFAULT_ADMIN_EMAIL = "admin@injaaz.com"
DEFAULT_ADMIN_FULL_NAME = "System Administrator"
DEFAULT_ADMIN_PASSWORD_FALLBACK = "Arshith&Taha@2026"


def _desired_password() -> str:
    return os.environ.get("DEFAULT_ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD_FALLBACK


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def ensure_default_admin() -> None:
    """Create or sync the primary admin user used for platform login."""
    from app.models import User, db

    desired_username = (
        os.environ.get("DEFAULT_ADMIN_USERNAME") or DEFAULT_ADMIN_USERNAME
    ).strip() or DEFAULT_ADMIN_USERNAME
    desired_password = _desired_password()
    # Default ON so a redeploy can repair production without Render Shell.
    # After login works, set SYNC_DEFAULT_ADMIN=false in the host env to stop
    # resetting the admin password on every restart.
    force_sync = _truthy("SYNC_DEFAULT_ADMIN", "true")

    admin = (
        User.query.filter_by(role="admin").order_by(User.id.asc()).first()
        or User.query.filter_by(username=desired_username).first()
        or User.query.filter_by(username="admin").first()
    )

    if not admin:
        logger.info("Creating default admin user (%s)...", desired_username)
        admin = User(
            username=desired_username,
            email=DEFAULT_ADMIN_EMAIL,
            full_name=DEFAULT_ADMIN_FULL_NAME,
            role="admin",
            is_active=True,
            access_hvac=True,
            access_civil=True,
            access_cleaning=True,
            password_changed=True,
            admin_visible_password=desired_password,
            password_locked=False,
        )
        admin.set_password(desired_password)
        db.session.add(admin)
        db.session.commit()
        logger.info("✅ Default admin user created (username: %s)", desired_username)
        return

    username_l = (admin.username or "").strip().lower()
    # Always migrate legacy "admin"; otherwise only when SYNC_DEFAULT_ADMIN is enabled.
    should_sync = force_sync or username_l == "admin"
    if not should_sync:
        logger.info("✅ Admin user already exists (username: %s)", admin.username)
        return

    password_ok = False
    try:
        password_ok = admin.check_password(desired_password)
    except Exception:
        password_ok = False

    needs_update = (
        admin.username != desired_username
        or not password_ok
        or not admin.is_active
        or bool(getattr(admin, "password_locked", False))
    )
    if not needs_update:
        logger.info("✅ Admin user already exists")
        return

    conflict = (
        User.query.filter(User.username == desired_username, User.id != admin.id).first()
    )
    if conflict:
        logger.warning(
            "Cannot rename admin to %r — username already taken by id=%s; "
            "updating password on existing admin id=%s instead",
            desired_username,
            conflict.id,
            admin.id,
        )
        target = admin
    else:
        target = admin
        target.username = desired_username

    target.set_password(desired_password)
    target.password_changed = True
    target.admin_visible_password = desired_password
    target.password_locked = False
    target.is_active = True
    if not target.role:
        target.role = "admin"
    db.session.commit()
    logger.warning(
        "✅ Synced default admin credentials (username: %s). "
        "Set SYNC_DEFAULT_ADMIN=false after you can log in.",
        target.username,
    )
