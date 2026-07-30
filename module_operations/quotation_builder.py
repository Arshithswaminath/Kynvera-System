"""Amaan sales quotation PDF — matches client New Quotation Format.xls layout."""
from __future__ import annotations

import base64
import io
import logging
import os
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

INK = colors.HexColor('#111827')
BRAND = colors.HexColor('#a8121e')
RULE = colors.HexColor('#d1d5db')
MUTED = colors.HexColor('#6b7280')
HEADER_BG = colors.HexColor('#a8121e')
ROW_ALT = colors.HexColor('#fafafa')
STAMP_BOX = colors.HexColor('#f3f4f6')

_ONES = (
    '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
    'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
    'Seventeen', 'Eighteen', 'Nineteen',
)
_TENS = (
    '', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety',
)


def _words_under_1000(n: int) -> str:
    n = int(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + (' ' + _ONES[n % 10] if n % 10 else '')).strip()
    hund = _ONES[n // 100] + ' Hundred'
    rest = n % 100
    if rest:
        return hund + ' ' + _words_under_1000(rest)
    return hund


def amount_to_aed_words(amount) -> str:
    """Convert a number to English AED amount-in-words (no fils)."""
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    whole = int(round(value))
    if whole == 0:
        return 'Zero Only'
    parts = []
    billions = whole // 1_000_000_000
    millions = (whole % 1_000_000_000) // 1_000_000
    thousands = (whole % 1_000_000) // 1000
    rem = whole % 1000
    if billions:
        parts.append(_words_under_1000(billions) + ' Billion')
    if millions:
        parts.append(_words_under_1000(millions) + ' Million')
    if thousands:
        parts.append(_words_under_1000(thousands) + ' Thousand')
    if rem:
        parts.append(_words_under_1000(rem))
    return ' '.join(parts) + ' Only'


def _fmt_date(d) -> str:
    if not d:
        return '—'
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime('%d/%m/%Y')
    return str(d)


def _fmt_money(v) -> str:
    try:
        return f'{float(v or 0):,.2f}'
    except (TypeError, ValueError):
        return '0.00'


def _p(text, size=9, bold=False, color=INK, align=TA_LEFT, leading=None):
    style = ParagraphStyle(
        'qt_p',
        fontName='Helvetica-Bold' if bold else 'Helvetica',
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=leading or (size + 3),
    )
    return Paragraph((text or '').replace('\n', '<br/>'), style)


def _find_logo():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in (
        'static/icons/Amaan-logo-tight.png',
        'static/icons/Amaan.png',
        'static/icons/Amaan-logo-report.png',
        'static/logo.png',
    ):
        path = os.path.join(root, rel)
        if os.path.exists(path):
            return path
    return None


def _find_stamp():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'static/icons/Amaan-stamp.png')
    return path if os.path.exists(path) else None


def _load_sig_image(b64_data, width=40 * mm, height=14 * mm):
    if not b64_data or not str(b64_data).startswith('data:image'):
        return None
    try:
        raw = b64_data.split(',', 1)[1] if ',' in b64_data else b64_data
        return RLImage(io.BytesIO(base64.b64decode(raw)), width=width, height=height)
    except Exception as e:
        logger.warning('Could not decode quotation signature for PDF: %s', e)
        return None


def _stamp_cell():
    stamp_path = _find_stamp()
    if stamp_path:
        try:
            img = RLImage(stamp_path, width=28 * mm, height=28 * mm)
            return Table([[img]], colWidths=[36 * mm])
        except Exception as e:
            logger.warning('Could not load stamp image: %s', e)
    inner = Table(
        [
            [_p('COMPANY', 7, bold=True, color=MUTED, align=TA_CENTER)],
            [_p('STAMP', 10, bold=True, color=BRAND, align=TA_CENTER)],
            [_p('Place stamp file at\nstatic/icons/Amaan-stamp.png', 6, color=MUTED, align=TA_CENTER)],
        ],
        colWidths=[36 * mm],
    )
    inner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), STAMP_BOX),
        ('BOX', (0, 0), (-1, -1), 0.8, BRAND),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return inner


