"""
FM Asset Management — CRUD, dashboard KPIs, AI failure/RUL estimates.
URL prefix: /assets
"""
import json
import logging
import os
from datetime import datetime, date, timezone
from io import BytesIO
from base64 import b64encode
from flask import (
    Blueprint, render_template, request, jsonify, redirect, g,
    send_file, current_app, url_for,
)
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, inspect, text

from app.models import (
    db, User, Asset, Ticket, AssetPrediction, FloorPlan,
    PortfolioForecast, OutboundWebhook, IntegrationApiKey, TicketAsset,
    TicketProject, TicketProperty,
)
from common.fm_integration import (
    fm_log_audit, dispatch_webhooks, jwt_or_api_key_required, create_api_key,
)
from module_assets.qr_labels import (
    asset_qr_png_bytes,
    asset_text_qr_png_bytes,
    build_bulk_labels_pdf,
    build_single_label_pdf,
    ensure_asset_qr_code,
)
from module_assets.twin import (
    DEFAULT_PLAN_SVG,
    catalog_buildings_for_project,
    drawings_for_asset,
    enrich_floor_plan,
    normalize_hotspots,
    plan_pin_stats,
    project_location_assets,
    recommend_fallback,
    save_plan_image,
    ticket_location_catalog,
)

logger = logging.getLogger(__name__)

