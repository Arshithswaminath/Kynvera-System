"""
Fire Systems inspection → Service Report PDF.

Page 1: exact company Service Report template (shared with ticketing).
Page 2: inspection photos + workflow signatures (Supervisor → GM).
"""
from __future__ import annotations

import logging
import os
import types
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from common.utils import get_image_for_pdf
from module_ticketing.service_report_pdf_builder import (
    AVAIL_W,
    BORDER,
    MARGIN_B,
    MARGIN_L,
    MARGIN_R,
    MARGIN_T,
    RULE,
    _SRCanvas,
    _find_logo_path,
    _load_sig_image,
    build_service_report_page1_story,
)

logger = logging.getLogger(__name__)

RED = colors.HexColor('#d21725')
DARK = colors.HexColor('#1f2937')
MUTED = colors.HexColor('#6b7280')

# Workflow roles drawn on page 2 (order matches approval chain)
_WORKFLOW_ROLES = [
    ('Supervisor', (
        'supervisor_signature',
    ), (
        'supervisor_comments',
    )),
    ('Operations Manager', (
        'operations_manager_signature', 'opMan_signature', 'opman_signature',
    ), (
        'operations_manager_comments', 'opMan_comments', 'opman_comments',
    )),
    ('Business Development', (
        'business_dev_signature', 'business_development_signature',
    ), (
        'business_dev_comments', 'business_development_comments',
    )),
    ('Procurement', (
        'procurement_signature',
    ), (
        'procurement_comments',
    )),
    ('General Manager', (
        'general_manager_signature',
    ), (
        'general_manager_comments',
    )),
]


def _first_present(data: dict, keys: tuple[str, ...]):
    nested = data.get('data') if isinstance(data.get('data'), dict) else {}
    form = data.get('form_data') if isinstance(data.get('form_data'), dict) else {}
    for key in keys:
        for src in (data, nested, form):
            if not src:
                continue
            val = src.get(key)
            if val is None or val == '' or val == 'None':
                continue
            if isinstance(val, dict):
                url = val.get('url') or val.get('path')
                if url:
                    return url
                continue
            return val
    return None


def _normalize_photo(photo) -> Any:
    if isinstance(photo, dict):
        return photo.get('url') or photo.get('path') or photo
    return photo


def flatten_inspection_photos(data: dict) -> list:
    """Collect photos from all inspection items (preserving item labels)."""
    out = []
    for idx, item in enumerate(data.get('items') or [], start=1):
        if not isinstance(item, dict):
            continue
        photos = item.get('photos') or item.get('photo_urls') or item.get('photoUrls') or []
        asset = item.get('asset') or item.get('system') or f'Item {idx}'
        for p in photos:
            url = _normalize_photo(p)
            if url:
                out.append({'url': url, 'label': asset, 'raw': p})
    return out


