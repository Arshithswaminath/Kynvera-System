"""
Amaan Service Report PDF builder.

Reproduces the paper Service Report template using ReportLab.
Layout mirrors the physical form exactly:
  header (logo · SERVICE REPORT · contact + SRN),
  the boxed general-info grid (Customer / Job No / Page, Site / Location,
  Engineer, Fire Alarm System, tall Date cell, and the Arrive/Left/Travel/Total
  time table down the right edge),
  the Fire Fighting + Type of Job band,
  ruled Comments area,
  side-by-side Parts Used / Parts Required tables,
  Customer Remarks, and the Customer / Engineer signature footer.

This is the client-facing document — no internal pricing.
"""
import io
import os
import base64
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image as RLImage, HRFlowable,
)
from reportlab.graphics.shapes import Drawing, Rect, Circle, PolyLine
from reportlab.pdfgen.canvas import Canvas

logger = logging.getLogger(__name__)

# ── Brand constants ───────────────────────────────────────────────────────────
RED       = colors.HexColor('#d21725')
DARK_RED  = colors.HexColor('#a8121e')
BLACK     = colors.black
WHITE     = colors.white
LIGHT_GRAY = colors.HexColor('#f5f5f5')
BORDER    = colors.HexColor('#333333')
RULE      = colors.HexColor('#bdbdbd')

PAGE_W, PAGE_H = A4
MARGIN_L = 14 * mm
MARGIN_R = 12 * mm
MARGIN_T = 12 * mm
MARGIN_B = 12 * mm
AVAIL_W  = PAGE_W - MARGIN_L - MARGIN_R

# Authoritative AMAAN contact block (from the paper template)
CONTACT_LINES = [
    'Tel.: +971 6 741 2778',
    'Fax: +971 6 741 2595',
    'P.O. Box: 7777, Ajman, UAE',
    'e-mail: info@amaanajh.com',
    'Website: www.amaanajh.com',
]

# ── Styles ────────────────────────────────────────────────────────────────────
def _s(name, **kw):
    base = kw.pop('parent', None)
    defaults = dict(fontName='Helvetica', fontSize=8, leading=10, textColor=BLACK)
    if base:
        for k, v in base.__dict__.items():
            if not k.startswith('_'):
                defaults[k] = v
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

LABEL  = _s('SR_Label', fontSize=6.5, fontName='Helvetica-Bold', textColor=colors.HexColor('#555555'))
VALUE  = _s('SR_Value', fontSize=8.5, fontName='Helvetica', leading=11)
BOLD9  = _s('SR_Bold9', fontSize=9, fontName='Helvetica-Bold')
TITLE  = _s('SR_Title', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER)
SMALL  = _s('SR_Small', fontSize=7, leading=9, textColor=colors.HexColor('#444444'))
TINY   = _s('SR_Tiny', fontSize=5.5, fontName='Helvetica-Bold', textColor=colors.HexColor('#777777'))
RED_SM = _s('SR_RedSm', fontSize=7.5, leading=10, fontName='Helvetica-Bold', textColor=RED)
SRN_ST = _s('SR_Srn', fontSize=8, leading=14, fontName='Helvetica-Bold',
            textColor=BLACK, alignment=TA_LEFT)
CENTER = _s('SR_Center', fontSize=8.5, alignment=TA_CENTER)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _cell(text, style=None):
    """Paragraph cell shorthand."""
    return Paragraph(str(text) if text not in (None, '') else '', style or VALUE)


def _hm(d: dict) -> str:
    """{'h':9,'m':30} → '09:30' or '—'"""
    if not d or d.get('h') is None:
        return '—'
    return f"{int(d['h']):02d}:{int(d['m']):02d}"


def _hm_diff(arrive, left) -> str:
    """Return HH:MM difference string or ''."""
    if not arrive or not left:
        return ''
    try:
        ah, am = int(arrive.get('h', 0) or 0), int(arrive.get('m', 0) or 0)
        lh, lm = int(left.get('h', 0) or 0), int(left.get('m', 0) or 0)
        total = (lh * 60 + lm) - (ah * 60 + am)
        if total < 0:
            return ''
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return ''


