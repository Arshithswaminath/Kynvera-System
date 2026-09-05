"""Execute catalog jobs: save to Files, email attachments, optional Drive sync."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.automations.jobs import (
    ensure_seed_jobs,
    filter_exports,
    get_catalog_entry,
    join_and,
    module_labels,
    resolve_recipients,
    selected_modules,
)
from app.automations.run_record import (
    OUTCOME_FAILED,
    OUTCOME_SENT,
    OUTCOME_SKIPPED,
    REASON_EMAIL_NOT_CONFIGURED,
    REASON_NO_ATTACHMENTS,
    REASON_NO_RECIPIENTS,
    REASON_SEND_EMAIL_OFF,
    REASON_SEND_FAILED,
    build_email_outcome,
    build_run_detail,
    file_record,
    lookup_email_log,
    normalize_run_view,
    related_id_for_run,
)
from app.models import AutomationJob, AutomationRun, FilesItem, db, _utcnow
from common.email_service import branded_kynvera_html, is_email_configured, send_email

logger = logging.getLogger(__name__)

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PDF_MIME = 'application/pdf'
_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(slug: str) -> threading.Lock:
    lock = _LOCKS.get(slug)
    if lock is None:
        lock = threading.Lock()
        _LOCKS[slug] = lock
    return lock


def _safe_rollback() -> None:
    """Clear a failed SQLAlchemy transaction so later jobs can use this session."""
    try:
        db.session.rollback()
    except Exception:
        logger.warning('Automations session rollback failed', exc_info=True)


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


def _now_for_job(job: AutomationJob, now_local: Optional[datetime] = None) -> datetime:
    tz = job_timezone(job)
    if now_local is None:
        return datetime.now(tz)
    if getattr(now_local, 'tzinfo', None) is None:
        return now_local.replace(tzinfo=tz)
    return now_local.astimezone(tz)


def scheduled_at_today(job: AutomationJob, now_local: Optional[datetime] = None) -> datetime:
    now = _now_for_job(job, now_local)
    hour = int(job.schedule_hour if job.schedule_hour is not None else 20)
    minute = int(job.schedule_minute if job.schedule_minute is not None else 0)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def due_trigger_for_job(job: AutomationJob, now_local: Optional[datetime] = None) -> Optional[str]:
    """How a minute-tick should label this job, or None if it is not due yet today.

    Exact scheduled minute → ``scheduler``. After that time the same local day →
    ``catchup``. Before the scheduled time → None (do not run early on restart).
    """
    now = _now_for_job(job, now_local)
    due_at = scheduled_at_today(job, now)
    if now < due_at:
        return None
    if now.hour == due_at.hour and now.minute == due_at.minute:
        return 'scheduler'
    return 'catchup'


def succeeded_today(job: AutomationJob, now_local: Optional[datetime] = None) -> bool:
    if not job.last_success_at:
        return False
    now = _now_for_job(job, now_local)
    stamp = _as_aware_utc(job.last_success_at)
    if stamp is None:
        return False
    return stamp.astimezone(now.tzinfo).date() == now.date()


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


def _email_copy(
    spec: dict[str, Any],
    now_local: datetime,
    names: str,
    *,
    module_labels_list: Optional[list[str]] = None,
    files: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str, str, str]:
    """Subject, text body, HTML body, and email-log source."""
    day = now_local.strftime('%Y-%m-%d')
    try:
        pretty = now_local.strftime('%-d %b %Y')
    except ValueError:
        pretty = now_local.strftime('%d %b %Y').lstrip('0')
    prefix = (spec.get('email_subject_prefix') or spec.get('title') or 'Daily export').strip()
    subject = f'{prefix} — {day}'
    labels = [lab for lab in (module_labels_list or []) if lab]
    included = join_and(labels) or 'Excel'
    folder = ''
    for row in files or []:
        folder = (row.get('folder') or '').strip()
        if folder:
            break
    folder = folder or 'Files'
    snapshot = bool(spec.get('ui_snapshot'))
    pdf_note = ', plus a PDF of the matching live screens' if snapshot else ''
    template = spec.get('email_body') or (
        'Attached are today’s Excel exports.\n\n'
        'Files: {names}\n'
    )
    if labels:
        body = (
            f'Today’s {included} backup is attached{pdf_note}.\n\n'
            f'Files: {names}\n'
            f'Saved under Files → {folder}.\n'
        )
    else:
        body = str(template).replace('{names}', names).replace('{date}', day)
    html = _email_html(
        greeting=f'{prefix}',
        pretty=pretty,
        included=included,
        labels=labels,
        pdf_note=pdf_note,
        files=files or [],
        names=names,
        folder=folder,
    )
    source = (spec.get('email_source') or spec.get('slug') or 'automations').strip() or 'automations'
    return subject, body, html, source


def _files_cta_url() -> str:
    try:
        from flask import current_app
        base = (current_app.config.get('APP_BASE_URL') or '').rstrip('/')
    except Exception:
        base = ''
    if not base:
        return ''
    return f'{base}/files/'


def _email_html(
    *,
    greeting: str,
    pretty: str,
    included: str,
    labels: list[str],
    pdf_note: str,
    files: list[dict[str, Any]],
    names: str,
    folder: str,
) -> str:
    from html import escape as esc

    intro = f'Today’s {esc(included)} backup is attached{esc(pdf_note)}.'
    date_line = f'{esc(pretty)} · Dubai'
    chips = ''
    for lab in labels:
        chips += (
            f'<span style="display:inline-block;margin:0 6px 8px 0;padding:5px 11px;'
            f'font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:bold;'
            f'color:#c2440c;background:#fff4ef;border:1px solid #ffcdb8;border-radius:999px;">'
            f'{esc(lab)}</span>'
        )
    chip_block = (
        f'<div style="margin:0 0 14px 0;">{chips}</div>' if chips else ''
    )
    rows = ''
    for row in files:
        name = esc(row.get('filename') or row.get('label') or 'File')
        kind = 'PDF' if str(row.get('filename') or '').lower().endswith('.pdf') else 'Workbook'
        label = esc(row.get('label') or kind)
        rows += (
            '<tr>'
            f'<td style="padding:10px 12px;font-family:Arial,Helvetica,sans-serif;font-size:14px;'
            f'color:#191b23;border-bottom:1px solid #efe7e2;">{name}'
            f'<div style="font-size:12px;color:#8a7e78;margin-top:2px;">{label} · {kind}</div></td>'
            '</tr>'
        )
    if not rows and names:
        for part in [p.strip() for p in names.split(',') if p.strip()]:
            rows += (
                '<tr><td style="padding:10px 12px;font-family:Arial,Helvetica,sans-serif;font-size:14px;'
                f'color:#191b23;border-bottom:1px solid #efe7e2;">{esc(part)}</td></tr>'
            )
    extra = (
        f'<p style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;'
        f'letter-spacing:0.04em;text-transform:uppercase;color:#8a7e78;">{date_line}</p>'
        f'{chip_block}'
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:0 0 16px 0;background-color:#fff8f5;border:1px solid #fde4d8;border-radius:12px;">'
        f'{rows}'
        '</table>'
        f'<p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#5c616e;">'
        f'Saved in Files → {esc(folder)}. Import a workbook if a tracker is lost.</p>'
    )
    return branded_kynvera_html(
        greeting=esc(greeting),
        paragraphs=[intro],
        extra_html=extra,
        cta_url=_files_cta_url(),
        cta_label='Open Files',
    )


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


def _attach_ui_snapshot(
    *,
    job: AutomationJob,
    now_local: datetime,
    user_id: Optional[int],
    files_out: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    warnings: list[str],
    modules: Optional[list[str]] = None,
) -> None:
    """Capture the HR module screens into a branded PDF. Never raises."""
    from app.automations.hr_snapshot_pdf import (
        build_hr_ui_snapshot_pdf,
        snapshot_filenames,
    )

    try:
        pdf_bytes, snap_warn = build_hr_ui_snapshot_pdf(
            now_local=now_local,
            user_id=user_id,
            modules=modules,
        )
    except Exception as exc:
        logger.exception('Automations UI snapshot crashed')
        warnings.append(f'UI snapshot PDF failed: {exc}'[:240])
        return

    if snap_warn:
        if snap_warn.lower().startswith('ui snapshot skipped'):
            logger.info('%s', snap_warn)
        else:
            warnings.append(snap_warn)
    if not pdf_bytes:
        return

    filename, display = snapshot_filenames(now_local)
    item_id = None
    folder_label = 'HR'
    drive_result: dict[str, Any] = {'synced': False, 'skipped': True, 'reason': 'Not saved to Files'}
    if job.save_to_files:
        try:
            from module_files import service as files_service

            folder = files_service.get_folder_by_path_key('hr', created_by=user_id)
            item = files_service.save_bytes_to_folder(
                folder=folder,
                data=pdf_bytes,
                display_name=display,
                filename=filename,
                mime_type=PDF_MIME,
                source_module='hr',
                source_kind='ui_snapshot',
                created_by=user_id,
            )
            item_id = item.id
            folder_label = folder.name or 'HR'
            drive_result = {'synced': False, 'skipped': True, 'reason': 'Drive sync off'}
            if job.sync_drive:
                drive_result = _try_sync_drive(item)
                if drive_result.get('error') and not drive_result.get('skipped'):
                    warnings.append(f'UI snapshot: Drive sync failed — {drive_result["error"]}')
        except Exception as exc:
            logger.warning('Automations UI snapshot save-to-Files failed: %s', exc)
            warnings.append(f'UI snapshot saved to email only — Files save failed: {exc}'[:200])

    attachments.append({
        'content': pdf_bytes,
        'filename': filename,
        'mime_type': PDF_MIME,
    })
    files_out.append(file_record(
        module='hr_snapshot',
        label='HR UI Snapshot',
        item_id=item_id,
        filename=filename,
        folder=folder_label,
        size_bytes=len(pdf_bytes),
        drive=drive_result,
        attached_to_email=True,
    ))


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
        if trigger in ('catchup', 'scheduler') and succeeded_today(job):
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
        try:
            db.session.commit()
        except Exception:
            _safe_rollback()
            raise

        files_out: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        warnings: list[str] = []
        fatal: Optional[str] = None
        related_id = related_id_for_run(run.id)
        recipients = resolve_recipients(job)
        modules = selected_modules(getattr(job, 'export_modules', None), spec)
        labels = module_labels(modules, spec)
        subject, _, _, _ = _email_copy(spec, now_local, '', module_labels_list=labels)
        email_result = build_email_outcome(
            outcome=OUTCOME_SKIPPED,
            reason=REASON_SEND_EMAIL_OFF if not job.send_email else None,
            recipients=recipients,
            subject=subject,
            related_id=related_id,
        )

        try:
            from module_files import service as files_service

            files_service.ensure_default_folders(created_by=user_id)
            if job.save_to_files:
                for export in filter_exports(spec, modules):
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
                        files_out.append(file_record(
                            module=module,
                            label=label,
                            item_id=item.id,
                            filename=item.filename,
                            folder=folder_label,
                            size_bytes=item.size_bytes,
                            drive=drive_result,
                            attached_to_email=True,
                        ))
                    except Exception as exc:
                        logger.exception('Automations export failed for %s', module)
                        fatal = f'{label} export failed: {exc}'
                        warnings.append(fatal)
                        break
            else:
                warnings.append('Save to Files is off — nothing to email or sync')

            if fatal is None and spec.get('ui_snapshot') and (job.save_to_files or job.send_email):
                _attach_ui_snapshot(
                    job=job,
                    now_local=now_local,
                    user_id=user_id,
                    files_out=files_out,
                    attachments=attachments,
                    warnings=warnings,
                    modules=modules,
                )

            attachment_names = [a['filename'] for a in attachments if a.get('filename')]
            email_result['attachment_names'] = attachment_names
            if fatal is None and job.send_email:
                if not recipients:
                    warnings.append('No email recipients (set AUTOMATION_BACKUP_TO or job recipients)')
                    email_result = build_email_outcome(
                        outcome=OUTCOME_SKIPPED,
                        reason=REASON_NO_RECIPIENTS,
                        recipients=recipients,
                        subject=subject,
                        attachment_names=attachment_names,
                        related_id=related_id,
                    )
                elif not is_email_configured():
                    warnings.append('Email is not configured — files were still saved')
                    email_result = build_email_outcome(
                        outcome=OUTCOME_SKIPPED,
                        reason=REASON_EMAIL_NOT_CONFIGURED,
                        recipients=recipients,
                        subject=subject,
                        attachment_names=attachment_names,
                        related_id=related_id,
                    )
                elif not attachments:
                    warnings.append('No Excel attachments to email')
                    email_result = build_email_outcome(
                        outcome=OUTCOME_SKIPPED,
                        reason=REASON_NO_ATTACHMENTS,
                        recipients=recipients,
                        subject=subject,
                        attachment_names=attachment_names,
                        related_id=related_id,
                    )
                else:
                    names = ', '.join(attachment_names)
                    subject, body, html_body, email_source = _email_copy(
                        spec,
                        now_local,
                        names,
                        module_labels_list=labels,
                        files=files_out,
                    )
                    ok = send_email(
                        recipients,
                        subject,
                        body,
                        html_body=html_body,
                        attachments=attachments,
                        source=email_source,
                        sent_by_user_id=user_id,
                        related_id=related_id,
                    )
                    log = lookup_email_log(related_id)
                    email_result = build_email_outcome(
                        outcome=OUTCOME_SENT if ok else OUTCOME_FAILED,
                        reason=None if ok else REASON_SEND_FAILED,
                        recipients=recipients,
                        subject=subject,
                        attachment_names=attachment_names,
                        email_log_id=log.id if log else None,
                        related_id=related_id,
                    )
                    if not ok:
                        warnings.append('Email send failed — files were still saved')
            elif not job.send_email:
                email_result = build_email_outcome(
                    outcome=OUTCOME_SKIPPED,
                    reason=REASON_SEND_EMAIL_OFF,
                    recipients=recipients,
                    subject=subject,
                    attachment_names=attachment_names,
                    related_id=related_id,
                )
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
        run.detail = build_run_detail(
            job=job,
            spec=spec,
            files=files_out,
            email=email_result,
            warnings=warnings,
            dubai_date=now_local.strftime('%Y-%m-%d'),
        )
        if status in ('ok', 'warning'):
            job.last_success_at = _utcnow()
            job.last_error = ('; '.join(warnings)[:500] if warnings else None)
        else:
            job.last_error = run.error_message
        try:
            db.session.commit()
        except Exception:
            _safe_rollback()
            raise

        return {
            'slug': slug,
            'status': status,
            'run': normalize_run_view(run),
            'job': job.to_dict(),
            'warnings': warnings,
            'message': 'Backup finished' if status != 'error' else (run.error_message or 'Backup failed'),
        }


def _iter_enabled_implemented_jobs():
    ensure_seed_jobs()
    jobs = AutomationJob.query.filter_by(enabled=True).all()
    for job in jobs:
        spec = get_catalog_entry(job.slug)
        if spec and spec.get('implemented'):
            yield job


def run_catchup(now_local: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Run enabled jobs whose scheduled time has passed today and that have not succeeded."""
    results = []
    due_slugs: list[str] = []
    for job in _iter_enabled_implemented_jobs():
        if succeeded_today(job, now_local):
            results.append({'slug': job.slug, 'status': 'skipped', 'message': 'Already succeeded today'})
            continue
        if due_trigger_for_job(job, now_local) is None:
            results.append({'slug': job.slug, 'status': 'skipped', 'message': 'Not due yet today'})
            continue
        due_slugs.append(job.slug)
    for slug in due_slugs:
        try:
            results.append(run_job(slug, trigger='catchup'))
        except Exception as exc:
            _safe_rollback()
            logger.exception('Automations catch-up failed for %s', slug)
            results.append({'slug': slug, 'status': 'error', 'message': str(exc)})
    return results


