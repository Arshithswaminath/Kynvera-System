"""Device Management module — FM-style pages and inventory APIs."""
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.models import db, Device, TicketProperty

ROOT = Path(__file__).resolve().parents[1]


def _create_device(app, **kwargs):
    defaults = {
        'device_id': kwargs.pop('device_id', 'DEV-4242'),
        'name': 'Ops Desktop',
        'device_type': 'Desktop',
        'os': 'Windows 11',
        'status': 'offline',
        'health': 40,
        'serial_or_asset_tag': 'AST-9',
        'last_active_at': datetime.now(timezone.utc).replace(tzinfo=None),
    }
    defaults.update(kwargs)
    device = Device(**defaults)
    db.session.add(device)
    db.session.commit()
    return device


def test_device_pages_require_admin(client, admin_auth_headers, auth_headers):
    denied = client.get('/admin/devices/', headers=auth_headers)
    assert denied.status_code in (302, 401, 403)
    for path in (
        '/admin/devices/',
        '/admin/devices/all',
        '/admin/devices/analytics',
        '/admin/devices/map',
        '/admin/devices/compliance',
        '/admin/devices/audit',
        '/admin/devices/new',
    ):
        res = client.get(path, headers=admin_auth_headers)
        assert res.status_code == 200, path
        html = res.get_data(as_text=True)
        assert 'fm-assets-shell' in html
        assert 'Device Management' in html
        assert 'tkt-menu-toggle' in html
        assert 'coming soon' not in html.lower()


def test_dashboard_and_analytics_look_like_fm_executive(client, admin_auth_headers):
    dash = client.get('/admin/devices/', headers=admin_auth_headers).get_data(as_text=True)
    assert 'tkt-topbar-title">Dashboard</h1>' in dash
    assert 'id="enrollBtn"' in dash
    assert 'id="enrollModal"' in dash
    assert 'dm-ov-canvas' in dash
    assert 'Enrolled this month' in dash
    assert 'dm-ov-range' in dash
    assert '?range=month' in dash
    assert '?range=all' in dash
    assert 'data-dm-live-root' in dash
    assert 'data-dm-range-link="month"' in dash
    assert 'Week 1' in dash
    assert '>Mon<' in dash
    assert '2pm' not in dash
    month = client.get('/admin/devices/?range=month', headers=admin_auth_headers).get_data(as_text=True)
    assert 'Enrolled this year' in month
    assert 'data-dm-period="month"' in month
    assert 'data-dm-range-link="month"' in month
    assert '>Jan<' in month
    assert '>Dec<' in month
    assert 'data-dm-cols="12"' in month
    assert 'Week 1' in month
    assert '2pm' not in month
    all_time = client.get('/admin/devices/?range=all', headers=admin_auth_headers).get_data(as_text=True)
    assert 'Yearly' in all_time
    assert 'Enrolled this week' not in all_time
    assert 'Enrolled this month' not in all_time
    assert 'data-dm-range-link="all"' in all_time
    assert 'data-dm-period="all"' in all_time
    assert 'data-dm-cols="12"' in all_time
    assert '>Jan<' in all_time
    assert '>Dec<' in all_time
    assert 'Week 1' in all_time
    assert 'Week 4' in all_time
    assert '2pm' not in all_time
    assert 'Online now' in dash
    assert 'id="dmOvSearch"' in dash
    assert 'Overview' in dash
    assert 'Fleet mix' in dash
    assert 'Follow-ups' in dash
    assert 'Work activity' in dash
    assert 'Device inventory' in dash
    assert 'data-dm-tip="' in dash
    assert 'How many devices are in inventory right now' in dash
    assert 'How many devices were added in the selected' in dash
    assert 'Average inventory health score' in dash
    assert 'devices last seen.' in dash
    assert 'One month, split into four weeks.' not in dash
    assert 'When devices were enrolled across this range.' not in dash

    analytics = client.get('/admin/devices/analytics?range=month', headers=admin_auth_headers).get_data(as_text=True)
    assert 'Fleet health' in analytics
    assert 'fm-kpi-grid' in analytics
    assert 'By building' in analytics or 'No activity' in analytics
    assert 'Fleet narrative' in analytics
    assert 'Enrolled this year' in analytics
    assert 'data-dm-period="month"' in analytics
    assert 'Last seen in range' in analytics


