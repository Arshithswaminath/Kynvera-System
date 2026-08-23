"""2D Digital Twin: live pin status, plan CRUD, recommendations without LLM."""
from io import BytesIO
from pathlib import Path

from app.models import db, Asset, FloorPlan, Ticket, TicketProject


def _add_asset(app, **kwargs):
    defaults = dict(
        asset_id='AST-TWIN-1',
        name='Chiller CH-01',
        asset_type='chiller',
        building='Tower A',
        floor='B1',
        room='Plant Room 1',
        status='active',
        health_score=82,
    )
    defaults.update(kwargs)
    with app.app_context():
        row = Asset(**defaults)
        db.session.add(row)
        db.session.commit()
        return row.id, row.asset_id


def _add_ticket(app, admin_user, asset_pk, **kwargs):
    defaults = dict(
        ticket_id='TKT-TWIN01',
        reporter_id=admin_user.id,
        project='Marina Towers',
        service_group='HVAC',
        category='Chiller',
        fault_type='Performance',
        priority='critical',
        title='High condenser pressure',
        work_description='Alarm on CH-01',
        status='open',
        asset_id=asset_pk,
    )
    defaults.update(kwargs)
    with app.app_context():
        row = Ticket(**defaults)
        db.session.add(row)
        db.session.commit()
        return row.ticket_id


def _add_plan(app, **kwargs):
    defaults = dict(
        name='Tower A L3 Mechanical',
        building='Tower A',
        floor='L3',
        image_url='https://example.test/plan.png',
        hotspots=[
            {'id': 'hs-plant', 'room': 'Plant Room 1', 'x_pct': 22, 'y_pct': 28, 'asset_ids': ['AST-TWIN-1']},
            {'id': 'hs-lobby', 'room': 'Lobby', 'x_pct': 50, 'y_pct': 72, 'asset_ids': []},
        ],
    )
    defaults.update(kwargs)
    with app.app_context():
        row = FloorPlan(**defaults)
        db.session.add(row)
        db.session.commit()
        return row.id


def _cleanup(app, plan_id=None, asset_ids=None, ticket_ids=None, project_ids=None):
    with app.app_context():
        for tid in ticket_ids or []:
            row = Ticket.query.filter_by(ticket_id=tid).first()
            if row:
                db.session.delete(row)
        if plan_id:
            row = FloorPlan.query.get(plan_id)
            if row:
                db.session.delete(row)
        for pid in project_ids or []:
            row = TicketProject.query.get(pid)
            if row:
                db.session.delete(row)
        for code in asset_ids or []:
            row = Asset.query.filter_by(asset_id=code).first()
            if row:
                db.session.delete(row)
        db.session.commit()


def _add_project(app, **kwargs):
    defaults = dict(name='Marina Twin Hub', client_name='Acme FM', is_active=True)
    defaults.update(kwargs)
    with app.app_context():
        row = TicketProject(**defaults)
        db.session.add(row)
        db.session.commit()
        return row.id


