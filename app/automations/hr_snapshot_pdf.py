"""HR daily UI snapshot PDF: live screenshots matching the Excel workbooks.

Playwright captures each Excel-equivalent view (Hiring Candidates, Leave Sick /
Annual / Logs / Planner, Manpower All Trades + Lists). Tall tables are sliced
across pages so rows stay readable. Capture runs in a subprocess so APScheduler
/ request threads never hit Playwright greenlet limits.

Excel backup still sends if this PDF is skipped or fails.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from io import BytesIO
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from common import kynvera_pdf_brand as brand

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 14 * mm
SHOT_BOX_TOP = PAGE_H - 31 * mm
SHOT_BOX_BOTTOM = 16 * mm
SHOT_BOX_H = SHOT_BOX_TOP - SHOT_BOX_BOTTOM
SHOT_BOX_W = PAGE_W - 2 * MARGIN
PDF_MIME = 'application/pdf'
SNAPSHOT_STEM = 'HR_Daily_Snapshot'

_LEAVE_DASH_READY = (
    "() => { const el = document.getElementById('ltStatTotal'); "
    "const detail = document.getElementById('ltMonthDetail'); "
    "const ws = document.getElementById('ltMonthWorkspace'); "
    "return !!(el && el.textContent && el.textContent.trim() !== '—' "
    "&& detail && !detail.hidden && ws); }"
)
_TAB_READY = (
    "() => {{ const p = document.getElementById('{panel}'); "
    "if (!p || p.hidden) return false; "
    "const loading = Array.from(p.querySelectorAll('.lt-empty')).some("
    "t => (t.textContent || '').includes('Loading')); "
    "return !loading; }}"
)

HR_SNAPSHOT_PAGES: list[dict[str, str]] = [
    {
        'key': 'hiring_docs',
        'group': 'Hiring',
        'module': 'hiring',
        'title': 'Hiring — Documents',
        'subtitle': 'Excel: Candidates',
        'path': '/hr/hiring',
        'ready': (
            "() => !!document.querySelector('.hh-row, .hh-empty') "
            "&& !document.querySelector('.hh-loading')"
        ),
        'paged_next': '.hh-page-btn[data-page="next"]',
    },
    {
        'key': 'hiring_letters',
        'group': 'Hiring',
        'module': 'hiring',
        'title': 'Hiring — Letters of Intent',
        'subtitle': 'Unsigned and signed letters',
        'path': '/hr/hiring/offer-letters',
        'ready': "() => !!document.querySelector('.ol-row, .hh-empty, .ol-empty')",
        'paged_next': '[data-ol-page="next"]',
    },
    {
        'key': 'leave_sick',
        'group': 'Leave',
        'module': 'leave',
        'title': 'Leave Tracker — Sick Leave',
        'subtitle': 'Excel: Sick Leave',
        'path': '/hr/leave-tracker?month={month}',
        'ready': _LEAVE_DASH_READY,
        'click': '.lt-tab[data-tab="sick"]',
        'after_ready': _TAB_READY.format(panel='ltPanelSick'),
    },
    {
        'key': 'leave_annual',
        'group': 'Leave',
        'module': 'leave',
        'title': 'Leave Tracker — Annual Leave',
        'subtitle': 'Excel: Annual Leave',
        'path': '/hr/leave-tracker?month={month}',
        'ready': _LEAVE_DASH_READY,
        'click': '.lt-tab[data-tab="annual"]',
        'after_ready': _TAB_READY.format(panel='ltPanelAnnual'),
    },
    {
        'key': 'leave_logs',
        'group': 'Leave',
        'module': 'leave',
        'title': 'Leave Tracker — Leave Log',
        'subtitle': 'Excel: Leave Log',
        'path': '/hr/leave-tracker?month={month}',
        'ready': _LEAVE_DASH_READY,
        'click': '.lt-tab[data-tab="logs"]',
        'after_ready': _TAB_READY.format(panel='ltPanelLogs'),
    },
    {
        'key': 'leave_planner',
        'group': 'Leave',
        'module': 'leave',
        'title': 'Leave Tracker — Planner',
        'subtitle': 'Excel: Plans',
        'path': '/hr/leave-tracker?month={month}',
        'ready': _LEAVE_DASH_READY,
        'click': '.lt-tab[data-tab="planner"]',
        'after_ready': _TAB_READY.format(panel='ltPanelPlanner'),
    },
    {
        'key': 'manpower_board',
        'group': 'Manpower',
        'module': 'manpower',
        'title': 'Manpower Tracker — All Trades',
        'subtitle': 'Excel: All Trades',
        'path': '/hr/manpower-tracker',
        'ready': (
            "() => { const el = document.getElementById('mpStatTotal'); "
            "return !!(el && el.textContent && el.textContent.trim() !== '—'); }"
        ),
        'after_ready': (
            "() => { const body = document.getElementById('mpBoardBody'); "
            "if (!body) return true; "
            "return !Array.from(body.querySelectorAll('.mp-empty')).some("
            "t => (t.textContent || '').includes('Loading')); }"
        ),
    },
    {
        'key': 'manpower_lists',
        'group': 'Manpower',
        'module': 'manpower',
        'title': 'Manpower Tracker — Lists',
        'subtitle': 'Excel: Lists (trades and projects)',
        'path': '/hr/manpower-tracker',
        'ready': (
            "() => { const el = document.getElementById('mpStatTotal'); "
            "return !!(el && el.textContent && el.textContent.trim() !== '—'); }"
        ),
        'click': '#mpSidebarSettings',
        'after_ready': (
            "() => { const view = document.getElementById('mpSettingsView'); "
            "return !!(view && !view.hidden); }"
        ),
    },
]

_SNAPSHOT_LAYOUT_JS = """
() => {
  document.documentElement.setAttribute('data-kynvera-snapshot', '1');
  document.documentElement.classList.add('kynvera-snapshot');
  const hide = document.querySelectorAll(
    '.hh-sidebar, .hh-sidebar-toggle, nav.nav, #nav, .nav,' +
    '#injaazAssistant, .injaaz-assistant, [data-assistant-root],' +
    '.toast, .toast-container, #toastContainer'
  );
  hide.forEach((el) => { el.style.setProperty('display', 'none', 'important'); });
  const grow = document.querySelectorAll(
    'html, body, .hh-page, .hh-shell, .hh-main, .hh-list, .ol-list,' +
    '.mp-view, .mp-bento, .mp-bento-chrome, .mp-board-wrap, #mpSettingsView,' +
    '.lt-month-workspace, #ltMonthWorkspace, .lt-cal, #ltPlannerCal'
  );
  grow.forEach((el) => {
    el.style.setProperty('overflow', 'visible', 'important');
    el.style.setProperty('max-height', 'none', 'important');
    el.style.setProperty('height', 'auto', 'important');
    el.style.setProperty('min-height', '0', 'important');
    el.style.setProperty('flex', 'none', 'important');
  });
  const board = document.querySelector('.mp-board-wrap');
  if (board) {
    const w = Math.max(board.scrollWidth, board.clientWidth, 1);
    const h = Math.max(board.scrollHeight, board.clientHeight, 1);
    board.style.setProperty('width', w + 'px', 'important');
    board.style.setProperty('height', h + 'px', 'important');
  }
}
"""


def snapshot_enabled() -> bool:
    raw = (os.environ.get('AUTOMATION_UI_SNAPSHOT') or '1').strip().lower()
    if raw in ('0', 'false', 'no', 'off'):
        return False
    try:
        from flask import has_app_context, current_app
        if has_app_context() and current_app.config.get('TESTING'):
            return False
    except Exception:
        pass
    env = (os.environ.get('TESTING') or '').strip().lower()
    if env in ('1', 'true', 'yes'):
        return False
    flask_env = (os.environ.get('FLASK_ENV') or '').strip().lower()
    return flask_env != 'testing'


def snapshot_filenames(now_local: datetime) -> tuple[str, str]:
    day = now_local.strftime('%Y-%m-%d')
    return f'{SNAPSHOT_STEM}_{day}.pdf', f'HR Daily Snapshot ({day})'


def resolve_snapshot_base_url() -> str:
    override = (os.environ.get('AUTOMATION_SNAPSHOT_BASE_URL') or '').strip()
    if override:
        return override.rstrip('/')
    port = (os.environ.get('PORT') or '5004').strip() or '5004'
    return f'http://127.0.0.1:{port}'


def resolve_snapshot_user(preferred_user_id: Optional[int] = None):
    from app.models import User, db

    if preferred_user_id:
        user = db.session.get(User, preferred_user_id)
        if user and user.is_active:
            return user
    admin = (
        User.query.filter_by(role='admin', is_active=True)
        .order_by(User.id.asc())
        .first()
    )
    if admin:
        return admin
    return (
        User.query.filter_by(access_hr=True, is_active=True)
        .order_by(User.id.asc())
        .first()
    )


def mint_snapshot_token(user) -> str:
    from datetime import timedelta, timezone

    from flask import current_app
    from flask_jwt_extended import create_access_token, get_jti

    from app.models import Session, db

    token = create_access_token(identity=str(user.id))
    jti = get_jti(token)
    jwt_expires = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES') or timedelta(hours=1)
    exp_dt = datetime.now(timezone.utc).replace(tzinfo=None) + jwt_expires
    db.session.add(Session(user_id=user.id, token_jti=jti, expires_at=exp_dt))
    db.session.commit()
    return token


def _app_reachable(base_url: str, timeout: float = 4.0) -> tuple[bool, str]:
    url = f'{base_url.rstrip("/")}/login'
    try:
        req = Request(url, method='GET', headers={'User-Agent': 'Kynvera-HR-Snapshot/1'})
        with urlopen(req, timeout=timeout) as resp:
            if int(getattr(resp, 'status', 200) or 200) >= 500:
                return False, f'{url} returned HTTP {resp.status}'
        return True, ''
    except Exception as exc:
        return False, f'App not reachable at {url} ({exc})'


def _png_to_jpeg(png_bytes: bytes, max_width: int = 2600) -> tuple[BytesIO, int, int]:
    from PIL import Image as PILImage

    im = PILImage.open(BytesIO(png_bytes))
    if im.mode not in ('RGB', 'L'):
        im = im.convert('RGB')
    elif im.mode == 'L':
        im = im.convert('RGB')
    if im.width > max_width:
        ratio = max_width / float(im.width)
        im = im.resize((max_width, max(1, int(im.height * ratio))), PILImage.Resampling.LANCZOS)
    buf = BytesIO()
    im.save(buf, format='JPEG', quality=88, optimize=True)
    buf.seek(0)
    return buf, im.width, im.height


def _wait_ready(page, expression: Optional[str], timeout_ms: int = 22000) -> None:
    if not expression:
        return
    try:
        page.wait_for_function(expression, timeout=timeout_ms)
    except Exception:
        page.wait_for_timeout(900)


def snapshot_pages_for_modules(modules: Optional[list[str]] = None) -> list[dict[str, str]]:
    wanted = {str(m).strip().lower() for m in (modules or []) if str(m).strip()}
    if not wanted:
        return list(HR_SNAPSHOT_PAGES)
    return [p for p in HR_SNAPSHOT_PAGES if (p.get('module') or '').lower() in wanted]


def _dubai_month() -> int:
    try:
        from zoneinfo import ZoneInfo
        return int(datetime.now(ZoneInfo('Asia/Dubai')).month)
    except Exception:
        return int(datetime.now().month)


def _spec_path(spec: dict[str, str]) -> str:
    return (spec.get('path') or '').replace('{month}', str(_dubai_month()))


def _prepare_snapshot_layout(page) -> None:
    try:
        page.evaluate(_SNAPSHOT_LAYOUT_JS)
    except Exception:
        logger.warning('HR snapshot: layout expand failed', exc_info=True)


def _screenshot_main(page) -> bytes:
    _prepare_snapshot_layout(page)
    main = page.locator('main.hh-main').first
    if main.count():
        try:
            return main.screenshot(type='png', timeout=60000)
        except Exception:
            logger.warning('HR snapshot: main screenshot failed, using full page')
    return page.screenshot(full_page=True, type='png')


def _append_shot(shots: list[dict[str, Any]], spec: dict[str, str], png: bytes, title: Optional[str] = None) -> None:
    shots.append({
        'key': spec['key'],
        'group': spec.get('group') or '',
        'title': title or spec['title'],
        'subtitle': spec['subtitle'],
        'png': png,
    })


def _click_next_page(page, selector: str) -> bool:
    loc = page.locator(selector).first
    try:
        if not loc.count():
            return False
        if loc.is_disabled():
            return False
        loc.click(timeout=8000)
        page.wait_for_timeout(400)
        return True
    except Exception:
        logger.warning('HR snapshot: next-page click failed (%s)', selector)
        return False


def capture_module_screenshots(
    base_url: str,
    access_token: str,
    modules: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Return screenshot dicts. Raises if Playwright cannot start."""
    from playwright.sync_api import sync_playwright

    base = base_url.rstrip('/')
    parsed = urlparse(base)
    pages = snapshot_pages_for_modules(modules)
    if not pages:
        raise RuntimeError('No snapshot views for the selected modules')
    shots: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--disable-dev-shm-usage', '--no-sandbox'],
        )
        context = browser.new_context(
            viewport={'width': 1600, 'height': 1000},
            device_scale_factor=2,
            color_scheme='light',
        )
        context.add_cookies([
            {
                'name': 'access_token_cookie',
                'value': access_token,
                'url': base,
                'httpOnly': True,
                'sameSite': 'Lax',
            },
        ])
        token_js = access_token.replace('\\', '\\\\').replace("'", "\\'")
        context.add_init_script(
            "document.documentElement.setAttribute('data-kynvera-snapshot', '1');"
            f"window.localStorage.setItem('access_token', '{token_js}');"
        )
        page = context.new_page()
        page.set_default_timeout(45000)
        last_path = None
        try:
            for spec in pages:
                path = _spec_path(spec)
                if path != last_path:
                    page.goto(f'{base}{path}', wait_until='domcontentloaded', timeout=45000)
                    last_path = path
                    _wait_ready(page, spec.get('ready'))
                click = (spec.get('click') or '').strip()
                if click:
                    loc = page.locator(click).first
                    try:
                        if loc.count():
                            loc.click(timeout=8000)
                            page.wait_for_timeout(350)
                    except Exception:
                        logger.warning('HR snapshot: click failed for %s (%s)', spec['key'], click)
                _wait_ready(page, spec.get('after_ready') or spec.get('ready'), timeout_ms=16000)
                page.wait_for_timeout(250)
                _append_shot(shots, spec, _screenshot_main(page))
                next_sel = (spec.get('paged_next') or '').strip()
                page_no = 2
                while next_sel and page_no <= 20:
                    if not _click_next_page(page, next_sel):
                        break
                    _wait_ready(page, spec.get('after_ready') or spec.get('ready'), timeout_ms=16000)
                    page.wait_for_timeout(250)
                    _append_shot(
                        shots,
                        spec,
                        _screenshot_main(page),
                        title=f"{spec['title']} — page {page_no}",
                    )
                    page_no += 1
        finally:
            context.close()
            browser.close()
    if not shots:
        raise RuntimeError('No module screenshots were captured')
    logger.info('HR snapshot captured %s view(s) from %s', len(shots), parsed.netloc or base)
    return shots