def test_device_crud_patch_and_audit(client, app, admin_auth_headers, admin_user):
    create = client.post(
        '/api/admin/devices',
        headers=admin_auth_headers,
        json={
            'name': 'Facilities Laptop — Ahmed',
            'device_type': 'Laptop',
            'os': 'macOS',
            'building': 'Tower A',
            'serial_or_asset_tag': 'DEV-S001',
        },
    )
    assert create.status_code == 201
    body = create.get_json()
    device = body.get('device') or {}
    assert device['name'] == 'Facilities Laptop — Ahmed'
    assert device['building'] == 'Tower A'
    pk = device['id']

    listed = client.get('/api/admin/devices', headers=admin_auth_headers)
    assert listed.status_code == 200
    assert listed.get_json()['count'] >= 1

    patched = client.patch(
        f'/api/admin/devices/{pk}',
        headers=admin_auth_headers,
        json={'status': 'online', 'health': 91, 'latitude': 25.2048, 'longitude': 55.2708},
    )
    assert patched.status_code == 200
    updated = patched.get_json()['device']
    assert updated['status'] == 'online'
    assert updated['health'] == 91
    assert updated['latitude'] == 25.2048

    points = client.get('/api/admin/devices/map-points', headers=admin_auth_headers)
    assert points.status_code == 200
    assert points.get_json()['count'] >= 1

    kpis = client.get('/api/admin/devices/kpis', headers=admin_auth_headers)
    assert kpis.status_code == 200
    payload = kpis.get_json()['kpis']
    assert payload['total'] >= 1
    assert 'fleet_health_pct' in payload

    overview = client.get('/api/admin/devices/overview?range=month', headers=admin_auth_headers)
    assert overview.status_code == 200
    ov = overview.get_json()['overview']
    assert ov['period'] == 'month'
    assert ov['day_labels'] == ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    assert ov['bucket_count'] == 12
    assert [row['label'] for row in ov['heat_rows']] == ['Week 1', 'Week 2', 'Week 3', 'Week 4']
    assert ov['heat_nav']['mode'] == 'year'
    assert 'Darker squares' in ov['heat_tip']

    week = client.get('/api/admin/devices/overview?range=week', headers=admin_auth_headers)
    assert week.status_code == 200
    week_ov = week.get_json()['overview']
    assert week_ov['period'] == 'week'
    assert week_ov['day_labels'] == ['Week 1', 'Week 2', 'Week 3', 'Week 4']
    assert week_ov['bucket_count'] == 4
    assert [row['label'] for row in week_ov['heat_rows']] == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    assert week_ov['heat_nav']['mode'] == 'month'

    jan = client.get('/api/admin/devices/overview?range=week&year=2026&month=1', headers=admin_auth_headers)
    assert jan.status_code == 200
    jan_ov = jan.get_json()['overview']
    assert jan_ov['heat_nav']['month'] == 1
    assert jan_ov['heat_nav']['year'] == 2026

    yearly = client.get('/api/admin/devices/overview?range=all', headers=admin_auth_headers)
    assert yearly.status_code == 200
    year_ov = yearly.get_json()['overview']
    assert year_ov['period'] == 'all'
    assert year_ov['period_label'] == 'Yearly'
    assert year_ov['bucket_count'] == 12
    assert year_ov['day_labels'][0] == 'Jan'
    assert year_ov['day_labels'][-1] == 'Dec'
    assert [row['label'] for row in year_ov['heat_rows']] == ['Week 1', 'Week 2', 'Week 3', 'Week 4']

    compliance = client.get('/api/admin/devices/compliance', headers=admin_auth_headers)
    assert compliance.status_code == 200
    assert 'checks' in compliance.get_json()

    narrative = client.get('/api/admin/devices/narrative', headers=admin_auth_headers)
    assert narrative.status_code == 200
    assert 'narrative' in narrative.get_json()

    audit = client.get('/api/admin/devices/audit', headers=admin_auth_headers)
    assert audit.status_code == 200
    actions = {row['action'] for row in audit.get_json()['logs']}
    assert 'device_enroll' in actions
    assert 'device_update' in actions

    detail = client.get(f'/admin/devices/{pk}', headers=admin_auth_headers)
    assert detail.status_code == 200
    assert 'Facilities Laptop' in detail.get_data(as_text=True)

    removed = client.delete(f'/api/admin/devices/{pk}', headers=admin_auth_headers)
    assert removed.status_code == 200
    missing = client.get(f'/api/admin/devices/{pk}', headers=admin_auth_headers)
    assert missing.status_code == 404


