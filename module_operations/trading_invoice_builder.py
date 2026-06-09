"""
Trading invoice PDF builder — Operations module.
Uses SF (San Francisco / SFNS) — the iOS/macOS system font — with a graceful
fallback to Helvetica when the font files are unavailable (e.g. on Linux hosts).
"""
import os
import logging
import tempfile
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage,
)
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ── iOS / SF Pro font registration ───────────────────────────────────────────
_SF_PATH  = '/System/Library/Fonts/SFNS.ttf'
_USE_SF   = False

try:
    pdfmetrics.registerFont(TTFont('SF',      _SF_PATH, subfontIndex=0))
    pdfmetrics.registerFont(TTFont('SF-Bold', _SF_PATH, subfontIndex=1))
    pdfmetrics.registerFontFamily('SF', normal='SF', bold='SF-Bold',
                                  italic='SF', boldItalic='SF-Bold')
    _USE_SF = True
except Exception:
    pass   # non-macOS host — Helvetica fallback below

def _crop_logo(src_path, display_h_mm=30, dpi=300):
    """Crop PNG to content bounds, resize to print resolution, save to temp file.

    Removes transparent padding using PIL's alpha getbbox(), then scales the
    result to (display_h_mm / 25.4 * dpi) pixels tall so the embedded image
    is crisp at print resolution without ballooning the PDF file size.
    """
    try:
        from PIL import Image
        img = Image.open(src_path).convert('RGBA')
        bbox = img.split()[3].getbbox()
        if not bbox:
            return src_path
        pad = 20
        box = (max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
               min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height))
        cropped = img.crop(box)
        # Resize to print resolution (300 DPI at display_h_mm)
        target_h = int(display_h_mm / 25.4 * dpi)
        aspect   = cropped.width / cropped.height
        target_w = int(target_h * aspect)
        resized  = cropped.resize((target_w, target_h), Image.LANCZOS)
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        resized.save(tmp.name, 'PNG', optimize=True)
        return tmp.name
    except Exception as e:
        logger.warning('Logo crop failed: %s', e)
        return src_path


def _font(bold=False):
    if _USE_SF:
        return 'SF-Bold' if bold else 'SF'
    return 'Helvetica-Bold' if bold else 'Helvetica'


# ── Palette ──────────────────────────────────────────────────────────────────
INK        = colors.HexColor('#0f172a')
BRAND      = colors.HexColor('#a8121e')
ACCENT     = colors.HexColor('#d21725')
RULE       = colors.HexColor('#cbd5e1')
TABLE_HEAD = colors.HexColor('#a8121e')
ROW_ALT    = colors.HexColor('#f8f5f5')
TOTAL_BG   = colors.HexColor('#a8121e')
MUTED      = colors.HexColor('#64748b')

PAGE_W, PAGE_H = A4
L_MARGIN = 18 * mm
R_MARGIN = 18 * mm
T_MARGIN = 14 * mm
B_MARGIN = 16 * mm
AVAIL_W  = PAGE_W - L_MARGIN - R_MARGIN


# ── Canvas (top/bottom brand stripe + footer) ────────────────────────────────
class _InvoiceCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self._logo_path = kwargs.pop('logo_path', None)
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
        self.setFillColor(BRAND)
        self.rect(0, PAGE_H - 6 * mm, PAGE_W, 6 * mm, stroke=0, fill=1)
        self.rect(0, 0, PAGE_W, 6 * mm, stroke=0, fill=1)
        self.setFillColor(colors.white)
        self.setFont(_font(bold=True), 7)
        self.drawString(L_MARGIN, 2.1 * mm, 'Amaan Facilities Management')
        self.drawRightString(PAGE_W - R_MARGIN, 2.1 * mm,
                             f'Page {self._pageNumber} of {total_pages}')
        self.restoreState()


# ── Helper: paragraph ────────────────────────────────────────────────────────
def _p(text, size=9, bold=False, color=INK, align=TA_LEFT, leading=None):
    txt = str(text) if (text is not None and str(text) != '') else '—'
    return Paragraph(
        txt,
        ParagraphStyle('_', fontName=_font(bold), fontSize=size,
                       textColor=color, alignment=align,
                       leading=leading or (size * 1.45)),
    )


