"""Purchase-request PDF and APPROVED stamp overlay."""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from common import kynvera_pdf_brand as brand

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
RAIL = 3.2 * mm
L_MARGIN = 20 * mm
R_MARGIN = 18 * mm
T_MARGIN = 16 * mm
B_MARGIN = 18 * mm
AVAIL_W = PAGE_W - L_MARGIN - R_MARGIN
INK = brand.TEXT_DARK
MUTED = brand.TEXT_MID
ACCENT = brand.PRIMARY
RULE = brand.HAIRLINE
ROW_ALT = brand.SURFACE_ALT
STATUS_LABELS = {
    'procurement_review': 'Procurement review',
    'awaiting_quotation': 'Awaiting quotation',
    'gm_review': 'GM / finance review',
    'approved': 'Approved',
    'ordered': 'Ordered',
    'received': 'Received',
    'closed': 'Closed',
    'rejected': 'Rejected',
}


def _p(text, size=9, bold=False, color=INK, align=TA_LEFT, leading=None):
    fn = 'Helvetica-Bold' if bold else 'Helvetica'
    return Paragraph(
        str(text) if text else '—',
        ParagraphStyle('_', fontName=fn, fontSize=size, textColor=color,
                       alignment=align, leading=leading or (size * 1.35)),
    )


