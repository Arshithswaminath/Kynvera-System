"""APScheduler for Automations: 1-minute tick with due-time catch-up.

Reads live DB hour/minute/enabled each tick. Catch-up runs only after today's
scheduled time, so a restart before 11:10 does not send the backup early.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_TICK_ID = 'automations_minute_tick'


def _env_timezone() -> ZoneInfo:
    name = (os.environ.get('AUTOMATION_SCHEDULE_TIMEZONE') or 'Asia/Dubai').strip() or 'Asia/Dubai'
    try:
        return ZoneInfo(name)
    except Exception:
        logger.warning('Automations scheduler: invalid timezone %r, using Asia/Dubai', name)
        return ZoneInfo('Asia/Dubai')


def _run_tick(app):
    with app.app_context():
        try:
            from app.automations.runner import run_scheduler_tick
            results = run_scheduler_tick()
            for row in results:
                status = row.get('status')
                if status == 'skipped':
                    continue
                logger.info('Automations tick %s: %s', row.get('slug'), status)
        except Exception:
            try:
                from app.models import db
                db.session.rollback()
            except Exception:
                pass
            logger.exception('Automations scheduler tick failed')


def _is_testing(app) -> bool:
    if app is not None and app.config.get('TESTING'):
        return True
    env = (os.environ.get('TESTING') or '').strip().lower()
    if env in ('1', 'true', 'yes'):
        return True
    return (os.environ.get('FLASK_ENV') or '').strip().lower() == 'testing'


def _scheduler_disabled(app) -> bool:
    flag = (os.environ.get('AUTOMATIONS_SCHEDULER') or '').strip().lower()
    if flag in ('0', 'false', 'no', 'off'):
        return True
    return _is_testing(app)


def refresh_cron_jobs(app) -> None:
    """Kept for PATCH callers. The minute tick reads hour/minute/enabled from DB."""
    return


def init_scheduler(app) -> None:
    global _scheduler
    if _scheduler_disabled(app):
        return
    if _scheduler and _scheduler.running:
        return

    tz = _env_timezone()
    _scheduler = BackgroundScheduler(daemon=True, timezone=tz)
    _scheduler.add_job(
        _run_tick,
        IntervalTrigger(minutes=1, timezone=tz),
        args=[app],
        id=_TICK_ID,
        replace_existing=True,
        next_run_time=datetime.now(tz) + timedelta(seconds=15),
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info('Automations APScheduler started (1-minute tick, timezone %s)', tz.key)
