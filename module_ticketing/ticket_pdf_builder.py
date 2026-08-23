"""
PDF report builder for ticketing / work order module.
Uses ReportLab with Kynvera branding.
"""
import io
import os
import logging
from datetime import datetime, timezone

from module_ticketing.tz_utils import to_gst

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage, KeepTogether,
)
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

from common import kynvera_pdf_brand as brand

logger = logging.getLogger(__name__)

# Brand colours — Kynvera coral + neutrals
BRAND_DARK = brand.TEXT_DARK
BRAND_BLUE = brand.PRIMARY
BRAND_LIGHT = brand.SOFT_WASH
BRAND_BORDER = brand.HAIRLINE
PRIORITY_COLORS = {
    'critical': colors.HexColor('#dc2626'),
    'high': colors.HexColor('#ea580c'),
    'medium': colors.HexColor('#ca8a04'),
    'low': colors.HexColor('#16a34a'),
}
STATUS_COLORS = {
    'open': brand.PRIMARY_DARK,
    'pending_supervisor': colors.HexColor('#7c3aed'),
    'in_progress': colors.HexColor('#7c3aed'),
    'pending_parts': colors.HexColor('#ca8a04'),
    'pending_verification': colors.HexColor('#d97706'),
    'resolved': colors.HexColor('#16a34a'),
    'closed': colors.HexColor('#374151'),
}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


class _TicketPDFCanvas(Canvas):
    """Canvas with Kynvera header chrome and page numbering."""

    def __init__(self, *args, **kwargs):
        self._logo_path = kwargs.pop('logo_path', None)
        self._ticket_id = kwargs.pop('ticket_id', '')
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page(num_pages)
            super().showPage()
        super().save()

    def _draw_page(self, num_pages):
        self.saveState()
        brand.draw_page_chrome(
            self,
            self._pageNumber,
            num_pages,
            report_title=self._ticket_id or 'Work Order',
            left_margin=MARGIN,
            right_margin=MARGIN,
            footer_left=brand.FOOTER_CONFIDENTIAL,
            header_title='Work Order Report',
        )
        self.restoreState()


def _styles():
    base = getSampleStyleSheet()
    heading = ParagraphStyle('TicketH2', parent=base['Heading2'],
                              textColor=BRAND_DARK, spaceAfter=4,
                              spaceBefore=10, fontSize=11)
    normal = ParagraphStyle('TicketNormal', parent=base['Normal'],
                             fontSize=9, leading=13, textColor=brand.TEXT_DARK)
    small = ParagraphStyle('TicketSmall', parent=base['Normal'],
                            fontSize=8, leading=11, textColor=brand.TEXT_MUTED)
    bold = ParagraphStyle('TicketBold', parent=base['Normal'],
                          fontSize=9, leading=13, fontName='Helvetica-Bold',
                          textColor=brand.TEXT_DARK)
    center = ParagraphStyle('TicketCenter', parent=base['Normal'],
                             fontSize=9, alignment=TA_CENTER)
    return heading, normal, small, bold, center


def _section_header(title: str, h_style) -> list:
    return [
        HRFlowable(width='100%', thickness=1.2, color=brand.PRIMARY, spaceAfter=2),
        Paragraph(title, h_style),
    ]


