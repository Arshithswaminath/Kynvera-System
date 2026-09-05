"""Styled Kynvera Excel sample for procurement material import."""
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

MATERIALS_HEADERS = (
    'Material Name',
    'Category',
    'Description',
    'Unit',
    'Quantity',
    'Unit Price',
    'Supplier',
    'Notes',
)

SAMPLE_ROWS = (
    ('Office Paper A4 Ream', 'Stationery', '500 sheets per ream', 'ream', 50, 12.50, 'Gulf Paper Co', 'Monthly supply'),
    ('Printer Toner Cartridge', 'IT Supplies', 'Laser printer compatible', 'pcs', 10, 85.00, 'Tech Supplies LLC', ''),
    ('Cleaning Detergent 5L', 'Cleaning', 'Multi-surface cleaner', 'bottle', 20, 28.00, 'CleanPro', 'Bulk order'),
    ('LED Bulb 18W', 'Electrical', 'E27 fitting, warm white', 'pcs', 100, 4.25, 'Lighting World', ''),
    ('Hand Soap Refill 5L', 'Hygiene', 'Dispenser refill', 'bottle', 15, 22.00, 'Hygiene Plus', 'Washrooms'),
    ('Safety Gloves Box', 'PPE', '100 pairs per box', 'box', 5, 35.00, 'Safety First', 'Site use'),
    ('Paint 20L White', 'Paints', 'Interior emulsion', 'can', 8, 120.00, 'Paint Depot', 'Tower A'),
)

MATERIALS_SHEET = 'Materials'


def build_procurement_sample_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = MATERIALS_SHEET
    write_header_row(ws, MATERIALS_HEADERS)
    for i, row in enumerate(SAMPLE_ROWS, start=2):
        write_data_row(ws, i, row, example=True)
    apply_column_widths(ws, [28, 16, 28, 10, 12, 12, 20, 22])

    unit_dv = DataValidation(
        type='list',
        formula1='"pcs,box,ream,bottle,can,kg,litre,pack,set,roll"',
        allow_blank=True,
        showDropDown=False,
    )
    unit_dv.add('D2:D500')
    ws.add_data_validation(unit_dv)

    write_instructions_sheet(wb, InstructionSpec(
        title='Procurement materials sample',
        module_label='Procurement',
        about=(
            'Sample import workbook for materials. Each row becomes one material on the Procurement dashboard.',
            'Material Name is required. Quantity and Unit Price should be numbers (no currency symbol).',
        ),
        how_to=(
            'Open the Materials sheet. Keep the coral header row.',
            'Replace the sample rows with your materials, or add new rows below them.',
            'Use a numeric Quantity and Unit Price. Unit can be pcs, box, ream, bottle, can, kg, litre, pack, set, or roll.',
            'Save as .xlsx and click Import Excel on the Procurement materials page.',
        ),
        columns=(
            ('Material Name', 'Required. Also accepted as Material, Item, Item Name, or Name.'),
            ('Category', 'Optional. Grouping such as Stationery, PPE, Electrical.'),
            ('Description', 'Optional. Also accepted as Desc.'),
            ('Unit', 'Optional. Unit of measure.'),
            ('Quantity', 'Optional number. Also accepted as Qty.'),
            ('Unit Price', 'Optional number (AED). Also accepted as Price or Rate. No currency symbol.'),
            ('Supplier', 'Optional. Also accepted as Vendor.'),
            ('Notes', 'Optional. Also accepted as Remarks or Comments.'),
        ),
        example_headers=MATERIALS_HEADERS,
        example_rows=SAMPLE_ROWS[:2],
        import_rules=(
            'Rows with a blank Material Name are skipped.',
            'Each imported row is created as a new material (this sample does not upsert by name).',
            'Header names are matched case-insensitively with common aliases.',
        ),
    ))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