def test_twin_hub_lists_ticket_projects(client, app, admin_auth_headers):
    pid = _add_project(app)
    plan_id = _add_plan(app, project_id=pid, name='Hub assigned floor')
    try:
        res = client.get('/assets/twin', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'Marina Twin Hub' in html
        assert 'twin-hub-grid' in html
        assert 'planSelect' not in html
        assert 'twin-workspace' not in html
        assert 'fm-twin.js' not in html
    finally:
        _cleanup(app, plan_id=plan_id, project_ids=[pid])


def test_twin_drawing_page_has_ops_hooks(client, app, admin_auth_headers):
    plan_id = _add_plan(app)
    try:
        res = client.get(f'/assets/twin/plan/{plan_id}', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'twin-workspace' in html
        assert 'planSelect' in html
        assert 'jumpBuilding' in html
        assert 'jumpFloor' in html
        assert 'twinPinPanel' in html
        assert 'Place pins' in html
        assert 'downloadPlanBtn' in html
        assert 'Download drawing' in html
        assert 'fm-twin.js' in html
    finally:
        _cleanup(app, plan_id=plan_id)


def test_twin_js_exports_drawing_with_kynvera_logo():
    js = (Path(__file__).resolve().parents[1] / 'static' / 'js' / 'fm-twin.js').read_text()
    assert 'function downloadDrawing' in js
    assert 'kynvera-wordmark.png' in js
    assert 'drawKynveraFooter' in js


def test_twin_legacy_plan_query_redirects(client, app, admin_auth_headers):
    plan_id = _add_plan(app)
    try:
        res = client.get(f'/assets/twin?plan={plan_id}&pin=hs-plant', headers=admin_auth_headers)
        assert res.status_code in (301, 302)
        loc = res.headers.get('Location') or ''
        assert f'/assets/twin/plan/{plan_id}' in loc
        assert 'pin=hs-plant' in loc
    finally:
        _cleanup(app, plan_id=plan_id)


def test_twin_project_page_lists_only_that_project(client, app, admin_auth_headers):
    pid = _add_project(app, name='Project Alpha Twin')
    other = _add_project(app, name='Project Beta Twin')
    mine = _add_plan(app, project_id=pid, name='Alpha Ground Floor')
    theirs = _add_plan(app, project_id=other, name='Beta Roof Plan')
    try:
        res = client.get(f'/assets/twin/project/{pid}', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'Alpha Ground Floor' in html
        assert 'Beta Roof Plan' not in html
        listed = client.get(f'/assets/api/floor-plans?project_id={pid}', headers=admin_auth_headers)
        assert listed.status_code == 200
        names = [p['name'] for p in listed.get_json()['plans']]
        assert 'Alpha Ground Floor' in names
        assert 'Beta Roof Plan' not in names
    finally:
        _cleanup(app, plan_id=mine, project_ids=[pid])
        _cleanup(app, plan_id=theirs, project_ids=[other])


def test_twin_project_jump_and_fed_assets(client, app, admin_auth_headers):
    from tests.factories import make_location_hierarchy

    with app.app_context():
        loc = make_location_hierarchy(
            project_name='HQ Jump Twin',
            property_name='HQ Building',
            zone_name='Ground floor',
            base_unit_name='Reception',
        )
        pid = loc['project'].id
    _, code = _add_asset(
        app,
        asset_id='AST-JUMP-1',
        name='AHU-01',
        project_id=pid,
        building='HQ Building',
        floor='Ground floor',
        room='Reception',
    )
    other_code = _add_asset(
        app,
        asset_id='AST-JUMP-2',
        name='Pump-09',
        project_id=pid,
        building='HQ Building',
        floor='First floor',
        room='Plant',
    )[1]
    plan_id = _add_plan(
        app,
        project_id=pid,
        name='HQ Ground',
        building='HQ Building',
        floor='Ground floor',
    )
    try:
        res = client.get(f'/assets/twin/project/{pid}', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'jumpBuilding' in html
        assert 'jumpFloor' in html
        assert 'Still want to open?' in html
        assert 'twinConfirm' in html
        assert 'HQ Building' in html
        assert 'Ground floor' in html
        assert 'AST-JUMP-1' in html
        assert 'twinFeed' in html
        assert '/assets/twin/plan/' in html
        assert '/assets/twin/project/' in html
        assert '/draw?' in html
        assert str(plan_id) in html
        assert 'place' in html
        listed = client.get(
            f'/assets/api/assets?project_id={pid}&building=HQ Building&floor=Ground floor',
            headers=admin_auth_headers,
        )
        assert listed.status_code == 200
        codes = [a['asset_id'] for a in listed.get_json()['assets']]
        assert 'AST-JUMP-1' in codes
        assert 'AST-JUMP-2' not in codes
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code, other_code], project_ids=[pid])


def test_twin_js_does_not_scroll_document_on_pin_select():
    js = Path('static/js/fm-twin.js').read_text(encoding='utf-8')
    assert 'scrollIntoView' not in js
    assert 'preventScroll: true' in js
    assert 'overflow-anchor' not in js  # CSS, not JS
    css = Path('static/css/fm-assets.css').read_text(encoding='utf-8')
    assert 'overflow-anchor: none' in css
    assert 'twin-floor-loc' in js
    assert 'twin-floor-empty' in js
    assert 'function showDraft' in js
    assert 'Still want to open?' in js
    assert 'twin-draft' in js


def test_twin_empty_draw_page_for_floor_without_plan(client, app, admin_auth_headers):
    from tests.factories import make_location_hierarchy

    with app.app_context():
        loc = make_location_hierarchy(
            project_name='HQ Empty Draw',
            property_name='HQ Building',
            zone_name='Ground floor',
            base_unit_name='Reception',
        )
        pid = loc['project'].id
    plan_id = _add_plan(
        app,
        project_id=pid,
        name='HQ Ground',
        building='HQ Building',
        floor='Ground floor',
    )
    try:
        res = client.get(
            f'/assets/twin/project/{pid}/draw?building=HQ Building&floor=First Floor',
            headers=admin_auth_headers,
        )
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'FM_TWIN_DRAFT' in html
        assert 'First Floor' in html
        assert 'Add a drawing for this floor' in html
        assert 'twin-workspace' in html
        assert 'fm-twin.js' in html

        existing = client.get(
            f'/assets/twin/project/{pid}/draw?building=HQ Building&floor=Ground Floor',
            headers=admin_auth_headers,
        )
        assert existing.status_code in (301, 302)
        loc_hdr = existing.headers.get('Location') or ''
        assert f'/assets/twin/plan/{plan_id}' in loc_hdr
    finally:
        _cleanup(app, plan_id=plan_id, project_ids=[pid])


def test_live_status_critical_from_open_ticket(client, app, admin_user, admin_auth_headers):
    pk, code = _add_asset(app)
    tkt = _add_ticket(app, admin_user, pk)
    plan_id = _add_plan(app)
    try:
        res = client.get(f'/assets/api/floor-plans/{plan_id}', headers=admin_auth_headers)
        assert res.status_code == 200
        plan = res.get_json()['plan']
        plant = next(h for h in plan['hotspots'] if h['room'] == 'Plant Room 1')
        lobby = next(h for h in plan['hotspots'] if h['room'] == 'Lobby')
        assert plant['severity'] == 'crit'
        assert plant['open_ticket_count'] >= 1
        assert plant['open_tickets'][0]['ticket_id'] == tkt
        assert lobby['severity'] == 'ok'
        assert plan['counts']['crit'] >= 1
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code], ticket_ids=[tkt])