def _kv_table(pairs: list, normal, bold, col_widths=None) -> Table:
    """Build a two-column key-value table."""
    col_widths = col_widths or [55 * mm, PAGE_W - 2 * MARGIN - 55 * mm]
    data = [[Paragraph(k, bold), Paragraph(str(v) if v else '—', normal)] for k, v in pairs]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, -1), brand.SOFT_WASH),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, brand.SURFACE_ALT]),
        ('GRID', (0, 0), (-1, -1), 0.4, brand.HAIRLINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def build_ticket_pdf(ticket, notes, images, materials, manpower_entries, output_stream, location_map=None):
    """Main PDF builder entry point."""
    heading, normal, small, bold, center = _styles()

    logo_path = brand.resolve_logo_path(prefer_wordmark=True)

    doc = SimpleDocTemplate(
        output_stream,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=28 * mm, bottomMargin=20 * mm,
        title=f'Work Order {ticket.ticket_id}',
        author=brand.PDF_AUTHOR,
    )

    story = []
    avail_w = PAGE_W - 2 * MARGIN

    # ── Title block ──────────────────────────────────────────────────────────
    pri_color = PRIORITY_COLORS.get(ticket.priority, BRAND_BLUE)
    sta_color = STATUS_COLORS.get(ticket.status, BRAND_BLUE)

    title_data = [[
        Paragraph(f'<font color="#191b23"><b>{ticket.ticket_id}</b></font>', ParagraphStyle(
            'TID', parent=normal, fontSize=14)),
        Paragraph(f'<font color="{pri_color.hexval()}">'
                  f'<b>{ticket.priority.upper()}</b></font>', ParagraphStyle(
            'TPri', parent=normal, fontSize=10, alignment=TA_CENTER)),
        Paragraph(f'<font color="{sta_color.hexval()}">'
                  f'<b>{ticket.status.replace("_", " ").upper()}</b></font>', ParagraphStyle(
            'TSta', parent=normal, fontSize=10, alignment=TA_RIGHT)),
    ]]
    title_tbl = Table(title_data, colWidths=[avail_w * 0.55, avail_w * 0.22, avail_w * 0.23])
    title_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.8, brand.PRIMARY),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(title_tbl)
    story.append(Paragraph(ticket.title, ParagraphStyle(
        'TTitle', parent=normal, fontSize=13, fontName='Helvetica-Bold',
        textColor=BRAND_DARK, spaceAfter=4, spaceBefore=6)))
    story.append(Spacer(1, 4))

    # ── Ticket Info ──────────────────────────────────────────────────────────
    story += _section_header('Ticket Information', heading)
    created_str = to_gst(ticket.created_at).strftime('%d %b %Y %H:%M') + ' GST' if ticket.created_at else '—'
    closed_str = to_gst(ticket.closed_at).strftime('%d %b %Y %H:%M') + ' GST' if ticket.closed_at else '—'
    story.append(_kv_table([
        ('Project', ticket.project),
        ('Service Group', ticket.service_group),
        ('Category', ticket.category),
        ('Fault Type', ticket.fault_type),
        ('Priority', ticket.priority.upper()),
        ('Status', ticket.status.replace('_', ' ').upper()),
        ('Reported By', ticket.reporter.full_name if ticket.reporter else '—'),
        ('Supervisor', ticket.supervisor.full_name if getattr(ticket, 'supervisor', None) else 'Not assigned'),
        ('Technician', ticket.technician.full_name if getattr(ticket, 'technician', None) else 'Not assigned'),
        ('Created', created_str),
        ('Closed', closed_str),
    ], normal, bold))
    story.append(Spacer(1, 6))

    # ── Location ─────────────────────────────────────────────────────────────
    loc_pairs = []
    if any([ticket.property_name, ticket.zone, ticket.sub_zone, ticket.base_unit]):
        loc_pairs = [
            ('Property', ticket.property_name or '—'),
            ('Zone', ticket.zone or '—'),
            ('Sub Zone', ticket.sub_zone or '—'),
            ('Base Unit', ticket.base_unit or '—'),
        ]
    pin = location_map or {}
    lat, lng = pin.get('lat'), pin.get('lng')
    if lat is not None and lng is not None:
        loc_pairs.append(('Map pin', f'{float(lat):.6f}, {float(lng):.6f}'))
        source = pin.get('source')
        if source:
            loc_pairs.append(('Pin source', 'Base unit' if source == 'unit' else source.replace('_', ' ').title()))
    if loc_pairs:
        story += _section_header('Location', heading)
        story.append(_kv_table(loc_pairs, normal, bold))
        story.append(Spacer(1, 6))

    # ── Work Description ──────────────────────────────────────────────────────
    story += _section_header('Work Description', heading)
    story.append(Paragraph(ticket.work_description or '—', normal))
    story.append(Spacer(1, 6))

    # ── Manpower ─────────────────────────────────────────────────────────────
    if manpower_entries:
        story += _section_header('Manpower Used', heading)
        mp_data = [['Worker', 'Hours', 'Rate/hr (AED)', 'Total (AED)', 'Date']]
        for e in manpower_entries:
            mp_data.append([
                e.worker_name,
                _fmt_hours(e.hours),
                f'{e.rate_per_hour:.2f}' if e.rate_per_hour else '—',
                f'{e.total_cost:.2f}' if e.total_cost else '—',
                e.work_date.strftime('%d %b %Y') if e.work_date else '—',
            ])
        mp_tbl = Table(mp_data, colWidths=[avail_w * 0.28, avail_w * 0.14,
                                           avail_w * 0.18, avail_w * 0.18, avail_w * 0.22])
        mp_tbl.setStyle(_data_table_style())
        story.append(mp_tbl)
        mp_total = sum(e.total_cost or 0 for e in manpower_entries)
        story.append(Paragraph(
            f'<b>Manpower Subtotal: AED {mp_total:.2f}</b>',
            ParagraphStyle('sub', parent=normal, alignment=TA_RIGHT, spaceBefore=4)))
        story.append(Spacer(1, 6))

    # ── Materials ─────────────────────────────────────────────────────────────
    if materials:
        story += _section_header('Materials Used', heading)
        mat_data = [['Material', 'Qty', 'Unit', 'Unit Price (AED)', 'Total (AED)']]
        for m in materials:
            mat_data.append([
                m.material_name,
                str(m.quantity),
                m.unit or '—',
                f'{m.unit_price:.2f}',
                f'{m.total_price:.2f}',
            ])
        mat_tbl = Table(mat_data, colWidths=[avail_w * 0.34, avail_w * 0.10,
                                             avail_w * 0.12, avail_w * 0.22, avail_w * 0.22])
        mat_tbl.setStyle(_data_table_style())
        story.append(mat_tbl)
        mat_total = sum(m.total_price or 0 for m in materials)
        story.append(Paragraph(
            f'<b>Materials Subtotal: AED {mat_total:.2f}</b>',
            ParagraphStyle('sub2', parent=normal, alignment=TA_RIGHT, spaceBefore=4)))
        story.append(Spacer(1, 6))

    # ── Cost Summary with Pricing Breakdown ───────────────────────────────────
    story += _section_header('Cost Summary', heading)
    mp_total = sum(e.total_cost or 0 for e in manpower_entries)
    mat_total = sum(m.total_price or 0 for m in materials)
    base_cost = mp_total + mat_total

    actual_price = round(base_cost, 2)

    markup_pct = getattr(ticket, 'markup_pct', None)
    selling_price = getattr(ticket, 'selling_price', None)

    cost_data = [
        ['Manpower Total', f'AED {mp_total:.2f}'],
        ['Materials Total', f'AED {mat_total:.2f}'],
        ['Actual Price (MP + Materials)', f'AED {actual_price:.2f}'],
    ]
    if ticket.projected_cost:
        cost_data.insert(0, ['Projected Cost', f'AED {ticket.projected_cost:.2f}'])

    cost_tbl = Table(cost_data, colWidths=[avail_w * 0.50, avail_w * 0.50])
    cost_style = [
        ('GRID', (0, 0), (-1, -1), 0.4, brand.HAIRLINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, brand.SURFACE_ALT]),
    ]
    actual_row_idx = len(cost_data) - 1
    cost_style += [
        ('BACKGROUND', (0, actual_row_idx), (-1, actual_row_idx), BRAND_LIGHT),
        ('FONTNAME', (0, actual_row_idx), (-1, actual_row_idx), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, actual_row_idx), (-1, actual_row_idx), BRAND_DARK),
        ('LINEABOVE', (0, actual_row_idx), (-1, actual_row_idx), 1.0, brand.PRIMARY),
    ]
    cost_tbl.setStyle(TableStyle(cost_style))
    story.append(cost_tbl)

    if markup_pct is not None:
        story.append(Spacer(1, 6))
        markup_banner_style = [
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef3c7')),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#f59e0b')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]
        markup_amt = round(actual_price * markup_pct / 100.0, 2)
        sell_price = selling_price or round(actual_price + markup_amt, 2)

        markup_data = [
            [Paragraph('<b>INTERNAL PRICING — NOT FOR CLIENT DISTRIBUTION</b>',
                       ParagraphStyle('warn', parent=small, textColor=colors.HexColor('#92400e'),
                                      fontSize=7.5, fontName='Helvetica-Bold')), ''],
            ['Actual Price (base for markup)', f'AED {actual_price:.2f}'],
            [f'Markup Applied ({markup_pct:.0f}%)', f'AED {markup_amt:.2f}'],
            ['SELLING PRICE', f'AED {sell_price:.2f}'],
        ]
        markup_tbl = Table(markup_data, colWidths=[avail_w * 0.60, avail_w * 0.40])
        markup_tbl.setStyle(TableStyle(markup_banner_style + [
            ('SPAN', (0, 0), (-1, 0)),
            ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 3), (-1, 3), brand.TEXT_DARK),
            ('FONTSIZE', (0, 3), (-1, 3), 10),
            ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#fde68a')),
        ]))
        story.append(markup_tbl)
    else:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            '<i>Markup not yet set. Supervisor will apply before closing.</i>',
            ParagraphStyle('nomk', parent=small, textColor=brand.TEXT_MUTED)))

    story.append(Spacer(1, 4))

    sup_name = ticket.supervisor.full_name if getattr(ticket, 'supervisor', None) else '—'
    tech_name = ticket.technician.full_name if getattr(ticket, 'technician', None) else '—'
    if sup_name != '—' or tech_name != '—':
        story.append(_kv_table([
            ('Supervisor', sup_name),
            ('Technician', tech_name),
        ], normal, bold))
    story.append(Spacer(1, 6))

    if notes:
        story += _section_header('Activity Log', heading)
        for note in notes:
            dt_str = to_gst(note.created_at).strftime('%d %b %Y %H:%M') if note.created_at else ''
            author = note.author.full_name if note.author else 'Unknown'
            story.append(Paragraph(
                f'<b>{author}</b> <font color="#9498a3">{dt_str}</font>',
                ParagraphStyle('NoteH', parent=small, spaceBefore=4)))
            story.append(Paragraph(note.content, ParagraphStyle(
                'NoteB', parent=normal,
                leftIndent=10, borderPad=4)))
        story.append(Spacer(1, 6))

    if images:
        story += _section_header('Attached Images', heading)
        img_row = []
        for img in images:
            if not img.file_path or not os.path.exists(img.file_path):
                continue
            cell = _pdf_image_cell(img, small)
            if cell is None:
                continue
            img_row.append(cell)
            if len(img_row) == 3:
                story.append(_image_row_table(img_row, avail_w))
                img_row = []
        if img_row:
            story.append(_image_row_table(img_row, avail_w))
        story.append(Spacer(1, 6))

    if ticket.status == 'closed' and ticket.close_signature:
        story += _section_header('Closure Sign-off', heading)
        if ticket.close_notes:
            story.append(Paragraph(f'<b>Closing notes:</b> {ticket.close_notes}', normal))
            story.append(Spacer(1, 4))
        try:
            sig_data = ticket.close_signature
            if sig_data.startswith('data:'):
                import base64
                header, encoded = sig_data.split(',', 1)
                sig_bytes = base64.b64decode(encoded)
                sig_buf = io.BytesIO(sig_bytes)
                ri_sig = RLImage(sig_buf, width=60 * mm, height=25 * mm, kind='proportional')
                sig_label = Paragraph(
                    f'Signed by: <b>{ticket.close_signed_by}</b>'
                    + (f' ({ticket.close_signed_role})' if ticket.close_signed_role else ''),
                    normal)
                sig_tbl = Table([[ri_sig, sig_label]],
                                colWidths=[65 * mm, avail_w - 65 * mm])
                sig_tbl.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOX', (0, 0), (-1, -1), 0.5, BRAND_BORDER),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(sig_tbl)
        except Exception as exc:
            logger.warning("Could not render signature in PDF: %s", exc)
            story.append(Paragraph(
                f'Signed by: {ticket.close_signed_by} ({ticket.close_signed_role})', normal))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _TicketPDFCanvas(
            *a, logo_path=logo_path, ticket_id=ticket.ticket_id, **kw),
    )