def _rule(color=RULE, thickness=0.6):
    return HRFlowable(width='100%', thickness=thickness, color=color,
                      spaceAfter=4, spaceBefore=4)


def _stack(col_w, *items):
    t = Table([[item] for item in items], colWidths=[col_w])
    t.setStyle(TableStyle([
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _aed(v):
    return f'AED {float(v or 0):,.2f}'


def _fmt_qty(v):
    try:
        n = float(v)
        return str(int(n)) if n == int(n) else f'{n:g}'
    except (TypeError, ValueError):
        return '—'


def _fmt_date(d):
    if not d:
        return '—'
    try:
        return d.strftime('%d %B %Y')
    except Exception:
        return str(d)


def _items_table(rows, col_widths):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), TABLE_HEAD),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), _font(bold=True)),
        ('FONTSIZE',      (0, 0), (-1, 0), 8.5),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('FONTNAME',      (0, 1), (-1, -1), _font()),
        ('FONTSIZE',      (0, 1), (-1, -1), 8.5),
        ('TOPPADDING',    (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 7),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 7),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID',          (0, 0), (-1, -1), 0.4, RULE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
    ]))
    return t


def _summary_row(label, value, avail_w, bold=False):
    w1, w2 = avail_w * 0.72, avail_w * 0.28
    t = Table([[_p(label, 8.5, bold=True, color=MUTED, align=TA_RIGHT),
                _p(value, 8.5, bold=bold, color=INK, align=TA_RIGHT)]],
              colWidths=[w1, w2])
    t.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('LINEABOVE',     (0, 0), (-1, 0), 0.4, RULE),
    ]))
    return t


