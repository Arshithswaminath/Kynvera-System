#!/usr/bin/env python3
"""
Export key markdown docs in /docs to PDF.
Run from project root: python scripts/export_docs_to_pdf.py
"""
import os
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")


FILES_TO_EXPORT = [
    "PROJECT_SCOPE_METHODS_AND_TECHNIQUES.md",
    "APPLICATION_OVERVIEW.md",
]


def _clean_inline_md(text: str) -> str:
    # Links: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Inline code: `x` -> x
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Bold/italic markers
    text = text.replace("**", "").replace("__", "").replace("*", "")
    # Escape XML-sensitive chars for Paragraph
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text


def export_markdown_to_pdf(md_path: str, pdf_path: str) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1a365d"),
        spaceAfter=14,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=colors.HexColor("#2c5282"),
        spaceBefore=10,
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#2d3748"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=16,
        bulletIndent=6,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#718096"),
        alignment=TA_CENTER,
        spaceBefore=10,
    )

    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )

    story = []
    first_h1_done = False
    in_fence = False

    for line in lines:
        raw = line.rstrip()
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            story.append(Paragraph(_clean_inline_md(raw), body_style))
            continue

        stripped = raw.strip()
        if not stripped:
            story.append(Spacer(1, 0.12 * cm))
            continue
        if stripped == "---":
            story.append(Spacer(1, 0.2 * cm))
            continue
        if stripped.startswith("|"):
            # Keep markdown table rows as readable text lines in PDF.
            story.append(Paragraph(_clean_inline_md(stripped), body_style))
            continue
        if stripped.startswith("# "):
            txt = _clean_inline_md(stripped[2:].strip())
            story.append(Paragraph(txt, title_style))
            first_h1_done = True
            continue
        if stripped.startswith("## "):
            txt = _clean_inline_md(stripped[3:].strip())
            story.append(Paragraph(txt, h1_style if first_h1_done else title_style))
            first_h1_done = True
            continue
        if stripped.startswith("### "):
            txt = _clean_inline_md(stripped[4:].strip())
            story.append(Paragraph(txt, h2_style))
            continue
        if stripped.startswith("- "):
            txt = _clean_inline_md(stripped[2:].strip())
            story.append(Paragraph(txt, bullet_style, bulletText="•"))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            txt = _clean_inline_md(stripped)
            story.append(Paragraph(txt, body_style))
            continue

        story.append(Paragraph(_clean_inline_md(stripped), body_style))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph(f"Generated from markdown on {generated}", meta_style))

    doc.build(story)


def main() -> None:
    for name in FILES_TO_EXPORT:
        md_path = os.path.join(DOCS_DIR, name)
        if not os.path.exists(md_path):
            print(f"[SKIP] missing {md_path}")
            continue
        pdf_name = os.path.splitext(name)[0] + ".pdf"
        pdf_path = os.path.join(DOCS_DIR, pdf_name)
        export_markdown_to_pdf(md_path, pdf_path)
        print(f"[OK] {pdf_path}")


if __name__ == "__main__":
    main()
