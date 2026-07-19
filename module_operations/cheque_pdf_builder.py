"""
Cheque Preparation / Request Form PDF builder — Operations module.
Reproduces the paper "Cheque Preparation/ Request Form" template (Office /
Department header, SN-Supplier-Amount-Date-Remarks table, Requested by /
Verified by / Approved by signature blocks, Remarks and Attached Documents)
using ReportLab. Uses SF (San Francisco / SFNS) — the iOS/macOS system font —
with a graceful fallback to Helvetica when the font files are unavailable.
"""
import os
import io
import base64
import logging
import tempfile

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
_SF_PATH = '/System/Library/Fonts/SFNS.ttf'
_USE_SF = False

try:
    pdfmetrics.registerFont(TTFont('SF',      _SF_PATH, subfontIndex=0))
    pdfmetrics.registerFont(TTFont('SF-Bold', _SF_PATH, subfontIndex=1))
    pdfmetrics.registerFontFamily('SF', normal='SF', bold='SF-Bold',
                                  italic='SF', boldItalic='SF-Bold')
    _USE_SF = True
except Exception:
    pass   # non-macOS host — Helvetica fallback below


def _crop_logo(src_path, display_h_mm=30, dpi=300):
    """Crop PNG to content bounds, resize to print resolution, save to temp file."""
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
        target_h = int(display_h_mm / 25.4 * dpi)
        aspect = cropped.width / cropped.height
        target_w = int(target_h * aspect)
        resized = cropped.resize((target_w, target_h), Image.LANCZOS)
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
PENDING_CLR = colors.HexColor('#94a3b8')

STATUS_LABELS = {
    'requested': 'Requested', 'verified': 'Verified', 'approved': 'Approved',
    'prepared': 'Prepared', 'submitted': 'Submitted', 'cleared': 'Cleared',
    'rejected': 'Rejected', 'cancelled': 'Cancelled',
}

PAGE_W, PAGE_H = A4
L_MARGIN = 18 * mm
R_MARGIN = 18 * mm
T_MARGIN = 14 * mm
B_MARGIN = 16 * mm
AVAIL_W  = PAGE_W - L_MARGIN - R_MARGIN


# ── Canvas (top/bottom brand stripe + footer) ────────────────────────────────
class _ChequeCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self._ref_no = kwargs.pop('ref_no', None)
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
        left = f'Amaan Systems LLC · {self._ref_no}' if self._ref_no else 'Amaan Systems LLC'
        self.drawString(L_MARGIN, 2.1 * mm, left)
        self.drawRightString(PAGE_W - R_MARGIN, 2.1 * mm,
                             f'Page {self._pageNumber} of {total_pages}')
        self.restoreState()


# ── Helpers ──────────────────────────────────────────────────────────────────
def _xml_escape(text):
    """Escape text for ReportLab Paragraph and keep real newlines as <br/> so
    multi-line remarks grow the cell/box instead of being flattened to one line."""
    if text is None:
        return ''
    s = str(text)
    s = (s.replace('&', '&amp;')
           .replace('<', '&lt;')
           .replace('>', '&gt;'))
    # Normalize line breaks → Paragraph line breaks (2nd line, 3rd line, …)
    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br/>')
    return s


def _p(text, size=9, bold=False, color=INK, align=TA_LEFT, leading=None, italic=False):
    raw = str(text) if (text is not None and str(text) != '') else '—'
    txt = _xml_escape(raw)
    font_name = _font(bold)
    if italic and not _USE_SF:
        font_name = 'Helvetica-Oblique'
    return Paragraph(
        txt,
        ParagraphStyle('_', fontName=font_name, fontSize=size,
                       textColor=color, alignment=align,
                       leading=leading or (size * 1.45)),
    )


def _rule(color=RULE, thickness=0.6):
    return HRFlowable(width='100%', thickness=thickness, color=color,
                      spaceAfter=4, spaceBefore=4)


def _aed(v):
    return f'AED {float(v or 0):,.2f}'


def _fmt_date(d):
    if not d:
        return '—'
    try:
        return d.strftime('%d %b %Y')
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
        # Extra vertical padding so remarks / multi-line content has room
        ('TOPPADDING',    (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 7),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 7),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('GRID',          (0, 0), (-1, -1), 0.4, RULE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
    ]))
    return t