assets_bp = Blueprint(
    'assets_bp',
    __name__,
    url_prefix='/assets',
    template_folder='templates',
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _current_user():
    uid = get_jwt_identity()
    return User.query.get(uid) if uid else None


def _has_access(user):
    if not user:
        return False
    if user.role == 'admin':
        return True
    if getattr(user, 'access_ticketing', False):
        return True
    return False


def _can_write(user):
    if not user:
        return False
    if user.role == 'admin':
        return True
    if getattr(user, 'access_ticketing', False) and user.designation in (
        'supervisor', 'operations_manager', 'general_manager',
    ):
        return True
    return user.role == 'admin'


def _next_asset_id():
    codes = [row[0] for row in db.session.query(Asset.asset_id).all()]
    max_n = 0
    for code in codes:
        if code and str(code).upper().startswith('AST-'):
            try:
                max_n = max(max_n, int(str(code).split('-', 1)[1]))
            except ValueError:
                pass
    return f'AST-{max_n + 1:04d}'


def _parse_date(val):
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _asset_from_payload(data, asset=None):
    asset = asset or Asset()
    if not asset.asset_id:
        asset.asset_id = (data.get('asset_id') or '').strip() or _next_asset_id()
    asset.qr_code = (data.get('qr_code') or '').strip() or None
    if not asset.qr_code:
        ensure_asset_qr_code(asset)
    asset.name = (data.get('name') or '').strip()
    asset.asset_type = (data.get('asset_type') or '').strip() or None
    asset.building = (data.get('building') or '').strip() or None
    asset.floor = (data.get('floor') or '').strip() or None
    asset.room = (data.get('room') or '').strip() or None
    if 'project_id' in data:
        pid, err = _parse_project_id(data.get('project_id'))
        if not err:
            asset.project_id = pid
    asset.manufacturer = (data.get('manufacturer') or '').strip() or None
    asset.model = (data.get('model') or '').strip() or None
    asset.serial_number = (data.get('serial_number') or '').strip() or None
    asset.installation_date = _parse_date(data.get('installation_date'))
    asset.warranty_expiry = _parse_date(data.get('warranty_expiry'))
    try:
        asset.purchase_cost = float(data['purchase_cost']) if data.get('purchase_cost') not in (None, '') else None
    except (TypeError, ValueError):
        asset.purchase_cost = None
    try:
        mct = data.get('maintenance_cost_total')
        asset.maintenance_cost_total = float(mct) if mct not in (None, '') else (asset.maintenance_cost_total or 0.0)
    except (TypeError, ValueError):
        pass
    asset.status = (data.get('status') or asset.status or 'active').strip()
    try:
        hs = data.get('health_score')
        asset.health_score = int(hs) if hs not in (None, '') else None
        if asset.health_score is not None:
            asset.health_score = max(0, min(100, asset.health_score))
    except (TypeError, ValueError):
        pass
    urls = data.get('image_urls')
    if isinstance(urls, list):
        asset.image_urls = json.dumps(urls)
    elif isinstance(urls, str) and urls.strip():
        asset.image_urls = urls.strip()
    asset.notes = (data.get('notes') or '').strip() or None
    for coord in ('latitude', 'longitude'):
        if data.get(coord) not in (None, ''):
            try:
                setattr(asset, coord, float(data[coord]))
            except (TypeError, ValueError):
                pass
        elif coord in data and data.get(coord) in (None, ''):
            setattr(asset, coord, None)
    asset.updated_at = _utcnow()
    return asset


def _add_missing_columns(table, extras):
    inspector = inspect(db.engine)
    if table not in inspector.get_table_names():
        return
    existing = {col['name'] for col in inspector.get_columns(table)}
    missing = [(name, typ) for name, typ in extras if name not in existing]
    if not missing:
        return
    with db.engine.begin() as conn:
        for name, typ in missing:
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {typ}'))
                logger.info('Added column %s.%s', table, name)
            except Exception as exc:
                err = str(exc).lower()
                if 'already exists' in err or 'duplicate' in err:
                    logger.info('Column %s.%s already exists', table, name)
                else:
                    logger.warning('Could not add %s.%s: %s', table, name, exc)


def _ensure_asset_columns(app):
    with app.app_context():
        try:
            db.create_all()
            _add_missing_columns('fm_assets', [
                ('latitude', 'REAL'),
                ('longitude', 'REAL'),
                ('project_id', 'INTEGER'),
            ])
            _add_missing_columns('fm_floor_plans', [('project_id', 'INTEGER')])
        except Exception as exc:
            logger.warning('Asset column ensure: %s', exc)


@assets_bp.record_once
def _on_register(state):
    _ensure_asset_columns(state.app)


def compute_dashboard_kpis():
    """SQL aggregates for Building Health %, Warranty Status, Budget Utilization."""
    today = date.today()
    total = Asset.query.count()
    if total == 0:
        return {
            'total_assets': 0,
            'building_health_pct': None,
            'warranty': {'active': 0, 'expiring_30d': 0, 'expired': 0, 'unknown': 0},
            'budget': {
                'purchase_total': 0.0,
                'maintenance_total': 0.0,
                'utilization_pct': None,
            },
            'critical_count': 0,
            'by_building': [],
        }

    avg_health = db.session.query(func.avg(Asset.health_score)).filter(
        Asset.health_score.isnot(None)
    ).scalar()
    building_health_pct = round(float(avg_health), 1) if avg_health is not None else None

    assets = Asset.query.all()
    warranty = {'active': 0, 'expiring_30d': 0, 'expired': 0, 'unknown': 0}
    for a in assets:
        if not a.warranty_expiry:
            warranty['unknown'] += 1
        elif a.warranty_expiry < today:
            warranty['expired'] += 1
        elif (a.warranty_expiry - today).days <= 30:
            warranty['expiring_30d'] += 1
        else:
            warranty['active'] += 1

    purchase_total = db.session.query(func.coalesce(func.sum(Asset.purchase_cost), 0.0)).scalar() or 0.0
    maintenance_total = db.session.query(
        func.coalesce(func.sum(Asset.maintenance_cost_total), 0.0)
    ).scalar() or 0.0
    utilization_pct = None
    if purchase_total and float(purchase_total) > 0:
        utilization_pct = round(100.0 * float(maintenance_total) / float(purchase_total), 1)

    critical_count = Asset.query.filter(
        db.or_(
            Asset.status == 'critical',
            Asset.health_score.isnot(None) & (Asset.health_score < 40),
        )
    ).count()

    by_building_rows = (
        db.session.query(
            Asset.building,
            func.count(Asset.id),
            func.avg(Asset.health_score),
        )
        .group_by(Asset.building)
        .all()
    )
    by_building = [
        {
            'building': b or 'Unassigned',
            'count': c,
            'avg_health': round(float(h), 1) if h is not None else None,
        }
        for b, c, h in by_building_rows
    ]

    return {
        'total_assets': total,
        'building_health_pct': building_health_pct,
        'warranty': warranty,
        'budget': {
            'purchase_total': round(float(purchase_total), 2),
            'maintenance_total': round(float(maintenance_total), 2),
            'utilization_pct': utilization_pct,
        },
        'critical_count': critical_count,
        'by_building': by_building,
    }


# ── Pages ──────────────────────────────────────────────────────────────

@assets_bp.route('/')
@jwt_required()
def assets_dashboard():
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    kpis = compute_dashboard_kpis()
    assets = Asset.query.order_by(Asset.updated_at.desc()).limit(50).all()
    return render_template(
        'assets_dashboard.html',
        user=user,
        kpis=kpis,
        assets=assets,
        can_write=_can_write(user),
    )


@assets_bp.route('/executive')
@jwt_required()
def assets_executive():
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    kpis = compute_dashboard_kpis()
    ticket_stats = _ticket_exec_stats()
    forecast = PortfolioForecast.query.order_by(PortfolioForecast.created_at.desc()).first()
    # Narrative is fetched async by the page (see /assets/api/narrative) so the
    # dashboard render never blocks on an LLM call.
    return render_template(
        'assets_executive.html',
        user=user,
        kpis=kpis,
        ticket_stats=ticket_stats,
        forecast=forecast.to_dict() if forecast else None,
        can_write=_can_write(user),
    )


@assets_bp.route('/map')
@jwt_required()
def assets_map_page():
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    return render_template('assets_map.html', user=user, can_write=_can_write(user))


def _parse_project_id(raw):
    if raw in (None, '', 'null', 'none'):
        return None, None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None, 'Invalid project_id'
    if not TicketProject.query.get(pid):
        return None, 'Unknown project_id'
    return pid, None


def _default_building_for_project(project):
    if not project:
        return ''
    prop = (
        TicketProperty.query.filter_by(project_id=project.id, is_active=True)
        .order_by(TicketProperty.name)
        .first()
    )
    return (prop.name if prop else '') or (project.name or '')


def _twin_hub_data():
    projects = (
        TicketProject.query.filter_by(is_active=True)
        .order_by(TicketProject.name)
        .all()
    )
    plans = FloorPlan.query.order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name).all()
    stats = {p.id: plan_pin_stats(p) for p in plans}
    by_proj = {}
    unassigned = []
    for plan in plans:
        info = stats[plan.id]
        if plan.project_id:
            by_proj.setdefault(plan.project_id, []).append(info)
        else:
            unassigned.append(info)
    cards = []
    for proj in projects:
        floors = by_proj.get(proj.id, [])
        info = proj.to_dict() if hasattr(proj, 'to_dict') else {}
        cards.append({
            'id': proj.id,
            'name': proj.name,
            'client_name': info.get('client_name') or getattr(proj, 'client_name', None),
            'supervisor_name': info.get('supervisor_name'),
            'floor_count': len(floors),
            'pin_count': sum(f['pin_count'] for f in floors),
            'crit': sum(f['crit'] for f in floors),
            'warn': sum(f['warn'] for f in floors),
            'ok': sum(f['ok'] for f in floors),
        })
    totals = {
        'projects': len(cards),
        'floors': len(plans),
        'pins': sum(s['pin_count'] for s in stats.values()),
    }
    return cards, unassigned, totals, projects


