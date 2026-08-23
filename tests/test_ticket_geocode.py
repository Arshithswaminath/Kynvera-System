"""New Work Order site-path geocode API."""
from unittest.mock import Mock, patch

import pytest

from module_ticketing import routes as tkt_routes


@pytest.fixture(autouse=True)
def _clear_geocode_cache():
    tkt_routes._SITE_GEOCODE_CACHE.clear()
    yield
    tkt_routes._SITE_GEOCODE_CACHE.clear()


class TestTicketGeocode:
    def test_requires_auth(self, client):
        response = client.get('/tickets/api/geocode?q=Ajman')
        assert response.status_code in (401, 422)

    def test_rejects_short_query(self, client, admin_auth_headers):
        response = client.get('/tickets/api/geocode?q=ab', headers=admin_auth_headers)
        assert response.status_code == 400
        assert response.get_json()['success'] is False

    def test_returns_nominatim_hit(self, client, admin_auth_headers):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{'lat': '25.4052', 'lon': '55.5136'}]
        with patch.object(tkt_routes.requests, 'get', return_value=mock_resp) as mocked:
            response = client.get(
                '/tickets/api/geocode?q=A%26F%20Building,%20Ajman',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['lat'] == 25.4052
        assert data['lng'] == 55.5136
        mocked.assert_called_once()

    def test_caches_repeat_queries(self, client, admin_auth_headers):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{'lat': '25.4', 'lon': '55.5'}]
        with patch.object(tkt_routes.requests, 'get', return_value=mock_resp) as mocked:
            first = client.get('/tickets/api/geocode?q=Ajman%20UAE', headers=admin_auth_headers)
            second = client.get('/tickets/api/geocode?q=Ajman%20UAE', headers=admin_auth_headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert mocked.call_count == 1

    def test_not_found(self, client, admin_auth_headers):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = []
        with patch.object(tkt_routes.requests, 'get', return_value=mock_resp):
            response = client.get('/tickets/api/geocode?q=Unknown%20Site', headers=admin_auth_headers)
        assert response.status_code == 404
        assert response.get_json()['success'] is False

    def test_saves_pin_on_property(self, client, admin_auth_headers, app):
        from app.models import db, TicketProperty
        with app.app_context():
            prop = TicketProperty(name='A&F Building', is_active=True)
            db.session.add(prop)
            db.session.commit()
            pid = prop.id
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{'lat': '25.4052', 'lon': '55.5136'}]
        with patch.object(tkt_routes.requests, 'get', return_value=mock_resp):
            response = client.get(
                f'/tickets/api/geocode?q=A%26F%20Building,%20Ajman&property_id={pid}',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['saved'] is True
        with app.app_context():
            saved = db.session.get(TicketProperty, pid)
            assert saved.latitude == 25.4052
            assert saved.longitude == 55.5136

    def test_saves_pin_on_base_unit(self, client, admin_auth_headers, app):
        from app.models import db, TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit
        with app.app_context():
            prop = TicketProperty(name='Pin Tower', is_active=True)
            db.session.add(prop)
            db.session.flush()
            zone = TicketZone(name='Podium', property_id=prop.id, is_active=True)
            db.session.add(zone)
            db.session.flush()
            sz = TicketSubZone(name='West Wing', zone_id=zone.id, is_active=True)
            db.session.add(sz)
            db.session.flush()
            unit = TicketBaseUnit(name='Apt 12', sub_zone_id=sz.id, is_active=True)
            db.session.add(unit)
            db.session.commit()
            uid = unit.id
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{'lat': '25.4111', 'lon': '55.5222'}]
        with patch.object(tkt_routes.requests, 'get', return_value=mock_resp):
            response = client.get(
                f'/tickets/api/geocode?q=Apt%2012,%20Ajman&base_unit_id={uid}',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200
        data = response.get_json()
        assert data['saved'] is True
        assert data['lat'] == 25.4111
        with app.app_context():
            saved = db.session.get(TicketBaseUnit, uid)
            assert saved.latitude == 25.4111
            assert saved.longitude == 55.5222

    def test_patch_base_unit_coords(self, client, admin_auth_headers, app):
        from app.models import db, TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit
        with app.app_context():
            prop = TicketProperty(name='Coord Tower', is_active=True)
            db.session.add(prop)
            db.session.flush()
            zone = TicketZone(name='Zone C', property_id=prop.id, is_active=True)
            db.session.add(zone)
            db.session.flush()
            sz = TicketSubZone(name='Sub C', zone_id=zone.id, is_active=True)
            db.session.add(sz)
            db.session.flush()
            unit = TicketBaseUnit(name='Office 3', sub_zone_id=sz.id, is_active=True)
            db.session.add(unit)
            db.session.commit()
            uid = unit.id
        res = client.patch(
            f'/tickets/api/settings/base-units/{uid}',
            headers=admin_auth_headers,
            json={'latitude': 25.4, 'longitude': 55.5},
        )
        assert res.status_code == 200
        body = res.get_json()['base_unit']
        assert body['latitude'] == 25.4
        assert body['longitude'] == 55.5


class TestTicketLocationMapPayload:
    def test_includes_site_path_fields(self, app, admin_user):
        from app.models import db, Ticket
        with app.app_context():
            t = Ticket(
                ticket_id='TKT-LOC-PAY',
                reporter_id=admin_user.id,
                title='Map payload',
                project='Ajman Mall',
                service_group='HVAC',
                category='AC',
                fault_type='Filter',
                priority='medium',
                work_description='Clean',
                status='open',
                property_name='Retail Podium',
                zone='Ground Level',
                sub_zone='Back of House',
                base_unit='Staff Canteen',
            )
            db.session.add(t)
            db.session.commit()
            payload = tkt_routes._ticket_location_map_payload(t)
            assert payload['ticket_id'] == 'TKT-LOC-PAY'
            assert payload['project'] == 'Ajman Mall'
            assert payload['property_name'] == 'Retail Podium'
            assert payload['zone'] == 'Ground Level'
            assert payload['sub_zone'] == 'Back of House'
            assert payload['base_unit'] == 'Staff Canteen'
            assert payload['label'] == 'Retail Podium / Ground Level / Back of House / Staff Canteen'
            db.session.delete(t)
            db.session.commit()
