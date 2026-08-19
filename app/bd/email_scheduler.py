"""APScheduler tick for BD email automations (daily hour/minute in Dubai time)."""

import logging
import os
from datetime import timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_JOB_ID = 'bd_email_automations_tick'


def _cron_timezone():
    name = (os.environ.get('BD_EMAIL_SCHEDULE_TIMEZONE') or os.environ.get('MMR_SCHEDULE_TIMEZONE') or 'Asia/Dubai').strip() or 'Asia/Dubai'
    try:
        return ZoneInfo(name)
    except Exception:
        logger.warning('BD email scheduler: invalid timezone %r, using Asia/Dubai', name)
        return ZoneInfo('Asia/Dubai')


def _already_ran_today(auto, now_local):
    if not auto.last_run_at:
        return False
    stamp = auto.last_run_at
    if getattr(stamp, 'tzinfo', None) is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    local_date = stamp.astimezone(now_local.tzinfo).date()
    return local_date == now_local.date()


def _run_due_automations(app):
    from datetime import datetime

    with app.app_context():
        try:
            from app.models import EmailAutomation
            from app.bd.email_automation import run_automation, AutomationError

            tz = _cron_timezone()
            now = datetime.now(tz)
            rows = EmailAutomation.query.filter_by(
                enabled=True,
                schedule_enabled=True,
                schedule_paused=False,
            ).all()
            for auto in rows:
                hour = int(auto.schedule_hour if auto.schedule_hour is not None else 10)
                minute = int(auto.schedule_minute if auto.schedule_minute is not None else 0)
                if hour != now.hour or minute != now.minute:
                    continue
                if _already_ran_today(auto, now):
                    continue
                try:
                    result = run_automation(auto, user=None, trigger='scheduler')
                    if result.get('skipped'):
                        logger.info(
                            'BD email automation %s skipped: %s',
                            auto.id,
                            result.get('message'),
                        )
                    else:
                        logger.info('BD email automation %s sent', auto.id)
                except AutomationError as err:
                    logger.warning('BD email automation %s failed: %s', auto.id, err.message)
                except Exception:
                    logger.exception('BD email automation %s crashed', auto.id)
        except Exception:
            logger.exception('BD email scheduler tick failed')


def init_scheduler(app):
    """Start a 1-minute tick that sends due daily automations."""
    global _scheduler

    if app.config.get('TESTING'):
        return
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_due_automations,
        IntervalTrigger(minutes=1),
        args=[app],
        id=_JOB_ID,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info('BD email APScheduler started (1-minute tick, timezone %s)', getattr(_cron_timezone(), 'key', 'Asia/Dubai'))
