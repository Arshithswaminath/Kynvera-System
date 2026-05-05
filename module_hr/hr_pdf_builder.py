"""
Professional PDF builder for HR forms — Injaaz application theme.
Native ReportLab generation, no DOCX conversion.
"""
import os
import base64
import io
import tempfile
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
    KeepTogether, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

# ── Modern minimal: black & white only ─────────────────────────────────────
C_BLACK = colors.black
C_GRAY = colors.HexColor("#666666")
C_MUTED = colors.HexColor("#6b7280")
C_LIGHT = colors.HexColor("#cccccc")
C_WHITE = colors.white

_W, _H = A4
_LM = 1.2 * cm
_RM = 1.2 * cm
CONTENT_W = _W - _LM - _RM

LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "logo.png",
)


def _fmt(v):
    if not v:
        return "-"
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        s = str(v)
        return s if s not in ("", "-") else "-"


def _fd(fd, key, default="-"):
    v = (fd or {}).get(key)
    if v in (None, "", "-"):
        return default
    return str(v)


def _section_avg(fd, sn, suffixes):
    """Compute section average from sub-ratings when rating_{sn} not provided."""
    v = (fd or {}).get(f"rating_{sn}")
    if v not in (None, "", "-"):
        return str(v)
    vals = []
    for s in suffixes:
        x = (fd or {}).get(f"rating_{sn}{s}")
        if x not in (None, "", "-"):
            try:
                vals.append(float(str(x).strip()))
            except (ValueError, TypeError):
                pass
    if vals:
        return f"{sum(vals) / len(vals):.1f}"
    return "-"


def _sig_to_image(data_url, w_mm=36, h_mm=12):
    """Load signature image and make white background transparent."""
    if not data_url or not isinstance(data_url, str) or not data_url.startswith("data:image"):
        return None
    try:
        _, b64 = data_url.split(",", 1)
        raw = io.BytesIO(base64.b64decode(b64))
        try:
            from PIL import Image as PILImage
            pil = PILImage.open(raw).convert("RGBA")
            data = pil.load()
            w, h = pil.size
            for y in range(h):
                for x in range(w):
                    r, g, b, a = data[x, y]
                    if r >= 250 and g >= 250 and b >= 250:
                        data[x, y] = (r, g, b, 0)
            out = io.BytesIO()
            pil.save(out, "PNG")
            out.seek(0)
            raw = out
        except Exception:
            raw.seek(0)
        return Image(raw, width=w_mm * mm, height=h_mm * mm)
    except Exception:
        return None


# ── Canvas: top accent bar + footer ──────────────────────────────────────────
class HRPDFCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self._saved = []
        self._form_title = kwargs.pop("form_title", "HR Form")
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for s in self._saved:
            self.__dict__.update(s)
            self._draw_decorations(n)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_decorations(self, total):
        w, h = _W, _H
        self.setStrokeColor(C_BLACK)
        self.setLineWidth(0.3)
        self.line(0, h - 0.08 * cm, w, h - 0.08 * cm)
        self.setStrokeColor(C_LIGHT)
        self.setLineWidth(0.3)
        self.line(_LM, 1.3 * cm, w - _RM, 1.3 * cm)
        self.setFont("Helvetica", 5)
        self.setFillColor(C_GRAY)
        self.drawString(_LM, 0.85 * cm, "INJAAZ")
        self.drawRightString(w - _RM, 0.85 * cm, f"Page {self._pageNumber} of {total}")


# ── Paragraph styles ─────────────────────────────────────────────────────────
def _get_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "HRTitle", parent=base["Normal"],
            fontSize=14, textColor=C_BLACK, fontName="Helvetica-Bold",
            alignment=TA_LEFT, spaceAfter=0, spaceBefore=0,
        ),
        "section": ParagraphStyle(
            "HRSec", parent=base["Normal"],
            fontSize=9, textColor=C_BLACK, fontName="Helvetica-Bold",
            alignment=TA_LEFT, spaceAfter=2, spaceBefore=10, leftIndent=0,
        ),
        "body": ParagraphStyle(
            "HRBody", parent=base["Normal"],
            fontSize=9, textColor=C_BLACK, fontName="Helvetica",
            alignment=TA_LEFT, spaceAfter=1, spaceBefore=0, leading=13,
        ),
        "label": ParagraphStyle(
            "HRLbl", parent=base["Normal"],
            fontSize=8, textColor=C_BLACK, fontName="Helvetica-Bold",
            alignment=TA_LEFT, spaceAfter=0, spaceBefore=0,
        ),
        "small": ParagraphStyle(
            "HRSm", parent=base["Normal"],
            fontSize=7, textColor=C_BLACK, fontName="Helvetica",
            alignment=TA_LEFT, spaceAfter=0, spaceBefore=0,
        ),
    }


# ── Reusable layout components ───────────────────────────────────────────────

def _header_table(form_name, styles, show_bottom_line=True):
    """Logo right, headline: INJAAZ FACILITY MANAGEMENT (small) + form name (bold). Matches reference design."""
    logo_cell = ""
    if os.path.exists(LOGO_PATH):
        try:
            # Logo: proportional scaling, proper size for PDF header
            logo_cell = Image(LOGO_PATH, width=0.7 * inch, height=0.7 * inch, kind="proportional")
        except Exception:
            pass
    if not logo_cell:
        logo_cell = Paragraph(
            "<b>INJAAZ</b>",
            ParagraphStyle("HL", fontSize=10, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_RIGHT),
        )
    # Injaaz Facility Management - a little bigger, bold (stays gray)
    sub = Paragraph(
        '<font size="8" color="#666666"><b>Injaaz Facility Management</b></font>',
        ParagraphStyle("HSub", fontSize=8, textColor=C_GRAY, fontName="Helvetica-Bold", alignment=TA_LEFT, spaceAfter=3),
    )
    # Form name - headline, compact
    ttl = Paragraph(
        f'<font size="14" color="#000000"><b>{form_name.title()}</b></font>',
        ParagraphStyle("HT", fontSize=14, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_LEFT, spaceAfter=0),
    )
    title_block = Table([[sub], [ttl]], colWidths=[CONTENT_W * 0.68])
    title_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    t = Table([[title_block, logo_cell]], colWidths=[CONTENT_W * 0.68, CONTENT_W * 0.32])
    header_style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 12),
        ("LEFTPADDING", (1, 0), (1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]
    if show_bottom_line:
        header_style.append(("LINEBELOW", (0, 0), (-1, -1), 0.5, C_BLACK))
    t.setStyle(TableStyle(header_style))
    return t


def _instruction_line(text, styles=None):
    p = Paragraph(
        f'<font size="6" color="#000000">{text}</font>',
        ParagraphStyle("Inst", fontSize=6, textColor=C_BLACK, fontName="Helvetica", alignment=TA_LEFT, spaceAfter=0, spaceBefore=10),
    )
    return p


def _info_box(text, styles=None):
    inner = Paragraph(
        f'<font size="7" color="#000000"><b>Note</b> {text}</font>',
        ParagraphStyle("Info", fontSize=7, textColor=C_BLACK, fontName="Helvetica", alignment=TA_LEFT, spaceAfter=0, spaceBefore=0),
    )
    t = Table([[inner]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ]))
    return t


def _section_bar(title, styles):
    """Section header without number."""
    return _section_bar_numbered(None, title, styles)


def _section_bar_numbered(num, title, styles=None, large=False):
    """Compact: number + title, thin underline. large=True for slightly bigger section headers."""
    styles = styles or _get_styles()
    fs, bp = (9, 6) if large else (8, 4)
    if num:
        txt = f"<b>{num}. {title}</b>"
        inner = Paragraph(txt, ParagraphStyle("Sec", fontSize=fs, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_LEFT))
        t = Table([[inner]], colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), bp),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, C_BLACK),
        ]))
    else:
        sec_s = ParagraphStyle("SecU", parent=styles["section"], fontSize=fs)
        t = Table(
            [[Paragraph(f"<b>{title.title()}</b>", sec_s)]],
            colWidths=[CONTENT_W],
        )
        t.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 6 if not large else 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if not large else 6),
        ]))
    return t


def _data_table(pairs, cols=2, styles=None, large=False):
    """Compact: label | value, horizontal lines only. large=True for slightly bigger text."""
    if not pairs:
        return Spacer(1, 0.03 * inch)
    lf, vf, ld = (8, 9, 12) if large else (7, 8, 10)
    cp = 5 if large else 4
    lbl_style = ParagraphStyle("DTL", fontSize=lf, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_LEFT)
    val_style = ParagraphStyle("DTV", fontSize=vf, textColor=C_BLACK, fontName="Helvetica", alignment=TA_LEFT, leading=ld)
    if cols == 4:
        rows = []
        for i in range(0, len(pairs), 2):
            r = []
            for j in range(2):
                if i + j < len(pairs):
                    lbl, val = pairs[i + j]
                    r.append(Paragraph(f"{lbl.title()}", lbl_style))
                    r.append(Paragraph(str(val)[:800] if val else "—", val_style))
                else:
                    r.extend(["", ""])
            rows.append(r)
        lw, vw = CONTENT_W * 0.22, CONTENT_W * 0.28
        cw = [lw, vw, lw, vw]
    else:
        rows = [
            [Paragraph(l.title(), lbl_style), Paragraph(str(v)[:800] if v else "—", val_style)]
            for l, v in pairs
        ]
        cw = [CONTENT_W * 0.28, CONTENT_W * 0.72]
    t = Table(rows, colWidths=cw)
    pad = 6 if large else 5
    style_cmds = [
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), cp),
        ("BOTTOMPADDING", (0, 0), (-1, -1), cp),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, C_LIGHT),
    ]
    if cols == 4:
        style_cmds.extend([
            ("LINEAFTER", (0, 0), (0, -1), 0.25, C_LIGHT),
            ("LINEAFTER", (2, 0), (2, -1), 0.25, C_LIGHT),
        ])
    else:
        style_cmds.append(("LINEAFTER", (0, 0), (0, -1), 0.25, C_LIGHT))
    t.setStyle(TableStyle(style_cmds))
    return t


def _form_fields(pairs, styles=None):
    """Form fields: label | value (same as data table)."""
    return _data_table(pairs, cols=2, styles=styles)


def _long_field(label, value, styles=None, large=False):
    lf, vf, ld = (8, 9, 12) if large else (7, 8, 10)
    pad, cp = (6, 5) if large else (5, 4)
    lbl_style = ParagraphStyle("LFL", fontSize=lf, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_LEFT)
    val_style = ParagraphStyle("LFV", fontSize=vf, textColor=C_BLACK, fontName="Helvetica", alignment=TA_LEFT, leading=ld)
    t = Table([
        [Paragraph(label.title(), lbl_style)],
        [Paragraph(str(value)[:4000] if value else "—", val_style)],
    ], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), cp - 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), cp),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, C_LIGHT),
    ]))
    return t


