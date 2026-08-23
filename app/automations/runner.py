"""Execute catalog jobs: save to Files, email attachments, optional Drive sync."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.automations.jobs import (
    ensure_seed_jobs,
    get_catalog_entry,
    resolve_recipients,
)
from app.models import AutomationJob, AutomationRun, FilesItem, db, _utcnow
from common.email_service import is_email_configured, send_email

logger = logging.getLogger(__name__)

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(slug: str) -> threading.Lock:
    lock = _LOCKS.get(slug)
    if lock is None:
        lock = threading.Lock()
        _LOCKS[slug] = lock
    return lock


def job_timezone(job: AutomationJob) -> ZoneInfo:
    name = (job.timezone or 'Asia/Dubai').strip() or 'Asia/Dubai'
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo('Asia/Dubai')


def _as_aware_utc(stamp: Optional[datetime]) -> Optional[datetime]:
    if stamp is None:
        return None
    if getattr(stamp, 'tzinfo', None) is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def succeeded_today(job: AutomationJob, now_local: Optional[datetime] = None) -> bool:
    if not job.last_success_at:
        return False
    tz = job_timezone(job)
    now = now_local or datetime.now(tz)
    stamp = _as_aware_utc(job.last_success_at)
    if stamp is None:
        return False
    return stamp.astimezone(tz).date() == now.date()


def _dated_names(file_stem: str, now_local: datetime) -> tuple[str, str]:
    day = now_local.strftime('%Y-%m-%d')
    filename = f'{file_stem}_{day}.xlsx'
    display = f'{file_stem.replace("_", " ")} ({day})'
    return filename, display


def _apply_dated_filename(item: FilesItem, file_stem: str, now_local: datetime) -> FilesItem:
    filename, display = _dated_names(file_stem, now_local)
    item.filename = filename
    item.name = display
    item.updated_at = _utcnow()
    return item


def _try_sync_drive(item: FilesItem) -> dict[str, Any]:
    from module_files import drive_service

    status = drive_service.drive_status()
    if not status.get('connected'):
        return {'synced': False, 'skipped': True, 'reason': status.get('message') or 'Drive not connected'}
    try:
        drive_service.sync_item(item.id)
        db.session.refresh(item)
        return {
            'synced': item.sync_status == 'synced',
            'skipped': False,
            'status': item.sync_status,
            'error': item.sync_error or '',
        }
    except Exception as exc:
        logger.warning('Automations Drive sync failed for item %s: %s', item.id, exc)
        return {'synced': False, 'skipped': False, 'error': str(exc)[:400]}


def run_job(
    slug: str,
    *,
    trigger: str = 'manual',
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Run an implemented job. Drive failures become warnings, not hard errors."""
    spec = get_catalog_entry(slug)
    if not spec or not spec.get('implemented'):
        raise ValueError(f'Job is not implemented: {slug}')

    with _lock_for(slug):
        ensure_seed_jobs()
        job = AutomationJob.query.filter_by(slug=slug).first()
        if not job:
            raise ValueError(f'Job not found: {slug}')
        if trigger == 'catchup' and succeeded_today(job):
            return {
                'slug': slug,
                'status': 'skipped',
                'message': 'Already succeeded today (Dubai)',
            }

        tz = job_timezone(job)
        now_local = datetime.now(tz)
        run = AutomationRun(
            job_id=job.id,
            trigger=trigger,
            status='running',
            detail={},
            started_at=_utcnow(),
        )
        db.session.add(run)
        job.last_run_at = _utcnow()
        job.last_error = None
        db.session.commit()

        files_out: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        warnings: list[str] = []
        fatal: Optional[str] = None

        try:
            from module_files import service as files_service

            files_service.ensure_default_folders(created_by=user_id)
            if job.save_to_files:
                for export in spec.get('exports') or []:
                    module = export['module']
                    kind = export.get('kind') or 'export'
                    label = export.get('label') or module
                    stem = export.get('file_stem') or f'{module.title()}_Export'
                    try:
                        item, folder_label = files_service.save_from_module(
                            module, kind, created_by=user_id,
                        )
                        _apply_dated_filename(item, stem, now_local)
                        db.session.commit()
                        abs_path = files_service.resolve_item_abs_path(item)
                        with open(abs_path, 'rb') as fh:
                            payload = fh.read()
                        attachments.append({
                            'content': payload,
                            'filename': item.filename,
                            'mime_type': XLSX_MIME,
                        })
                        drive_result = {'synced': False, 'skipped': True, 'reason': 'Drive sync off'}
                        if job.sync_drive:
                            drive_result = _try_sync_drive(item)
                            if drive_result.get('error') and not drive_result.get('skipped'):
                                warnings.append(f'{label}: Drive sync failed — {drive_result["error"]}')
                        files_out.append({
                            'module': module,
                            'label': label,
                            'item_id': item.id,
                            'filename': item.filename,
                            'folder': folder_label,
                            'size_bytes': item.size_bytes,
                            'drive': drive_result,
                        })
                    except Exception as exc:
                        logger.exception('Automations export failed for %s', module)
                        fatal = f'{label} export failed: {exc}'
                        warnings.append(fatal)
                        break
            else:
                warnings.append('Save to Files is off — nothing to email or sync')

            email_result: dict[str, Any] = {'sent': False, 'skipped': True}
            if fatal is None and job.send_email:
                recipients = resolve_recipients(job)
                if not recipients:
                    warnings.append('No email recipients (set AUTOMATION_BACKUP_TO or job recipients)')
                    email_result = {'sent': False, 'skipped': True, 'reason': 'no_recipients'}
                elif not is_email_configured():
                    warnings.append('Email is not configured — files were still saved')
                    email_result = {'sent': False, 'skipped': True, 'reason': 'email_not_configured'}
                elif not attachments:
                    warnings.append('No Excel attachments to email')
                    email_result = {'sent': False, 'skipped': True, 'reason': 'no_attachments'}
                else:
                    names = ', '.join(a['filename'] for a in attachments)
                    ok = send_email(
                        recipients,
                        f'HR daily backup — {now_local.strftime("%Y-%m-%d")}',
                        (
                            'Attached are today’s Hiring Docs, Leave Tracker, and Manpower Excel exports.\n\n'
                            f'Files: {names}\n'
                            'Saved under Files → HR. Import these workbooks if the local trackers are lost.\n'
                        ),
                        attachments=attachments,
                        source='hr',
                        sent_by_user_id=user_id,
                    )
                    email_result = {'sent': bool(ok), 'skipped': False, 'recipients': recipients}
                    if not ok:
                        warnings.append('Email send failed — files were still saved')
        except Exception as exc:
            logger.exception('Automations job %s crashed', slug)
            fatal = str(exc)[:500]

        if fatal and not files_out:
            status = 'error'
        elif fatal or warnings:
            status = 'warning' if files_out else 'error'
        else:
            status = 'ok'

        run.status = status
        run.finished_at = _utcnow()
        run.error_message = (fatal or (warnings[0] if status == 'error' else ''))[:500] or None
        run.detail = {
            'files': files_out,
            'email': email_result if 'email_result' in locals() else {'sent': False, 'skipped': True},
            'warnings': warnings,
            'dubai_date': now_local.strftime('%Y-%m-%d'),
        }
        if status in ('ok', 'warning'):
            job.last_success_at = _utcnow()
            job.last_error = ('; '.join(warnings)[:500] if warnings else None)
        else:
            job.last_error = run.error_message
        db.session.commit()

        return {
            'slug': slug,
            'status': status,
            'run': run.to_dict(),
            'job': job.to_dict(),
            'warnings': warnings,
            'message': 'Backup finished' if status != 'error' else (run.error_message or 'Backup failed'),
        }


