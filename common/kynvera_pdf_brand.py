"""
Shared Kynvera branding for ReportLab PDFs.

Colors and naming match docs/KYNVERA_DESIGN.md / design-tokens.css.
The wordmark image is the logo text; body copy uses Helvetica.
"""
from __future__ import annotations

import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, inch, mm
from reportlab.platypus import Image, Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.utils import ImageReader

from common.kynvera_brand import (
    COMPANY_NAME,
    COMPANY_NAME_UPPER,
    DEFAULT_REPORT_TITLE,
    FOOTER_CONFIDENTIAL,
    MARK_PATH,
    MARK_PATH_FALLBACK,
    PDF_AUTHOR,
    TAGLINE,
    WORDMARK_PATH,
    resolve_logo_path,
    BRAND,
    BRAND_DARK,
    BRAND_HOVER,
    BRAND_WASH,
    CHROME,
)

logger = logging.getLogger(__name__)

# ── Colors (coral + neutrals) — common.kynvera_brand ─────────────────────────
PRIMARY = colors.HexColor(BRAND)
PRIMARY_DARK = colors.HexColor(BRAND_DARK)
PRIMARY_LIGHT = colors.HexColor(BRAND_HOVER)
SOFT_WASH = colors.HexColor(BRAND_WASH)
TEXT_DARK = colors.HexColor(CHROME["text"])
TEXT_MID = colors.HexColor(CHROME["text_mid"])
TEXT_MUTED = colors.HexColor(CHROME["text_muted"])
HAIRLINE = colors.HexColor(CHROME["hairline"])
SURFACE_ALT = colors.HexColor(CHROME["well"])
WHITE = colors.white
BLACK = colors.black

# Backward-compatible aliases used by professional PDF helpers
PRIMARY_COLOR = PRIMARY
SECONDARY_COLOR = PRIMARY_DARK
ACCENT_COLOR = SOFT_WASH
HEADER_BG = SOFT_WASH
TABLE_HEADER_BG = SOFT_WASH
TABLE_ALT_ROW = SURFACE_ALT
BORDER_COLOR = HAIRLINE
LIGHT_BG = SURFACE_ALT

# Prefer wordmark for headers; mark for compact canvas slots
LOGO_PATH = resolve_logo_path(prefer_wordmark=True) or MARK_PATH_FALLBACK


def wordmark_flowable(max_width=1.55 * inch, max_height=0.38 * inch):
    """ReportLab Image for the Kynvera wordmark, or None."""
    path = resolve_logo_path(prefer_wordmark=True)
    if not path:
        return None
    try:
        return Image(path, width=max_width, height=max_height, kind="proportional")
    except Exception as exc:
        logger.warning("Could not load Kynvera wordmark: %s", exc)
        return None


def mark_flowable(size=0.55 * inch):
    """ReportLab Image for the compact mark, or None."""
    path = resolve_logo_path(prefer_wordmark=False)
    if not path:
        return None
    try:
        return Image(path, width=size, height=size, kind="proportional")
    except Exception as exc:
        logger.warning("Could not load Kynvera mark: %s", exc)
        return None


def logo_or_text_paragraph(align=TA_RIGHT, font_size=10):
    """Wordmark image, or bold KYNVERA text fallback."""
    img = wordmark_flowable()
    if img:
        return img
    return Paragraph(
        f"<b>{COMPANY_NAME_UPPER}</b>",
        ParagraphStyle(
            "KynveraLogoFallback",
            fontSize=font_size,
            textColor=PRIMARY_DARK,
            fontName="Helvetica-Bold",
            alignment=align,
        ),
    )


def _fitted_image_size(path, max_width, max_height):
    """Return (width, height) that fit inside max bounds, preserving aspect ratio."""
    try:
        iw, ih = ImageReader(path).getSize()
        if iw <= 0 or ih <= 0:
            return max_width, max_height
        scale = min(max_width / iw, max_height / ih)
        return iw * scale, ih * scale
    except Exception:
        return max_width, max_height