def _rating_table(rows_data, styles=None):
    styles = styles or _get_styles()
    hdr_s = ParagraphStyle("RTH", fontSize=8, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_LEFT)
    hdr = [Paragraph("<b>Criterion</b>", hdr_s), Paragraph("<b>Score</b>", hdr_s), Paragraph("<b>Max</b>", hdr_s)]
    data = [hdr]
    for row in rows_data:
        if len(row) == 4:
            crit, indicator, score, mx = row
            if indicator:
                first_cell = Paragraph(
                    crit[:120] + "<br/><font color='#6b7280'><i>%s</i></font>" % (indicator[:100].replace("&", "&amp;").replace("<", "&lt;")),
                    styles["body"],
                )
            else:
                first_cell = Paragraph(crit[:120], styles["body"])
        else:
            crit, score, mx = row
            first_cell = Paragraph(crit[:120], styles["body"])
        sv = str(score) if score not in (None, "", "-") else "-"
        data.append([
            first_cell,
            Paragraph(sv, styles["body"]),
            Paragraph(str(mx), styles["small"]),
        ])
    t = Table(data, colWidths=[CONTENT_W * 0.60, CONTENT_W * 0.20, CONTENT_W * 0.20])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_BLACK),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, C_LIGHT),
    ]))
    return t


def _checklist_table(items, styles=None, with_date=False):
    """Premium checklist: clean header, horizontal rules only."""
    styles = styles or _get_styles()
    hdr_s = ParagraphStyle("CTH", fontSize=8, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_LEFT)
    if with_date:
        hdr = [Paragraph("<b>Item</b>", hdr_s), Paragraph("<b>Status</b>", hdr_s), Paragraph("<b>Date</b>", hdr_s)]
        cw = [CONTENT_W * 0.60, CONTENT_W * 0.20, CONTENT_W * 0.20]
    else:
        hdr = [Paragraph("<b>Item</b>", hdr_s), Paragraph("<b>Status</b>", hdr_s)]
        cw = [CONTENT_W * 0.75, CONTENT_W * 0.25]
    data = [hdr]
    for row in items:
        label = row[0]
        status = row[1] if len(row) > 1 else None
        date_val = row[2] if len(row) > 2 and with_date else None
        done = str(status).lower() in ("on", "completed", "yes", "true", "1") if status else False
        if with_date and date_val is not None:
            data.append([
                Paragraph(label[:90], styles["body"]),
                Paragraph("Done" if done else "-", styles["body"]),
                Paragraph(_fmt(date_val), styles["small"]),
            ])
        elif with_date:
            data.append([
                Paragraph(label[:90], styles["body"]),
                Paragraph("Done" if done else "-", styles["body"]),
                Paragraph("-", styles["small"]),
            ])
        else:
            data.append([
                Paragraph(label[:90], styles["body"]),
                Paragraph("Done" if done else "-", styles["body"]),
            ])
    t = Table(data, colWidths=cw)
    cmds = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_BLACK),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, C_LIGHT),
    ]
    if with_date:
        cmds.append(("ALIGN", (2, 0), (2, -1), "CENTER"))
    t.setStyle(TableStyle(cmds))
    return t


def _signature_block(signatures, styles=None, large=False, center=False):
    """Compact: transparent signature only, no box or background. large=True for bigger labels/sigs. center=True for horizontal centering."""
    n = len(signatures)
    sig_w = min(52 * mm if large else 40 * mm, CONTENT_W / max(n, 1))
    cw = [sig_w] * n
    fs, sp = (10, 8) if large else (7, 4)
    lbl_row, sig_row, dt_row = [], [], []
    for label, img_data, date_val in signatures:
        lbl_row.append(Paragraph(
            f"<b>{label}</b>",
            ParagraphStyle("SL", fontSize=fs, textColor=C_BLACK, fontName="Helvetica-Bold", alignment=TA_CENTER if center else TA_LEFT),
        ))
        img = _sig_to_image(img_data, w_mm=52 if large else 36, h_mm=20 if large else 12)
        if img:
            sig_cell = img
        else:
            sig_cell = Paragraph(
                '<font color="#999999">Sign</font>',
                ParagraphStyle("SH", fontSize=fs, textColor=C_BLACK, fontName="Helvetica", alignment=TA_LEFT),
            )
        sig_row.append(sig_cell)
        dt_row.append(Paragraph(
            _fmt(date_val) if date_val else "Date",
            ParagraphStyle("SD", fontSize=fs - 2, textColor=C_BLACK, fontName="Helvetica", alignment=TA_CENTER if center else TA_LEFT),
        ))
    row_ht = [14, 44, 12] if large else [10, 28, 8]
    t = Table([lbl_row, sig_row, dt_row], colWidths=cw, rowHeights=row_ht)
    t.hAlign = "CENTER" if center else "LEFT"
    top_pad = sp + (25 if large else 0)  # Extra space above labels when large
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER" if center else "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), sp),
        ("RIGHTPADDING", (0, 0), (-1, -1), sp),
        ("TOPPADDING", (0, 0), (-1, -1), top_pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), sp),
    ]))
    return t