def _split_hm(s: str):
    """'09:30' → ('09', '30'); '—' / '' → ('', '')."""
    if s and ':' in s:
        h, m = s.split(':', 1)
        return h, m
    return '', ''


def _cb(checked: bool) -> str:
    """Unicode checkbox character (kept for compatibility; drawn markers preferred)."""
    return '☑' if checked else '☐'


def _checkbox(checked: bool, size=3.4 * mm) -> Drawing:
    """Vector checkbox — font-independent so it renders on any platform."""
    d = Drawing(size, size)
    d.add(Rect(0.4, 0.4, size - 0.8, size - 0.8, rx=0.5, ry=0.5,
               strokeColor=BORDER, strokeWidth=0.8, fillColor=None))
    if checked:
        s = size
        d.add(PolyLine([s * 0.22, s * 0.50, s * 0.42, s * 0.28, s * 0.80, s * 0.78],
                       strokeColor=RED, strokeWidth=1.2,
                       strokeLineCap=1, strokeLineJoin=1))
    d.hAlign = 'CENTER'
    return d


def _radio(selected: bool, size=3.4 * mm) -> Drawing:
    """Vector radio marker — outline circle, filled when selected."""
    d = Drawing(size, size)
    cx = cy = size / 2
    r = (size - 0.9) / 2
    d.add(Circle(cx, cy, r, strokeColor=BORDER, strokeWidth=0.8, fillColor=None))
    if selected:
        d.add(Circle(cx, cy, r * 0.5, strokeColor=None, fillColor=RED))
    d.hAlign = 'CENTER'
    return d


def _lc(label: str, value):
    """Stacked label (small bold) + value — one info-grid cell."""
    return [Paragraph(label, LABEL), Paragraph(str(value) if value not in (None, '') else '', VALUE)]


def _load_sig_image(b64_data: str, width=46 * mm, height=15 * mm):
    """Convert base64 data-URL to RLImage. Returns None on failure."""
    if not b64_data:
        return None
    try:
        if ',' in b64_data:
            b64_data = b64_data.split(',', 1)[1]
        raw = base64.b64decode(b64_data)
        buf = io.BytesIO(raw)
        # Fixed dimensions — no proportional scaling to avoid None-width errors
        return RLImage(buf, width=width, height=height)
    except Exception as e:
        logger.warning('Could not decode service report signature: %s', e)
        return None


def _logo_image(path: str, height=16 * mm):
    if not path or not os.path.exists(path):
        return None
    try:
        tmp = RLImage(path)
        # Compute width from aspect ratio so we never pass width=None
        ratio = (tmp.imageWidth / tmp.imageHeight) if tmp.imageHeight else 2.5
        return RLImage(path, width=height * ratio, height=height)
    except Exception:
        return None


# ── Canvas (footer with page numbers) ─────────────────────────────────────────
class _SRCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        kwargs.pop('logo_path', None)
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states):
            self.__dict__.update(state)
            self.setFont('Helvetica', 7)
            self.setFillColor(colors.HexColor('#888888'))
            self.drawRightString(PAGE_W - MARGIN_R, 6 * mm,
                                 f'Page {i+1} of {n} — Amaan Facilities Management')
            super().showPage()
        super().save()


# ── Main builder ──────────────────────────────────────────────────────────────
def build_service_report_pdf(ticket, sr_data: dict, materials: list, output_stream):
    """
    Build the Amaan Service Report PDF into output_stream.

    :param ticket:       Ticket model instance
    :param sr_data:      Merged service_report_data dict (from service_report.merge_service_report_data)
    :param materials:    List of TicketMaterial instances
    :param output_stream: Writable binary stream
    """
    doc = SimpleDocTemplate(
        output_stream,
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=f"Service Report — {ticket.ticket_id}",
    )

    # Logo candidates
    logo_path = None
    for cand in [
        'static/icons/AMAAN Logo - Edited.png',
        'static/icons/Amaan.png',
        'static/icons/icon-144x144.png',
        'static/logo.png',
    ]:
        if os.path.exists(cand):
            logo_path = cand
            break

    story = []
    story.append(_build_header(sr_data, logo_path))
    story.append(Spacer(1, 2 * mm))
    story.append(_build_general_info(ticket, sr_data))
    story.append(_build_system_jobtype(sr_data))
    story.append(_build_comments(sr_data))
    story.append(_build_parts_row(sr_data, materials))
    story.append(_build_customer_remarks(sr_data))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_build_signatures(ticket, sr_data))

    doc.build(story, canvasmaker=_SRCanvas)