def run_catchup() -> list[dict[str, Any]]:
    """Run implemented enabled jobs that have not succeeded today (Dubai)."""
    ensure_seed_jobs()
    results = []
    jobs = AutomationJob.query.filter_by(enabled=True).all()
    for job in jobs:
        spec = get_catalog_entry(job.slug)
        if not spec or not spec.get('implemented'):
            continue
        if succeeded_today(job):
            results.append({'slug': job.slug, 'status': 'skipped', 'message': 'Already succeeded today'})
            continue
        try:
            results.append(run_job(job.slug, trigger='catchup'))
        except Exception as exc:
            logger.exception('Automations catch-up failed for %s', job.slug)
            results.append({'slug': job.slug, 'status': 'error', 'message': str(exc)})
    return results


def run_scheduled_due() -> list[dict[str, Any]]:
    """Run enabled implemented jobs whose hour/minute match now in the job timezone."""
    ensure_seed_jobs()
    results = []
    jobs = AutomationJob.query.filter_by(enabled=True).all()
    for job in jobs:
        spec = get_catalog_entry(job.slug)
        if not spec or not spec.get('implemented'):
            continue
        tz = job_timezone(job)
        now = datetime.now(tz)
        hour = int(job.schedule_hour if job.schedule_hour is not None else 20)
        minute = int(job.schedule_minute if job.schedule_minute is not None else 0)
        if now.hour != hour or now.minute != minute:
            continue
        try:
            results.append(run_job(job.slug, trigger='scheduler'))
        except Exception as exc:
            logger.exception('Automations scheduled run failed for %s', job.slug)
            results.append({'slug': job.slug, 'status': 'error', 'message': str(exc)})
    return results
