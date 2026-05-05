"""
module_hvac_mep/generator.py

Background generator for HVAC/MEP submissions.
"""
import os
import json
import time
import traceback
import mimetypes
import ssl
import smtplib
from email.message import EmailMessage
from datetime import datetime
import logging

from flask import url_for

# site-visit generators (should exist in repo)
from module_site_visit.utils.pdf_generator import generate_visit_pdf
from module_site_visit.utils.excel_writer import create_report_workbook

# job helpers - use the config-aware wrappers
from common.utils import (
    mark_job_done_with_config as mark_job_done,
    update_job_progress_with_config as update_job_progress
)

logger = logging.getLogger(__name__)

# Defaults (can be overridden via app.config)
BLUEPRINT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BLUEPRINT_DIR)
DEFAULT_GENERATED_DIR = os.path.join(BASE_DIR, "generated")
DEFAULT_UPLOADS_DIR = os.path.join(DEFAULT_GENERATED_DIR, "uploads")
DEFAULT_JOBS_DIR = os.path.join(DEFAULT_GENERATED_DIR, "jobs")


def _paths_from_app(app):
    gen = app.config.get("GENERATED_DIR", DEFAULT_GENERATED_DIR)
    uploads = app.config.get("UPLOADS_DIR", DEFAULT_UPLOADS_DIR)
    jobs = app.config.get("JOBS_DIR", DEFAULT_JOBS_DIR)
    return gen, uploads, jobs