# ── Section builders ──────────────────────────────────────────────────────────

def _build_header(sr_data: dict, logo_path: str) -> Table:
    """Open header: logo | SERVICE REPORT (underlined) | contact block + SRN."""
    logo = _logo_image(logo_path, height=21 * mm)
    logo_cell = logo if logo else Paragraph('AMAAN', _s('SR_LogoTxt', fontSize=18,
                                                        fontName='Helvetica-Bold', textColor=DARK_RED))

    title_cell = Paragraph('<u>SERVICE REPORT</u>', TITLE)

    contact_cell = [Paragraph(line, RED_SM) for line in CONTACT_LINES]

    srn = sr_data.get('service_report_no', '')
    srn_para = Paragraph(
        f'SRN: <font size="14" color="#d21725">{srn}</font>' if srn else 'SRN:',
        SRN_ST,
    )

    # Contact block sits above the SRN line, both right-aligned in the right column
    right_block = Table([[c] for c in contact_cell] + [[srn_para]],
                        colWidths=[AVAIL_W * 0.34])
    right_block.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING',    (0, -1), (-1, -1), 3),  # gap above SRN
    ]))

    tbl = Table(
        [[logo_cell, title_cell, right_block]],
        colWidths=[AVAIL_W * 0.24, AVAIL_W * 0.42, AVAIL_W * 0.34],
    )
    tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (1, 0),   'MIDDLE'),
        ('VALIGN',        (2, 0), (2, 0),   'TOP'),
        ('ALIGN',         (0, 0), (0, 0),   'LEFT'),
        ('ALIGN',         (1, 0), (1, 0),   'CENTER'),
        ('ALIGN',         (2, 0), (2, 0),   'RIGHT'),
        ('LEFTPADDING',   (0, 0), (-1, -1),  0),
        ('RIGHTPADDING',  (0, 0), (-1, -1),  0),
        ('TOPPADDING',    (0, 0), (-1, -1),  0),
        ('BOTTOMPADDING', (0, 0), (-1, -1),  0),
    ]))
    return tbl


