#!/usr/bin/env python3
"""
Generate the Kynvera IT review pack (landscape client decks):

  docs/Architecture_Deck.pdf
  docs/IT_Clarification_Answer_Matrix.pdf
  docs/Agent_Connectivity_Permissions_Attributes.pdf
  docs/artifacts/*.svg

Run from the project root:
    python scripts/generate_kynvera_it_pack.py
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

from common.kynvera_brand import (
    BRAND,
    BRAND_DARK,
    BRAND_WASH,
    CHROME,
    COMPANY_NAME,
    FOOTER_CONFIDENTIAL,
    TAGLINE,
    resolve_logo_path,
)
from common.kynvera_pdf_brand import _fitted_image_size

DOCS = os.path.join(PROJECT_ROOT, "docs")
ARTIFACTS = os.path.join(DOCS, "artifacts")

CORAL = colors.HexColor(BRAND)
CORAL_DARK = colors.HexColor(BRAND_DARK)
WASH = colors.HexColor(BRAND_WASH)
MUTED = colors.HexColor(CHROME["text_muted"])
HAIR = colors.HexColor(CHROME["hairline"])
WELL = colors.HexColor(CHROME["well"])
PAGE = colors.HexColor(CHROME["page"])
WHITE = colors.white
INK = colors.HexColor(CHROME["text"])
SLATE = colors.HexColor(CHROME["text_mid"])
ZINC = colors.HexColor("#3f4654")
INK2 = colors.HexColor("#27272a")
SLATE_BAR = colors.HexColor("#71717a")
TODAY = date.today().strftime("%d %b %Y")

# Compact chrome
M_L = 1.1 * cm
M_R = 1.1 * cm
HDR_H = 0.92 * cm
FTR_H = 0.92 * cm

CHART_PALETTE = [CORAL, INK2, SLATE_BAR, colors.HexColor("#a1a1aa"), WASH]


# ── styles ──────────────────────────────────────────────────────────────────


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def styles_pack():
    return {
        "kicker": ParagraphStyle(
            "Kicker", fontName="Helvetica-Bold", fontSize=7, textColor=CORAL_DARK,
            spaceAfter=1, leading=9, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "H1", fontName="Helvetica-Bold", fontSize=18, textColor=INK,
            spaceAfter=3, leading=21,
        ),
        "h2": ParagraphStyle(
            "H2", fontName="Helvetica-Bold", fontSize=11, textColor=INK,
            spaceBefore=0, spaceAfter=3, leading=14,
        ),
        "h3": ParagraphStyle(
            "H3", fontName="Helvetica-Bold", fontSize=8.5, textColor=INK,
            spaceBefore=0, spaceAfter=2, leading=11,
        ),
        "body": ParagraphStyle(
            "Body", fontName="Helvetica", fontSize=7.5, textColor=ZINC,
            leading=10, spaceAfter=2,
        ),
        "caption": ParagraphStyle(
            "Cap", fontName="Helvetica", fontSize=6.5, textColor=MUTED, leading=8.5, spaceAfter=1,
        ),
        "cell": ParagraphStyle(
            "Cell", fontName="Helvetica", fontSize=6.5, textColor=ZINC, leading=8.8,
        ),
        "cell_b": ParagraphStyle(
            "CellB", fontName="Helvetica-Bold", fontSize=6.5, textColor=INK, leading=8.8,
        ),
        "th": ParagraphStyle(
            "TH", fontName="Helvetica-Bold", fontSize=6.5, textColor=INK, leading=8.8,
        ),
        "kpi_v": ParagraphStyle(
            "KpiV", fontName="Helvetica-Bold", fontSize=11, textColor=CORAL_DARK,
            alignment=TA_CENTER, leading=13,
        ),
        "kpi_l": ParagraphStyle(
            "KpiL", fontName="Helvetica", fontSize=6.2, textColor=MUTED,
            alignment=TA_CENTER, leading=8,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", fontName="Helvetica", fontSize=8.5, textColor=SLATE,
            leading=11, spaceAfter=2,
        ),
        "tiny": ParagraphStyle(
            "Tiny", fontName="Helvetica", fontSize=6, textColor=MUTED, leading=8,
        ),
        "pill": ParagraphStyle(
            "Pill", fontName="Helvetica-Bold", fontSize=6.5, textColor=CORAL_DARK,
            alignment=TA_CENTER, leading=9,
        ),
    }


def _p(text, style):
    return Paragraph(_esc(text).replace("\n", "<br/>"), style)


def table_style(header=True, alt=True, compact=True):
    pad = 3 if compact else 4
    cmds = [
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK) if header else ("TEXTCOLOR", (0, 0), (-1, -1), ZINC),
        ("BACKGROUND", (0, 0), (-1, 0), WASH) if header else ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("TEXTCOLOR", (0, 1), (-1, -1), ZINC),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("GRID", (0, 0), (-1, -1), 0.35, HAIR),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
    ]
    if alt:
        cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, WELL]))
    return TableStyle(cmds)


def matrix_table(st, headers, rows, col_widths):
    data = [[Paragraph(_esc(h), st["th"]) for h in headers]]
    for row in rows:
        data.append([
            Paragraph(_esc(c), st["cell_b"] if i == 0 else st["cell"])
            for i, c in enumerate(row)
        ])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(table_style())
    return t


def qa_table(st, rows, col_widths):
    data = [[Paragraph(h, st["th"]) for h in ["#", "Question", "Answer"]]]
    for n, q, a in rows:
        data.append([
            Paragraph(str(n), st["cell_b"]),
            Paragraph(_esc(q), st["cell_b"]),
            Paragraph(_esc(a), st["cell"]),
        ])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(table_style())
    return t


def two_col(left, right, cw, left_frac=0.56, gap=8):
    lw = cw * left_frac
    rw = cw - lw - gap
    t = Table([[left, right]], colWidths=[lw, rw])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), gap / 2),
        ("LEFTPADDING", (1, 0), (1, 0), gap / 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def kpi_strip(st, items, cw):
    """items: list of (value, label)"""
    n = len(items)
    gap = 5
    w = (cw - gap * (n - 1)) / n
    cells = []
    for val, lab in items:
        inner = Table(
            [[Paragraph(_esc(val), st["kpi_v"])], [Paragraph(_esc(lab), st["kpi_l"])]],
            colWidths=[w - 4],
        )
        inner.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, 0), (-1, -1), WASH),
            ("BOX", (0, 0), (-1, -1), 0.5, CORAL),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        cells.append(inner)
    t = Table([cells], colWidths=[w] * n)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ── chrome ───────────────────────────────────────────────────────────────────


class PackCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, page_size=A4, doc_title="", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []
        self._page_size = page_size
        self._doc_title = doc_title

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for i, state in enumerate(self._saved, 1):
            self.__dict__.update(state)
            self._chrome(i, n)
            super().showPage()
        super().save()

    def _chrome(self, page_number, page_count):
        w, h = self._page_size
        c = self
        c.setFillColor(WHITE)
        c.rect(0, h - HDR_H, w, HDR_H, fill=1, stroke=0)
        c.setStrokeColor(CORAL)
        c.setLineWidth(2.2)
        c.line(0, h - 0.6, w, h - 0.6)

        path = resolve_logo_path(prefer_wordmark=True)
        if path:
            try:
                dw, dh = _fitted_image_size(path, 2.9 * cm, 0.58 * cm)
                c.drawImage(
                    path, M_L, h - HDR_H + (HDR_H - dh) / 2,
                    width=dw, height=dh, preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(CORAL_DARK)
                c.drawString(M_L, h - 0.58 * cm, COMPANY_NAME)
        c.setFont("Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawRightString(w - M_R, h - 0.55 * cm, self._doc_title)

        c.setStrokeColor(HAIR)
        c.setLineWidth(0.4)
        c.line(M_L, h - HDR_H, w - M_R, h - HDR_H)
        c.line(M_L, FTR_H, w - M_R, FTR_H)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawString(M_L, 0.38 * cm, FOOTER_CONFIDENTIAL + "  ·  " + TODAY)
        c.drawRightString(w - M_R, 0.38 * cm, f"{page_number} / {page_count}")


def make_doc(path, page_size, title, author="Kynvera"):
    w, h = page_size
    top = HDR_H + 0.18 * cm
    bot = FTR_H + 0.12 * cm
    doc = BaseDocTemplate(
        path,
        pagesize=page_size,
        leftMargin=M_L,
        rightMargin=M_R,
        topMargin=top,
        bottomMargin=bot,
        title=title,
        author=author,
    )
    frame = Frame(M_L, bot, w - M_L - M_R, h - top - bot, id="main", showBoundary=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    return doc, w - M_L - M_R


# ── drawing primitives ─────────────────────────────────────────────────────


def _round_box(c, x, y, w, h, fill, stroke, radius=3.5):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def _label(c, x, y, text, size=6.5, color=INK, bold=True, align="center"):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(color)
    if align == "center":
        c.drawCentredString(x, y, text)
    elif align == "left":
        c.drawString(x, y, text)
    else:
        c.drawRightString(x, y, text)


def _arrow(c, x1, y1, x2, y2, color=MUTED):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.0)
    c.line(x1, y1, x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    s = 3.5
    c.line(x2, y2, x2 - ux * s + px * 2.6, y2 - uy * s + py * 2.6)
    c.line(x2, y2, x2 - ux * s - px * 2.6, y2 - uy * s - py * 2.6)


class ArchitectureStack(Flowable):
    def __init__(self, width, height=168):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        boxes = [
            (0, h - 22, w * 0.22, 20, "Web / PWA", WHITE, HAIR),
            (w * 0.24, h - 22, w * 0.22, 20, "Capacitor", WHITE, HAIR),
            (w * 0.48, h - 22, w * 0.24, 20, "HTTPS + JWT", WASH, CORAL),
        ]
        for x, y, bw, bh, t, f, s in boxes:
            _round_box(c, x, y, bw, bh, f, s, 3)
            _label(c, x + bw / 2, y + 6.5, t, 6.5)
        _arrow(c, w * 0.60, h - 24, w * 0.60, h - 34, CORAL)

        _round_box(c, 0, 42, w, h - 62, WASH, CORAL, 6)
        _label(c, 8, h - 50, "CUSTOMER-CONTROLLED BOUNDARY", 6.5, CORAL_DARK, True, "left")
        _label(
            c, 8, h - 61,
            "Nginx / TLS  ·  Flask (Gunicorn)  ·  RBAC · ticket ACL · rate limits · audit · CSRF",
            5.8, SLATE, False, "left",
        )
        mods = [
            "Auth", "Workflow", "Inspections", "Tickets", "HR", "Procurement",
            "MMR", "DocHub", "Files", "QHSI / BD", "Assets", "Ask Kynvera",
        ]
        mw = (w - 16) / 6
        for i, name in enumerate(mods):
            col, row = i % 6, i // 6
            x = 8 + col * mw
            y = h - 86 - row * 22
            _round_box(c, x, y, mw - 5, 18, WHITE, HAIR, 3)
            _label(c, x + (mw - 5) / 2, y + 5.5, name, 6)
        _label(c, 8, 48, "PostgreSQL  ·  Redis (optional)  ·  GENERATED_DIR disk", 5.8, SLATE, False, "left")

        egress = [
            (0, 4, w * 0.31, 32, "Cloudinary", "media · required in prod"),
            (w * 0.345, 4, w * 0.31, 32, "Mail / Drive", "optional · allow-listed"),
            (w * 0.69, 4, w * 0.31, 32, "LLM endpoint", "prompt + snippets only"),
        ]
        for x, y, bw, bh, t, sub in egress:
            _round_box(c, x, y, bw, bh, WHITE, HAIR, 3)
            _label(c, x + bw / 2, y + 18, t, 6.5)
            _label(c, x + bw / 2, y + 7, sub, 5.5, MUTED, False)
        _arrow(c, w * 0.155, 42, w * 0.155, 38, MUTED)
        _arrow(c, w * 0.50, 42, w * 0.50, 38, MUTED)
        _arrow(c, w * 0.845, 42, w * 0.845, 38, MUTED)


class Pipeline(Flowable):
    def __init__(self, width, stages, note="", height=58):
        super().__init__()
        self.width = width
        self.stages = stages
        self.note = note
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        n = len(self.stages)
        gap = 10
        bw = (self.width - gap * (n - 1)) / n
        y = 12 if self.note else 4
        h = self.height - (18 if self.note else 8)
        for i, (title, sub) in enumerate(self.stages):
            x = i * (bw + gap)
            _round_box(c, x, y, bw, h, WHITE, CORAL if i == n - 1 else HAIR, 3)
            _label(c, x + bw / 2, y + h / 2 + 4, title, 6.5)
            if sub:
                _label(c, x + bw / 2, y + h / 2 - 8, sub, 5.5, MUTED, False)
            if i < n - 1:
                _arrow(c, x + bw, y + h / 2, x + bw + gap, y + h / 2, CORAL)
        if self.note:
            _label(c, 0, 2, self.note, 5.8, MUTED, False, "left")


class DonutChart(Flowable):
    """Honest structural donut. slices: [(value, label)]."""

    def __init__(self, width, slices, title="", height=118):
        super().__init__()
        self.width = width
        self.slices = slices
        self.title = title
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        if self.title:
            _label(c, 0, self.height - 10, self.title, 7, INK, True, "left")
        total = sum(v for v, _ in self.slices) or 1
        cx, cy, r, ir = 52, 48, 38, 22
        start = 90
        for i, (v, lab) in enumerate(self.slices):
            extent = -360.0 * v / total
            col = CHART_PALETTE[i % len(CHART_PALETTE)]
            c.setFillColor(col)
            c.setStrokeColor(WHITE)
            c.setLineWidth(1)
            c.wedge(cx - r, cy - r, cx + r, cy + r, start, extent, fill=1, stroke=1)
            start += extent
        c.setFillColor(WHITE)
        c.setStrokeColor(WHITE)
        c.circle(cx, cy, ir, fill=1, stroke=0)
        _label(c, cx, cy - 3, str(int(total)), 9, INK, True)
        ly = self.height - 24
        for i, (v, lab) in enumerate(self.slices):
            col = CHART_PALETTE[i % len(CHART_PALETTE)]
            c.setFillColor(col)
            c.rect(100, ly - 1, 7, 7, fill=1, stroke=0)
            pct = 100.0 * v / total
            _label(c, 112, ly, f"{lab}  {v:.0f}  ({pct:.0f}%)", 6.2, ZINC, False, "left")
            ly -= 12


class HBarChart(Flowable):
    """Horizontal bars. rows: [(label, value, max)]."""

    def __init__(self, width, rows, title="", height=90):
        super().__init__()
        self.width = width
        self.rows = rows
        self.title = title
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        y0 = self.height - 12
        if self.title:
            _label(c, 0, y0, self.title, 7, INK, True, "left")
            y0 -= 12
        n = len(self.rows)
        row_h = min(16, (y0 - 4) / max(n, 1))
        mx = max(r[1] for r in self.rows) or 1
        bar_x = 118
        bar_w = self.width - bar_x - 28
        for i, (lab, val, _) in enumerate(self.rows):
            y = y0 - (i + 1) * row_h + 2
            _label(c, 0, y + 3, lab, 6, ZINC, False, "left")
            c.setFillColor(WELL)
            c.roundRect(bar_x, y, bar_w, 9, 2, fill=1, stroke=0)
            c.setFillColor(CORAL)
            c.roundRect(bar_x, y, max(2, bar_w * val / mx), 9, 2, fill=1, stroke=0)
            _label(c, bar_x + bar_w + 4, y + 2, str(val), 6, INK, True, "left")


class NetworkDiagram(Flowable):
    def __init__(self, width, height=132):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        _round_box(c, w * 0.34, h / 2 - 22, w * 0.32, 44, WASH, CORAL, 6)
        _label(c, w / 2, h / 2 + 4, "Kynvera app", 8)
        _label(c, w / 2, h / 2 - 9, "Flask · Gunicorn · JWT", 5.8, MUTED, False)

        left = [
            (0.02, 0.78, "Users", "443 TLS inbound"),
            (0.02, 0.46, "PostgreSQL", "internal"),
            (0.02, 0.14, "Redis", "internal / TLS"),
        ]
        right = [
            (0.72, 0.82, "Cloudinary", "443 out"),
            (0.72, 0.58, "Mail APIs", "443 out"),
            (0.72, 0.34, "LLM", "443 · optional"),
            (0.72, 0.10, "Drive / OSM", "443 · optional"),
        ]
        for fx, fy, t, sub in left + right:
            x, y = w * fx, h * fy
            bw = w * 0.24
            _round_box(c, x, y, bw, 24, WHITE, HAIR, 3)
            _label(c, x + 5, y + 13, t, 6.2, INK, True, "left")
            _label(c, x + 5, y + 4, sub, 5.4, MUTED, False, "left")
            if fx < 0.5:
                _arrow(c, x + bw, y + 12, w * 0.34, h / 2, MUTED)
            else:
                _arrow(c, w * 0.66, h / 2, x, y + 12, MUTED)


class RbacLayers(Flowable):
    def __init__(self, width, height=72):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        layers = [
            ("1  JWT identity", "Signed-in user only.", "No client-supplied user_id."),
            ("2  Flags + designation", "access_* and role.", "Supervisor / GM / HR."),
            ("3  Object ACL", "Ticket roster, DocHub.", "Files / Drive consent."),
            ("4  Retrieval filter", "Assistant sees only", "what the user may see."),
        ]
        bw = (self.width - 12) / 4
        for i, (t, s1, s2) in enumerate(layers):
            x = i * (bw + 4)
            _round_box(c, x, 6, bw, 58, WASH if i == 3 else WHITE, CORAL if i == 3 else HAIR, 3)
            _label(c, x + 6, 48, t, 6.3, CORAL_DARK, True, "left")
            _label(c, x + 6, 32, s1, 5.6, MUTED, False, "left")
            _label(c, x + 6, 22, s2, 5.6, MUTED, False, "left")
            if i < 3:
                _arrow(c, x + bw, 35, x + bw + 4, 35, CORAL)


class ModuleCards(Flowable):
    def __init__(self, width, modules, height=148):
        super().__init__()
        self.width = width
        self.modules = modules  # (name, auto, human)
        self.height = height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        cols = 2
        rows = math.ceil(len(self.modules) / cols)
        gap = 5
        cw = (self.width - gap) / cols
        rh = (self.height - gap * (rows - 1)) / rows
        for i, (name, auto, human) in enumerate(self.modules):
            col, row = i % cols, i // cols
            x = col * (cw + gap)
            y = self.height - (row + 1) * rh - gap * row
            box_h = rh - 2
            _round_box(c, x, y, cw, box_h, WHITE, HAIR, 3)
            _label(c, x + 6, y + box_h - 12, name, 7, CORAL_DARK, True, "left")
            _label(c, x + 6, y + box_h - 24, "Auto  " + auto, 5.6, ZINC, False, "left")
            _label(c, x + 6, y + box_h - 34, "Human  " + human, 5.6, MUTED, False, "left")


# ── SVG artifacts ─────────────────────────────────────────────────────────────


def write_svgs():
    os.makedirs(ARTIFACTS, exist_ok=True)
    files = {
        "architecture-stack.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 380" font-family="Helvetica, Arial, sans-serif">
  <rect width="980" height="380" fill="#f7f7f9"/>
  <rect x="24" y="14" width="180" height="32" rx="5" fill="#fff" stroke="#e9eaee"/><text x="114" y="35" text-anchor="middle" font-size="12" fill="#191b23">Web / PWA</text>
  <rect x="220" y="14" width="180" height="32" rx="5" fill="#fff" stroke="#e9eaee"/><text x="310" y="35" text-anchor="middle" font-size="12" fill="#191b23">Capacitor</text>
  <rect x="416" y="14" width="200" height="32" rx="5" fill="#fff4ef" stroke="#ff8e68"/><text x="516" y="35" text-anchor="middle" font-size="12" fill="#e05f36">HTTPS + JWT</text>
  <rect x="24" y="62" width="932" height="210" rx="8" fill="#fff4ef" stroke="#ff8e68"/>
  <text x="40" y="84" font-size="11" font-weight="700" fill="#e05f36">CUSTOMER-CONTROLLED BOUNDARY</text>
  <g font-size="11" fill="#191b23">
    <rect x="40" y="100" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="110" y="118" text-anchor="middle">Auth</text>
    <rect x="190" y="100" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="260" y="118" text-anchor="middle">Workflow</text>
    <rect x="340" y="100" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="410" y="118" text-anchor="middle">Inspections</text>
    <rect x="490" y="100" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="560" y="118" text-anchor="middle">Tickets</text>
    <rect x="640" y="100" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="710" y="118" text-anchor="middle">HR</text>
    <rect x="790" y="100" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="860" y="118" text-anchor="middle">Procurement</text>
    <rect x="40" y="138" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="110" y="156" text-anchor="middle">MMR</text>
    <rect x="190" y="138" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="260" y="156" text-anchor="middle">DocHub</text>
    <rect x="340" y="138" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="410" y="156" text-anchor="middle">Files</text>
    <rect x="490" y="138" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="560" y="156" text-anchor="middle">QHSI / BD</text>
    <rect x="640" y="138" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="710" y="156" text-anchor="middle">Assets</text>
    <rect x="790" y="138" width="140" height="28" rx="4" fill="#fff" stroke="#e9eaee"/><text x="860" y="156" text-anchor="middle">Ask Kynvera</text>
  </g>
  <text x="40" y="198" font-size="11" fill="#5c616e">PostgreSQL · Redis · GENERATED_DIR</text>
  <rect x="40" y="300" width="280" height="52" rx="6" fill="#fff" stroke="#e9eaee"/><text x="180" y="322" text-anchor="middle" font-size="13">Cloudinary</text><text x="180" y="338" text-anchor="middle" font-size="10" fill="#9498a3">media · required in prod</text>
  <rect x="350" y="300" width="280" height="52" rx="6" fill="#fff" stroke="#e9eaee"/><text x="490" y="322" text-anchor="middle" font-size="13">Mail / Drive</text><text x="490" y="338" text-anchor="middle" font-size="10" fill="#9498a3">optional · allow-listed</text>
  <rect x="660" y="300" width="280" height="52" rx="6" fill="#fff" stroke="#e9eaee"/><text x="800" y="322" text-anchor="middle" font-size="13">LLM endpoint</text><text x="800" y="338" text-anchor="middle" font-size="10" fill="#9498a3">prompt + snippets only</text>
</svg>""",
        "ask-kynvera-rag.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 160" font-family="Helvetica, Arial, sans-serif">
  <rect width="980" height="160" fill="#f7f7f9"/>
  <text x="20" y="22" font-size="12" font-weight="700" fill="#e05f36">DATA FLOW C — Ask Kynvera</text>
  <rect x="16" y="48" width="150" height="56" rx="6" fill="#fff" stroke="#e9eaee"/><text x="91" y="80" text-anchor="middle" font-size="12">Question</text>
  <rect x="196" y="48" width="160" height="56" rx="6" fill="#fff4ef" stroke="#ff8e68"/><text x="276" y="80" text-anchor="middle" font-size="12">Tool loop</text>
  <rect x="386" y="48" width="170" height="56" rx="6" fill="#fff" stroke="#e9eaee"/><text x="471" y="80" text-anchor="middle" font-size="12">SQL / DocHub</text>
  <rect x="586" y="48" width="160" height="56" rx="6" fill="#fff" stroke="#e9eaee"/><text x="666" y="80" text-anchor="middle" font-size="12">Compose</text>
  <rect x="776" y="48" width="180" height="56" rx="6" fill="#fff" stroke="#e9eaee"/><text x="866" y="80" text-anchor="middle" font-size="12">Answer / Confirm</text>
  <text x="20" y="140" font-size="11" fill="#5c616e">ACL first. Writes are proposals. Restricted material never enters the prompt.</text>