def test_asset_ids_match_across_floors(client, app, admin_user, admin_auth_headers):
    """Hotspot on L3 still lights up an asset whose floor is B1 when asset_ids is set."""
    pk, code = _add_asset(app, floor='B1', health_score=30, status='active')
    plan_id = _add_plan(app, floor='L3')
    try:
        res = client.get(f'/assets/api/floor-plans/{plan_id}', headers=admin_auth_headers)
        plant = next(h for h in res.get_json()['plan']['hotspots'] if 'Plant' in h['room'])
        assert plant['severity'] == 'crit'
        assert code in plant['asset_ids']
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code])


def test_put_and_delete_plan(client, app, admin_auth_headers):
    plan_id = _add_plan(app, name='Temp plan', hotspots=[])
    try:
        res = client.put(
            f'/assets/api/floor-plans/{plan_id}',
            headers=admin_auth_headers,
            json={
                'hotspots': [
                    {'room': 'AHU room', 'x_pct': 40, 'y_pct': 60, 'asset_ids': []},
                ]
            },
        )
        assert res.status_code == 200
        pins = res.get_json()['plan']['hotspots']
        assert len(pins) == 1
        assert pins[0]['room'] == 'AHU room'
        gone = client.delete(f'/assets/api/floor-plans/{plan_id}', headers=admin_auth_headers)
        assert gone.status_code == 200
        missing = client.get(f'/assets/api/floor-plans/{plan_id}', headers=admin_auth_headers)
        assert missing.status_code == 404
        plan_id = None
    finally:
        _cleanup(app, plan_id=plan_id)


def test_create_plan_without_image_url(client, app, admin_auth_headers):
    res = client.post(
        '/assets/api/floor-plans',
        headers=admin_auth_headers,
        json={'name': 'Twin create', 'building': 'Tower Z', 'floor': 'L1'},
    )
    assert res.status_code == 201
    plan = res.get_json()['plan']
    assert plan['name'] == 'Twin create'
    assert plan['display_url']
    _cleanup(app, plan_id=plan['id'])


