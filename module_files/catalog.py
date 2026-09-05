"""Predictable Save-to-Files options per source module + Excel template library."""

from __future__ import annotations

MODULE_OPTIONS = {
    'manpower': {
        'label': 'Manpower Tracker',
        'folder_path_key': 'hr/manpower',
        'folder_label': 'HR / Manpower',
        'options': [
            {
                'kind': 'template',
                'label': 'Manpower template (Excel)',
                'description': 'Blank template for importing vacancies.',
            },
            {
                'kind': 'export',
                'label': 'Updated Manpower export (Excel)',
                'description': 'Current board data as an Excel workbook.',
            },
        ],
    },
    'leave': {
        'label': 'Leave Tracker',
        'folder_path_key': 'hr/leave',
        'folder_label': 'HR / Leave Tracker',
        'options': [
            {
                'kind': 'template',
                'label': 'Leave log template (Excel)',
                'description': 'Blank leave-log template for the current window.',
            },
            {
                'kind': 'export',
                'label': 'Updated Leave export (Excel)',
                'description': 'Full leave tracker workbook (employees, plans, logs).',
            },
        ],
    },
    'hiring': {
        'label': 'Hiring Documents',
        'folder_path_key': 'hr/hiring',
        'folder_label': 'HR / Hiring Docs',
        'options': [
            {
                'kind': 'template',
                'label': 'Hiring tracker template (Excel)',
                'description': 'Blank template for importing hiring candidates.',
            },
            {
                'kind': 'export',
                'label': 'Updated Hiring export (Excel)',
                'description': 'Current hiring document tracker workbook.',
            },
        ],
    },
    'procurement': {
        'label': 'Procurement',
        'folder_path_key': 'procurement',
        'folder_label': 'Procurement',
        'options': [
            {
                'kind': 'template',
                'label': 'Procurement sample Excel',
                'description': 'Sample import workbook for materials.',
            },
            {
                'kind': 'export',
                'label': 'Materials export (Excel)',
                'description': 'Current procurement materials list.',
            },
        ],
    },
    'qhsi': {
        'label': 'QHSE — Staff Compliance',
        'folder_path_key': 'qhse/staff',
        'folder_label': 'QHSE / Staff Compliance',
        'options': [
            {
                'kind': 'template',
                'label': 'Staff compliance import template (Excel)',
                'description': 'Blank template for staff compliance import.',
            },
            {
                'kind': 'export',
                'label': 'Staff compliance export (Excel)',
                'description': 'Current staff compliance records as an Excel workbook.',
            },
        ],
    },
    'mmr': {
        'label': 'Report Generation',
        'folder_path_key': 'reports/mmr',
        'folder_label': 'Reports / MMR',
        'options': [
            {
                'kind': 'export',
                'label': 'MMR chargeable report (Excel)',
                'description': 'Generate report from the last uploaded CAFM Excel (requires upload first).',
            },
        ],
    },
    'devices': {
        'label': 'Device Management',
        'folder_path_key': 'admin/devices',
        'folder_label': 'Admin / Devices',
        'options': [
            {
                'kind': 'template',
                'label': 'Device import sample (Excel)',
                'description': 'Sample workbook for bulk device import.',
            },
            {
                'kind': 'export',
                'label': 'Devices export (Excel)',
                'description': 'Current device inventory as an Excel workbook.',
            },
        ],
    },
    'technicians': {
        'label': 'Team Management — Technicians',
        'folder_path_key': 'admin/technicians',
        'folder_label': 'Admin / Technicians',
        'options': [
            {
                'kind': 'template',
                'label': 'Technicians import template (Excel)',
                'description': 'Blank template for technician bulk import.',
            },
            {
                'kind': 'export',
                'label': 'Technicians export (Excel)',
                'description': 'Current technician roster as an Excel workbook.',
            },
        ],
    },
    'dochub': {
        'label': 'DocHub',
        'folder_path_key': 'dochub',
        'folder_label': 'DocHub',
        'options': [
            {
                'kind': 'export',
                'label': 'Document library export (Excel)',
                'description': 'Current DocHub document index (title, status, category, author).',
            },
        ],
    },
    'ticketing': {
        'label': 'Service Tickets',
        'folder_path_key': 'ticketing',
        'folder_label': 'Service Tickets',
        'options': [
            {
                'kind': 'locations',
                'label': 'Location hierarchy template (Excel)',
                'description': 'Blank Property / Zone / Sub Zone / Base Unit import workbook.',
            },
        ],
    },
}

