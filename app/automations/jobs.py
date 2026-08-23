"""Catalog of Automations jobs.

Only `implemented=True` jobs can run. Other rows are listed as coming soon so
the hub can grow to procurement, QHSE, admin exports, etc. without new UI.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from app.models import AutomationJob, db

HR_DAILY_EXCEL = 'hr_daily_excel'

JOB_CATALOG: list[dict[str, Any]] = [
    {
        'slug': HR_DAILY_EXCEL,
        'title': 'HR daily Excel backup',
        'description': (
            'Save Hiring Docs, Leave Tracker, and Manpower Excel into Files, '
            'email the three workbooks, and sync to Google Drive when connected.'
        ),
        'implemented': True,
        'default_hour': 20,
        'default_minute': 0,
        'exports': [
            {'module': 'hiring', 'kind': 'export', 'label': 'Hiring Docs', 'file_stem': 'Hiring_Export'},
            {'module': 'leave', 'kind': 'export', 'label': 'Leave Tracker', 'file_stem': 'Leave_Tracker_Export'},
            {'module': 'manpower', 'kind': 'export', 'label': 'Manpower', 'file_stem': 'Manpower_Export'},
        ],
    },
    {
        'slug': 'procurement_daily_excel',
        'title': 'Procurement daily Excel',
        'description': 'Daily materials export into Files / Procurement.',
        'implemented': False,
        'default_hour': 20,
        'default_minute': 0,
        'exports': [{'module': 'procurement', 'kind': 'export', 'label': 'Procurement'}],
    },
    {
        'slug': 'devices_daily_excel',
        'title': 'Devices export',
        'description': 'Admin devices workbook.',
        'implemented': False,
        'default_hour': 20,
        'default_minute': 0,
        'exports': [{'module': 'devices', 'kind': 'export', 'label': 'Devices'}],
    },
    {
        'slug': 'technicians_daily_excel',
        'title': 'Technicians export',
        'description': 'Admin technicians workbook.',
        'implemented': False,
        'default_hour': 20,
        'default_minute': 0,
        'exports': [{'module': 'technicians', 'kind': 'export', 'label': 'Technicians'}],
    },
    {
        'slug': 'mmr_daily_excel',
        'title': 'MMR report export',
        'description': 'Covered today by Report Generation email automation — listed here for a future unified hub.',
        'implemented': False,
        'default_hour': 10,
        'default_minute': 0,
        'exports': [{'module': 'mmr', 'kind': 'export', 'label': 'MMR'}],
    },
]


def catalog_by_slug() -> dict[str, dict[str, Any]]:
    return {row['slug']: row for row in JOB_CATALOG}


def get_catalog_entry(slug: str) -> Optional[dict[str, Any]]:
    return catalog_by_slug().get((slug or '').strip())


def default_backup_to() -> str:
    return (os.environ.get('AUTOMATION_BACKUP_TO') or '').strip()


def parse_emails(raw: Optional[str]) -> list[str]:
    text = (raw or '').replace(';', ',')
    seen: set[str] = set()
    out: list[str] = []
    for part in text.split(','):
        email = part.strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        out.append(email)
    return out


def resolve_recipients(job: AutomationJob) -> list[str]:
    emails = parse_emails(job.to_emails)
    if emails:
        return emails
    return parse_emails(default_backup_to())


def ensure_seed_jobs() -> AutomationJob:
    """Create the HR daily job row if missing. Returns that job."""
    job = AutomationJob.query.filter_by(slug=HR_DAILY_EXCEL).first()
    if job:
        return job
    spec = get_catalog_entry(HR_DAILY_EXCEL) or {}
    job = AutomationJob(
        slug=HR_DAILY_EXCEL,
        enabled=True,
        schedule_hour=int(spec.get('default_hour') or 20),
        schedule_minute=int(spec.get('default_minute') or 0),
        timezone='Asia/Dubai',
        to_emails=default_backup_to() or None,
        save_to_files=True,
        send_email=True,
        sync_drive=True,
    )
    db.session.add(job)
    db.session.commit()
    return job
