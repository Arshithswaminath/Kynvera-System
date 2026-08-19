"""QR label generation for FM assets.

QR payloads are public URLs (`/assets/tag/<asset_id>`) so a normal phone camera
opens an operational summary. `qr_code` remains a human-readable sticker label.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Iterable, Union
from urllib.parse import unquote

from flask import current_app, has_app_context
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdf_canvas

from common.kynvera_pdf_brand import PRIMARY, TEXT_DARK, TEXT_MID, HAIRLINE

AssetLike = Union[object, str]

_TAG_PATH_RE = re.compile(r'/assets/tag/([^/?#]+)', re.IGNORECASE)
_AST_EXACT_RE = re.compile(r'^AST-\d+$', re.IGNORECASE)
_AST_FIND_RE = re.compile(r'AST-\d+', re.IGNORECASE)

# Compact printable sticker (Avery-style)
LABEL_PAGE = (88 * mm, 50 * mm)


def _app_base_url(base_url: str | None = None) -> str:
    if base_url:
        return str(base_url).rstrip('/')
    if has_app_context():
        return (current_app.config.get('APP_BASE_URL') or '').rstrip('/')
    return ''


def asset_id_of(asset: AssetLike) -> str:
    if hasattr(asset, 'asset_id'):
        return (getattr(asset, 'asset_id') or '').strip()
    return str(asset or '').strip()


def public_asset_url(asset: AssetLike, base_url: str | None = None) -> str:
    """Absolute URL encoded into the QR (phone-camera destination)."""
    aid = asset_id_of(asset)
    return f'{_app_base_url(base_url)}/assets/tag/{aid}'


def ensure_asset_qr_code(asset) -> str | None:
    """Set `QR-{asset_id}` when the human label is empty. Does not commit."""
    existing = (getattr(asset, 'qr_code', None) or '').strip()
    if existing:
        asset.qr_code = existing
        return existing
    aid = asset_id_of(asset)
    if not aid:
        return None
    asset.qr_code = f'QR-{aid}'
    return asset.qr_code


def parse_scanned_asset_code(raw: str | None) -> str:
    """Normalize a scan (public URL, asset ID, or QR label) for lookup."""
    code = (raw or '').strip()
    if not code:
        return ''
    match = _TAG_PATH_RE.search(code)
    if match:
        return unquote(match.group(1)).strip()
    if _AST_EXACT_RE.match(code):
        return code.upper()
    found = _AST_FIND_RE.search(code)
    if found:
        return found.group(0).upper()
    return code


def qr_png_bytes(payload: str, box_size: int = 8, border: int = 2) -> bytes:
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    if hasattr(img, 'convert'):
        img = img.convert('RGB')
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def asset_qr_png_bytes(asset, base_url: str | None = None) -> bytes:
    return qr_png_bytes(public_asset_url(asset, base_url=base_url))


def _fmt_date(val) -> str:
    if not val:
        return ''
    if hasattr(val, 'isoformat'):
        return val.isoformat()[:10]
    return str(val).strip()[:10]


def asset_text_payload(asset) -> str:
    """Plain-text QR body so a phone camera shows a summary without opening a browser."""
    lines = ['Kynvera asset', asset_id_of(asset)]
    name = (getattr(asset, 'name', None) or '').strip()
    if name:
        lines.append(name[:80])
    kind = (getattr(asset, 'asset_type', None) or '').strip()
    if kind:
        lines.append(kind)
    loc = asset_location_line(asset)
    if loc:
        lines.append(loc)
    spec = ' '.join(
        p for p in (
            (getattr(asset, 'manufacturer', None) or '').strip(),
            (getattr(asset, 'model', None) or '').strip(),
        ) if p
    )
    if spec:
        lines.append(spec)
    serial = (getattr(asset, 'serial_number', None) or '').strip()
    if serial:
        lines.append(f'SN {serial}')
    status = (getattr(asset, 'status', None) or 'active').strip()
    health = getattr(asset, 'health_score', None)
    if health is not None:
        lines.append(f'Status {status} · health {health}/100')
    else:
        lines.append(f'Status {status}')
    warranty = _fmt_date(getattr(asset, 'warranty_expiry', None))
    if warranty:
        lines.append(f'Warranty {warranty}')
    text = '\n'.join(lines)
    return text[:400]


def asset_text_qr_png_bytes(asset) -> bytes:
    return qr_png_bytes(asset_text_payload(asset))


def asset_location_line(asset) -> str:
    parts = [
        p for p in (
            getattr(asset, 'building', None),
            getattr(asset, 'floor', None),
            getattr(asset, 'room', None),
        ) if p
    ]
    return ' / '.join(parts)


def _fit_width(text: str | None, font: str, size: float, max_w: float) -> str:
    value = (text or '').strip()
    if not value:
        return ''
    if stringWidth(value, font, size) <= max_w:
        return value
    ell = '…'
    while value and stringWidth(value + ell, font, size) > max_w:
        value = value[:-1]
    return (value + ell) if value else ''


def _label_detail_lines(asset) -> list[str]:
    """Operational lines for the sticker (skip empty / financial fields)."""
    lines: list[str] = []
    kind = (getattr(asset, 'asset_type', None) or '').strip()
    status = (getattr(asset, 'status', None) or '').strip()
    health = getattr(asset, 'health_score', None)
    meta = []
    if kind:
        meta.append(kind)
    if status:
        meta.append(status)
    if health is not None:
        meta.append(f'health {health}/100')
    if meta:
        lines.append(' · '.join(meta))
    loc = asset_location_line(asset)
    if loc:
        lines.append(loc)
    spec = ' '.join(
        p for p in (
            (getattr(asset, 'manufacturer', None) or '').strip(),
            (getattr(asset, 'model', None) or '').strip(),
        ) if p
    )
    if spec:
        lines.append(spec)
    serial = (getattr(asset, 'serial_number', None) or '').strip()
    if serial:
        lines.append(f'SN {serial}')
    installed = _fmt_date(getattr(asset, 'installation_date', None))
    warranty = _fmt_date(getattr(asset, 'warranty_expiry', None))
    dates = []
    if installed:
        dates.append(f'Inst {installed}')
    if warranty:
        dates.append(f'Warr {warranty}')
    if dates:
        lines.append(' · '.join(dates))
    return lines


def _draw_sticker(c: pdf_canvas.Canvas, asset, x: float, y: float, w: float, h: float):
    """Draw one compact QR sticker (origin = bottom-left of cell)."""
    pad = 2.2 * mm
    gutter = 2.0 * mm
    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(0.5)
    c.roundRect(x, y, w, h, 1.4 * mm, stroke=1, fill=0)

    qr_size = min(h - 2 * pad, 28 * mm)
    png = asset_qr_png_bytes(asset)
    reader = ImageReader(BytesIO(png))
    c.drawImage(
        reader,
        x + pad,
        y + h - pad - qr_size,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask='auto',
    )

    tx = x + pad + qr_size + gutter
    tw = max(12 * mm, w - (tx - x) - pad)
    ty = y + h - pad - 2.4 * mm
    leading_sm = 3.15 * mm
    footer_y = y + pad + 0.4 * mm

    c.setFillColor(TEXT_MID)
    c.setFont('Helvetica', 6)
    c.drawString(tx, ty, _fit_width('Kynvera asset', 'Helvetica', 6, tw))
    ty -= 3.6 * mm

    c.setFillColor(PRIMARY)
    c.setFont('Helvetica-Bold', 10)
    c.drawString(tx, ty, _fit_width(asset_id_of(asset), 'Helvetica-Bold', 10, tw))
    ty -= 3.8 * mm

    c.setFillColor(TEXT_DARK)
    c.setFont('Helvetica-Bold', 8)
    name = (getattr(asset, 'name', None) or '').strip()
    if name:
        for part in _wrap(name, max(12, int(tw / 3.3)))[:2]:
            if ty < footer_y + 4 * mm:
                break
            c.drawString(tx, ty, _fit_width(part, 'Helvetica-Bold', 8, tw))
            ty -= 3.3 * mm

    c.setFillColor(TEXT_MID)
    c.setFont('Helvetica', 6.5)
    for line in _label_detail_lines(asset):
        if ty < footer_y + 3.6 * mm:
            break
        for part in _wrap(line, max(14, int(tw / 3.0)))[:2]:
            if ty < footer_y + 3.6 * mm:
                break
            c.drawString(tx, ty, _fit_width(part, 'Helvetica', 6.5, tw))
            ty -= leading_sm

    label = (getattr(asset, 'qr_code', None) or '').strip()
    if label:
        c.setFillColor(TEXT_MID)
        c.setFont('Helvetica', 6)
        c.drawString(tx, footer_y, _fit_width(label, 'Helvetica', 6, tw))


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ''
    for word in words:
        trial = f'{current} {word}'.strip()
        if len(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def build_single_label_pdf(asset) -> bytes:
    buf = BytesIO()
    page_w, page_h = LABEL_PAGE
    c = pdf_canvas.Canvas(buf, pagesize=LABEL_PAGE)
    c.setTitle(f'{asset_id_of(asset)} QR label')
    _draw_sticker(c, asset, 1.2 * mm, 1.2 * mm, page_w - 2.4 * mm, page_h - 2.4 * mm)
    c.save()
    buf.seek(0)
    return buf.getvalue()


def build_bulk_labels_pdf(assets: Iterable) -> bytes:
    rows_list = list(assets)
    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    c.setTitle('Asset QR labels')
    page_w, page_h = A4
    cols, rows = 2, 5
    margin = 6 * mm
    gap = 2.4 * mm
    cell_w = (page_w - 2 * margin - gap) / cols
    cell_h = (page_h - 2 * margin - (rows - 1) * gap) / rows

    if not rows_list:
        c.setFillColor(TEXT_MID)
        c.setFont('Helvetica', 12)
        c.drawString(margin, page_h - 30 * mm, 'No assets to print.')
        c.save()
        buf.seek(0)
        return buf.getvalue()

    per_page = cols * rows
    for i, asset in enumerate(rows_list):
        if i and i % per_page == 0:
            c.showPage()
        pos = i % per_page
        col = pos % cols
        row = pos // cols
        x = margin + col * (cell_w + gap)
        y = page_h - margin - (row + 1) * cell_h - row * gap
        _draw_sticker(c, asset, x, y, cell_w, cell_h)

    c.save()
    buf.seek(0)
    return buf.getvalue()