def _fmt_hours(h: float) -> str:
    if h == 0.25:
        return '15 min'
    if h == 0.5:
        return '30 min'
    if h == 0.75:
        return '45 min'
    if h == int(h):
        return f'{int(h)}h'
    return f'{h}h'


def _pdf_image_cell(img, small_style):
    """Build a ReportLab image+caption cell, or skip corrupt attachments.

    ReportLab defers decode until doc.build(); verifying with Pillow and passing
    an in-memory PNG avoids a single bad file crashing the whole PDF.
    """
    label = img.caption or img.filename or 'Attachment'
    try:
        from PIL import Image as PILImage
        with PILImage.open(img.file_path) as pil_im:
            pil_im.load()
            rgb = pil_im.convert('RGB') if pil_im.mode not in ('RGB', 'L') else pil_im
            buf = io.BytesIO()
            rgb.save(buf, format='PNG')
            buf.seek(0)
        ri = RLImage(buf, width=55 * mm, height=44 * mm, kind='proportional')
        return [ri, Paragraph(label, small_style)]
    except Exception as exc:
        logger.warning(
            'Skipping corrupt ticket image in PDF (%s): %s',
            getattr(img, 'file_path', None), exc,
        )
        return [Paragraph(f'[Image unavailable: {label}]', small_style), Paragraph('', small_style)]


def _data_table_style():
    return TableStyle(brand.data_header_table_style())


def _image_row_table(img_row: list, avail_w: float) -> Table:
    col_w = avail_w / 3
    data = [[item[0] for item in img_row]]
    cap_row = [[item[1] for item in img_row]]
    while len(data[0]) < 3:
        data[0].append('')
        cap_row[0].append('')
    full_data = [data[0], cap_row[0]]
    tbl = Table(full_data, colWidths=[col_w] * 3)
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return tbl