def _grand_total_block(label, value, avail_w):
    w1, w2 = avail_w * 0.72, avail_w * 0.28
    t = Table([[_p(label, 11, bold=True, color=colors.white, align=TA_RIGHT),
                _p(value, 11, bold=True, color=colors.white, align=TA_RIGHT)]],
              colWidths=[w1, w2])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), TOTAL_BG),
        ('TOPPADDING',    (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    return t


# ── Main entry point ─────────────────────────────────────────────────────────
def build_trading_invoice_pdf(invoice, client, items, output_stream):
    """Render a trading invoice to output_stream (BytesIO)."""

    invoice_no = invoice.invoice_no

    # Logo — prefer the branded Amaan mark
    raw_logo = None
    for candidate in [
        'static/icons/Amaan.png',
        'static/icons/Amaan - Edited.png',
        'static/logo.png',
    ]:
        if os.path.exists(candidate):
            raw_logo = candidate
            break
    logo_path = _crop_logo(raw_logo) if raw_logo else None

    doc = SimpleDocTemplate(
        output_stream,
        pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN + 10 * mm, bottomMargin=B_MARGIN + 10 * mm,
        title=invoice_no,
    )

    story = []

    # ── 1. HERO HEADER ───────────────────────────────────────────────────────
    # Logo is the sole brand identifier — it already contains "AMAAN" inside
    # the artwork. No redundant text. Right-aligned at 30mm height.
    LOGO_H   = 30 * mm
    brand_col = AVAIL_W * 0.40

    logo_img = None
    if logo_path:
        try:
            from PIL import Image as _PILImg
            with _PILImg.open(logo_path) as _pil:
                _pw, _ph = _pil.size
            # Constrain to LOGO_H; calculate width from aspect ratio
            _aspect  = _pw / _ph
            _logo_h  = LOGO_H
            _logo_w  = min(_logo_h * _aspect, brand_col)
            logo_img = RLImage(logo_path, width=_logo_w, height=_logo_h,
                               hAlign='RIGHT')
        except Exception as e:
            logger.warning('RLImage failed: %s', e)

    hero_right_content = logo_img if logo_img else \
        _p('Amaan', 16, bold=True, color=BRAND, align=TA_RIGHT)

    hero_right = Table([[hero_right_content]], colWidths=[brand_col])
    hero_right.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))

    hero_left = _p('TRADING INVOICE', 26, bold=True, color=ACCENT)

    hero_tbl = Table([[hero_left, hero_right]],
                     colWidths=[AVAIL_W * 0.60, brand_col])
    hero_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(hero_tbl)
    story.append(_rule(color=ACCENT, thickness=2))
    story.append(Spacer(1, 4))

    # ── 2. META ROW: invoice details + bill-to ───────────────────────────────
    meta_left = Table([
        [_p('INVOICE NO:', 8, bold=True, color=MUTED), _p(invoice_no, 8, bold=True)],
        [_p('DATE:',       8, bold=True, color=MUTED), _p(_fmt_date(invoice.invoice_date), 8)],
        [_p('DUE DATE:',   8, bold=True, color=MUTED), _p(_fmt_date(invoice.due_date), 8)],
        [_p('STATUS:',     8, bold=True, color=MUTED),
         _p((invoice.status or 'draft').upper(), 8, bold=True, color=ACCENT)],
    ], colWidths=[28 * mm, AVAIL_W * 0.35])
    meta_left.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))

    addr_parts = [x for x in [
        getattr(client, 'billing_address', None),
        getattr(client, 'city', None),
        getattr(client, 'country', None),
    ] if x]
    bill_to = _stack(AVAIL_W * 0.46,
        _p('Bill To', 8, bold=True, color=MUTED),
        Spacer(1, 3),
        _p(client.client_name if client else '—', 11, bold=True),
        _p(getattr(client, 'contact_person', None) or '', 9),
        _p(', '.join(addr_parts) if addr_parts else '—', 8.5, color=MUTED),
        _p(getattr(client, 'phone', None) or '', 8.5, color=MUTED),
        _p(getattr(client, 'email', None) or '', 8.5, color=MUTED),
    )

    meta_tbl = Table([[meta_left, bill_to]],
                     colWidths=[AVAIL_W * 0.54, AVAIL_W * 0.46])
    meta_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 6))
    story.append(_rule())
    story.append(Spacer(1, 4))

    # ── 3. ITEMS TABLE ───────────────────────────────────────────────────────
    story.append(_p('ITEMS', 9, bold=True, color=BRAND))
    story.append(Spacer(1, 3))

    header = ['#', 'Material', 'Description', 'Qty', 'Unit', 'Unit Price', 'Total']
    rows = [header]
    for i, it in enumerate(items, start=1):
        rows.append([
            _p(str(i), 8.5),
            _p(it.material_name, 8.5, bold=True),
            _p(it.description or '—', 8.5, color=MUTED),
            _p(_fmt_qty(it.quantity), 8.5, align=TA_RIGHT),
            _p(it.unit or '—', 8.5),
            _p(_aed(it.unit_price), 8.5, align=TA_RIGHT),
            _p(_aed(it.total_price), 8.5, bold=True, align=TA_RIGHT),
        ])
    col_w = [AVAIL_W * x for x in (0.05, 0.24, 0.27, 0.08, 0.08, 0.14, 0.14)]
    story.append(_items_table(rows, col_w))
    story.append(Spacer(1, 8))

    # ── 4. SUMMARY ───────────────────────────────────────────────────────────
    story.append(_summary_row('Subtotal', _aed(invoice.subtotal), AVAIL_W))
    tax_label = f'Tax ({invoice.tax_pct:g}%)' if invoice.tax_pct else 'Tax'
    story.append(_summary_row(tax_label, _aed(invoice.tax_amount), AVAIL_W))
    story.append(Spacer(1, 4))
    story.append(_grand_total_block('GRAND TOTAL', _aed(invoice.grand_total), AVAIL_W))

    # ── 5. NOTES ─────────────────────────────────────────────────────────────
    if invoice.notes:
        story.append(Spacer(1, 10))
        story.append(_p('Notes', 8, bold=True, color=MUTED))
        story.append(_p(invoice.notes, 8.5))

    def _canvas_factory(*args, **kwargs):
        kwargs['logo_path'] = logo_path
        return _InvoiceCanvas(*args, **kwargs)

    try:
        doc.build(story, canvasmaker=_canvas_factory)
    finally:
        # Remove temp cropped logo if it was written
        if logo_path and logo_path != raw_logo:
            try:
                os.unlink(logo_path)
            except Exception:
                pass

    return output_stream
