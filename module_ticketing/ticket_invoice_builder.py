"""
Invoice PDF builder for ticketing / work order module.
Generates a clean, professional service invoice after a work order is closed.
Layout inspired by classic invoice style: large heading, company branding,
bill-to block, itemised table with subtotals, grand total box.
"""
import io
import os
import base64
import logging
from datetime import datetime

from module_ticketing.tz_utils import to_gst

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage,
)

from reportlab.pdfgen.canvas import Canvas

from common import kynvera_pdf_brand as brand

logger = logging.getLogger(__name__)

# ── Palette — Kynvera coral ──────────────────────────────────────────────────
INK        = brand.TEXT_DARK
BRAND      = brand.TEXT_DARK
ACCENT     = brand.PRIMARY
RULE       = brand.HAIRLINE
TABLE_HEAD = brand.SOFT_WASH
ROW_ALT    = brand.SURFACE_ALT
TOTAL_BG   = brand.PRIMARY_DARK
MUTED      = brand.TEXT_MID

PAGE_W, PAGE_H = A4
L_MARGIN  = 18 * mm
R_MARGIN  = 18 * mm
T_MARGIN  = 14 * mm
B_MARGIN  = 16 * mm
AVAIL_W   = PAGE_W - L_MARGIN - R_MARGIN


# ── Canvas (header / footer decoration) ──────────────────────────────────────

class _InvoiceCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self._logo_path  = kwargs.pop('logo_path', None)
        self._invoice_no = kwargs.pop('invoice_no', '')
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

        # Coral top accent
        self.setStrokeColor(ACCENT)
        self.setLineWidth(2.2)
        self.line(0, PAGE_H - 1, PAGE_W, PAGE_H - 1)

        # Light footer band
        self.setFillColor(brand.SOFT_WASH)
        self.rect(0, 0, PAGE_W, 8 * mm, fill=1, stroke=0)
        self.setStrokeColor(ACCENT)
        self.setLineWidth(1.2)
        self.line(0, 8 * mm, PAGE_W, 8 * mm)

        self.setFillColor(MUTED)
        self.setFont('Helvetica', 7)
        self.drawString(L_MARGIN, 2.8 * mm,
                        f'{brand.COMPANY_NAME_UPPER}  —  SERVICE INVOICE  —  CONFIDENTIAL')
        self.drawRightString(PAGE_W - R_MARGIN, 2.8 * mm,
                             f'Page {self._pageNumber} of {total_pages}  |  {self._invoice_no}')

        self.restoreState()


# ── Style helpers ─────────────────────────────────────────────────────────────

def _p(text, size=9, bold=False, color=INK, align=TA_LEFT, leading=None):
    fn = 'Helvetica-Bold' if bold else 'Helvetica'
    return Paragraph(
        str(text) if text else '—',
        ParagraphStyle('_', fontName=fn, fontSize=size, textColor=color,
                       alignment=align, leading=leading or (size * 1.4)),
    )


def _rule(color=RULE, thickness=0.6):
    return HRFlowable(width='100%', thickness=thickness, color=color,
                      spaceAfter=4, spaceBefore=4)


