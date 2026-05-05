#!/usr/bin/env python3
"""
Generate docs/Injaaz_Comprehensive_Documentation.pdf
A fully narrative, stakeholder-ready project document.
Run from project root: python scripts/generate_comprehensive_doc.py
"""
import os, sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, NextPageTemplate,
    Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
    KeepTogether,
)

# ── Colours ────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1a365d")
BLUE   = colors.HexColor("#2c5282")
TEAL   = colors.HexColor("#2b6cb0")
LGREY  = colors.HexColor("#f7fafc")
MGREY  = colors.HexColor("#e2e8f0")
DGREY  = colors.HexColor("#4a5568")
BLACK  = colors.HexColor("#1a202c")
WHITE  = colors.white
GOLD   = colors.HexColor("#d69e2e")

W, H = A4


# ── Page callbacks ─────────────────────────────────────────────────────────
def _cover_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, H * 0.38, W, H * 0.62, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, H * 0.37, W, 4, fill=1, stroke=0)
    canvas.restoreState()


def _body_page(canvas, doc):
    canvas.saveState()
    # Left accent bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, 6, H, fill=1, stroke=0)
    # Header band
    canvas.setFillColor(LGREY)
    canvas.rect(6, H - 1.4 * cm, W - 6, 1.4 * cm, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(1.5 * cm, H - 0.85 * cm, "INJAAZ")
    canvas.setFillColor(DGREY)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 1.5 * cm, H - 0.85 * cm,
                           "Project Documentation — April 2026")
    # Footer
    canvas.setFillColor(MGREY)
    canvas.rect(6, 0, W - 6, 1.2 * cm, fill=1, stroke=0)
    canvas.setFillColor(DGREY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.5 * cm, 0.45 * cm, "Injaaz Facilities & Operations Platform")
    canvas.drawRightString(W - 1.5 * cm, 0.45 * cm, f"Page {doc.page}")
    canvas.restoreState()


# ── Style factory ──────────────────────────────────────────────────────────
def _styles():
    def ps(name, **kw):
        return ParagraphStyle(name, **kw)

    return dict(
        cover_title=ps("CovTitle", fontSize=34, fontName="Helvetica-Bold",
                        textColor=WHITE, alignment=TA_LEFT, leading=42, spaceAfter=10),
        cover_sub=ps("CovSub", fontSize=15, fontName="Helvetica",
                      textColor=colors.HexColor("#bee3f8"), alignment=TA_LEFT, leading=22),
        cover_meta=ps("CovMeta", fontSize=10, fontName="Helvetica",
                       textColor=colors.HexColor("#90cdf4"), alignment=TA_LEFT, spaceAfter=4),
        section_num=ps("SecNum", fontSize=10, fontName="Helvetica-Bold",
                        textColor=GOLD, spaceBefore=0, spaceAfter=2),
        h1=ps("H1", fontSize=17, fontName="Helvetica-Bold",
               textColor=NAVY, spaceBefore=2, spaceAfter=8, leading=22),
        h2=ps("H2", fontSize=12, fontName="Helvetica-Bold",
               textColor=BLUE, spaceBefore=14, spaceAfter=6, leading=16),
        h3=ps("H3", fontSize=10, fontName="Helvetica-Bold",
               textColor=TEAL, spaceBefore=10, spaceAfter=4),
        body=ps("Body", fontSize=10, fontName="Helvetica",
                 textColor=BLACK, leading=15, alignment=TA_JUSTIFY, spaceAfter=6),
        bullet=ps("Bul", fontSize=10, fontName="Helvetica",
                   textColor=BLACK, leading=15, leftIndent=18, bulletIndent=6,
                   spaceAfter=4),
        small=ps("Small", fontSize=8.5, fontName="Helvetica",
                  textColor=DGREY, leading=12, spaceAfter=4),
        toc_entry=ps("TOC", fontSize=10, fontName="Helvetica",
                      textColor=BLACK, leading=16, spaceAfter=2, leftIndent=6),
        toc_h=ps("TOCH", fontSize=11, fontName="Helvetica-Bold",
                  textColor=NAVY, leading=18, spaceAfter=4),
        callout=ps("Call", fontSize=10, fontName="Helvetica-Oblique",
                    textColor=NAVY, leading=15, leftIndent=12, rightIndent=12,
                    spaceAfter=8, spaceBefore=4),
    )