def _build_general_info(ticket, sr_data: dict) -> Table:
    """
    The boxed general-info grid — faithful to the paper:

        Customer (tall) | Job No        | Page: 1 of 1
                        | Site Name     | Location
        Engineer/Technician (wide)      | Date  | Time Arrive  Hrs  Mns
        Fire Alarm System (wide)        | (tall | Time Left    Hrs  Mns
        Qty:        | Type:             | date) | Travel Time  Hrs  Mns
        Make:       | No of Zones/Loops | (tall)| Total        Hrs  Mns
    """
    customer = sr_data.get('client_name') or ticket.project or ''
    job_no   = sr_data.get('job_no') or ticket.ticket_id or ''
    site_name = sr_data.get('site_name') or ticket.property_name or ''
    location  = sr_data.get('location') or '  /  '.join(
        filter(None, [ticket.zone, ticket.sub_zone, ticket.base_unit]))

    tech = sr_data.get('technician_name') or ''
    if not tech:
        if getattr(ticket, 'technician', None):
            tech = ticket.technician.full_name
        elif getattr(ticket, 'assigned_to', None):
            tech = ticket.assigned_to.full_name

    svc_date = sr_data.get('service_date', '')
    if svc_date:
        try:
            svc_date = datetime.strptime(svc_date, '%Y-%m-%d').strftime('%d %b %Y')
        except ValueError:
            pass

    fa = sr_data.get('fire_alarm', {}) or {}

    # ── Nested time table (right column, spans rows 3–6) ──
    total_str = _hm(sr_data.get('total_time'))
    if total_str == '—':
        total_str = _hm_diff(sr_data.get('time_arrive'), sr_data.get('time_left')) or ''

    def _time_row(label, hm_str):
        h, m = _split_hm(hm_str)
        return [
            Paragraph(label, LABEL),
            Paragraph('Hrs', TINY), Paragraph(h, VALUE),
            Paragraph('Mns', TINY), Paragraph(m, VALUE),
        ]

    w_time = AVAIL_W * 0.32
    time_tbl = Table(
        [
            _time_row('Time Arrive', _hm(sr_data.get('time_arrive'))),
            _time_row('Time Left',   _hm(sr_data.get('time_left'))),
            _time_row('Travel Time', _hm(sr_data.get('travel_time'))),
            _time_row('Total',       total_str),
        ],
        colWidths=[w_time * 0.40, w_time * 0.14, w_time * 0.16, w_time * 0.14, w_time * 0.16],
    )
    time_tbl.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -1), 0.4, RULE),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 2),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 2),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    # ── Outer 4-column grid (c0,c1 = left; c2 = middle/Date; c3 = right/time) ──
    blank = ''
    data = [
        # Row 0
        [_lc('Customer', customer), blank, _lc('Job No', job_no),  _lc('Page', '1  of  1')],
        # Row 1
        [blank, blank,                   _lc('Site Name', site_name), _lc('Location', location)],
        # Row 2
        [_lc('Engineer / Technician', tech), blank, _lc('Date', svc_date), time_tbl],
        # Row 3
        [[Paragraph('Fire Alarm System', BOLD9)], blank, blank, blank],
        # Row 4
        [_lc('Qty', fa.get('qty', '')), _lc('Type', fa.get('type', '')), blank, blank],
        # Row 5
        [_lc('Make', fa.get('make', '')), _lc('No. of Zones / Loops', fa.get('zones_loops', '')), blank, blank],
    ]

    cw = [AVAIL_W * 0.21, AVAIL_W * 0.24, AVAIL_W * 0.23, AVAIL_W * 0.32]
    rh = [10 * mm, 10 * mm, 9 * mm, 7 * mm, 9 * mm, 9 * mm]
    outer = Table(data, colWidths=cw, rowHeights=rh)
    outer.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -1), 0.6, BORDER),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        # Customer — tall cell spanning rows 0–1 across c0–c1
        ('SPAN',          (0, 0), (1, 1)),
        # Engineer / Technician — wide across c0–c1
        ('SPAN',          (0, 2), (1, 2)),
        # Fire Alarm System heading — wide across c0–c1
        ('SPAN',          (0, 3), (1, 3)),
        # Date — tall cell spanning rows 2–5 (c2)
        ('SPAN',          (2, 2), (2, 5)),
        # Time table — tall cell spanning rows 2–5 (c3)
        ('SPAN',          (3, 2), (3, 5)),
        ('VALIGN',        (3, 2), (3, 5), 'MIDDLE'),
        ('LEFTPADDING',   (3, 2), (3, 5), 0),
        ('RIGHTPADDING',  (3, 2), (3, 5), 0),
        ('TOPPADDING',    (3, 2), (3, 5), 0),
        ('BOTTOMPADDING', (3, 2), (3, 5), 0),
    ]))
    return outer