# Access flags: admin always sees all; otherwise require the listed User attribute
# (or 'access_files' / role checks applied in list_excel_templates_for_user).
EXCEL_TEMPLATES = [
    {
        'id': 'manpower',
        'module': 'manpower',
        'kind': 'template',
        'label': 'Manpower vacancies template',
        'filename': 'Manpower_Tracker_Template.xlsx',
        'description': 'Blank template for importing vacancies.',
        'module_label': 'HR / Manpower',
        'access': 'access_hiring',
    },
    {
        'id': 'leave',
        'module': 'leave',
        'kind': 'template',
        'label': 'Leave log template',
        'filename': 'Leave_Log_Template.xlsx',
        'description': 'Blank leave-log template for the current window.',
        'module_label': 'HR / Leave Tracker',
        'access': 'access_hiring',
    },
    {
        'id': 'hiring',
        'module': 'hiring',
        'kind': 'template',
        'label': 'Hiring document tracker template',
        'filename': 'Hiring_Document_Tracker_Template.xlsx',
        'description': 'Blank template for importing hiring candidates.',
        'module_label': 'HR / Hiring Docs',
        'access': 'access_hiring',
    },
    {
        'id': 'procurement',
        'module': 'procurement',
        'kind': 'template',
        'label': 'Procurement materials sample',
        'filename': 'Procurement_Import_Sample.xlsx',
        'description': 'Sample import workbook for materials.',
        'module_label': 'Procurement',
        'access': 'access_procurement_module',
    },
    {
        'id': 'qhsi',
        'module': 'qhsi',
        'kind': 'template',
        'label': 'QHSE staff compliance template',
        'filename': 'QHSE_Staff_Compliance_Import_Template.xlsx',
        'description': 'Blank template for staff compliance import.',
        'module_label': 'QHSE / Staff Compliance',
        'access': 'access_qhsi',
    },
    {
        'id': 'devices',
        'module': 'devices',
        'kind': 'template',
        'label': 'Device import sample',
        'filename': 'Device_Import_Sample.xlsx',
        'description': 'Sample workbook for bulk device import.',
        'module_label': 'Admin / Devices',
        'access': 'access_files',
    },
    {
        'id': 'technicians',
        'module': 'technicians',
        'kind': 'template',
        'label': 'Technicians import template',
        'filename': 'Technicians_Import_Template.xlsx',
        'description': 'Blank template for technician bulk import.',
        'module_label': 'Admin / Technicians',
        'access': 'access_files',
    },
    {
        'id': 'locations',
        'module': 'ticketing',
        'kind': 'locations',
        'label': 'Location hierarchy template',
        'filename': 'Location_Template.xlsx',
        'description': 'Blank Property / Zone / Sub Zone / Base Unit import workbook.',
        'module_label': 'Service Tickets',
        'access': 'access_ticketing',
    },
]


DEFAULT_FOLDER_TREE = [
    {'path_key': 'branding', 'name': 'Branding', 'parent_key': None},
    {'path_key': 'hr', 'name': 'HR', 'parent_key': None},
    {'path_key': 'hr/leave', 'name': 'Leave Tracker', 'parent_key': 'hr'},
    {'path_key': 'hr/manpower', 'name': 'Manpower', 'parent_key': 'hr'},
    {'path_key': 'hr/hiring', 'name': 'Hiring Docs', 'parent_key': 'hr'},
    {'path_key': 'procurement', 'name': 'Procurement', 'parent_key': None},
    {'path_key': 'reports', 'name': 'Reports', 'parent_key': None},
    {'path_key': 'reports/mmr', 'name': 'MMR', 'parent_key': 'reports'},
    {'path_key': 'reports/email', 'name': 'Email Automation', 'parent_key': 'reports'},
    {'path_key': 'admin', 'name': 'Admin', 'parent_key': None},
    {'path_key': 'admin/devices', 'name': 'Devices', 'parent_key': 'admin'},
    {'path_key': 'admin/technicians', 'name': 'Technicians', 'parent_key': 'admin'},
    {'path_key': 'dochub', 'name': 'DocHub', 'parent_key': None},
    {'path_key': 'ticketing', 'name': 'Service Tickets', 'parent_key': None},
    {'path_key': 'qhse', 'name': 'QHSE', 'parent_key': None},
    {'path_key': 'qhse/staff', 'name': 'Staff Compliance', 'parent_key': 'qhse'},
]


def get_module_catalog(module: str) -> dict | None:
    key = (module or '').strip().lower().replace(' ', '_').replace('-', '_')
    aliases = {
        'tickets': 'ticketing',
        'ticket': 'ticketing',
        'service_tickets': 'ticketing',
        'service_ticket': 'ticketing',
        'qhse': 'qhsi',
    }
    resolved = aliases.get(key, key)
    return MODULE_OPTIONS.get(resolved)


