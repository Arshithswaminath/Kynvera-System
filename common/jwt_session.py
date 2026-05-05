"""
Ensure `sessions` rows exist for valid access JWTs (JTI).
Used by JWT blocklist + token_required so behavior stays consistent.
"""
import logging
from datetime import datetime, timezone

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
