"""Catalog of Automations jobs.

Only `implemented=True` jobs can run. Linked rows (Report Generation) stay
read-only in this hub. Other unimplemented rows list as coming soon.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from app.models import AutomationJob, db

HR_DAILY_EXCEL = 'hr_daily_excel'
PROCUREMENT_DAILY_EXCEL = 'procurement_daily_excel'
DEVICES_DAILY_EXCEL = 'devices_daily_excel'
TECHNICIANS_DAILY_EXCEL = 'technicians_daily_excel'
MMR_DAILY_EXCEL = 'mmr_daily_excel'

JOB_CATALOG: list[dict[str, Any]] = [
    {
        'slug': HR_DAILY_EXCEL,
        'title': 'HR daily Excel backup',
        'description': (
            'Save Hiring Docs, Leave Tracker, and Manpower Excel into Files, '
            'email the workbooks, and sync to Google Drive when connected.'
        ),
        'implemented': True,
        'default_hour': 20,
        'default_minute': 0,
        'email_subject_prefix': 'HR daily backup',
        'email_body': (
            'Attached are today’s Hiring Docs, Leave Tracker, and Manpower Excel exports.\n\n'
            'Files: {names}\n'
            'Saved under Files → HR. Import the workbooks if the local trackers are lost.\n'
        ),
        'ui_snapshot': False,
        'email_source': 'hr',
        'files_hint': 'Hiring, Leave, Manpower',
        'exports': [
            {'module': 'hiring', 'kind': 'export', 'label': 'Hiring Docs', 'file_stem': 'Hiring_Export', 'short_label': 'Hiring'},
            {'module': 'leave', 'kind': 'export', 'label': 'Leave Tracker', 'file_stem': 'Leave_Tracker_Export', 'short_label': 'Leave'},
            {'module': 'manpower', 'kind': 'export', 'label': 'Manpower', 'file_stem': 'Manpower_Export', 'short_label': 'Manpower'},
        ],
    },
    {
        'slug': PROCUREMENT_DAILY_EXCEL,
        'title': 'Procurement daily Excel',
        'description': 'Daily materials export into Files / Procurement.',
        'implemented': True,
        'default_hour': 20,
        'default_minute': 0,
        'email_subject_prefix': 'Procurement daily export',
        'email_body': (
            'Attached is today’s procurement materials export.\n\n'
            'Files: {names}\n'
            'Saved under Files → Procurement.\n'
        ),
        'email_source': 'procurement',
        'files_hint': 'Files / Procurement',
        'exports': [
            {
                'module': 'procurement',
                'kind': 'export',
                'label': 'Procurement',
                'file_stem': 'Procurement_Export',
            },
        ],
    },
    {
        'slug': DEVICES_DAILY_EXCEL,
        'title': 'Devices export',
        'description': 'Admin devices workbook.',
        'implemented': True,
        'default_hour': 20,
        'default_minute': 0,
        'email_subject_prefix': 'Devices export',
        'email_body': (
            'Attached is today’s admin devices workbook.\n\n'
            'Files: {names}\n'
            'Saved under Files → Admin / Devices.\n'
        ),
        'email_source': 'devices',
        'files_hint': 'Admin / Devices',
        'exports': [
            {'module': 'devices', 'kind': 'export', 'label': 'Devices', 'file_stem': 'Devices_Export'},
        ],
    },
    {
        'slug': TECHNICIANS_DAILY_EXCEL,
        'title': 'Technicians export',
        'description': 'Admin technicians workbook.',
        'implemented': True,
        'default_hour': 20,
        'default_minute': 0,
        'email_subject_prefix': 'Technicians export',
        'email_body': (
            'Attached is today’s admin technicians workbook.\n\n'
            'Files: {names}\n'
            'Saved under Files → Admin / Technicians.\n'
        ),
        'email_source': 'technicians',
        'files_hint': 'Admin / Technicians',
        'exports': [
            {
                'module': 'technicians',
                'kind': 'export',
                'label': 'Technicians',
                'file_stem': 'Technicians_Export',
            },
        ],
    },
    {
        'slug': MMR_DAILY_EXCEL,
        'title': 'Report generated',
        'description': (
            'Report Generation sends the MMR email. This hub shows when that '
            'email went out and which workbook was attached.'
        ),
        'implemented': False,
        'linked': True,
        'linked_url': '/admin/mmr/',
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


_SHORT_LABELS = {
    'hiring': 'Hiring',
    'leave': 'Leave',
    'manpower': 'Manpower',
}


def module_choices_for_spec(spec: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    """Selectable modules for a job, in catalog order."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for export in (spec or {}).get('exports') or []:
        mid = str(export.get('module') or '').strip().lower()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        label = (
            str(export.get('short_label') or '').strip()
            or _SHORT_LABELS.get(mid)
            or str(export.get('label') or mid).strip()
        )
        out.append({'id': mid, 'label': label})
    return out


def allowed_module_ids(spec: Optional[dict[str, Any]]) -> list[str]:
    return [row['id'] for row in module_choices_for_spec(spec)]


def join_and(parts: list[str]) -> str:
    labels = [p for p in parts if p]
    if not labels:
        return ''
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f'{labels[0]} and {labels[1]}'
    return f'{", ".join(labels[:-1])}, and {labels[-1]}'


def parse_module_list(raw) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        parts = str(raw or '').replace(';', ',').split(',')
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        mid = str(part or '').strip().lower()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out


def selected_modules(raw, spec: Optional[dict[str, Any]]) -> list[str]:
    """Resolved module ids. Empty or unknown values fall back to every catalog export."""
    allowed = allowed_module_ids(spec)
    if not allowed:
        return []
    picked = [mid for mid in parse_module_list(raw) if mid in allowed]
    return picked or list(allowed)


def serialize_modules(ids: list[str]) -> str:
    return ','.join(ids)


def module_labels(ids: list[str], spec: Optional[dict[str, Any]]) -> list[str]:
    by_id = {row['id']: row['label'] for row in module_choices_for_spec(spec)}
    return [by_id.get(mid, mid.title()) for mid in ids]


def filter_exports(spec: Optional[dict[str, Any]], modules: list[str]) -> list[dict[str, Any]]:
    wanted = set(modules)
    return [
        export for export in (spec or {}).get('exports') or []
        if str(export.get('module') or '').strip().lower() in wanted
    ]


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
    """Create DB rows for implemented catalog jobs. Returns the HR job.

    New jobs seed as enabled=False so they do not email until an admin turns
    them on. Existing rows are not overwritten.
    """
    existing = {j.slug: j for j in AutomationJob.query.all()}
    created = False
    for spec in JOB_CATALOG:
        if not spec.get('implemented'):
            continue
        slug = spec['slug']
        if slug in existing:
            continue
        job = AutomationJob(
            slug=slug,
            enabled=(slug == HR_DAILY_EXCEL),
            schedule_hour=int(spec.get('default_hour') or 20),
            schedule_minute=int(spec.get('default_minute') or 0),
            timezone='Asia/Dubai',
            to_emails=default_backup_to() or None,
            save_to_files=True,
            send_email=True,
            sync_drive=True,
        )
        db.session.add(job)
        existing[slug] = job
        created = True
    if created:
        db.session.commit()
    hr = existing.get(HR_DAILY_EXCEL)
    if hr is None:
        raise RuntimeError('HR daily Excel job was not seeded')
    return hr