def _twin_drawing_page_vars(user, project, plans, current_plan=None,
                            draft_building='', draft_floor=''):
    loc_building = (current_plan.building if current_plan else draft_building) or ''
    return dict(
        user=user,
        plans=plans,
        current_plan=current_plan,
        project=project,
        can_write=_can_write(user),
        default_building=loc_building or (
            _default_building_for_project(project) if project else ''
        ),
        catalog_buildings=catalog_buildings_for_project(project.id) if project else [],
        plans_payload=[
            {'id': p.id, 'name': p.name, 'building': p.building, 'floor': p.floor or ''}
            for p in plans
        ],
        draft_building=draft_building or '',
        draft_floor=draft_floor or '',
    )


@assets_bp.route('/twin')
@jwt_required()
def assets_twin_page():
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    raw_plan = request.args.get('plan')
    if raw_plan:
        try:
            plan_id = int(raw_plan)
        except (TypeError, ValueError):
            plan_id = None
        if plan_id and FloorPlan.query.get(plan_id):
            qs = []
            pin = request.args.get('pin') or request.args.get('pin')
            asset = request.args.get('asset') or request.args.get('asset')
            if pin:
                qs.append('pin=' + pin)
            if asset:
                qs.append('asset=' + asset)
            dest = url_for('assets_bp.assets_twin_plan_page', plan_id=plan_id)
            if qs:
                dest = dest + '?' + '&'.join(qs)
            return redirect(dest)
    cards, unassigned, totals, projects = _twin_hub_data()
    return render_template(
        'assets_twin_hub.html',
        user=user,
        can_write=_can_write(user),
        projects=cards,
        unassigned=unassigned,
        totals=totals,
        assign_projects=projects,
        ticket_settings_url='/tickets/settings',
    )


@assets_bp.route('/twin/project/<int:project_id>')
@jwt_required()
def assets_twin_project_page(project_id):
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    project = TicketProject.query.get_or_404(project_id)
    plans = (
        FloorPlan.query.filter_by(project_id=project.id)
        .order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name)
        .all()
    )
    floors = [plan_pin_stats(p) for p in plans]
    catalog_buildings = catalog_buildings_for_project(project.id)
    building_names = [b['name'] for b in catalog_buildings] or [
        f['building'] for f in floors if f.get('building')
    ]
    pinned = {}
    for plan in plans:
        for hs in normalize_hotspots(plan.hotspots):
            for code in hs.get('asset_ids') or []:
                pinned[str(code)] = plan.id
    location_assets = []
    for row in project_location_assets(project.id, building_names):
        item = row.to_dict()
        item['url'] = '/assets/' + row.asset_id
        item['pinned_plan_id'] = pinned.get(row.asset_id)
        location_assets.append(item)
    return render_template(
        'assets_twin_project.html',
        user=user,
        can_write=_can_write(user),
        project=project,
        floors=floors,
        default_building=_default_building_for_project(project),
        catalog_buildings=catalog_buildings,
        location_assets=location_assets,
    )


@assets_bp.route('/twin/plan/<int:plan_id>')
@jwt_required()
def assets_twin_plan_page(plan_id):
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    plan = FloorPlan.query.get_or_404(plan_id)
    project = TicketProject.query.get(plan.project_id) if plan.project_id else None
    if project:
        plans = (
            FloorPlan.query.filter_by(project_id=project.id)
            .order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name)
            .all()
        )
    else:
        plans = (
            FloorPlan.query.filter(FloorPlan.project_id.is_(None))
            .order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name)
            .all()
        )
    return render_template(
        'assets_twin.html',
        **_twin_drawing_page_vars(user, project, plans, current_plan=plan),
    )


@assets_bp.route('/twin/project/<int:project_id>/draw')
@jwt_required()
def assets_twin_draw_page(project_id):
    """Empty drawing workspace for a building/floor that has no plan yet."""
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    project = TicketProject.query.get_or_404(project_id)
    plans = (
        FloorPlan.query.filter_by(project_id=project.id)
        .order_by(FloorPlan.building, FloorPlan.floor, FloorPlan.name)
        .all()
    )
    building = (request.args.get('building') or '').strip()
    floor = (request.args.get('floor') or '').strip()
    match = next(
        (
            p for p in plans
            if (p.building or '').strip().lower() == building.lower()
            and (p.floor or '').strip().lower() == floor.lower()
        ),
        None,
    )
    if match:
        return redirect(url_for('assets_bp.assets_twin_plan_page', plan_id=match.id))
    return render_template(
        'assets_twin.html',
        **_twin_drawing_page_vars(
            user, project, plans,
            draft_building=building,
            draft_floor=floor,
        ),
    )


@assets_bp.route('/scan')
@jwt_required()
def assets_scan_page():
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    return render_template(
        'assets_scan.html',
        user=user,
        can_write=_can_write(user),
    )


@assets_bp.route('/tag/<string:asset_code>/qr.png')
def assets_public_qr_png(asset_code):
    """Public QR image so the scan page never needs a login cookie."""
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    png = asset_qr_png_bytes(asset)
    return send_file(
        BytesIO(png),
        mimetype='image/png',
        as_attachment=False,
        download_name=f'{asset.asset_id}-qr.png',
        max_age=300,
    )


@assets_bp.route('/tag/<string:asset_code>')
def assets_public_tag(asset_code):
    """No-login operational summary opened by a phone-camera QR scan."""
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    return render_template(
        'assets_public_tag.html',
        asset=asset,
        url_qr_src=_png_data_uri(asset_qr_png_bytes(asset)),
    )


