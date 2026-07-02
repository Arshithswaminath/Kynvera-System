"""PDF and Excel reports for QHSA unified inspections."""
import logging
import os
from datetime import datetime
from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from common.utils import get_image_for_pdf

logger = logging.getLogger(__name__)

_DEPT_LABEL = {'hvac': 'HVAC & MEP', 'civil': 'Civil Works', 'cleaning': 'Cleaning Services'}


def _items_from_record(record):
    return record.get('items') or []


def create_excel_report(submission_record, output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'QHSA Inspection'
    header_fill = PatternFill('solid', fgColor='125435')
    header_font = Font(color='FFFFFF', bold=True)
    ws.append(['QHSA Site Inspection Report'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append([])
    meta = [
        ('Project', submission_record.get('project_name', '')),
        ('Visit Date', submission_record.get('visit_date', '')),
        ('Department', _DEPT_LABEL.get(submission_record.get('department'), submission_record.get('department'))),
        ('Inspector', submission_record.get('inspector_name', '')),
        ('Location', submission_record.get('location', '')),
        ('Summary', submission_record.get('summary', '')),
    ]
    for label, val in meta:
        ws.append([label, val])
    ws.append([])
    ws.append(['#', 'Area / System', 'Equipment', 'Severity', 'Description', 'Photos'])
    for c in range(1, 7):
        cell = ws.cell(row=ws.max_row, column=c)
        cell.fill = header_fill
        cell.font = header_font
    for i, item in enumerate(_items_from_record(submission_record), 1):
        area = item.get('area') or item.get('system') or item.get('trade') or ''
        equip = item.get('equipment') or item.get('zone') or ''
        photos = len(item.get('photos') or [])
        ws.append([
            i,
            area,
            equip,
            item.get('severity', ''),
            (item.get('description') or '')[:500],
            photos,
        ])
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    wb.save(output_path)
    return output_path


def create_pdf_report(submission_record, output_path):
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#d21725'))
    body = []
    body.append(Paragraph('QHSA Site Inspection', title_style))
    body.append(Spacer(1, 12))
    meta_data = [
        ['Project', submission_record.get('project_name', '-')],
        ['Date', submission_record.get('visit_date', '-')],
        ['Department', _DEPT_LABEL.get(submission_record.get('department'), '-')],
        ['Inspector', submission_record.get('inspector_name', '-')],
    ]
    t = Table(meta_data, colWidths=[4 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f5ee')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    body.append(t)
    body.append(Spacer(1, 16))
    if submission_record.get('summary'):
        body.append(Paragraph(f"<b>Summary:</b> {submission_record.get('summary')}", styles['Normal']))
        body.append(Spacer(1, 12))
    for i, item in enumerate(_items_from_record(submission_record), 1):
        label = item.get('area') or item.get('system') or item.get('trade') or 'Item'
        equip = item.get('equipment') or item.get('zone') or ''
        body.append(Paragraph(f"<b>{i}. {label}</b> — {equip}", styles['Heading3']))
        if item.get('description'):
            body.append(Paragraph(item['description'], styles['Normal']))
        for ph in (item.get('photos') or [])[:4]:
            url = ph.get('url') if isinstance(ph, dict) else ph
            if not url:
                continue
            try:
                img_data = get_image_for_pdf(url)
                if img_data:
                    body.append(Image(BytesIO(img_data), width=8 * cm, height=6 * cm))
            except Exception as e:
                logger.debug('PDF image skip: %s', e)
        body.append(Spacer(1, 10))
    doc.build(body)
    return output_path
