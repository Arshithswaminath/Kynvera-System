"""
Ensure `sessions` rows exist for valid access JWTs (JTI).
Used by JWT blocklist + token_required so behavior stays consistent.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.models import Session, User, db
from common.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)


def sync_access_session_row(jti, jwt_payload):
    """
    Return the Session row for this access token JTI, creating it if missing.
    Returns None if the token cannot be backed (invalid sub, inactive user, refresh token, etc.).
    """
    if not jti or jwt_payload.get('type') == 'refresh':
        return None
    session = Session.query.filter_by(token_jti=jti).first()
    if session is not None:
        return session
    try:
        sub = jwt_payload.get('sub') or jwt_payload.get('identity')
        uid = int(sub) if sub is not None else None
    except (TypeError, ValueError):
        return None
    if uid is None:
        return None
    user = db.session.get(User, uid)
    if not user or not user.is_active:
        return None
    exp = jwt_payload.get('exp')
    exp_dt = (
        datetime.fromtimestamp(int(exp), tz=timezone.utc).replace(tzinfo=None)
        if exp
        else utc_now_naive()
    )
    try:
        row = Session(user_id=user.id, token_jti=jti, expires_at=exp_dt)
        db.session.add(row)
        db.session.commit()
        return row
    except IntegrityError:
        db.session.rollback()
        return Session.query.filter_by(token_jti=jti).first()
    except Exception as e:
        db.session.rollback()
        logger.warning("sync_access_session_row failed for jti=%s: %s", jti, e)
        return None


def mint_access_token_from_refresh_cookie():
    """
    Silently issue a fresh access token from the refresh cookie, if valid.

    Called when a full-page navigation hits an EXPIRED access token. Browsers
    navigating between server-rendered pages never run the JS refresh flow, so
    without this they get bounced to /login the moment the 1h access token
    lapses — even though the 7-day refresh cookie is still perfectly valid.

    Validation mirrors the blocklist loader: the refresh JWT must have a good
    signature, be unexpired, be of type 'refresh', map to a known non-revoked
    Session row, and belong to an active user. Returns the new access token
    string on success, or None if a silent refresh is not possible (caller
    should then fall back to redirecting to /login).
    """
    from flask import request, current_app
    from flask_jwt_extended import decode_token, create_access_token, get_jti

    cookie_name = current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token_cookie')
    refresh_cookie = request.cookies.get(cookie_name)
    if not refresh_cookie:
        return None

    try:
        # decode_token verifies signature and rejects expired tokens.
        payload = decode_token(refresh_cookie)
    except Exception:
        return None

    if payload.get('type') != 'refresh':
        return None

    jti = payload.get('jti')
    if not jti:
        return None

    # The refresh token must be a session we minted and have not revoked.
    session = Session.query.filter_by(token_jti=jti).first()
    if session is None or session.is_revoked:
        return None

    try:
        uid = int(payload.get('sub'))
    except (TypeError, ValueError):
        return None

    user = db.session.get(User, uid)
    if not user or not user.is_active:
        return None

    access_token = create_access_token(identity=str(uid))
    access_jti = get_jti(access_token)
    jwt_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES') or timedelta(hours=1)
    exp_dt = utc_now_naive() + jwt_expires
    try:
        db.session.add(Session(user_id=uid, token_jti=access_jti, expires_at=exp_dt))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    except Exception as e:
        db.session.rollback()
        logger.warning("silent refresh: failed to record session for uid=%s: %s", uid, e)
        return None

    return access_token