def _build_system_jobtype(sr_data: dict) -> Table:
    """
    Fire Fighting checklist (2-up, each with its own drawn checkbox) on the left,
    Type of Job (single-choice radios) on the right — mirrors the paper's columns.
    """
    ff = sr_data.get('fire_fighting', {}) or {}
    jt = sr_data.get('job_type', '')
    jt_other = sr_data.get('job_type_other', '')

    ff_items = [
        ('fire_extinguisher', 'Fire Extinguisher'),
        ('gas_suppression',   'Gas Suppression'),
        ('hose_reel',         'Hose Reel'),
        ('kitchen_hood',      'Kitchen Hood'),
        ('sprinkler',         'Sprinkler'),
        ('wet_dry_riser',     'Wet / Dry Riser'),
        ('fire_pump_set',     'Fire Pump Set'),
        ('others',            'Others'),
    ]

    job_types = [
        ('maintenance',   'Maintenance'),
        ('installation',  'Installation'),
        ('rectification', 'Rectification'),
        ('others',        'Others'),
    ]

    def _ff_label(key, label):
        if key == 'others':
            txt = ff.get('others_text') or ''
            label = f'Others: {txt}' if txt else 'Others'
        return Paragraph(label, VALUE)

    def _jt_label(key, label):
        if key == 'others' and jt == 'others' and jt_other:
            label = f'Others: {jt_other}'
        return Paragraph(label, VALUE)

    # 6 columns: FF-label-A | box | FF-label-B | box | JobType-label | radio
    rows = [[
        Paragraph('Fire Fighting System', BOLD9), '', '', '',
        Paragraph('Type of Job', BOLD9), '',
    ]]
    for i in range(4):
        k1, l1 = ff_items[i * 2]
        k2, l2 = ff_items[i * 2 + 1]
        jt_key, jt_label = job_types[i]
        rows.append([
            _ff_label(k1, l1), _checkbox(bool(ff.get(k1))),
            _ff_label(k2, l2), _checkbox(bool(ff.get(k2))),
            _jt_label(jt_key, jt_label), _radio(jt == jt_key),
        ])

    cw = [AVAIL_W * 0.20, AVAIL_W * 0.05, AVAIL_W * 0.23, AVAIL_W * 0.05,
          AVAIL_W * 0.37, AVAIL_W * 0.10]
    tbl = Table(rows, colWidths=cw)
    tbl.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
        # vertical divider between fire-fighting and type-of-job regions
        ('LINEBEFORE',    (4, 0), (4, -1), 0.6, BORDER),
        ('LINEBELOW',     (0, 0), (-1, 0), 0.6, BORDER),
        ('SPAN',          (0, 0), (3, 0)),   # "Fire Fighting System" header
        ('SPAN',          (4, 0), (5, 0)),   # "Type of Job" header
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (1, 0), (1, -1),  'CENTER'),
        ('ALIGN',         (3, 0), (3, -1),  'CENTER'),
        ('ALIGN',         (5, 0), (5, -1),  'CENTER'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    return tbl


def _build_comments(sr_data: dict) -> Table:
    """Boxed Comments area: 'Comments:' header row, then ruled lines."""
    comments = sr_data.get('comments', '') or ''
    lines = [ln for ln in comments.split('\n')] if comments else []

    MIN_LINES = 10
    while len(lines) < MIN_LINES:
        lines.append('')

    rows = [[Paragraph('Comments:', BOLD9)]]
    rows += [[Paragraph(ln if ln.strip() else ' ', VALUE)] for ln in lines]

    tbl = Table(rows, colWidths=[AVAIL_W])
    style = [
        ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
        ('LINEBELOW',     (0, 0), (0, 0),   0.6, BORDER),  # under header
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    # ruled lines between comment rows (skip header)
    for i in range(2, len(rows)):
        style.append(('LINEABOVE', (0, i), (-1, i), 0.3, RULE))
    tbl.setStyle(TableStyle(style))
    return tbl


def _build_parts_row(sr_data: dict, materials: list) -> Table:
    """Side-by-side Parts Used (from materials) | Parts Required (from sr_data)."""
    MIN_ROWS = 6

    def _qty_str(q):
        try:
            return str(int(q)) if float(q) == int(float(q)) else str(q)
        except (TypeError, ValueError):
            return str(q) if q not in (None, '') else ''

    def _parts_table(title, header_rows, col_fracs):
        head = [[
            Paragraph(title, BOLD9),
            Paragraph('Specification', BOLD9),
            Paragraph('Qty', BOLD9),
        ]]
        rows = head + header_rows
        while len(rows) < MIN_ROWS + 1:
            rows.append(['', '', ''])
        t = Table(rows, colWidths=col_fracs)
        t.setStyle(TableStyle([
            ('BOX',          (0, 0), (-1, -1), 0.6, BORDER),
            ('INNERGRID',    (0, 0), (-1, -1), 0.3, RULE),
            ('BACKGROUND',   (0, 0), (-1, 0), LIGHT_GRAY),
            ('FONTSIZE',     (0, 0), (-1, -1), 8),
            ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
            ('ALIGN',        (2, 0), (2, -1), 'CENTER'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING',   (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
        ]))
        return t

    half = AVAIL_W * 0.48
    pu_cols = [half * 0.46, half * 0.38, half * 0.16]
    pr_cols = [half * 0.46, half * 0.38, half * 0.16]

    pu_rows = [[
        Paragraph(m.material_name or '', VALUE),
        Paragraph(m.notes or '', SMALL),
        Paragraph(_qty_str(getattr(m, 'quantity', '')), VALUE),
    ] for m in (materials or [])]

    pr_rows = [[
        Paragraph(r.get('part', '') or '', VALUE),
        Paragraph(r.get('specification', '') or '', SMALL),
        Paragraph(_qty_str(r.get('qty', '')), VALUE),
    ] for r in (sr_data.get('parts_required', []) or [])]

    pu_tbl = _parts_table('Parts Used', pu_rows, pu_cols)
    pr_tbl = _parts_table('Parts Required', pr_rows, pr_cols)

    gap = Table([['']], colWidths=[AVAIL_W * 0.04])
    gap.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))

    outer = Table([[pu_tbl, gap, pr_tbl]],
                  colWidths=[AVAIL_W * 0.48, AVAIL_W * 0.04, AVAIL_W * 0.48])
    outer.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return outer


def _build_customer_remarks(sr_data: dict) -> Table:
    """Boxed Customer Remarks: header row + 3 ruled lines."""
    remarks = sr_data.get('customer_remarks', '') or ''
    lines = (remarks.split('\n') + ['', '', ''])[:3]

    rows = [[Paragraph('Customer Remarks:', BOLD9)]]
    rows += [[Paragraph(ln if ln.strip() else ' ', VALUE)] for ln in lines]

    tbl = Table(rows, colWidths=[AVAIL_W])
    style = [
        ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
        ('LINEBELOW',     (0, 0), (0, 0),   0.6, BORDER),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]
    for i in range(2, len(rows)):
        style.append(('LINEABOVE', (0, i), (-1, i), 0.3, RULE))
    tbl.setStyle(TableStyle(style))
    return tbl


def _build_signatures(ticket, sr_data: dict) -> Table:
    """Two-column footer: Customer (Name/Signature/Mobile) | Engineer (Name/Signature/ID)."""
    cust_name = ticket.client_signed_by or sr_data.get('client_name') or ''
    cust_mob  = sr_data.get('client_mobile') or ticket.client_mobile or ''
    cust_sig  = _load_sig_image(ticket.client_signature)

    tech_obj = getattr(ticket, 'technician', None) or getattr(ticket, 'assigned_to', None)
    tech_name = (sr_data.get('technician_name')
                 or (tech_obj.full_name if tech_obj else None)
                 or ticket.close_signed_by or '')
    tech_id   = sr_data.get('technician_id_no') or ticket.technician_id_no or ''
    tech_sig  = _load_sig_image(ticket.close_signature)

    def _sig_block(title, name_label, name_val, sig_img, last_label, last_val):
        rows = [
            [Paragraph(f'<b>{name_label}</b>  {name_val}', VALUE)],
            [sig_img if sig_img else Paragraph('', VALUE)],
            [Paragraph(f'<b>{last_label}</b>  {last_val}', VALUE)],
        ]
        t = Table(rows, colWidths=[AVAIL_W * 0.48], rowHeights=[9 * mm, 18 * mm, 9 * mm])
        t.setStyle(TableStyle([
            ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
            ('LINEBELOW',     (0, 0), (-1, 0), 0.3, RULE),
            ('LINEBELOW',     (0, 1), (-1, 1), 0.3, RULE),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        # second row holds the signature image — top-anchor the caption row text
        return t

    cust_tbl = _sig_block('Customer', 'Customer Name :', cust_name, cust_sig, 'Mobile No:', cust_mob)
    tech_tbl = _sig_block('Engineer', 'Engineer/Technician Name:', tech_name, tech_sig, 'ID No:', tech_id)

    gap = Table([['']], colWidths=[AVAIL_W * 0.04])
    outer = Table([[cust_tbl, gap, tech_tbl]],
                  colWidths=[AVAIL_W * 0.48, AVAIL_W * 0.04, AVAIL_W * 0.48])
    outer.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return outer