def test_map_points_inherit_building_coordinates(client, app, admin_auth_headers):
    with app.app_context():
        prop = TicketProperty(
            name='Device Lab North',
            is_active=True,
            latitude=25.21,
            longitude=55.28,
        )
        db.session.add(prop)
        db.session.commit()
        _create_device(
            app,
            device_id='DEV-TOWER',
            name='Site Tablet — Lab North',
            building='Device Lab North',
            latitude=None,
            longitude=None,
            health=88,
            status='idle',
        )

    res = client.get('/api/admin/devices/map-points', headers=admin_auth_headers)
    assert res.status_code == 200
    points = res.get_json()['points']
    match = next(p for p in points if p['device_id'] == 'DEV-TOWER')
    assert match['latitude'] == 25.21
    assert match['longitude'] == 55.28
    assert match['coord_source'] == 'property'


def test_compliance_buckets_and_stale(client, app, admin_auth_headers):
    with app.app_context():
        stale_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=21)
        _create_device(
            app,
            device_id='DEV-STALE',
            name='Old Laptop',
            status='offline',
            health=30,
            assigned_user_id=None,
            serial_or_asset_tag=None,
            last_active_at=stale_at,
        )
    res = client.get('/api/admin/devices/compliance', headers=admin_auth_headers)
    data = res.get_json()
    by_id = {c['id']: c for c in data['checks']}
    assert by_id['critical']['count'] >= 1
    assert by_id['stale']['count'] >= 1
    assert by_id['unassigned']['count'] >= 1
    assert by_id['missing_serial']['count'] >= 1
    assert by_id['offline']['count'] >= 1


def test_list_filter_query(client, app, admin_auth_headers):
    with app.app_context():
        _create_device(app, device_id='DEV-FILT', name='Ops Desktop', status='offline', device_type='Desktop')
    res = client.get('/api/admin/devices?status=offline&q=Ops', headers=admin_auth_headers)
    assert res.status_code == 200
    names = [d['name'] for d in res.get_json()['devices']]
    assert 'Ops Desktop' in names


def test_overview_counts_weekly_enrolls(client, app, admin_auth_headers):
    with app.app_context():
        _create_device(
            app,
            device_id='DEV-WEEK',
            name='New Tablet',
            status='online',
            health=90,
            last_active_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    html = client.get('/admin/devices/', headers=admin_auth_headers).get_data(as_text=True)
    assert 'Enrolled this month' in html
    assert 'dm-ov-hero' in html
    assert 'Online now' in html


def test_range_filters_update_in_place_without_reload():
    js = (ROOT / 'static' / 'js' / 'dm-devices.js').read_text()
    assert 'e.preventDefault()' in js
    assert 'history.pushState' in js
    assert 'function applyRange' in js
    assert '/api/admin/devices/overview' in js
    assert 'function bindTips' in js
    assert 'data-dm-tip' in js
    assert 'dm-float-tip' in js
    css = (ROOT / 'static' / 'css' / 'dm-devices.css').read_text()
    assert 'left: calc(100% / var(--dm-cols, 7) / 2)' in css
    assert 'transform: translateX(-50%)' in css