def _rule():
    return HRFlowable(width="100%", thickness=0.6, color=MGREY, spaceAfter=8, spaceBefore=2)


def _section_hdr(num, title, s):
    return KeepTogether([
        Paragraph(num, s["section_num"]),
        Paragraph(title, s["h1"]),
        _rule(),
    ])


def _table(data, col_widths, header_bg=NAVY, stripe=LGREY):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND",   (0, 0), (-1, 0),  header_bg),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [stripe, WHITE]),
        ("GRID",         (0, 0), (-1, -1), 0.5, MGREY),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]
    t.setStyle(TableStyle(style))
    return t


def _bp(text, s):
    return Paragraph(text, s["bullet"], bulletText="•")


def _callout(text, s):
    tbl = Table([[Paragraph(text, s["callout"])]], colWidths=["100%"])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), colors.HexColor("#ebf8ff")),
        ("LINEAFTER",   (0, 0), (0, -1),  3, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0,0), (-1, -1), 8),
    ]))
    return tbl


# ── Build ──────────────────────────────────────────────────────────────────
def build(path: str):
    s = _styles()
    LM, RM, TM, BM = 1.8*cm, 1.8*cm, 2.0*cm, 1.8*cm

    cover_frame = Frame(0, 0, W, H, leftPadding=2.5*cm, rightPadding=2.5*cm,
                        topPadding=H*0.43, bottomPadding=2*cm, id="cover")
    body_frame  = Frame(LM + 4, BM + 1.4*cm, W - LM - RM - 4,
                        H - TM - BM - 2.8*cm, id="body")

    doc = BaseDocTemplate(
        path, pagesize=A4,
        title="Injaaz — Comprehensive Project Documentation",
        author="Injaaz Development Team",
    )
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=_cover_bg),
        PageTemplate(id="Body",  frames=[body_frame],  onPage=_body_page),
    ])

    story = []
    generated = datetime.now().strftime("%d %B %Y")

    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(NextPageTemplate("Cover"))
    story.append(Spacer(1, 1))

    story += [
        Paragraph("INJAAZ", s["cover_title"]),
        Paragraph("Facilities &amp; Operations Platform", s["cover_sub"]),
        Spacer(1, 0.6*cm),
        Paragraph("Comprehensive Project Documentation", s["cover_meta"]),
        Paragraph(f"Generated: {generated}", s["cover_meta"]),
        Paragraph("Version 1.0 — Confidential", s["cover_meta"]),
    ]

    # ── Switch to body layout ──────────────────────────────────────────────
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())

    # ── Table of contents ─────────────────────────────────────────────────
    story += [
        Paragraph("Table of Contents", s["h1"]),
        _rule(),
        Spacer(1, 0.2*cm),
    ]
    toc = [
        ("1", "Executive Summary"),
        ("2", "Platform Purpose and Goals"),
        ("3", "User Management and Access Control"),
        ("4", "Field Operations Modules"),
        ("5", "Human Resources (HR) Module"),
        ("6", "Approval Workflow Engine"),
        ("7", "Procurement Module"),
        ("8", "MMR — Reporting and Analytics"),
        ("9", "Business Development Module"),
        ("10", "Document Hub (DocHub)"),
        ("11", "Document Generation Capabilities"),
        ("12", "Notifications and Audit Trail"),
        ("13", "Mobile and Progressive Web App"),
        ("14", "Deployment and Infrastructure"),
        ("15", "Security Approach"),
        ("16", "Summary of Delivered Capabilities"),
    ]
    for num, title in toc:
        row = Table(
            [[Paragraph(f"{num}.", s["toc_entry"]),
              Paragraph(title, s["toc_entry"])]],
            colWidths=[1.0*cm, None],
        )
        row.setStyle(TableStyle([
            ("LEFTPADDING",  (0,0),(-1,-1), 4),
            ("RIGHTPADDING", (0,0),(-1,-1), 4),
            ("TOPPADDING",   (0,0),(-1,-1), 3),
            ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ]))
        story.append(row)
    story.append(PageBreak())

    # ── 1. Executive Summary ───────────────────────────────────────────────
    story.append(_section_hdr("1", "Executive Summary", s))
    story.append(Paragraph(
        "Injaaz is a comprehensive, cloud-ready web platform built to digitalise and "
        "streamline facilities and operations management. It replaces paper-based processes "
        "with structured digital workflows, covering everything from on-site inspections and "
        "maintenance forms to human resources administration, procurement tracking, and "
        "monthly maintenance reporting.",
        s["body"]))
    story.append(Paragraph(
        "The system is designed for use across multiple operational roles — field inspectors, "
        "HR officers, operations managers, the General Manager, and administrators — each "
        "accessing only the parts of the platform relevant to their responsibilities. "
        "Every form submission flows through a defined review and approval process, producing "
        "signed, downloadable PDF and Word documents as official records.",
        s["body"]))
    story.append(_callout(
        "Key achievement: A single, unified platform replaces multiple disconnected tools, "
        "providing real-time visibility, structured approvals, and automated document output "
        "across all operational areas.",
        s))
    story.append(Spacer(1, 0.3*cm))

    # ── 2. Platform Purpose ────────────────────────────────────────────────
    story.append(_section_hdr("2", "Platform Purpose and Goals", s))
    story.append(Paragraph(
        "The primary purpose of Injaaz is to give the facilities and operations team a single, "
        "reliable place to capture, review, approve, and store all operational records. "
        "The goals that shaped every design and development decision are:", s["body"]))
    for item in [
        "Replace paper forms with structured digital submissions that are timestamped, attributed to named users, and impossible to lose.",
        "Enforce approval chains automatically — no form can bypass the required reviewer stages.",
        "Produce professional, signed PDF and Word documents instantly upon completion, ready for distribution or filing.",
        "Give managers real-time visibility into pending tasks, form history, and team activity from any device.",
        "Support both office and mobile use; the platform works as a browser-based app and can be packaged as a native mobile application.",
        "Integrate with cloud infrastructure so the platform is available and scalable without on-premise servers.",
    ]:
        story.append(_bp(item, s))
    story.append(Spacer(1, 0.3*cm))

    # ── 3. User Management ────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("3", "User Management and Access Control", s))
    story.append(Paragraph(
        "Every person who uses Injaaz has a personal account. Accounts are created and managed "
        "by administrators through the Admin panel. The platform supports fine-grained "
        "control over what each user can see and do.", s["body"]))

    story.append(Paragraph("Roles", s["h2"]))
    role_data = [
        ["Role", "Description"],
        ["Administrator",
         "Full access to every module, all submissions, and all admin tools. "
         "Responsible for creating user accounts, setting permissions, and system configuration."],
        ["HR Officer / HR Manager",
         "Access to HR submission queues. Reviews submitted HR forms, adds the HR signature, "
         "and forwards approved requests to the General Manager."],
        ["General Manager",
         "Final approver for HR requests and other GM-level workflows. "
         "Reviews requests forwarded by HR and issues final approval or rejection."],
        ["Field Inspector / Operational User",
         "Submits forms in the modules they have been given access to. "
         "Can track the status of their own submissions."],
        ["Procurement / BD User",
         "Access to procurement and business development workflows as assigned by an administrator."],
    ]
    story.append(_table(role_data, [3.5*cm, 12*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Module-level permissions", s["h2"]))
    story.append(Paragraph(
        "In addition to roles, each user account carries individual on/off flags for each "
        "operational module: HVAC & MEP, Civil, Cleaning, HR, and Procurement. "
        "An administrator can grant a user access to one module without granting access to others. "
        "Administrator accounts automatically have access to every module.", s["body"]))

    story.append(Paragraph("Authentication and sessions", s["h2"]))
    story.append(Paragraph(
        "The platform uses JSON Web Tokens (JWT) for secure, stateless authentication. "
        "When a user logs in, they receive a short-lived access token (valid for one hour by "
        "default) and a longer-lived refresh token. Tokens are delivered both as HTTP-only "
        "cookies (for browser navigation) and in the response body (for API access). "
        "Every active session is recorded in the database; logging out immediately revokes "
        "the session so the token cannot be reused. Passwords are stored as bcrypt hashes — "
        "the original password is never stored anywhere.", s["body"]))

    # ── 4. Field Ops Modules ───────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("4", "Field Operations Modules", s))
    story.append(Paragraph(
        "Three core field modules handle the day-to-day operational paperwork for the "
        "technical teams. Each module follows the same overall pattern: a user opens the form, "
        "fills in the site details, uploads photos, draws or uploads their signature, and "
        "submits. The platform then generates a professional Excel and PDF report automatically "
        "in the background while the user sees a live progress indicator.", s["body"]))

    story.append(Paragraph("HVAC and MEP Module", s["h2"]))
    story.append(Paragraph(
        "Covers Heating, Ventilation, Air Conditioning, Mechanical, Electrical, and Plumbing "
        "site visits. Inspectors fill in checklist-style forms recording the condition of "
        "equipment and services at a site. Photographs are uploaded directly from a phone or "
        "tablet and are embedded in the generated PDF report alongside the completed checklist. "
        "Dropdown data for equipment types and common observations is pre-loaded so inspectors "
        "can complete forms quickly even on site.", s["body"]))

    story.append(Paragraph("Civil Works Module", s["h2"]))
    story.append(Paragraph(
        "Captures site visit data for civil engineering and construction tasks. The module "
        "supports structured recording of work carried out, observations, and photographic "
        "evidence. Reports follow the same generation pipeline as HVAC, producing both an "
        "Excel summary and a PDF with embedded photos.", s["body"]))

    story.append(Paragraph("Cleaning Module", s["h2"]))
    story.append(Paragraph(
        "Records cleaning services inspections, including location details, quality ratings, "
        "observations, and photos. Useful for verifying service-level compliance and "
        "producing evidence records for client reporting.", s["body"]))

    story.append(Paragraph("Inspection Module", s["h2"]))
    story.append(Paragraph(
        "A cross-trade inspection module that spans HVAC, Civil, and Cleaning workflows, "
        "allowing inspectors to record multi-discipline observations in a single visit form "
        "under the unified path. The module shares the same approval and reporting "
        "infrastructure as the individual trade modules.", s["body"]))

    story.append(Paragraph("How report generation works", s["h2"]))
    story.append(Paragraph(
        "When a form is submitted, the platform queues a background job immediately. "
        "The user is not kept waiting — they receive a job reference and can monitor the "
        "progress bar as the report is built. The background process generates an Excel "
        "workbook with the structured form data, then generates a PDF with professional "
        "layout, embedded photos, and the submitted signatures. Both files are uploaded to "
        "cloud storage and download links are presented to the user as soon as the job "
        "completes. On production deployments, file storage uses Cloudinary so documents "
        "are accessible from any device without relying on a specific server's disk.", s["body"]))

    # ── 5. HR Module ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("5", "Human Resources (HR) Module", s))
    story.append(Paragraph(
        "The HR module is one of the most feature-rich parts of the platform. It brings "
        "all human resources paperwork into a single digital system, eliminating printed "
        "forms, manual routing between offices, and paper signature chains.", s["body"]))

    story.append(Paragraph("Supported form types", s["h2"]))
    hr_forms = [
        ["Form", "Purpose"],
        ["Leave Application",     "Employee requests annual, sick, compassionate, study, or other leave types, with replacement details."],
        ["Commencement",          "Onboarding form recording a new employee's joining details, bank information, and reporting manager."],
        ["Duty Resumption",       "Records an employee's return to work after a period of leave."],
        ["Contract Renewal",      "Documents an evaluation and recommendation for renewing an employee's contract, with detailed rating categories."],
        ["Performance Evaluation","Structured scoring across multiple competency areas, with observations and development notes."],
        ["Staff Appraisal",       "Periodic staff appraisal recording ratings, strengths, improvement areas, and overall recommendation."],
        ["Passport Release",      "Requests the release of an employee's passport for personal travel or visa renewal."],
        ["Visa Renewal",          "Documents the visa renewal process and required approvals."],
        ["Grievance",             "Formal complaint submission with full details of the grievance and parties involved."],
        ["Interview Assessment",  "Structured assessment form for candidates in a hiring interview."],
        ["Station Clearance",     "Departure checklist covering equipment return, system access cancellation, and handover on final working day."],
    ]
    story.append(_table(hr_forms, [4*cm, 11.5*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Document output", s["h2"]))
    story.append(Paragraph(
        "Every HR form can be downloaded in two formats once it reaches the approved state. "
        "The Word document (DOCX) is built from a professionally designed template where "
        "field values and signature images are merged into the correct positions. "
        "The PDF is generated programmatically with a pixel-precise layout that mirrors "
        "the official form design — including all signature areas, section headers, "
        "checkboxes, and the Injaaz branding. Signatures captured during the workflow "
        "appear in the correct positions on both the DOCX and PDF outputs.", s["body"]))

    # ── 6. Approval Workflow ───────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("6", "Approval Workflow Engine", s))
    story.append(Paragraph(
        "Every HR submission moves through a defined sequence of stages. The system "
        "enforces the order — a General Manager cannot approve a request that has not "
        "yet been reviewed by HR, and HR cannot approve a request that has already been "
        "forwarded to the GM. This prevents accidental bypassing of the approval chain.", s["body"]))

    story.append(Paragraph("HR approval stages", s["h2"]))
    wf_data = [
        ["Stage", "Responsible party", "Actions available", "Next stage"],
        ["Pending HR Review", "HR Officer or HR Manager",
         "Review form details, add HR comments, draw or upload HR signature, fill HR-specific fields (e.g. leave balance)",
         "Forwards to GM — or Rejected"],
        ["Pending GM Approval", "General Manager or Administrator",
         "Review the full submission including HR comments and signature, add GM comments, add GM signature",
         "Approved — or Rejected"],
        ["Approved", "System record",
         "Available for PDF and DOCX download; visible in Approved Forms archive", "—"],
        ["Rejected", "System record",
         "Rejection reason recorded; submitter receives notification; form closed", "—"],
    ]
    story.append(_table(wf_data, [3*cm, 3.5*cm, 5*cm, 3.5*cm]))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Notifications", s["h2"]))
    story.append(Paragraph(
        "The platform sends in-app notifications automatically at each workflow transition. "
        "When an employee submits a form, all HR officers are notified. When HR approves and "
        "forwards, all General Manager-level users are notified. When the GM gives final "
        "approval, both the original employee and the HR reviewer who processed the request "
        "are notified. If a request is rejected at any stage, the submitter receives "
        "a notification with the reason for rejection.", s["body"]))

    story.append(Paragraph("Signatures in the workflow", s["h2"]))
    story.append(Paragraph(
        "Signatures are captured as drawn images directly in the browser or on a touchscreen "
        "device. Each approver draws or uploads their signature when they perform their "
        "approval action. These signature images are stored alongside the form data and "
        "are embedded in the correct positions when DOCX or PDF documents are generated. "
        "The result is a document that carries the actual, visible signatures of every "
        "party who participated in the approval process.", s["body"]))

    # ── 7. Procurement ────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("7", "Procurement Module", s))
    story.append(Paragraph(
        "The procurement module provides a structured digital workflow for procurement "
        "activities within the organisation. Users with procurement access can submit "
        "and manage procurement requests through the platform at the dedicated path, "
        "with role-based visibility ensuring that only authorised staff can view or act "
        "on procurement submissions. The module follows the same submission and "
        "workflow patterns as other parts of the platform, integrating with the central "
        "notifications and audit systems.", s["body"]))

    # ── 8. MMR ────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("8", "MMR — Reporting and Analytics", s))
    story.append(Paragraph(
        "MMR (Monthly Maintenance Report) is the platform's analytics and reporting centre. "
        "It is designed to process CAFM (Computer-Aided Facilities Management) data exports "
        "and turn them into formatted, distributable reports — automatically, on a schedule.", s["body"]))

    story.append(Paragraph("Data ingestion", s["h2"]))
    story.append(Paragraph(
        "Administrators upload a CAFM export file. The platform handles the complexity of "
        "real-world export formats, including cases where the file is technically an HTML "
        "table saved with an Excel extension — a common pattern in facilities management "
        "software. The data is parsed, structured, and stored for processing.", s["body"]))

    story.append(Paragraph("Analytics and chargeable rules", s["h2"]))
    story.append(Paragraph(
        "Once data is uploaded, the platform applies the organisation's configured chargeable "
        "and non-chargeable rules to categorise work orders. A dashboard presents summary "
        "statistics, breakdowns by category, and trend data. This gives management an "
        "immediate view of maintenance activity without needing to open a spreadsheet.", s["body"]))

    story.append(Paragraph("Report generation and distribution", s["h2"]))
    story.append(Paragraph(
        "Users can generate formatted Excel reports on demand, covering daily or monthly "
        "date ranges. Reports can be downloaded immediately, saved to a designated network "
        "folder, or sent by email. An optional automated schedule can be configured so "
        "that the platform generates and emails the report at a set time each day — "
        "by default using the Asia/Dubai timezone. The schedule, recipient list, "
        "and email subject can all be configured without touching the code, through the "
        "MMR settings interface.", s["body"]))

    story.append(Paragraph("Activity and cycle logging", s["h2"]))
    story.append(Paragraph(
        "Every upload, report generation, email send, and schedule run is recorded in an "
        "activity log with timestamps and the identity of the user or automated process "
        "that triggered the action. Cycle records track the progression from upload through "
        "approval to distribution for each reporting period.", s["body"]))

    # ── 9. BD ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("9", "Business Development Module", s))
    story.append(Paragraph(
        "The Business Development module provides dedicated screens and workflows for BD "
        "activities, accessible to users with appropriate permissions. It integrates with "
        "the central workflow engine so that BD submissions flow through the same review "
        "and approval framework as other parts of the platform. An admin entry point "
        "provides management-level visibility into BD activity.", s["body"]))

    # ── 10. DocHub ────────────────────────────────────────────────────────
    story.append(_section_hdr("10", "Document Hub (DocHub)", s))
    story.append(Paragraph(
        "DocHub is a centralised document repository within the platform. Authorised users "
        "can access, browse, and retrieve documents through the DocHub interface. "
        "The underlying API provides secure, authenticated document retrieval so that "
        "sensitive documents are never accessible to unauthenticated parties. "
        "DocHub complements the workflow-generated documents by providing a place for "
        "reference materials and shared documents alongside the operational records "
        "produced by the form modules.", s["body"]))

    # ── 11. Document Generation ───────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("11", "Document Generation Capabilities", s))
    story.append(Paragraph(
        "Producing professional, accurate documents is one of the core value propositions "
        "of the platform. The following output types are supported:", s["body"]))

    story.append(Paragraph("PDF generation", s["h2"]))
    story.append(Paragraph(
        "PDFs are built programmatically using the ReportLab library. Every element — "
        "tables, labels, checkboxes, section headers, borders, and signature images — is "
        "placed at an exact position on the page. The layout is carefully aligned to the "
        "official form designs so that a generated PDF is indistinguishable from one "
        "printed and signed by hand. Colour, typography, and spacing follow the "
        "established Injaaz brand standards.", s["body"]))

    story.append(Paragraph("Word document (DOCX) generation", s["h2"]))
    story.append(Paragraph(
        "Word documents are produced by merging live data into professionally designed "
        "template files. Each HR form has a corresponding template where placeholder "
        "tags mark every variable field. When the document is generated, the platform "
        "replaces the placeholders with the actual submitted values and inserts "
        "signature images into the correct cells. The resulting DOCX file is fully "
        "editable if a recipient needs to make minor adjustments.", s["body"]))

    story.append(Paragraph("Excel reports", s["h2"]))
    story.append(Paragraph(
        "Excel files are produced using multiple libraries depending on the module's needs — "
        "openpyxl for feature-rich workbooks and XlsxWriter for performance-optimised "
        "output. Reports include structured data tables, summary rows, and formatted "
        "headers consistent with the organisation's reporting standards.", s["body"]))

    story.append(Paragraph("Print and HTML view", s["h2"]))
    story.append(Paragraph(
        "In addition to downloadable files, every HR form can be viewed as a formatted, "
        "print-ready HTML page directly in the browser. The print view renders all "
        "fields and embedded signature images in a clean layout, allowing users to "
        "print directly from the browser without needing to download a file.", s["body"]))

    # ── 12. Notifications & Audit ─────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("12", "Notifications and Audit Trail", s))
    story.append(Paragraph("In-app notifications", s["h2"]))
    story.append(Paragraph(
        "The platform maintains a notifications inbox for each user. Notifications are "
        "generated automatically at key workflow events: new submission received, request "
        "forwarded for approval, request approved, request rejected. Users can see an "
        "unread count badge and mark individual or all notifications as read. This "
        "removes the need for manual email chasing between team members for routine "
        "approval updates.", s["body"]))

    story.append(Paragraph("Audit log", s["h2"]))
    story.append(Paragraph(
        "All significant actions in the system are recorded in an audit log: logins, "
        "logouts, form submissions, approvals, rejections, and administrative changes "
        "such as user creation or permission updates. Each log entry records the "
        "acting user, the timestamp, the IP address, and the specific action taken. "
        "This provides a complete, tamper-evident history that can be reviewed "
        "for compliance purposes.", s["body"]))

    # ── 13. Mobile and PWA ────────────────────────────────────────────────
    story.append(_section_hdr("13", "Mobile and Progressive Web App", s))
    story.append(Paragraph(
        "The platform is designed to work on any device — desktop, tablet, or smartphone. "
        "The responsive interface adapts to screen size so that form fields, photo uploads, "
        "and signature capture all work correctly on a phone held in one hand in the field.", s["body"]))
    story.append(Paragraph(
        "A Progressive Web App (PWA) configuration is included. Users can install the "
        "platform directly to their device's home screen from the browser — no app store "
        "required. The PWA includes a service worker that enables the app icon and shell "
        "to load even when offline, with graceful offline messaging when the user is not "
        "connected. An offline page is shown automatically when connectivity is unavailable.", s["body"]))
    story.append(Paragraph(
        "For organisations that require a fully native mobile experience, the platform "
        "supports packaging as an Android or iOS application using Capacitor. The same "
        "web codebase powers the native app — there is no duplication of logic.", s["body"]))

    # ── 14. Deployment ────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("14", "Deployment and Infrastructure", s))
    story.append(Paragraph(
        "The platform is built for cloud deployment. It runs as a Python web application "
        "served by the Gunicorn WSGI server, and is documented for deployment on Render "
        "and equivalent cloud platforms.", s["body"]))

    deploy_data = [
        ["Component", "Development", "Production"],
        ["Database",      "SQLite (local file)",
                          "PostgreSQL (cloud-hosted, mandatory)"],
        ["File storage",  "Local directory",
                          "Cloudinary cloud storage (all uploads and generated files)"],
        ["Caching",       "In-memory (optional)",
                          "Redis (Upstash or similar; rate limiting and background queues)"],
        ["Email",         "SMTP or disabled",
                          "Mailjet or Brevo REST API (bypass blocked SMTP ports)"],
        ["Web server",    "Flask development server",
                          "Gunicorn (multi-worker WSGI)"],
        ["Config",        ".env file",
                          "Environment variables set in the hosting platform dashboard"],
    ]
    story.append(_table(deploy_data, [3.8*cm, 5.5*cm, 6.2*cm]))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Database schema changes are managed through Flask-Migrate, which keeps a versioned "
        "migration history and allows forward and backward schema changes without data loss. "
        "On startup, the application automatically verifies that the expected tables and "
        "columns exist, and adds any that are missing from older deployments.", s["body"]))
    story.append(Paragraph(
        "The application factory pattern means that the same codebase can run in "
        "development, staging, and production modes with different configurations simply "
        "by changing environment variables — no code changes required between environments.", s["body"]))

    # ── 15. Security ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("15", "Security Approach", s))
    for item in [
        "All passwords are stored as bcrypt hashes. The original password is never stored or logged.",
        "JWT tokens expire automatically. Short-lived access tokens (one hour) limit the window of exposure if a token is compromised. Logout immediately revokes the token by marking the session record.",
        "HTTP-only cookies prevent JavaScript from reading authentication tokens, reducing cross-site scripting risk.",
        "Rate limiting on login and registration endpoints prevents brute-force credential attacks.",
        "Sensitive configuration (database passwords, API keys, JWT secrets) is supplied through environment variables — never hardcoded in the source code and never committed to the repository.",
        "HTTPS-only cookie flags are enabled in production so authentication tokens are only transmitted over encrypted connections.",
        "The configuration validator checks for weak or default secrets at startup and refuses to start in production with unsafe values.",
        "All user actions that modify data or access sensitive functionality are authenticated with a valid, non-revoked JWT token.",
        "Module access flags mean a user cannot reach a module they have not been explicitly granted access to, regardless of whether they know the URL.",
        "The audit log provides a complete, non-repudiable record of who did what and when.",
    ]:
        story.append(_bp(item, s))

    # ── 16. Summary ───────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_hdr("16", "Summary of Delivered Capabilities", s))
    story.append(Paragraph(
        "The following table summarises the complete set of capabilities delivered in the "
        "current version of the Injaaz platform.", s["body"]))

    summary_data = [
        ["Capability", "Details"],
        ["User accounts and roles",
         "Account creation, password hashing, role assignment, per-module access flags, session management, audit logging of all actions."],
        ["HVAC & MEP forms",
         "Structured site visit forms with photo upload, dropdown data, signature capture, background Excel and PDF generation."],
        ["Civil Works forms",
         "Same capability set as HVAC, adapted for civil engineering site visits."],
        ["Cleaning forms",
         "Service inspection forms with the full generation pipeline."],
        ["Cross-trade Inspection",
         "Multi-discipline inspection forms spanning all operational trades."],
        ["11 HR form types",
         "Leave, commencement, duty resumption, contract renewal, performance evaluation, staff appraisal, passport release, visa renewal, grievance, interview assessment, station clearance."],
        ["Two-stage HR approval",
         "Employee submits → HR reviews and signs → GM final approval, with full rejection path at each stage."],
        ["PDF and DOCX output",
         "Professional, signed documents generated on approval, matching official form designs."],
        ["HTML print view",
         "Browser-printable view of any submitted HR form."],
        ["MMR analytics and reporting",
         "CAFM data ingestion, chargeable rule application, dashboard analytics, Excel report generation, automated scheduled email, cycle and activity logging."],
        ["Procurement workflows",
         "Structured procurement request and approval flows."],
        ["Business Development module",
         "BD submission and review workflows with admin visibility."],
        ["DocHub document repository",
         "Secure, authenticated document access and retrieval."],
        ["In-app notifications",
         "Automatic notifications for all workflow events; unread count; mark-as-read."],
        ["Audit trail",
         "Complete log of all user and system actions with timestamps."],
        ["PWA and mobile support",
         "Installable progressive web app; responsive design; optional Capacitor native app packaging."],
        ["Cloud-ready deployment",
         "Cloudinary file storage, PostgreSQL, Redis, Gunicorn, Render-documented deployment."],
    ]
    story.append(_table(summary_data, [4.5*cm, 11*cm]))
    story.append(Spacer(1, 0.5*cm))
    story.append(_callout(
        f"This documentation was generated automatically on {generated}. "
        "It reflects the state of the Injaaz platform as delivered and tested. "
        "Update this document whenever major new capabilities are added.",
        s))

    doc.build(story)


def main():
    out_dir = os.path.join(PROJECT_ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "Injaaz_Comprehensive_Documentation.pdf")
    build(out_path)
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
