#!/usr/bin/env python3
"""
Generate docs/Injaaz_Project_Overview.pdf — executive-style project summary.
Run from project root: python scripts/generate_project_overview_pdf.py
"""
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
)


def _p(text, style):
    return Paragraph(text.replace("&", "&amp;"), style)


def build_pdf(path: str) -> None:
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Injaaz App — Project Overview",
        author="Injaaz",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=22,
        spaceAfter=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1a365d"),
    )
    subtitle = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontSize=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4a5568"),
        spaceAfter=24,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=14,
        spaceBefore=18,
        spaceAfter=10,
        textColor=colors.HexColor("#2c5282"),
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#2d3748"),
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    bullet = ParagraphStyle(
        "Bullet",
        parent=body,
        leftIndent=18,
        bulletIndent=8,
    )
    footer_note = ParagraphStyle(
        "FootNote",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#718096"),
        alignment=TA_CENTER,
    )

    generated = datetime.now().strftime("%d %B %Y")
    story = []

    story.append(_p("Injaaz App", title))
    story.append(
        _p(
            "Facilities & operations platform — architecture and modules<br/>"
            f"<i>Generated {generated}</i>",
            subtitle,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    story.append(_p("1. Purpose", h1))
    story.append(
        _p(
            "Injaaz is a production-ready Flask application for facilities and operations: "
            "digital site-visit and inspection forms, multi-stage review workflows, "
            "reporting, document generation (including HR forms as PDF and DOCX), and "
            "centralized administration. The codebase is organized as a <b>modular monolith</b>—"
            "one deployable app with feature blueprints sharing authentication, database, and services.",
            body,
        )
    )

    story.append(_p("2. Technical foundation", h1))
    tech_data = [
        ["Area", "Technology"],
        ["Runtime", "Python, Flask"],
        ["API auth", "JWT (Flask-JWT-Extended)"],
        ["Database", "SQLAlchemy; SQLite (dev), PostgreSQL (production)"],
        ["Frontend", "HTML, CSS, JavaScript; PWA assets; Capacitor for mobile shells"],
        ["Files / media", "Local uploads; Cloudinary in production where configured"],
        ["Email", "Mailjet (e.g. MMR scheduled reports)"],
        ["Production", "wsgi.py; documented for Render and similar hosts"],
    ]
    t = Table(tech_data, colWidths=[4.2 * cm, 12.3 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7fafc"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))

    story.append(_p("3. Core platform", h1))
    for line in [
        "Authentication (<b>/api/auth</b>) — login, registration, access and refresh tokens.",
        "Dashboard and main UI — gated by role and module permissions.",
        "Admin (<b>/api/admin</b>) — users, access flags, device and operational admin tools.",
        "Workflow (<b>/api/workflow</b>) — submission pipelines, pending reviews, history.",
        "Reports API (<b>/api/reports</b>) — on-demand reporting where implemented.",
    ]:
        story.append(Paragraph(line, bullet, bulletText="•"))

    story.append(PageBreak())

    story.append(_p("4. Operational modules", h1))
    mod_data = [
        ["Module", "Typical URL", "Role"],
        ["HVAC / MEP", "/hvac-mep", "HVAC & MEP forms, generators, reporting"],
        ["Civil", "/civil", "Civil works forms and reports"],
        ["Cleaning", "/cleaning", "Cleaning services forms and reports"],
        ["Inspection", "/inspection", "Cross-trade inspection workflows"],
        ["HR", "/hr", "HR forms, HR→GM approval, PDF/DOCX output"],
        ["Procurement", "/procurement", "Procurement workflows"],
        ["MMR", "/admin/mmr", "CAFM analytics, Excel reports, scheduled email (Dubai TZ)"],
        ["Business Development", "/bd, /admin/bd", "BD flows and admin entry"],
        ["DocHub", "/api/docs, /dochub", "Authorized document hub"],
    ]
    mt = Table(mod_data, colWidths=[3.2 * cm, 3.8 * cm, 9.5 * cm])
    mt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7fafc"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(mt)
    story.append(Spacer(1, 0.5 * cm))

    story.append(_p("5. How the pieces fit together", h1))
    story.append(
        _p(
            "Users authenticate and open the dashboard; permissions control admin, workflow, and "
            "module routes. Field modules capture structured data and attachments. Workflow advances "
            "records through supervisors and reviewers. HR submissions follow <b>employee submit → "
            "HR review and sign → General Manager final approval</b>, with printable HTML and "
            "downloadable PDF/DOCX. MMR ingests CAFM exports and applies business rules for "
            "chargeable analysis. Configuration is centralized in <b>config.py</b> and environment "
            "variables (database, Redis, secrets, mail, schedules).",
            body,
        )
    )

    story.append(_p("6. Repository documentation", h1))
    story.append(
        _p(
            "For setup and deployment: <b>README.md</b>, <b>SETUP.md</b>, <b>QUICK_START.md</b>. "
            "For structure and flows: <b>PROJECT_STRUCTURE.md</b>, <b>PROJECT_FLOW.md</b>. "
            "For architecture detail: <b>docs/APPLICATION_OVERVIEW.md</b>. "
            "Production notes: <b>CLOUD_ONLY_SETUP.md</b>, <b>RENDER_DEPLOYMENT_PHASES.md</b>.",
            body,
        )
    )

    story.append(Spacer(1, 1 * cm))
    story.append(
        _p(
            "This PDF is generated by <b>scripts/generate_project_overview_pdf.py</b> and summarizes "
            "the Injaaz application for stakeholders and onboarding. Update the script when major "
            "modules or URLs change.",
            footer_note,
        )
    )

    doc.build(story)


def main():
    out_dir = os.path.join(PROJECT_ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "Injaaz_Project_Overview.pdf")
    build_pdf(out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