def compose_snapshot_pdf(
    shots: list[dict[str, Any]],
    *,
    now_local: Optional[datetime] = None,
    day: Optional[str] = None,
    tz_label: str = 'Asia/Dubai',
) -> bytes:
    """Build a landscape Kynvera PDF from PNG screenshot dicts."""
    when = now_local or datetime.now()
    date_line = day or when.strftime('%Y-%m-%d')
    pretty = f"{when.strftime('%A')}, {when.day} {when.strftime('%B %Y')}"
    time_line = when.strftime('%H:%M') + f' {tz_label}'

    jpeg_keep: list[BytesIO] = []
    prepared: list[dict[str, Any]] = []
    for shot in shots:
        png = shot.get('png') or shot.get('jpeg')
        if not png:
            continue
        buf, iw, ih = _png_to_jpeg(png)
        jpeg_keep.append(buf)
        strips = _split_tall_image(buf, iw, ih, jpeg_keep)
        total_parts = len(strips)
        for part_idx, (strip_buf, sw, sh) in enumerate(strips, start=1):
            title = shot.get('title') or 'Module'
            if total_parts > 1:
                title = f'{title}  ({part_idx} of {total_parts})'
            prepared.append({
                'title': title,
                'subtitle': shot.get('subtitle') or '',
                'key': shot.get('key') or '',
                'group': shot.get('group') or '',
                'jpeg': strip_buf,
                'width': sw,
                'height': sh,
                'continued': part_idx > 1,
            })
    if not prepared:
        raise ValueError('No screenshot images to compose')

    buf = BytesIO()
    canvas = Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    canvas.setTitle(f'HR Daily Snapshot — {date_line}')
    canvas.setAuthor(brand.PDF_AUTHOR)
    canvas.setSubject('Live HR module screens')
    canvas.setCreator('Kynvera Automations')

    pages: list[dict[str, Any]] = [{'kind': 'cover'}]
    for item in prepared:
        pages.append({'kind': 'shot', **item})
    total = len(pages)

    for index, page in enumerate(pages, start=1):
        if page['kind'] == 'cover':
            _draw_cover(canvas, pretty, time_line, date_line, prepared)
        else:
            _draw_shot_page(canvas, page, date_line)
        _draw_chrome(canvas, index, total, date_line)
        canvas.showPage()

    canvas.save()
    return buf.getvalue()