def _send_email(app, subject, body, recipients, attachments=None):
    """
    Simple SMTP mailer using app.config. Returns True on success.
    Config keys:
      MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD,
      MAIL_USE_TLS, MAIL_USE_SSL, MAIL_DEFAULT_SENDER
    """
    if not recipients:
        app.logger.warning("No recipients provided for email")
        return False

    mail_server = app.config.get("MAIL_SERVER")
    mail_port = int(app.config.get("MAIL_PORT", 0) or 0)
    mail_user = app.config.get("MAIL_USERNAME")
    mail_pass = app.config.get("MAIL_PASSWORD")
    mail_use_tls = bool(app.config.get("MAIL_USE_TLS", False))
    mail_use_ssl = bool(app.config.get("MAIL_USE_SSL", False))
    mail_sender = app.config.get("MAIL_DEFAULT_SENDER") or mail_user

    if not mail_server or not mail_port:
        app.logger.warning("Mail server/port not configured; skipping email")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_sender
    if isinstance(recipients, (list, tuple)):
        msg["To"] = ", ".join(recipients)
    else:
        msg["To"] = recipients
    msg.set_content(body)

    attachments = attachments or []
    for path in attachments:
        try:
            if not os.path.exists(path):
                app.logger.warning("Attachment not found: %s", path)
                continue
            ctype, encoding = mimetypes.guess_type(path)
            if ctype is None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(path, "rb") as fh:
                data = fh.read()
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(path))
        except Exception:
            app.logger.exception("Failed to attach file %s", path)

    try:
        if mail_use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(mail_server, mail_port, context=context) as server:
                if mail_user and mail_pass:
                    server.login(mail_user, mail_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(mail_server, mail_port) as server:
                if mail_use_tls:
                    server.starttls()
                if mail_user and mail_pass:
                    server.login(mail_user, mail_pass)
                server.send_message(msg)
        app.logger.info("Email sent to %s", recipients)
        return True
    except Exception:
        app.logger.exception("Failed to send email")
        return False


def process_submission(submission_data, job_id, config):
    """
    Main background worker. Expects `config` (dict from app.config) and submission_data dict.

    This function will:
      - use submission_data directly (no need to load from file)
      - construct visit_info and processed_items
      - generate Excel and PDF into GENERATED_DIR
      - build absolute URLs using submission_data['base_url'] + relative url_for(...)
      - optionally email results
      - mark job done / failed
    """
    gen_dir = config.get("GENERATED_DIR", DEFAULT_GENERATED_DIR)
    uploads_dir = config.get("UPLOADS_DIR", DEFAULT_UPLOADS_DIR)
    start_ts = time.time()

    try:
        logger.info(f"[JOB {job_id}] START processing submission")
        update_job_progress(job_id, 5, config)

        submission = submission_data
        logger.info(f"[JOB {job_id}] loaded submission id={submission.get('id')} items={len(submission.get('items', []))}")

        # Build visit_info expected by site_visit utils
        visit_info = {}
        visit_info["building_name"] = submission.get("site_name") or submission.get("id", "Unknown")
        visit_info["building_address"] = submission.get("site_address", "")
        visit_info["visit_date"] = submission.get("visit_date", "")

        # Signatures: can be saved filename or external url
        tech_sig = submission.get("tech_signature") or {}
        opman_sig = submission.get("opman_signature") or {}
        if isinstance(tech_sig, dict):
            if tech_sig.get("url"):
                visit_info["tech_signature_url"] = tech_sig.get("url")
            if tech_sig.get("saved"):
                visit_info["tech_signature_path"] = os.path.join(uploads_dir, tech_sig.get("saved"))
        if isinstance(opman_sig, dict):
            if opman_sig.get("url"):
                visit_info["opMan_signature_url"] = opman_sig.get("url")
            if opman_sig.get("saved"):
                visit_info["opMan_signature_path"] = os.path.join(uploads_dir, opman_sig.get("saved"))

        # Other metadata
        visit_info["technician_name"] = submission.get("technician_name") or submission.get("tech_name") or ""
        visit_info["opMan_name"] = submission.get("opMan_name") or ""
        visit_info["contact_person"] = submission.get("contact_person") or ""
        visit_info["contact_number"] = submission.get("contact_number") or ""
        visit_info["email"] = submission.get("email") or ""
        visit_info["general_notes"] = submission.get("general_notes") or ""

        # Build processed_items for generators (image_paths and image_urls)
        processed_items = []
        for it in submission.get("items", []) or []:
            image_paths = []
            image_urls = []
            for p in (it.get("photos") or []):
                if isinstance(p, dict):
                    if p.get("path"):
                        image_paths.append(p.get("path"))
                    if p.get("url"):
                        image_urls.append(p.get("url"))
                else:
                    # treat as filename fallback
                    try:
                        fp = os.path.join(uploads_dir, p)
                        if os.path.exists(fp):
                            image_paths.append(fp)
                    except Exception:
                        pass
            processed_items.append({
                "asset": it.get("asset", ""),
                "system": it.get("system", ""),
                "description": it.get("description", ""),
                "quantity": it.get("quantity", ""),
                "brand": it.get("brand", ""),
                "comments": it.get("comments", ""),
                "image_paths": image_paths,
                "image_urls": image_urls,
            })

        update_job_progress(job_id, 15, config)

        # Excel
        try:
            logger.info(f"Generating Excel report for job {job_id}")
            excel_path, excel_filename = create_report_workbook(gen_dir, visit_info, processed_items)
            if not excel_path or not os.path.exists(excel_path):
                raise Exception("Excel report generation failed")
        except Exception:
            logger.exception(f"[JOB {job_id}] Excel generation failed")
            excel_path, excel_filename = None, None
        logger.info(f"[JOB {job_id}] excel result: {excel_path} / {excel_filename}")
        update_job_progress(job_id, 50, config)

        # PDF
        try:
            logger.info(f"Generating PDF report for job {job_id}")
            pdf_path, pdf_filename = generate_visit_pdf(visit_info, processed_items, gen_dir)
            if not pdf_path or not os.path.exists(pdf_path):
                raise Exception("PDF report generation failed")
        except Exception:
            logger.exception(f"[JOB {job_id}] PDF generation failed")
            pdf_path, pdf_filename = None, None
        logger.info(f"[JOB {job_id}] pdf result: {pdf_path} / {pdf_filename}")
        update_job_progress(job_id, 85, config)

        # Build results - use submission base_url for absolute links
        results = {}
        base = submission.get("base_url", "")
        
        if excel_filename and excel_path:
            results['excel_url'] = f"{base}/hvac-mep/generated/{excel_filename}"
            
        if pdf_filename and pdf_path:
            results['pdf_url'] = f"{base}/hvac-mep/generated/{pdf_filename}"

        logger.info(f"[JOB {job_id}] Built results: {results}")

        # Mark job done - this sets state="done" and progress=100
        mark_job_done(job_id, True, config, results=results)

        logger.info(f"[JOB {job_id}] DONE total={(time.time() - start_ts):.2f}s")

    except Exception as e:
        logger.exception(f"[JOB {job_id}] Unhandled exception in process_submission")
        try:
            mark_job_done(job_id, False, config, error=str(e))
        except Exception:
            pass

def generate_visit_pdf(visit_info, processed_items, output_dir):
    """
    Generate comprehensive HVAC/MEP PDF report with ALL images.
    Handles unlimited images per item with proper pagination.
    """
    try:
        logger.info(f"Starting PDF generation in {output_dir}")
        
        # Generate filename
        site_name = visit_info.get('building_name', 'Unknown_Site').replace(' ', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f"HVAC_MEP_{site_name}_{timestamp}.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Container for PDF elements
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#125435'),
            spaceAfter=0.3*inch,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#125435'),
            spaceAfter=0.2*inch,
            spaceBefore=0.3*inch,
            fontName='Helvetica-Bold'
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#1a7a4d'),
            spaceAfter=0.15*inch,
            fontName='Helvetica-Bold'
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=0.1*inch
        )
        
        # TITLE
        story.append(Paragraph("HVAC & MEP INSPECTION REPORT", title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # SITE INFORMATION
        story.append(Paragraph("Site Information", heading_style))
        
        site_info_data = [
            ['Site Name:', visit_info.get('building_name', 'N/A')],
            ['Visit Date:', visit_info.get('visit_date', 'N/A')],
            ['Report Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Total Items:', str(len(processed_items))]
        ]
        
        site_table = Table(site_info_data, colWidths=[2*inch, 4*inch])
        site_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(site_table)
        story.append(Spacer(1, 0.3*inch))
        
        # INSPECTION ITEMS
        if processed_items:
            for idx, item in enumerate(processed_items, 1):
                # Item header
                story.append(Paragraph(f"Item {idx}: {item.get('asset', 'N/A')}", subheading_style))
                
                # Item details table
                item_details = [
                    ['Asset:', item.get('asset', 'N/A')],
                    ['System:', item.get('system', 'N/A')],
                    ['Description:', item.get('description', 'N/A')],
                    ['Photos:', str(len(item.get('image_paths', [])))]
                ]
                
                item_table = Table(item_details, colWidths=[1.5*inch, 4.5*inch])
                item_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f9fafb')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
                ]))
                
                story.append(item_table)
                story.append(Spacer(1, 0.15*inch))
                
                # PHOTOS - Add ALL photos for this item
                photos = item.get('image_paths', [])
                
                if photos:
                    # Process photos in rows of 2 for better layout
                    photo_rows = []
                    for i in range(0, len(photos), 2):
                        row_photos = photos[i:i+2]
                        photo_row = []
                        
                        for photo_path in row_photos:
                            try:
                                if os.path.exists(photo_path):
                                    img = Image(photo_path, width=2.5*inch, height=2*inch)
                                    photo_row.append(img)
                                else:
                                    logger.warning(f"Photo not found: {photo_path}")
                                    photo_row.append(Paragraph(f"Image not found", normal_style))
                            except Exception as e:
                                logger.error(f"Error loading photo {photo_path}: {str(e)}")
                                photo_row.append(Paragraph(f"Error loading image", normal_style))
                        
                        # If odd number of photos, add empty cell
                        if len(photo_row) == 1:
                            photo_row.append('')
                        
                        photo_rows.append(photo_row)
                    
                    # Create photo table
                    if photo_rows:
                        photo_table = Table(photo_rows, colWidths=[2.8*inch, 2.8*inch])
                        photo_table.setStyle(TableStyle([
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 5),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                            ('TOPPADDING', (0, 0), (-1, -1), 5),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                        ]))
                        story.append(photo_table)
                        story.append(Spacer(1, 0.2*inch))
                
                # Add page break after each item (except last)
                if idx < len(processed_items):
                    story.append(PageBreak())
        
        else:
            story.append(Paragraph("No inspection items recorded.", normal_style))
        
        # SIGNATURES PAGE
        story.append(PageBreak())
        story.append(Paragraph("Signatures", heading_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Technician Signature
        tech_signature = visit_info.get('tech_signature', '')
        story.append(Paragraph("Technician Signature:", subheading_style))
        
        if tech_signature and tech_signature.startswith('data:image'):
            try:
                # Extract base64 data
                img_data = tech_signature.split(',')[1]
                img_bytes = base64.b64decode(img_data)
                img_buffer = BytesIO(img_bytes)
                
                sig_img = Image(img_buffer, width=3*inch, height=1.5*inch)
                story.append(sig_img)
            except Exception as e:
                logger.error(f"Error processing tech signature: {str(e)}")
                story.append(Paragraph("Signature not available", normal_style))
        else:
            story.append(Paragraph("Not signed", normal_style))
        
        story.append(Spacer(1, 0.3*inch))
        
        # Manager Signature
        manager_signature = visit_info.get('opMan_signature', '')
        story.append(Paragraph("Operation Manager Signature:", subheading_style))
        
        if manager_signature and manager_signature.startswith('data:image'):
            try:
                img_data = manager_signature.split(',')[1]
                img_bytes = base64.b64decode(img_data)
                img_buffer = BytesIO(img_bytes)
                
                sig_img = Image(img_buffer, width=3*inch, height=1.5*inch)
                story.append(sig_img)
            except Exception as e:
                logger.error(f"Error processing manager signature: {str(e)}")
                story.append(Paragraph("Signature not available", normal_style))
        else:
            story.append(Paragraph("Not signed", normal_style))
        
        # Footer
        story.append(Spacer(1, 0.5*inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            f"Generated by Injaaz Application • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            footer_style
        ))
        
        # Build PDF
        doc.build(story)
        
        if not os.path.exists(pdf_path):
            raise Exception(f"PDF file not created at {pdf_path}")
        
        logger.info(f"✅ PDF report created successfully: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        logger.error(f"❌ PDF generation error: {str(e)}")
        raise