def draw_page_chrome(
    c,
    page_number: int,
    page_count: int,
    *,
    report_title: str = "",
    left_margin=1.4 * cm,
    right_margin=1.4 * cm,
    footer_left: str | None = None,
    show_wordmark: bool = True,
    header_title: str | None = None,
):
    """
    Light header (coral top rule + wordmark) and footer with page numbers.
    The wordmark already reads "Kynvera"; company-name text is only drawn when
    the logo is missing, or when header_title is a distinct document label.
    Call from a NumberedCanvas-style save() loop.
    """
    page_w, page_h = A4
    hdr_h = 1.42 * cm
    hdr_y = page_h - hdr_h
    text_y = hdr_y + (hdr_h / 2) - 0.11 * cm

    # White header band
    c.setFillColor(WHITE)
    c.rect(0, hdr_y, page_w, hdr_h, fill=1, stroke=0)

    # Coral top accent
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(2.2)
    c.line(0, page_h - 1, page_w, page_h - 1)

    logo_drawn = False
    drawn_w = 0
    if show_wordmark:
        path = resolve_logo_path(prefer_wordmark=True)
        if path:
            try:
                drawn_w, drawn_h = _fitted_image_size(path, 3.4 * cm, 0.82 * cm)
                c.drawImage(
                    path,
                    left_margin,
                    hdr_y + (hdr_h - drawn_h) / 2,
                    width=drawn_w,
                    height=drawn_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                logo_drawn = True
            except Exception as exc:
                logger.warning("Chrome wordmark draw failed: %s", exc)

    label = (header_title or "").strip()
    if logo_drawn and (not label or label.lower() == COMPANY_NAME.lower()):
        label = None
    elif not logo_drawn:
        label = label or COMPANY_NAME

    if label:
        name_x = left_margin + (drawn_w + 0.28 * cm if logo_drawn else 0)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(TEXT_DARK)
        c.drawString(name_x, text_y, label)

    if report_title:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(TEXT_MUTED)
        c.drawRightString(page_w - right_margin, text_y, report_title)

    # Hairline under header
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.5)
    c.line(left_margin, hdr_y, page_w - right_margin, hdr_y)

    # Footer
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.5)
    c.line(left_margin, 1.25 * cm, page_w - right_margin, 1.25 * cm)

    c.setFont("Helvetica", 7)
    c.setFillColor(TEXT_MUTED)
    left = footer_left if footer_left is not None else FOOTER_CONFIDENTIAL
    c.drawString(left_margin, 0.85 * cm, left)
    c.drawRightString(
        page_w - right_margin,
        0.85 * cm,
        f"Page {page_number} of {page_count}",
    )


def draw_simple_footer(
    c,
    page_number: int,
    page_count: int,
    *,
    left_margin=1.4 * cm,
    right_margin=1.4 * cm,
    footer_left: str | None = None,
):
    """Minimal footer only (for builders that put branding in the story)."""
    page_w, _ = A4
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.5)
    c.line(left_margin, 1.25 * cm, page_w - right_margin, 1.25 * cm)
    c.setFont("Helvetica", 7)
    c.setFillColor(TEXT_MUTED)
    c.drawString(left_margin, 0.85 * cm, footer_left or FOOTER_CONFIDENTIAL)
    c.drawRightString(
        page_w - right_margin,
        0.85 * cm,
        f"Page {page_number} of {page_count}",
    )


def draw_top_accent(c, thickness=2.0):
    """Full-bleed coral rule at the top of the page."""
    page_w, page_h = A4
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(thickness)
    c.line(0, page_h - 1, page_w, page_h - 1)


def story_header_block(title: str, subtitle: str | None = None, content_width=None):
    """
    Story-level header: title left, wordmark right.
    Returns a Table flowable.
    """
    cw = content_width or (A4[0] - 2.8 * cm)
    title_style = ParagraphStyle(
        "KynStoryTitle",
        fontSize=14,
        textColor=TEXT_DARK,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
        spaceAfter=0,
        leading=18,
    )
    sub_style = ParagraphStyle(
        "KynStorySub",
        fontSize=8,
        textColor=TEXT_MID,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    rows = []
    if subtitle:
        rows.append([Paragraph(subtitle, sub_style)])
    rows.append([Paragraph(title, title_style)])
    title_block = Table(rows, colWidths=[cw * 0.68])
    title_block.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    logo = logo_or_text_paragraph()
    t = Table([[title_block, logo]], colWidths=[cw * 0.68, cw * 0.32])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, PRIMARY),
            ]
        )
    )
    return t


def meta_table_style():
    """Shared TableStyle rules for clean key/value meta grids."""
    return [
        ("BACKGROUND", (0, 0), (0, -1), SOFT_WASH),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_DARK),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, HAIRLINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [WHITE, SURFACE_ALT]),
    ]


def data_header_table_style():
    """Header row with soft wash (not solid green/navy)."""
    return [
        ("BACKGROUND", (0, 0), (-1, 0), SOFT_WASH),
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT_DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.4, HAIRLINE),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]


def generated_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