</svg>""",
        "ticket-lifecycle.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 180" font-family="Helvetica, Arial, sans-serif">
  <rect width="980" height="180" fill="#f7f7f9"/>
  <text x="20" y="22" font-size="12" font-weight="700" fill="#e05f36">DATA FLOW D — Work orders</text>
  <rect x="16" y="70" width="150" height="50" rx="6" fill="#fff" stroke="#e9eaee"/><text x="91" y="100" text-anchor="middle" font-size="12">UI / chat / email</text>
  <rect x="196" y="70" width="150" height="50" rx="6" fill="#fff4ef" stroke="#ff8e68"/><text x="271" y="100" text-anchor="middle" font-size="12">Ticket</text>
  <rect x="376" y="70" width="160" height="50" rx="6" fill="#fff" stroke="#e9eaee"/><text x="456" y="100" text-anchor="middle" font-size="12">Triage preview</text>
  <rect x="566" y="70" width="160" height="50" rx="6" fill="#fff" stroke="#e9eaee"/><text x="646" y="100" text-anchor="middle" font-size="12">Human confirm</text>
  <rect x="756" y="70" width="200" height="50" rx="6" fill="#fff" stroke="#e9eaee"/><text x="856" y="100" text-anchor="middle" font-size="12">PDF / invoice</text>
</svg>""",
        "network-connectivity.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 280" font-family="Helvetica, Arial, sans-serif">
  <rect width="980" height="280" fill="#f7f7f9"/>
  <text x="20" y="22" font-size="12" font-weight="700" fill="#e05f36">NETWORK — allow-listed HTTPS</text>
  <rect x="360" y="110" width="260" height="64" rx="8" fill="#fff4ef" stroke="#ff8e68"/>
  <text x="490" y="140" text-anchor="middle" font-size="14">Kynvera app</text>
  <text x="490" y="156" text-anchor="middle" font-size="10" fill="#5c616e">no extra public inbound</text>
  <rect x="20" y="40" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="120" y="62" text-anchor="middle" font-size="11">Users 443 TLS</text>
  <rect x="20" y="120" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="120" y="142" text-anchor="middle" font-size="11">PostgreSQL</text>
  <rect x="20" y="200" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="120" y="222" text-anchor="middle" font-size="11">Redis</text>
  <rect x="760" y="36" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="860" y="58" text-anchor="middle" font-size="11">Cloudinary 443</text>
  <rect x="760" y="90" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="860" y="112" text-anchor="middle" font-size="11">Mail 443</text>
  <rect x="760" y="144" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="860" y="166" text-anchor="middle" font-size="11">LLM 443 optional</text>
  <rect x="760" y="198" width="200" height="36" rx="5" fill="#fff" stroke="#e9eaee"/><text x="860" y="220" text-anchor="middle" font-size="11">Drive / OSM optional</text>