def _split_tall_image(
    jpeg_buf: BytesIO,
    img_w: int,
    img_h: int,
    keep: list[BytesIO],
) -> list[tuple[BytesIO, int, int]]:
    """Slice a tall screenshot so each strip fills one landscape content box."""
    from PIL import Image as PILImage

    if img_w <= 0 or img_h <= 0:
        return [(jpeg_buf, img_w, img_h)]
    scale = SHOT_BOX_W / float(img_w)
    visible_src_h = max(1, int(SHOT_BOX_H / scale))
    if img_h <= int(visible_src_h * 1.32) + 8:
        return [(jpeg_buf, img_w, img_h)]

    jpeg_buf.seek(0)
    image = PILImage.open(jpeg_buf)
    overlap = max(28, int(visible_src_h * 0.04))
    strips: list[tuple[BytesIO, int, int]] = []
    y = 0
    while y < img_h:
        y2 = min(img_h, y + visible_src_h)
        crop = image.crop((0, y, img_w, y2))
        out = BytesIO()
        crop.convert('RGB').save(out, format='JPEG', quality=88, optimize=True)
        out.seek(0)
        keep.append(out)
        strips.append((out, crop.width, crop.height))
        if y2 >= img_h:
            break
        y = y2 - overlap
    return strips or [(jpeg_buf, img_w, img_h)]


