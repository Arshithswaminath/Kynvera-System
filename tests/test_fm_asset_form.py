"""New/edit asset form uses Service Tickets location catalog."""
from app.models import db, TicketProject

from tests.factories import make_location_hierarchy


def test_locations_api_maps_project_property_zone_unit(client, app, admin_auth_headers):
    with app.app_context():
        loc = make_location_hierarchy(
            project_name='FM Catalog Project',
            property_name='FM Catalog Tower',
            zone_name='FM Catalog L3',
            base_unit_name='FM Catalog Plant',
        )
        pid = loc['project'].id
    try:
        res = client.get('/assets/api/locations', headers=admin_auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        proj = next(p for p in data['projects'] if p['name'] == 'FM Catalog Project')
        assert proj['id'] == pid
        tower = next(b for b in proj['buildings'] if b['name'] == 'FM Catalog Tower')
        floors = {f['name']: f for f in tower['floors']}
        assert 'FM Catalog L3' in floors
        rooms = [r['name'] for r in floors['FM Catalog L3']['rooms']]
        assert 'FM Catalog Plant' in rooms
    finally:
        with app.app_context():
            row = db.session.get(TicketProject, pid)
            if row:
                db.session.delete(row)
                db.session.commit()


def test_new_asset_form_embeds_ticket_project(client, app, admin_auth_headers):
    with app.app_context():
        loc = make_location_hierarchy(
            project_name='FM Form Project',
            property_name='FM Form Building',
            zone_name='FM Form Mezz',
            base_unit_name='FM Form Pantry',
        )
        pid = loc['project'].id
    try:
        res = client.get('/assets/new', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'assetProject' in html
        assert 'FM Form Project' in html
        assert 'FM Form Building' in html
        assert 'project → property → zone → unit' in html
    finally:
        with app.app_context():
            row = db.session.get(TicketProject, pid)
            if row:
                db.session.delete(row)
                db.session.commit()


def test_assets_map_page_has_list_split(client, admin_auth_headers):
    res = client.get('/assets/map', headers=admin_auth_headers)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'fm-gis-split' in html
    assert 'fm-gis-map' in html
    assert 'fmGisList' in html
    assert 'focusAsset' in html
    assert 'markerZoomAnimation: false' in html
    assert 'flyTo' not in html
    assert 'GIS — Asset map' not in html
    assert 'tkt-topbar-title">Map</h1>' in html
    assert '<h1>Map</h1>' not in html.split('tkt-content', 1)[-1]


def test_fm_human_label_readable():
    from module_assets.routes import fm_human_label
    assert fm_human_label('active') == 'Active'
    assert fm_human_label('package_unit') == 'Package unit'
    assert fm_human_label('AHU') == 'AHU'
    assert fm_human_label('work_started') == 'Work started'
    assert fm_human_label(None) == '—'


class TestFmAssetsClickins:
    def test_dashboard_menu_chip_hides_back(self, client, admin_auth_headers):
        res = client.get('/assets/', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'tkt-menu-toggle' in html
        assert 'tkt-menu-toggle-label">Menu</span>' in html
        assert 'App Home' in html
        assert 'Main dashboard' not in html
        assert 'data-module-back' not in html
        assert '<h1>FM Assets</h1>' not in html
        assert 'tkt-topbar-title">Dashboard</h1>' in html
        assert 'Welcome back' in html
        assert 'Performance' in html
        assert 'id="fmDashChart"' in html
        assert 'aria-label="Daily work orders and assets"' in html
        assert 'Last 30 days' in html
        assert 'Asset status' in html
        assert 'Assets by building' in html
        assert 'Warranty mix' in html
        assert 'id="fmStatusChart"' in html
        assert 'id="fmWarrantyChart"' in html
        assert 'Recent assets' in html
        assert 'Buildings' in html
        assert '/assets/api/assets.xlsx' in html
        assert 'chart.js' in html
        assert 'fm-dash-page' in html
        assert 'fm-wrap-wide' in html
        assert 'id="fmDashTip"' in html
        assert 'fm-dash-pill' in html
        assert 'fm-dash-rule' in html

    def test_inner_pages_back_to_fm_hub(self, client, admin_auth_headers):
        res = client.get('/assets/list', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'data-module-back' in html
        assert 'href="/assets/"' in html
        assert '<h1>All assets</h1>' not in html
        assert 'tkt-topbar-title">All assets</h1>' in html

    def test_add_asset_matches_sidebar_and_single_back(self, client, admin_auth_headers):
        res = client.get('/assets/new', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'tkt-topbar-title">Add asset</h1>' in html
        assert '← Dashboard' not in html
        assert 'New asset' not in html
        assert html.count('data-module-back') == 1
        assert '>Active</option>' in html

    def test_executive_empty_forecast_and_scan_title(self, client, admin_auth_headers):
        exec_html = client.get('/assets/executive', headers=admin_auth_headers).get_data(as_text=True)
        assert 'FM Executive Dashboard' not in exec_html
        assert 'No forecast yet' in exec_html
        assert 'method: sample' not in exec_html
        scan_html = client.get('/assets/scan', headers=admin_auth_headers).get_data(as_text=True)
        assert 'QR / asset lookup' not in scan_html
        assert 'tkt-topbar-title">QR scan</h1>' in scan_html
        twin_html = client.get('/assets/twin', headers=admin_auth_headers).get_data(as_text=True)
        assert '2D Digital Twin' not in twin_html
        assert 'tkt-topbar-title">Digital twin</h1>' in twin_html

    def test_dashboard_humanizes_status_type_and_plural(self, client, app, admin_auth_headers):
        from app.models import Asset
        with app.app_context():
            db.session.add(Asset(
                asset_id='AST-QA-1',
                name='QA Pump',
                asset_type='fire_pump',
                status='decommissioned',
                building='QA Tower',
            ))
            db.session.commit()
        res = client.get('/assets/', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'Fire pump' in html
        assert 'Decommissioned' in html
        assert 'fire_pump' not in html
        assert '>decommissioned<' not in html
        assert '1 asset' in html
        assert '1 assets' not in html

    def test_detail_back_to_list_no_breadcrumb(self, client, app, admin_auth_headers):
        from app.models import Asset
        with app.app_context():
            db.session.add(Asset(
                asset_id='AST-QA-2',
                name='QA Handler',
                asset_type='package_unit',
                status='active',
            ))
            db.session.commit()
        res = client.get('/assets/AST-QA-2', headers=admin_auth_headers)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'tkt-topbar-title">AST-QA-2</h1>' in html
        assert 'QA Handler' in html
        assert 'Package unit' in html
        assert 'fm-eyebrow' not in html
        assert 'href="/assets/list"' in html
        assert '>Active</span>' in html


def test_dashboard_day_series_length(app):
    from module_assets.routes import dashboard_day_series
    with app.app_context():
        pack = dashboard_day_series(30)
        assert pack['days'] == 30
        assert len(pack['labels']) == 30
        assert len(pack['iso']) == 30
        assert len(pack['work_orders']) == 30
        assert len(pack['assets']) == 30
        pack7 = dashboard_day_series(7)
        assert pack7['days'] == 7
        assert len(pack7['labels']) == 7


def test_assets_xlsx_export(client, app, admin_auth_headers):
    from app.models import Asset
    with app.app_context():
        db.session.add(Asset(
            asset_id='AST-XLS-1',
            name='Export Pump',
            asset_type='fire_pump',
            status='active',
            building='Export Tower',
        ))
        db.session.commit()
    res = client.get('/assets/api/assets.xlsx', headers=admin_auth_headers)
    assert res.status_code == 200
    assert 'spreadsheetml' in (res.content_type or '')
    assert res.data[:2] == b'PK'


