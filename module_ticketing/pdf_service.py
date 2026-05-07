"""
Ticketing PDF report - HR-form style service report using ReportLab.
"""
import base64
import os
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, KeepTogether,
)


BRAND = colors.HexColor('#125435')
BRAND_LIGHT = colors.HexColor('#e7f3ec')
INK = colors.HexColor('#0f172a')
MUTED = colors.HexColor('#64748b')
HAIR = colors.HexColor('#cbd5e1')


def _img_from_data_url(data_url, max_w=70 * mm, max_h=30 * mm):
    if not data_url or ',' not in data_url:
        return None
    try:
        _, b64 = data_url.split(',', 1)
        raw = base64.b64decode(b64)
        bio = BytesIO(raw)
        img = RLImage(bio)
        # Preserve aspect ratio
        iw, ih = img.imageWidth, img.imageHeight
        if iw and ih:
            ratio = min(max_w / iw, max_h / ih)
            img.drawWidth = iw * ratio
            img.drawHeight = ih * ratio
        else:
            img.drawWidth, img.drawHeight = max_w, max_h
        return img
    except Exception:
        return None


def _img_from_file(path, max_w=80 * mm, max_h=55 * mm):
    if not path or not os.path.isfile(path):
        return None
    try:
        img = RLImage(path)
        iw, ih = img.imageWidth, img.imageHeight
        if iw and ih:
            ratio = min(max_w / iw, max_h / ih)
            img.drawWidth = iw * ratio
            img.drawHeight = ih * ratio
        else:
            img.drawWidth, img.drawHeight = max_w, max_h
        return img
    except Exception:
        return None