def _cover_thumbs(prepared: list[dict[str, Any]]) -> list[dict[str, Any]]:
    thumbs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in prepared:
        group = (item.get('group') or item.get('title') or '').split('  (')[0]
        if not group or group in seen:
            continue
        seen.add(group)
        thumbs.append(item)
        if len(thumbs) >= 3:
            break
    return thumbs or prepared[:3]


def _draw_chrome(c: Canvas, page_number: int, page_count: int, date_line: str) -> None:
    c.saveState()
    c.setStrokeColor(brand.PRIMARY)
    c.setLineWidth(2.2)
    c.line(0, PAGE_H - 1, PAGE_W, PAGE_H - 1)

    hdr_y = PAGE_H - 12.5 * mm
    logo_path = brand.resolve_logo_path(prefer_wordmark=True)
    if logo_path and os.path.isfile(logo_path):
        try:
            c.drawImage(
                logo_path,
                MARGIN,
                hdr_y - 1.2 * mm,
                width=34 * mm,
                height=8 * mm,
                preserveAspectRatio=True,
                mask='auto',
            )
        except Exception:
            c.setFont('Helvetica-Bold', 10)
            c.setFillColor(brand.PRIMARY_DARK)
            c.drawString(MARGIN, hdr_y + 1.5 * mm, brand.COMPANY_NAME_UPPER)
    else:
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(brand.PRIMARY_DARK)
        c.drawString(MARGIN, hdr_y + 1.5 * mm, brand.COMPANY_NAME_UPPER)

    c.setFont('Helvetica', 8)
    c.setFillColor(brand.TEXT_MUTED)
    c.drawRightString(PAGE_W - MARGIN, hdr_y + 1.8 * mm, f'HR Daily Snapshot  ·  {date_line}')

    c.setStrokeColor(brand.HAIRLINE)
    c.setLineWidth(0.5)
    c.line(MARGIN, PAGE_H - 14.5 * mm, PAGE_W - MARGIN, PAGE_H - 14.5 * mm)

    c.line(MARGIN, 11 * mm, PAGE_W - MARGIN, 11 * mm)
    c.setFont('Helvetica', 7)
    c.setFillColor(brand.TEXT_MUTED)
    c.drawString(MARGIN, 6.4 * mm, brand.FOOTER_CONFIDENTIAL)
    c.drawCentredString(PAGE_W / 2, 6.4 * mm, 'Live module screens at backup time')
    c.drawRightString(PAGE_W - MARGIN, 6.4 * mm, f'Page {page_number} of {page_count}')
    c.restoreState()