def _ticket_exec_stats():
    open_statuses = {
        'open', 'assigned', 'site_attended', 'work_started', 'work_completed',
        'verification', 'provider_closed', 'on_hold',
        'pending_supervisor', 'in_progress', 'pending_parts', 'pending_verification',
    }
    tickets = Ticket.query.filter(Ticket.status != 'draft').all()
    open_count = sum(1 for t in tickets if (t.status or '') in open_statuses)
    critical = sum(1 for t in tickets if t.priority == 'critical' and (t.status or '') in open_statuses)
    breached = 0
    now = _utcnow()
    for t in tickets:
        if not t.sla_hours or not t.created_at or (t.status or '') not in open_statuses:
            continue
        try:
            elapsed = (now - t.created_at).total_seconds() / 3600.0
            if elapsed > float(t.sla_hours):
                breached += 1
        except Exception:
            pass
    return {
        'total': len(tickets),
        'open': open_count,
        'critical_open': critical,
        'sla_breached': breached,
    }


@assets_bp.route('/list')
@jwt_required()
def assets_list_page():
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    return render_template(
        'assets_list.html',
        user=user,
        can_write=_can_write(user),
    )


@assets_bp.route('/new')
@jwt_required()
def assets_new_page():
    user = _current_user()
    if not _can_write(user):
        return redirect('/assets/')
    return render_template(
        'assets_form.html',
        user=user,
        asset=None,
        mode='create',
        can_write=True,
        locations=ticket_location_catalog(),
    )


@assets_bp.route('/<string:asset_code>')
@jwt_required()
def assets_detail_page(asset_code):
    user = _current_user()
    if not _has_access(user):
        return redirect('/dashboard')
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    link_ticket_ids = [
        row.ticket_id
        for row in TicketAsset.query.filter_by(asset_pk=asset.id).all()
    ]
    filters = [Ticket.asset_id == asset.id]
    if link_ticket_ids:
        filters.append(Ticket.id.in_(link_ticket_ids))
    tickets = (
        Ticket.query.filter(db.or_(*filters))
        .order_by(Ticket.created_at.desc())
        .limit(20)
        .all()
    )
    last_pred = (
        AssetPrediction.query.filter_by(asset_pk=asset.id)
        .order_by(AssetPrediction.created_at.desc())
        .first()
    )
    before = asset.qr_code
    ensure_asset_qr_code(asset)
    if asset.qr_code != before:
        db.session.commit()
    return render_template(
        'assets_detail.html',
        user=user,
        asset=asset,
        tickets=tickets,
        last_prediction=last_pred.to_dict() if last_pred else None,
        drawings=drawings_for_asset(asset.asset_id),
        can_write=_can_write(user),
        url_qr_src=_png_data_uri(asset_qr_png_bytes(asset)),
    )


@assets_bp.route('/<string:asset_code>/edit')
@jwt_required()
def assets_edit_page(asset_code):
    user = _current_user()
    if not _can_write(user):
        return redirect(f'/assets/{asset_code}')
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    return render_template(
        'assets_form.html',
        user=user,
        asset=asset,
        mode='edit',
        can_write=True,
        locations=ticket_location_catalog(),
    )


# ── API ────────────────────────────────────────────────────────────────

@assets_bp.route('/api/locations', methods=['GET'])
@jwt_required()
def api_ticket_locations():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return jsonify({'success': True, 'projects': ticket_location_catalog()})


@assets_bp.route('/api/assets', methods=['GET'])
@jwt_or_api_key_required
def api_list_assets():
    if getattr(g, 'auth_via', None) != 'api_key':
        user = _current_user()
        if not _has_access(user):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
    q = Asset.query
    status = request.args.get('status')
    building = request.args.get('building')
    floor = request.args.get('floor')
    search = (request.args.get('q') or '').strip()
    critical = request.args.get('critical')
    if status:
        q = q.filter(Asset.status == status)
    if building:
        q = q.filter(Asset.building == building)
    if floor:
        q = q.filter(Asset.floor == floor)
    pid, pid_err = _parse_project_id(request.args.get('project_id'))
    if pid_err:
        return jsonify({'success': False, 'error': pid_err}), 400
    if pid:
        q = q.filter(Asset.project_id == pid)
    if critical in ('1', 'true', 'yes'):
        q = q.filter(
            db.or_(
                Asset.status == 'critical',
                Asset.health_score.isnot(None) & (Asset.health_score < 40),
            )
        )
    if search:
        like = f'%{search}%'
        q = q.filter(
            db.or_(
                Asset.name.ilike(like),
                Asset.asset_id.ilike(like),
                Asset.qr_code.ilike(like),
                Asset.asset_type.ilike(like),
                Asset.serial_number.ilike(like),
                Asset.building.ilike(like),
            )
        )
    rows = q.order_by(Asset.name.asc()).limit(500).all()
    return jsonify({'success': True, 'assets': [a.to_dict() for a in rows]})