def _sig_column(role, name, sig_date, signature=None):
    sig_img = _load_sig_image(signature)
    sig_cell = sig_img if sig_img is not None else Spacer(1, 12 * mm)
    rows = [
        [_p(role, 7.5, bold=True, color=colors.white, align=TA_CENTER)],
        [_p(name or '—', 8.5, bold=True)],
        [sig_cell],
        [HRFlowable(width='100%', thickness=0.5, color=RULE)],
        [_p(_fmt_date(sig_date), 7.5, color=MUTED)],
    ]
    t = Table(rows, colWidths=[52 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), BRAND),
        ('BOX', (0, 0), (-1, -1), 0.5, RULE),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _section(title, body):
    if not (body or '').strip():
        return []
    return [
        Spacer(1, 6),
        _p(title, 10, bold=True, color=BRAND),
        Spacer(1, 2),
        _p(body.strip(), 8.5, color=INK, leading=12),
    ]


def build_quotation_pdf(quotation, output_path: str) -> str:
    """Write quotation PDF to output_path and return the path."""
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    from app.models import (
        QUOTATION_DEFAULT_EXCLUSIONS,
        QUOTATION_DEFAULT_INTRO,
        QUOTATION_DEFAULT_NOTES,
        QUOTATION_DEFAULT_SIGNATORY_EMAIL,
        QUOTATION_DEFAULT_SIGNATORY_NAME,
        QUOTATION_DEFAULT_SIGNATORY_PHONE,
        QUOTATION_DEFAULT_TERMS,
    )

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    avail = A4[0] - 32 * mm
    story = []

    logo_path = _find_logo()
    logo_cell = Spacer(1, 1)
    if logo_path:
        try:
            logo_cell = RLImage(logo_path, width=38 * mm, height=18 * mm)
        except Exception:
            logo_cell = Spacer(1, 1)

    ref_no = (getattr(quotation, 'ref_no', None) or quotation.quote_no or '—').strip()
    q_date = _fmt_date(quotation.quote_date)
    right_meta = Table(
        [
            [_p('QUOTATION / PROPOSAL', 14, bold=True, color=BRAND, align=TA_RIGHT)],
            [_p(f'Ref no: {ref_no}', 9, bold=True, align=TA_RIGHT)],
            [_p(f'Date: {q_date}', 9, align=TA_RIGHT)],
            [_p(f'Status: {(quotation.status or "").upper()}', 8, color=MUTED, align=TA_RIGHT)],
        ],
        colWidths=[110 * mm],
    )
    head = Table([[logo_cell, right_meta]], colWidths=[60 * mm, avail - 60 * mm])
    head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(head)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width='100%', thickness=2, color=BRAND, spaceAfter=8))

    company = quotation.company_name or '—'
    kind_attn = getattr(quotation, 'kind_attn', None) or quotation.contact_name or '—'
    tel = getattr(quotation, 'client_tel', None) or '—'
    subject = getattr(quotation, 'subject', None) or '—'
    project = getattr(quotation, 'project_name', None) or (
        quotation.bd_project.name if getattr(quotation, 'bd_project', None) else '—'
    )
    intro = (getattr(quotation, 'intro_text', None) or QUOTATION_DEFAULT_INTRO).strip()

    client_block = [
        [_p(f'<b>Client Name</b>  {company}', 9)],
        [_p(f'<b>Kind Attn:</b>  {kind_attn}', 9)],
        [_p(f'<b>Tel:</b>  {tel}', 9)],
        [Spacer(1, 4)],
        [_p(f'<b>Subject:</b>  {subject}', 9)],
        [_p(f'<b>Project:</b>  {project}', 9)],
    ]
    story.append(Table(client_block, colWidths=[avail]))
    story.append(Spacer(1, 6))
    story.append(_p(intro, 9, leading=13))
    story.append(Spacer(1, 8))

    headers = [
        _p('<b>S.No.</b>', 8, bold=True, color=colors.white, align=TA_CENTER),
        _p('<b>Description</b>', 8, bold=True, color=colors.white),
        _p('<b>Qty.</b>', 8, bold=True, color=colors.white, align=TA_CENTER),
        _p('<b>U.Price</b>', 8, bold=True, color=colors.white, align=TA_RIGHT),
        _p('<b>Total</b>', 8, bold=True, color=colors.white, align=TA_RIGHT),
    ]
    rows = [headers]
    items = list(quotation.items or [])
    if not items:
        rows.append([
            _p('—', 8, color=MUTED, align=TA_CENTER),
            _p('No line items', 8, color=MUTED),
            '', '', '',
        ])
    else:
        for i, item in enumerate(items, 1):
            rows.append([
                _p(str(i), 8.5, align=TA_CENTER),
                _p(item.description or '', 8.5),
                _p(f'{item.quantity or 0:g}', 8.5, align=TA_CENTER),
                _p(_fmt_money(item.unit_price), 8.5, align=TA_RIGHT),
                _p(_fmt_money(item.total_price), 8.5, align=TA_RIGHT),
            ])

    col_w = [12 * mm, avail - 70 * mm, 14 * mm, 22 * mm, 22 * mm]
    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('GRID', (0, 0), (-1, -1), 0.4, RULE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    for r in range(1, len(rows)):
        if r % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, r), (-1, r), ROW_ALT))
    tbl.setStyle(TableStyle(style_cmds))
    story.append(tbl)
    story.append(Spacer(1, 8))

    subtotal = float(quotation.subtotal or 0)
    discount = float(getattr(quotation, 'discount_amount', None) or 0)
    final_ex_vat = round(max(subtotal - discount, 0), 2)
    words = (getattr(quotation, 'amount_in_words', None) or '').strip() or amount_to_aed_words(final_ex_vat)

    totals = Table(
        [
            [_p('Total', 9, bold=True), _p(f'AED {_fmt_money(subtotal)}', 9, bold=True, align=TA_RIGHT)],
            [_p('Discounted amount', 9), _p(f'AED {_fmt_money(discount)}', 9, align=TA_RIGHT)],
            [
                _p('Final Price After Discount', 9.5, bold=True, color=BRAND),
                _p(f'AED {_fmt_money(final_ex_vat)}+VAT', 9.5, bold=True, color=BRAND, align=TA_RIGHT),
            ],
            [_p(words, 9, bold=True, color=INK), ''],
        ],
        colWidths=[avail - 45 * mm, 45 * mm],
    )
    totals.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, 2), (-1, 2), 0.8, BRAND),
        ('SPAN', (0, 3), (-1, 3)),
    ]))
    story.append(totals)

    notes = getattr(quotation, 'notes_text', None) or quotation.notes or QUOTATION_DEFAULT_NOTES
    exclusions = getattr(quotation, 'exclusions_text', None) or QUOTATION_DEFAULT_EXCLUSIONS
    terms = getattr(quotation, 'terms_text', None) or QUOTATION_DEFAULT_TERMS
    story.extend(_section('NOTE :', notes))
    story.extend(_section('EXCLUSION', exclusions))
    story.extend(_section('TERMS & CONDITIONS', terms))

    story.append(Spacer(1, 12))
    story.append(_p('Thanks & Regards', 9, bold=True))
    story.append(Spacer(1, 6))

    sig_name = getattr(quotation, 'signatory_name', None) or QUOTATION_DEFAULT_SIGNATORY_NAME
    sig_email = getattr(quotation, 'signatory_email', None) or QUOTATION_DEFAULT_SIGNATORY_EMAIL
    sig_phone = getattr(quotation, 'signatory_phone', None) or QUOTATION_DEFAULT_SIGNATORY_PHONE
    prepared_sig = getattr(quotation, 'prepared_signature', None)
    approval_sig = getattr(quotation, 'approval_signature', None)
    approver_name = None
    if getattr(quotation, 'approved_by', None):
        approver_name = quotation.approved_by.full_name or quotation.approved_by.username
    prepared_date = getattr(quotation, 'submitted_at', None) or quotation.quote_date
    approved_date = getattr(quotation, 'approved_at', None)

    sig_row = Table(
        [[
            _stamp_cell(),
            _sig_column('Prepared by', sig_name, prepared_date, prepared_sig),
            _sig_column('Approved by', approver_name or 'Pending', approved_date, approval_sig),
        ]],
        colWidths=[40 * mm, 58 * mm, 58 * mm],
    )
    sig_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(KeepTogether([sig_row]))
    story.append(Spacer(1, 6))
    story.append(_p(sig_name, 9, bold=True))
    story.append(_p(sig_email, 8, color=MUTED))
    story.append(_p(sig_phone, 8, color=MUTED))

    doc.build(story)
    return output_path