def _draw_cover(
    c: Canvas,
    pretty: str,
    time_line: str,
    date_line: str,
    prepared: list[dict[str, Any]],
) -> None:
    c.setFillColor(brand.SOFT_WASH)
    c.rect(0, 0, PAGE_W * 0.38, PAGE_H, fill=1, stroke=0)

    left = MARGIN
    y = PAGE_H - 32 * mm
    c.setFillColor(brand.PRIMARY_DARK)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(left, y, 'AUTOMATIONS  ·  HR')
    y -= 12 * mm
    c.setFillColor(brand.TEXT_DARK)
    c.setFont('Helvetica-Bold', 26)
    c.drawString(left, y, 'Daily snapshot')
    y -= 8 * mm
    c.setFont('Helvetica', 11)
    c.setFillColor(brand.TEXT_MID)
    c.drawString(left, y, pretty)
    y -= 5.5 * mm
    c.setFont('Helvetica', 9)
    c.setFillColor(brand.TEXT_MUTED)
    c.drawString(left, y, f'Captured {time_line}')

    y -= 16 * mm
    c.setStrokeColor(brand.PRIMARY)
    c.setLineWidth(1.4)
    c.line(left, y, left + 28 * mm, y)
    y -= 10 * mm
    c.setFont('Helvetica', 9)
    c.setFillColor(brand.TEXT_MID)
    groups: list[str] = []
    for item in prepared:
        group = (item.get('group') or '').strip()
        if group and group not in groups:
            groups.append(group)
    if not groups:
        wrap = 'Live screens matching today’s Excel backup.'
    elif len(groups) == 1:
        wrap = f'Live screens for {groups[0]}.'
    elif len(groups) == 2:
        wrap = f'Live screens for {groups[0]} and {groups[1]}.'
    else:
        wrap = f'Live screens for {", ".join(groups[:-1])}, and {groups[-1]}.'
    for line in _wrap_text(wrap, 42):
        c.drawString(left, y, line)
        y -= 4.4 * mm

    y -= 6 * mm
    seen: set[str] = set()
    cover_items = []
    for item in prepared:
        label = item.get('title') or ''
        if ' of ' in label and label.rsplit('(', 1)[-1][:1].isdigit():
            # Skip continuation slices on the cover list
            if '(1 of ' not in label:
                continue
            label = label.rsplit('  (', 1)[0]
        if label in seen:
            continue
        seen.add(label)
        cover_items.append(label)
    for i, label in enumerate(cover_items, start=1):
        num = f'{i:02d}'
        c.setFillColor(brand.PRIMARY)
        c.circle(left + 3.2 * mm, y + 1.2 * mm, 3.4 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 7)
        c.drawCentredString(left + 3.2 * mm, y, num)
        c.setFillColor(brand.TEXT_DARK)
        c.setFont('Helvetica', 8.5)
        c.drawString(left + 10 * mm, y, label)
        y -= 6.4 * mm
        if y < 22 * mm:
            break

    thumbs = _cover_thumbs(prepared)
    card_x = PAGE_W * 0.40
    card_w = PAGE_W - MARGIN - card_x
    card_h = (PAGE_H - 32 * mm) / max(len(thumbs), 1) - 5 * mm
    top = PAGE_H - 20 * mm
    for i, item in enumerate(thumbs):
        cy = top - (i + 1) * (card_h + 5 * mm)
        _draw_image_card(
            c,
            item['jpeg'],
            item['width'],
            item['height'],
            card_x,
            cy,
            card_w,
            card_h - 6 * mm,
        )
        c.setFont('Helvetica-Bold', 7.5)
        c.setFillColor(brand.TEXT_DARK)
        thumb_title = (item.get('group') or item['title']).split('  (')[0]
        c.drawString(card_x, cy + card_h - 4.5 * mm, thumb_title)