</svg>""",
    }
    for name, body in files.items():
        path = os.path.join(ARTIFACTS, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        print("  wrote", path)


def _canvas_maker(page_size, title):
    def _inner(filename, **kw):
        return PackCanvas(filename, page_size=page_size, doc_title=title, **kw)
    return _inner


# ── Architecture ─────────────────────────────────────────────────────────────


def build_architecture(path):
    st = styles_pack()
    page = landscape(A4)
    doc, cw = make_doc(path, page, "Kynvera · Solution Architecture")
    story = []

    # 1 Cover
    story.append(_p("SOLUTION ARCHITECTURE", st["kicker"]))
    story.append(_p("Kynvera — Injaaz FM Operations Platform", st["h1"]))
    story.append(_p(
        "Inside your operations stack  ·  Grounded & auditable  ·  Yours to operate  ·  " + TAGLINE,
        st["cover_sub"],
    ))
    story.append(Spacer(1, 4))
    story.append(kpi_strip(st, [
        ("12", "Operations modules"),
        ("Confirm", "Before any assistant write"),
        ("No Graph", "No Microsoft tenant grant"),
        ("No GPU", "LLM at approved endpoint"),
    ], cw))
    story.append(Spacer(1, 6))
    story.append(ArchitectureStack(cw, 168))
    story.append(Spacer(1, 4))
    pillars = [
        ["Inside the boundary", "Grounded by design", "Yours to operate"],
        [
            "Postgres, disk, prompts, audit. Cloud is allow-listed egress only.",
            "SQL tools, labelled estimates, Confirm on writes, deterministic PDFs.",
            "Redeploy + restore. No per-seat platform tax from Kynvera.",
        ],
    ]
    pdat = [
        [Paragraph(_esc(c), st["th"] if i == 0 else st["cell"]) for c in row]
        for i, row in enumerate(pillars)
    ]
    pt = Table(pdat, colWidths=[cw / 3.0] * 3)
    pt.setStyle(table_style())
    story.append(pt)
    story.append(PageBreak())

    # 2 Operating team
    story.append(_p("THE OPERATING TEAM", st["kicker"]))
    story.append(_p("Modules own stages of FM work. Ask Kynvera sits across them.", st["h2"]))
    mods = [
        ("Ask Kynvera", "Grounded Q&A; draft proposals", "Confirm before any write"),
        ("Inspections", "HVAC / Civil / Cleaning, PDF", "Reviewer signatures"),
        ("Ticketing", "Lifecycle, photos, SLA, costs", "Assign, verify, close, markup"),
        ("Email intake", "Mail → draft ticket", "Convert draft to live work"),
        ("AI triage", "Priority / SLA / technician / parts", "Accept or override"),
        ("Assets / GIS", "Registry, QR, map, 2D twin", "Master data decisions"),
        ("HR", "Leave and workforce forms", "HR → GM chain"),
        ("Procurement", "Catalogues, PRs", "Threshold / GM rules"),
        ("MMR", "CAFM ingest, chargeable rules", "Recipients you configure"),
        ("DocHub / Files", "Controlled docs; optional Drive", "Publish and folder policy"),
    ]
    story.append(two_col(
        ModuleCards(cw * 0.62, mods, 250),
        DonutChart(cw * 0.36, [
            (10, "Automated processing"),
            (10, "Human gate required"),
        ], "Stages: process vs sign-off"),
        cw, 0.63, 8,
    ))
    story.append(Spacer(1, 4))
    story.append(_p(
        "Source: module count in the product. Automation handles processing and drafts; people approve, assign, sign, and close. Nothing client-facing goes out on assistant say-so.",
        st["caption"],
    ))
    story.append(PageBreak())

    # 3 Data classification + LLM
    story.append(_p("DATA SOVEREIGNTY", st["kicker"]))
    story.append(_p("Records stay. Inference is a single logged path you approve.", st["h2"]))
    story.append(two_col(
        ArchitectureStack(cw * 0.58, 160),
        Table([
            [DonutChart(cw * 0.40, [
                (1, "Approved cloud"),
                (1, "Your endpoint"),
                (1, "LLM off"),
            ], "LLM modes (options, not usage)")],
            [Spacer(1, 4)],
            [HBarChart(cw * 0.40, [
                ("Stays in Postgres", 4, 5),
                ("Allow-listed media", 2, 5),
                ("One-turn LLM payload", 1, 5),
            ], "Relative exposure classes", 78)],
        ], colWidths=[cw * 0.40]),
        cw, 0.58, 8,
    ))
    story.append(Spacer(1, 4))
    story.append(matrix_table(st, ["Class", "Where it lives", "May leave?"], [
        ["Tickets, forms, HR, assets", "PostgreSQL", "No — never as a bulk dump"],
        ["Knowledge / FAQs / DocHub", "Postgres + DocHub ACL", "Only retrieved excerpts in a prompt"],
        ["Photos / signatures", "Cloudinary (prod) or disk", "Yes — contracted media account"],
        ["Generated PDF / Excel", "GENERATED_DIR", "No unless you email them"],
        ["Assistant writes", "Pending action 15 min, then Confirm", "No unattended submit"],
    ], [cw * 0.28, cw * 0.36, cw * 0.36]))
    story.append(_p("Cloud LLM: current turn only. Provider API terms do not train on API traffic by default, subject to your agreement.", st["caption"]))
    story.append(PageBreak())

    # 4 Flows A+B
    story.append(_p("DATA FLOW A — FIELD CAPTURE", st["kicker"]))
    story.append(_p("Site visit to signed, auditable record", st["h3"]))
    story.append(Pipeline(cw, [
        ("Phone / PWA", "photos · checklist"),
        ("Form", "module flag"),
        ("Submission", "JSON + media"),
        ("Workflow", "designation"),
        ("PDF / Excel", "deterministic"),
    ], "Media to Cloudinary or disk — not to the LLM unless a later permitted question retrieves it.", 56))
    story.append(Spacer(1, 6))
    story.append(_p("DATA FLOW B — KNOWLEDGE", st["kicker"]))
    story.append(_p("Help content becomes answers without dumping the database", st["h3"]))
    story.append(Pipeline(cw, [
        ("FAQ / admin KB", "text · upload · URL"),
        ("DocHub", "if user may access"),
        ("Retrieve", "scored excerpts"),
        ("Compose", "LLM optional"),
        ("Cited answer", "honest gap"),
    ], "Ingestion stays in Postgres/DocHub. Only compose may call a model.", 56))
    story.append(Spacer(1, 6))
    story.append(two_col(
        matrix_table(st, ["Form class", "Stored as", "Completeness"], [
            ["Inspection / HR", "Submission + JSON form_data", "Workflow + signatures"],
            ["Work orders", "Ticket rows + images + SLA", "Draft vs live separated"],
            ["Assets", "Asset registry + QR + lat/lng", "CRUD + ticket link"],
            ["CAFM / MMR", "Uploaded workbooks + rules", "Chargeable checks"],
        ], [cw * 0.56 * 0.28, cw * 0.56 * 0.38, cw * 0.56 * 0.34]),
        DonutChart(cw * 0.42, [
            (4, "Structured DB records"),
            (1, "Optional LLM compose"),
        ], "Capture vs compose"),
        cw, 0.56, 8,
    ))
    story.append(PageBreak())

    # 5 Flows C+D
    story.append(_p("DATA FLOW C — ASK KYNVERA", st["kicker"]))
    story.append(_p("A question becomes a cited answer — or a Confirm card", st["h3"]))
    story.append(Pipeline(cw, [
        ("Question", "signed-in user"),
        ("Plan tools", "≤ 4 rounds"),
        ("SQL / DocHub", "ACL first"),
        ("Compose", "single egress"),
        ("Answer / Confirm", "writes are proposals"),
    ], "Restricted tools return allowed:false. Restricted material never enters the prompt.", 56))
    story.append(Spacer(1, 6))
    story.append(_p("DATA FLOW D — WORK ORDERS", st["kicker"]))
    story.append(_p("Three intakes. One ticket. Humans own commercial numbers.", st["h3"]))
    story.append(Pipeline(cw, [
        ("UI / chat / email", "three doors"),
        ("Ticket", "draft or open"),
        ("Triage preview", "never auto-apply"),
        ("Work + markup", "supervisor"),
        ("PDF / invoice", "builders, not LLM"),
    ], "Markup % and chargeable flags are supervisor fields — the assistant has no cost-estimator write tool.", 56))
    story.append(Spacer(1, 4))
    story.append(two_col(
        DonutChart(cw * 0.46, [
            (12, "Read tools"),
            (2, "Propose-only writes"),
        ], "Ask Kynvera tools (count)"),
        HBarChart(cw * 0.52, [
            ("Retrieve / SQL (inside)", 3, 4),
            ("Compose / LLM egress", 1, 4),
        ], "RAG steps inside vs egress", 72),
        cw, 0.46, 8,
    ))
    story.append(_p("Source: module_assistant tool registry — 12 read tools, 2 propose tools (ticket draft, leave draft).", st["caption"]))
    story.append(PageBreak())

    # 6 E+F
    story.append(_p("DATA FLOW E — MMR / CAFM", st["kicker"]))
    story.append(Pipeline(cw, [
        ("CAFM Excel", "upload"),
        ("pandas + rules", "chargeable policy"),
        ("Dashboard", "Excel pack"),
        ("Scheduler", "Asia/Dubai"),
        ("Email", "recipients you set"),
    ], "Workbook stays in app/disk. Email is an approved outbound path.", 54))
    story.append(Spacer(1, 6))
    story.append(_p("DATA FLOW F — FILES AND DRIVE", st["kicker"]))
    story.append(Pipeline(cw, [
        ("In-app Files", "Postgres metadata"),
        ("HR automations", "Excel copies"),
        ("OAuth (opt.)", "drive.file only"),
        ("Kynvera Files", "app-created root"),
        ("Local Files", "works if Drive off"),
    ], "drive.file cannot read the rest of the user’s Drive.", 54))
    story.append(Spacer(1, 6))
    story.append(matrix_table(st, ["Control", "Meaning"], [
        ["Source-bound", "Ticket/leave/FM numbers from SQL; policies from knowledge/DocHub"],
        ["Gaps flagged", "No source → say so; triage returns null technician if none fit"],
        ["Estimates labelled", "Asset RUL stored as method=llm_estimate until a trained model exists"],
        ["Human-in-the-loop", "Confirm, workflow sign, email-draft conversion"],
        ["Deterministic docs", "Client PDFs, invoices, MMR packs are ReportLab/openpyxl — not LLM prose"],
    ], [cw * 0.26, cw * 0.74]))
    story.append(PageBreak())

    # 7 Run + security + adoption
    story.append(_p("WHERE IT RUNS  ·  HARDENING  ·  ADOPTION", st["kicker"]))
    story.append(_p("Right-sized VM. GPU unused. Degrades gracefully. VAPT is your production gate if required.", st["h2"]))
    story.append(two_col(
        matrix_table(st, ["Component", "Reference", "Notes"], [
            ["Application", "2–4 vCPU, 8–16 GB", "Gunicorn; GPU unused"],
            ["PostgreSQL", "Managed", "Required in production"],
            ["Redis", "256 MB+", "Rate limits; optional RQ"],
            ["Disk", "100 GB+ SSD", "GENERATED_DIR reports"],
            ["OS", "Ubuntu 22.04 / 24.04", "Docker user injaaz"],
        ], [cw * 0.48 * 0.30, cw * 0.48 * 0.32, cw * 0.48 * 0.38]),
        matrix_table(st, ["Failure", "Behaviour"], [
            ["LLM down", "FAQ/intent fallback; forms continue"],
            ["Cloudinary down", "New uploads fail; DB intact"],
            ["Mail down", "UI continues; mail delayed"],
            ["Drive down", "Local Files continues"],
            ["Redis down", "App may run; limits degraded"],
            ["App VM fails", "Redeploy + restore Postgres + disk"],
        ], [cw * 0.50 * 0.32, cw * 0.50 * 0.68]),
        cw, 0.48, 8,
    ))
    story.append(Spacer(1, 5))
    story.append(matrix_table(st, ["Layer", "What exists today"], [
        ["Build", "Pinned deps, secrets in env, non-root container"],
        ["Identity", "bcrypt, JWT + session JTI blocklist, rate-limited login"],
        ["Transport / headers", "TLS, HSTS, nosniff, SAMEORIGIN, CSP Report-Only"],
        ["AuthZ / AI", "Module flags, ticket ACL, tool ACL, 15-min pending actions"],
        ["Not claimed as default", "Third-party pen-test, ISO/SOC, Entra SSO, TOTP MFA"],
    ], [cw * 0.24, cw * 0.76]))
    story.append(Spacer(1, 5))
    story.append(Pipeline(cw, [
        ("1 Inspections", "identity + workflow"),
        ("2 Ticketing", "email intake"),
        ("3 Assistant", "confirm-before-write"),
        ("4 Assets / GIS", "executive FM"),
        ("5 MMR / HR / Files", "back office"),
        ("6 ERP / BMS", "after discovery"),
    ], "Each phase is useful alone. No rip-and-replace of ERP. Next: security review → confirm LLM, Cloudinary, mail, Drive → contained pilot.", 54))

    doc.build(story, canvasmaker=_canvas_maker(page, "Kynvera · Solution Architecture"))
    print("  wrote", path)


# ── IT matrix ───────────────────────────────────────────────────────────────


def build_it_matrix(path):
    st = styles_pack()
    page = landscape(A4)
    doc, cw = make_doc(path, page, "Kynvera · IT Clarification Answer Matrix")
    story = []

    story.append(_p("ENTERPRISE IT CLARIFICATION", st["kicker"]))
    story.append(_p("Answer Matrix — Kynvera FM operations platform", st["h1"]))
    story.append(_p(
        "Not a generic chatbot and not a replacement for ERP or Microsoft 365. "
        "Records live in your PostgreSQL. The assistant reads only what the signed-in user may see. "
        "Writes are proposals until a human confirms.",
        st["cover_sub"],
    ))
    story.append(Spacer(1, 3))
    story.append(kpi_strip(st, [
        ("27", "IT questions answered"),
        ("3", "LLM modes"),
        ("1", "Logged model egress"),
        ("You", "Own backups"),
    ], cw))
    story.append(Spacer(1, 5))
    story.append(two_col(
        ArchitectureStack(cw * 0.58, 158),
        DonutChart(cw * 0.40, [
            (1, "Approved cloud"),
            (1, "Your endpoint"),
            (1, "LLM off"),
        ], "LLM modes — what can leave"),
        cw, 0.58, 8,
    ))
    story.append(_p(
        "Cloud mode sends only the user prompt plus retrieved passages or tool JSON for that turn. Never the full corpus.",
        st["caption"],
    ))
    story.append(PageBreak())

    story.append(_p("Q1–9  ·  BOUNDARY, GROUNDING, SCALE", st["kicker"]))
    story.append(two_col(
        qa_table(st, [
            (1, "Does operational / HR / commercial data leave? Is the LLM on-prem?",
             "Records stay in your DB and approved stores. LLM is provider-agnostic: approved cloud, your compatible endpoint, or off. Cloud sends only prompt + snippets for that turn. No bulk dump. No fine-tune of your data at the provider."),
            (2, "Complete architecture, integrations, data flow?",
             "Yes — Architecture Deck: components, trust boundary, flows A–F."),
            (3, "How are critical fields / SLA terms preserved?",
             "Typed DB rows and JSON form_data with workflow history — not naive chat chunking. Assistant facts come from live SQL scoped to the user."),
            (4, "How do you prevent hallucinated costs, SLA, assignments, policy?",
             "Grounded tools + confirm-before-write + labelled estimates. Counts and IDs from SQL. Missing sources → “I don’t have that.” Triage never auto-applies. Markup is a supervisor field."),
            (5, "How does it scale? Data loss on large packs?",
             "Web, Postgres, Redis, Cloudinary, report workers scale independently. Email intake is logged even on failure. Persistent disk required for generated reports."),
            (6, "Hardware: CPU, RAM, GPU?",
             "2–4 vCPU, 8 GB min / 16 GB rec, 100 GB+ SSD, Ubuntu, Postgres, Redis. GPU unused."),
            (7, "Accuracy rates? Validation before users see output?",
             "No single headline number. Trust is by construction: live SQL, RAG over approved knowledge, Confirm on writes, labelled estimates."),
            (8, "Inbound ticket email? Browser automation?",
             "Mailjet Parse → secret webhook → draft ticket. No tender-portal browser bot. Wrong secret returns 404."),
            (9, "What is automated vs human?",
             "Automation processes and drafts. People approve, assign, sign, close, convert email drafts, and set markup."),
        ], [cw * 0.62 * 0.07, cw * 0.62 * 0.30, cw * 0.62 * 0.63]),
        DonutChart(cw * 0.36, [
            (10, "Automated processing"),
            (10, "Human gate"),
        ], "Q9 — process vs sign-off"),
        cw, 0.62, 8,
    ))
    story.append(PageBreak())

    story.append(_p("Q10–18  ·  INTEGRATIONS, ACCESS, OPERATIONS", st["kicker"]))
    story.append(two_col(
        qa_table(st, [
            (10, "Microsoft 365, Google Drive, email, WhatsApp?",
             "Email (Mailjet/Brevo/SMTP) and optional Google Drive are native. No Microsoft Graph tenant grant. WhatsApp is not a product channel; field photos go app → Cloudinary."),
            (11, "Cloudinary / email / Drive — sensitive site data?",
             "Each is an explicit payload. Drive uses drive.file only (Kynvera Files root). Keep highly sensitive HR/commercial files in-app / DocHub unless policy permits Drive."),
            (12, "CAFM / ERP (MRI, Dynamics, SAP)?",
             "MMR already ingests CAFM-style Excel/HTML. Generic authenticated API + webhooks. Named ERP/BMS connectors after discovery."),
            (13, "Separate VPS for heavy work?",
             "No public VPS. PDF/Excel/MMR run as jobs on the app host or a worker inside the same boundary."),
            (14, "Concurrent users / tickets?",
             "Tens of concurrent interactive users on the reference VM. Re-size for heavy PDF/Excel. Confirm in a scoped pilot."),
            (15, "Restrict by module, project, ticket, document?",
             "Yes. Role + designation + access_* + ticket ACL + DocHub list. Retrieval filters so the assistant cannot see what the user cannot."),
            (16, "Vulnerabilities, pen tests, certifications?",
             "Secure SDLC, headers, rate limits, non-root container. No default third-party pen-test or ISO pack. VAPT can be your go-live gate."),
            (17, "Support after deployment?",
             "Internal product, operated by Injaaz. Warranty/handover as contracted. Stack is runnable independently."),
            (18, "If Microsoft 365, Cloudinary, or LLM is down?",
             "Core login, forms, tickets run if app + Postgres are up. LLM/mail/Drive/Cloudinary degrade as documented."),
        ], [cw * 0.62 * 0.07, cw * 0.62 * 0.30, cw * 0.62 * 0.63]),
        DonutChart(cw * 0.36, [
            (3, "Required (DB, Cloudinary, TLS)"),
            (6, "Optional (LLM, Drive, mail, OSM, Redis)"),
        ], "Integrations — required vs optional"),
        cw, 0.62, 8,
    ))
    story.append(_p("Source: production validator + .env.example. Postgres and Cloudinary are required in production; LLM, Drive, inbound mail, Redis, and geocode are optional.", st["caption"]))
    story.append(PageBreak())

    story.append(_p("Q19–27  ·  BACKUP, OWNERSHIP, ACCESS", st["kicker"]))
    story.append(two_col(
        qa_table(st, [
            (19, "Business continuity / DR?",
             "Postgres backups, versioned app deploy, GENERATED_DIR on persistent disk, documented restore. Optional provider PITR / OCI snapshots."),
            (20, "Who owns AI “memory” backups?",
             "You do. FAQs, admin knowledge, pending actions, triage logs, audit are in PostgreSQL. No fine-tuned copy at the model provider."),
            (21, "App server fails — restore trained state?",
             "Stateless app + restore Postgres (+ disk + secrets). Agent logic is versioned code, not model weights."),
            (22, "Standard backup routines?",
             "Follow your IT standard: pg_dump / snapshots; snapshot GENERATED_DIR; Cloudinary for media; secrets never in git."),
            (23, "End-to-end bid-to-finance, or operations + integrations?",
             "FM operations backbone. Complements ERP/finance/CAFM."),
            (24, "Global Administrator on Microsoft 365?",
             "Never. No Graph. Optional Drive is user-consented OAuth (drive.file + email/openid). In-app admin is our RBAC role."),
            (25, "What does the assistant touch?",
             "Only listed tools, as the signed-in user. Writes: propose ticket or leave draft. No approve, close, send mail, or Drive."),
            (26, "How does it know what a user may access?",
             "Kynvera user record: role, designation, access_*, ticket roster, DocHub row. JWT identity is user id."),
            (27, "Restrict pricing / commercial data?",
             "Yes. Markup, selling price, chargeable flags are supervisor fields. MMR needs access_report_generation. Assistant has no commercial write tool."),
        ], [cw * 0.62 * 0.07, cw * 0.62 * 0.30, cw * 0.62 * 0.63]),
        HBarChart(cw * 0.36, [
            ("You own Postgres", 1, 1),
            ("You own disk", 1, 1),
            ("Cloudinary media", 1, 1),
            ("Git + secrets store", 1, 1),
        ], "Backup ownership", 110),
        cw, 0.62, 8,
    ))
    story.append(Spacer(1, 4))
    story.append(_p(
        "Use with Architecture Deck (trust boundary) and Agent Connectivity (tools, OAuth, ports). "
        "Confirm LLM mode, Cloudinary, mail, and whether Google Drive is in scope before go-live.",
        st["body"],
    ))

    doc.build(story, canvasmaker=_canvas_maker(page, "Kynvera · IT Clarification Answer Matrix"))
    print("  wrote", path)


# ── Connectivity ───────────────────────────────────────────────────────────


def build_connectivity(path):
    st = styles_pack()
    page = landscape(A4)
    doc, cw = make_doc(path, page, "Kynvera · Agent Connectivity")
    story = []

    story.append(_p("IT AND SECURITY REVIEW", st["kicker"]))
    story.append(_p("Agent Connectivity, Permissions & Attributes", st["h1"]))
    story.append(_p(
        "What Kynvera connects to, what Ask Kynvera may read and propose, and least-privilege "
        "permissions for optional Google Drive, email, and object storage. "
        "Not a Microsoft 365 tenant agent. No Global Admin, Sites.Read.All, Mail.Send, or WhatsApp.",
        st["cover_sub"],
    ))
    story.append(Spacer(1, 3))
    story.append(kpi_strip(st, [
        ("12 / 2", "Read tools / propose"),
        ("drive.file", "Google scope (optional)"),
        ("443", "User inbound (TLS)"),
        ("Never", "Mail.Send / Graph"),
    ], cw))
    story.append(Spacer(1, 5))
    story.append(RbacLayers(cw, 70))
    story.append(Spacer(1, 4))
    story.append(_p(
        "Ask Kynvera always runs as the signed-in JWT user. Background jobs use server configuration, "
        "except Drive sync which uses the connecting user’s stored OAuth token. Administrators grant or "
        "revoke module flags in Administration.",
        st["body"],
    ))
    story.append(Spacer(1, 5))
    story.append(matrix_table(st, ["Never requested", "Never accessed"], [
        ["Microsoft Global Admin / Graph", "Full Google Drive or Gmail"],
        ["Mail.Send", "WhatsApp"],
        ["Sites.Read.All / Sites.FullControl.All", "Payroll / bank files"],
        ["Unrestricted database chat", "Automatic client-portal submit"],
    ], [cw * 0.50, cw * 0.50]))
    story.append(PageBreak())

    story.append(_p("ASK KYNVERA — TOOL MATRIX", st["kicker"]))
    story.append(_p("Read tools execute immediately. Write tools store a pending action until Confirm (15-minute TTL).", st["h2"]))
    story.append(two_col(
        matrix_table(st, ["Tool", "Kind", "Touches", "Access"], [
            ["get_pending_forms", "Read", "Pending reviewer items", "Reviewer or admin"],
            ["get_my_leave", "Read", "Own leave applications", "Own rows"],
            ["get_my_tickets", "Read", "Raised or assigned", "access_ticketing"],
            ["get_my_profile", "Read", "Own profile; admin person_name", "Self; others = admin"],
            ["search_documents", "Read", "Published DocHub", "DocHub access"],
            ["search_knowledge", "Read", "FAQ + admin KB + DocHub", "Authenticated (filtered)"],
            ["get_fm_critical_assets", "Read", "Critical / low-health assets", "access_ticketing"],
            ["get_fm_failures_by_building", "Read", "Failures by building", "access_ticketing"],
            ["get_fm_cost_trend", "Read", "Month vs prior costs", "access_ticketing"],
            ["get_fm_maintenance_report_hint", "Read", "How to generate MMR", "Ticketing or report_generation"],
            ["get_my_submissions / inspections", "Read", "Own form counts", "Signed-in user"],
            ["propose_create_ticket", "Propose", "Draft after Confirm", "access_ticketing"],
            ["propose_leave_draft", "Propose", "Leave draft — not submitted", "HR path"],
        ], [cw * 0.60 * 0.34, cw * 0.60 * 0.12, cw * 0.60 * 0.28, cw * 0.60 * 0.26]),
        DonutChart(cw * 0.38, [
            (12, "Read"),
            (2, "Propose"),
        ], "Tool kinds (count)"),
        cw, 0.62, 8,
    ))
    story.append(_p(
        "Out of scope: approve/reject workflow, close tickets, send mail, read/write Drive, payroll, passwords. "
        "AI triage is a separate preview/confirm API (TicketTriageLog). Source: module_assistant/agent.py tool registry.",
        st["caption"],
    ))
    story.append(PageBreak())

    story.append(_p("PLATFORM INTEGRATIONS  ·  GOOGLE OAUTH", st["kicker"]))
    story.append(two_col(
        matrix_table(st, ["Integration", "Reads / writes", "Required?"], [
            ["PostgreSQL", "All operational data", "Yes (production)"],
            ["Redis", "Rate-limit counters / jobs", "Strongly recommended"],
            ["Cloudinary", "Images, signatures, DocHub files", "Yes in production"],
            ["Mail outbound", "Reset, workflow, MMR", "When email is needed"],
            ["Mail inbound", "Subject/body → draft Ticket", "Optional"],
            ["Google Drive", "App-created tree under Kynvera Files", "Optional; user consent"],
            ["LLM", "Prompt + tool JSON → inference", "Optional"],
            ["Nominatim / Leaflet", "Geocode / map tiles", "Optional"],
        ], [cw * 0.56 * 0.30, cw * 0.56 * 0.42, cw * 0.56 * 0.28]),
        matrix_table(st, ["Scope", "Why", "Not requested"], [
            ["drive.file", "Files this app created (Kynvera Files root)", "drive / drive.readonly"],
            ["userinfo.email", "Show connected Google account", "Gmail, Contacts"],
            ["openid", "Link this Google login", "Calendar, Docs-wide"],
        ], [cw * 0.42 * 0.28, cw * 0.42 * 0.40, cw * 0.42 * 0.32]),
        cw, 0.56, 8,
    ))
    story.append(Spacer(1, 4))
    story.append(_p("Microsoft Graph is not used. No Sites.Selected, Mail.ReadWrite, or Teams RSC.", st["caption"]))
    story.append(Spacer(1, 4))
    story.append(HBarChart(cw, [
        ("Required prod (DB, Cloudinary, TLS)", 3, 9),
        ("Recommended (Redis)", 1, 9),
        ("Optional (LLM, Drive, mail, OSM)", 5, 9),
    ], "Integration count by necessity", 70))
    story.append(PageBreak())

    story.append(_p("NETWORK", st["kicker"]))
    story.append(_p("Almost all traffic is outbound HTTPS. No extra public inbound ports.", st["h2"]))
    story.append(two_col(
        NetworkDiagram(cw * 0.56, 150),
        matrix_table(st, ["Flow", "Dir", "Port", "When"], [
            ["Users / PWA / Capacitor", "In", "443 TLS", "Always"],
            ["PostgreSQL", "App → DB", "5432 / provider", "Yes"],
            ["Redis", "App → Redis", "6379 / rediss", "Recommended"],
            ["Cloudinary", "Out", "443", "Production"],
            ["Mailjet / Brevo", "Out", "443", "If email"],
            ["SMTP alt.", "Out", "587 STARTTLS", "If SMTP"],
            ["LLM endpoint", "Out", "443", "If LLM"],
            ["Google OAuth + Drive", "Out", "443", "If Drive"],
            ["Nominatim", "Out", "443", "If geocode"],
        ], [cw * 0.42 * 0.40, cw * 0.42 * 0.16, cw * 0.42 * 0.22, cw * 0.42 * 0.22]),
        cw, 0.56, 8,
    ))
    story.append(Spacer(1, 4))
    story.append(two_col(
        DonutChart(cw * 0.46, [
            (4, "Required / always"),
            (5, "Optional outbound"),
        ], "Network flows"),
        HBarChart(cw * 0.52, [
            ("Inbound (users via proxy)", 1, 6),
            ("Internal (DB / Redis)", 2, 6),
            ("Outbound HTTPS", 6, 6),
        ], "Direction count", 78),
        cw, 0.46, 8,
    ))
    story.append(PageBreak())

    story.append(_p("RBAC  ·  BOUNDARIES  ·  HUMAN APPROVAL", st["kicker"]))
    story.append(matrix_table(st, ["Role", "Tickets", "Assistant writes", "Admin"], [
        ["Field / user", "Own raised / assigned", "Ticket draft if flagged; leave draft", "—"],
        ["Supervisor", "Roster / email drafts", "Per flags", "—"],
        ["Operations manager", "As configured", "Per flags", "—"],
        ["Procurement", "As flagged", "No commercial tool", "—"],
        ["HR / HR manager", "—", "Own leave draft", "HR tools"],
        ["General manager", "As configured", "Per flags", "—"],
        ["Administrator", "All", "Allowed tools + profile lookup", "Yes"],
    ], [cw * 0.22, cw * 0.28, cw * 0.34, cw * 0.16]))
    story.append(Spacer(1, 4))
    story.append(two_col(
        matrix_table(st, ["Never requested", "Never accessed"], [
            ["Microsoft Global Admin / Graph", "Full Google Drive or Gmail"],
            ["Mail.Send", "WhatsApp"],
            ["Sites.Read.All", "Payroll / bank files"],
            ["Unrestricted DB chat", "Automatic client-portal submit"],
        ], [cw * 0.50 * 0.50, cw * 0.50 * 0.50]),
        matrix_table(st, ["Human gate", "Rule"], [
            ["Chat ticket", "Draft after Confirm, then supervisor workflow"],
            ["Leave from chat", "Draft only until HR form is signed"],
            ["Email intake", "Stays draft until supervisor converts"],
            ["Drive", "User consents; IT can set GOOGLE_DRIVE_ENABLED=false"],
            ["Application mail", "Server-side reset / workflow / MMR only"],
        ], [cw * 0.48 * 0.32, cw * 0.48 * 0.68]),
        cw, 0.50, 8,
    ))
    story.append(Spacer(1, 4))
    story.append(_p(
        "Ticket ACL: access_ticketing does not mean every ticket. Visibility is reporter, assignee, technician, supervisor, or supervised project. "
        "Review with Architecture Deck and IT Clarification Answer Matrix.",
        st["caption"],
    ))

    doc.build(story, canvasmaker=_canvas_maker(page, "Kynvera · Agent Connectivity"))
    print("  wrote", path)


def main():
    os.makedirs(DOCS, exist_ok=True)
    print("SVG artifacts")
    write_svgs()
    print("PDFs")
    build_architecture(os.path.join(DOCS, "Architecture_Deck.pdf"))
    build_it_matrix(os.path.join(DOCS, "IT_Clarification_Answer_Matrix.pdf"))
    build_connectivity(os.path.join(DOCS, "Agent_Connectivity_Permissions_Attributes.pdf"))
    print("done")


if __name__ == "__main__":
    main()