def _esc(text):
    return (
        str(text or '')
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _status_label(status):
    key = (status or '').strip().lower()
    if key in STATUS_LABELS:
        return STATUS_LABELS[key]
    return (status or '—').replace('_', ' ').title()


class _PrCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self._pr_id = kwargs.pop('pr_id', '')
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page(total)
            super().showPage()
        super().save()

    def _draw_page(self, total_pages):
        self.saveState()
        self.setFillColor(ACCENT)
        self.rect(0, 0, RAIL, PAGE_H, fill=1, stroke=0)
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(L_MARGIN, 11 * mm, PAGE_W - R_MARGIN, 11 * mm)
        self.setFillColor(MUTED)
        self.setFont('Helvetica', 7)
        self.drawString(
            L_MARGIN, 5.5 * mm,
            f'{brand.COMPANY_NAME}  ·  Purchase request  ·  Confidential',
        )
        self.drawRightString(
            PAGE_W - R_MARGIN, 5.5 * mm,
            f'{self._pr_id}   {self._pageNumber} / {total_pages}',
        )
        self.restoreState()


def _fact(label, value, width):
    t = Table([
        [_p(label, 7, bold=True, color=MUTED, leading=9)],
        [_p(value, 10, bold=True, color=INK, leading=13)],
    ], colWidths=[width])
    t.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 2),
        ('BOTTOMPADDING', (0, 1), (0, 1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _status_chip(text):
    chip = Table(
        [[_p(text, 8, bold=True, color=brand.PRIMARY_DARK, align=TA_CENTER, leading=10)]],
        colWidths=[48 * mm],
    )
    chip.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), brand.SOFT_WASH),
        ('BOX', (0, 0), (-1, -1), 0.8, ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return chip


def build_pr_pdf(pr) -> bytes:
    """Build the procurement purchase-request PDF from current lines."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN, bottomMargin=B_MARGIN + 4 * mm,
        title=f'Purchase request {pr.public_id}',
        author=brand.PDF_AUTHOR,
    )
    story = []
    public_id = pr.public_id or ''
    status_text = _status_label(pr.status)

    wordmark = brand.wordmark_flowable(max_width=32 * mm, max_height=9 * mm)
    if wordmark:
        brand_cell = Table([
            [wordmark],
            [_p(brand.TAGLINE, 7, color=MUTED, leading=9)],
        ], colWidths=[AVAIL_W * 0.48])
    else:
        brand_cell = Table([
            [_p(brand.COMPANY_NAME, 13, bold=True, color=ACCENT, leading=16)],
            [_p(brand.TAGLINE, 7, color=MUTED, leading=9)],
        ], colWidths=[AVAIL_W * 0.48])
    brand_cell.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))

    id_block = Table([
        [_p('Purchase request', 8, bold=True, color=MUTED, align=TA_RIGHT, leading=10)],
        [_p(public_id, 16, bold=True, color=INK, align=TA_RIGHT, leading=20)],
        [_status_chip(status_text)],
    ], colWidths=[AVAIL_W * 0.52])
    id_block.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    hero = Table([[brand_cell, id_block]], colWidths=[AVAIL_W * 0.48, AVAIL_W * 0.52])
    hero.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(hero)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=1.15, color=INK, spaceBefore=0, spaceAfter=0))
    story.append(Spacer(1, 12))

    created = pr.created_at.strftime('%d %b %Y') if pr.created_at else '—'
    who = '—'
    if pr.requested_by:
        who = pr.requested_by.full_name or pr.requested_by.username or '—'
    property_name = pr.property.name if pr.property else 'Unassigned'
    supplier_name = pr.supplier.name if pr.supplier else 'Not set'
    line_count = len(pr.lines or [])
    approval = 'GM / finance (AED 1,000+)' if pr.needs_gm else 'Procurement'

    col = AVAIL_W / 3
    facts = Table([
        [
            _fact('Raised', created, col),
            _fact('Requested by', who, col),
            _fact('Approval', approval, col),
        ],
        [
            _fact('Property', property_name, col),
            _fact('Supplier', supplier_name, col),
            _fact('Lines', str(line_count), col),
        ],
    ], colWidths=[col, col, col])
    facts.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, 0), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 1), (-1, 1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, RULE),
    ]))
    story.append(facts)
    story.append(Spacer(1, 16))
    story.append(_p('Materials', 8, bold=True, color=MUTED))
    story.append(Spacer(1, 5))

    col_w = [
        AVAIL_W * 0.07, AVAIL_W * 0.37, AVAIL_W * 0.14,
        AVAIL_W * 0.12, AVAIL_W * 0.15, AVAIL_W * 0.15,
    ]
    head_color = colors.white
    rows = [[
        _p('#', 7.5, bold=True, color=head_color),
        _p('Material', 7.5, bold=True, color=head_color),
        _p('Trade', 7.5, bold=True, color=head_color),
        _p('Qty', 7.5, bold=True, color=head_color, align=TA_RIGHT),
        _p('Unit', 7.5, bold=True, color=head_color, align=TA_RIGHT),
        _p('Total', 7.5, bold=True, color=head_color, align=TA_RIGHT),
    ]]
    for i, line in enumerate(pr.lines or [], start=1):
        item = line.catalog_item
        name = item.name if item else '—'
        brand_name = (item.brand if item else '') or ''
        label = f'<b>{_esc(name)}</b>'
        if brand_name:
            label += f'<br/><font size="8" color="#71717a">{_esc(brand_name)}</font>'
        qty = float(line.qty or 0)
        price = float(line.unit_price or 0)
        uom = (item.uom if item else 'PCS') or 'PCS'
        rows.append([
            _p(str(i), 8.5, color=MUTED),
            Paragraph(label, ParagraphStyle(
                '_', fontName='Helvetica', fontSize=9, textColor=INK, leading=12,
            )),
            _p(item.department if item else '—', 8, color=MUTED),
            _p(f'{qty:g} {uom}', 9, align=TA_RIGHT),
            _p(f'AED {price:,.2f}', 9, align=TA_RIGHT),
            _p(f'AED {qty * price:,.2f}', 9, bold=True, align=TA_RIGHT),
        ])
    if len(rows) == 1:
        rows.append([
            _p('—', 8, color=MUTED),
            _p('No lines on this request', 9, color=MUTED),
            _p('', 8), _p('', 8), _p('', 8), _p('', 8),
        ])
    table = Table(rows, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), INK),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [brand.WHITE, ROW_ALT]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))

    total = float(pr.total_aed or 0)
    total_inner = Table([[
        _p('Request total', 8, bold=True, color=MUTED, align=TA_RIGHT, leading=10),
        _p(f'AED {total:,.2f}', 14, bold=True, color=INK, align=TA_RIGHT, leading=17),
    ]], colWidths=[AVAIL_W * 0.22, AVAIL_W * 0.28])
    total_inner.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 0), (-1, 0), 1.6, ACCENT),
    ]))
    total_wrap = Table([['', total_inner]], colWidths=[AVAIL_W * 0.50, AVAIL_W * 0.50])
    total_wrap.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(total_wrap)

    if pr.notes:
        story.append(Spacer(1, 16))
        story.append(HRFlowable(width='100%', thickness=0.5, color=RULE, spaceBefore=0, spaceAfter=6))
        story.append(_p('Notes', 7.5, bold=True, color=MUTED))
        story.append(Spacer(1, 3))
        story.append(_p(pr.notes, 9, color=INK))

    generated = datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')
    story.append(Spacer(1, 16))
    story.append(_p(f'Generated {generated} UTC', 7.5, color=MUTED))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _PrCanvas(*a, pr_id=public_id, **kw),
    )
    return buf.getvalue()


def wrap_image_as_pdf(image_path: str) -> bytes:
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    try:
        c.drawImage(
            image_path, L_MARGIN, 20 * mm,
            width=AVAIL_W, height=PAGE_H - 40 * mm,
            preserveAspectRatio=True, anchor='c',
        )
    except Exception:
        logger.exception('Could not embed image %s', image_path)
        c.setFont('Helvetica', 12)
        c.drawString(L_MARGIN, PAGE_H / 2, os.path.basename(image_path))
    c.save()
    return buf.getvalue()


def _stamp_check(c, x, y, size):
    """Filled coral disc with a white tick."""
    c.setFillColor(brand.PRIMARY_DARK)
    c.circle(x, y, size / 2, fill=1, stroke=0)
    c.setStrokeColor(brand.WHITE)
    c.setLineWidth(max(1.15, size * 0.12))
    c.setLineCap(1)
    c.setLineJoin(1)
    c.line(x - size * 0.22, y - size * 0.02, x - size * 0.04, y - size * 0.18)
    c.line(x - size * 0.04, y - size * 0.18, x + size * 0.24, y + size * 0.16)


def _draw_approved_badge(c, *, pr_id, approver, kind, page_w, page_h):
    """Compact upright plaque in the top-right of the real page."""
    kind_key = (kind or '').strip().lower()
    kind_label = {
        'pr_pdf': 'Request',
        'quotation': 'Quotation',
        'quotation_2': 'Quotation',
        'quotation_3': 'Quotation',
        'invoice': 'Invoice',
    }.get(kind_key, kind_key.replace('_', ' ').title() or 'Document')
    when = datetime.now(timezone.utc).strftime('%d %b %Y')
    who = (approver or 'Procurement').strip()[:36]
    ref = (pr_id or '')[:28]
    box_w, box_h = 62 * mm, 20 * mm
    pad = 10 * mm
    x = max(8 * mm, page_w - pad - box_w)
    y = max(8 * mm, page_h - pad - box_h)

    c.saveState()
    c.setFillColor(colors.Color(0.09, 0.09, 0.11, alpha=0.06))
    c.roundRect(x + 0.9, y - 0.9, box_w, box_h, 3.2, fill=1, stroke=0)
    c.setFillColor(colors.Color(1, 0.97, 0.95, alpha=0.96))
    c.setStrokeColor(brand.PRIMARY_DARK)
    c.setLineWidth(1.15)
    c.roundRect(x, y, box_w, box_h, 3.2, fill=1, stroke=1)

    disc = 7.2 * mm
    _stamp_check(c, x + 6.4 * mm, y + box_h / 2, disc)

    text_x = x + 12.2 * mm
    c.setFillColor(brand.PRIMARY_DARK)
    c.setFont('Helvetica-Bold', 10)
    c.drawString(text_x, y + box_h - 7.4 * mm, 'APPROVED')
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 6)
    c.drawString(text_x + 28.5 * mm, y + box_h - 7.1 * mm, kind_label.upper()[:16])

    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 7)
    c.drawString(text_x, y + 7.2 * mm, ref)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 6.5)
    meta = f'{who}  ·  {when}'
    c.drawString(text_x, y + 3.1 * mm, meta[:52])
    c.restoreState()


def stamp_pdf_bytes(src_bytes: bytes, *, pr_id: str, approver: str, kind: str) -> bytes:
    """Overlay a compact APPROVED badge on the first page of a PDF."""
    from pypdf import PdfReader, PdfWriter

    src = io.BytesIO(src_bytes)
    reader = PdfReader(src)
    if not reader.pages:
        return src_bytes
    page0 = reader.pages[0]
    page_w = float(page0.mediabox.width)
    page_h = float(page0.mediabox.height)

    overlay_buf = io.BytesIO()
    c = Canvas(overlay_buf, pagesize=(page_w, page_h))
    _draw_approved_badge(
        c, pr_id=pr_id, approver=approver, kind=kind,
        page_w=page_w, page_h=page_h,
    )
    c.save()
    overlay_buf.seek(0)
    writer = PdfWriter(clone_from=io.BytesIO(src_bytes))
    stamp = PdfReader(overlay_buf).pages[0]
    writer.pages[0].merge_page(stamp)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
