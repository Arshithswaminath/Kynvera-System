"""Predictable Save-to-Files options per source module."""

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
        ],
    },
    'mmr': {
        'label': 'Report Generation (MMR)',
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
        ],
    },
}

DEFAULT_FOLDER_TREE = [
    {'path_key': 'hr', 'name': 'HR', 'parent_key': None},
    {'path_key': 'hr/leave', 'name': 'Leave Tracker', 'parent_key': 'hr'},
    {'path_key': 'hr/manpower', 'name': 'Manpower', 'parent_key': 'hr'},
    {'path_key': 'hr/hiring', 'name': 'Hiring Docs', 'parent_key': 'hr'},
    {'path_key': 'procurement', 'name': 'Procurement', 'parent_key': None},
    {'path_key': 'qhse', 'name': 'QHSE', 'parent_key': None},
    {'path_key': 'qhse/staff', 'name': 'Staff Compliance', 'parent_key': 'qhse'},
    {'path_key': 'reports', 'name': 'Reports', 'parent_key': None},
    {'path_key': 'reports/mmr', 'name': 'MMR', 'parent_key': 'reports'},
    {'path_key': 'admin', 'name': 'Admin', 'parent_key': None},
    {'path_key': 'admin/devices', 'name': 'Devices', 'parent_key': 'admin'},
    {'path_key': 'admin/technicians', 'name': 'Technicians', 'parent_key': 'admin'},
]


def get_module_catalog(module: str) -> dict | None:
    return MODULE_OPTIONS.get((module or '').strip().lower())


def list_catalog() -> dict:
    return MODULE_OPTIONS
