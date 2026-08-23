"""Integration tests for module_procurement/routes.py (blueprint mounted at /procurement).

Covers: page routes, materials CRUD, recent activity, Excel import/export,
properties, property-materials, material-property assignment, catalog
materials CRUD, and registered properties.

Access rule exercised throughout: every route (except GET
/procurement/api/catalog/materials) requires `user.role == 'admin'` or
`user.access_procurement_module` truthy, else 403. The catalog GET route is
intentionally open to any authenticated user (inspection-form consumers).
"""
from io import BytesIO

import openpyxl
import pytest

from tests.factories import make_user


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_procurement_submissions(app):
    """Procurement data lives in the shared, session-scoped Submission table
    (see conftest.py's session-scoped `app` fixture — the in-memory DB is
    never reset between tests). Isolate each test in this file by clearing
    out procurement-related rows before it runs; this does not touch
    submissions belonging to other modules/test files."""
    with app.app_context():
        from app.models import db, Submission
        Submission.query.filter(Submission.module_type.in_(
            ['procurement_material', 'procurement_property', 'catalog_material']
        )).delete(synchronize_session=False)
        db.session.commit()
    yield


# A "procurement-enabled" standard user, distinct from the plain
# `standard_user`/`auth_headers` fixtures in conftest.py which do NOT have
# access_procurement_module set.
# ---------------------------------------------------------------------------

@pytest.fixture
def procurement_user(app):
    """A non-admin user with explicit access_procurement_module=True."""
    with app.app_context():
        user, password = make_user(
            username='proc_user',
            access_procurement_module=True,
        )
        user_id = user.id
        yield {'id': user_id, 'username': 'proc_user', 'password': password}
        from app.models import db, User
        u = db.session.get(User, user_id)
        if u:
            db.session.delete(u)
            db.session.commit()


@pytest.fixture
def procurement_auth_headers(client, procurement_user):
    response = client.post('/api/auth/login', json={
        'username': procurement_user['username'],
        'password': procurement_user['password'],
    })
    token = response.get_json().get('access_token')
    return {'Authorization': f'Bearer {token}'}


def make_material(client, headers, **overrides):
    """Create a procurement material via the API and return its submission_id."""
    payload = {'material_name': 'Widget'}
    payload.update(overrides)
    resp = client.post('/procurement/api/materials', headers=headers, json=payload)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['submission_id']


def make_xlsx_bytes(rows, headers=None):
    """Build an in-memory .xlsx file. `rows` is a list of lists (data rows)."""
    if headers is None:
        headers = ['Material Name', 'Category', 'Description', 'Unit',
                    'Quantity', 'Unit Price', 'Supplier', 'Notes']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Materials'
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

