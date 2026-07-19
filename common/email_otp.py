"""
Reusable email OTP for protect-PIN reset and self-service password reset.

Codes are hashed in the DB; a successful verify issues a short-lived signed
reset grant token used to authorize the actual PIN/password change.
"""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.models import EmailOtp, User, bcrypt, db
from common.datetime_utils import utc_now_naive
from common.email_service import is_email_configured, send_otp_email

logger = logging.getLogger(__name__)

PURPOSE_PROTECT_PIN_RESET = 'protect_pin_reset'
PURPOSE_PASSWORD_RESET = 'password_reset'
VALID_PURPOSES = frozenset({PURPOSE_PROTECT_PIN_RESET, PURPOSE_PASSWORD_RESET})

OTP_TTL_SECONDS = 600  # 10 minutes
OTP_LENGTH = 6
MAX_VERIFY_ATTEMPTS = 5
MAX_SENDS_PER_WINDOW = 3
SEND_WINDOW_SECONDS = 900  # 15 minutes
RESET_GRANT_MAX_AGE = 600  # 10 minutes after OTP verified
_GRANT_SALT = 'email-otp-reset-grant'

PURPOSE_LABELS = {
    PURPOSE_PROTECT_PIN_RESET: 'Protect PIN reset',
    PURPOSE_PASSWORD_RESET: 'Password reset',
}


class EmailOtpError(Exception):
    """Raised for expected OTP failures (safe to show message to client)."""

    def __init__(self, message, *, status_code=400, error_code='OTP_ERROR'):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


def mask_email(email: str | None) -> str:
    """Mask an email for UI display (j***@example.com)."""
    if not email or '@' not in email:
        return '***'
    local, _, domain = email.strip().partition('@')
    if not local:
        return f'***@{domain}'
    if len(local) == 1:
        shown = local[0]
    else:
        shown = local[0] + '***'
    return f'{shown}@{domain}'


def _hash_code(code: str) -> str:
    return bcrypt.generate_password_hash(code).decode('utf-8')


def _check_code(code_hash: str, code: str) -> bool:
    try:
        return bcrypt.check_password_hash(code_hash, code)
    except Exception:
        return False


def _generate_code() -> str:
    # 6-digit numeric, zero-padded
    return f'{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}'


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=_GRANT_SALT)


def issue_reset_grant(secret_key: str, user_id, purpose: str, *, max_age=RESET_GRANT_MAX_AGE):
    """Return (token, expires_in_seconds) after OTP was verified."""
    token = _serializer(secret_key).dumps({
        'user_id': str(user_id),
        'purpose': purpose,
    })
    return token, int(max_age)


def verify_reset_grant(secret_key: str, token: str, purpose: str, *, max_age=RESET_GRANT_MAX_AGE):
    """Return user_id (int) when grant is valid for purpose, else None."""
    if not token or purpose not in VALID_PURPOSES:
        return None
    try:
        payload = _serializer(secret_key).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if str(payload.get('purpose') or '') != purpose:
        return None
    try:
        return int(payload.get('user_id'))
    except (TypeError, ValueError):
        return None


def _invalidate_active_otps(user_id: int, purpose: str) -> None:
    now = utc_now_naive()
    rows = (
        EmailOtp.query.filter(
            EmailOtp.user_id == user_id,
            EmailOtp.purpose == purpose,
            EmailOtp.consumed_at.is_(None),
            EmailOtp.expires_at > now,
        ).all()
    )
    for row in rows:
        row.consumed_at = now


def _send_count_in_window(user_id: int, purpose: str) -> int:
    since = utc_now_naive() - timedelta(seconds=SEND_WINDOW_SECONDS)
    return (
        EmailOtp.query.filter(
            EmailOtp.user_id == user_id,
            EmailOtp.purpose == purpose,
            EmailOtp.created_at >= since,
        ).count()
    )


