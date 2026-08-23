"""APScheduler for Automations: 8 PM Dubai cron + startup catch-up."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_CRON_PREFIX = 'automations_cron_'
_CATCHUP_ID = 'automations_startup_catchup'


def _env_timezone() -> ZoneInfo:
    name = (os.environ.get('AUTOMATION_SCHEDULE_TIMEZONE') or 'Asia/Dubai').strip() or 'Asia/Dubai'
    try:
        return ZoneInfo(name)
    except Exception:
        logger.warning('Automations scheduler: invalid timezone %r, using Asia/Dubai', name)
        return ZoneInfo('Asia/Dubai')


def _cron_job_id(slug: str) -> str:
    return f'{_CRON_PREFIX}{slug}'


def _run_scheduled(app):
    with app.app_context():
        try:
            from app.automations.runner import run_scheduled_due
            results = run_scheduled_due()
            for row in results:
                logger.info('Automations scheduled %s: %s', row.get('slug'), row.get('status'))
        except Exception:
            logger.exception('Automations scheduled tick failed')


def _run_catchup(app):
    with app.app_context():
        try:
            from app.automations.runner import run_catchup
            results = run_catchup()
            for row in results:
                logger.info('Automations catch-up %s: %s', row.get('slug'), row.get('status'))
        except Exception:
            logger.exception('Automations catch-up failed')


def _is_testing(app) -> bool:
    if app is not None and app.config.get('TESTING'):
        return True
    env = (os.environ.get('TESTING') or '').strip().lower()
    if env in ('1', 'true', 'yes'):
        return True
    return (os.environ.get('FLASK_ENV') or '').strip().lower() == 'testing'


def refresh_cron_jobs(app) -> None:
    """Re-register cron jobs from DB rows (enabled + implemented)."""
    global _scheduler
    if not _scheduler:
        return
    from app.automations.jobs import ensure_seed_jobs, get_catalog_entry
    from app.models import AutomationJob

    existing = [j.id for j in _scheduler.get_jobs() if str(j.id).startswith(_CRON_PREFIX)]
    for jid in existing:
        try:
            _scheduler.remove_job(jid)
        except Exception:
            pass

    specs = []
    with app.app_context():
        ensure_seed_jobs()
        for job in AutomationJob.query.all():
            spec = get_catalog_entry(job.slug)
            if not spec or not spec.get('implemented') or not job.enabled:
                continue
            specs.append({
                'slug': job.slug,
                'timezone': (job.timezone or '').strip(),
                'hour': int(job.schedule_hour if job.schedule_hour is not None else 20),
                'minute': int(job.schedule_minute if job.schedule_minute is not None else 0),
            })

    for row in specs:
        tz_name = row['timezone']
        try:
            tz = ZoneInfo(tz_name) if tz_name else _env_timezone()
        except Exception:
            tz = _env_timezone()
        hour = row['hour']
        minute = row['minute']
        _scheduler.add_job(
            _run_scheduled,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            args=[app],
            id=_cron_job_id(row['slug']),
            replace_existing=True,
            misfire_grace_time=120,
        )
        logger.info(
            'Automations cron %s at %02d:%02d %s',
            row['slug'], hour, minute, getattr(tz, 'key', str(tz)),
        )


def init_scheduler(app) -> None:
    global _scheduler
    if _is_testing(app):
        return
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    refresh_cron_jobs(app)
    _scheduler.add_job(
        _run_catchup,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=15)),
        args=[app],
        id=_CATCHUP_ID,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info('Automations APScheduler started (daily cron + startup catch-up)')
