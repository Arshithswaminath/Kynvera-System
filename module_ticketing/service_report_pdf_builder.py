"""
Amaan Service Report PDF builder.

Reproduces the paper Service Report template using ReportLab.
Layout mirrors the physical form exactly:
  header (logo · SERVICE REPORT · contact + SRN),
  the boxed general-info grid (Customer / Job No / Page, Site / Location,
  Engineer, Fire Alarm System, tall Date cell, and the Arrive/Left/Travel/Total
  time table down the right edge),
  the Fire Fighting + Type of Job band (PPM / Inspection / Rectification / Others;
  Type of Job header includes the ticket job name),
  ruled Comments area (expanded for more work notes),
  side-by-side Parts Used / Parts Required tables (extra blank rows),
  Customer Remarks, and the Customer / Engineer signature footer.

This is the client-facing document — no internal pricing.
SRN is assigned by the application via get_or_assign_service_report_no().
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
    Spacer, Image as RLImage,
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
# Tight page margins — stay A4 but use the full printable area
MARGIN_L = 12 * mm
MARGIN_R = 11 * mm
MARGIN_T = 7 * mm
MARGIN_B = 8 * mm
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
VALUE  = _s('SR_Value', fontSize=8, fontName='Helvetica', leading=10)
BOLD9  = _s('SR_Bold9', fontSize=8.5, fontName='Helvetica-Bold', leading=10)
BOLD8  = _s('SR_Bold8', fontSize=8, fontName='Helvetica-Bold', leading=9.5)
TITLE  = _s('SR_Title', fontSize=16, fontName='Helvetica-Bold', alignment=TA_CENTER)
SMALL  = _s('SR_Small', fontSize=7, leading=8.5, textColor=colors.HexColor('#444444'))
TINY   = _s('SR_Tiny', fontSize=5.5, fontName='Helvetica-Bold', textColor=colors.HexColor('#777777'))
RED_SM = _s('SR_RedSm', fontSize=7.5, leading=10, fontName='Helvetica-Bold', textColor=RED)
SRN_ST = _s('SR_Srn', fontSize=8, leading=14, fontName='Helvetica-Bold',
            textColor=BLACK, alignment=TA_LEFT)
CENTER = _s('SR_Center', fontSize=8.5, alignment=TA_CENTER)
# Checklist / job-type labels — compact so they clear cell borders
CHK_VAL = _s('SR_ChkVal', fontSize=7.5, fontName='Helvetica', leading=9)

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
    """Stacked label (small bold) + value — sized to clear cell borders."""
    lbl = _s('SR_LcLbl', fontSize=6, fontName='Helvetica-Bold',
             textColor=colors.HexColor('#555555'), leading=7.5)
    val = _s('SR_LcVal', fontSize=7.5, fontName='Helvetica', leading=9)
    return [
        Paragraph(label, lbl),
        Paragraph(str(value) if value not in (None, '') else '&nbsp;', val),
    ]


def _load_sig_image(sig_data, width=46 * mm, height=15 * mm):
    """Load a signature as RLImage from data-URL, HTTP URL, path, or {url} dict."""
    if not sig_data:
        return None
    if isinstance(sig_data, dict):
        sig_data = sig_data.get('url') or sig_data.get('path') or ''
    if not sig_data:
        return None
    try:
        # Fast path: data-URL
        if isinstance(sig_data, str) and sig_data.startswith('data:image'):
            raw = sig_data.split(',', 1)[1] if ',' in sig_data else sig_data
            buf = io.BytesIO(base64.b64decode(raw))
            return RLImage(buf, width=width, height=height)

        # URL / local path / data URI via shared helper
        from common.utils import get_image_for_pdf
        img_data, is_stream = get_image_for_pdf(sig_data)
        if not img_data:
            return None
        if is_stream and hasattr(img_data, 'seek'):
            img_data.seek(0)
        return RLImage(img_data, width=width, height=height)
    except Exception as e:
        logger.warning('Could not load service report signature: %s', e)
        return None


def _find_logo_path() -> str | None:
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    for cand in [
        os.path.join(_root, 'static', 'icons', 'Amaan-logo-tight.png'),
        os.path.join(_root, 'static', 'icons', 'Amaan-mark.png'),
        os.path.join(_root, 'static', 'icons', 'AMAAN Logo - Edited.png'),
        os.path.join(_root, 'static', 'icons', 'Amaan.png'),
        os.path.join(_root, 'static', 'logo.png'),
    ]:
        if os.path.exists(cand):
            return cand
    return None


def _logo_image(path: str, height=22 * mm):
    """Load logo, crop transparent padding, and size for the PDF header."""
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as src:
            im = src.convert('RGBA')
            # Drop empty transparent margins so the mark fills the header slot
            alpha = im.split()[-1]
            bbox = alpha.getbbox()
            if bbox:
                im = im.crop(bbox)
            # Downscale huge source assets before ReportLab embeds them
            target_h = 200
            ratio = (im.width / im.height) if im.height else 1.0
            im = im.resize((max(1, int(target_h * ratio)), target_h), PILImage.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='PNG')
            buf.seek(0)
            return RLImage(buf, width=height * ratio, height=height)
    except Exception as exc:
        logger.warning('Could not load service report logo (%s): %s', path, exc)
        try:
            tmp = RLImage(path)
            ratio = (tmp.imageWidth / tmp.imageHeight) if tmp.imageHeight else 2.5
            return RLImage(path, width=height * ratio, height=height)
        except Exception:
            return None


def _stack_height(flowables, width):
    """Measure total height of a sequence of flowables at the given width."""
    total = 0.0
    for fl in flowables:
        _w, h = fl.wrap(width, PAGE_H)
        total += float(h or 0)
    return total


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
            self.drawRightString(PAGE_W - MARGIN_R, 4 * mm,
                                 f'Page {i+1} of {n} — Amaan Facilities Management')
            super().showPage()
        super().save()


# ── Main builder ──────────────────────────────────────────────────────────────
def build_service_report_page1_story(sr_data: dict, ctx, materials: list, logo_path: str | None = None):
    """
    Build page-1 Service Report flowables (exact paper template).

    ``ctx`` is duck-typed (Ticket or SimpleNamespace) with optional:
      ticket_id, project, property_name, zone, sub_zone, base_unit,
      technician, assigned_to, client_signed_by, client_signature,
      client_mobile, close_signed_by, close_signature, technician_id_no
    """
    if logo_path is None:
        logo_path = _find_logo_path()

    story = []
    story.append(_build_header(sr_data, logo_path))
    story.append(Spacer(1, 1 * mm))
    story.append(_build_general_info(ctx, sr_data))
    story.append(_build_system_jobtype(sr_data))

    # Tail of the form (everything after Comments) — kept flush, no spacers between boxes
    parts = _build_parts_row(sr_data, materials)
    remarks = _build_customer_remarks(sr_data)
    sigs = _build_signatures(ctx, sr_data)
    tail = [parts, remarks, sigs]

    # Grow Comments to fill leftover frame height so boxes stay continuous
    frame_h = PAGE_H - MARGIN_T - MARGIN_B
    used = _stack_height(story, AVAIL_W) + _stack_height(tail, AVAIL_W)
    comments_fill = max(40 * mm, frame_h - used - 6 * mm)
    story.append(_build_comments(sr_data, fill_height=comments_fill))
    story.extend(tail)
    return story


def build_service_report_pdf(ticket, sr_data: dict, materials: list, output_stream):
    """
    Build the Amaan Service Report PDF into output_stream (page 1 only).

    :param ticket:       Ticket model instance (or duck-typed equivalent)
    :param sr_data:      Merged service_report_data dict
    :param materials:    List of TicketMaterial instances (or duck-typed)
    :param output_stream: Writable binary stream
    """
    job_id = getattr(ticket, 'ticket_id', None) or sr_data.get('job_no') or 'Service Report'
    doc = SimpleDocTemplate(
        output_stream,
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=f"Service Report — {job_id}",
    )
    story = build_service_report_page1_story(sr_data, ticket, materials)
    doc.build(story, canvasmaker=_SRCanvas)


# ── Section builders ──────────────────────────────────────────────────────────

def _build_header(sr_data: dict, logo_path: str) -> Table:
    """Open header: Amaan logo (left) | SERVICE REPORT | contact + SRN (flush right)."""
    logo = _logo_image(logo_path, height=15 * mm)
    logo_cell = logo if logo else Paragraph(
        'AMAAN',
        _s('SR_LogoTxt', fontSize=18, fontName='Helvetica-Bold', textColor=DARK_RED),
    )

    title_cell = Paragraph('<u>SERVICE REPORT</u>', TITLE)

    # Contact + SRN flush to the right edge of the page
    RED_RIGHT = _s('SR_RedRight', fontSize=7.5, leading=10,
                   fontName='Helvetica-Bold', textColor=RED, alignment=TA_RIGHT)
    SRN_RIGHT = _s('SR_SrnRight', fontSize=8, leading=14,
                   fontName='Helvetica-Bold', textColor=BLACK, alignment=TA_RIGHT)

    contact_rows = [[Paragraph(line, RED_RIGHT)] for line in CONTACT_LINES]

    srn = sr_data.get('service_report_no', '')
    srn_para = Paragraph(
        f'SRN: <font size="14" color="#d21725">{srn}</font>' if srn else 'SRN:',
        SRN_RIGHT,
    )
    contact_rows.append([srn_para])

    right_w = AVAIL_W * 0.36
    right_block = Table(contact_rows, colWidths=[right_w])
    right_block.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5),
        ('TOPPADDING',    (0, -1), (-1, -1), 2),  # gap above SRN
    ]))

    tbl = Table(
        [[logo_cell, title_cell, right_block]],
        colWidths=[AVAIL_W * 0.22, AVAIL_W * 0.42, right_w],
    )
    tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (0, 0),   'MIDDLE'),
        ('VALIGN',        (1, 0), (1, 0),   'MIDDLE'),
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


def _build_general_info(ctx, sr_data: dict) -> Table:
    """
    The boxed general-info grid — faithful to the paper:

        Customer (tall) | Job No        | Page: 1 of 1
                        | Site Name     | Location
        Engineer/Technician (wide)      | Date  | Time Arrive  Hrs  Mns
        Fire Alarm System (wide)        | (tall | Time Left    Hrs  Mns
        Qty:        | Type:             | date) | Travel Time  Hrs  Mns
        Make:       | No of Zones/Loops | (tall)| Total        Hrs  Mns
    """
    customer = sr_data.get('client_name') or getattr(ctx, 'project', None) or ''
    job_no   = sr_data.get('job_no') or getattr(ctx, 'ticket_id', None) or ''
    site_name = sr_data.get('site_name') or getattr(ctx, 'property_name', None) or ''
    location  = sr_data.get('location') or '  /  '.join(
        filter(None, [
            getattr(ctx, 'zone', None),
            getattr(ctx, 'sub_zone', None),
            getattr(ctx, 'base_unit', None),
        ]))

    tech = sr_data.get('technician_name') or ''
    if not tech:
        tech_obj = getattr(ctx, 'technician', None) or getattr(ctx, 'assigned_to', None)
        if tech_obj and getattr(tech_obj, 'full_name', None):
            tech = tech_obj.full_name

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
        ('LEFTPADDING',   (0, 0), (-1, -1), 2.5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 2.5),
        ('TOPPADDING',    (0, 0), (-1, -1), 1.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.8),
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
        # Row 3 — heading only (single flowable; do not nest a list-in-list)
        [Paragraph('Fire Alarm System', BOLD8), blank, blank, blank],
        # Row 4
        [_lc('Qty', fa.get('qty', '')), _lc('Type', fa.get('type', '')), blank, blank],
        # Row 5
        [_lc('Make', fa.get('make', '')), _lc('No. of Zones / Loops', fa.get('zones_loops', '')), blank, blank],
    ]

    cw = [AVAIL_W * 0.21, AVAIL_W * 0.24, AVAIL_W * 0.23, AVAIL_W * 0.32]
    # Tall enough for label + value + padding so glyphs never sit on grid lines
    rh = [8.5 * mm, 8.5 * mm, 9.2 * mm, 5.5 * mm, 8.5 * mm, 8.5 * mm]
    outer = Table(data, colWidths=cw, rowHeights=rh)
    outer.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -1), 0.6, BORDER),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3.5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3.5),
        ('TOPPADDING',    (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        # Customer — tall cell spanning rows 0–1 across c0–c1
        ('SPAN',          (0, 0), (1, 1)),
        ('VALIGN',        (0, 0), (1, 1), 'TOP'),
        # Engineer / Technician — wide across c0–c1
        ('SPAN',          (0, 2), (1, 2)),
        # Fire Alarm System heading — wide across c0–c1
        ('SPAN',          (0, 3), (1, 3)),
        ('VALIGN',        (0, 3), (1, 3), 'MIDDLE'),
        # Date — tall cell spanning rows 2–5 (c2)
        ('SPAN',          (2, 2), (2, 5)),
        ('VALIGN',        (2, 2), (2, 5), 'TOP'),
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
    Job name (ticket title) is shown in the Type of Job header.
    """
    ff = sr_data.get('fire_fighting', {}) or {}
    jt = sr_data.get('job_type', '') or ''
    # Legacy keys from earlier Maintenance / Installation labels
    jt = {'maintenance': 'ppm', 'installation': 'inspection'}.get(jt, jt)
    jt_other = sr_data.get('job_type_other', '')
    job_name = (sr_data.get('job_name') or '').strip()

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
        ('ppm',           'PPM'),
        ('inspection',    'Inspection'),
        ('rectification', 'Rectification'),
        ('others',        'Others'),
    ]

    def _ff_label(key, label):
        if key == 'others':
            txt = ff.get('others_text') or ''
            label = f'Others: {txt}' if txt else 'Others'
        return Paragraph(label, CHK_VAL)

    def _jt_label(key, label):
        if key == 'others' and jt == 'others' and jt_other:
            label = f'Others: {jt_other}'
        return Paragraph(label, CHK_VAL)

    # Job name under "Type of Job" — smaller type + clear of header rule
    JT_NAME = _s('SR_JtName', fontSize=6.5, fontName='Helvetica', leading=8,
                 textColor=colors.HexColor('#444444'), spaceBefore=1)
    if job_name:
        display = job_name if len(job_name) <= 48 else (job_name[:45].rstrip() + '…')
        jt_header_cell = [Paragraph('Type of Job', BOLD8), Paragraph(display, JT_NAME)]
    else:
        jt_header_cell = Paragraph('Type of Job', BOLD8)

    # 6 columns: FF-label-A | box | FF-label-B | box | JobType-label | radio
    rows = [[
        Paragraph('Fire Fighting System', BOLD8), '', '', '',
        jt_header_cell, '',
    ]]
    for i in range(4):
        k1, l1 = ff_items[i * 2]
        k2, l2 = ff_items[i * 2 + 1]
        jt_key, jt_label = job_types[i]
        rows.append([
            _ff_label(k1, l1), _checkbox(bool(ff.get(k1)), size=2.8 * mm),
            _ff_label(k2, l2), _checkbox(bool(ff.get(k2)), size=2.8 * mm),
            _jt_label(jt_key, jt_label), _radio(jt == jt_key, size=2.8 * mm),
        ])

    cw = [AVAIL_W * 0.20, AVAIL_W * 0.05, AVAIL_W * 0.23, AVAIL_W * 0.05,
          AVAIL_W * 0.37, AVAIL_W * 0.10]
    # Compact but tall enough that labels/checks clear the borders
    header_h = 8.5 * mm if job_name else 5.8 * mm
    row_h = [header_h] + [5.6 * mm] * 4
    tbl = Table(rows, colWidths=cw, rowHeights=row_h)
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
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('TOPPADDING',    (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        # Extra air under the Type of Job header rule
        ('TOPPADDING',    (4, 0), (5, 0), 2),
        ('BOTTOMPADDING', (4, 0), (5, 0), 2),
    ]))
    return tbl