def request_otp(user: User, purpose: str, *, ip: str | None = None) -> dict:
    """
    Create and email a new OTP for user+purpose.

    Returns dict: sent, masked_email, expires_in.
    Raises EmailOtpError on rate limit / mail / validation failures.
    """
    if not user or not getattr(user, 'id', None):
        raise EmailOtpError('User not found', status_code=404, error_code='NOT_FOUND')
    if purpose not in VALID_PURPOSES:
        raise EmailOtpError('Invalid OTP purpose', status_code=400, error_code='VALIDATION_ERROR')
    if not getattr(user, 'is_active', True):
        raise EmailOtpError('Account is inactive', status_code=403, error_code='INACTIVE')

    email = (getattr(user, 'email', None) or '').strip()
    if not email:
        raise EmailOtpError(
            'No email address is on file for this account.',
            status_code=400,
            error_code='NO_EMAIL',
        )

    if not is_email_configured():
        raise EmailOtpError(
            'Email is not configured on this server. Contact an administrator.',
            status_code=503,
            error_code='EMAIL_NOT_CONFIGURED',
        )

    if _send_count_in_window(user.id, purpose) >= MAX_SENDS_PER_WINDOW:
        raise EmailOtpError(
            'Too many codes requested. Please wait a few minutes and try again.',
            status_code=429,
            error_code='RATE_LIMITED',
        )

    code = _generate_code()
    now = utc_now_naive()
    _invalidate_active_otps(user.id, purpose)

    row = EmailOtp(
        user_id=user.id,
        purpose=purpose,
        code_hash=_hash_code(code),
        expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
        attempts=0,
        consumed_at=None,
        request_ip=(ip or None),
        created_at=now,
    )
    db.session.add(row)
    db.session.flush()

    display_name = (user.full_name or user.username or 'User').strip()
    purpose_label = PURPOSE_LABELS.get(purpose, 'Verification')
    sent = send_otp_email(
        email,
        display_name,
        code,
        purpose_label,
        expires_minutes=OTP_TTL_SECONDS // 60,
    )
    if not sent:
        db.session.rollback()
        raise EmailOtpError(
            'Failed to send the verification email. Please try again shortly.',
            status_code=502,
            error_code='EMAIL_SEND_FAILED',
        )

    db.session.commit()
    logger.info(
        'email_otp sent purpose=%s user_id=%s masked=%s',
        purpose,
        user.id,
        mask_email(email),
    )
    return {
        'sent': True,
        'masked_email': mask_email(email),
        'expires_in': OTP_TTL_SECONDS,
    }


def verify_otp(user: User, purpose: str, code: str) -> dict:
    """
    Verify OTP; on success consume it and return reset_token + expires_in.
    """
    if not user or not getattr(user, 'id', None):
        raise EmailOtpError('User not found', status_code=404, error_code='NOT_FOUND')
    if purpose not in VALID_PURPOSES:
        raise EmailOtpError('Invalid OTP purpose', status_code=400, error_code='VALIDATION_ERROR')

    code = (code or '').strip()
    if not code.isdigit() or len(code) != OTP_LENGTH:
        raise EmailOtpError(
            f'Enter the {OTP_LENGTH}-digit code from your email.',
            status_code=400,
            error_code='VALIDATION_ERROR',
        )

    now = utc_now_naive()
    row = (
        EmailOtp.query.filter(
            EmailOtp.user_id == user.id,
            EmailOtp.purpose == purpose,
            EmailOtp.consumed_at.is_(None),
        )
        .order_by(EmailOtp.created_at.desc())
        .first()
    )
    if not row or row.expires_at <= now:
        raise EmailOtpError(
            'Code expired or not found. Request a new code.',
            status_code=400,
            error_code='OTP_EXPIRED',
        )

    if (row.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
        row.consumed_at = now
        db.session.commit()
        raise EmailOtpError(
            'Too many incorrect attempts. Request a new code.',
            status_code=429,
            error_code='OTP_LOCKED',
        )

    if not _check_code(row.code_hash, code):
        row.attempts = int(row.attempts or 0) + 1
        db.session.commit()
        remaining = MAX_VERIFY_ATTEMPTS - row.attempts
        raise EmailOtpError(
            f'Incorrect code. {remaining} attempt(s) remaining.'
            if remaining > 0
            else 'Incorrect code. Request a new code.',
            status_code=403,
            error_code='OTP_INVALID',
        )

    row.consumed_at = now
    db.session.commit()

    secret = current_app.config.get('SECRET_KEY') or current_app.config.get('JWT_SECRET_KEY')
    if not secret:
        raise EmailOtpError('Server misconfigured', status_code=500, error_code='CONFIG_ERROR')

    token, expires_in = issue_reset_grant(secret, user.id, purpose)
    return {
        'reset_token': token,
        'expires_in': expires_in,
    }


def resolve_user_for_password_reset(identifier: str) -> User | None:
    """Find active user by username or email (case-insensitive)."""
    ident = (identifier or '').strip()
    if not ident:
        return None
    user = User.query.filter(User.username.ilike(ident)).first()
    if not user:
        user = User.query.filter(User.email.ilike(ident)).first()
    if user and getattr(user, 'is_active', True):
        return user
    return None