def _content_box(text_or_flowables):
    """Bordered content area that grows with the text (wraps / multi-line)."""
    if isinstance(text_or_flowables, list):
        parts = list(text_or_flowables)
    else:
        parts = [_p(text_or_flowables, 9)]
    if not parts:
        parts = [_p('—', 9)]
    inner_w = AVAIL_W - 16
    inner = Table([[p] for p in parts], colWidths=[inner_w])
    inner.setStyle(TableStyle([
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    t = Table([[inner]], colWidths=[AVAIL_W])
    t.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.6, RULE),
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#fafafa')),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _load_sig_image(b64_data, width=42 * mm, height=14 * mm):
    """Convert a base64 data-URL signature into a ReportLab Image, or None."""
    if not b64_data:
        return None
    try:
        raw = b64_data.split(',', 1)[1] if ',' in b64_data else b64_data
        return RLImage(io.BytesIO(base64.b64decode(raw)), width=width, height=height)
    except Exception as e:
        logger.warning('Could not decode cheque signature for PDF: %s', e)
        return None


def _sig_block(role, name, sig_date, signature=None):
    """One Requested/Verified/Approved-by column: role, NAME, SIGNATURE ink, DATE."""
    pending = not bool(name)
    name_p = _p(name if name else 'Pending', 9.5, bold=not pending,
               color=(PENDING_CLR if pending else INK), italic=pending)
    sig_img = _load_sig_image(signature)
    sig_cell = sig_img if sig_img is not None else Spacer(1, 14)
    rows = [
        [_p(role.upper(), 7.5, bold=True, color=colors.white)],
        [Spacer(1, 3)],
        [_p('NAME:', 6.8, bold=True, color=MUTED)],
        [name_p],
        [Spacer(1, 7)],
        [_p('SIGNATURE:', 6.8, bold=True, color=MUTED)],
        [sig_cell],
        [HRFlowable(width='92%', thickness=0.6, color=RULE)],
        [Spacer(1, 4)],
        [_p('DATE:', 6.8, bold=True, color=MUTED),],
        [_p(_fmt_date(sig_date) if sig_date else '—', 8.5, bold=True)],
    ]
    t = Table(rows, colWidths=[None])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, 0), BRAND),
        ('TOPPADDING',    (0, 0), (0, 0), 6),
        ('BOTTOMPADDING', (0, 0), (0, 0), 6),
        ('LEFTPADDING',   (0, 0), (0, 0), 8),
        ('LEFTPADDING',   (0, 1), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 1), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
        ('BOX',           (0, 0), (-1, -1), 0.6, RULE),
    ]))
    return t


