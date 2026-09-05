"""Styled Kynvera Excel templates for Admin device and technician imports."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

from common.kynvera_excel_brand import (
    InstructionSpec,
    apply_column_widths,
    write_data_row,
    write_header_row,
    write_instructions_sheet,
)

DEVICE_HEADERS = (
    'Device Name',
    'Device Type',
    'OS',
    'Status',
    'Health',
    'Assigned User Email',
    'Serial / Asset Tag',
)

DEVICE_SAMPLE_ROWS = (
    ('LAPTOP-HQ-001', 'Laptop', 'Windows 11 Pro', 'online', 96, 'admin@injaaz.ae', 'AST-10001'),
    ('DESKTOP-FIN-014', 'Desktop', 'Windows 10', 'idle', 88, '', 'AST-10002'),
    ('MOBILE-OPS-022', 'Mobile', 'Android 15', 'online', 93, '', 'AST-10003'),
    ('TABLET-QA-005', 'Tablet', 'iOS 18', 'update', 72, '', 'AST-10004'),
    ('SERVER-DC-002', 'Server', 'Ubuntu 24.04', 'online', 91, '', 'AST-10005'),
    ('LAPTOP-BD-011', 'Laptop', 'macOS Sequoia', 'offline', 54, '', 'AST-10006'),
    ('DESKTOP-HR-018', 'Desktop', 'Windows 11', 'idle', 84, '', 'AST-10007'),
    ('LAPTOP-ENG-031', 'Laptop', 'Windows 11', 'online', 97, '', 'AST-10008'),
    ('MOBILE-FIELD-040', 'Mobile', 'Android 14', 'update', 67, '', 'AST-10009'),
    ('TABLET-MEET-003', 'Tablet', 'iPadOS 18', 'online', 89, '', 'AST-10010'),
)

TECHNICIAN_HEADERS = (
    'Employee ID',
    'Full Name',
    'Designation',
    'Department',
    'Specialization',
    'Phone',
    'Email',
    'Salary',
    'Joining Date',
    'Status',
    'Supervisor User ID',
    'Notes',
)

TECHNICIAN_EXAMPLE_ROW = (
    'EMP-001',
    'John Smith',
    'HVAC Technician',
    'MEP',
    'Air Conditioning',
    '+971-50-000-0000',
    'john@example.com',
    5000,
    '2024-01-15',
    'active',
    '',
    'Example row — replace or delete before importing',
)


def build_devices_sample_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Devices'
    write_header_row(ws, DEVICE_HEADERS)
    for i, row in enumerate(DEVICE_SAMPLE_ROWS, start=2):
        write_data_row(ws, i, row, example=True)
    apply_column_widths(ws, [20, 14, 18, 12, 10, 28, 20])

    type_dv = DataValidation(
        type='list',
        formula1='"Laptop,Desktop,Mobile,Tablet,Server,Other"',
        allow_blank=True,
        showDropDown=False,
    )
    type_dv.add('B2:B500')
    ws.add_data_validation(type_dv)
    status_dv = DataValidation(
        type='list',
        formula1='"online,offline,idle,update"',
        allow_blank=True,
        showDropDown=False,
    )
    status_dv.add('D2:D500')
    ws.add_data_validation(status_dv)

    write_instructions_sheet(wb, InstructionSpec(
        title='Device import sample',
        module_label='Admin / Devices',
        about=(
            'Bulk-create devices in Admin → Devices. Each row is one device.',
            'Device Name is required. Duplicate name + serial combinations are skipped.',
        ),
        how_to=(
            'Open the Devices sheet. Keep the coral header row.',
            'Replace the sample rows with your devices, or add new rows below them.',
            'Assigned User Email must match an existing user if you want the device assigned.',
            'Save as .xlsx and click Import Excel on the Devices page.',
        ),
        columns=(
            ('Device Name', 'Required. Also accepted as Name or Device.'),
            ('Device Type', 'Optional. Laptop, Desktop, Mobile, Tablet, Server, or Other.'),
            ('OS', 'Optional. Also accepted as Operating System.'),
            ('Status', 'Optional. online, offline, idle, or update.'),
            ('Health', 'Optional 0–100 number. Also accepted as Health Percent.'),
            ('Assigned User Email', 'Optional. Must match an existing user email to assign.'),
            ('Serial / Asset Tag', 'Optional unique serial or asset tag.'),
        ),
        example_headers=DEVICE_HEADERS,
        example_rows=DEVICE_SAMPLE_ROWS[:2],
        import_rules=(
            'Rows with a blank Device Name are skipped.',
            'Duplicates (same name + serial) are skipped.',
            'Header names are matched case-insensitively with common aliases.',
        ),
    ))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_technicians_template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Technicians'
    write_header_row(ws, TECHNICIAN_HEADERS)
    write_data_row(ws, 2, TECHNICIAN_EXAMPLE_ROW, example=True)
    apply_column_widths(ws, [16, 28, 24, 22, 22, 18, 28, 12, 16, 12, 18, 36])

    status_dv = DataValidation(
        type='list',
        formula1='"active,inactive,on_leave"',
        allow_blank=True,
        showDropDown=False,
    )
    status_dv.add('J2:J500')
    ws.add_data_validation(status_dv)

    write_instructions_sheet(wb, InstructionSpec(
        title='Technicians import template',
        module_label='Admin / Technicians',
        about=(
            'Bulk-create technicians (staff roster) from Excel. Each row is one person.',
            'Employee ID and Full Name are required. Duplicate Employee IDs are skipped.',
        ),
        how_to=(
            'Open the Technicians sheet. Keep the coral header row.',
            'Replace the example row and add one row per technician.',
            'Status defaults to active if blank. Salary must be a number with no currency symbol.',
            'Save as .xlsx and click Import Excel on the Technicians page.',
        ),
        columns=(
            ('Employee ID', 'Required. Unique identifier (e.g. EMP-001). Duplicates are skipped.'),
            ('Full Name', 'Required.'),
            ('Designation', 'Job title (e.g. HVAC Technician, Plumber, Electrician).'),
            ('Department', 'Team (e.g. MEP, Civil, Cleaning).'),
            ('Specialization', 'Area of expertise (e.g. Air Conditioning, Electrical).'),
            ('Phone', 'Optional contact number.'),
            ('Email', 'Optional.'),
            ('Salary', 'Optional monthly salary — numbers only, no currency symbol.'),
            ('Joining Date', 'Optional. YYYY-MM-DD or DD/MM/YYYY.'),
            ('Status', 'active, inactive, or on_leave. Defaults to active if blank.'),
            ('Supervisor User ID', 'Optional numeric user.id of an active Supervisor / Ops Manager / GM.'),
            ('Notes', 'Optional.'),
        ),
        example_headers=TECHNICIAN_HEADERS,
        example_rows=(TECHNICIAN_EXAMPLE_ROW,),
        import_rules=(
            'Rows missing Employee ID or Full Name are skipped.',
            'Existing Employee IDs are skipped (not updated).',
            'Invalid supervisor_user_id skips that row; other rows still import.',
        ),
    ))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