def build_ticket_pdf(ticket, out_path):
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle('h_title', parent=styles['Heading1'],
                             textColor=BRAND, fontSize=18, leading=22, spaceAfter=4)
    h_sub = ParagraphStyle('h_sub', parent=styles['Normal'],
                           textColor=MUTED, fontSize=9, leading=12, spaceAfter=8)
    h_section = ParagraphStyle('h_section', parent=styles['Heading2'],
                               textColor=BRAND, fontSize=12, leading=16,
                               spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle('body', parent=styles['Normal'],
                          textColor=INK, fontSize=10, leading=14)
    label = ParagraphStyle('label', parent=styles['Normal'],
                           textColor=MUTED, fontSize=8, leading=11)

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f'Service Report - {ticket.ticket_no}',
    )
    story = []

    # ---- Header band ----
    closed_str = ticket.closed_at.strftime('%d %b %Y, %H:%M') if ticket.closed_at else '-'
    created_str = ticket.created_at.strftime('%d %b %Y, %H:%M') if ticket.created_at else '-'
    header = Table([
        [Paragraph('<b>INJAAZ</b><br/>Service Report', ParagraphStyle(
            'brand', parent=body, textColor=colors.white, fontSize=14, leading=17)),
         Paragraph(
             f'<font color="#ffffff"><b>{ticket.ticket_no}</b></font><br/>'
             f'<font color="#d1fae5" size=8>Closed: {closed_str}</font>',
             body)]
    ], colWidths=[110 * mm, 64 * mm])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))

    # ---- Title / status row ----
    story.append(Paragraph(ticket.title or '-', h_title))
    story.append(Paragraph(
        f'Project: <b>{ticket.project_name or "-"}</b> &nbsp; | &nbsp; '
        f'Priority: <b>{(ticket.priority or "-").upper()}</b> &nbsp; | &nbsp; '
        f'Status: <b>{(ticket.status or "-").upper()}</b> &nbsp; | &nbsp; '
        f'Created: {created_str}', h_sub))

    # ---- Reporter & classification ----
    def kv(label_text, value):
        return [Paragraph(label_text, label),
                Paragraph(str(value if value not in (None, '') else '-'), body)]

    info_rows = [
        kv('Reporter', ticket.reporter_name) + kv('Contact', ticket.reporter_contact),
        kv('Service Group', ticket.service_group) + kv('Category', ticket.category),
        kv('Fault Type', ticket.fault_type) +
        kv('Chargeable', 'Yes' if ticket.chargeable else 'No'),
        kv('Assigned To', ticket.assignee.full_name if ticket.assignee else '-') +
        kv('Closed By', ticket.closed_by.full_name if ticket.closed_by else '-'),
    ]
    t = Table(info_rows, colWidths=[26 * mm, 60 * mm, 26 * mm, 62 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), BRAND_LIGHT),
        ('BACKGROUND', (2, 0), (2, -1), BRAND_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, HAIR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    # ---- Location ----
    story.append(Paragraph('Location', h_section))
    loc = Table([
        [Paragraph('Property', label), Paragraph('Zone', label),
         Paragraph('Sub-zone', label), Paragraph('Base Unit', label)],
        [Paragraph(ticket.loc_property or '-', body),
         Paragraph(ticket.loc_zone or '-', body),
         Paragraph(ticket.loc_sub_zone or '-', body),
         Paragraph(ticket.loc_base_unit or '-', body)],
    ], colWidths=[43.5 * mm] * 4)
    loc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, HAIR),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(loc)

    # ---- Work description ----
    story.append(Paragraph('Work Description', h_section))
    story.append(Paragraph((ticket.description or '-').replace('\n', '<br/>'), body))

    # ---- Manpower ----
    story.append(Paragraph('Manpower Used', h_section))
    labor_rows = [['Worker', 'Duration', 'Rate', 'Cost', 'Notes']]
    for entry in ticket.labor_entries:
        from app.models import _format_duration
        labor_rows.append([
            entry.worker_name or '-',
            _format_duration(entry.duration_minutes),
            f'{entry.hourly_rate:.2f}' if entry.hourly_rate else '-',
            f'{entry.cost:.2f}' if entry.cost else '-',
            (entry.notes or '')[:40],
        ])
    if len(labor_rows) == 1:
        labor_rows.append(['-', '-', '-', '-', '-'])
    lt = Table(labor_rows, colWidths=[40 * mm, 25 * mm, 25 * mm, 25 * mm, 59 * mm])
    lt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, HAIR),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(lt)

    # ---- Materials ----
    story.append(Paragraph('Materials Used', h_section))
    mat_rows = [['Material', 'Source', 'Qty', 'Unit', 'Unit Price', 'Cost']]
    for m in ticket.material_entries:
        mat_rows.append([
            m.name,
            'New' if m.is_new else ('Procurement' if m.procurement_ref else '-'),
            f'{m.quantity:g}',
            m.unit or '-',
            f'{m.unit_price:.2f}' if m.unit_price else '-',
            f'{m.cost:.2f}' if m.cost else '-',
        ])
    if len(mat_rows) == 1:
        mat_rows.append(['-'] * 6)
    mt = Table(mat_rows, colWidths=[55 * mm, 25 * mm, 18 * mm, 22 * mm, 25 * mm, 29 * mm])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, HAIR),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(mt)

    # ---- Cost summary ----
    story.append(Paragraph('Cost Summary', h_section))
    total = (ticket.labor_cost_total or 0) + (ticket.material_cost_total or 0)
    cost_tbl = Table([
        ['Manpower', 'Materials', 'Projected', 'Total'],
        [f'{(ticket.labor_cost_total or 0):.2f}',
         f'{(ticket.material_cost_total or 0):.2f}',
         f'{(ticket.projected_price or 0):.2f}',
         f'{total:.2f}'],
    ], colWidths=[43.5 * mm] * 4)
    cost_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_LIGHT),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, HAIR),
        ('TEXTCOLOR', (3, 1), (3, 1), BRAND),
        ('FONTNAME', (3, 1), (3, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(cost_tbl)

    # ---- Notes (live conversation log) ----
    notes = ticket.notes.all() if hasattr(ticket.notes, 'all') else list(ticket.notes)
    if notes:
        story.append(Paragraph('Activity / Live Notes', h_section))
        for n in notes:
            ts = n.created_at.strftime('%d %b %Y %H:%M') if n.created_at else ''
            story.append(Paragraph(
                f'<b>{n.author_name or "Unknown"}</b> '
                f'<font color="#64748b" size=8>{ts}</font>', body))
            story.append(Paragraph(
                (n.body or '').replace('\n', '<br/>'), body))
            story.append(Spacer(1, 4))

    # ---- Closure summary ----
    if ticket.closure_summary:
        story.append(Paragraph('Closure Summary', h_section))
        story.append(Paragraph(
            ticket.closure_summary.replace('\n', '<br/>'), body))

    # ---- Signatures ----
    story.append(Paragraph('Signatures', h_section))
    req_img = _img_from_data_url(ticket.requester_signature)
    tech_img = _img_from_data_url(ticket.technician_signature)
    sig_row = [
        [Paragraph('Requester', label),
         Paragraph('Technician', label)],
        [req_img or Paragraph('<i>not signed</i>', body),
         tech_img or Paragraph('<i>not signed</i>', body)],
        [Paragraph(ticket.reporter_name or '-', body),
         Paragraph(ticket.assignee.full_name if ticket.assignee else '-', body)],
    ]
    sig_tbl = Table(sig_row, colWidths=[87 * mm, 87 * mm])
    sig_tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, HAIR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_LIGHT),
    ]))
    story.append(KeepTogether(sig_tbl))

    # ---- Photos ----
    images = list(ticket.images.all() if hasattr(ticket.images, 'all') else ticket.images)
    if images:
        story.append(PageBreak())
        story.append(Paragraph('Photos', h_section))
        from flask import current_app
        upload_root = current_app.config.get('UPLOADS_DIR') or \
                      os.path.join(current_app.root_path, 'generated', 'uploads')
        rows = []
        row = []
        for img in images:
            full = os.path.join(upload_root, img.file_path)
            obj = _img_from_file(full)
            if obj is None:
                continue
            row.append(obj)
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            row.append(Paragraph('', body))
            rows.append(row)
        if rows:
            it = Table(rows, colWidths=[87 * mm, 87 * mm])
            it.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(it)

    doc.build(story)
    return out_path