def map_inspection_to_sr_data(data: dict) -> tuple[dict, types.SimpleNamespace, list]:
    """
    Map Fire Systems inspection form_data → (sr_data, ctx, materials).

    Type of Job is always ``inspection``.
    """
    site = (data.get('site_name') or '').strip() or 'Fire Systems Site'
    visit = (data.get('visit_date') or '').strip()
    submission_id = (
        data.get('submission_id')
        or data.get('job_no')
        or data.get('report_id')
        or ''
    )

    # Comments: item findings + optional supervisor note
    comment_lines = []
    for item in data.get('items') or []:
        if not isinstance(item, dict):
            continue
        asset = (item.get('asset') or '').strip()
        system = (item.get('system') or '').strip()
        desc = (item.get('description') or '').strip()
        remarks = (item.get('comments') or '').strip()
        label = ' / '.join(p for p in (system, asset) if p) or 'Item'
        bits = [b for b in (desc, remarks) if b and b not in ('N/A', '—')]
        if bits:
            comment_lines.append(f"{label}: {' — '.join(bits)}")
    supervisor_comments = _first_present(data, ('supervisor_comments',))
    if supervisor_comments and str(supervisor_comments).strip():
        comment_lines.append(f"Supervisor: {str(supervisor_comments).strip()}")

    # Parts required from materials_required
    parts_required = []
    for m in data.get('materials_required') or []:
        if not isinstance(m, dict):
            continue
        name = (m.get('name') or m.get('material_name') or '').strip()
        if not name:
            continue
        brand = (m.get('brand') or '').strip()
        uom = (m.get('uom') or '').strip()
        spec = ' / '.join(p for p in (brand, uom) if p)
        parts_required.append({
            'part': name,
            'specification': spec,
            'qty': m.get('quantity', ''),
        })

    tech_name = (
        data.get('technician_name')
        or data.get('submitted_by_name')
        or data.get('engineer_name')
        or ''
    )
    tech_sig = _first_present(data, ('tech_signature', 'technician_signature'))

    # Optional SR fields if already present on form_data (future-proof)
    fire_alarm = data.get('fire_alarm') if isinstance(data.get('fire_alarm'), dict) else {
        'qty': '', 'type': '', 'make': '', 'zones_loops': '',
    }
    fire_fighting = data.get('fire_fighting') if isinstance(data.get('fire_fighting'), dict) else {
        'fire_extinguisher': False,
        'gas_suppression': False,
        'hose_reel': False,
        'kitchen_hood': False,
        'sprinkler': False,
        'wet_dry_riser': False,
        'fire_pump_set': False,
        'others': False,
        'others_text': '',
    }

    sr_data = {
        'client_name': data.get('client_name') or site,
        'job_no': submission_id or site,
        'site_name': site,
        'location': data.get('location') or '',
        'technician_name': tech_name,
        'service_date': visit,
        'time_arrive': data.get('time_arrive') or {'h': None, 'm': None},
        'time_left': data.get('time_left') or {'h': None, 'm': None},
        'travel_time': data.get('travel_time') or {'h': None, 'm': None},
        'total_time': data.get('total_time') or {'h': None, 'm': None},
        'fire_alarm': fire_alarm,
        'fire_fighting': fire_fighting,
        'job_type': 'inspection',
        'job_type_other': '',
        'job_name': data.get('job_name') or 'Fire Systems Inspection',
        'comments': '\n'.join(comment_lines),
        'parts_required': parts_required,
        'customer_remarks': data.get('customer_remarks') or '',
        'client_mobile': data.get('client_mobile') or '',
        'technician_id_no': data.get('technician_id_no') or '',
        'service_report_no': data.get('service_report_no') or submission_id or '',
    }

    ctx = types.SimpleNamespace(
        ticket_id=submission_id or site,
        project=site,
        property_name=site,
        zone=None,
        sub_zone=None,
        base_unit=None,
        technician=None,
        assigned_to=None,
        client_signed_by=data.get('client_signed_by') or '',
        client_signature=data.get('client_signature'),
        client_mobile=sr_data['client_mobile'],
        close_signed_by=tech_name,
        close_signature=tech_sig,
        technician_id_no=sr_data['technician_id_no'],
    )

    # Parts Used — inspection typically has none; keep empty list
    materials: list = []
    return sr_data, ctx, materials


def _heading(text: str) -> Paragraph:
    return Paragraph(
        text,
        ParagraphStyle(
            'InspP2H',
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=RED,
            spaceAfter=4,
            spaceBefore=2,
        ),
    )


def _body(text: str, bold: bool = False) -> Paragraph:
    return Paragraph(
        text or '—',
        ParagraphStyle(
            'InspP2B',
            fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=DARK,
        ),
    )


def _muted(text: str) -> Paragraph:
    return Paragraph(
        text,
        ParagraphStyle(
            'InspP2M',
            fontName='Helvetica-Oblique',
            fontSize=8,
            textColor=MUTED,
        ),
    )