def _footer_block(styles=None):
    return Paragraph(
        f'<font color="#000000" size="6">Generated {datetime.now().strftime("%d/%m/%Y %H:%M")}</font>',
        ParagraphStyle("Ftr", fontSize=6, textColor=C_BLACK, alignment=TA_CENTER, fontName="Helvetica", spaceBefore=4),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Form builders
# ═══════════════════════════════════════════════════════════════════════════════

def _leave_tick(fd, key, label):
    """Return ticked or empty checkbox label matching exact Word run-text format."""
    raw_lt    = (fd.get("leave_type") or "").strip().lower()
    lt_disp   = (fd.get("leave_type_display") or "").strip().lower()
    is_sel = (raw_lt == key
              or lt_disp == label.lower()
              or lt_disp == key
              or (key == "other" and raw_lt == "other"))
    box = "[&#10003;]" if is_sel else "[ ]"
    if key == "other" and is_sel:
        other = fd.get("leave_type_other", "")
        lbl = f"Other (Specify): {other}" if other else "Other (Specify)"
    else:
        lbl = label
    return f"{box}  {lbl}"


def _build_leave(story, fd, styles):
    """
    PDF Leave Application Form — structure mirrors the MAIN Word document row-for-row.

    Word table structure (29 rows, 2 effective columns ~48% / ~48%):
      r0  : Name:                              (full-width)
      r1  : Job Title:          | Today's Date:
      r2  : Employee ID:        | Department:
      r3  : Date of Joining:    | Mobile No.:
      r4  : Last Leave Date:                   (full-width)
      r5  : DETAILS OF LEAVE                   (full-width, bold header)
      r6  : Type of Leave (header) | No. of Days
      r7–r15: 9 leave option checkbox rows
      r16 : Total No. of Days Requested:       (full-width)
      r17 : First Day of leave: | Last Day of Leave:
      r18 : Date returning to work:            (full-width)
      r19 : Leave Salary Advance Requested: [ ] YES  [ ] NO
      r20 : Telephone Number where you can be reached:
      r21 : Replacement Name:  | Signature:
      r22 : Employee Signature: | Manager Signature:
      r23 : Checked by HR: YES / NO            (full-width)
      r24 : HR Comments:                       (full-width)
      r25 : For Human Resources Only           (full-width, centred bold)
      r26 : Balance C/F:       | Contract Year:
      r27 : Paid:              | Unpaid:
      r28 : HR Signature:      | Date:
    """
    # ── styles ────────────────────────────────────────────────────────────────
    LBL = ParagraphStyle("LvLbl", fontSize=9,  fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_LEFT, leading=12)
    VAL = ParagraphStyle("LvVal", fontSize=9,  fontName="Helvetica",
                         textColor=C_BLACK, alignment=TA_LEFT, leading=12)
    HDR = ParagraphStyle("LvHdr", fontSize=10, fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_CENTER, leading=14)
    SEC = ParagraphStyle("LvSec", fontSize=9,  fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_CENTER, leading=13)
    OPT = ParagraphStyle("LvOpt", fontSize=9,  fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_LEFT, leading=13)
    OPT_DAYS = ParagraphStyle("LvOptDays", fontSize=9, fontName="Helvetica-Bold",
                              textColor=C_BLACK, alignment=TA_CENTER, leading=13)
    SIG_LBL = ParagraphStyle("LvSig", fontSize=8, fontName="Helvetica-Bold",
                              textColor=C_BLACK, alignment=TA_LEFT, leading=11)

    # ── column widths (mirror Word: col0≈49%, col1≈3%, col2≈0%, col3≈48%) ──
    # Simplified to 2 effective cols for PDF
    CW = CONTENT_W
    L  = CW * 0.50   # left col
    R  = CW * 0.50   # right col

    def _lv(label, value):
        """Label: value cell content as Paragraph."""
        v = str(value) if value not in (None, "", "-") else "—"
        return Paragraph(f"<b>{label}</b>  {v}", VAL)

    def _lv2(label, value):
        """Separate label paragraph + value for two-row-style display."""
        v = str(value) if value not in (None, "", "-") else "—"
        return Paragraph(f"<b>{label}:</b>  {v}", VAL)

    # Salary advance ticks
    sa = (fd.get("salary_advance") or "").strip().lower()
    sa_yes = "[&#10003;] YES" if sa == "yes" else "[ ] YES"
    sa_no  = "[&#10003;] NO"  if sa == "no"  else "[ ] NO"

    # HR checked ticks
    hr_chk = (fd.get("hr_checked") or "").strip().lower()
    chk_yes = "[&#10003;] YES" if hr_chk in ("yes", "checked", "verified") else "[ ] YES"
    chk_no  = "[&#10003;] NO"  if hr_chk in ("no",)                        else "[ ] NO"

    # Signature helpers
    def _sig_cell(label, img_data, date_val):
        """
        Compact signature cell: label and signature on one line.
        Signature keeps its aspect ratio and has a small gap from the label.
        """
        # Slightly bigger image while preserving a clear, compact inline layout
        img = _sig_to_image(img_data, w_mm=36, h_mm=13)

        lbl = Paragraph(f"<b>{label}:</b>", SIG_LBL)

        if img:
            # Inner 1×2 table: [Label | Signature]
            inner = Table(
                [[lbl, img]],
                colWidths=[38 * mm, 34 * mm],
                rowHeights=[10],
            )
            inner.setStyle(TableStyle([
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN",         (0, 0), (0, 0),   "LEFT"),
                ("ALIGN",         (1, 0), (1, 0),   "RIGHT"),
                # Small horizontal gap between label and signature
                ("LEFTPADDING",   (0, 0), (0, 0),   0),
                ("RIGHTPADDING",  (0, 0), (0, 0),   3),
                ("LEFTPADDING",   (1, 0), (1, 0),   3),
                ("RIGHTPADDING",  (1, 0), (1, 0),   0),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            return inner

        # Fallback without image: just label
        return lbl

    # ── build rows ────────────────────────────────────────────────────────────
    LEAVE_OPTIONS = [
        ("annual",          "Annual Leave"),
        ("ot_compensatory", "OT Compensatory Off"),
        ("examination",     "Examination Leave (UAE Nationals)"),
        ("study",           "Study Leave"),
        ("sick",            "Sick Leave"),
        ("compassionate",   "Compassionate Leave"),
        ("unpaid",          "Unpaid Leave"),
        ("hajj",            "Hajj Leave"),
        ("other",           "Other (Specify)"),
    ]

    rows = [
        # r0 : Name (full-width span)
        [Paragraph(f"<b>Name:</b>  {_fd(fd,'employee_name')}", VAL), ""],
        # r1 : Job Title | Today's Date
        [_lv2("Job Title",    _fd(fd, "job_title")),
         _lv2("Today's Date", _fmt(fd.get("today_date")))],
        # r2 : Employee ID | Department
        [_lv2("Employee ID",  _fd(fd, "employee_id")),
         _lv2("Department",   _fd(fd, "department"))],
        # r3 : Date of Joining | Mobile No.
        [_lv2("Date of Joining", _fmt(fd.get("date_of_joining"))),
         _lv2("Mobile No.",      _fd(fd, "mobile_no"))],
        # r4 : Last Leave Date (full-width)
        [Paragraph(f"<b>Last Leave Date:</b>  {_fmt(fd.get('last_leave_date'))}", VAL), ""],
        # r5 : DETAILS OF LEAVE (bold centred header, full-width)
        [Paragraph("<b>DETAILS OF LEAVE</b>", SEC), ""],
        # r6 : Type of Leave header | Number of Days header
        [Paragraph("<b>Type of Leave</b><br/>"
                   '<font size="7">(Check&#10003;  the appropriate box whichever is applicable)</font>',
                   HDR),
         Paragraph("<b>Number of Days</b>", HDR)],
    ]
    # r7–r15 : 9 checkbox leave options (right col shows days for the ticked row)
    total_days = _fd(fd, "total_days_requested")
    raw_lt  = (fd.get("leave_type") or "").strip().lower()
    lt_disp = (fd.get("leave_type_display") or "").strip().lower()
    for key, label in LEAVE_OPTIONS:
        is_sel = (raw_lt == key
                  or lt_disp == label.lower()
                  or lt_disp == key
                  or (key == "other" and raw_lt == "other"))
        days_cell = Paragraph(
            str(total_days) if (is_sel and total_days not in (None, "", "—", "-")) else "",
            OPT_DAYS,
        )
        rows.append([Paragraph(_leave_tick(fd, key, label), OPT), days_cell])
    rows += [
        # r16 : Total days (full-width)
        [Paragraph(f"<b>Total No. of Days Requested:</b>  {_fd(fd,'total_days_requested')}", VAL), ""],
        # r17 : First day | Last day
        [_lv2("First Day of Leave",  _fmt(fd.get("first_day_of_leave"))),
         _lv2("Last Day of Leave",   _fmt(fd.get("last_day_of_leave")))],
        # r18 : Date returning (full-width)
        [Paragraph(f"<b>Date returning to work:</b>  {_fmt(fd.get('date_returning_to_work'))}", VAL), ""],
        # r19 : Salary advance (full-width)
        [Paragraph(f"<b>Leave Salary Advance Requested:</b>  {sa_yes}   {sa_no}", VAL), ""],
        # r20 : Telephone (full-width)
        [Paragraph(f"<b>Telephone Number where you can be reached:</b>  {_fd(fd,'telephone_reachable')}", VAL), ""],
        # r21 : Replacement Name | Replacement Signature
        [_lv2("Replacement Name", _fd(fd, "replacement_name")),
         _sig_cell("Signature", fd.get("replacement_signature"), None)],
        # r22 : Employee Signature | Manager Signature
        [_sig_cell("Employee Signature", fd.get("employee_signature"), fd.get("today_date")),
         _sig_cell("Manager Signature",  fd.get("gm_signature"), None)],
        # r23 : Checked by HR YES/NO (full-width)
        [Paragraph(f"<b>Checked by HR:</b>  {chk_yes}   {chk_no}", VAL), ""],
        # r24 : HR Comments (full-width)
        [Paragraph(f"<b>HR Comments:</b>  {_fd(fd,'hr_comments')}", VAL), ""],
        # r25 : For Human Resources Only (centred bold, full-width)
        [Paragraph("<b>For Human Resources Only</b>", SEC), ""],
        # r26 : Balance C/F | Contract Year
        [_lv2("Balance C/F",   _fd(fd, "hr_balance_cf")),
         _lv2("Contract Year", _fd(fd, "hr_contract_year"))],
        # r27 : Paid | Unpaid
        [_lv2("Paid",   _fd(fd, "hr_paid")),
         _lv2("Unpaid", _fd(fd, "hr_unpaid"))],
        # r28 : HR Signature | Date
        [_sig_cell("HR Signature", fd.get("hr_signature"), fd.get("hr_date")),
         _lv2("Date", _fd(fd, "hr_date"))],
    ]

    # ── assemble table ────────────────────────────────────────────────────────
    # Row index reference (0-based, 29 total matching MAIN Word doc):
    #  0=Name  1=JobTitle/Date  2=EmpID/Dept  3=DOJ/Mobile  4=LastLeave
    #  5=DETAILS header  6=Leave type hdr
    #  7-15=9 leave options  16=TotalDays  17=FirstDay/LastDay  18=DateReturn
    #  19=SalaryAdvance  20=Telephone  21=ReplacementName/Sig  22=EmpSig/MgrSig
    #  23=CheckedByHR  24=HRComments  25=For HR Only  26=Balance/Contract
    #  27=Paid/Unpaid  28=HRSig/Date
    # Slightly increase row heights so form fills page better.
    row_heights = [None] * len(rows)
    for ri in range(7, 16):   # leave option rows
        row_heights[ri] = 22
    for ri in [21, 22, 28]:   # signature rows
        row_heights[ri] = 32

    t = Table(rows, colWidths=[L, R], rowHeights=row_heights)

    style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        # outer box
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        # horizontal lines between every row
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        # vertical divider between the two columns
        ("LINEAFTER",     (0, 0), (0, -1),  0.3, C_LIGHT),
        # DETAILS OF LEAVE header — stronger border above
        ("LINEABOVE",     (0, 5), (-1, 5),  0.5, C_BLACK),
        # Type of Leave header row (6) — bold border below
        ("LINEBELOW",     (0, 6), (-1, 6),  0.5, C_BLACK),
        # For Human Resources Only section divider (row 25)
        ("LINEABOVE",     (0, 25), (-1, 25), 0.5, C_BLACK),
        # Centre-align the section-header rows
        ("ALIGN",         (0, 5),  (-1, 5),  "CENTER"),
        ("ALIGN",         (0, 6),  (-1, 6),  "CENTER"),
        ("ALIGN",         (0, 25), (-1, 25), "CENTER"),
    ]

    # Full-width spans: rows that occupy both columns
    for ri in [0, 4, 5, 16, 18, 19, 20, 23, 24, 25]:
        style.append(("SPAN", (0, ri), (1, ri)))

    # Leave checkbox rows (7-15): NOT spanned — show divider + days in right col
    # Centre-align the right "Number of Days" column for header + option rows
    for ri in range(6, 16):
        style.append(("ALIGN",  (1, ri), (1, ri), "CENTER"))
        style.append(("VALIGN", (1, ri), (1, ri), "MIDDLE"))

    # Signature rows: compact, but with enough breathing room for readability
    for ri in [21, 22, 28]:
        style.append(("TOPPADDING",    (0, ri), (-1, ri), 6))
        style.append(("BOTTOMPADDING", (0, ri), (-1, ri), 6))

    t.setStyle(TableStyle(style))

    story.append(_header_table("Leave Application Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─── shared per-form helpers ────────────────────────────────────────────────
_C_SEC_BG = colors.HexColor("#f0f0f0")


def _fstyles():
    """Return (LBL, VAL, SEC, SML, ITL) paragraph styles for form tables."""
    LBL = ParagraphStyle("fLBL", fontSize=9,   fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=12)
    VAL = ParagraphStyle("fVAL", fontSize=9,   fontName="Helvetica",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=12)
    SEC = ParagraphStyle("fSEC", fontSize=9,   fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_CENTER, leading=13)
    SML = ParagraphStyle("fSML", fontSize=7.5, fontName="Helvetica",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=10)
    ITL = ParagraphStyle("fITL", fontSize=8.5, fontName="Helvetica-Oblique",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=11)
    return LBL, VAL, SEC, SML, ITL


def _flv(label, val):
    """'Label: value' paragraph."""
    _, VAL, _, _, _ = _fstyles()
    v = str(val) if val not in (None, "", "-") else ""
    return Paragraph(f"<b>{label}:</b>  {v}", VAL)


def _fsec(text, left=False):
    """Section-header paragraph (centred by default)."""
    align = TA_LEFT if left else TA_CENTER
    s = ParagraphStyle("_fsecX", fontSize=9, fontName="Helvetica-Bold",
                       textColor=C_BLACK, alignment=align, leading=13)
    return Paragraph(f"<b>{text}</b>", s)


def _fchk(val, label, compare=None):
    """[ ] / [✓] checkbox paragraph."""
    _, VAL, _, _, _ = _fstyles()
    if compare is not None:
        checked = str(val or "").strip().lower() == compare.lower()
    else:
        checked = bool(val) and str(val).strip().lower() not in ("", "no", "false", "0")
    box = "[&#10003;]" if checked else "[ ]"
    return Paragraph(f"{box}  {label}", VAL)


def _fsig(label, img_data):
    """Compact inline signature cell (label left, image right)."""
    LBL, _, _, _, _ = _fstyles()
    img = _sig_to_image(img_data, w_mm=36, h_mm=13)
    lbl = Paragraph(f"<b>{label}:</b>", LBL)
    if img:
        inner = Table([[lbl, img]], colWidths=[40 * mm, 34 * mm], rowHeights=[10])
        inner.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return inner
    return lbl


def _ftable(rows, cws, spans=(), secs=(), sigs=(), extra=()):
    """
    Build a consistently styled single form table.
    spans  – row indices to span full width
    secs   – row indices that are section headers (shaded, bold border below)
    sigs   – row indices that need extra padding (signature rows)
    extra  – additional TableStyle commands
    """
    t = Table(rows, colWidths=cws)
    ncols = len(cws)
    style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.3, C_LIGHT),
    ]
    for ri in spans:
        style.append(("SPAN", (0, ri), (-1, ri)))
    for ri in secs:
        style.append(("BACKGROUND", (0, ri), (-1, ri), _C_SEC_BG))
        style.append(("LINEBELOW",  (0, ri), (-1, ri), 0.5, C_BLACK))
        style.append(("ALIGN",      (0, ri), (-1, ri), "CENTER"))
    for ri in sigs:
        style.append(("TOPPADDING",    (0, ri), (-1, ri), 8))
        style.append(("BOTTOMPADDING", (0, ri), (-1, ri), 8))
    style.extend(extra)
    t.setStyle(TableStyle(style))
    return t


# ─────────────────────────────────────────────────────────────────────────────
#  COMMENCEMENT FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_commencement(story, fd, styles):
    """Commencement Form — mirrors HR Documents - Main reference."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, ITL = _fstyles()

    inst = Paragraph(
        "To complete the administrative aspect of your Employment please complete this form within "
        "5 days of joining and fax it back to AH or email it to joana@ajmanholding.ae",
        ITL,
    )

    rows = [
        [inst, ""],                                                          # r0 instruction
        [_fsec("Personal Details:"), ""],                                    # r1
        [_flv("Name",         _fd(fd, "employee_name")), ""],                # r2
        [_flv("Position",     _fd(fd, "position")),
         _flv("Contacts",     _fd(fd, "contacts"))],                         # r3
        [_flv("Department",   _fd(fd, "department")),
         _flv("Organization", _fd(fd, "organization", "INJAAZ LLC"))],       # r4
        [_flv("Date of Joining", _fmt(fd.get("date_of_joining"))), ""],      # r5
        [_fsec("Bank Account Details:"), ""],                                # r6
        [_flv("Bank Name", _fd(fd, "bank_name")), ""],                       # r7
        [_flv("Branch",    _fd(fd, "bank_branch")),
         _flv("Account Number", _fd(fd, "account_number"))],                 # r8
        [_fsig("Employee's Signature", fd.get("employee_signature")),
         _flv("Date", _fmt(fd.get("employee_sign_date")))],                  # r9 sig
        [_fsec("Reporting To:"), ""],                                        # r10
        [_flv("Name", _fd(fd, "reporting_to_name")), ""],                    # r11
        [_flv("Designation / Title", _fd(fd, "reporting_to_designation")),
         _flv("Contact No",          _fd(fd, "reporting_to_contact"))],      # r12
        [_fsig("Signature", fd.get("reporting_to_signature")),
         _flv("Date", _fmt(fd.get("reporting_sign_date")))],                 # r13 sig
    ]

    t = _ftable(rows, [L, R],
                spans=(0, 1, 2, 5, 6, 7, 10, 11),
                secs=(1, 6, 10),
                sigs=(9, 13))

    story.append(_header_table("Commencement Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)
    story.append(Spacer(1, 6))

    note = Paragraph(
        "If you need assistance with Salary letter required to open new bank account, please "
        "forward an email to HR Department at joana@ajmanholding.ae",
        ParagraphStyle("cNote", fontSize=8, fontName="Helvetica-Oblique",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11),
    )
    nt = Table([[note]], colWidths=[CW])
    nt.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(nt)


# ─────────────────────────────────────────────────────────────────────────────
#  DUTY RESUMPTION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_duty_resumption(story, fd, styles):
    """Resumption of Duty Form — mirrors Word document."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, _ = _fstyles()

    rows = [
        [_fsec("Requester:"), ""],                                           # r0
        [_flv("Employee Name", _fd(fd, "employee_name")),
         _flv("Employee ID",   _fd(fd, "employee_id"))],                     # r1
        [_flv("Job Title",     _fd(fd, "job_title")),
         _flv("Company",       _fd(fd, "company", "INJAAZ LLC"))],           # r2
        [_fsec("Leave Information:"), ""],                                   # r3
        [_flv("Leave Started",  _fmt(fd.get("leave_started"))),
         _flv("Leave Ended",    _fmt(fd.get("leave_ended")))],               # r4
        [_flv("Planned Resumption Date",
              _fmt(fd.get("planned_resumption_date"))), ""],                 # r5
        [_flv("Actual Resumption Date",
              _fmt(fd.get("actual_resumption_date"))), ""],                  # r6
        [_flv("Note",          _fd(fd, "note")), ""],                        # r7
        [_fsig("Employee Signature", fd.get("employee_signature")),
         _flv("Date", _fmt(fd.get("sign_date")))],                           # r8 sig
        [_flv("Line Manager Remarks", _fd(fd, "line_manager_remarks")), ""],   # r9
        [_fsig("Approved by Line Manager", fd.get("gm_signature")),
         _flv("Date", "")],                                                  # r11 sig
        [_fsig("HR Signature", fd.get("hr_signature")),
         _flv("Date", "")],                                                  # r12 sig
    ]

    t = _ftable(rows, [L, R],
                spans=(0, 3, 5, 6, 7, 9),
                secs=(0, 3),
                sigs=(8, 10, 11),
                extra=[("MINROWHEIGHT", (0, 9), (-1, 9), 28)])

    story.append(_header_table("Resumption of Duty Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  PASSPORT RELEASE / SUBMISSION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_passport_release(story, fd, styles):
    """Passport Release/Submission Form — two sections matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, ITL = _fstyles()

    ft = _fd(fd, "passport_form_type", "Release").replace("_", " ").title()
    purpose = _fd(fd, "purpose_of_release")

    # ── Section 1: Release ──────────────────────────────────────────────
    rows1 = [
        [_fsec(f"Passport {ft} Form"), ""],                                  # r0 title
        [_flv("Employee Name", _fd(fd, "employee_name")),
         _flv("Employee ID",   _fd(fd, "employee_id"))],                     # r1
        [_flv("Job Title",     _fd(fd, "job_title")),
         _flv("Project",       _fd(fd, "project"))],                         # r2
        [_flv("Date", _fmt(fd.get("form_date"))), ""],                       # r3
        [_fsec("Purpose of Release:"), ""],                                  # r4
        [Paragraph(purpose, VAL), ""],                                       # r5
        [_flv("Release Date", _fmt(fd.get("release_date"))), ""],            # r6
        [_fsig("Employee Signature", fd.get("employee_signature")), ""],     # r7 sig
        [_fsec("Note"), ""],                                                 # r8
        [Paragraph(
            "If an employee submits their passport to management for safekeeping, "
            "they should provide a dated signature of consent during duty resumption "
            "in the submission part of the same form of requisition.<br/>"
            "Management will not accept any passport for safekeeping without a signed "
            "consent from the employee.<br/>"
            "All passports will be released two days before the requested date, and "
            "immediately in emergency cases.",
            ITL), ""],                                                       # r9
        [_fsig("Approved by Line Manager", fd.get("gm_signature")),
         _flv("Date", "")],                                                  # r10 sig
        [_fsig("HR Signature", fd.get("hr_signature")),
         _flv("Date", "")],                                                  # r11 sig
    ]

    t1 = _ftable(rows1, [L, R],
                 spans=(0, 3, 4, 5, 6, 7, 8, 9),
                 secs=(0, 4, 8),
                 sigs=(7, 10, 11))

    story.append(_header_table("Passport Release / Submission Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t1)

    # ── Section 2: Safekeeping Requisition ──────────────────────────────
    story.append(Spacer(1, 8))
    rows2 = [
        [_fsec("Requisition for Safekeeping"), ""],                          # r0
        [_flv("Employee Name", _fd(fd, "employee_name")),
         _flv("Employee ID",   _fd(fd, "employee_id"))],                     # r1
        [_flv("Job Title",     _fd(fd, "job_title")),
         _flv("Date",          _fmt(fd.get("form_date")))],                  # r2
        [_fsig("Approved by Line Manager", fd.get("gm_signature")),
         _flv("Date", "")],                                                  # r3 sig
        [_fsig("HR Signature", fd.get("hr_signature")),
         _flv("Date", "")],                                                  # r4 sig
    ]

    t2 = _ftable(rows2, [L, R],
                 spans=(0,),
                 secs=(0,),
                 sigs=(3, 4))
    story.append(t2)

    # DOC NO footer row
    story.append(Spacer(1, 6))
    doc_row = Table(
        [[Paragraph("<b>DOC NO:</b> HR-FRM-003", ParagraphStyle("dr", fontSize=7.5, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=10)),
          Paragraph("<b>DATE:</b> 09/05/2025",   ParagraphStyle("dr2", fontSize=7.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=10)),
          Paragraph("<b>ISSUE:</b> 01",           ParagraphStyle("dr3", fontSize=7.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=10)),
          Paragraph("<b>REVISION:</b> 02",        ParagraphStyle("dr4", fontSize=7.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_RIGHT, leading=10))]],
        colWidths=[CW * 0.30, CW * 0.25, CW * 0.20, CW * 0.25],
    )
    doc_row.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(doc_row)


# ─────────────────────────────────────────────────────────────────────────────
#  VISA RENEWAL FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_visa_renewal(story, fd, styles):
    """Visa Renewal Form — letter-format matching Word document."""
    CW = CONTENT_W
    _, VAL, _, _, ITL = _fstyles()

    name       = _fd(fd, "employee_name")
    emp_id     = _fd(fd, "employee_id")
    employer   = _fd(fd, "employer", "INJAAZ LLC")
    position   = _fd(fd, "position")
    years      = _fd(fd, "years_completed")
    form_date  = _fmt(fd.get("form_date"))
    decision   = (fd.get("decision") or "").strip().lower()

    rows = [
        [_flv("Date", form_date)],                                          # r0
        [Paragraph("", VAL)],                                               # r1 blank
        [Paragraph("<b>To: HR Department,</b>", VAL)],                      # r2
        [Paragraph("", VAL)],                                               # r3 blank
        [Paragraph(
            f"I, <b>{name}</b> with ID number <b>{emp_id}</b> employed by "
            f"<b>{employer}</b>", VAL)],                                     # r4
        [Paragraph("", VAL)],                                               # r5 blank
        [Paragraph(
            f"in the position <b>{position}</b> have completed "
            f"<b>{years}</b> years.", VAL)],                                 # r6
        [Paragraph("I would like to confirm my decision to,", VAL)],        # r7
        [Paragraph("", VAL)],                                               # r8 blank
        [_fchk(decision == "continue", "1.  Continue by employment with the company for the next 2 years and willing to have my visa renewed.")],  # r9
        [Paragraph("", VAL)],                                               # r10 blank
        [_fchk(decision == "discontinue" or decision == "cancel",
               "2.  Discontinue my service and require visa cancellation.")], # r11
        [Paragraph("", VAL)],                                               # r12 blank
        [Paragraph(
            "<i>Note: In case I do not continue my service, I will be liable "
            "to cover any additional charges covered by the company.</i>",
            ITL)],                                                           # r13
        [Paragraph("", VAL)],                                               # r14 blank
        [_fsig("Signature of Employee", fd.get("employee_signature"))],     # r15 sig
        [Paragraph("", VAL)],                                               # r16 blank
        [Paragraph("<b>INJAAZ LLC</b>", VAL)],                              # r17
    ]

    t = Table(rows, colWidths=[CW])
    t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("TOPPADDING",    (0, 15), (-1, 15), 8),
        ("BOTTOMPADDING", (0, 15), (-1, 15), 8),
    ]))

    story.append(_header_table("Visa Renewal Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLEARANCE FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_station_clearance(story, fd, styles):
    """Station Clearance Form — info header + 3-col checklist matching Word doc."""
    CW = CONTENT_W
    _, VAL, _, SML, _ = _fstyles()

    dep_map = {"transfer": "Transfer", "resignation": "Resignation",
               "termination": "Termination", "end_of_contract": "End of Contract"}
    tdep = dep_map.get(_fd(fd, "type_of_departure"), _fd(fd, "type_of_departure"))

    # ── Top info section: 4 equal columns (LabelL | ValL | LabelR | ValR) ──
    LBL  = ParagraphStyle("scLb", fontSize=9, fontName="Helvetica-Bold",
                          textColor=C_BLACK, alignment=TA_LEFT, leading=12)
    VALC = ParagraphStyle("scVl", fontSize=9, fontName="Helvetica",
                          textColor=C_BLACK, alignment=TA_LEFT, leading=12)
    IW = CW / 4
    info_rows = [
        [Paragraph("<b>Employee Name</b>", LBL),
         Paragraph(_fd(fd, "employee_name"), VALC),
         Paragraph("<b>Employee ID</b>", LBL),
         Paragraph(_fd(fd, "employee_id"), VALC)],
        [Paragraph("<b>Employment Date</b>", LBL),
         Paragraph(_fmt(fd.get("employment_date")), VALC),
         Paragraph("<b>Position</b>", LBL),
         Paragraph(_fd(fd, "position"), VALC)],
        [Paragraph("<b>Department</b>", LBL),
         Paragraph(_fd(fd, "department"), VALC),
         Paragraph("<b>Section</b>", LBL),
         Paragraph(_fd(fd, "section"), VALC)],
        [Paragraph("<b>Type of Departure</b>", LBL),
         Paragraph(tdep, VALC),
         Paragraph("<b>Last Working Date</b>", LBL),
         Paragraph(_fmt(fd.get("last_working_date")), VALC)],
    ]
    t_info = Table(info_rows, colWidths=[IW]*4)
    t_info.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (0, -1),  _C_SEC_BG),  # label cols shaded
        ("BACKGROUND",    (2, 0), (2, -1),  _C_SEC_BG),
    ]))

    # ── Checklist: 3 columns (item 58%, date 21%, sig 21%) — no empty col ──
    CI = CW * 0.58
    CD = CW * 0.21
    CS = CW * 0.21

    def chk(item, chk_val, date_val=""):
        tick = "[&#10003;]" if chk_val else "[ ]"
        return [
            Paragraph(f"{tick}  {item}", VAL),
            Paragraph(_fmt(date_val) if date_val else "", SML),
            Paragraph("", SML),
        ]

    def sec_hdr(title):
        return [
            Paragraph(f"<b>{title}</b>", ParagraphStyle(
                "scSH", fontSize=9, fontName="Helvetica-Bold",
                textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph("<b>DATE</b>", ParagraphStyle(
                "scDH", fontSize=9, fontName="Helvetica-Bold",
                textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph("<b>SIGNATURE</b>", ParagraphStyle(
                "scSIH", fontSize=9, fontName="Helvetica-Bold",
                textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        ]

    dept_hdr  = [sec_hdr("EMPLOYEE'S DEPARTMENT / SECTION")]
    dept_rows = [
        chk("Has completed / handed over all tasks on hand",  fd.get("tasks_handed_over")),
        chk("Has handed over all original working documents", fd.get("documents_handed_over")),
        chk("Has handed over all normal & Electronic files",  fd.get("files_handed_over")),
        chk("Keys Returned",      fd.get("keys_returned")),
        chk("Toolbox Returned",   fd.get("toolbox_returned")),
        chk("Access card",        fd.get("access_card_returned")),
        chk(f"Others: {_fd(fd, 'dept_others', '')}",         False),
    ]
    it_hdr  = [sec_hdr("INFORMATION TECHNOLOGY DEPARTMENT")]
    it_rows = [
        chk("E-mail Account Cancelled",                       fd.get("email_cancelled")),
        chk("Has returned all software / hardware materials", fd.get("software_hardware_returned")),
        chk("Laptop Returned",                                fd.get("laptop_returned")),
        chk("Mobile Returned",                                fd.get("mobile_returned")),
        chk(f"Others: {_fd(fd, 'it_others', '')}",           False),
    ]
    hr_hdr  = [sec_hdr("HUMAN RESOURCES & ADMINISTRATION")]
    hr_rows = [
        chk("Employee file Shifted to Exit folder",           fd.get("file_shifted")),
        chk("Payment of outstanding dues (Salary)",           fd.get("dues_paid")),
        chk("Medical Card Returned",                          fd.get("medical_card_returned")),
        chk(f"Others: {_fd(fd, 'hr_others', '')}",           False),
    ]
    fin_hdr  = [sec_hdr("FINANCE DEPARTMENT")]
    fin_rows = [
        chk("EOS Benefits Transfer",                          fd.get("eos_transfer")),
        chk(f"Others: {_fd(fd, 'finance_others', '')}",      False),
    ]

    rem_row = [[
        Paragraph(f"<b>Remarks:</b>  {_fd(fd, 'remarks')}", VAL),
        "", "",
    ]]
    sig_row = [[
        _fsig("Employee Signature", fd.get("employee_signature")),
        _fsig("Human Resources Manager", fd.get("hr_signature")),
        "",
    ]]

    # Row indices
    n_dh = 1; n_d = len(dept_rows)
    n_ih = 1; n_i = len(it_rows)
    n_hh = 1; n_hr2 = len(hr_rows)
    n_fh = 1; n_f = len(fin_rows)
    r_ih = n_dh + n_d
    r_hh = r_ih + n_ih + n_i
    r_fh = r_hh + n_hh + n_hr2
    r_rem= r_fh + n_fh + n_f
    r_sig= r_rem + 1
    sec_rows = [0, r_ih, r_hh, r_fh]

    all_rows = dept_hdr + dept_rows + it_hdr + it_rows + hr_hdr + hr_rows + fin_hdr + fin_rows + rem_row + sig_row
    t_chk = Table(all_rows, colWidths=[CI, CD, CS])

    style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.3, C_LIGHT),
        # remarks spans all 3
        ("SPAN",  (0, r_rem), (-1, r_rem)),
        ("MINROWHEIGHT", (0, r_rem), (-1, r_rem), 40),
        # sig row: employee col0, HR spans col1+col2
        ("SPAN",  (1, r_sig), (2, r_sig)),
        ("TOPPADDING",    (0, r_sig), (-1, r_sig), 8),
        ("BOTTOMPADDING", (0, r_sig), (-1, r_sig), 8),
    ]
    for ri in sec_rows:
        style.extend([
            ("BACKGROUND", (0, ri), (-1, ri), _C_SEC_BG),
            ("LINEBELOW",  (0, ri), (-1, ri), 0.5, C_BLACK),
            ("ALIGN",      (0, ri), (-1, ri), "CENTER"),
        ])

    t_chk.setStyle(TableStyle(style))

    story.append(_header_table("Station Clearance Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))

    intro = Paragraph(
        "The following departments must ensure that all exit formalities have been "
        "conducted for transferring employees.",
        ParagraphStyle("scI", fontSize=8.5, fontName="Helvetica-Oblique",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11),
    )
    story.append(intro)
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 3))
    story.append(t_chk)


# ─────────────────────────────────────────────────────────────────────────────
#  GRIEVANCE / DISCIPLINARY ACTION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_grievance(story, fd, styles):
    """Employee Grievance/Disciplinary Action Form — mirrors Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, ITL = _fstyles()

    desc  = _fd(fd, "complaint_description") or _fd(fd, "complaint")
    wits  = _fd(fd, "witnesses")
    who   = _fd(fd, "who_informed")
    att   = _fd(fd, "attachment")
    loc   = _fd(fd, "issue_location", "").replace("_", " ").title()
    s2v   = _fd(fd, "statement_2nd_party")
    hrv   = _fd(fd, "hr_statement_verified")
    hrf   = _fd(fd, "hr_first_recurring")
    hra   = _fd(fd, "hr_remarks")
    gma   = _fd(fd, "gm_remarks")

    rows = [
        # ── Purpose ────────────────────────────────────────────────────
        [Paragraph(
            "The purpose of the Grievance/Disciplinary form is to establish a method whereby "
            "grievances and disciplinary issues of employees will be resolved fairly and effectively. "
            "The filing of a grievance and disciplinary issues will in no way prejudice the status of "
            "the employee. This form remains confidential with Line Manager / Human Resource department.",
            ITL), ""],                                                        # r0
        # ── Part A: 1st Party ──────────────────────────────────────────
        [_fsec("1st Party:  Complainant Information — Part A"), ""],          # r1
        [_flv("Employee Name",    _fd(fd, "complainant_name")),
         _flv("Employee ID #",    _fd(fd, "complainant_id"))],                # r2
        [_flv("Designation",      _fd(fd, "complainant_designation")),
         _flv("Date of Incident", _fmt(fd.get("date_of_incident")))],         # r3
        [_flv("Shift / Time",     _fd(fd, "shift_time")),
         _flv("Employee Contact #", _fd(fd, "complainant_contact"))],         # r4
        [_flv("Issue happened at", loc), ""],                                 # r5
        # ── Part B: 2nd Party ──────────────────────────────────────────
        [_fsec("2nd Party — Part B"), ""],                                    # r6
        [Paragraph(
            "<i>Note: use new form if complaint is for more than 1 employee.</i>",
            ITL), ""],                                                        # r7
        [_flv("Employee Name",    _fd(fd, "second_party_name")),
         _flv("Staff ID",         _fd(fd, "second_party_id"))],               # r8
        [_flv("Department",       _fd(fd, "second_party_department")),
         _flv("Place of Incident",_fd(fd, "place_of_incident"))],             # r9
        [_flv("Shift / Time",     _fd(fd, "second_party_shift")),
         _flv("Employee Contact #",_fd(fd, "second_party_contact"))],         # r10
        # ── Part C: Complaint ──────────────────────────────────────────
        [_fsec("What is the complaint/issue? — Part C"), ""],                 # r11
        [Paragraph(desc, VAL), ""],                                           # r12
        # ── Witnesses / Attachment ─────────────────────────────────────
        [_flv("Witnesses", wits),
         _flv("Attachment", att)],                                            # r13
        [_flv("Who was informed", who), ""],                                  # r14
        # ── Acknowledgement (1st party) ────────────────────────────────
        [_fsec("Acknowledgement and Signature"), ""],                         # r15
        [Paragraph(
            "I have written and signed this grievance/disciplinary action form.",
            VAL), ""],                                                        # r16
        [_fsig("Signature of Complainant (1st Party)",
               fd.get("complainant_signature")), ""],                         # r17 sig
        # ── For HOD / Engineer use ─────────────────────────────────────
        [_fsec("For Engineer, QHSE & Head of Department (HOD) Use"), ""],     # r18
        [Paragraph(
            "The Engineer, QHSE or HOD handling the employee grievance needs to state "
            "the actions or recommendations taken to resolve the issues. Did both "
            "(disputing) parties reach a solution/agreement?", VAL), ""],     # r19
        [Paragraph(
            "<b>Statement of 2nd party been taken &amp; attached?</b>"
            "&nbsp;&nbsp;&nbsp;&nbsp;"
            f"{'[&#10003;]' if s2v == 'yes' else '[ ]'} Yes"
            "&nbsp;&nbsp;&nbsp;&nbsp;"
            f"{'[&#10003;]' if s2v == 'no' else '[ ]'} No"
            "&nbsp;&nbsp;&nbsp;&nbsp;"
            f"{'[&#10003;]' if s2v in ('na', 'n/a') else '[ ]'} Not required",
            VAL), ""],                                                        # r20
        [Paragraph(_fd(fd, "hod_actions") or "", VAL), ""],                  # r21 HOD actions
        [_fsig("Signature of Engineer / QHSE / HOD",
               fd.get("hod_signature")), ""],                                 # r22 sig
        # ── 2nd party consent ──────────────────────────────────────────
        [_fsec("Employee Acknowledgement / Consent (2nd Party)"), ""],        # r23
        [Paragraph(
            "I have read & agreed and signed on this form as per the actions taken "
            "or recommended by my engineer, QHSE or HOD.", VAL), ""],         # r24
        [_fsig("Employee Signature (2nd Party)",
               fd.get("second_party_signature")), ""],                        # r25 sig
        # ── For HR use ─────────────────────────────────────────────────
        [_fsec("For HR Use Only"), ""],                                       # r26
        [_flv("Statement verified",  hrv),
         _flv("1st / Recurring",     hrf)],                                   # r27
        [Paragraph(f"<b>HR Remarks:</b>  {hra}", VAL), ""],                  # r28
        [_fsig("HR Signature", fd.get("hr_signature")), ""],                  # r29 sig
        # ── For GM use ─────────────────────────────────────────────────
        [_fsec("For General Manager Use Only"), ""],                          # r30
        [Paragraph(f"<b>GM Remarks:</b>  {gma}", VAL), ""],                  # r31
        [_fsig("GM Signature", fd.get("gm_signature")), ""],                  # r32 sig
    ]

    t = _ftable(rows, [L, R],
                spans=(0, 1, 5, 6, 7, 11, 12, 14, 15, 16, 17,
                       18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32),
                secs=(1, 6, 11, 15, 18, 23, 26, 30),
                sigs=(17, 22, 25, 29, 32),
                extra=[("MINROWHEIGHT", (0, 12), (-1, 12), 40),
                       ("MINROWHEIGHT", (0, 21), (-1, 21), 35),
                       ("MINROWHEIGHT", (0, 28), (-1, 28), 30),
                       ("MINROWHEIGHT", (0, 31), (-1, 31), 30)])

    story.append(_header_table("Employee Grievance / Disciplinary Action Form",
                               styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  INTERVIEW ASSESSMENT FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_interview_assessment(story, fd, styles):
    """Interview Assessment Form — rating table matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, ITL = _fstyles()

    RATING_MAP = {"outstanding": "Outstanding", "v_good": "V. Good",
                  "good": "Good", "fair": "Fair", "low": "Low"}

    def tick(val, target):
        return "[&#10003;]" if RATING_MAP.get(str(val or "").strip().lower()) == target else "[ ]"

    def gender_cell():
        g = str(fd.get("gender") or "").strip().upper()
        f_box = "[&#10003;] F" if g == "F" else "[ ] F"
        m_box = "[&#10003;] M" if g == "M" else "[ ] M"
        _, VAL, _, _, _ = _fstyles()
        return Paragraph(f"<b>Gender:</b>  {f_box}    {m_box}", VAL)

    # ── Candidate info ───────────────────────────────────────────────
    info_rows = [
        [_flv("Candidate Name",       _fd(fd, "candidate_name")),
         _flv("Position Title",        _fd(fd, "position_title"))],
        [_flv("Academic Qualification",_fd(fd, "academic_qualification")),
         _flv("Age",                   _fd(fd, "age"))],
        [_flv("Marital Status",        _fd(fd, "marital_status")),
         _flv("No. of Dependents",     _fd(fd, "dependents"))],
        [_flv("Nationality",           _fd(fd, "nationality")),
         gender_cell()],
        [_flv("Current Job Title",     _fd(fd, "current_job_title")),
         _flv("Years of Experience",   _fd(fd, "years_experience"))],
        [_flv("Current Salary",        _fd(fd, "current_salary")),
         _flv("Expected Salary",       _fd(fd, "expected_salary"))],
        [_flv("Interview Date",        _fmt(fd.get("interview_date"))),
         _flv("Interview By",          _fd(fd, "interview_by"))],
    ]

    t_info = _ftable(info_rows, [L, R])
    story.append(_header_table("Interview Assessment Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Note ────────────────────────────────────────────────────────
    note = Paragraph(
        "<i>Note: The Interviewer shall indicate the rating by ticking the appropriate column.</i>",
        ITL)
    story.append(note)
    story.append(Spacer(1, 4))

    # ── Rating table ─────────────────────────────────────────────────
    FACTORS = [
        ("Turn-out & Appearance",
         "The Turn-out and appearance are appropriate to the position",
         "rating_turnout"),
        ("Confidence",
         "Demonstrates professional competence and self-confidence",
         "rating_confidence"),
        ("Mental Alertness",
         "Comprehends and coherently responds to questions",
         "rating_mental_alertness"),
        ("Maturity & Emotional Stability",
         "Demonstrates composure and balanced behaviour when under pressure "
         "or responding to difficult/critical queries.",
         "rating_maturity"),
        ("Communication Skills",
         "Good listener, Expresses own thoughts and opinions clearly and to "
         "the point? Fluent in conversational English.",
         "rating_communication"),
        ("Technical Knowledge",
         "Candidate awareness of his own duties and responsibilities as per "
         "experience gained",
         "rating_technical"),
        ("Relevant Training",
         "Has professional/technical training relevant to the job requirements",
         "rating_training"),
        ("Relevant Experience",
         "Previous work experience meets with job requirement",
         "rating_experience"),
        ("Overall Rating",
         "The candidate's overall suitability for the position",
         "rating_overall"),
    ]

    CW_F = CW * 0.22
    CW_I = CW * 0.38
    CW_R = CW * 0.08

    hdr = [[
        Paragraph("<b>FACTOR</b>", ParagraphStyle("rh", fontSize=8.5, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=11)),
        Paragraph("<b>DEMONSTRABLE INDICATORS</b>", ParagraphStyle("rh2", fontSize=8.5, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=11)),
        Paragraph("<b>Outstanding</b>", SML),
        Paragraph("<b>V. Good</b>", SML),
        Paragraph("<b>Good</b>", SML),
        Paragraph("<b>Fair</b>", SML),
        Paragraph("<b>Low</b>", SML),
    ]]

    rating_rows = []
    for factor, indicator, key in FACTORS:
        val = fd.get(key)
        rating_rows.append([
            Paragraph(factor, VAL),
            Paragraph(indicator, ParagraphStyle("rI", fontSize=8.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
            Paragraph(tick(val, "Outstanding"), SML),
            Paragraph(tick(val, "V. Good"),     SML),
            Paragraph(tick(val, "Good"),         SML),
            Paragraph(tick(val, "Fair"),         SML),
            Paragraph(tick(val, "Low"),          SML),
        ])

    all_rating = hdr + rating_rows
    t_rate = Table(all_rating, colWidths=[CW_F, CW_I, CW_R, CW_R, CW_R, CW_R, CW_R])
    t_rate.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (2, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
    ]))
    story.append(t_rate)
    story.append(Spacer(1, 6))

    # ── Comments / Eligibility ───────────────────────────────────────
    comment_rows = [
        [_fsec("Overall Assessment / Comments"), ""],
        [Paragraph(
            f"<b>Professional</b> (e.g. academic qualification, technical training and experience):<br/>"
            f"{_fd(fd, 'assessment_professional') or _fd(fd, 'overall_assessment')}", VAL), ""],
        [Paragraph(
            f"<b>Personality</b> (e.g. behaviour, attitude and presentation):<br/>"
            f"{_fd(fd, 'assessment_personality')}", VAL), ""],
        [_flv("Eligibility for Employment",
              _fd(fd, "eligibility")),
         _flv("Job Recommended for",
              _fd(fd, "job_recommended_for"))],
        [_flv("Interviewer's Name",
              _fd(fd, "interviewer_name", _fd(fd, "interview_by"))),
         _flv("Title", _fd(fd, "interviewer_title"))],
        [_fsig("Interviewer Signature",
               fd.get("interviewer_signature")),
         ""],
    ]
    t_cmt = _ftable(comment_rows, [L, R],
                    spans=(0, 1, 2, 5),
                    secs=(0,),
                    sigs=(5,),
                    extra=[("MINROWHEIGHT", (0, 1), (-1, 1), 40),
                           ("MINROWHEIGHT", (0, 2), (-1, 2), 40)])
    story.append(t_cmt)


# ─────────────────────────────────────────────────────────────────────────────
#  STAFF APPRAISAL FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_staff_appraisal(story, fd, styles):
    """Staff Appraisal Form — weighted rating table matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, _ = _fstyles()

    # ── Employee info ────────────────────────────────────────────────
    info_rows = [
        [_flv("Name",            _fd(fd, "employee_name")),
         _flv("Employee ID",     _fd(fd, "employee_id"))],
        [_flv("Department",      _fd(fd, "department")),
         _flv("Position",        _fd(fd, "position"))],
        [_flv("Appraisal Period",_fd(fd, "appraisal_period")),
         _flv("Reviewer",        _fd(fd, "reviewer"))],
    ]
    t_info = _ftable(info_rows, [L, R])
    story.append(_header_table("Staff Appraisal Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Performance criteria table ───────────────────────────────────
    CRITERIA = [
        ("Punctuality",             "15%", "rating_punctuality",
         "Regularity in attendance and adherence to schedules."),
        ("Job Knowledge and Expertise","15%","rating_job_knowledge",
         "Understanding of job responsibilities, skills, and processes."),
        ("Quality of Work",         "15%", "rating_quality",
         "Accuracy, attention to detail, and meeting quality standards."),
        ("Productivity",            "15%", "rating_productivity",
         "Efficiency, meeting deadlines, and handling workload."),
        ("Communication Skills",    "10%", "rating_communication",
         "Effectiveness in written and verbal communication."),
        ("Teamwork and Collaboration","10%","rating_teamwork",
         "Willingness to work with others and contribute to a team environment."),
        ("Problem-Solving & Initiative","10%","rating_problem_solving",
         "Root Cause Analytic, Ability to handle challenges and suggest improvements."),
        ("Adaptability",            "5%",  "rating_adaptability",
         "Flexibility in dealing with changes and new responsibilities."),
        ("Leadership (if applicable)","5%","rating_leadership",
         "Ability to lead, motivate, and manage a team effectively."),
    ]

    CW_C = CW * 0.30
    CW_W = CW * 0.12
    CW_R = CW * 0.10
    CW_M = CW * 0.48

    hdr = [[
        Paragraph("<b>Performance Criterion</b>", ParagraphStyle("sah", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Weightage (%)</b>",         ParagraphStyle("sah2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Rating (1–5)</b>",           ParagraphStyle("sah3", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Comments</b>",               ParagraphStyle("sah4", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]
    criteria_rows = []
    for criterion, wt, key, comment_desc in CRITERIA:
        criteria_rows.append([
            Paragraph(criterion, VAL),
            Paragraph(wt, ParagraphStyle("saw", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(_fd(fd, key), ParagraphStyle("sar", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(fd.get(key.replace("rating_", "comments_")) or comment_desc,
                      ParagraphStyle("sacd", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
        ])

    total_score = _fd(fd, "total_score")
    total_row = [[
        Paragraph("<b>Total Score:</b>", VAL),
        Paragraph("100%", ParagraphStyle("sat", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph(f"<b>{total_score}</b> / 5", ParagraphStyle("tat2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Rating:</b>  1 Unsatisfactory   2 Conditional   3 Satisfactory   4 Excellent   5 Outstanding",
                  ParagraphStyle("saleg", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
    ]]

    all_rows = hdr + criteria_rows + total_row
    t_crit = Table(all_rows, colWidths=[CW_C, CW_W, CW_R, CW_M])
    t_crit.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
        ("BACKGROUND",    (0, -1),(-1, -1), _C_SEC_BG),
        ("LINEABOVE",     (0, -1),(-1, -1), 0.5, C_BLACK),
    ]))
    story.append(t_crit)
    story.append(Spacer(1, 6))

    # ── Narrative + signatures ───────────────────────────────────────
    narrative_fields = [
        ("Employee Strengths and Achievements",
         _fd(fd, "employee_strengths")),
        ("Areas for Improvement",
         _fd(fd, "areas_for_improvement")),
        ("Development Goals",
         _fd(fd, "development_goals")),
        ("Employee's Feedback (Optional)",
         _fd(fd, "employee_feedback")),
        ("Appraiser's Comments",
         _fd(fd, "appraiser_comments")),
    ]
    narrative_rows = []
    for label, val in narrative_fields:
        narrative_rows.append([_fsec(label, left=True), ""])
        narrative_rows.append([Paragraph(val, VAL), ""])

    sig_rows_idx = []
    sig_r_start = len(narrative_rows)
    narrative_rows.append([
        _fsig("Employee Signature", fd.get("employee_signature")),
        _fsig("Appraiser Signature", fd.get("hr_signature")),
    ])
    sig_rows_idx.append(sig_r_start)

    span_idx = [i for i in range(0, len(narrative_rows) - 1, 2)]
    content_idx = [i for i in range(1, len(narrative_rows) - 1, 2)]
    sec_idx = span_idx

    t_narr = _ftable(narrative_rows, [L, R],
                     spans=span_idx + content_idx,
                     secs=sec_idx,
                     sigs=sig_rows_idx,
                     extra=[("MINROWHEIGHT", (0, i), (-1, i), 35)
                             for i in content_idx])
    story.append(t_narr)


# ─────────────────────────────────────────────────────────────────────────────
#  PERFORMANCE EVALUATION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_performance_evaluation(story, fd, styles):
    """Employee Performance Evaluation Form — 10-parameter table matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, ITL = _fstyles()

    # ── Employee info ────────────────────────────────────────────────
    info_rows = [
        [_flv("Employee Name",    _fd(fd, "employee_name")),
         _flv("Date of Evaluation",_fmt(fd.get("date_of_evaluation")))],
        [_flv("Employee ID No",   _fd(fd, "employee_id")),
         _flv("Date of Joining",  _fmt(fd.get("date_of_joining")))],
        [_flv("Department / Section", _fd(fd, "department")),
         _flv("Designation",      _fd(fd, "designation"))],
        [_flv("Evaluation Done By",   _fd(fd, "evaluation_done_by")), ""],
    ]
    t_info = _ftable(info_rows, [L, R], spans=(3,))

    story.append(_header_table("Employee Performance Evaluation Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Rating legend ────────────────────────────────────────────────
    story.append(Paragraph(
        "<b>To be filled by Supervisor / HOD / Manager:</b>&nbsp;&nbsp;&nbsp;"
        "<b>To be filled by the Performance Evaluator:</b>",
        ParagraphStyle("peNote", fontSize=8.5, fontName="Helvetica-Bold",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11)))
    story.append(Spacer(1, 3))

    leg_left  = ("Outstanding 10 &nbsp; Excellent 8 &nbsp; Satisfactory 7 &nbsp; "
                 "Conditional 5 &nbsp; Unsatisfactory 4 or less")
    leg_right = ("90 &amp; above = Outstanding &nbsp; 80-89 = Excellent &nbsp; "
                 "70-79 = Satisfactory &nbsp; 50-69 = Conditional &nbsp; "
                 "00-49 = Unsatisfactory")
    leg_t = Table([[
        Paragraph(f"<b>RATING:</b><br/>{leg_left}", ParagraphStyle("ll", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
        Paragraph(f"<b>PERFORMANCE RATING:</b><br/>{leg_right}", ParagraphStyle("lr", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
    ]], colWidths=[L, R])
    leg_t.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (0, -1),  0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND",    (0, 0), (-1, -1), _C_SEC_BG),
    ]))
    story.append(leg_t)
    story.append(Spacer(1, 5))

    # ── Evaluation table ─────────────────────────────────────────────
    PARAMS = [
        ("01", "Communication.",
         "Internal/external communications with staff, client, contractors, "
         "supplier, etc on timely manners", "score_01"),
        ("02", "Achievements.",
         "Departmental achievements for better approach and company image",
         "score_02"),
        ("03", "Creativity and innovation.",
         "Reactiveness & productivity", "score_03"),
        ("04", "Collaboration and teamwork.",        "", "score_04"),
        ("05", "Problem-solving & reliability.",     "", "score_05"),
        ("06", "Quality and accuracy of work.",      "", "score_06"),
        ("07", "Attendance, punctuality.",            "", "score_07"),
        ("08", "Ability to accomplish goals and meet the deadlines.", "", "score_08"),
        ("09", "Intelligence:",
         "Analytic ability, mental alertness & general awareness", "score_09"),
        ("10", "Policy & HSE compliance:",
         "Awareness and complying with company policies and procedures as per "
         "HSE department", "score_10"),
    ]

    CW_SN = CW * 0.07
    CW_PM = CW * 0.71
    CW_SC = CW * 0.22

    eval_hdr = [[
        Paragraph("<b>SN</b>", ParagraphStyle("eh", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Evaluation Parameters</b>", ParagraphStyle("eh2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>SCORE</b>", ParagraphStyle("eh3", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]
    eval_rows = []
    for sn, title, desc, key in PARAMS:
        txt = f"<b>{title}</b>"
        if desc:
            txt += f"<br/><font size='8'>{desc}</font>"
        eval_rows.append([
            Paragraph(sn, ParagraphStyle("esn", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(txt, VAL),
            Paragraph(_fd(fd, key), ParagraphStyle("esc", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        ])

    total_score = _fd(fd, "overall_score")
    overall_row = [[
        Paragraph("<b>OVERALL SCORE:</b>", ParagraphStyle("eos", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=12)),
        Paragraph("", VAL),
        Paragraph(f"<b>{total_score}</b>", ParagraphStyle("eos2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]

    t_eval = Table(eval_hdr + eval_rows + overall_row, colWidths=[CW_SN, CW_PM, CW_SC])
    extra_style_eval = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
        ("ALIGN",         (2, 0), (2, -1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
        ("BACKGROUND",    (0, -1),(-1, -1), _C_SEC_BG),
        ("LINEABOVE",     (0, -1),(-1, -1), 0.5, C_BLACK),
        ("SPAN",          (0, -1),(1, -1)),
    ]
    t_eval.setStyle(TableStyle(extra_style_eval))
    story.append(t_eval)
    story.append(Spacer(1, 6))

    # ── Evaluation details + signatures ──────────────────────────────
    eval_name = _fd(fd, "evaluator_name")
    eval_desig = _fd(fd, "evaluator_designation")
    obs         = _fd(fd, "evaluator_observation")
    concern     = _fd(fd, "area_of_concern")
    training    = _fd(fd, "training_required")
    emp_cmt     = _fd(fd, "employee_comments")
    incharge    = _fd(fd, "concern_incharge_name")
    inch_cmt    = _fd(fd, "incharge_comments")
    gm_rem      = _fd(fd, "gm_remarks")
    hr_rem      = _fd(fd, "hr_remarks")

    inch_sig = _fd(fd, "incharge_signature")
    detail_rows = [
        [_fsec("Evaluation Details"), ""],                                   # r0
        [_flv("Evaluator Name", eval_name),
         _flv("Designation",    eval_desig)],                                # r1
        [_flv("Evaluator Observation / Suggestion / Remarks", obs), ""],    # r2
        [_flv("Area of Concern / Weakness", concern), ""],                  # r3
        [_flv("Employee Training Required", training), ""],                  # r4
        [_flv("Employee Comments", emp_cmt), ""],                            # r5
        [_fsig("Employee Signature",  fd.get("employee_signature")),
         _fsig("Evaluator Signature", fd.get("evaluator_signature"))],       # r6 sigs
        [_fsec("For In-charge / Engineer / Manager"), ""],                   # r7
        [_flv("In-charge Name", incharge), ""],                              # r8
        [_flv("Comments & Recommendations", inch_cmt), ""],                  # r9
        [_fsig("In-charge / Engineer Signature",
               fd.get("incharge_signature")), ""],                           # r10 sig
        [_fsec("For General Manager"), ""],                                  # r11
        [_flv("GM Remarks / Comments", gm_rem), ""],                         # r12
        [_fsig("GM Signature", fd.get("gm_signature")), ""],                 # r13 sig
        [_fsec("For HR — Use Only"), ""],                                    # r14
        [_flv("HR Remarks / Comments", hr_rem), ""],                         # r15
        [_fsig("HR Signature", fd.get("hr_signature")), ""],                 # r16 sig
    ]

    t_det = _ftable(detail_rows, [L, R],
                    spans=(0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
                    secs=(0, 7, 11, 14),
                    sigs=(6, 10, 13, 16),
                    extra=[("MINROWHEIGHT", (0, 2), (-1, 2), 35),
                           ("MINROWHEIGHT", (0, 5), (-1, 5), 35),
                           ("MINROWHEIGHT", (0, 9), (-1, 9), 35),
                           ("MINROWHEIGHT", (0, 12),(-1, 12), 35),
                           ("MINROWHEIGHT", (0, 15),(-1, 15), 35)])
    story.append(t_det)


# ─────────────────────────────────────────────────────────────────────────────
#  CONTRACT RENEWAL ASSESSMENT FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_contract_renewal(story, fd, styles):
    """Employee Contract Renewal Assessment — mirrors Word doc exactly."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, _ = _fstyles()

    # ── Employee info ────────────────────────────────────────────────
    info_rows = [
        [_flv("Employee Name",    _fd(fd, "employee_name")),
         _flv("Date of Evaluation",
              _fmt(fd.get("date_of_evaluation")) or _fmt(fd.get("today_date")))],
        [_flv("Employee ID",      _fd(fd, "employee_id")),
         _flv("Date of Joining",  _fmt(fd.get("date_of_joining")))],
        [_flv("Department / Section", _fd(fd, "department")),
         _flv("Contract End Date",    _fmt(fd.get("contract_end_date")))],
        [_flv("Evaluation By",    _fd(fd, "evaluation_by") or _fd(fd, "evaluator_name")),
         _flv("Designation",      _fd(fd, "designation"))],
    ]
    t_info = _ftable(info_rows, [L, R])

    story.append(_header_table("Employee Contract Renewal Assessment", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))

    note_p = Paragraph(
        "<b>To be filled by supervisor:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "<b>To be filled by the Performance Evaluator:</b>",
        ParagraphStyle("crNote", fontSize=8.5, fontName="Helvetica-Bold",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11))
    story.append(note_p)
    story.append(Spacer(1, 3))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Score/decision legend ────────────────────────────────────────
    leg_l  = "Outstanding 5 &nbsp; Excellent 4 &nbsp; Satisfactory 3 &nbsp; Conditional 2 &nbsp; Unsatisfactory 1"
    leg_r  = "3 &amp; above → Renew Contract &nbsp; | &nbsp; 2–&gt;3 → Renew/Extend with Conditions &nbsp; | &nbsp; 2&lt; → Terminate"
    leg_t  = Table([[
        Paragraph(f"<b>SCORE AND PERFORMANCE RATING:</b><br/>{leg_l}",
                  ParagraphStyle("crll", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
        Paragraph(f"<b>DECISION BASED ON THE EVALUATION:</b><br/>{leg_r}",
                  ParagraphStyle("crlr", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
    ]], colWidths=[L, R])
    leg_t.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (0, -1),  0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND",    (0, 0), (-1, -1), _C_SEC_BG),
    ]))
    story.append(leg_t)
    story.append(Spacer(1, 5))

    # ── Main evaluation table ────────────────────────────────────────
    SECTIONS = [
        ("01", "Job Performance", [
            ("01A", "a", "Completes assigned tasks efficiently and accurately."),
            ("01B", "b", "Demonstrates a strong understanding of job responsibilities."),
            ("01C", "c", "Meets deadlines consistently."),
            ("01D", "d", "Produces work of high quality."),
            ("01E", "e", "Takes initiative to improve work processes."),
        ]),
        ("02", "Work Attitude and Behaviour", [
            ("02A", "a", "Shows a positive attitude towards work and colleagues."),
            ("02B", "b", "Accepts feedback constructively and strives for improvement."),
            ("02C", "c", "Maintains professionalism in all interactions."),
            ("02D", "d", "Demonstrates adaptability to changing situations or challenges."),
            ("02E", "e", "Upholds company policies and values."),
        ]),
        ("03", "Communication and Teamwork", [
            ("03A", "a", "Communicates clearly and effectively with team members."),
            ("03B", "b", "Works collaboratively and contributes to team goals."),
            ("03C", "c", "Resolves conflicts or issues amicably."),
            ("03D", "d", "Demonstrates good listening skills."),
            ("03E", "e", "Keeps supervisors and colleagues informed of work progress."),
        ]),
        ("04", "Attendance and Punctuality", [
            ("04A", "a", "Arrives on time and prepared for work."),
            ("04B", "b", "Maintains consistent attendance."),
            ("04C", "c", "Provides notice and valid reasons for absences."),
        ]),
    ]

    CW_SN = CW * 0.07
    CW_SB = CW * 0.07
    CW_PM = CW * 0.72
    CW_SC = CW * 0.14

    CR_hdr = [[
        Paragraph("<b>SN</b>", SML),
        Paragraph("", SML),
        Paragraph("<b>Evaluation Parameters</b>", ParagraphStyle("creh", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Rating</b>", ParagraphStyle("creh2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]

    CR_rows = []
    for sn, sec_title, items in SECTIONS:
        # Section header row — title in col1 so SPAN(1,ri)→(3,ri) shows it
        CR_rows.append([
            Paragraph(f"<b>{sn}</b>", ParagraphStyle("crsn", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(f"<b>{sec_title}</b>", ParagraphStyle("crst", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=12)),
            Paragraph("", SML),
            Paragraph("", SML),
        ])
        # Sub-items
        for code, suffix, desc in items:
            key = f"rating_{sn.lower()}{suffix}"
            CR_rows.append([
                Paragraph(sn,    SML),
                Paragraph(suffix.upper(), SML),
                Paragraph(desc,  VAL),
                Paragraph(_fd(fd, key), ParagraphStyle("crsc", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            ])

    # Overall Evaluation
    strength  = _fd(fd, "strength")
    improve   = _fd(fd, "areas_for_improvement")
    overall   = _fd(fd, "overall_score") or _fd(fd, "overall_rating")
    CR_rows += [
        [Paragraph("<b>05</b>", SML),
         Paragraph("<b>Overall Evaluation</b>", ParagraphStyle("crOE", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=12)),
         Paragraph("", SML), Paragraph("", SML)],
        [Paragraph("05", SML),
         Paragraph(f"<b>Strength:</b>  {strength}", VAL),
         Paragraph("", SML), Paragraph("", SML)],
        [Paragraph("05", SML),
         Paragraph(f"<b>Areas for Improvement:</b>  {improve}", VAL),
         Paragraph("", SML), Paragraph("", SML)],
        [Paragraph("<b>OVERALL SCORE:</b>", VAL),
         Paragraph("", SML),
         Paragraph("", SML),
         Paragraph(f"<b>{overall}</b>",
                   ParagraphStyle("cros2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12))],
    ]

    # Section header row indices in all_cr (0-based)
    all_cr = CR_hdr + CR_rows
    n_hdr  = 1  # CR_hdr has 1 row
    sec_hdr_rows = []
    ri = n_hdr
    for _, _, items in SECTIONS:
        sec_hdr_rows.append(ri)  # section header at ri
        ri += 1 + len(items)    # skip header + items
    # overall (05) header
    sec_hdr_rows.append(ri)

    # Calculate overall sub-rows indices for spanning col2+col3
    # Strength / improvement rows need col1+col2+col3 span
    strength_row_idx  = ri + 1
    improve_row_idx   = ri + 2
    overall_score_idx = ri + 3

    t_cr = Table(all_cr, colWidths=[CW_SN, CW_SB, CW_PM, CW_SC])
    cr_style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
        ("ALIGN",         (1, 0), (1, -1),  "CENTER"),
        ("ALIGN",         (3, 0), (3, -1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
        # Strength and improvement rows: span col1+col2+col3
        ("SPAN",          (1, strength_row_idx),  (2, strength_row_idx)),
        ("SPAN",          (1, improve_row_idx),   (2, improve_row_idx)),
        # Overall score row: span col0+col1+col2
        ("SPAN",          (0, overall_score_idx), (2, overall_score_idx)),
        # Section header: span col1+col2 (leave rating col separate)
        ("BACKGROUND",    (0, overall_score_idx), (-1, overall_score_idx), _C_SEC_BG),
        ("LINEABOVE",     (0, overall_score_idx), (-1, overall_score_idx), 0.5, C_BLACK),
        ("MINROWHEIGHT",  (0, strength_row_idx), (-1, strength_row_idx), 28),
        ("MINROWHEIGHT",  (0, improve_row_idx),  (-1, improve_row_idx),  28),
    ]
    for ri_s in sec_hdr_rows:
        cr_style.extend([
            ("BACKGROUND", (0, ri_s), (-1, ri_s), _C_SEC_BG),
            ("LINEBELOW",  (0, ri_s), (-1, ri_s), 0.5, C_BLACK),
            ("SPAN",       (1, ri_s), (3, ri_s)),   # title in col1 spans to col3
        ])

    t_cr.setStyle(TableStyle(cr_style))
    story.append(t_cr)
    story.append(Spacer(1, 5))

    # ── Recommendation + signature ───────────────────────────────────
    decision = (fd.get("decision") or fd.get("recommendation") or "").strip().lower()
    rec_rows = [
        [_fsec("Evaluator's Recommendation"), ""],
        [_fchk(decision == "renew",
               "3 & above    —    Renew Contract"), ""],
        [_fchk(decision in ("renew_conditions", "conditional"),
               "2 – >3    —    Renew or extend Contract with Conditions"), ""],
        [_fchk(decision == "terminate",
               "2<    —    Terminate Contract"), ""],
        [_fsig("Evaluator's Signature", fd.get("evaluator_signature")),
         _flv("Date", _fmt(fd.get("date_of_evaluation")))],
    ]
    t_rec = _ftable(rec_rows, [L, R],
                    spans=(0, 1, 2, 3),
                    secs=(0,),
                    sigs=(4,))
    story.append(t_rec)



_BUILDERS = {
    "leave_application": (_build_leave, "Leave Application"),
    "leave": (_build_leave, "Leave Application"),
    "commencement": (_build_commencement, "Commencement"),
    "duty_resumption": (_build_duty_resumption, "Duty Resumption"),
    "passport_release": (_build_passport_release, "Passport Release"),
    "grievance": (_build_grievance, "Grievance"),
    "visa_renewal": (_build_visa_renewal, "Visa Renewal"),
    "interview_assessment": (_build_interview_assessment, "Interview Assessment"),
    "staff_appraisal": (_build_staff_appraisal, "Staff Appraisal"),
    "station_clearance": (_build_station_clearance, "Station Clearance"),
    "performance_evaluation": (_build_performance_evaluation, "Performance Evaluation"),
    "contract_renewal": (_build_contract_renewal, "Contract Renewal"),
}


def build_hr_pdf(form_type, form_data, output_stream, submission_id=None):
    """Build a professional PDF for the given HR form type. Returns True on success."""
    builder, title = _BUILDERS.get(form_type, (None, None))
    if not builder:
        return False

    fd = form_data or {}
    styles = _get_styles()
    story = []

    builder(story, fd, styles)
    story.append(Spacer(1, 0.12 * inch))
    story.append(_footer_block(styles))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=_LM, rightMargin=_RM,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
    )
    doc.build(story, canvasmaker=lambda *a, **k: HRPDFCanvas(*a, form_title=title, **k))

    pdf_bytes = buf.getvalue()
    if hasattr(output_stream, "write"):
        output_stream.write(pdf_bytes)
    else:
        with open(output_stream, "wb") as f:
            f.write(pdf_bytes)
    return True


def supports_pdf(form_type):
    return form_type in _BUILDERS