def _stack(col_w, *items):
    """Wrap multiple flowables into a single-column Table cell for embedding inside another Table."""
    rows = [[item] for item in items]
    t = Table(rows, colWidths=[col_w])
    t.setStyle(TableStyle([
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _fmt_hours(h):
    if not h:
        return '—'
    if h == 0.25: return '15 min'
    if h == 0.5:  return '30 min'
    if h == 0.75: return '45 min'
    return f'{int(h)}h' if h == int(h) else f'{h}h'


def _aed(v):
    return f'AED {v:,.2f}' if v else 'AED 0.00'


def _fmt_qty(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return '—'
    return str(int(n)) if n == int(n) else f'{n:g}'


# ── Line-item table builder ───────────────────────────────────────────────────

def _items_table(rows, col_widths):
    """rows = list of lists of strings; first row = header."""
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    n = len(rows)
    style = [
        # Header row — soft wash + coral underline
        ('BACKGROUND',   (0, 0), (-1, 0),  TABLE_HEAD),
        ('TEXTCOLOR',    (0, 0), (-1, 0),  INK),
        ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0),  8.5),
        ('ALIGN',        (0, 0), (-1, 0),  'CENTER'),
        ('TOPPADDING',   (0, 0), (-1, 0),  7),
        ('BOTTOMPADDING',(0, 0), (-1, 0),  7),
        ('LINEBELOW',    (0, 0), (-1, 0),  1.2, ACCENT),
        # Data rows
        ('FONTSIZE',     (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR',    (0, 1), (-1, -1), INK),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
        ('LEFTPADDING',  (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID',         (0, 0), (-1, -1), 0.4, RULE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
    ]
    t.setStyle(TableStyle(style))
    return t


def _subtotal_row(label, value, avail_w):
    """A right-aligned subtotal row spanning full width."""
    w1 = avail_w * 0.72
    w2 = avail_w * 0.28
    t = Table([[_p(label, 8.5, bold=True, color=MUTED, align=TA_RIGHT),
                _p(value, 8.5, bold=True, color=INK,   align=TA_RIGHT)]],
              colWidths=[w1, w2])
    t.setStyle(TableStyle([
        ('ALIGN',        (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEABOVE',    (0, 0), (-1, 0),  0.4, RULE),
    ]))
    return t


def _grand_total_block(label, value, avail_w):
    w1 = avail_w * 0.72
    w2 = avail_w * 0.28
    t = Table([[_p(label, 11, bold=True, color=colors.white, align=TA_RIGHT),
                _p(value, 11, bold=True, color=colors.white, align=TA_RIGHT)]],
              colWidths=[w1, w2])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), TOTAL_BG),
        ('ALIGN',        (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',   (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 9),
        ('LEFTPADDING',  (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ROUNDEDCORNERS', [4]),
    ]))
    return t


# ── Main entry point ─────────────────────────────────────────────────────────

def build_invoice_pdf(ticket, materials, manpower_entries, output_stream):
    """
    Generate a service invoice PDF for the given closed work order.
    Output is written to output_stream (BytesIO).
    """
    invoice_no = f'INV-{ticket.ticket_id}'

    logo_path = brand.resolve_logo_path(prefer_wordmark=True)

    doc = SimpleDocTemplate(
        output_stream,
        pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN + 6 * mm, bottomMargin=B_MARGIN + 10 * mm,
        title=invoice_no,
        author=brand.PDF_AUTHOR,
    )

    story = []

    # ── 1. HERO HEADER ROW: "SERVICE INVOICE" left, wordmark + company right ──
    logo_cell = ''
    if logo_path:
        try:
            logo_cell = RLImage(logo_path, width=36 * mm, height=10 * mm,
                                preserveAspectRatio=True)
        except Exception:
            pass

    hero_left = _p('SERVICE INVOICE', 26, bold=True, color=ACCENT)
    hero_right = Table([
        [logo_cell],
        [_p(brand.COMPANY_NAME, 12, bold=True, color=BRAND, align=TA_RIGHT)],
        [_p(brand.TAGLINE, 7, color=MUTED, align=TA_RIGHT)],
    ], colWidths=[AVAIL_W * 0.4])
    hero_right.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    hero_tbl = Table([[hero_left, hero_right]],
                     colWidths=[AVAIL_W * 0.58, AVAIL_W * 0.42])
    hero_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(hero_tbl)
    story.append(_rule(color=ACCENT, thickness=2))
    story.append(Spacer(1, 4))

    # ── 2. META ROW: invoice details left, address right ─────────────────────
    closed_str   = to_gst(ticket.closed_at).strftime('%d %B %Y') if ticket.closed_at else \
                   to_gst(datetime.utcnow()).strftime('%d %B %Y')
    created_str  = to_gst(ticket.created_at).strftime('%d %B %Y') if ticket.created_at else '—'

    meta_left = Table([
        [_p('INVOICE NO:',  8, bold=True, color=MUTED), _p(invoice_no, 8, bold=True, color=INK)],
        [_p('DATE:',        8, bold=True, color=MUTED), _p(closed_str, 8, color=INK)],
        [_p('WORK ORDER:',  8, bold=True, color=MUTED), _p(ticket.ticket_id, 8, color=INK)],
        [_p('ISSUED DATE:', 8, bold=True, color=MUTED), _p(created_str, 8, color=INK)],
    ], colWidths=[28*mm, AVAIL_W*0.35])
    meta_left.setStyle(TableStyle([
        ('TOPPADDING',   (0,0),(-1,-1), 2),
        ('BOTTOMPADDING',(0,0),(-1,-1), 2),
        ('LEFTPADDING',  (0,0),(-1,-1), 0),
        ('RIGHTPADDING', (0,0),(-1,-1), 4),
    ]))

    loc_parts = [x for x in [ticket.property_name, ticket.zone, ticket.sub_zone, ticket.base_unit] if x]
    location_str = ', '.join(loc_parts) if loc_parts else '—'
    meta_right = Table([
        [_p('PROJECT:', 8, bold=True, color=MUTED), _p(ticket.project or '—', 8, color=INK)],
        [_p('LOCATION:', 8, bold=True, color=MUTED), _p(location_str, 8, color=INK)],
    ], colWidths=[24*mm, AVAIL_W * 0.38 - 24*mm])
    meta_right.setStyle(TableStyle([
        ('TOPPADDING',   (0,0),(-1,-1), 2),
        ('BOTTOMPADDING',(0,0),(-1,-1), 2),
        ('LEFTPADDING',  (0,0),(-1,-1), 0),
        ('RIGHTPADDING', (0,0),(-1,-1), 0),
    ]))

    meta_tbl = Table([[meta_left, meta_right]],
                     colWidths=[AVAIL_W * 0.54, AVAIL_W * 0.46])
    meta_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',  (0,0),(-1,-1), 0),
        ('RIGHTPADDING', (0,0),(-1,-1), 0),
        ('TOPPADDING',   (0,0),(-1,-1), 0),
        ('BOTTOMPADDING',(0,0),(-1,-1), 0),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 6))
    story.append(_rule())

    # ── 3. BILL TO + SERVICE INFO ─────────────────────────────────────────────
    reporter_name = ticket.reporter.full_name if ticket.reporter else '—'
    assigned_name = ticket.assigned_to.full_name if ticket.assigned_to else 'Unassigned'

    cw_half = AVAIL_W * 0.50

    bill_left = _stack(cw_half,
        _p('Bill To', 8, bold=True, color=MUTED),
        Spacer(1, 3),
        _p(reporter_name, 11, bold=True, color=INK),
        _p(ticket.project or '—', 9, color=INK),
        _p(location_str, 8.5, color=MUTED),
    )

    bill_right = _stack(cw_half,
        _p('Service Information', 8, bold=True, color=MUTED),
        Spacer(1, 3),
        _p(ticket.title, 10, bold=True, color=INK),
        _p(f'{ticket.service_group} / {ticket.category}', 8.5, color=MUTED),
        _p(f'Assigned to: {assigned_name}', 8.5, color=INK),
        _p(f'Priority: {ticket.priority.upper()}', 8.5, bold=True,
           color=colors.HexColor('#dc2626') if ticket.priority == 'critical'
           else colors.HexColor('#ea580c') if ticket.priority == 'high'
           else INK),
    )

    bill_tbl = Table([[bill_left, bill_right]],
                     colWidths=[AVAIL_W * 0.52, AVAIL_W * 0.48])
    bill_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',  (0,0),(-1,-1), 0),
        ('RIGHTPADDING', (0,0),(-1,-1), 0),
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
    ]))
    story.append(bill_tbl)
    story.append(_rule())
    story.append(Spacer(1, 4))

    # ── 4. Compute total to bill ──────────────────────────────────────────────
    mp_total = sum((e.total_cost or 0.0) for e in manpower_entries)
    mat_total = sum((m.total_price or 0.0) for m in materials)
    # Use the pre-computed selling_price if available (supervisor has set markup),
    # otherwise fall back to the actual_price or the raw base cost.
    base_total = mp_total + mat_total
    if getattr(ticket, 'selling_price', None):
        invoice_total = ticket.selling_price
    elif getattr(ticket, 'actual_price', None):
        invoice_total = ticket.actual_price
    else:
        invoice_total = round(base_total, 2)

    # ── 5. Unified itemised table (Materials first, then Manpower) ───────────
    story.append(_p('ITEMS', 9, bold=True, color=BRAND))
    story.append(Spacer(1, 3))

    line_items = []
    for m in materials:
        qty = float(m.quantity or 1)
        base_sub = float(m.total_price or 0)
        line_items.append({
            'description': m.material_name or 'Material',
            'type': 'Material',
            'qty': qty,
            'unit': m.unit or 'PCS',
            'base_subtotal': base_sub,
        })
    for e in manpower_entries:
        qty = float(e.hours or 0)
        base_sub = float(e.total_cost or 0)
        line_items.append({
            'description': e.worker_name or 'Technician',
            'type': 'Manpower',
            'qty': qty,
            'unit': 'HR',
            'base_subtotal': base_sub,
        })

    if not line_items:
        line_items.append({
            'description': 'Service Charge',
            'type': 'Service',
            'qty': 1.0,
            'unit': 'EA',
            'base_subtotal': invoice_total,
        })
        base_total = invoice_total

    factor = (invoice_total / base_total) if base_total > 0 else 1.0
    running_total = 0.0
    for idx, row in enumerate(line_items):
        allocated = round(row['base_subtotal'] * factor, 2)
        row['allocated_subtotal'] = allocated
        running_total += allocated
        if idx == len(line_items) - 1:
            # adjust final row so the table sums exactly to invoice_total
            diff = round(invoice_total - running_total, 2)
            row['allocated_subtotal'] = round(row['allocated_subtotal'] + diff, 2)
        qty = row['qty'] if row['qty'] else 1.0
        row['allocated_rate'] = round(row['allocated_subtotal'] / qty, 2) if qty else row['allocated_subtotal']

    col_w = [AVAIL_W*0.34, AVAIL_W*0.14, AVAIL_W*0.12, AVAIL_W*0.18, AVAIL_W*0.22]
    rows = [['DESCRIPTION', 'TYPE', 'QTY/HRS', 'RATE', 'SUBTOTAL']]
    for row in line_items:
        rows.append([
            row['description'],
            row['type'],
            _fmt_qty(row['qty']) + f" {row['unit']}",
            f"AED {row['allocated_rate']:.2f}",
            f"AED {row['allocated_subtotal']:.2f}",
        ])

    story.append(_items_table(rows, col_w))
    story.append(Spacer(1, 6))

    materials_alloc_total = round(sum(i['allocated_subtotal'] for i in line_items if i['type'] == 'Material'), 2)
    manpower_alloc_total = round(sum(i['allocated_subtotal'] for i in line_items if i['type'] == 'Manpower'), 2)
    story.append(_subtotal_row('Materials (allocated)', _aed(materials_alloc_total), AVAIL_W))
    story.append(_subtotal_row('Manpower (allocated)', _aed(manpower_alloc_total), AVAIL_W))
    story.append(Spacer(1, 4))
    story.append(_grand_total_block('TOTAL AMOUNT DUE', _aed(invoice_total), AVAIL_W))
    story.append(Spacer(1, 12))

    # ── 7. FOOTER: terms left, signature right ────────────────────────────────
    terms_text = (
        'This invoice is issued upon successful completion and closure of the above '
        'work order. The amount shown reflects the total service charge. '
        f'For queries or disputes, contact {brand.COMPANY_NAME}.'
    )
    cw_terms = AVAIL_W * 0.56
    cw_sig   = AVAIL_W * 0.44

    terms_block = _stack(cw_terms,
        _p('TERMS & CONDITIONS', 7.5, bold=True, color=BRAND),
        Spacer(1, 3),
        _p(terms_text, 7.5, color=MUTED),
    )

    sig_items = [
        _p('AUTHORISED BY', 7.5, bold=True, color=BRAND),
        Spacer(1, 3),
    ]

    if ticket.close_signature:
        try:
            sig_data = ticket.close_signature
            if sig_data.startswith('data:'):
                _, encoded = sig_data.split(',', 1)
                sig_bytes = base64.b64decode(encoded)
                sig_buf = io.BytesIO(sig_bytes)
                ri_sig = RLImage(sig_buf, width=50*mm, height=20*mm, kind='proportional')
                sig_items.append(ri_sig)
        except Exception as exc:
            logger.warning('Invoice: could not render signature: %s', exc)

    signer = ticket.close_signed_by or (
        ticket.reporter.full_name if ticket.reporter else 'N/A')
    role   = ticket.close_signed_role or 'General Manager'

    sig_items += [
        _rule(thickness=0.5),
        _p(signer, 9, bold=True, color=INK),
        _p(role, 8, color=MUTED),
    ]

    sig_block = _stack(cw_sig, *sig_items)

    footer_tbl = Table([[terms_block, sig_block]],
                       colWidths=[cw_terms, cw_sig])
    footer_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',  (0,0),(-1,-1), 0),
        ('RIGHTPADDING', (0,0),(-1,-1), 0),
        ('TOPPADDING',   (0,0),(-1,-1), 0),
        ('BOTTOMPADDING',(0,0),(-1,-1), 0),
    ]))
    story.append(footer_tbl)

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _InvoiceCanvas(
            *a, logo_path=logo_path, invoice_no=invoice_no, **kw),
    )
