import os
import time
import io
import logging

from common.datetime_utils import utc_now_naive

import requests
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors, utils
from reportlab.lib.units import mm

from common import kynvera_pdf_brand as brand
from reportlab.pdfgen.canvas import Canvas

logger = logging.getLogger(__name__)


class _VisitCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self._report_title = kwargs.pop('report_title', 'Site Visit Report')
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for s in self._saved:
            self.__dict__.update(s)
            brand.draw_page_chrome(
                self,
                self._pageNumber,
                n,
                report_title=self._report_title,
                left_margin=20 * mm,
                right_margin=20 * mm,
                footer_left=brand.FOOTER_CONFIDENTIAL,
            )
            Canvas.showPage(self)
        Canvas.save(self)


def _fetch_image_stream(url, timeout=8):
    """Download image and return BytesIO or None on failure."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return io.BytesIO(resp.content)
    except Exception:
        logger.exception("Failed to fetch image %s", url)
        return None


def _make_image_flowable(img_stream, max_width_mm=160):
    """
    Create a reportlab Image flowable from a BytesIO stream.
    max_width_mm: maximum width in millimeters to fit on page.
    """
    try:
        img_reader = utils.ImageReader(img_stream)
        iw, ih = img_reader.getSize()
        max_width = max_width_mm * mm
        if iw <= 0:
            return None
        scale = 1.0
        if iw > max_width:
            scale = max_width / iw
        width = iw * scale
        height = ih * scale
        img_stream.seek(0)
        return Image(img_stream, width=width, height=height)
    except Exception:
        logger.exception("Failed to create image flowable")
        return None


def generate_visit_pdf(visit_info, items, generated_dir, report_id=None):
    """
    Generate a PDF report for the visit.
    - visit_info: dict with keys like 'building_name', 'email', etc.
    - items: list of item dicts; each item may include 'description' and 'image_urls' (list).
    - generated_dir: directory to write the PDF into (will be created if missing).
    - report_id: optional string used in filename.
    Returns: (pdf_path, pdf_filename)
    """
    os.makedirs(generated_dir, exist_ok=True)
    timestamp = int(time.time())
    filename = f"report_{report_id or timestamp}.pdf"
    pdf_path = os.path.join(generated_dir, filename)

    try:
        title_text = visit_info.get('building_name') or "Site Visit Report"
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=24 * mm,
            bottomMargin=22 * mm,
            title=title_text,
            author=brand.PDF_AUTHOR,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'VisitTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=brand.TEXT_DARK,
            fontName='Helvetica-Bold',
        )
        normal = ParagraphStyle(
            'VisitBody',
            parent=styles['BodyText'],
            fontSize=9,
            textColor=brand.TEXT_DARK,
        )
        small = ParagraphStyle(
            'small',
            parent=normal,
            fontSize=9,
            textColor=brand.TEXT_MID,
        )

        story = []
        content_w = A4[0] - 40 * mm
        story.append(brand.story_header_block(title_text, brand.COMPANY_NAME, content_w))
        story.append(Spacer(1, 8))

        meta_lines = []
        meta_lines.append(("Date", utc_now_naive().strftime("%Y-%m-%d %H:%M UTC")))
        if visit_info.get('email'):
            meta_lines.append(("Technician", visit_info.get('email')))
        if visit_info.get('building_address'):
            meta_lines.append(("Address", visit_info.get('building_address')))

        meta_table_data = [[Paragraph(f"<b>{k}</b>", small), Paragraph(str(v), small)] for k, v in meta_lines]
        if meta_table_data:
            t = Table(meta_table_data, colWidths=[40 * mm, None])
            t.setStyle(TableStyle(brand.meta_table_style()))
            story.append(t)
            story.append(Spacer(1, 8))

        if not items:
            story.append(Paragraph("No items recorded.", normal))
        else:
            for idx, it in enumerate(items, start=1):
                heading = Paragraph(
                    f"<b>{idx}. {it.get('title', it.get('description', 'Item'))}</b>",
                    ParagraphStyle(
                        'VisitItem',
                        parent=styles['Heading4'],
                        textColor=brand.TEXT_DARK,
                    ),
                )
                story.append(heading)
                desc = it.get('description', '')
                if desc:
                    story.append(Paragraph(desc, normal))
                story.append(Spacer(1, 4))

                image_urls = it.get('image_urls') or []
                for img_url in image_urls:
                    stream = _fetch_image_stream(img_url)
                    if not stream:
                        continue
                    img_flow = _make_image_flowable(stream)
                    if img_flow:
                        story.append(img_flow)
                        story.append(Spacer(1, 6))

                story.append(Spacer(1, 8))

        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Generated by {brand.COMPANY_NAME}", small))

        doc.build(
            story,
            canvasmaker=lambda *a, **kw: _VisitCanvas(*a, report_title=title_text, **kw),
        )
        logger.info("Generated PDF: %s", pdf_path)
        return pdf_path, filename
    except Exception:
        logger.exception("Failed to generate PDF")
        # ensure no empty or broken file left
        try:
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) == 0:
                os.remove(pdf_path)
        except Exception:
            pass
        raise