def get_excel_template(template_id: str) -> dict | None:
    tid = (template_id or '').strip().lower()
    for entry in EXCEL_TEMPLATES:
        if entry['id'] == tid:
            return entry
    return None


def user_can_see_excel_template(user, entry: dict) -> bool:
    """Admin sees all; others need the template's access flag (or access_files for admin templates)."""
    if not user:
        return False
    if getattr(user, 'role', None) == 'admin':
        return True
    access = entry.get('access') or ''
    if access == 'access_hiring':
        hiring_fn = getattr(user, 'has_hiring_submodule', None)
        hiring_ok = bool(hiring_fn()) if callable(hiring_fn) else bool(getattr(user, 'access_hiring', False))
        return hiring_ok or bool(getattr(user, 'access_files', False))
    if access == 'access_hr':
        return bool(getattr(user, 'access_hr', False) or getattr(user, 'access_files', False))
    if access == 'access_procurement_module':
        return bool(getattr(user, 'access_procurement_module', False) or getattr(user, 'access_files', False))
    if access == 'access_qhsi':
        return bool(getattr(user, 'access_qhsi', False) or getattr(user, 'access_files', False))
    if access == 'access_ticketing':
        return bool(getattr(user, 'access_ticketing', False) or getattr(user, 'access_files', False))
    if access == 'access_files':
        return bool(getattr(user, 'access_files', False))
    return False


def list_excel_templates_for_user(user) -> list[dict]:
    """Return public template dicts the user is allowed to see."""
    out = []
    for entry in EXCEL_TEMPLATES:
        if not user_can_see_excel_template(user, entry):
            continue
        out.append({
            'id': entry['id'],
            'module': entry['module'],
            'kind': entry['kind'],
            'label': entry['label'],
            'filename': entry['filename'],
            'description': entry['description'],
            'module_label': entry['module_label'],
        })
    return out


def list_dochub_document_options() -> list:
    """Live DocHub documents as Save-to-Files choices (kind doc:<id>)."""
    from sqlalchemy import or_

    from app.models import DocHubDocument

    docs = (
        DocHubDocument.query.filter(
            or_(DocHubDocument.inline_asset.is_(False), DocHubDocument.inline_asset.is_(None))
        )
        .order_by(DocHubDocument.updated_at.desc())
        .all()
    )
    options = []
    for d in docs:
        dtype = 'Uploaded file' if (d.doc_type or '') == 'upload' else 'Editable page'
        bits = [x for x in [(d.category or '').strip(), (d.status or '').strip(), dtype] if x]
        options.append({
            'kind': f'doc:{d.id}',
            'label': (d.title or f'Document {d.id}').strip(),
            'description': ' · '.join(bits),
        })
    return options


CLOSED_TICKET_CAP = 150


def list_closed_ticket_options(user=None) -> list:
    """Closed work orders as Save-to-Files choices (kind ticket:<id>:report|invoice)."""
    try:
        from app.models import Ticket
        from module_ticketing.routes import _can_user_view_ticket
    except Exception:
        return []

    tickets = (
        Ticket.query.filter(Ticket.status == 'closed')
        .order_by(Ticket.closed_at.desc().nullslast(), Ticket.id.desc())
        .limit(CLOSED_TICKET_CAP * 4)
        .all()
    )
    options = []
    kept = 0
    for t in tickets:
        if user is not None and not _can_user_view_ticket(user, t):
            continue
        code = (t.ticket_id or f'Ticket {t.id}').strip()
        title = (t.title or '').strip()
        closed_bit = ''
        if t.closed_at:
            try:
                closed_bit = t.closed_at.strftime('%d %b %Y')
            except Exception:
                closed_bit = ''
        desc = ' · '.join(x for x in [title, closed_bit] if x) or 'Closed work order'
        options.append({
            'kind': f'ticket:{t.id}:report',
            'label': f'{code} — Service report',
            'description': desc,
        })
        options.append({
            'kind': f'ticket:{t.id}:invoice',
            'label': f'{code} — Invoice',
            'description': desc,
        })
        kept += 1
        if kept >= CLOSED_TICKET_CAP:
            break
    return options


def expand_module_catalog(module: str, catalog: dict, user=None) -> dict:
    """Attach live item lists for modules that support picking records."""
    mod = (module or '').strip().lower().replace(' ', '_').replace('-', '_')
    if mod in ('tickets', 'ticket', 'service_tickets', 'service_ticket'):
        mod = 'ticketing'
    options = list(catalog.get('options') or [])
    try:
        if mod == 'dochub':
            options.extend(list_dochub_document_options())
        elif mod == 'ticketing':
            options.extend(list_closed_ticket_options(user))
    except Exception:
        pass
    return {**catalog, 'options': options}


def list_catalog() -> dict:
    return dict(MODULE_OPTIONS)
