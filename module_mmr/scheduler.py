"""
APScheduler wrapper for the MMR daily email.
Runs a cron job at the configured time (default 10:00 AM).

Schedule hour/minute are interpreted in Dubai time (Asia/Dubai), not server UTC.
Override with env MMR_SCHEDULE_TIMEZONE (e.g. UTC for debugging).
"""
import logging
import os
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


def _cron_timezone():
    """IANA zone for cron triggers; default Asia/Dubai (UAE)."""
    name = (os.environ.get('MMR_SCHEDULE_TIMEZONE') or 'Asia/Dubai').strip() or 'Asia/Dubai'
    try:
        return ZoneInfo(name)
    except Exception:
        logger.warning(
            'MMR scheduler: invalid MMR_SCHEDULE_TIMEZONE=%r, using Asia/Dubai',
            name,
        )
        return ZoneInfo('Asia/Dubai')

_scheduler: BackgroundScheduler | None = None
_JOB_ID = 'mmr_daily_report'
_WATCHDOG_JOB_ID = 'mmr_cycle_approval_watchdog'
# Legacy id from pre-removal upload reminder job — still unregistered in update_schedule.
_LEGACY_REMINDER_JOB_ID = 'mmr_upload_reminder'


# ──────────────────────────────────────────────────────────────────────────────
# Job function (runs outside request context – needs its own app context)
# ──────────────────────────────────────────────────────────────────────────────

def _run_scheduled_report(app):
    with app.app_context():
        try:
            from datetime import datetime, timedelta
            from .routes import (_upload_path, _load_config, _save_config, _save_last_run,
                                  append_automation_activity,
                                  _save_report_to_folder, _save_email_report_to_network,
                                  _format_report_date, _format_report_date_range_str,
                                  _REPORT_DATE_PLACEHOLDER, _report_filename, _complete_current_cycle,
                                  auto_stop_stale_cycle, _is_current_cycle_approved)
            from .mmr_service import parse_excel, generate_report_excel, get_report_date_range_from_df, get_report_date_from_excel, build_mmr_email_bodies
            from common.email_service import send_email

            config = _load_config()
            if not config.get('schedule_enabled'):
                return
            if config.get('schedule_paused'):
                logger.info('MMR scheduler: paused (upload new Excel to resume)')
                return

            # Approval gate — never send for an unreviewed cycle.
            if auto_stop_stale_cycle('triggered by scheduler'):
                logger.warning('MMR scheduler: cycle approval timeout — automation stopped')
                return
            if not _is_current_cycle_approved():
                logger.info('MMR scheduler: skipped (current cycle not approved yet)')
                append_automation_activity(
                    'run_skipped',
                    'Scheduled run skipped: cycle not approved',
                    'Approve the current cycle from the dashboard before the scheduled time.',
                    meta={'reason': 'not_approved'},
                )
                return

            path = _upload_path()
            if not os.path.exists(path):
                logger.info('MMR scheduler: no Excel file found, skipping')
                append_automation_activity(
                    'run_skipped',
                    'Scheduled run skipped: no Excel file on the server',
                    None,
                    meta={'reason': 'no_file'},
                )
                return

            last_mt = config.get('last_sent_source_mtime')
            if last_mt is not None:
                try:
                    if os.path.getmtime(path) <= float(last_mt) + 0.001:
                        logger.warning(
                            'MMR scheduler: Excel unchanged since last send; skipping (upload required)'
                        )
                        cfg2 = _load_config()
                        cfg2['schedule_paused'] = True
                        _save_config(cfg2)
                        append_automation_activity(
                            'run_skipped',
                            'Scheduled run skipped: Excel file unchanged since last send',
                            'Upload a fresh CAFM export before the next run.',
                            meta={'reason': 'stale_file'},
                        )
                        return
                except (TypeError, ValueError):
                    pass

            to_raw = config.get('to', '').strip()
            if not to_raw:
                logger.warning('MMR scheduler: no recipient configured, skipping')
                append_automation_activity(
                    'run_skipped',
                    'Scheduled run skipped: no recipients configured',
                    None,
                    meta={'reason': 'no_recipients'},
                )
                return

            to_list = [e.strip() for e in to_raw.split(',') if e.strip()]
            cc_raw  = config.get('cc', '').strip()
            cc_list = [e.strip() for e in cc_raw.split(',') if e.strip()] if cc_raw else None

            df = parse_excel(path)
            report_bytes = generate_report_excel(df)
            date_range = get_report_date_range_from_df(df)
            rf = config.get('report_format', 'daily')
            rf = str(rf).strip().lower() if rf is not None else 'daily'
            if rf not in ('daily', 'monthly'):
                rf = 'daily'
            filename = _report_filename(report_date_range=date_range, upload_path=path, report_format=rf)

            report_date = _format_report_date_range_str(date_range)
            if report_date is None:
                report_dt = get_report_date_from_excel(path) or (datetime.now() - timedelta(days=1))
                report_date = _format_report_date(report_dt)
            subject = config.get('subject', 'Daily Report on Resolved and Pending Complaints for {{REPORT_DATE}}').replace(_REPORT_DATE_PLACEHOLDER, report_date)
            body = config.get('body', '').replace(_REPORT_DATE_PLACEHOLDER, report_date)
            body, html_body = build_mmr_email_bodies(body, df)

            send_email(
                recipient=to_list,
                subject=subject,
                body=body,
                html_body=html_body,
                cc=cc_list,
                attachments=[{
                    'content': report_bytes,
                    'filename': filename,
                    'mime_type': ('application/vnd.openxmlformats-'
                                  'officedocument.spreadsheetml.sheet'),
                }],
                source='mmr',
                related_id=filename,
            )
            recipient_count = len(to_list) + (len(cc_list) if cc_list else 0)
            cid = _complete_current_cycle('scheduler', subject, recipient_count, filename)
            _save_last_run(
                'success', to_list, cc_list, subject, recipient_count,
                activity_source='scheduler', cycle_id=cid,
            )
            _save_report_to_folder(report_bytes, filename, 'email')
            _save_email_report_to_network(report_bytes, filename)
            logger.info('MMR scheduled report sent successfully')
        except Exception:
            logger.exception('MMR scheduled report failed')
            try:
                from .routes import _load_config, _save_last_run
                config = _load_config()
                to_raw = config.get('to', '').strip()
                to_list = [e.strip() for e in to_raw.split(',') if e.strip()] if to_raw else []
                cc_raw = config.get('cc', '').strip()
                cc_list = [e.strip() for e in cc_raw.split(',') if e.strip()] if cc_raw else None
                _save_last_run(
                    'failed', to_list or [], cc_list or [], '', 0,
                    activity_source='scheduler',
                )
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def _run_approval_watchdog(app):
    """Auto-stop the automation when an uploaded cycle isn't approved within
    the timeout (default 30 minutes). Runs every 5 minutes regardless of
    whether the daily cron is enabled, so the safety net always applies."""
    with app.app_context():
        try:
            from .routes import auto_stop_stale_cycle
            if auto_stop_stale_cycle('approval watchdog'):
                logger.warning('MMR watchdog: cycle approval timeout — automation stopped')
        except Exception:
            logger.exception('MMR watchdog: error checking cycle approval timeout')


