"""Project pack PDF: identity, locations, assets, 2D drawings, and tickets."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from datetime import datetime, timezone

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
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
from sqlalchemy import or_

from app.models import Asset, FloorPlan, Ticket, TicketProject, TicketProperty
from common import kynvera_pdf_brand as brand

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
_KEEP = []


class _PackCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        self._heading = kwargs.pop('heading', 'Project pack')
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._paint(total)
            super().showPage()
        super().save()

    def _paint(self, total):
        self.saveState()
        ink = getattr(brand, 'TEXT_DARK', colors.HexColor('#191b23'))
        muted = getattr(brand, 'TEXT_MUTED', colors.HexColor('#9498a3'))
        coral = getattr(brand, 'PRIMARY', colors.HexColor('#ff8e68'))
        hair = getattr(brand, 'HAIRLINE', colors.HexColor('#e9eaee'))
        self.setStrokeColor(coral)
        self.setLineWidth(2.2)
        self.line(0, PAGE_H - 1, PAGE_W, PAGE_H - 1)
        logo_path = brand.resolve_logo_path(prefer_wordmark=True)
        y = PAGE_H - 14 * mm
        if logo_path and os.path.isfile(logo_path):
            try:
                self.drawImage(
                    logo_path, MARGIN, y - 1.2 * mm,
                    width=32 * mm, height=8 * mm,
                    preserveAspectRatio=True, mask='auto',
                )
            except Exception:
                logo_path = None
        if not logo_path:
            self.setFont('Helvetica-Bold', 10)
            self.setFillColor(ink)
            self.drawString(MARGIN, y + 1 * mm, 'Kynvera')
        right = f'Project pack / {self._heading}'
        if len(right) > 58:
            right = right[:55] + '…'
        self.setFont('Helvetica', 8)
        self.setFillColor(muted)
        self.drawRightString(PAGE_W - MARGIN, y + 1.5 * mm, right)
        self.setStrokeColor(hair)
        self.setLineWidth(0.4)
        self.line(MARGIN, PAGE_H - 18 * mm, PAGE_W - MARGIN, PAGE_H - 18 * mm)
        self.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
        self.setFont('Helvetica', 7.5)
        self.setFillColor(muted)
        self.drawString(MARGIN, 7.5 * mm, 'Kynvera — Confidential')
        self.drawRightString(PAGE_W - MARGIN, 7.5 * mm, f'Page {self._pageNumber} of {total}')
        self.restoreState()


def _esc(value) -> str:
    text = '—' if value is None or value == '' else str(value)
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('\n', '<br/>')
    )


def _styles():
    base = getSampleStyleSheet()
    ink = getattr(brand, 'TEXT_DARK', colors.HexColor('#191b23'))
    muted_c = getattr(brand, 'TEXT_MUTED', colors.HexColor('#9498a3'))
    heading = ParagraphStyle(
        'PackH', parent=base['Heading2'], fontSize=10, textColor=ink,
        spaceBefore=0, spaceAfter=2, fontName='Helvetica-Bold',
        leading=12,
    )
    body = ParagraphStyle(
        'PackBody', parent=base['Normal'], fontSize=8.5, leading=12, textColor=ink,
    )
    muted = ParagraphStyle(
        'PackMuted', parent=body, textColor=muted_c, fontSize=8, leading=11,
    )
    cell = ParagraphStyle(
        'PackCell', parent=body, fontSize=8, leading=11,
    )
    title = ParagraphStyle(
        'PackTitle', parent=base['Title'], fontSize=20, leading=24, textColor=ink,
        alignment=TA_LEFT, spaceAfter=2, fontName='Helvetica-Bold',
    )
    kpi_n = ParagraphStyle(
        'PackKpiN', parent=body, fontSize=16, leading=18, fontName='Helvetica-Bold',
        alignment=TA_CENTER, textColor=ink,
    )
    kpi_l = ParagraphStyle(
        'PackKpiL', parent=muted, fontSize=7, leading=9, alignment=TA_CENTER,
    )
    return heading, body, muted, cell, title, kpi_n, kpi_l


def _wash():
    return getattr(brand, 'SOFT_WASH', colors.HexColor('#fff4ef'))


def _alt():
    return getattr(brand, 'SURFACE_ALT', colors.HexColor('#fafafb'))


def _line():
    return getattr(brand, 'HAIRLINE', colors.HexColor('#e9eaee'))


def _section(label, heading):
    coral = getattr(brand, 'PRIMARY', colors.HexColor('#ff8e68'))
    return [
        Spacer(1, 12),
        Paragraph(_esc(label), heading),
        HRFlowable(
            width=22 * mm, thickness=1.6, color=coral,
            spaceBefore=1, spaceAfter=8, hAlign='LEFT',
        ),
    ]


def _kpi_strip(items, kpi_n, kpi_l, width):
    col = width / max(len(items), 1)
    cells = []
    for n, label in items:
        inner = Table(
            [[Paragraph(_esc(n), kpi_n)], [Paragraph(_esc(label), kpi_l)]],
            colWidths=[col - 4],
        )
        inner.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        cells.append(inner)
    table = Table([cells], colWidths=[col] * len(items))
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), _wash()),
        ('BOX', (0, 0), (-1, -1), 0.4, _line()),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, _line()),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    return table


def _kv_table(pairs, body):
    label = ParagraphStyle('PackLabel', parent=body, textColor=getattr(brand, 'TEXT_MUTED', colors.HexColor('#7a7f8c')), fontSize=7.5)
    value = ParagraphStyle('PackVal', parent=body, fontName='Helvetica-Bold', fontSize=8.5)
    data = [[Paragraph(_esc(k), label), Paragraph(_esc(v), value)] for k, v in pairs]
    half = int((len(data) + 1) // 2)
    left, right = data[:half], data[half:]
    while len(right) < len(left):
        right.append([Paragraph('', label), Paragraph('', value)])
    merged = [left[i] + right[i] for i in range(len(left))]
    w = (PAGE_W - 2 * MARGIN - 6) / 4
    table = Table(merged, colWidths=[w, w, w, w])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, _line()),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def _grid(headers, rows, cell, col_widths):
    head_style = ParagraphStyle(
        'PackHead', parent=cell, fontName='Helvetica-Bold', fontSize=7.5,
        textColor=getattr(brand, 'TEXT_MUTED', colors.HexColor('#7a7f8c')),
    )
    data = [[Paragraph(_esc(h), head_style) for h in headers]]
    for row in rows:
        data.append([Paragraph(_esc(c), cell) for c in row])
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _alt()]),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, getattr(brand, 'PRIMARY', colors.HexColor('#ff8e68'))),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, _line()),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return table


def _fmt_dt(value):
    if not value:
        return '—'
    try:
        return value.strftime('%d %b %Y %H:%M')
    except Exception:
        return str(value)


def _fmt_money(value):
    if value is None:
        return '—'
    try:
        return f'AED {float(value):,.2f}'
    except (TypeError, ValueError):
        return str(value)


_PIN_COLORS = {
    'ok': (22, 163, 74),
    'warn': (234, 88, 12),
    'crit': (220, 38, 38),
}
_PIN_COLOR_ALIASES = {
    'ok': 'ok', 'healthy': 'ok', 'good': 'ok', 'normal': 'ok',
    'warn': 'warn', 'warning': 'warn', 'caution': 'warn',
    'crit': 'crit', 'critical': 'crit', 'alarm': 'crit',
}
_PIN_STATUS = {
    'ok': 'Healthy',
    'warn': 'Watch',
    'crit': 'Critical',
}


def _hotspots(plan):
    raw = getattr(plan, 'hotspots', None) or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


def _pin_count(plan):
    return len(_hotspots(plan))


def _pin_severity(hs):
    raw = hs.get('live_severity') or hs.get('severity') or 'ok'
    return _PIN_COLOR_ALIASES.get(str(raw).lower(), 'ok')


def _pin_assets_label(hs, asset_by_code):
    ids = hs.get('asset_ids') or hs.get('assets') or []
    if isinstance(ids, str):
        ids = [ids]
    labels = []
    for code in ids:
        if isinstance(code, dict):
            code = code.get('asset_id') or code.get('id') or ''
        asset = asset_by_code.get(str(code))
        if asset:
            labels.append(f'{asset.asset_id} {asset.name}'.strip())
        elif code:
            labels.append(str(code))
    return ', '.join(labels) or '—'


def _pin_detail_rows(plan, asset_by_code):
    rows = []
    for i, hs in enumerate(_hotspots(plan), 1):
        if not isinstance(hs, dict):
            continue
        sev = _pin_severity(hs)
        try:
            x = float(hs.get('x_pct', hs.get('x', 0)))
            y = float(hs.get('y_pct', hs.get('y', 0)))
            pos = f'{x:.0f}%, {y:.0f}%'
        except (TypeError, ValueError):
            pos = '—'
        rows.append([
            str(i),
            hs.get('room') or hs.get('name') or hs.get('label') or f'Pin {i}',
            _PIN_STATUS[sev],
            _pin_assets_label(hs, asset_by_code),
            pos,
        ])
    return rows


def _pin_font(size):
    from PIL import ImageFont
    for path in (
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/Library/Fonts/Arial Bold.ttf',
        '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    ):
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _overlay_pins(im, hotspots):
    """Stamp twin pins onto a PIL image. Coordinates are percent of width/height."""
    if not hotspots:
        return im
    from PIL import ImageDraw
    rgb = im.convert('RGB')
    draw = ImageDraw.Draw(rgb)
    width, height = rgb.size
    radius = max(8, int(width * 0.0075))
    font_size = max(13, int(width * 0.011))
    font = _pin_font(font_size)
    num_font = _pin_font(max(10, int(radius * 1.15)))
    stroke = max(2, int(radius * 0.28))
    for idx, hs in enumerate(hotspots, 1):
        if not isinstance(hs, dict):
            continue
        try:
            x = float(hs.get('x_pct', hs.get('x', 0))) / 100.0 * width
            y = float(hs.get('y_pct', hs.get('y', 0))) / 100.0 * height
        except (TypeError, ValueError):
            continue
        x = max(radius, min(width - radius, x))
        y = max(radius, min(height - radius, y))
        sev = _pin_severity(hs)
        fill = _PIN_COLORS[sev]
        label = str(hs.get('room') or hs.get('name') or hs.get('label') or f'Pin {idx}').strip() or f'Pin {idx}'
        if len(label) > 28:
            label = label[:27] + '…'
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad_x, pad_y = max(6, int(font_size * 0.45)), max(3, int(font_size * 0.28))
        box_w, box_h = text_w + pad_x * 2, text_h + pad_y * 2
        box_x = min(width - box_w - 4, max(4, x - box_w / 2))
        box_y = max(4, y - radius - 8 - box_h)
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=6,
            fill=(25, 27, 35),
        )
        draw.text((box_x + pad_x, box_y + pad_y - bbox[1]), label, font=font, fill=(255, 255, 255))
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=fill,
            outline=(255, 255, 255),
            width=stroke,
        )
        num = str(idx)
        nb = draw.textbbox((0, 0), num, font=num_font)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        draw.text((x - nw / 2, y - nh / 2 - nb[1]), num, font=num_font, fill=(255, 255, 255))
    return rgb


def _stamped_plan_buffer(reader_src, hotspots):
    from PIL import Image as PILImage
    if isinstance(reader_src, io.BytesIO):
        reader_src.seek(0)
    im = PILImage.open(reader_src)
    im.load()
    stamped = _overlay_pins(im, hotspots)
    out = io.BytesIO()
    stamped.save(out, format='PNG')
    out.seek(0)
    _KEEP.append(out)
    return out


def _location_rows(project: TicketProject):
    rows = []
    props = project.properties.filter_by(is_active=True).order_by(TicketProperty.name)
    for prop in props:
        zones = list(prop.zones.filter_by(is_active=True).order_by('name'))
        if not zones:
            rows.append((prop.name, '—', '—', '—'))
            continue
        for zone in zones:
            subs = list(zone.sub_zones.filter_by(is_active=True).order_by('name'))
            if not subs:
                rows.append((prop.name, zone.name, '—', '—'))
                continue
            for sub in subs:
                units = list(sub.base_units.filter_by(is_active=True).order_by('name'))
                if not units:
                    rows.append((prop.name, zone.name, sub.name, '—'))
                    continue
                for unit in units:
                    rows.append((prop.name, zone.name, sub.name, unit.name))
    return rows


def _project_tickets(project: TicketProject):
    prop_ids = [p.id for p in project.properties]
    filters = [Ticket.project == project.name]
    if prop_ids:
        filters.append(Ticket.property_id.in_(prop_ids))
    return (
        Ticket.query.filter(or_(*filters))
        .order_by(Ticket.created_at.desc())
        .all()
    )


def _local_static_path(url: str):
    if not url or not url.startswith('/static/'):
        return None
    rel = url[len('/static/'):].replace('/', os.sep)
    folder = current_app.static_folder
    if not folder:
        return None
    path = os.path.join(folder, rel)
    return path if os.path.isfile(path) else None


def _plan_image(plan, max_w, max_h):
    src = (getattr(plan, 'image_url', None) or '').strip()
    if not src or 'svg' in src[:80].lower():
        return None
    reader_src = None
    if src.startswith('data:image/') and 'base64,' in src:
        try:
            raw = base64.b64decode(src.split('base64,', 1)[1])
            buf = io.BytesIO(raw)
            _KEEP.append(buf)
            reader_src = buf
        except Exception:
            return None
    elif src.startswith('/static/'):
        path = _local_static_path(src)
        if not path or path.lower().endswith('.svg'):
            return None
        reader_src = path
    else:
        return None
    pins = _hotspots(plan)
    if pins:
        try:
            reader_src = _stamped_plan_buffer(reader_src, pins)
        except Exception as exc:
            logger.warning('Could not stamp pins on floor plan %s: %s', getattr(plan, 'id', None), exc)
            if isinstance(reader_src, io.BytesIO):
                reader_src.seek(0)
    try:
        info = ImageReader(reader_src)
        iw, ih = info.getSize()
        if not iw or not ih:
            return None
        scale = min(max_w / iw, max_h / ih, 1)
        if isinstance(reader_src, io.BytesIO):
            reader_src.seek(0)
        img = RLImage(reader_src, width=iw * scale, height=ih * scale)
        img.hAlign = 'LEFT'
        return img
    except Exception as exc:
        logger.warning('Could not embed floor plan %s: %s', getattr(plan, 'id', None), exc)
        return None


def _ticket_loc(ticket):
    return ' / '.join(
        x for x in (
            getattr(ticket, 'property_name', None),
            getattr(ticket, 'zone', None),
            getattr(ticket, 'sub_zone', None),
            getattr(ticket, 'base_unit', None),
        ) if x
    ) or '—'


def build_project_pack_pdf(project: TicketProject, output_stream):
    """Write a branded project pack PDF into output_stream."""
    _KEEP.clear()
    heading, body, muted, cell, title, kpi_n, kpi_l = _styles()
    info = project.to_dict(with_property_count=True)
    assets = (
        Asset.query.filter_by(project_id=project.id)
        .order_by(Asset.building, Asset.floor, Asset.asset_id)
        .all()
    )
    plans = (
        FloorPlan.query.filter_by(project_id=project.id)
        .order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name)
        .all()
    )
    tickets = _project_tickets(project)
    locations = _location_rows(project)
    generated = datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')
    avail = PAGE_W - 2 * MARGIN
    client = info.get('client_name') or '—'
    asset_by_code = {str(a.asset_id): a for a in assets}

    story = [
        Paragraph(_esc(project.name), title),
        Paragraph(_esc(f'{client}  ·  Generated {generated}'), muted),
        Spacer(1, 10),
        _kpi_strip([
            (len(assets), 'Assets'),
            (len(plans), 'Drawings'),
            (len(locations), 'Locations'),
            (len(tickets), 'Tickets'),
        ], kpi_n, kpi_l, avail),
        *_section('Overview', heading),
        _kv_table([
            ('Client', client),
            ('Supervisors', info.get('supervisor_name') or 'Shared queue'),
            ('Linked BD project', info.get('bd_project_label')),
            ('Contract end', info.get('project_end_date')),
            ('Renewal', info.get('renewal_date')),
            ('Project value', _fmt_money(info.get('project_value'))),
        ], body),
    ]
    if info.get('description'):
        story.append(Spacer(1, 6))
        story.append(Paragraph(_esc(info['description']), body))

    story.extend(_section('Locations', heading))
    if locations:
        story.append(_grid(
            ['Building / property', 'Floor / zone', 'Sub-zone', 'Room / unit'],
            locations,
            cell,
            [avail * 0.30, avail * 0.24, avail * 0.23, avail * 0.23],
        ))
    else:
        story.append(Paragraph('No locations recorded for this project.', muted))

    story.extend(_section('Assets', heading))
    if assets:
        rows = []
        for asset in assets:
            loc = ' / '.join(x for x in (asset.building, asset.floor, getattr(asset, 'room', None)) if x) or '—'
            health = getattr(asset, 'health_score', None)
            health_txt = f'{health}%' if health is not None else '—'
            rows.append([
                asset.asset_id,
                asset.name,
                getattr(asset, 'asset_type', None) or '—',
                loc,
                asset.status or '—',
                health_txt,
            ])
        story.append(_grid(
            ['ID', 'Name', 'Type', 'Location', 'Status', 'Health'],
            rows,
            cell,
            [avail * 0.14, avail * 0.24, avail * 0.14, avail * 0.24, avail * 0.12, avail * 0.12],
        ))
    else:
        story.append(Paragraph('No FM assets linked to this project.', muted))

    story.extend(_section('2D drawings', heading))
    if not plans:
        story.append(Paragraph('No floor plans linked to this project.', muted))
    for plan in plans:
        bits = [plan.name]
        loc = ' / '.join(x for x in (plan.building, plan.floor) if x)
        if loc:
            bits.append(loc)
        pins = _pin_count(plan)
        bits.append(f'{pins} pin{"s" if pins != 1 else ""}')
        block = [Paragraph(_esc(' · '.join(bits)), body)]
        img = _plan_image(plan, avail, 90 * mm)
        if img:
            block.append(Spacer(1, 4))
            block.append(img)
        else:
            block.append(Paragraph('Drawing image could not be embedded.', muted))
        story.append(KeepTogether(block))
        pin_rows = _pin_detail_rows(plan, asset_by_code)
        if pin_rows:
            story.append(Spacer(1, 6))
            story.append(_grid(
                ['#', 'Pin', 'Status', 'Linked assets', 'On drawing'],
                pin_rows,
                cell,
                [avail * 0.08, avail * 0.22, avail * 0.14, avail * 0.36, avail * 0.20],
            ))
        elif pins:
            story.append(Paragraph('Pin records could not be listed.', muted))
        story.append(Spacer(1, 8))

    story.extend(_section('Service tickets', heading))
    if tickets:
        rows = []
        for ticket in tickets:
            rows.append([
                ticket.ticket_id,
                ticket.title,
                (ticket.status or '').replace('_', ' '),
                ticket.priority,
                _ticket_loc(ticket),
                _fmt_dt(ticket.created_at),
            ])
        story.append(_grid(
            ['Ticket', 'Title', 'Status', 'Priority', 'Location', 'Opened'],
            rows,
            cell,
            [avail * 0.14, avail * 0.26, avail * 0.14, avail * 0.10, avail * 0.20, avail * 0.16],
        ))
    else:
        story.append(Paragraph('No service tickets for this project.', muted))

    doc = SimpleDocTemplate(
        output_stream,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=f'{project.name} — project pack',
        author=getattr(brand, 'PDF_AUTHOR', 'Kynvera'),
    )
    doc.build(
        story,
        canvasmaker=lambda *a, **k: _PackCanvas(*a, heading=project.name, **k),
    )


def project_pack_filename(project: TicketProject) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', (project.name or 'project').lower()).strip('-')[:60]
    return f'{slug or "project"}-pack.pdf'
