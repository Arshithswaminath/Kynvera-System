"""Generate the Kynvera brand kit PDF (logos + colour codes)."""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from common import kynvera_brand as kv

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

PRIMARY = colors.HexColor(kv.BRAND)
PRIMARY_DARK = colors.HexColor(kv.BRAND_DARK)
TEXT_MID = colors.HexColor(kv.CHROME["text_mid"])
TEXT_MUTED = colors.HexColor(kv.CHROME["text_muted"])
HAIRLINE = colors.HexColor(kv.CHROME["hairline"])
WHITE = colors.white
INK = colors.HexColor(kv.CHROME["text"])


def _hex(c) -> colors.Color:
    return colors.HexColor(c) if isinstance(c, str) else c


def _fitted(path: str, max_w: float, max_h: float) -> tuple[float, float]:
    try:
        iw, ih = ImageReader(path).getSize()
        if iw <= 0 or ih <= 0:
            return max_w, max_h
        scale = min(max_w / iw, max_h / ih)
        return iw * scale, ih * scale
    except Exception:
        return max_w, max_h


def _draw_image(c: Canvas, path: str, x: float, y: float, max_w: float, max_h: float, *, center=False):
    w, h = _fitted(path, max_w, max_h)
    dx = x + ((max_w - w) / 2 if center else 0)
    dy = y + ((max_h - h) / 2 if center else 0)
    c.drawImage(path, dx, dy, width=w, height=h, preserveAspectRatio=True, mask="auto")
    return w, h


def _footer(c: Canvas, page: int, total: int, title: str):
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.5)
    c.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(TEXT_MUTED)
    c.drawString(MARGIN, 7.5 * mm, kv.FOOTER_CONFIDENTIAL)
    c.drawCentredString(PAGE_W / 2, 7.5 * mm, title)
    c.drawRightString(PAGE_W - MARGIN, 7.5 * mm, f"{page} / {total}")


def _header(c: Canvas, kicker: str, title: str):
    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H - 2.4, PAGE_W, 2.4, fill=1, stroke=0)
    wordmark = kv.get_logo("wordmark")
    if wordmark and wordmark.exists:
        _draw_image(
            c,
            wordmark.abs_path,
            MARGIN,
            PAGE_H - 18 * mm,
            42 * mm,
            8 * mm,
        )
    else:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(PRIMARY)
        c.drawString(MARGIN, PAGE_H - 15 * mm, kv.COMPANY_NAME)
    c.setFont("Helvetica", 8)
    c.setFillColor(TEXT_MUTED)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 12.5 * mm, kicker)
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(INK)
    c.drawString(MARGIN, PAGE_H - 28 * mm, title)
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.6)
    c.line(MARGIN, PAGE_H - 31 * mm, PAGE_W - MARGIN, PAGE_H - 31 * mm)


def _round_card(c: Canvas, x, y, w, h, *, fill=WHITE, stroke=HAIRLINE, radius=6):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def _draw_cover(c: Canvas):
    c.setFillColor(WHITE)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    band_h = 96 * mm
    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H - band_h, PAGE_W, band_h, fill=1, stroke=0)
    c.setFillColor(PRIMARY_DARK)
    c.rect(0, PAGE_H - band_h - 2 * mm, PAGE_W, 2 * mm, fill=1, stroke=0)

    mark = kv.get_logo("mark")
    if mark and mark.exists:
        plate = 36 * mm
        px = (PAGE_W - plate) / 2
        py = PAGE_H - 54 * mm
        c.setFillColor(WHITE)
        c.roundRect(px, py, plate, plate, 8, fill=1, stroke=0)
        _draw_image(
            c, mark.abs_path, px + 4 * mm, py + 4 * mm,
            plate - 8 * mm, plate - 8 * mm, center=True,
        )

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 66 * mm, kv.COMPANY_NAME.upper())
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 80 * mm, "Brand kit")
    c.setFont("Helvetica", 10)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 88 * mm, "Logos and colour codes")

    y = PAGE_H - band_h - 18 * mm
    wordmark = kv.get_logo("wordmark")
    if wordmark and wordmark.exists:
        _draw_image(c, wordmark.abs_path, (PAGE_W - 72 * mm) / 2, y, 72 * mm, 14 * mm, center=True)
        y -= 8 * mm
    else:
        c.setFillColor(PRIMARY)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(PAGE_W / 2, y + 4 * mm, kv.COMPANY_NAME)
        y -= 6 * mm

    c.setFillColor(TEXT_MID)
    c.setFont("Helvetica", 11)
    c.drawCentredString(PAGE_W / 2, y, kv.TAGLINE)

    # Preview strip of logo types
    strip_y = 38 * mm
    cards = [
        ("App mark", kv.get_logo("mark"), WHITE, HAIRLINE),
        ("Wordmark", kv.get_logo("wordmark"), colors.HexColor(kv.CHROME["page"]), HAIRLINE),
        ("Reversed", kv.get_logo("reversed"), colors.HexColor("#191b23"), colors.HexColor("#191b23")),
    ]
    gap = 6 * mm
    card_w = (CONTENT_W - 2 * gap) / 3
    card_h = 42 * mm
    for i, (label, logo, fill, stroke) in enumerate(cards):
        x = MARGIN + i * (card_w + gap)
        _round_card(c, x, strip_y, card_w, card_h, fill=fill, stroke=stroke, radius=8)
        if logo and logo.exists:
            pad = 8 * mm
            _draw_image(
                c, logo.abs_path, x + pad, strip_y + 14 * mm,
                card_w - 2 * pad, card_h - 24 * mm, center=True,
            )
        c.setFont("Helvetica", 8)
        c.setFillColor(WHITE if fill == colors.HexColor("#191b23") else TEXT_MID)
        c.drawCentredString(x + card_w / 2, strip_y + 5 * mm, label)

    _footer(c, 1, 4, "Brand kit")