def _photo_flowable(photo_info, max_w=80 * mm, max_h=55 * mm):
    try:
        raw = photo_info.get('raw') if isinstance(photo_info, dict) else photo_info
        img_data, is_stream = get_image_for_pdf(raw if raw is not None else photo_info)
        if not img_data:
            return None
        if is_stream and hasattr(img_data, 'seek'):
            img_data.seek(0)
        img = RLImage(img_data)
        iw = getattr(img, 'imageWidth', None) or max_w
        ih = getattr(img, 'imageHeight', None) or max_h
        if iw <= 0 or ih <= 0:
            return None
        scale = min(max_w / iw, max_h / ih, 1.0)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        return img
    except Exception as exc:
        logger.warning('Inspection photo load failed: %s', exc)
        return None


def build_inspection_page2_story(data: dict) -> list:
    """Page 2: photos (if any) + workflow signature blocks."""
    story = []
    site = data.get('site_name') or 'Fire Systems'
    story.append(_heading('Fire Systems Inspection — Attachments & Approvals'))
    story.append(_muted(f'Site: {site}'))
    story.append(Spacer(1, 3 * mm))

    # Photos
    photos = flatten_inspection_photos(data)
    story.append(_heading('Inspection Photos'))
    if not photos:
        story.append(_muted('No photos attached.'))
        story.append(Spacer(1, 4 * mm))
    else:
        story.append(_muted(f'{len(photos)} photo(s)'))
        story.append(Spacer(1, 2 * mm))
        row = []
        for i, ph in enumerate(photos):
            cell_bits = []
            label = ph.get('label') if isinstance(ph, dict) else ''
            if label:
                cell_bits.append(_body(str(label), bold=True))
            img = _photo_flowable(ph)
            if img:
                cell_bits.append(img)
            else:
                cell_bits.append(_muted('Photo unavailable'))
            inner = Table([[b] for b in cell_bits], colWidths=[AVAIL_W * 0.48])
            inner.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('BOX', (0, 0), (-1, -1), 0.4, RULE),
            ]))
            row.append(inner)
            if len(row) == 2 or i == len(photos) - 1:
                while len(row) < 2:
                    row.append('')
                tbl = Table([row], colWidths=[AVAIL_W * 0.5, AVAIL_W * 0.5])
                tbl.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 1),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 1),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 2.5 * mm))
                row = []

    story.append(Spacer(1, 3 * mm))
    story.append(_heading('Approval Signatures'))
    story.append(Spacer(1, 2 * mm))

    for role, sig_keys, comment_keys in _WORKFLOW_ROLES:
        sig = _first_present(data, sig_keys)
        comments = _first_present(data, comment_keys) or ''
        sig_img = _load_sig_image(sig, width=50 * mm, height=16 * mm)
        right = sig_img if sig_img else _muted('Not signed')
        comments_para = _body(str(comments).strip() if comments else '—')
        block = Table(
            [
                [_body(role, bold=True), ''],
                [_muted('Comments'), comments_para],
                [_muted('Signature'), right],
            ],
            colWidths=[AVAIL_W * 0.22, AVAIL_W * 0.78],
        )
        block.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, RULE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(block)
        story.append(Spacer(1, 3 * mm))

    return story


def build_inspection_service_report_pdf(data: dict, output_path: str) -> str:
    """
    Write Fire Systems inspection PDF: Service Report page 1 + page 2 attachments.
    Returns output_path.
    """
    sr_data, ctx, materials = map_inspection_to_sr_data(data)
    logo_path = _find_logo_path()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=f"Fire Systems Inspection — {sr_data.get('site_name') or 'Report'}",
    )

    story = build_service_report_page1_story(sr_data, ctx, materials, logo_path=logo_path)
    story.append(PageBreak())
    story.extend(build_inspection_page2_story(data))

    doc.build(story, canvasmaker=_SRCanvas)
    return output_path


def build_inspection_service_report_bytes(data: dict) -> bytes:
    buf = BytesIO()
    sr_data, ctx, materials = map_inspection_to_sr_data(data)
    logo_path = _find_logo_path()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=f"Fire Systems Inspection — {sr_data.get('site_name') or 'Report'}",
    )
    story = build_service_report_page1_story(sr_data, ctx, materials, logo_path=logo_path)
    story.append(PageBreak())
    story.extend(build_inspection_page2_story(data))
    doc.build(story, canvasmaker=_SRCanvas)
    return buf.getvalue()
