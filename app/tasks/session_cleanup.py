"""
Session cleanup task - removes expired sessions
"""
import logging
from datetime import timedelta
from app.models import db, Session
from common.datetime_utils import utc_now_naive

logger = logging.getLogger(__name__)


def cleanup_expired_sessions():
    """
    Remove expired sessions from database
    Should be run periodically (e.g., daily via cron or scheduled task)
    """
    try:
        # Delete sessions that expired more than 7 days ago
        cutoff_date = utc_now_naive() - timedelta(days=7)
        
        expired_sessions = Session.query.filter(
            Session.expires_at < cutoff_date
        ).all()
        
        count = len(expired_sessions)
        
        if count > 0:
            for session in expired_sessions:
                db.session.delete(session)
            db.session.commit()
            logger.info(f"Cleaned up {count} expired sessions")
        else:
            logger.debug("No expired sessions to clean up")
        
        return count
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cleaning up expired sessions: {str(e)}")
        return 0


def cleanup_revoked_sessions():
    """
    Remove revoked sessions older than 30 days
    """
    try:
        cutoff_date = utc_now_naive() - timedelta(days=30)
        
        revoked_sessions = Session.query.filter(
            Session.is_revoked == True,
            Session.expires_at < cutoff_date
        ).all()
        
        count = len(revoked_sessions)
        
        if count > 0:
            for session in revoked_sessions:
                db.session.delete(session)
            db.session.commit()
            logger.info(f"Cleaned up {count} old revoked sessions")
        
        return count
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cleaning up revoked sessions: {str(e)}")
        return 0

