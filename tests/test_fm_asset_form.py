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
    assert 'GIS — Asset map' in html