def _draw_logos(c: Canvas):
    c.setFillColor(WHITE)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    _header(c, "01  Logos", "Logo types")

    y = PAGE_H - 38 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(TEXT_MID)
    c.drawString(
        MARGIN,
        y,
        "Use the mark in-app. Use the wordmark on documents and About. Do not recolor outside coral or white.",
    )

    specimens = [
        kv.get_logo("mark"),
        kv.get_logo("wordmark"),
        kv.get_logo("reversed"),
    ]
    gap = 6 * mm
    card_w = (CONTENT_W - 2 * gap) / 3
    card_h = 62 * mm
    card_y = y - 10 * mm - card_h
    for i, logo in enumerate(specimens):
        if not logo:
            continue
        x = MARGIN + i * (card_w + gap)
        bg = colors.HexColor("#191b23") if logo.kind == "reversed" else colors.HexColor(kv.CHROME["page"])
        stroke = colors.HexColor("#191b23") if logo.kind == "reversed" else HAIRLINE
        _round_card(c, x, card_y, card_w, card_h, fill=bg, stroke=stroke, radius=8)
        if logo.exists:
            _draw_image(
                c, logo.abs_path, x + 8 * mm, card_y + 22 * mm,
                card_w - 16 * mm, 32 * mm, center=True,
            )
        label_color = WHITE if logo.kind == "reversed" else INK
        muted = colors.HexColor("#c4c4c8") if logo.kind == "reversed" else TEXT_MUTED
        c.setFillColor(label_color)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 6 * mm, card_y + 12 * mm, logo.label)
        c.setFillColor(muted)
        c.setFont("Helvetica", 7)
        c.drawString(x + 6 * mm, card_y + 5.5 * mm, logo.files_filename)

    # Usage notes
    note_y = card_y - 8 * mm
    for i, logo in enumerate(specimens):
        if not logo:
            continue
        x = MARGIN + i * (card_w + gap)
        c.setFillColor(TEXT_MID)
        c.setFont("Helvetica", 8)
        text = logo.use
        # wrap
        words = text.split()
        line = ""
        ly = note_y
        for word in words:
            trial = (line + " " + word).strip()
            if c.stringWidth(trial, "Helvetica", 8) > card_w:
                c.drawString(x, ly, line)
                ly -= 3.4 * mm
                line = word
            else:
                line = trial
        if line:
            c.drawString(x, ly, line)

    # Size row
    sizes = [kv.get_logo(k) for k in ("mark-32", "mark-48", "mark-96", "mark-180")]
    sizes = [s for s in sizes if s]
    band_h = 48 * mm
    band_y = 22 * mm
    _round_card(c, MARGIN, band_y, CONTENT_W, band_h, fill=colors.HexColor(kv.CHROME["page"]), radius=8)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN + 6 * mm, band_y + band_h - 8 * mm, "App mark sizes")
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN + 6 * mm, band_y + band_h - 13 * mm, "Favicon and nav scales — keep the coral tile intact.")

    slot_w = CONTENT_W / max(len(sizes), 1)
    for i, logo in enumerate(sizes):
        x = MARGIN + i * slot_w
        if logo.exists:
            max_side = {"mark-32": 32, "mark-48": 48, "mark-96": 56, "mark-180": 64}.get(logo.key, 48)
            # points ≈ pixels at 72dpi; bump a little for print
            side = max_side * 0.85
            _draw_image(
                c, logo.abs_path,
                x + (slot_w - side) / 2,
                band_y + 14 * mm,
                side, side, center=True,
            )
        c.setFillColor(TEXT_MID)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + slot_w / 2, band_y + 6 * mm, logo.label)

    _footer(c, 2, 4, "Logos")