def test_recommend_fallback_without_llm(client, app, admin_user, admin_auth_headers):
    pk, code = _add_asset(app, asset_id='AST-TWIN-2')
    tkt = _add_ticket(app, admin_user, pk, ticket_id='TKT-TWIN02')
    plan_id = _add_plan(
        app,
        hotspots=[{'room': 'Plant Room 1', 'x_pct': 20, 'y_pct': 20, 'asset_ids': ['AST-TWIN-2']}],
    )
    try:
        res = client.post(
            f'/assets/api/floor-plans/{plan_id}/recommend',
            headers=admin_auth_headers,
            json={},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert data['method'] == 'live_status'
        assert data['recommendations']
        assert any(r.get('severity') == 'crit' for r in data['recommendations'])
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code], ticket_ids=[tkt])


def test_image_upload(client, app, admin_auth_headers):
    plan_id = _add_plan(app)
    try:
        png = BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 24)
        png.name = 'plan.png'
        res = client.post(
            f'/assets/api/floor-plans/{plan_id}/image',
            headers=admin_auth_headers,
            data={'image': (png, 'plan.png')},
            content_type='multipart/form-data',
        )
        assert res.status_code == 200
        url = res.get_json()['image_url']
        assert url.startswith('/static/uploads/floor-plans/')
    finally:
        _cleanup(app, plan_id=plan_id)


def test_closed_ticket_does_not_turn_pin_red(client, app, admin_user, admin_auth_headers):
    pk, code = _add_asset(app, asset_id='AST-TWIN-3', health_score=90)
    tkt = _add_ticket(
        app, admin_user, pk,
        ticket_id='TKT-TWIN03',
        status='closed',
        priority='critical',
    )
    plan_id = _add_plan(
        app,
        hotspots=[{'room': 'Plant Room 1', 'x_pct': 20, 'y_pct': 20, 'asset_ids': ['AST-TWIN-3']}],
    )
    try:
        res = client.get(f'/assets/api/floor-plans/{plan_id}', headers=admin_auth_headers)
        plant = res.get_json()['plan']['hotspots'][0]
        assert plant['severity'] == 'ok'
        assert plant['open_ticket_count'] == 0
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code], ticket_ids=[tkt])


def test_manual_pin_health_overrides_live(client, app, admin_user, admin_auth_headers):
    pk, code = _add_asset(app, asset_id='AST-TWIN-4', health_score=20, status='critical')
    tkt = _add_ticket(app, admin_user, pk, ticket_id='TKT-TWIN04', priority='critical')
    plan_id = _add_plan(
        app,
        hotspots=[{
            'room': 'Plant Room 1',
            'x_pct': 20,
            'y_pct': 20,
            'asset_ids': ['AST-TWIN-4'],
            'severity': 'ok',
        }],
    )
    try:
        res = client.get(f'/assets/api/floor-plans/{plan_id}', headers=admin_auth_headers)
        plant = res.get_json()['plan']['hotspots'][0]
        assert plant['severity'] == 'ok'
        assert plant['live_severity'] == 'crit'
        put = client.put(
            f'/assets/api/floor-plans/{plan_id}',
            headers=admin_auth_headers,
            json={'hotspots': [{
                'room': 'Plant Room 1',
                'x_pct': 20,
                'y_pct': 20,
                'asset_ids': ['AST-TWIN-4'],
                'severity': 'warn',
            }]},
        )
        assert put.status_code == 200
        updated = put.get_json()['plan']['hotspots'][0]
        assert updated['severity'] == 'warn'
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code], ticket_ids=[tkt])


def test_asset_detail_shows_linked_drawing(client, app, admin_auth_headers):
    pk, code = _add_asset(app, asset_id='AST-TWIN-5')
    plan_id = _add_plan(
        app,
        name='Linked drawing plan',
        hotspots=[{
            'id': 'hs-ahu',
            'room': 'Plant Room 2',
            'x_pct': 30,
            'y_pct': 40,
            'asset_ids': ['AST-TWIN-5'],
        }],
    )
    try:
        res = client.get(f'/assets/{code}', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'Linked drawings' in html
        assert 'Linked drawing plan' in html
        assert f'/assets/twin/plan/{plan_id}' in html
        assert 'Plant Room 2' in html
    finally:
        _cleanup(app, plan_id=plan_id, asset_ids=[code])