def run_scheduled_due(now_local: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Run enabled jobs whose hour/minute match now and that have not succeeded today."""
    results = []
    due_slugs: list[str] = []
    for job in _iter_enabled_implemented_jobs():
        if due_trigger_for_job(job, now_local) != 'scheduler':
            continue
        if succeeded_today(job, now_local):
            results.append({'slug': job.slug, 'status': 'skipped', 'message': 'Already succeeded today'})
            continue
        due_slugs.append(job.slug)
    for slug in due_slugs:
        try:
            results.append(run_job(slug, trigger='scheduler'))
        except Exception as exc:
            _safe_rollback()
            logger.exception('Automations scheduled run failed for %s', slug)
            results.append({'slug': slug, 'status': 'error', 'message': str(exc)})
    return results


def run_scheduler_tick(now_local: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Minute tick: run due jobs that have not succeeded today.

    On the scheduled minute the trigger is ``scheduler``; later the same day it
    is ``catchup`` (missed cron, process restart, or a failed earlier attempt).
    """
    results = []
    due: list[tuple[str, str]] = []
    for job in _iter_enabled_implemented_jobs():
        if succeeded_today(job, now_local):
            results.append({'slug': job.slug, 'status': 'skipped', 'message': 'Already succeeded today'})
            continue
        trigger = due_trigger_for_job(job, now_local)
        if trigger is None:
            continue
        due.append((job.slug, trigger))
    for slug, trigger in due:
        try:
            results.append(run_job(slug, trigger=trigger))
        except Exception as exc:
            _safe_rollback()
            logger.exception('Automations %s run failed for %s', trigger, slug)
            results.append({'slug': slug, 'status': 'error', 'message': str(exc)})
    return results
