"""
Startup/bootstrap security helpers.

Keeps default-admin creation and secret validation out of ad-hoc scripts so
production cannot silently ship with well-known credentials or JWT keys.
"""
from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger(__name__)

# Values that must never be used as signing keys in production.
INSECURE_SECRET_DEFAULTS = frozenset({
    '',
    'change-me-in-production',
    'dev-secret-change-in-production',
    'change-me-jwt-secret',
    'secret',
    'jwt-secret',
})


def is_production_env(flask_env: str | None = None) -> bool:
    """True for explicit production OR known hosted PaaS signals (e.g. Render)."""
    env = (flask_env if flask_env is not None else os.environ.get('FLASK_ENV', 'development'))
    if (env or '').strip().lower() == 'production':
        return True
    # Render sets RENDER=true even when operators forget FLASK_ENV=production.
    if (os.environ.get('RENDER') or '').strip().lower() in ('1', 'true', 'yes'):
        return True
    return False


def resolve_bootstrap_admin_password(flask_env: str | None = None) -> tuple[str, bool]:
    """
    Resolve the password used when auto-creating the first admin user.

    Returns (password, was_generated).
    - Always prefer DEFAULT_ADMIN_PASSWORD from the environment.
    - Production: refuse to create an admin without that env var (no hardcoded fallback).
    - Non-production: generate a one-time random password when unset.
    """
    explicit = (os.environ.get('DEFAULT_ADMIN_PASSWORD') or '').strip()
    if explicit:
        return explicit, False

    if is_production_env(flask_env):
        raise RuntimeError(
            'DEFAULT_ADMIN_PASSWORD must be set to create the initial admin user in production. '
            'Refusing to bootstrap with a well-known password.'
        )

    generated = secrets.token_urlsafe(18)
    logger.critical(
        'DEFAULT_ADMIN_PASSWORD unset — generated a one-time admin password for this bootstrap. '
        'Store it securely and change it after first login. password=%s',
        generated,
    )
    return generated, True


def assert_secure_app_secrets(secret_key: str | None, jwt_secret_key: str | None, flask_env: str | None = None) -> None:
    """
    Fail closed in production when Flask/JWT signing secrets are still placeholders.
    In other environments, log a warning so local setups remain usable.
    """
    sk = (secret_key or '').strip()
    jk = (jwt_secret_key or '').strip()
    bad_secret = sk in INSECURE_SECRET_DEFAULTS
    bad_jwt = jk in INSECURE_SECRET_DEFAULTS

    if not bad_secret and not bad_jwt:
        return

    detail = []
    if bad_secret:
        detail.append('SECRET_KEY')
    if bad_jwt:
        detail.append('JWT_SECRET_KEY')
    joined = ' and '.join(detail)

    if is_production_env(flask_env):
        raise RuntimeError(
            f'{joined} is set to an insecure default. Set strong unique values before starting in production.'
        )

    logger.warning(
        '⚠️  Using insecure default %s! Set strong values in the environment before deploying.',
        joined,
    )
