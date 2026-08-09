"""
Professional PDF Service with Branding, Logo, and Signatures
Provides reusable components for all module PDFs
Enhanced with cover pages and Kynvera branding
"""
import os
import logging
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm, mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, 
                                Spacer, Image, PageBreak, Frame, PageTemplate,
                                KeepTogether, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, Line
from reportlab.graphics import renderPDF
from common.utils import get_image_for_pdf
from common import kynvera_pdf_brand as brand

logger = logging.getLogger(__name__)

# Company branding — Kynvera coral theme
PRIMARY_COLOR = brand.PRIMARY
SECONDARY_COLOR = brand.PRIMARY_DARK
ACCENT_COLOR = brand.SOFT_WASH
HEADER_BG = brand.SOFT_WASH
TABLE_HEADER_BG = brand.SOFT_WASH
TABLE_ALT_ROW = brand.SURFACE_ALT
BORDER_COLOR = brand.HAIRLINE
LIGHT_BG = brand.SURFACE_ALT

LOGO_PATH = brand.resolve_logo_path(prefer_wordmark=True) or brand.WORDMARK_PATH


class NumberedCanvas(canvas.Canvas):
    """Custom canvas to add header, footer, and page numbers"""
    
    def __init__(self, *args, **kwargs):
        self.report_title = kwargs.pop('report_title', brand.DEFAULT_REPORT_TITLE)
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
        
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
        
    def save(self):
        """Add page info to each page (page x of y)"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)
        
    def draw_page_decorations(self, page_count):
        """Draw compact header and footer on each page"""
        brand.draw_page_chrome(
            self,
            self._pageNumber,
            page_count,
            report_title=self.report_title,
            left_margin=1.4 * cm,
            right_margin=1.4 * cm,
            footer_left=f"Generated: {brand.generated_timestamp()}",
            header_title=brand.COMPANY_NAME,
        )


def get_professional_styles():
    """Return professional styled paragraph styles"""
    styles = getSampleStyleSheet()
    
    custom_styles = {
        'MainTitle': ParagraphStyle(
            'MainTitle',
            parent=styles['Heading1'],
            fontSize=13,
            textColor=PRIMARY_COLOR,
            spaceAfter=0.04*inch,
            spaceBefore=0,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
            leading=16,
            leftIndent=0,
            rightIndent=0,
        ),
        'Subtitle': ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=0.04*inch,
            alignment=TA_LEFT,
            fontName='Helvetica',
            leftIndent=0,
        ),
        'SectionHeading': ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=10,
            textColor=brand.TEXT_DARK,
            spaceAfter=0.14*inch,
            spaceBefore=0.08*inch,
            fontName='Helvetica-Bold',
            borderPadding=8,
            borderColor=PRIMARY_COLOR,
            borderWidth=0,
            borderRadius=0,
            backColor=HEADER_BG,
            leftIndent=0,
            rightIndent=0,
            leading=14,
        ),
        'ItemHeading': ParagraphStyle(
            'ItemHeading',
            parent=styles['Heading3'],
            fontSize=9.5,
            textColor=brand.PRIMARY_DARK,
            spaceAfter=0.03*inch,
            spaceBefore=0.08*inch,
            fontName='Helvetica-Bold',
            leading=13,
            leftIndent=0,
            rightIndent=0,
        ),
        'Normal': ParagraphStyle(
            'ProfessionalNormal',
            parent=styles['Normal'],
            fontSize=8.5,
            textColor=brand.TEXT_DARK,
            spaceAfter=0.02*inch,
            leading=12
        ),
        'Small': ParagraphStyle(
            'Small',
            parent=styles['Normal'],
            fontSize=7.5,
            textColor=brand.TEXT_MUTED,
            alignment=TA_CENTER,
            leading=10,
        ),
        'CommentLead': ParagraphStyle(
            'CommentLead',
            parent=styles['Normal'],
            fontSize=9.5,
            textColor=brand.TEXT_DARK,
            spaceAfter=0.06*inch,
            fontName='Helvetica-Bold',
            leading=13,
        ),
    }
    
    return custom_styles


def create_header_with_logo(story, title, subtitle=None):
    """Add document title header — logo is already in the running canvas header,
    so we only show the title text here to avoid duplication."""
    styles = get_professional_styles()

    story.append(Paragraph(f"<b>{title}</b>", styles['MainTitle']))

    if subtitle:
        story.append(Paragraph(subtitle, styles['Subtitle']))

    story.append(HRFlowable(
        width="100%", thickness=1, color=PRIMARY_COLOR,
        spaceBefore=0.06*inch, spaceAfter=0.08*inch
    ))
    return story


def create_info_table(data_list, col_widths=None):
    """Create a professional styled information table
    
    Args:
        data_list: List of [label, value] pairs
        col_widths: Optional column widths
    """
    styles = get_professional_styles()

    label_style = ParagraphStyle(
        'InfoTableLabel', parent=styles['Normal'], alignment=TA_RIGHT, fontName='Helvetica-Bold'
    )
    value_style = ParagraphStyle(
        'InfoTableValue', parent=styles['Normal'], alignment=TA_RIGHT
    )

    # Wrap long text values in Paragraphs so they word-wrap nicely
    table_data = []
    for row in data_list:
        new_row = []
        for col_idx, cell in enumerate(row):
            # Convert plain strings to Paragraphs for better wrapping
            if isinstance(cell, str):
                if col_idx == 0:
                    new_row.append(Paragraph(f"<b>{cell}</b>", label_style))
                else:
                    new_row.append(Paragraph(cell, value_style))
            else:
                new_row.append(cell)
        table_data.append(new_row)

    # Default: label col wide enough for "Specification", "Description", etc.
    if not col_widths:
        col_widths = [2.35*inch, 4.65*inch]

    table = Table(table_data, colWidths=col_widths)
    n = len(table_data)
    row_style = [('BACKGROUND', (0, i), (-1, i), colors.white) for i in range(n)]

    table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#111827')),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('LINEAFTER', (0, 0), (0, -1), 1, PRIMARY_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, -1), 6),
        ('LEFTPADDING', (1, 0), (1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ] + row_style))
    
    return table


def create_data_table(headers, rows, col_widths=None):
    """Create a professional data table with headers
    
    Args:
        headers: List of header strings
        rows: List of row data lists
        col_widths: Optional column widths
    """
    styles = get_professional_styles()

    # Build table data with Paragraphs so long text wraps instead of overflowing
    table_data = []

    # Header row – bold text
    header_cells = []
    for header in headers:
        if isinstance(header, str):
            header_cells.append(Paragraph(f"<b>{header}</b>", styles['Normal']))
        else:
            header_cells.append(header)
    table_data.append(header_cells)

    data_cell_style = ParagraphStyle(
        'DataTableCell', parent=styles['Normal'], alignment=TA_RIGHT
    )

    # Data rows
    for row in rows:
        new_row = []
        for cell in row:
            if isinstance(cell, str):
                new_row.append(Paragraph(cell, data_cell_style))
            else:
                new_row.append(cell)
        table_data.append(new_row)
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Header row — soft wash + coral rule (not solid green)
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), brand.TEXT_DARK),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, TABLE_ALT_ROW]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, PRIMARY_COLOR),
        
        # Padding
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    return table


def _photo_grid_layout(photo_count, photos_per_row=None, photo_width=None, photo_height=None):
    """Pick column count and max cell size from printable width (A4 minus margins)."""
    content_w = 6.5 * inch
    gap = 0.12 * inch

    if photos_per_row is not None and photo_width is not None and photo_height is not None:
        return photos_per_row, photo_width, photo_height, content_w

    if photo_count == 1:
        return 1, content_w, 5.0 * inch, content_w
    if photo_count <= 2:
        cell_w = (content_w - gap) / 2
        return 2, cell_w, 3.25 * inch, content_w
    if photo_count <= 6:
        cell_w = (content_w - gap) / 2
        return 2, cell_w, 2.85 * inch, content_w
    if photo_count <= 15:
        cell_w = (content_w - 2 * gap) / 3
        return 3, cell_w, 2.1 * inch, content_w
    cell_w = (content_w - 3 * gap) / 4
    return 4, cell_w, 1.55 * inch, content_w


def _scaled_pdf_image(img_data, max_width, max_height, styles):
    """Build a ReportLab Image flowable scaled to fit max_width x max_height."""
    from reportlab.lib import utils

    if isinstance(img_data, str):
        img_reader = utils.ImageReader(img_data)
        orig_width, orig_height = img_reader.getSize()
        img_source = img_data
    else:
        img_data.seek(0)
        img_reader = utils.ImageReader(img_data)
        orig_width, orig_height = img_reader.getSize()
        img_data.seek(0)
        img_source = img_data

    if orig_width <= 0 or orig_height <= 0:
        img = Image(img_source, width=max_width, height=max_height)
    else:
        scale = min(max_width / orig_width, max_height / orig_height)
        final_width = orig_width * scale
        final_height = orig_height * scale
        img = Image(img_source, width=final_width, height=final_height)

    img.hAlign = 'CENTER'
    return img


def add_photo_grid(story, photos, photos_per_row=None, photo_width=None, photo_height=None):
    """Add a grid of photos; each row stays on one page and scales to fit its cell."""
    styles = get_professional_styles()

    if not photos:
        return story

    photo_count = len(photos)
    photos_per_row, max_cell_w, max_cell_h, content_w = _photo_grid_layout(
        photo_count, photos_per_row, photo_width, photo_height
    )
    gap = 0.12 * inch
    col_width = (content_w - gap * (photos_per_row - 1)) / photos_per_row
    col_widths = [col_width] * photos_per_row

    row_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ])

    for i in range(0, len(photos), photos_per_row):
        row_photos = photos[i:i + photos_per_row]
        photo_row = []

        for photo_item in row_photos:
            try:
                img_data, _is_url = get_image_for_pdf(photo_item)
                if img_data:
                    try:
                        photo_row.append(_scaled_pdf_image(img_data, max_cell_w, max_cell_h, styles))
                    except Exception as img_error:
                        logger.error(f"Error processing image: {img_error}")
                        try:
                            if isinstance(img_data, str):
                                img = Image(img_data, width=max_cell_w, height=max_cell_h)
                            else:
                                img_data.seek(0)
                                img = Image(img_data, width=max_cell_w, height=max_cell_h)
                            img.hAlign = 'CENTER'
                            photo_row.append(img)
                        except Exception as final_error:
                            logger.error(f"Photo fallback failed: {final_error}")
                            photo_row.append(Paragraph("Error loading image", styles['Small']))
                else:
                    logger.warning(f"get_image_for_pdf returned None for photo_item: {photo_item}")
                    photo_row.append(Paragraph("Image not available", styles['Small']))
            except Exception as e:
                logger.error(f"Error loading photo: {e}")
                photo_row.append(Paragraph("Error loading image", styles['Small']))

        while len(photo_row) < photos_per_row:
            photo_row.append('')

        row_table = Table([photo_row], colWidths=col_widths, hAlign='CENTER')
        row_table.setStyle(row_style)
        story.append(KeepTogether([row_table]))

    story.append(Spacer(1, 0.12 * inch))
    return story


def add_signatures_section(story, signatures_dict):
    """Add professional signatures section
    
    Args:
        story: PDF story list
        signatures_dict: Dict with signature info, e.g.:
            {
                'Technician': signature_data,
                'Manager': signature_data,
                'Inspector': signature_data
            }
    """
    styles = get_professional_styles()
    
    # No page break - let signatures flow with content
    story.append(Paragraph("Signatures & Approval", styles['SectionHeading']))
    story.append(Spacer(1, 0.15*inch))  # Reduced spacing
    
    sig_rows = []
    
    for role, sig_data in signatures_dict.items():
        if not sig_data:
            sig_rows.append([
                Paragraph(f"<b>{role}:</b>", styles['Normal']),
                Paragraph("Not signed", styles['Small'])
            ])
            continue
        
        try:
            img_data, is_url = get_image_for_pdf(sig_data)
            if img_data:
                sig_img = Image(img_data)
                sig_img._restrictSize(2.5*inch, 1.2*inch)  # Max size, keeps aspect ratio
                sig_rows.append([
                    Paragraph(f"<b>{role}:</b>", styles['Normal']),
                    sig_img
                ])
            else:
                sig_rows.append([
                    Paragraph(f"<b>{role}:</b>", styles['Normal']),
                    Paragraph("Signature not available", styles['Small'])
                ])
        except Exception as e:
            logger.error(f"Error processing {role} signature: {str(e)}")
            sig_rows.append([
                Paragraph(f"<b>{role}:</b>", styles['Normal']),
                Paragraph("Error loading signature", styles['Small'])
            ])
    
    if sig_rows:
        sig_table = Table(sig_rows, colWidths=[2*inch, 3.5*inch])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, PRIMARY_COLOR),
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(sig_table)
    
    # Add signature date
    story.append(Spacer(1, 0.15*inch))  # Reduced spacing
    story.append(Paragraph(
        f"<i>Document signed on: {datetime.now().strftime('%B %d, %Y at %H:%M')}</i>",
        styles['Small']
    ))
    
    return story


def create_professional_pdf(pdf_path, story, report_title=None):
    """Build the PDF with professional styling
    
    Args:
        pdf_path: Output path for PDF
        story: List of flowables (content)
        report_title: Title for footer
    """
    if report_title is None:
        report_title = brand.DEFAULT_REPORT_TITLE
    try:
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=1.6*cm,
            leftMargin=1.6*cm,
            topMargin=1.9*cm,
            bottomMargin=1.8*cm,
            title=report_title,
            author=brand.PDF_AUTHOR
        )
        
        # Build with custom canvas for headers/footers
        doc.build(
            story,
            canvasmaker=lambda *args, **kwargs: NumberedCanvas(
                *args, 
                **kwargs, 
                report_title=report_title
            )
        )
        
        if not os.path.exists(pdf_path):
            raise Exception(f"PDF file not created at {pdf_path}")
        
        # Verify PDF file is not empty and has valid structure
        file_size = os.path.getsize(pdf_path)
        if file_size == 0:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            raise Exception(f"PDF file is empty at {pdf_path}")
        
        # Verify PDF header (should start with %PDF)
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF'):
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                    raise Exception(f"PDF file has invalid header at {pdf_path} (expected %PDF, got {header[:8]})")
        except Exception as e:
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except:
                    pass
            raise Exception(f"Failed to verify PDF file: {str(e)}")
        
        logger.info(f"✅ Professional PDF created: {pdf_path} ({file_size} bytes)")
        return pdf_path
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"❌ PDF creation failed: {str(e)}")
        logger.error(f"❌ PDF creation traceback:\n{error_details}")
        raise


def add_section_heading(story, text):
    """Add a section heading"""
    styles = get_professional_styles()
    story.append(Paragraph(text, styles['SectionHeading']))
    return story


def append_section_keep_together(story, heading_text, content_flowables):
    """Keep a section heading and its content on the same page when they fit together."""
    styles = get_professional_styles()
    block = [Paragraph(heading_text, styles['SectionHeading'])]
    block.extend(content_flowables)
    story.append(KeepTogether(block))
    return story


def add_item_heading(story, text):
    """Add an item heading"""
    styles = get_professional_styles()
    story.append(Paragraph(text, styles['ItemHeading']))
    return story


def add_paragraph(story, text):
    """Add a normal paragraph"""
    styles = get_professional_styles()
    story.append(Paragraph(text, styles['Normal']))
    return story


def create_cover_page(story, report_info):
    """Create a professional cover page for the PDF report
    
    Args:
        story: PDF story list
        report_info: Dictionary with report details:
            - title: Main report title (e.g., "Site Assessment Report")
            - subtitle: Optional subtitle (e.g., "HVAC & MEP Inspection")
            - project_name: Project/Site name
            - location: Site location
            - date: Report date
            - prepared_by: Name of person who prepared the report
            - prepared_for: Client/company name (optional)
            - report_id: Submission ID or reference number
            - status: Workflow status (optional)
    """
    styles = get_professional_styles()
    
    # Create cover page styles
    cover_title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['MainTitle'],
        fontSize=28,
        textColor=PRIMARY_COLOR,
        spaceAfter=0.2*inch,
        spaceBefore=0,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=34
    )
    
    cover_subtitle_style = ParagraphStyle(
        'CoverSubtitle',
        fontSize=16,
        textColor=SECONDARY_COLOR,
        spaceAfter=0.5*inch,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    cover_info_style = ParagraphStyle(
        'CoverInfo',
        fontSize=12,
        textColor=colors.HexColor('#374151'),
        spaceAfter=0.15*inch,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    cover_label_style = ParagraphStyle(
        'CoverLabel',
        fontSize=10,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=0.05*inch,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    # Add top spacing
    story.append(Spacer(1, 1.2*inch))
    
    # Wordmark
    logo = brand.wordmark_flowable(max_width=2.4*inch, max_height=0.6*inch)
    if logo:
        logo.hAlign = 'CENTER'
        story.append(logo)
        story.append(Spacer(1, 0.25*inch))
    
    # Company name
    story.append(Paragraph(brand.COMPANY_NAME, ParagraphStyle(
        'CompanyName',
        fontSize=14,
        textColor=brand.TEXT_DARK,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=0.08*inch
    )))
    
    # Tagline
    story.append(Paragraph(brand.TAGLINE, ParagraphStyle(
        'Tagline',
        fontSize=10,
        textColor=brand.TEXT_MUTED,
        alignment=TA_CENTER,
        fontName='Helvetica-Oblique',
        spaceAfter=0.5*inch
    )))
    
    # Decorative coral line
    story.append(HRFlowable(
        width="60%",
        thickness=2,
        color=PRIMARY_COLOR,
        spaceBefore=0.15*inch,
        spaceAfter=0.35*inch,
        hAlign='CENTER'
    ))
    
    # Main title
    title = report_info.get('title', 'Site Assessment Report')
    story.append(Paragraph(title, cover_title_style))
    
    # Subtitle
    subtitle = report_info.get('subtitle', '')
    if subtitle:
        story.append(Paragraph(subtitle, cover_subtitle_style))
    else:
        story.append(Spacer(1, 0.3*inch))
    
    # Project info box
    project_name = report_info.get('project_name', 'N/A')
    location = report_info.get('location', '')
    report_date = report_info.get('date', datetime.now().strftime('%B %d, %Y'))
    
    # Create info table
    info_data = []
    
    info_data.append([
        Paragraph("<b>Project / Site</b>", cover_label_style),
        Paragraph(project_name, cover_info_style)
    ])
    
    if location:
        info_data.append([
            Paragraph("<b>Location</b>", cover_label_style),
            Paragraph(location, cover_info_style)
        ])
    
    info_data.append([
        Paragraph("<b>Report Date</b>", cover_label_style),
        Paragraph(str(report_date), cover_info_style)
    ])
    
    report_id = report_info.get('report_id', '')
    if report_id:
        info_data.append([
            Paragraph("<b>Reference No.</b>", cover_label_style),
            Paragraph(report_id, cover_info_style)
        ])
    
    # Status badge
    status = report_info.get('status', '')
    if status:
        status_display = status.replace('_', ' ').title()
        status_color = PRIMARY_COLOR if status == 'completed' else SECONDARY_COLOR
        info_data.append([
            Paragraph("<b>Status</b>", cover_label_style),
            Paragraph(f"<font color='#{status_color.hexval()[2:]}'><b>{status_display}</b></font>", cover_info_style)
        ])
    
    info_table = Table(info_data, colWidths=[2*inch, 3.5*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT_COLOR),
        ('BOX', (0, 0), (-1, -1), 1, PRIMARY_COLOR),
        ('LINEABOVE', (0, 0), (-1, 0), 2, PRIMARY_COLOR),
        ('LINEBELOW', (0, -1), (-1, -1), 2, PRIMARY_COLOR),
    ]))
    
    story.append(Spacer(1, 0.3*inch))
    story.append(info_table)
    
    # Prepared by section
    prepared_by = report_info.get('prepared_by', '')
    prepared_for = report_info.get('prepared_for', '')
    
    if prepared_by or prepared_for:
        story.append(Spacer(1, 0.8*inch))
        
        if prepared_for:
            story.append(Paragraph("Prepared For", cover_label_style))
            story.append(Paragraph(prepared_for, cover_info_style))
            story.append(Spacer(1, 0.3*inch))
        
        if prepared_by:
            story.append(Paragraph("Prepared By", cover_label_style))
            story.append(Paragraph(prepared_by, cover_info_style))
    
    # Footer with generation timestamp
    story.append(Spacer(1, 1*inch))
    story.append(HRFlowable(
        width="40%",
        thickness=1,
        color=BORDER_COLOR,
        spaceBefore=0.2*inch,
        spaceAfter=0.2*inch,
        hAlign='CENTER'
    ))
    
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}",
        ParagraphStyle(
            'Generated',
            fontSize=9,
            textColor=colors.HexColor('#9ca3af'),
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
    ))
    
    # Page break after cover
    story.append(PageBreak())
    
    return story


def add_executive_summary(story, summary_data):
    """Add an executive summary section with key metrics
    
    Args:
        story: PDF story list
        summary_data: Dictionary with summary info:
            - total_items: Number of items inspected
            - photos_count: Number of photos
            - status: Overall status
            - highlights: List of key findings
            - recommendations: List of recommendations (optional)
    """
    styles = get_professional_styles()
    
    story.append(Paragraph("Executive Summary", styles['SectionHeading']))
    story.append(Spacer(1, 0.15*inch))
    
    # Summary stats in a grid
    stats_data = []
    stats_row = []
    
    total_items = summary_data.get('total_items', 0)
    photos_count = summary_data.get('photos_count', 0)
    status = summary_data.get('status', 'N/A')
    
    # Create stat boxes
    stat_style = ParagraphStyle(
        'StatValue',
        fontSize=24,
        textColor=PRIMARY_COLOR,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    stat_label_style = ParagraphStyle(
        'StatLabel',
        fontSize=9,
        textColor=colors.HexColor('#6b7280'),
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    stats_row.append([
        Paragraph(str(total_items), stat_style),
        Paragraph("Items Inspected", stat_label_style)
    ])
    
    stats_row.append([
        Paragraph(str(photos_count), stat_style),
        Paragraph("Photos Captured", stat_label_style)
    ])
    
    status_display = status.replace('_', ' ').title()
    stats_row.append([
        Paragraph(status_display, ParagraphStyle(
            'StatusValue',
            fontSize=14,
            textColor=PRIMARY_COLOR if status == 'completed' else SECONDARY_COLOR,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )),
        Paragraph("Status", stat_label_style)
    ])
    
    # Create stats table - each stat is a mini-table
    stats_tables = []
    for stat in stats_row:
        mini_table = Table([stat], colWidths=[1.8*inch])
        mini_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), ACCENT_COLOR),
            ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        stats_tables.append(mini_table)
    
    stats_container = Table([stats_tables], colWidths=[2*inch] * 3)
    stats_container.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    story.append(stats_container)
    story.append(Spacer(1, 0.2*inch))
    
    # Highlights/Key Findings
    highlights = summary_data.get('highlights', [])
    if highlights:
        story.append(Paragraph("<b>Key Findings:</b>", styles['Normal']))
        for highlight in highlights[:5]:  # Limit to 5 highlights
            story.append(Paragraph(f"• {highlight}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
    
    # Recommendations
    recommendations = summary_data.get('recommendations', [])
    if recommendations:
        story.append(Paragraph("<b>Recommendations:</b>", styles['Normal']))
        for rec in recommendations[:3]:  # Limit to 3 recommendations
            story.append(Paragraph(f"• {rec}", styles['Normal']))
    
    story.append(Spacer(1, 0.2*inch))
    
    return story


def add_qr_code_section(story, url, label="Scan to view online"):
    """Add a QR code linking to the digital version (placeholder for future)
    
    Note: This requires qrcode library. For now, just adds a text reference.
    """
    styles = get_professional_styles()
    
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(
        f"<i>Digital Version: {url}</i>",
        ParagraphStyle(
            'QRLabel',
            fontSize=8,
            textColor=colors.HexColor('#6b7280'),
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
    ))
    
    return story


def add_section_with_icon(story, title, icon_char="📋"):
    """Add a section heading with an icon character
    
    Args:
        story: PDF story list
        title: Section title
        icon_char: Emoji or character to use as icon (limited support in PDFs)
    """
    styles = get_professional_styles()
    
    # Create styled section heading
    section_style = ParagraphStyle(
        'IconSection',
        parent=styles['SectionHeading'],
        fontSize=13,
        textColor=PRIMARY_COLOR,
        spaceAfter=0.08*inch,
        spaceBefore=0.12*inch,
        fontName='Helvetica-Bold',
        borderPadding=3,
        borderColor=PRIMARY_COLOR,
        borderWidth=1,
        borderRadius=3,
        backColor=ACCENT_COLOR,
        leftIndent=4,
    )
    
    # Note: Emoji support in PDFs is limited, so we use a decorated title
    story.append(Paragraph(f"■ {title}", section_style))
    
    return story