@assets_bp.route('/api/assets', methods=['POST'])
@jwt_required()
def api_create_asset():
    user = _current_user()
    if not _can_write(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data = request.get_json(silent=True) or {}
    if not (data.get('name') or '').strip():
        return jsonify({'success': False, 'error': 'name is required'}), 400
    asset = _asset_from_payload(data)
    if Asset.query.filter_by(asset_id=asset.asset_id).first():
        return jsonify({'success': False, 'error': f'Asset ID {asset.asset_id} already exists'}), 400
    db.session.add(asset)
    db.session.commit()
    fm_log_audit(user.id, 'asset_create', 'asset', asset.asset_id, {'name': asset.name})
    if (asset.status or '') == 'critical':
        dispatch_webhooks('asset.critical', asset.to_dict())
    return jsonify({'success': True, 'asset': asset.to_dict()}), 201


@assets_bp.route('/api/assets/<string:asset_code>', methods=['GET'])
@jwt_required()
def api_get_asset(asset_code):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    return jsonify({'success': True, 'asset': asset.to_dict()})


@assets_bp.route('/api/assets/<string:asset_code>', methods=['PUT'])
@jwt_required()
def api_update_asset(asset_code):
    user = _current_user()
    if not _can_write(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    data = request.get_json(silent=True) or {}
    if data.get('name') is not None and not str(data.get('name')).strip():
        return jsonify({'success': False, 'error': 'name is required'}), 400
    _asset_from_payload(data, asset=asset)
    db.session.commit()
    fm_log_audit(user.id, 'asset_update', 'asset', asset.asset_id, {'name': asset.name})
    if (asset.status or '') == 'critical':
        dispatch_webhooks('asset.critical', asset.to_dict())
    return jsonify({'success': True, 'asset': asset.to_dict()})


@assets_bp.route('/api/assets/<string:asset_code>', methods=['DELETE'])
@jwt_required()
def api_delete_asset(asset_code):
    user = _current_user()
    if not _can_write(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    Ticket.query.filter_by(asset_id=asset.id).update({'asset_id': None})
    code = asset.asset_id
    db.session.delete(asset)
    db.session.commit()
    fm_log_audit(user.id, 'asset_delete', 'asset', code, None)
    return jsonify({'success': True})


def _png_data_uri(png: bytes) -> str:
    return 'data:image/png;base64,' + b64encode(png).decode('ascii')


def _is_text_qr_request() -> bool:
    kind = (request.args.get('type') or request.args.get('kind') or '').strip().lower()
    return kind in ('text', 'plain', 'summary')


def _backfill_missing_qr_codes(assets):
    changed = False
    for asset in assets:
        before = asset.qr_code
        ensure_asset_qr_code(asset)
        if asset.qr_code != before:
            changed = True
    if changed:
        db.session.commit()


@assets_bp.route('/api/assets/<string:asset_code>/qr.png', methods=['GET'])
@jwt_required()
def api_asset_qr_png(asset_code):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    before = asset.qr_code
    ensure_asset_qr_code(asset)
    if asset.qr_code != before:
        db.session.commit()
    png = asset_qr_png_bytes(asset)
    if _is_text_qr_request():
        png = asset_text_qr_png_bytes(asset)
        filename = f'{asset.asset_id}-qr-text.png'
    else:
        filename = f'{asset.asset_id}-qr.png'
    as_attachment = (request.args.get('download') or '').lower() in ('1', 'true', 'yes')
    return send_file(
        BytesIO(png),
        mimetype='image/png',
        as_attachment=as_attachment,
        download_name=filename,
    )


@assets_bp.route('/api/assets/<string:asset_code>/qr-text.png', methods=['GET'])
@jwt_required()
def api_asset_qr_text_png(asset_code):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    before = asset.qr_code
    ensure_asset_qr_code(asset)
    if asset.qr_code != before:
        db.session.commit()
    png = asset_text_qr_png_bytes(asset)
    as_attachment = (request.args.get('download') or '').lower() in ('1', 'true', 'yes')
    return send_file(
        BytesIO(png),
        mimetype='image/png',
        as_attachment=as_attachment,
        download_name=f'{asset.asset_id}-qr-text.png',
    )


@assets_bp.route('/api/assets/<string:asset_code>/qr-label.pdf', methods=['GET'])
@jwt_required()
def api_asset_qr_label_pdf(asset_code):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    before = asset.qr_code
    ensure_asset_qr_code(asset)
    if asset.qr_code != before:
        db.session.commit()
    pdf = build_single_label_pdf(asset)
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{asset.asset_id}-qr-label.pdf',
    )


@assets_bp.route('/api/qr-labels.pdf', methods=['GET'])
@jwt_required()
def api_bulk_qr_labels_pdf():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    q = Asset.query
    status = request.args.get('status')
    search = (request.args.get('q') or '').strip()
    if status:
        q = q.filter(Asset.status == status)
    if search:
        like = f'%{search}%'
        q = q.filter(
            db.or_(
                Asset.name.ilike(like),
                Asset.asset_id.ilike(like),
                Asset.qr_code.ilike(like),
                Asset.asset_type.ilike(like),
                Asset.serial_number.ilike(like),
                Asset.building.ilike(like),
            )
        )
    assets = q.order_by(Asset.asset_id.asc()).all()
    _backfill_missing_qr_codes(assets)
    pdf = build_bulk_labels_pdf(assets)
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name='asset-qr-labels.pdf',
    )


@assets_bp.route('/api/kpis', methods=['GET'])
@jwt_required()
def api_kpis():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return jsonify({'success': True, 'kpis': compute_dashboard_kpis()})


@assets_bp.route('/api/narrative', methods=['GET'])
@jwt_required()
def api_cost_narrative():
    """Short Claude cost narrative for the executive dashboard (async-loaded)."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    try:
        from module_assistant.llm import generate_structured, StructuredLLMError, is_llm_enabled
        from module_assistant.tools import get_fm_cost_trend
    except ImportError:
        return jsonify({'success': True, 'narrative': None})
    if not is_llm_enabled():
        return jsonify({'success': True, 'narrative': None})

    trend = get_fm_cost_trend(user)
    if not trend.get('allowed'):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    system_prompt = (
        'You write one-line cost summaries for an FM executive dashboard. '
        'Respond with at most two short factual sentences in third person. '
        'Never use first person, never ask questions, never offer help, '
        'never mention missing data beyond a plain statement of the numbers. '
        'Example tone: "Maintenance costs rose 12% vs June, driven by HVAC work orders."'
    )
    user_content = (
        f"Cost facts:\n{json.dumps(trend, default=str)}\n\n"
        'Return JSON: {"narrative": "<max two sentences>"}'
    )
    try:
        result = generate_structured(
            system_prompt, user_content,
            {'required': ['narrative'], 'properties': {'narrative': str}},
        )
        narrative = (result.get('narrative') or '').strip()[:400] or None
    except StructuredLLMError as exc:
        logger.warning('Cost narrative failed: %s', exc)
        narrative = None
    return jsonify({'success': True, 'narrative': narrative})


@assets_bp.route('/api/assets/<string:asset_code>/predict', methods=['POST'])
@jwt_required()
def api_predict_asset(asset_code):
    """Phase 3 — Claude-reasoned failure/RUL estimate (method: llm_estimate)."""
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()

    try:
        from module_assistant.llm import generate_structured, StructuredLLMError, is_llm_enabled
    except ImportError:
        return jsonify({'success': False, 'error': 'LLM module unavailable'}), 503

    if not is_llm_enabled():
        return jsonify({'success': False, 'error': 'LLM is not enabled'}), 503

    history = (
        Ticket.query.filter_by(asset_id=asset.id)
        .order_by(Ticket.created_at.desc())
        .limit(30)
        .all()
    )
    history_lines = []
    for t in history:
        history_lines.append(
            f"- {t.ticket_id} [{t.status}] pri={t.priority} "
            f"{t.title} cost={t.total_cost or t.projected_cost or 0} "
            f"created={t.created_at.isoformat() if t.created_at else 'n/a'}"
        )

    system_prompt = (
        'You are an FM reliability analyst. Given an asset and its work-order history, '
        'estimate failure risk and remaining useful life. Be conservative. '
        'recommendation must be one of: maintain, replace, monitor.'
    )
    user_content = (
        f"Asset:\n{json.dumps(asset.to_dict(), default=str)}\n\n"
        f"Work order history ({len(history_lines)} recent):\n"
        + ('\n'.join(history_lines) if history_lines else '(none)')
        + '\n\nReturn JSON with keys: failure_probability_pct (number 0-100), '
        'rul_days (integer), predicted_maintenance_cost (number), '
        'recommendation (maintain|replace|monitor), justification (short string).'
    )
    schema = {
        'required': [
            'failure_probability_pct', 'rul_days', 'predicted_maintenance_cost',
            'recommendation', 'justification',
        ],
        'properties': {
            'failure_probability_pct': (int, float),
            'rul_days': int,
            'predicted_maintenance_cost': (int, float),
            'recommendation': str,
            'justification': str,
        },
    }
    try:
        result = generate_structured(system_prompt, user_content, schema)
    except StructuredLLMError as exc:
        logger.warning('Asset predict failed for %s: %s', asset_code, exc)
        return jsonify({'success': False, 'error': str(exc)}), 502

    rec = (result.get('recommendation') or 'monitor').strip().lower()
    if rec not in ('maintain', 'replace', 'monitor'):
        rec = 'monitor'
    try:
        fpp = float(result['failure_probability_pct'])
        fpp = max(0.0, min(100.0, fpp))
    except (TypeError, ValueError):
        fpp = 0.0
    try:
        rul = int(result['rul_days'])
        rul = max(0, min(3650, rul))
    except (TypeError, ValueError):
        rul = 0
    try:
        pmc = float(result['predicted_maintenance_cost'])
        pmc = max(0.0, pmc)
    except (TypeError, ValueError):
        pmc = 0.0

    payload = {
        'failure_probability_pct': round(fpp, 1),
        'rul_days': rul,
        'predicted_maintenance_cost': round(pmc, 2),
        'recommendation': rec,
        'justification': (result.get('justification') or '')[:500],
        'method': 'llm_estimate',
        'asset_id': asset.asset_id,
    }
    pred = AssetPrediction(
        asset_pk=asset.id,
        failure_probability_pct=payload['failure_probability_pct'],
        rul_days=payload['rul_days'],
        predicted_maintenance_cost=payload['predicted_maintenance_cost'],
        recommendation=payload['recommendation'],
        justification=payload['justification'],
        method='llm_estimate',
    )
    db.session.add(pred)
    db.session.commit()
    payload['prediction_id'] = pred.id
    payload['created_at'] = pred.created_at.isoformat() if pred.created_at else None
    return jsonify({'success': True, 'prediction': payload})


@assets_bp.route('/api/assets/<string:asset_code>/prediction', methods=['GET'])
@jwt_required()
def api_last_prediction(asset_code):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    asset = Asset.query.filter_by(asset_id=asset_code).first_or_404()
    pred = (
        AssetPrediction.query.filter_by(asset_pk=asset.id)
        .order_by(AssetPrediction.created_at.desc())
        .first()
    )
    if not pred:
        return jsonify({'success': True, 'prediction': None})
    data = pred.to_dict()
    data['asset_id'] = asset.asset_id
    return jsonify({'success': True, 'prediction': data})


@assets_bp.route('/api/map-points', methods=['GET'])
@jwt_required()
def api_map_points():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    points = []
    for a in Asset.query.filter(Asset.latitude.isnot(None), Asset.longitude.isnot(None)).all():
        open_tickets = Ticket.query.filter(
            Ticket.asset_id == a.id,
            Ticket.status.notin_(['closed', 'cancelled', 'draft', 'resolved']),
        ).count()
        points.append({
            **a.to_dict(),
            'open_tickets': open_tickets,
        })
    return jsonify({'success': True, 'points': points})


@assets_bp.route('/api/forecast', methods=['POST'])
@jwt_required()
def api_portfolio_forecast():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    try:
        from module_assistant.llm import generate_structured, StructuredLLMError, is_llm_enabled
    except ImportError:
        return jsonify({'success': False, 'error': 'LLM unavailable'}), 503
    if not is_llm_enabled():
        return jsonify({'success': False, 'error': 'LLM is not enabled'}), 503

    kpis = compute_dashboard_kpis()
    ticket_stats = _ticket_exec_stats()
    assets = [a.to_dict() for a in Asset.query.limit(80).all()]
    system_prompt = (
        'You are an FM portfolio analyst. Forecast next-quarter budget, failure volume, '
        'and spare-parts demand from the provided KPIs and assets. Be conservative.'
    )
    user_content = (
        f"KPIs:\n{json.dumps(kpis, default=str)}\n\nTicket stats:\n{json.dumps(ticket_stats)}\n\n"
        f"Assets sample ({len(assets)}):\n{json.dumps(assets[:40], default=str)}\n\n"
        'Return JSON with: budget_forecast (number), failure_count_forecast (integer), '
        'spare_parts_top (list of strings), narrative (short string), horizon_days (integer).'
    )
    schema = {
        'required': ['budget_forecast', 'failure_count_forecast', 'spare_parts_top', 'narrative', 'horizon_days'],
        'properties': {
            'budget_forecast': (int, float),
            'failure_count_forecast': int,
            'spare_parts_top': list,
            'narrative': str,
            'horizon_days': int,
        },
    }
    try:
        result = generate_structured(system_prompt, user_content, schema)
    except StructuredLLMError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502

    payload = {
        'budget_forecast': float(result.get('budget_forecast') or 0),
        'failure_count_forecast': int(result.get('failure_count_forecast') or 0),
        'spare_parts_top': list(result.get('spare_parts_top') or [])[:15],
        'narrative': (result.get('narrative') or '')[:800],
        'horizon_days': max(30, min(365, int(result.get('horizon_days') or 90))),
        'method': 'llm_estimate',
    }
    row = PortfolioForecast(payload=payload, method='llm_estimate', created_by=user.id)
    db.session.add(row)
    db.session.commit()
    return jsonify({'success': True, 'forecast': row.to_dict()})


@assets_bp.route('/api/forecast/latest', methods=['GET'])
@jwt_required()
def api_forecast_latest():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    row = PortfolioForecast.query.order_by(PortfolioForecast.created_at.desc()).first()
    return jsonify({'success': True, 'forecast': row.to_dict() if row else None})


def _plan_from_request():
    """Parse create/update fields from JSON or multipart form.

    Only includes keys the client actually sent so a pin-only PUT cannot
    wipe name/floor/image.
    """
    data = {}
    if request.files or (request.content_type or '').startswith('multipart/'):
        form = request.form
        for key in ('name', 'building', 'floor', 'image_url', 'project_id'):
            if key in form:
                data[key] = (form.get(key) or '').strip()
        if 'hotspots' in form:
            data['hotspots'] = form.get('hotspots')
        return data, request.files.get('image') or request.files.get('file')
    raw = request.get_json(silent=True) or {}
    for key in ('name', 'building', 'floor', 'image_url', 'project_id'):
        if key not in raw:
            continue
        val = raw.get(key)
        data[key] = '' if val is None else str(val).strip()
    if 'hotspots' in raw:
        data['hotspots'] = raw.get('hotspots')
    return data, None


@assets_bp.route('/api/floor-plans', methods=['GET', 'POST'])
@jwt_required()
def api_floor_plans():
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    if request.method == 'GET':
        q = FloorPlan.query
        raw_pid = request.args.get('project_id')
        if raw_pid in ('none', 'null'):
            q = q.filter(FloorPlan.project_id.is_(None))
        elif raw_pid not in (None, ''):
            pid, err = _parse_project_id(raw_pid)
            if err:
                return jsonify({'success': False, 'error': err}), 400
            q = q.filter_by(project_id=pid)
        rows = q.order_by(FloorPlan.building, FloorPlan.floor).all()
        return jsonify({'success': True, 'plans': [enrich_floor_plan(r) for r in rows]})
    if not _can_write(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data, image = _plan_from_request()
    if not (data.get('name') and data.get('building')):
        return jsonify({'success': False, 'error': 'name and building required'}), 400
    project_id = None
    if 'project_id' in data:
        project_id, err = _parse_project_id(data.get('project_id'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
    hotspots = normalize_hotspots(data.get('hotspots') or [])
    plan = FloorPlan(
        name=data['name'],
        building=data['building'],
        floor=data.get('floor') or None,
        image_url=data.get('image_url') or DEFAULT_PLAN_SVG,
        hotspots=hotspots,
        project_id=project_id,
    )
    db.session.add(plan)
    db.session.flush()
    if image and image.filename:
        url, err = save_plan_image(plan, image)
        if err:
            db.session.rollback()
            return jsonify({'success': False, 'error': err}), 400
        plan.image_url = url
    db.session.commit()
    return jsonify({'success': True, 'plan': enrich_floor_plan(plan)}), 201


@assets_bp.route('/api/floor-plans/<int:plan_id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def api_floor_plan_detail(plan_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    plan = FloorPlan.query.get_or_404(plan_id)
    if request.method == 'GET':
        return jsonify({'success': True, 'plan': enrich_floor_plan(plan)})
    if not _can_write(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    if request.method == 'DELETE':
        db.session.delete(plan)
        db.session.commit()
        return jsonify({'success': True})
    data, image = _plan_from_request()
    if data.get('name'):
        plan.name = data['name']
    if data.get('building'):
        plan.building = data['building']
    if 'floor' in data:
        plan.floor = data.get('floor') or None
    if data.get('image_url'):
        plan.image_url = data['image_url']
    if 'project_id' in data:
        pid, err = _parse_project_id(data.get('project_id'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        plan.project_id = pid
    if 'hotspots' in data:
        plan.hotspots = normalize_hotspots(data.get('hotspots'))
    if image and image.filename:
        url, err = save_plan_image(plan, image)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        plan.image_url = url
    db.session.commit()
    return jsonify({'success': True, 'plan': enrich_floor_plan(plan)})


@assets_bp.route('/api/floor-plans/<int:plan_id>/image', methods=['POST'])
@jwt_required()
def api_floor_plan_image(plan_id):
    user = _current_user()
    if not _can_write(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    plan = FloorPlan.query.get_or_404(plan_id)
    image = request.files.get('image') or request.files.get('file')
    if not image or not image.filename:
        return jsonify({'success': False, 'error': 'image file required'}), 400
    url, err = save_plan_image(plan, image)
    if err:
        return jsonify({'success': False, 'error': err}), 400
    db.session.commit()
    return jsonify({'success': True, 'plan': enrich_floor_plan(plan), 'image_url': url})


@assets_bp.route('/api/floor-plans/<int:plan_id>/file', methods=['GET'])
@jwt_required()
def api_floor_plan_file(plan_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    plan = FloorPlan.query.get_or_404(plan_id)
    url = plan.image_url or ''
    if url.startswith('/static/uploads/floor-plans/'):
        path = os.path.join(current_app.root_path, url.lstrip('/'))
        if os.path.isfile(path):
            return send_file(path)
    return jsonify({'success': False, 'error': 'No uploaded file'}), 404


@assets_bp.route('/api/floor-plans/<int:plan_id>/recommend', methods=['POST'])
@jwt_required()
def api_twin_recommend(plan_id):
    user = _current_user()
    if not _has_access(user):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    plan = FloorPlan.query.get_or_404(plan_id)
    enriched = enrich_floor_plan(plan)
    fallback = recommend_fallback(enriched)

    try:
        from module_assistant.llm import generate_structured, StructuredLLMError, is_llm_enabled
    except ImportError:
        return jsonify({'success': True, **fallback})
    if not is_llm_enabled():
        return jsonify({'success': True, **fallback})

    system_prompt = (
        'You are an FM digital-twin advisor. Given live room status from a 2D floor plan '
        '(severity crit/warn/ok, linked assets, open work orders), recommend next actions. '
        'Prioritise critical rooms. Return JSON only.'
    )
    user_content = (
        f"Plan: {json.dumps({k: enriched[k] for k in ('id', 'name', 'building', 'floor')})}\n"
        f"Live hotspots: {json.dumps(enriched.get('hotspots') or [], default=str)}\n"
        'Return JSON: recommendations (list of {room, severity, action, reason}), summary (string).'
    )
    schema = {
        'required': ['recommendations', 'summary'],
        'properties': {'recommendations': list, 'summary': str},
    }
    try:
        result = generate_structured(system_prompt, user_content, schema)
    except StructuredLLMError:
        return jsonify({'success': True, **fallback})
    recs = result.get('recommendations') or []
    if not isinstance(recs, list):
        recs = []
    return jsonify({
        'success': True,
        'method': 'llm_estimate',
        'summary': result.get('summary') or fallback['summary'],
        'recommendations': recs or fallback['recommendations'],
    })


@assets_bp.route('/api/integration/api-keys', methods=['GET', 'POST'])
@jwt_required()
def api_integration_keys():
    user = _current_user()
    if not user or user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    if request.method == 'GET':
        rows = IntegrationApiKey.query.order_by(IntegrationApiKey.created_at.desc()).all()
        return jsonify({'success': True, 'keys': [r.to_dict() for r in rows]})
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or 'Integration key').strip()
    row, raw = create_api_key(name, created_by=user.id)
    fm_log_audit(user.id, 'api_key_create', 'integration_api_key', row.id, {'name': name})
    return jsonify({'success': True, 'key': row.to_dict(), 'raw_key': raw}), 201


@assets_bp.route('/api/integration/webhooks', methods=['GET', 'POST'])
@jwt_required()
def api_webhooks():
    user = _current_user()
    if not user or user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    if request.method == 'GET':
        rows = OutboundWebhook.query.order_by(OutboundWebhook.created_at.desc()).all()
        return jsonify({'success': True, 'webhooks': [r.to_dict() for r in rows]})
    data = request.get_json(silent=True) or {}
    if not data.get('name') or not data.get('target_url'):
        return jsonify({'success': False, 'error': 'name and target_url required'}), 400
    hook = OutboundWebhook(
        name=data['name'].strip(),
        target_url=data['target_url'].strip(),
        secret=(data.get('secret') or '').strip() or None,
        events=data.get('events') or ['ticket.created', 'ticket.closed', 'asset.critical'],
        is_active=True,
    )
    db.session.add(hook)
    db.session.commit()
    return jsonify({'success': True, 'webhook': hook.to_dict()}), 201


@assets_bp.route('/api/docs/integration', methods=['GET'])
@jwt_required()
def api_integration_docs():
    """Lightweight integration surface documentation for the vendor checklist."""
    return jsonify({
        'success': True,
        'auth': {
            'jwt': 'Authorization: Bearer <access_token>',
            'api_key': 'X-API-Key: inj_... (admin-created)',
        },
        'endpoints': [
            {'method': 'GET', 'path': '/assets/api/assets', 'auth': 'jwt|api_key'},
            {'method': 'GET', 'path': '/assets/api/kpis', 'auth': 'jwt'},
            {'method': 'POST', 'path': '/assets/api/forecast', 'auth': 'jwt'},
            {'method': 'GET', 'path': '/tickets/api/tickets', 'auth': 'jwt'},
            {'method': 'POST', 'path': '/tickets/api/tickets', 'auth': 'jwt'},
        ],
        'webhooks': {
            'events': ['ticket.created', 'ticket.closed', 'asset.critical'],
            'configure': 'POST /assets/api/integration/webhooks',
        },
        'note': 'ERP/BMS/SCADA connectors require client discovery; not speculative.',
    })