# ── Main entry point ─────────────────────────────────────────────────────────
def build_cheque_pdf(cheque, output_stream):
    """Render a cheque preparation / request form to output_stream (BytesIO)."""

    ref_no = cheque.reference_no

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
        title=f'{ref_no} - Cheque Preparation Form',
    )

    story = []

    # ── 1. HERO HEADER ───────────────────────────────────────────────────────
    LOGO_H = 26 * mm
    brand_col = AVAIL_W * 0.38

    logo_img = None
    if logo_path:
        try:
            from PIL import Image as _PILImg
            with _PILImg.open(logo_path) as _pil:
                _pw, _ph = _pil.size
            _aspect = _pw / _ph
            _logo_h = LOGO_H
            _logo_w = min(_logo_h * _aspect, brand_col)
            logo_img = RLImage(logo_path, width=_logo_w, height=_logo_h, hAlign='RIGHT')
        except Exception as e:
            logger.warning('RLImage failed: %s', e)

    hero_right_content = logo_img if logo_img else _p('Amaan', 16, bold=True, color=BRAND, align=TA_RIGHT)
    hero_right = Table([[hero_right_content]], colWidths=[brand_col])
    hero_right.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))

    hero_left = Table([
        [_p('CHEQUE PREPARATION / REQUEST FORM', 17, bold=True, color=ACCENT)],
        [_p('AMAAN SYSTEMS LLC', 8.5, bold=True, color=MUTED)],
    ], colWidths=[AVAIL_W * 0.62])
    hero_left.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (0, 0), 2),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
    ]))

    hero_tbl = Table([[hero_left, hero_right]], colWidths=[AVAIL_W * 0.62, brand_col])
    hero_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(hero_tbl)
    story.append(_rule(color=ACCENT, thickness=2))
    story.append(Spacer(1, 6))

    # ── 2. META ROW: reference/status + office/department ───────────────────
    status_label = STATUS_LABELS.get(cheque.status, (cheque.status or '').title())
    meta_left = Table([
        [_p('REFERENCE NO:', 8, bold=True, color=MUTED), _p(ref_no, 8.5, bold=True)],
        [_p('STATUS:',       8, bold=True, color=MUTED), _p(status_label.upper(), 8.5, bold=True, color=ACCENT)],
        [_p('REQUEST DATE:', 8, bold=True, color=MUTED), _p(_fmt_date(cheque.requested_date), 8.5)],
    ], colWidths=[32 * mm, AVAIL_W * 0.32])
    meta_left.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))

    meta_right = Table([
        [_p('OFFICE:',     8, bold=True, color=MUTED), _p(cheque.office or '—', 8.5, bold=True)],
        [_p('DEPARTMENT:', 8, bold=True, color=MUTED), _p(cheque.department or 'Finance', 8.5, bold=True)],
    ], colWidths=[32 * mm, AVAIL_W * 0.32])
    meta_right.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))

    meta_tbl = Table([[meta_left, meta_right]], colWidths=[AVAIL_W * 0.5, AVAIL_W * 0.5])
    meta_tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8))
    story.append(_rule())
    story.append(Spacer(1, 6))

    # ── 3. SUPPLIER / ITEMS TABLE ────────────────────────────────────────────
    story.append(_p('SUPPLIER LINES', 9, bold=True, color=BRAND))
    story.append(Spacer(1, 3))

    header = ['SN', 'Supplier', 'Amount (AED)', 'Date', 'Remarks']
    rows = [header]
    items = list(cheque.items) if cheque.items else []
    for it in items:
        rows.append([
            _p(str(it.sn), 8.5, align=TA_CENTER),
            _p(it.supplier, 8.5, bold=True),
            _p(_aed(it.amount), 8.5, align=TA_RIGHT),
            _p(_fmt_date(it.cheque_date), 8.5),
            # Multi-line remarks wrap and grow the row height automatically
            _p(it.remarks or '—', 8.5, color=MUTED),
        ])
    if not items:
        rows.append([
            _p('—', 8.5, align=TA_CENTER),
            _p('No supplier lines recorded', 8.5, color=MUTED),
            _p('', 8.5), _p('', 8.5), _p('', 8.5),
        ])
    # Wider Remarks column — content wraps to 2nd/3rd line and scales the PDF
    col_w = [AVAIL_W * x for x in (0.06, 0.26, 0.16, 0.14, 0.38)]
    story.append(_items_table(rows, col_w))
    story.append(Spacer(1, 4))

    # Total
    w1, w2 = AVAIL_W * 0.75, AVAIL_W * 0.25
    total_tbl = Table([[_p('TOTAL', 10.5, bold=True, color=colors.white, align=TA_RIGHT),
                        _p(_aed(cheque.total_amount), 10.5, bold=True, color=colors.white, align=TA_RIGHT)]],
                      colWidths=[w1, w2])
    total_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), TOTAL_BG),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    story.append(total_tbl)
    story.append(Spacer(1, 14))

    # ── 4. SIGNATURE BLOCKS ──────────────────────────────────────────────────
    story.append(_p('APPROVAL SIGNATORIES', 9, bold=True, color=BRAND))
    story.append(Spacer(1, 5))
    gap = 8
    sig_w = (AVAIL_W - 2 * gap) / 3
    sig_row = Table([[
        _sig_block('Requested by', cheque.requested_by_name, cheque.requested_date,
                   getattr(cheque, 'requested_signature', None)), '',
        _sig_block('Verified by', cheque.verified_by_name, cheque.verified_date,
                   getattr(cheque, 'verified_signature', None)), '',
        _sig_block('Approved by', cheque.approved_by_name, cheque.approved_date,
                   getattr(cheque, 'approved_signature', None)),
    ]], colWidths=[sig_w, gap, sig_w, gap, sig_w])
    sig_row.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(sig_row)
    story.append(Spacer(1, 14))

    # ── 5. ATTACHED DOCUMENTS — one line per doc, box grows as needed ────────
    story.append(_p('ATTACHED DOCUMENTS', 8.5, bold=True, color=MUTED))
    story.append(Spacer(1, 3))
    docs = [d.strip() for d in (cheque.attached_documents or '').split('\n') if d.strip()]
    if docs:
        doc_flow = [_p(f'{i + 1}.  {d}', 9) for i, d in enumerate(docs)]
        story.append(_content_box(doc_flow))
    else:
        story.append(_content_box('—'))

    def _canvas_factory(*args, **kwargs):
        kwargs['ref_no'] = ref_no
        return _ChequeCanvas(*args, **kwargs)

    try:
        doc.build(story, canvasmaker=_canvas_factory)
    finally:
        if logo_path and logo_path != raw_logo:
            try:
                os.unlink(logo_path)
            except Exception:
                pass

    return output_stream