def _draw_shot_page(c: Canvas, page: dict[str, Any], date_line: str) -> None:
    title_y = PAGE_H - 22 * mm
    c.setFont('Helvetica-Bold', 14)
    c.setFillColor(brand.TEXT_DARK)
    c.drawString(MARGIN, title_y, page['title'])
    c.setFont('Helvetica', 8.5)
    c.setFillColor(brand.TEXT_MID)
    c.drawString(MARGIN, title_y - 5 * mm, page.get('subtitle') or '')
    c.setFont('Helvetica', 8)
    c.setFillColor(brand.TEXT_MUTED)
    c.drawRightString(PAGE_W - MARGIN, title_y, f'Live view  ·  {date_line}')

    box_top = title_y - 9 * mm
    box_bottom = 16 * mm
    _draw_image_card(
        c,
        page['jpeg'],
        page['width'],
        page['height'],
        MARGIN,
        box_bottom,
        PAGE_W - 2 * MARGIN,
        box_top - box_bottom,
    )


def _draw_image_card(
    c: Canvas,
    jpeg_buf: BytesIO,
    img_w: int,
    img_h: int,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    if img_w <= 0 or img_h <= 0 or w <= 0 or h <= 0:
        return
    scale = min(w / img_w, h / img_h)
    dw = img_w * scale
    dh = img_h * scale
    dx = x + (w - dw) / 2
    dy = y + (h - dh) / 2
    jpeg_buf.seek(0)
    c.saveState()
    c.setFillColor(colors.Color(0.10, 0.11, 0.14, alpha=0.07))
    c.roundRect(dx + 1.6 * mm, dy - 1.4 * mm, dw, dh, 2.2 * mm, fill=1, stroke=0)
    c.setFillColor(brand.WHITE)
    c.roundRect(dx - 0.4 * mm, dy - 0.4 * mm, dw + 0.8 * mm, dh + 0.8 * mm, 2 * mm, fill=1, stroke=0)
    c.drawImage(
        ImageReader(jpeg_buf),
        dx,
        dy,
        width=dw,
        height=dh,
        preserveAspectRatio=True,
        mask='auto',
    )
    c.setStrokeColor(brand.HAIRLINE)
    c.setLineWidth(0.6)
    c.roundRect(dx - 0.4 * mm, dy - 0.4 * mm, dw + 0.8 * mm, dh + 0.8 * mm, 2 * mm, fill=0, stroke=1)
    c.restoreState()


def _wrap_text(text: str, width: int) -> list[str]:
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


def build_hr_ui_snapshot_pdf(
    *,
    now_local: datetime,
    user_id: Optional[int] = None,
    modules: Optional[list[str]] = None,
) -> tuple[Optional[bytes], Optional[str]]:
    """Return (pdf_bytes, warning). Both None means skipped on purpose (tests)."""
    if not snapshot_enabled():
        return None, None

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return None, 'UI snapshot skipped — install Playwright (pip install playwright && playwright install chromium)'

    base = resolve_snapshot_base_url()
    ok, reason = _app_reachable(base)
    if not ok:
        return None, f'UI snapshot skipped — {reason}'

    user = resolve_snapshot_user(user_id)
    if not user:
        return None, 'UI snapshot skipped — no active admin or HR user to sign in as'

    token = mint_snapshot_token(user)
    day = now_local.strftime('%Y-%m-%d')
    tz_label = now_local.tzname() or 'Asia/Dubai'

    fd, out_path = tempfile.mkstemp(prefix='hr_snapshot_', suffix='.pdf')
    os.close(fd)
    try:
        env = os.environ.copy()
        env['HR_SNAPSHOT_BASE'] = base
        env['HR_SNAPSHOT_TOKEN'] = token
        env['HR_SNAPSHOT_OUT'] = out_path
        env['HR_SNAPSHOT_DATE'] = day
        env['HR_SNAPSHOT_TZ'] = tz_label
        env['HR_SNAPSHOT_PRETTY'] = now_local.strftime('%Y-%m-%dT%H:%M:%S')
        if modules:
            env['HR_SNAPSHOT_MODULES'] = ','.join(modules)
        proc = subprocess.run(
            [sys.executable, '-m', 'app.automations.hr_snapshot_pdf'],
            capture_output=True,
            timeout=300,
            env=env,
            cwd=_repo_root(),
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace').strip()
            logger.warning('HR snapshot subprocess failed: %s', err[:800])
            return None, f'UI snapshot failed — {(err or "unknown error")[:240]}'
        if not os.path.isfile(out_path) or os.path.getsize(out_path) < 200:
            return None, 'UI snapshot failed — PDF was not written'
        with open(out_path, 'rb') as fh:
            return fh.read(), None
    except subprocess.TimeoutExpired:
        return None, 'UI snapshot skipped — screenshot timed out'
    except Exception as exc:
        logger.exception('HR snapshot PDF failed')
        return None, f'UI snapshot failed — {exc}'[:240]
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cli_main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    base = (os.environ.get('HR_SNAPSHOT_BASE') or '').strip()
    token = (os.environ.get('HR_SNAPSHOT_TOKEN') or '').strip()
    out = (os.environ.get('HR_SNAPSHOT_OUT') or '').strip()
    day = (os.environ.get('HR_SNAPSHOT_DATE') or '').strip() or None
    tz_label = (os.environ.get('HR_SNAPSHOT_TZ') or 'Asia/Dubai').strip() or 'Asia/Dubai'
    stamp = (os.environ.get('HR_SNAPSHOT_PRETTY') or '').strip()
    modules_raw = (os.environ.get('HR_SNAPSHOT_MODULES') or '').strip()
    modules = [p.strip() for p in modules_raw.split(',') if p.strip()] or None
    if not base or not token or not out:
        print('HR_SNAPSHOT_BASE, HR_SNAPSHOT_TOKEN, and HR_SNAPSHOT_OUT are required', file=sys.stderr)
        return 2
    now_local = None
    if stamp:
        try:
            now_local = datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            now_local = None
    shots = capture_module_screenshots(base, token, modules=modules)
    pdf = compose_snapshot_pdf(shots, now_local=now_local, day=day, tz_label=tz_label)
    with open(out, 'wb') as fh:
        fh.write(pdf)
    logger.info('Wrote HR snapshot PDF (%s bytes) to %s', len(pdf), out)
    return 0


if __name__ == '__main__':
    raise SystemExit(_cli_main())