class TestProcurementPages:
    def test_dashboard_requires_auth(self, client):
        response = client.get('/procurement/')
        # Page routes are HTML navigations: unauthenticated GETs are silently
        # redirected to /login (302), not a JSON 401/422 like API routes.
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')

    def test_dashboard_admin_ok(self, client, admin_auth_headers):
        response = client.get('/procurement/', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_dashboard_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/', headers=auth_headers)
        assert response.status_code == 403
        assert response.get_json()['error'] == 'Access denied to Procurement module'

    def test_dashboard_allowed_with_module_access(self, client, procurement_auth_headers):
        response = client.get('/procurement/', headers=procurement_auth_headers)
        assert response.status_code == 200

    def test_materials_page_admin_ok(self, client, admin_auth_headers):
        response = client.get('/procurement/materials', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_materials_page_denied(self, client, auth_headers):
        response = client.get('/procurement/materials', headers=auth_headers)
        assert response.status_code == 403

    def test_add_material_page_admin_ok(self, client, admin_auth_headers):
        response = client.get('/procurement/add-material', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_properties_page_admin_ok(self, client, admin_auth_headers):
        response = client.get('/procurement/properties', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_property_detail_page_admin_ok(self, client, admin_auth_headers):
        response = client.get('/procurement/property/Tower%20A', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_catalog_department_valid_admin_ok(self, client, admin_auth_headers):
        response = client.get('/procurement/catalog/HVAC', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_catalog_department_invalid_500s(self, client, admin_auth_headers):
        """BUG: module_procurement/routes.py:653 calls redirect('/procurement/')
        for an unrecognized department, but `redirect` is never imported in
        this module (only render_template/request/jsonify/current_app/send_file
        are imported from flask). This raises a NameError, which the app's
        generic error handling turns into a 500 instead of a redirect."""
        response = client.get('/procurement/catalog/NotADepartment', headers=admin_auth_headers)
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET/POST /procurement/api/materials
# ---------------------------------------------------------------------------

class TestMaterialsApi:
    def test_requires_auth(self, client):
        response = client.get('/procurement/api/materials')
        assert response.status_code in (401, 422)

    def test_denied_without_module_access(self, client, auth_headers):
        response = client.get('/procurement/api/materials', headers=auth_headers)
        assert response.status_code == 403

    def test_get_empty_list(self, client, admin_auth_headers):
        response = client.get('/procurement/api/materials', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['materials'] == []
        assert data['total'] == 0

    def test_add_material_success(self, client, admin_auth_headers):
        response = client.post('/procurement/api/materials', headers=admin_auth_headers, json={
            'material_name': 'Office Chair',
            'property': 'Tower A',
            'category': 'Furniture',
            'quantity': 3,
            'unit_price': 150.0,
        })
        # Route returns plain jsonify() with no explicit status -> default 200
        # (not 201, despite this being a resource-creation endpoint).
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['submission_id'].startswith('PROC-MAT-')
        assert 'message' in data

        listed = client.get('/procurement/api/materials', headers=admin_auth_headers)
        materials = listed.get_json()['materials']
        assert len(materials) == 1
        m = materials[0]
        assert m['material_name'] == 'Office Chair'
        assert m['property'] == 'Tower A'
        assert m['quantity'] == 3
        assert m['unit_price'] == 150.0
        assert m['total_price'] == 450.0
        assert m['id'] == data['submission_id']

    def test_add_material_missing_name(self, client, admin_auth_headers):
        response = client.post('/procurement/api/materials', headers=admin_auth_headers, json={})
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Material name is required'

    def test_add_material_denied_without_access(self, client, auth_headers):
        response = client.post('/procurement/api/materials', headers=auth_headers, json={
            'material_name': 'Widget',
        })
        assert response.status_code == 403

    def test_add_material_allowed_with_module_access(self, client, procurement_auth_headers):
        response = client.post('/procurement/api/materials', headers=procurement_auth_headers, json={
            'material_name': 'Cable Reel',
        })
        assert response.status_code == 200
        assert response.get_json()['success'] is True

    def test_add_material_requires_auth(self, client):
        response = client.post('/procurement/api/materials', json={'material_name': 'X'})
        assert response.status_code in (401, 422)


# ---------------------------------------------------------------------------
# GET /procurement/api/recent-activity
# ---------------------------------------------------------------------------

class TestRecentActivity:
    def test_requires_auth(self, client):
        response = client.get('/procurement/api/recent-activity')
        assert response.status_code in (401, 422)

    def test_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/api/recent-activity', headers=auth_headers)
        assert response.status_code == 403

    def test_empty_activity(self, client, admin_auth_headers):
        response = client.get('/procurement/api/recent-activity', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['activities'] == []

    def test_lists_recent_materials(self, client, admin_auth_headers):
        make_material(client, admin_auth_headers, material_name='Ladder')
        response = client.get('/procurement/api/recent-activity', headers=admin_auth_headers)
        assert response.status_code == 200
        activities = response.get_json()['activities']
        assert len(activities) == 1
        assert activities[0]['material_name'] == 'Ladder'
        assert 'submitted_by' in activities[0]
        assert 'created_at' in activities[0]

    def test_limit_param_is_respected(self, client, admin_auth_headers):
        for i in range(5):
            make_material(client, admin_auth_headers, material_name=f'Item {i}')
        response = client.get('/procurement/api/recent-activity?limit=2', headers=admin_auth_headers)
        assert response.status_code == 200
        assert len(response.get_json()['activities']) == 2


# ---------------------------------------------------------------------------
# DELETE /procurement/api/materials/<material_id>
# ---------------------------------------------------------------------------

class TestDeleteMaterial:
    def test_requires_auth(self, client):
        response = client.delete('/procurement/api/materials/PROC-MAT-DOESNOTEXIST')
        assert response.status_code in (401, 422)

    def test_denied_without_access(self, client, auth_headers):
        response = client.delete('/procurement/api/materials/PROC-MAT-DOESNOTEXIST', headers=auth_headers)
        assert response.status_code == 403

    def test_delete_unknown_id_404(self, client, admin_auth_headers):
        response = client.delete('/procurement/api/materials/PROC-MAT-DOESNOTEXIST', headers=admin_auth_headers)
        assert response.status_code == 404
        assert response.get_json()['error'] == 'Material not found'

    def test_delete_success(self, client, admin_auth_headers):
        material_id = make_material(client, admin_auth_headers, material_name='Drill')
        response = client.delete(f'/procurement/api/materials/{material_id}', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        listed = client.get('/procurement/api/materials', headers=admin_auth_headers)
        assert listed.get_json()['total'] == 0


# ---------------------------------------------------------------------------
# POST /procurement/api/import-excel
# ---------------------------------------------------------------------------

class TestImportExcel:
    def test_requires_auth(self, client):
        buf = make_xlsx_bytes([['Widget', 'General', '', 'pcs', 1, 1, '', '']])
        response = client.post(
            '/procurement/api/import-excel',
            data={'file': (buf, 'materials.xlsx')},
            content_type='multipart/form-data',
        )
        assert response.status_code in (401, 422)

    def test_denied_without_access(self, client, auth_headers):
        buf = make_xlsx_bytes([['Widget', 'General', '', 'pcs', 1, 1, '', '']])
        response = client.post(
            '/procurement/api/import-excel',
            headers=auth_headers,
            data={'file': (buf, 'materials.xlsx')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 403

    def test_no_file_provided(self, client, admin_auth_headers):
        response = client.post(
            '/procurement/api/import-excel',
            headers=admin_auth_headers,
            data={},
            content_type='multipart/form-data',
        )
        assert response.status_code == 400
        assert response.get_json()['error'] == 'No file provided'

    def test_non_excel_file_rejected(self, client, admin_auth_headers):
        response = client.post(
            '/procurement/api/import-excel',
            headers=admin_auth_headers,
            data={'file': (BytesIO(b'not an excel file'), 'materials.txt')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 400
        assert 'Invalid file format' in response.get_json()['error']

    def test_import_valid_xlsx(self, client, admin_auth_headers):
        buf = make_xlsx_bytes([
            ['Office Paper A4 Ream', 'Stationery', '500 sheets', 'ream', 50, 12.5, 'Gulf Paper Co', 'Monthly'],
            ['Printer Toner', 'IT Supplies', 'Laser', 'pcs', 10, 85.0, 'Tech Supplies', ''],
        ])
        response = client.post(
            '/procurement/api/import-excel',
            headers=admin_auth_headers,
            data={'file': (buf, 'materials.xlsx')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['imported'] == 2
        assert data['total_rows'] == 2
        assert data['errors'] == []

        listed = client.get('/procurement/api/materials', headers=admin_auth_headers)
        materials = listed.get_json()['materials']
        assert len(materials) == 2
        names = {m['material_name'] for m in materials}
        assert names == {'Office Paper A4 Ream', 'Printer Toner'}
        assert all(m.get('imported_from_excel') is True for m in materials)

    def test_import_missing_material_name_column_400(self, client, admin_auth_headers):
        buf = make_xlsx_bytes(
            [['foo', 1]],
            headers=['Some Other Column', 'Quantity'],
        )
        response = client.post(
            '/procurement/api/import-excel',
            headers=admin_auth_headers,
            data={'file': (buf, 'materials.xlsx')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 400
        assert 'Material Name' in response.get_json()['error']

    def test_import_recognizes_alternate_column_names(self, client, admin_auth_headers):
        """The route lower-cases + maps common header variants (e.g. 'Item' -> material_name)."""
        buf = make_xlsx_bytes(
            [['Cordless Drill', 3, 99.99]],
            headers=['Item', 'Qty', 'Price'],
        )
        response = client.post(
            '/procurement/api/import-excel',
            headers=admin_auth_headers,
            data={'file': (buf, 'materials.xlsx')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['imported'] == 1

        listed = client.get('/procurement/api/materials', headers=admin_auth_headers)
        materials = listed.get_json()['materials']
        assert materials[0]['material_name'] == 'Cordless Drill'
        assert materials[0]['quantity'] == 3
        assert materials[0]['unit_price'] == 99.99


# ---------------------------------------------------------------------------
# GET /procurement/api/sample-excel and /procurement/api/export-excel
# ---------------------------------------------------------------------------

class TestSampleAndExportExcel:
    def test_sample_excel_requires_auth(self, client):
        response = client.get('/procurement/api/sample-excel')
        assert response.status_code in (401, 422)

    def test_sample_excel_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/api/sample-excel', headers=auth_headers)
        assert response.status_code == 403

    def test_sample_excel_download(self, client, admin_auth_headers):
        response = client.get('/procurement/api/sample-excel', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.headers['Content-Type'] == (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        assert response.data[:2] == b'PK'
        assert len(response.data) > 0

    def test_export_excel_requires_auth(self, client):
        response = client.get('/procurement/api/export-excel')
        assert response.status_code in (401, 422)

    def test_export_excel_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/api/export-excel', headers=auth_headers)
        assert response.status_code == 403

    def test_export_excel_empty(self, client, admin_auth_headers):
        response = client.get('/procurement/api/export-excel', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.headers['Content-Type'] == (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        assert response.data[:2] == b'PK'
        assert len(response.data) > 0

    def test_export_excel_with_property_filter(self, client, admin_auth_headers):
        make_material(client, admin_auth_headers, material_name='Filtered Item', property='Tower A')
        make_material(client, admin_auth_headers, material_name='Other Item', property='Tower B')
        response = client.get(
            '/procurement/api/export-excel?property=Tower%20A',
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert 'Tower_A' in response.headers.get('Content-Disposition', '')


# ---------------------------------------------------------------------------
# GET/POST /procurement/api/properties
# ---------------------------------------------------------------------------

class TestPropertiesApi:
    def test_get_requires_auth(self, client):
        response = client.get('/procurement/api/properties')
        assert response.status_code in (401, 422)

    def test_get_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/api/properties', headers=auth_headers)
        assert response.status_code == 403

    def test_get_empty(self, client, admin_auth_headers):
        response = client.get('/procurement/api/properties', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['properties'] == []

    def test_post_requires_name(self, client, admin_auth_headers):
        response = client.post('/procurement/api/properties', headers=admin_auth_headers, json={})
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Property name is required'

    def test_post_blank_name_rejected(self, client, admin_auth_headers):
        response = client.post('/procurement/api/properties', headers=admin_auth_headers, json={'name': '   '})
        assert response.status_code == 400

    def test_post_creates_property(self, client, admin_auth_headers):
        response = client.post('/procurement/api/properties', headers=admin_auth_headers, json={
            'name': 'Marina Heights',
            'address': '123 Marina St',
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'Marina Heights' in data['message']

    def test_post_denied_without_access(self, client, auth_headers):
        response = client.post('/procurement/api/properties', headers=auth_headers, json={'name': 'X'})
        assert response.status_code == 403

    def test_properties_aggregate_material_counts(self, client, admin_auth_headers):
        make_material(client, admin_auth_headers, material_name='A', property='Tower C', quantity=2, unit_price=10)
        make_material(client, admin_auth_headers, material_name='B', property='Tower C', quantity=1, unit_price=5)
        response = client.get('/procurement/api/properties', headers=admin_auth_headers)
        assert response.status_code == 200
        props = {p['name']: p for p in response.get_json()['properties']}
        assert props['Tower C']['materials_count'] == 2
        assert props['Tower C']['total_quantity'] == 3
        assert props['Tower C']['total_value'] == 25.0


# ---------------------------------------------------------------------------
# GET /procurement/api/property-materials/<property_name>
# ---------------------------------------------------------------------------

class TestPropertyMaterials:
    def test_requires_auth(self, client):
        response = client.get('/procurement/api/property-materials/Tower%20A')
        assert response.status_code in (401, 422)

    def test_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/api/property-materials/Tower%20A', headers=auth_headers)
        assert response.status_code == 403

    def test_empty_for_unknown_property(self, client, admin_auth_headers):
        response = client.get('/procurement/api/property-materials/Nowhere', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['property'] == 'Nowhere'
        assert data['materials'] == []
        assert data['total'] == 0

    def test_filters_by_property(self, client, admin_auth_headers):
        make_material(client, admin_auth_headers, material_name='In Tower D', property='Tower D')
        make_material(client, admin_auth_headers, material_name='In Tower E', property='Tower E')
        response = client.get('/procurement/api/property-materials/Tower%20D', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 1
        assert data['materials'][0]['material_name'] == 'In Tower D'


# ---------------------------------------------------------------------------
# POST /procurement/api/material-assign-property
# ---------------------------------------------------------------------------

class TestMaterialAssignProperty:
    def test_requires_auth(self, client):
        response = client.post('/procurement/api/material-assign-property', json={})
        assert response.status_code in (401, 422)

    def test_denied_without_access(self, client, auth_headers):
        response = client.post('/procurement/api/material-assign-property', headers=auth_headers, json={
            'material_id': 'X', 'property': 'Y',
        })
        assert response.status_code == 403

    def test_missing_fields_400(self, client, admin_auth_headers):
        response = client.post('/procurement/api/material-assign-property', headers=admin_auth_headers, json={})
        assert response.status_code == 400
        assert 'required' in response.get_json()['error'].lower()

    def test_unknown_material_404(self, client, admin_auth_headers):
        response = client.post('/procurement/api/material-assign-property', headers=admin_auth_headers, json={
            'material_id': 'PROC-MAT-DOESNOTEXIST',
            'property': 'Tower F',
        })
        assert response.status_code == 404
        assert response.get_json()['error'] == 'Material not found'

    def test_assign_success(self, client, admin_auth_headers):
        material_id = make_material(client, admin_auth_headers, material_name='Unassigned Item')
        response = client.post('/procurement/api/material-assign-property', headers=admin_auth_headers, json={
            'material_id': material_id,
            'property': 'Tower F',
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'Tower F' in data['message']

        by_property = client.get('/procurement/api/property-materials/Tower%20F', headers=admin_auth_headers)
        materials = by_property.get_json()['materials']
        assert len(materials) == 1
        assert materials[0]['id'] == material_id
        assert materials[0]['property'] == 'Tower F'


# ---------------------------------------------------------------------------
# GET/POST /procurement/api/catalog/materials, PUT/DELETE .../<material_id>
# ---------------------------------------------------------------------------

class TestCatalogMaterials:
    def test_get_requires_auth(self, client):
        response = client.get('/procurement/api/catalog/materials')
        assert response.status_code in (401, 422)

    def test_get_open_to_any_authenticated_user(self, client, auth_headers):
        """Unlike every other route in this module, GET catalog/materials has
        no admin/access_procurement_module check — any authenticated user can
        read it (the route docstring says this is intentional, for inspection
        forms)."""
        response = client.get('/procurement/api/catalog/materials', headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['materials'] == {}
        assert data['departments'] == []
        assert data['total'] == 0

    def test_post_requires_auth(self, client):
        response = client.post('/procurement/api/catalog/materials', json={})
        assert response.status_code in (401, 422)

    def test_post_denied_without_access(self, client, auth_headers):
        response = client.post('/procurement/api/catalog/materials', headers=auth_headers, json={
            'department': 'HVAC', 'material_name': 'Compressor',
        })
        assert response.status_code == 403

    def test_post_invalid_department_400(self, client, admin_auth_headers):
        response = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'NotADept', 'material_name': 'X',
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Invalid department'

    def test_post_missing_material_name_400(self, client, admin_auth_headers):
        response = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'HVAC',
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Material name is required'

    def test_post_negative_price_400(self, client, admin_auth_headers):
        response = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'HVAC', 'material_name': 'Compressor', 'unit_price': -1,
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Unit price cannot be negative'

    def test_post_invalid_price_400(self, client, admin_auth_headers):
        response = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'HVAC', 'material_name': 'Compressor', 'unit_price': 'not-a-number',
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Invalid unit price'

    def test_post_creates_catalog_material(self, client, admin_auth_headers):
        response = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'HVAC',
            'material_name': 'Compressor 1.5 Ton',
            'brand': 'Daikin',
            'uom': 'PCS',
            'unit_price': 1200,
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['id'].startswith('CAT-MAT-')

        listed = client.get('/procurement/api/catalog/materials?department=HVAC', headers=admin_auth_headers)
        materials = listed.get_json()['materials']
        assert 'HVAC' in materials
        assert materials['HVAC'][0]['name'] == 'Compressor 1.5 Ton'
        assert materials['HVAC'][0]['brand'] == 'Daikin'
        assert materials['HVAC'][0]['unit_price'] == 1200

    def test_get_filters_by_query_string(self, client, admin_auth_headers):
        client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'Cleaning', 'material_name': 'Mop Bucket',
        })
        client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'Cleaning', 'material_name': 'Floor Cleaner',
        })
        response = client.get('/procurement/api/catalog/materials?q=mop', headers=admin_auth_headers)
        assert response.status_code == 200
        materials = response.get_json()['materials']
        names = [m['name'] for m in materials.get('Cleaning', [])]
        assert names == ['Mop Bucket']

    def test_put_unknown_id_404(self, client, admin_auth_headers):
        response = client.put('/procurement/api/catalog/materials/CAT-MAT-DOESNOTEXIST', headers=admin_auth_headers, json={
            'material_name': 'New Name',
        })
        assert response.status_code == 404
        assert response.get_json()['error'] == 'Catalog material not found'

    def test_put_requires_auth(self, client):
        response = client.put('/procurement/api/catalog/materials/CAT-MAT-X', json={})
        assert response.status_code in (401, 422)

    def test_put_updates_material(self, client, admin_auth_headers):
        created = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'Electrical', 'material_name': 'Old Name', 'unit_price': 10,
        })
        material_id = created.get_json()['id']

        response = client.put(f'/procurement/api/catalog/materials/{material_id}', headers=admin_auth_headers, json={
            'material_name': 'New Name',
            'brand': 'ABB',
            'uom': 'BOX',
            'unit_price': 25.5,
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['route_version'] == 2
        assert data['material']['id'] == material_id
        assert data['material']['name'] == 'New Name'
        assert data['material']['brand'] == 'ABB'
        assert data['material']['uom'] == 'BOX'
        assert data['material']['unit_price'] == 25.5

    def test_put_blank_name_rejected(self, client, admin_auth_headers):
        created = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'Plumbing', 'material_name': 'Valve', 'unit_price': 5,
        })
        material_id = created.get_json()['id']
        response = client.put(f'/procurement/api/catalog/materials/{material_id}', headers=admin_auth_headers, json={
            'material_name': '   ',
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Material name is required'

    def test_put_negative_price_rejected(self, client, admin_auth_headers):
        created = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'Plumbing', 'material_name': 'Valve', 'unit_price': 5,
        })
        material_id = created.get_json()['id']
        response = client.put(f'/procurement/api/catalog/materials/{material_id}', headers=admin_auth_headers, json={
            'unit_price': -10,
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Unit price cannot be negative'

    def test_put_invalid_department_rejected(self, client, admin_auth_headers):
        created = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'Plumbing', 'material_name': 'Valve', 'unit_price': 5,
        })
        material_id = created.get_json()['id']
        response = client.put(f'/procurement/api/catalog/materials/{material_id}', headers=admin_auth_headers, json={
            'department': 'NotADept',
        })
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Invalid department'

    def test_delete_unknown_id_404(self, client, admin_auth_headers):
        response = client.delete('/procurement/api/catalog/materials/CAT-MAT-DOESNOTEXIST', headers=admin_auth_headers)
        assert response.status_code == 404
        assert response.get_json()['error'] == 'Catalog material not found'

    def test_delete_requires_auth(self, client):
        response = client.delete('/procurement/api/catalog/materials/CAT-MAT-X')
        assert response.status_code in (401, 422)

    def test_delete_denied_without_access(self, client, auth_headers):
        response = client.delete('/procurement/api/catalog/materials/CAT-MAT-X', headers=auth_headers)
        assert response.status_code == 403

    def test_delete_success(self, client, admin_auth_headers):
        created = client.post('/procurement/api/catalog/materials', headers=admin_auth_headers, json={
            'department': 'HVAC', 'material_name': 'Filter', 'unit_price': 3,
        })
        material_id = created.get_json()['id']
        response = client.delete(f'/procurement/api/catalog/materials/{material_id}', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        listed = client.get('/procurement/api/catalog/materials?department=HVAC', headers=admin_auth_headers)
        materials = listed.get_json()['materials']
        assert materials.get('HVAC', []) == []

    def test_delete_does_not_remove_regular_material_with_same_id_shape(self, client, admin_auth_headers):
        """DELETE on the catalog endpoint filters by module_type='catalog_material',
        so it must not be able to delete a regular procurement material even if
        (hypothetically) IDs collided in shape."""
        material_id = make_material(client, admin_auth_headers, material_name='Regular Material')
        response = client.delete(f'/procurement/api/catalog/materials/{material_id}', headers=admin_auth_headers)
        assert response.status_code == 404
        # Confirm the regular material is untouched.
        listed = client.get('/procurement/api/materials', headers=admin_auth_headers)
        assert listed.get_json()['total'] == 1


# ---------------------------------------------------------------------------
# GET /procurement/api/registered-properties
# ---------------------------------------------------------------------------

class TestRegisteredProperties:
    def test_requires_auth(self, client):
        response = client.get('/procurement/api/registered-properties')
        assert response.status_code in (401, 422)

    def test_denied_without_access(self, client, auth_headers):
        response = client.get('/procurement/api/registered-properties', headers=auth_headers)
        assert response.status_code == 403

    def test_empty(self, client, admin_auth_headers):
        response = client.get('/procurement/api/registered-properties', headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['properties'] == []

    def test_lists_created_properties(self, client, admin_auth_headers):
        client.post('/procurement/api/properties', headers=admin_auth_headers, json={
            'name': 'Registered Tower',
            'address': '456 Sample Rd',
            'description': 'A registered property',
        })
        response = client.get('/procurement/api/registered-properties', headers=admin_auth_headers)
        assert response.status_code == 200
        props = response.get_json()['properties']
        assert len(props) == 1
        p = props[0]
        assert p['name'] == 'Registered Tower'
        assert p['address'] == '456 Sample Rd'
        assert p['description'] == 'A registered property'
        assert p['id'].startswith('PROC-PROP-')
        assert p['created_at'] is not None