def _add_watchdog_job(app):
    """(Re)register the 5-min stale-cycle watchdog."""
    global _scheduler
    if not _scheduler:
        return
    if _scheduler.get_job(_WATCHDOG_JOB_ID):
        _scheduler.remove_job(_WATCHDOG_JOB_ID)
    _scheduler.add_job(
        _run_approval_watchdog,
        IntervalTrigger(minutes=5),
        args=[app],
        id=_WATCHDOG_JOB_ID,
        replace_existing=True,
    )


def init_scheduler(app):
    """Start the background scheduler and register a job if scheduling is enabled."""
    global _scheduler

    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)

    try:
        from .routes import _load_config
        with app.app_context():
            config = _load_config()
        if config.get('schedule_enabled'):
            _add_job(config, app)
            tz = _cron_timezone()
            sh = int(config.get('schedule_hour', 10))
            sm = int(config.get('schedule_minute', 0))
            logger.info(
                'MMR scheduler: report %02d:%02d %s (startup)',
                sh, sm, getattr(tz, 'key', str(tz)),
            )
    except Exception:
        logger.exception('MMR scheduler: error reading config during init')

    _add_watchdog_job(app)

    _scheduler.start()
    logger.info('MMR APScheduler started (cron + cycle approval watchdog)')


def update_schedule(config: dict, app):
    """Called after the admin saves email config – refreshes the cron job."""
    global _scheduler

    if not _scheduler:
        init_scheduler(app)
        return

    for jid in (_JOB_ID, _LEGACY_REMINDER_JOB_ID):
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)

    if config.get('schedule_enabled'):
        _add_job(config, app)
        tz = _cron_timezone()
        logger.info(
            'MMR scheduler: report %02d:%02d %s',
            int(config.get('schedule_hour', 10)),
            int(config.get('schedule_minute', 0)),
            getattr(tz, 'key', str(tz)),
        )
    else:
        logger.info('MMR scheduler: jobs disabled')

    # Watchdog runs in all modes — disable it only if no app instance.
    _add_watchdog_job(app)


def _add_job(config: dict, app):
    global _scheduler
    tz = _cron_timezone()
    sh = int(config.get('schedule_hour', 10))
    sm = int(config.get('schedule_minute', 0))
    _scheduler.add_job(
        _run_scheduled_report,
        CronTrigger(hour=sh, minute=sm, timezone=tz),
        args=[app],
        id=_JOB_ID,
        replace_existing=True,
    )
