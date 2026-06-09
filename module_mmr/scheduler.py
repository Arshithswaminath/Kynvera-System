"""
APScheduler wrapper for the Email Automation engine.

Each enabled EmailAutomation row gets its own job (id = email_auto_<id>).
Schedule times (hour/minute) are interpreted in Dubai time (Asia/Dubai), not
server UTC. Override with env MMR_SCHEDULE_TIMEZONE (e.g. UTC for debugging).
"""
import logging
import os
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


def _cron_timezone():
    """IANA zone for triggers; default Asia/Dubai (UAE)."""
    name = (os.environ.get('MMR_SCHEDULE_TIMEZONE') or 'Asia/Dubai').strip() or 'Asia/Dubai'
    try:
        return ZoneInfo(name)
    except Exception:
        logger.warning(
            'Automation scheduler: invalid MMR_SCHEDULE_TIMEZONE=%r, using Asia/Dubai',
            name,
        )
        return ZoneInfo('Asia/Dubai')


_scheduler: BackgroundScheduler | None = None


def _job_id(automation_id: int) -> str:
    return f'email_auto_{automation_id}'


# ──────────────────────────────────────────────────────────────────────────────
# Trigger construction
# ──────────────────────────────────────────────────────────────────────────────

def _trigger_for(automation):
    """Build an APScheduler trigger from an EmailAutomation row (Dubai tz)."""
    tz = _cron_timezone()
    hour = int(automation.hour or 0)
    minute = int(automation.minute or 0)
    st = (automation.schedule_type or 'daily').strip().lower()

    if st == 'weekly':
        wd = int(automation.weekday or 0)  # 0=Mon .. 6=Sun (matches APScheduler)
        return CronTrigger(day_of_week=wd, hour=hour, minute=minute, timezone=tz)

    if st == 'monthly':
        dom = max(1, min(28, int(automation.day_of_month or 1)))
        return CronTrigger(day=dom, hour=hour, minute=minute, timezone=tz)

    if st == 'quarterly':
        start = max(1, min(12, int(automation.quarter_start_month or 1)))
        months = sorted({((start - 1 + 3 * i) % 12) + 1 for i in range(4)})
        dom = max(1, min(28, int(automation.day_of_month or 1)))
        return CronTrigger(
            month=','.join(str(m) for m in months),
            day=dom, hour=hour, minute=minute, timezone=tz,
        )

    if st == 'interval':
        n = max(1, int(automation.interval_n or 1))
        unit = (automation.interval_unit or 'days').strip().lower()
        if unit == 'weeks':
            return IntervalTrigger(weeks=n, timezone=tz)
        if unit == 'months':
            # APScheduler has no month interval; approximate with cron month='*/N'
            # at the configured day/time. N=12 => yearly.
            dom = max(1, min(28, int(automation.day_of_month or 1)))
            return CronTrigger(
                month=f'*/{n}', day=dom, hour=hour, minute=minute, timezone=tz,
            )
        return IntervalTrigger(days=n, timezone=tz)

    # default: daily
    return CronTrigger(hour=hour, minute=minute, timezone=tz)


# ──────────────────────────────────────────────────────────────────────────────
# Job function (runs outside request context – needs its own app context)
# ──────────────────────────────────────────────────────────────────────────────