def _build_comments(sr_data: dict, fill_height=None) -> Table:
    """Boxed Comments area — flush to sections above/below; grows to fill leftover page height."""
    comments = sr_data.get('comments', '') or ''
    lines = [ln for ln in (comments.split('\n') if comments else [])]

    header_h = 5.4 * mm
    # Smaller type → more lines, with padding so glyphs clear the rules
    line_h = 4.8 * mm
    _MAX_COMMENT_LINES = 20

    filled = len([ln for ln in lines if ln.strip()])
    min_lines = max(filled + 1, 8)

    if fill_height and fill_height > header_h + line_h:
        # Size row count to consume available height exactly (no gap below)
        n = max(min_lines, int((float(fill_height) - header_h) / line_h))
        n = min(n, _MAX_COMMENT_LINES)
        line_h = max(4.4 * mm, (float(fill_height) - header_h) / n)
    else:
        n = min(max(min_lines, 10), _MAX_COMMENT_LINES)

    while len(lines) < n:
        lines.append('')
    if len(lines) > n:
        lines = lines[:n - 1] + [lines[n - 1][:110].rstrip() + '…']

    COMMENT_VAL = _s('SR_CommentVal', fontSize=6.5, fontName='Helvetica', leading=8.5)
    rows = [[Paragraph('Comments:', BOLD8)]]
    rows += [[Paragraph(ln if ln.strip() else ' ', COMMENT_VAL)] for ln in lines]

    row_heights = [header_h] + [line_h] * (len(rows) - 1)

    tbl = Table(rows, colWidths=[AVAIL_W], rowHeights=row_heights)
    style = [
        ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
        ('LINEBELOW',     (0, 0), (0, 0),   0.6, BORDER),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        # Keep glyphs clear of horizontal rules / outer box
        ('TOPPADDING',    (0, 0), (-1, -1), 1.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.8),
        ('TOPPADDING',    (0, 0), (-1, 0), 2),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
    ]
    for i in range(1, len(rows)):
        if i >= 2:
            style.append(('LINEABOVE', (0, i), (-1, i), 0.3, RULE))
    tbl.setStyle(TableStyle(style))
    return tbl