def _swatch(c: Canvas, x, y, w, h, hex_code: str, name: str, token: str):
    _round_card(c, x, y, w, h, fill=WHITE, radius=6)
    c.setFillColor(_hex(hex_code))
    c.roundRect(x, y + 18 * mm, w, h - 18 * mm, 6, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.rect(x, y + 18 * mm, w, 6, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 3.5 * mm, y + 11.5 * mm, name)
    c.setFillColor(TEXT_MID)
    c.setFont("Helvetica", 8)
    c.drawString(x + 3.5 * mm, y + 6.8 * mm, hex_code.upper())
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawString(x + 3.5 * mm, y + 2.8 * mm, token)


def _draw_brand_colors(c: Canvas):
    c.setFillColor(WHITE)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    _header(c, "02  Colour", "Brand coral")

    y = PAGE_H - 40 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(TEXT_MID)
    c.drawString(MARGIN, y, "Coral is the only loud colour. Neutrals carry the UI; coral means action or brand.")

    # Primary tokens — 4 large
    primaries = kv.COLOR_SWATCHES[:4]
    gap = 5 * mm
    card_w = (CONTENT_W - 3 * gap) / 4
    card_h = 42 * mm
    y = y - 8 * mm - card_h
    for i, (name, hex_code, token) in enumerate(primaries):
        x = MARGIN + i * (card_w + gap)
        _swatch(c, x, y, card_w, card_h, hex_code, name, token.split("·")[0].strip())
        c.setFillColor(TEXT_MUTED)
        c.setFont("Courier", 7)
        c.drawRightString(x + card_w - 3 * mm, y + 6.8 * mm, kv.rgb_label(hex_code))

    # Full coral scale
    y -= 16 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Coral scale")
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 8)
    c.drawRightString(PAGE_W - MARGIN, y, "--color-primary-50  →  950")

    y -= 6 * mm
    steps = list(kv.CORAL.items())
    sw_h = 28 * mm
    sw_w = CONTENT_W / len(steps)
    for i, (step, hex_code) in enumerate(steps):
        x = MARGIN + i * sw_w
        c.setFillColor(_hex(hex_code))
        c.rect(x, y - sw_h, sw_w, sw_h, fill=1, stroke=0)
        label_color = WHITE if int(step) >= 400 else INK
        c.setFillColor(label_color)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + sw_w / 2, y - 8 * mm, step)
        c.setFont("Helvetica", 6.2)
        c.drawCentredString(x + sw_w / 2, y - 13 * mm, hex_code.upper())

    y = y - sw_h - 16 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "How to use")
    y -= 7 * mm
    rules = (
        ("Do", "Keep coral for CTAs, focus rings, progress, and the logo. Surfaces stay cool and neutral."),
        ("Don't", "Don't introduce a second accent (purple, green chrome, competing orange) in core UI."),
        ("Print / Excel", "Headers use #FF8E68. Body text #191B23. Hairlines #E9EAEE. White type on coral bars."),
        ("Contrast", "White labels on solid coral. Dark ink on wash (#FFF4EF) and white surfaces."),
    )
    for title, body in rules:
        c.setFillColor(PRIMARY_DARK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN, y, title)
        c.setFillColor(TEXT_MID)
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN + 22 * mm, y, body)
        y -= 7 * mm

    _footer(c, 3, 4, "Colour")


def _draw_system_colors(c: Canvas):
    c.setFillColor(WHITE)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    _header(c, "03  Colour", "Neutrals, chrome, semantic")

    y = PAGE_H - 40 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(TEXT_MID)
    c.drawString(MARGIN, y, "Copy these hex codes. Tokens match static/css/design-tokens.css.")

    # Neutral scale
    y -= 10 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Neutral scale")
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 8)
    c.drawRightString(PAGE_W - MARGIN, y, "--color-neutral-0  →  950")

    y -= 6 * mm
    steps = list(kv.NEUTRAL.items())
    sw_h = 26 * mm
    sw_w = CONTENT_W / len(steps)
    for i, (step, hex_code) in enumerate(steps):
        x = MARGIN + i * sw_w
        c.setFillColor(_hex(hex_code))
        c.setStrokeColor(HAIRLINE)
        c.setLineWidth(0.4)
        c.rect(x, y - sw_h, sw_w, sw_h, fill=1, stroke=1)
        label_color = WHITE if int(step) >= 500 else INK
        c.setFillColor(label_color)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(x + sw_w / 2, y - 8 * mm, step)
        c.setFont("Helvetica", 5.8)
        c.drawCentredString(x + sw_w / 2, y - 12.5 * mm, hex_code.upper())

    # Chrome + remaining tokens as a table of swatches
    rest = kv.COLOR_SWATCHES[4:]
    y = y - sw_h - 16 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "App chrome & semantic")

    cols = 5
    gap = 4.5 * mm
    card_w = (CONTENT_W - (cols - 1) * gap) / cols
    card_h = 36 * mm
    y -= 6 * mm + card_h
    for i, (name, hex_code, token) in enumerate(rest):
        col = i % cols
        row = i // cols
        x = MARGIN + col * (card_w + gap)
        cy = y - row * (card_h + 5 * mm)
        _swatch(c, x, cy, card_w, card_h, hex_code, name, token.split("·")[0].strip())

    _footer(c, 4, 4, "Colour")


def build_brand_kit_pdf() -> bytes:
    """Return the brand kit PDF bytes (logos + colour codes)."""
    buf = BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(f"{kv.COMPANY_NAME} Brand Kit")
    c.setAuthor(kv.PDF_AUTHOR)
    c.setSubject("Logos and colour codes")
    _draw_cover(c)
    c.showPage()
    _draw_logos(c)
    c.showPage()
    _draw_brand_colors(c)
    c.showPage()
    _draw_system_colors(c)
    c.save()
    return buf.getvalue()