def _run_automation(automation_id, app, force=False):
    """Send the email for one automation. Records last-run status on the row.

    force=True (manual "Run now") sends even when the automation is disabled;
    the scheduled path uses force=False so disabled automations stay dormant.
    """
    with app.app_context():
        from datetime import datetime, timezone as _tz
        from app.models import db, EmailAutomation
        from common.email_service import send_email

        automation = EmailAutomation.query.get(automation_id)
        if not automation:
            logger.info('Automation %s no longer exists; skipping', automation_id)
            return
        if not automation.enabled and not force:
            logger.info('Automation %s disabled; skipping', automation_id)
            return

        to_list = [e.strip() for e in (automation.to_emails or '').split(',') if e.strip()]
        cc_list = [e.strip() for e in (automation.cc_emails or '').split(',') if e.strip()] or None

        def _finish(status, detail):
            try:
                automation.last_run_at = datetime.now(_tz.utc).replace(tzinfo=None)
                automation.last_run_status = status
                automation.last_run_detail = (detail or '')[:1000]
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception('Automation %s: failed to record last run', automation_id)

        if not to_list:
            logger.warning('Automation %s: no recipients; skipping', automation_id)
            _finish('failed', 'No recipients configured')
            return

        try:
            subject = automation.subject or '(no subject)'
            # Body must be non-empty — some providers (e.g. Brevo) reject blank text content.
            body = automation.body if (automation.body and automation.body.strip()) else subject
            body_escaped = (
                body.replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;').replace('\n', '<br>')
            )
            html_body = (
                '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                '<body style="font-family:Arial,sans-serif;font-size:13px;color:#333">'
                f'<p style="margin:0;line-height:1.5">{body_escaped}</p>'
                '</body></html>'
            )

            attachments = [
                {
                    'content': a.content,
                    'filename': a.filename,
                    'mime_type': a.mime_type or 'application/octet-stream',
                }
                for a in automation.attachments
            ] or None

            ok = send_email(
                recipient=to_list,
                subject=subject,
                body=body,
                html_body=html_body,
                cc=cc_list,
                attachments=attachments,
            )
            if not ok:
                _finish('failed', 'Email service rejected the send (check mail configuration)')
                logger.warning('Automation %s (%s): send_email returned False', automation_id, automation.name)
                return
            n_att = len(attachments) if attachments else 0
            n_rcpt = len(to_list) + (len(cc_list) if cc_list else 0)
            _finish('success', f'Sent to {n_rcpt} recipient(s) with {n_att} attachment(s)')
            logger.info('Automation %s (%s) sent successfully', automation_id, automation.name)
        except Exception as exc:
            logger.exception('Automation %s failed', automation_id)
            _finish('failed', str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def init_scheduler(app):
    """Start the background scheduler and register a job for each enabled automation."""
    global _scheduler

    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    logger.info('Email Automation APScheduler started')

    try:
        _sync_all_jobs(app)
    except Exception:
        logger.exception('Automation scheduler: error registering jobs during init')


def _sync_all_jobs(app):
    """Reload every enabled automation and (re)register its job. Removes stale jobs."""
    global _scheduler
    if not _scheduler:
        init_scheduler(app)
        return

    from app.models import EmailAutomation
    with app.app_context():
        automations = EmailAutomation.query.all()

    valid_ids = set()
    for automation in automations:
        valid_ids.add(_job_id(automation.id))
        _register_one(automation, app)

    # Drop jobs whose automation was deleted/disabled
    for job in list(_scheduler.get_jobs()):
        if job.id.startswith('email_auto_') and job.id not in valid_ids:
            _scheduler.remove_job(job.id)


def _register_one(automation, app):
    """Add/replace the job for one automation; remove it when disabled."""
    global _scheduler
    if not _scheduler:
        return
    jid = _job_id(automation.id)
    if _scheduler.get_job(jid):
        _scheduler.remove_job(jid)
    if not automation.enabled:
        return
    _scheduler.add_job(
        _run_automation,
        _trigger_for(automation),
        args=[automation.id, app],
        id=jid,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        'Automation scheduler: registered %s (%s)',
        jid, automation.schedule_summary(),
    )


def sync_automation_job(automation, app):
    """Public hook for CRUD routes: refresh one automation's job after save/toggle."""
    if not _scheduler:
        init_scheduler(app)
    _register_one(automation, app)


def remove_automation_job(automation_id, app):
    """Public hook for CRUD routes: drop a job when an automation is deleted."""
    global _scheduler
    if not _scheduler:
        return
    jid = _job_id(automation_id)
    if _scheduler.get_job(jid):
        _scheduler.remove_job(jid)
        logger.info('Automation scheduler: removed %s', jid)


def run_automation_now(automation_id, app):
    """Fire an automation immediately (manual test from the UI), even if disabled."""
    _run_automation(automation_id, app, force=True)