def _build_parts_row(sr_data: dict, materials: list) -> Table:
    """Side-by-side Parts Used | Parts Required — fewer blank rows, padding kept for text."""
    materials = list(materials or [])
    parts_req = list(sr_data.get('parts_required', []) or [])

    # Match both tables; keep a couple of blank rows, not a tall empty block
    content_n = max(len(materials), len(parts_req), 1)
    min_rows = min(max(content_n + 1, 4), 6)

    def _qty_str(q):
        try:
            return str(int(q)) if float(q) == int(float(q)) else str(q)
        except (TypeError, ValueError):
            return str(q) if q not in (None, '') else ''

    PART_VAL = _s('SR_PartVal', fontSize=7.5, fontName='Helvetica', leading=9.5)
    PART_SPEC = _s('SR_PartSpec', fontSize=6.5, leading=8.5, textColor=colors.HexColor('#444444'))

    def _parts_table(title, header_rows, col_fracs):
        head = [[
            Paragraph(title, BOLD8),
            Paragraph('Specification', BOLD8),
            Paragraph('Qty', BOLD8),
        ]]
        rows = head + header_rows
        while len(rows) < min_rows + 1:
            rows.append(['', '', ''])
        if len(rows) > min_rows + 1:
            rows = rows[:min_rows + 1]
        t = Table(
            rows,
            colWidths=col_fracs,
            rowHeights=[5.0 * mm] + [6.2 * mm] * (len(rows) - 1),
        )
        t.setStyle(TableStyle([
            ('BOX',          (0, 0), (-1, -1), 0.6, BORDER),
            ('INNERGRID',    (0, 0), (-1, -1), 0.3, RULE),
            ('BACKGROUND',   (0, 0), (-1, 0), LIGHT_GRAY),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',        (2, 0), (2, -1), 'CENTER'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING',   (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
        ]))
        return t

    half = AVAIL_W * 0.5
    pu_cols = [half * 0.46, half * 0.38, half * 0.16]
    pr_cols = [half * 0.46, half * 0.38, half * 0.16]

    pu_rows = [[
        Paragraph(m.material_name or '', PART_VAL),
        Paragraph(m.notes or '', PART_SPEC),
        Paragraph(_qty_str(getattr(m, 'quantity', '')), PART_VAL),
    ] for m in materials[:min_rows]]

    pr_rows = [[
        Paragraph(r.get('part', '') or '', PART_VAL),
        Paragraph(r.get('specification', '') or '', PART_SPEC),
        Paragraph(_qty_str(r.get('qty', '')), PART_VAL),
    ] for r in parts_req[:min_rows]]

    pu_tbl = _parts_table('Parts Used', pu_rows, pu_cols)
    pr_tbl = _parts_table('Parts Required', pr_rows, pr_cols)

    # Flush side-by-side — no white gap between the two parts boxes
    outer = Table([[pu_tbl, pr_tbl]], colWidths=[half, half])
    outer.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return outer


def _build_customer_remarks(sr_data: dict) -> Table:
    """Boxed Customer Remarks: header row + 2 ruled lines."""
    remarks = sr_data.get('customer_remarks', '') or ''
    lines = (remarks.split('\n') + ['', ''])[:2]
    REMARK_VAL = _s('SR_RemarkVal', fontSize=7, fontName='Helvetica', leading=9)

    rows = [[Paragraph('Customer Remarks:', BOLD8)]]
    rows += [[Paragraph(ln if ln.strip() else ' ', REMARK_VAL)] for ln in lines]

    tbl = Table(rows, colWidths=[AVAIL_W], rowHeights=[5.4 * mm, 5.8 * mm, 5.8 * mm])
    style = [
        ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
        ('LINEBELOW',     (0, 0), (0, 0),   0.6, BORDER),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]
    for i in range(2, len(rows)):
        style.append(('LINEABOVE', (0, i), (-1, i), 0.3, RULE))
    tbl.setStyle(TableStyle(style))
    return tbl


def _build_signatures(ctx, sr_data: dict) -> Table:
    """Two-column footer: Customer | Engineer — single box, no gap between columns."""
    cust_name = getattr(ctx, 'client_signed_by', None) or sr_data.get('client_name') or ''
    cust_mob  = sr_data.get('client_mobile') or getattr(ctx, 'client_mobile', None) or ''
    cust_sig  = _load_sig_image(getattr(ctx, 'client_signature', None), width=42 * mm, height=13 * mm)

    tech_obj = getattr(ctx, 'technician', None) or getattr(ctx, 'assigned_to', None)
    tech_name = (sr_data.get('technician_name')
                 or (tech_obj.full_name if tech_obj else None)
                 or getattr(ctx, 'close_signed_by', None) or '')
    tech_id   = sr_data.get('technician_id_no') or getattr(ctx, 'technician_id_no', None) or ''
    tech_sig  = _load_sig_image(getattr(ctx, 'close_signature', None), width=42 * mm, height=13 * mm)

    half = AVAIL_W * 0.5
    rows = [
        [
            Paragraph(f'<b>Customer Name :</b>  {cust_name}', VALUE),
            Paragraph(f'<b>Engineer/Technician Name:</b>  {tech_name}', VALUE),
        ],
        [
            cust_sig if cust_sig else Paragraph(' ', VALUE),
            tech_sig if tech_sig else Paragraph(' ', VALUE),
        ],
        [
            Paragraph(f'<b>Mobile No:</b>  {cust_mob}', VALUE),
            Paragraph(f'<b>ID No:</b>  {tech_id}', VALUE),
        ],
    ]
    tbl = Table(rows, colWidths=[half, half], rowHeights=[7 * mm, 14 * mm, 7 * mm])
    tbl.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.6, BORDER),
        ('LINEBEFORE',    (1, 0), (1, -1), 0.6, BORDER),  # shared center divider
        ('LINEBELOW',     (0, 0), (-1, 0), 0.3, RULE),
        ('LINEBELOW',     (0, 1), (-1, 1), 0.3, RULE),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return tbl
