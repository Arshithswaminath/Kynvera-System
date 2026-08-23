"""QHSI module route tests — dashboard, staff compliance, training, inspections.

Integration-style tests hitting the live Flask routes via the test client,
matching the style of tests/test_ticket_geocode.py and tests/test_technician_login.py.
"""
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest
from openpyxl import Workbook

from app.models import db, Job, QhseComplianceImport, QhsiTraining, Submission
from tests.factories import make_user


# ─── Local login helpers (per task instructions: do not touch conftest.py) ──

def _login(client, username, password):
    res = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200, res.get_json()
    token = res.get_json().get('access_token')
    assert token
    return {'Authorization': f'Bearer {token}'}


def _qhsi_user_headers(app, client, access_qhsi):
    """Create+commit a non-admin User with (or without) QHSI access, then log in."""
    with app.app_context():
        user, password = make_user(access_qhsi=access_qhsi)
        username = user.username
    return _login(client, username, password)


def _build_xlsx_bytes(rows=None):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Staff Compliance'
    ws.append(['Employee Name', 'Project', 'Item', 'Condition'])
    for row in (rows or [('Ahmed Hassan', 'Site A', 'Uniform Shirt', 'OK')]):
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ─── Dashboard (GET /qhsi/ — jwt_required only, no module_access_required) ──

class TestQhsiDashboard:
    def test_requires_auth(self, client):
        # HTML page routes (path has no '/api/' segment) go through the app's
        # `_is_html_page_request()` JWT-error branch, which silently redirects
        # to the login page instead of returning a JSON 401 — see
        # Injaaz.py's `unauthorized_loader`/`_silent_refresh_or_login`.
        res = client.get('/qhsi/')
        assert res.status_code == 302
        assert '/login' in res.headers.get('Location', '')

    def test_admin_sees_dashboard(self, client, admin_auth_headers):
        res = client.get('/qhsi/', headers=admin_auth_headers)
        assert res.status_code == 200

    def test_user_with_access_sees_dashboard(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=True)
        res = client.get('/qhsi/', headers=headers)
        assert res.status_code == 200

    def test_user_without_access_redirects_to_dashboard(self, client, app):
        """No @module_access_required on this route, but the handler manually
        checks _has_qhsi_access() and redirects instead of returning JSON 403."""
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.get('/qhsi/', headers=headers)
        assert res.status_code == 302
        assert '/dashboard' in res.headers.get('Location', '')


# ─── Sub-pages (jwt_required + module_access_required) ─────────────────────

QHSI_PAGES = ['/qhsi/staff-compliance', '/qhsi/training', '/qhsi/inspection']


class TestQhsiPages:
    @pytest.mark.parametrize('path', QHSI_PAGES)
    def test_requires_auth(self, client, path):
        # Same page-route redirect behavior as the dashboard (see comment above).
        res = client.get(path)
        assert res.status_code == 302
        assert '/login' in res.headers.get('Location', '')

    @pytest.mark.parametrize('path', QHSI_PAGES)
    def test_admin_can_view(self, client, admin_auth_headers, path):
        res = client.get(path, headers=admin_auth_headers)
        assert res.status_code == 200

    @pytest.mark.parametrize('path', QHSI_PAGES)
    def test_user_with_access_can_view(self, client, app, path):
        headers = _qhsi_user_headers(app, client, access_qhsi=True)
        res = client.get(path, headers=headers)
        assert res.status_code == 200

    @pytest.mark.parametrize('path', QHSI_PAGES)
    def test_user_without_access_forbidden(self, client, app, path):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.get(path, headers=headers)
        assert res.status_code == 403
        data = res.get_json()
        assert data.get('module') == 'qhsi'


# ─── Read-only API endpoints ─────────────────────────────────────────────

class TestQhsiReadApis:
    def test_inspection_catalog_unauthenticated(self, client):
        res = client.get('/qhsi/api/inspection-catalog')
        assert res.status_code in (401, 422)

    def test_inspection_catalog_no_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.get('/qhsi/api/inspection-catalog', headers=headers)
        assert res.status_code == 403

    def test_inspection_catalog_ok(self, client, admin_auth_headers):
        res = client.get('/qhsi/api/inspection-catalog', headers=admin_auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert 'catalog' in data

    def test_projects_ok(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=True)
        res = client.get('/qhsi/api/projects', headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert isinstance(data['projects'], list)

    def test_projects_no_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.get('/qhsi/api/projects', headers=headers)
        assert res.status_code == 403

    def test_stats_ok(self, client, admin_auth_headers):
        res = client.get('/qhsi/api/stats', headers=admin_auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert 'forms_submitted' in data
        assert 'submissions' in data
        assert 'import' in data

    def test_stats_unauthenticated(self, client):
        res = client.get('/qhsi/api/stats')
        assert res.status_code in (401, 422)


# ─── Staff compliance Excel import ───────────────────────────────────────

class TestStaffComplianceImport:
    def test_import_template_download(self, client, admin_auth_headers):
        res = client.get('/qhsi/api/staff-compliance/import-template', headers=admin_auth_headers)
        assert res.status_code == 200
        assert res.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert res.data[:2] == b'PK'
        assert len(res.data) > 0

    def test_import_template_requires_auth(self, client):
        res = client.get('/qhsi/api/staff-compliance/import-template')
        assert res.status_code in (401, 422)

    def test_import_no_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.post(
            '/qhsi/api/staff-compliance/import',
            headers=headers,
            data={'file': (BytesIO(_build_xlsx_bytes()), 'a.xlsx')},
            content_type='multipart/form-data',
        )
        assert res.status_code == 403

    def test_import_no_file_uploaded(self, client, admin_auth_headers):
        res = client.post(
            '/qhsi/api/staff-compliance/import',
            headers=admin_auth_headers,
            data={},
            content_type='multipart/form-data',
        )
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_import_rejects_non_excel_file(self, client, admin_auth_headers):
        res = client.post(
            '/qhsi/api/staff-compliance/import',
            headers=admin_auth_headers,
            data={'file': (BytesIO(b'just some plain text'), 'notes.txt')},
            content_type='multipart/form-data',
        )
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_import_happy_path(self, client, admin_auth_headers, app):
        res = client.post(
            '/qhsi/api/staff-compliance/import',
            headers=admin_auth_headers,
            data={'file': (BytesIO(_build_xlsx_bytes()), 'compliance.xlsx')},
            content_type='multipart/form-data',
        )
        assert res.status_code == 200, res.get_json()
        data = res.get_json()
        assert data['success'] is True
        assert data['stats']['employees'] == 1
        assert data['import']['row_count'] == 1

        latest = client.get('/qhsi/api/staff-compliance/import/latest', headers=admin_auth_headers)
        assert latest.status_code == 200
        latest_data = latest.get_json()
        assert latest_data['success'] is True
        assert latest_data['import']['has_import'] is True
        assert latest_data['import']['employees'] == 1
        assert latest_data['import']['kit_lines'] == 1
        assert latest_data['import']['compliant'] is not None
        assert latest_data['import']['issues'] is not None
        assert latest_data['import']['missing'] is not None

        with app.app_context():
            QhseComplianceImport.query.delete()
            db.session.commit()

    def test_import_latest_no_import_yet(self, client, admin_auth_headers, app):
        with app.app_context():
            QhseComplianceImport.query.delete()
            db.session.commit()
        res = client.get('/qhsi/api/staff-compliance/import/latest', headers=admin_auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert data['import']['has_import'] is False

    def test_delete_import(self, client, admin_auth_headers, app):
        client.post(
            '/qhsi/api/staff-compliance/import',
            headers=admin_auth_headers,
            data={'file': (BytesIO(_build_xlsx_bytes()), 'compliance2.xlsx')},
            content_type='multipart/form-data',
        )
        res = client.delete('/qhsi/api/staff-compliance/import', headers=admin_auth_headers)
        assert res.status_code == 200
        assert res.get_json()['success'] is True
        with app.app_context():
            assert QhseComplianceImport.query.count() == 0

    def test_delete_import_no_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.delete('/qhsi/api/staff-compliance/import', headers=headers)
        assert res.status_code == 403


# ─── Staff compliance record submission ──────────────────────────────────

class TestStaffComplianceSubmit:
    def test_requires_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.post('/qhsi/api/staff-compliance/submit', headers=headers, json={})
        assert res.status_code == 403

    def test_unauthenticated(self, client):
        res = client.post('/qhsi/api/staff-compliance/submit', json={})
        assert res.status_code in (401, 422)

    def test_missing_required_fields(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/staff-compliance/submit', headers=admin_auth_headers, json={})
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_happy_path(self, client, admin_auth_headers, app):
        payload = {
            'employee_name': 'Jane Doe',
            'project_name': 'Site Q',
            'record_date': date.today().isoformat(),
            'department': 'Operations',
            'kit_items': [{'item_type': 'helmet', 'item_label': 'Helmet', 'condition': 'ok'}],
        }
        res = client.post('/qhsi/api/staff-compliance/submit', headers=admin_auth_headers, json=payload)
        assert res.status_code == 200, res.get_json()
        data = res.get_json()
        assert data['success'] is True
        assert data['submission_id']

        with app.app_context():
            sub = Submission.query.filter_by(submission_id=data['submission_id']).first()
            assert sub is not None
            assert sub.module_type == 'qhsi_staff_compliance'
            db.session.delete(sub)
            db.session.commit()


# ─── Unified QHSA inspection submission ──────────────────────────────────

class TestInspectionSubmit:
    def test_requires_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.post('/qhsi/api/inspection/submit', headers=headers, json={})
        assert res.status_code == 403

    def test_unauthenticated(self, client):
        res = client.post('/qhsi/api/inspection/submit', json={})
        assert res.status_code in (401, 422)

    def test_missing_required_fields(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/inspection/submit', headers=admin_auth_headers, json={})
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_invalid_department(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/inspection/submit', headers=admin_auth_headers, json={
            'project_name': 'Site Q',
            'visit_date': date.today().isoformat(),
            'department': 'plumbing',
        })
        assert res.status_code == 400

    def test_requires_at_least_one_item(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/inspection/submit', headers=admin_auth_headers, json={
            'project_name': 'Site Q',
            'visit_date': date.today().isoformat(),
            'department': 'hvac',
            'items': [],
        })
        assert res.status_code == 400

    def test_requires_photo_per_item(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/inspection/submit', headers=admin_auth_headers, json={
            'project_name': 'Site Q',
            'visit_date': date.today().isoformat(),
            'department': 'hvac',
            'items': [{'description': 'Dirty filter', 'photos': []}],
        })
        assert res.status_code == 400

    def test_happy_path(self, client, admin_auth_headers, app):
        payload = {
            'project_name': 'Site Q',
            'visit_date': date.today().isoformat(),
            'department': 'hvac',
            'items': [{
                'trade': 'HVAC',
                'area': 'Lobby',
                'description': 'AC filter dirty',
                'severity': 'observation',
                'photos': ['data:image/png;base64,AAAA'],
            }],
        }
        # Mock the photo uploader (would otherwise hit Cloudinary — real network
        # call with retry/backoff — and the background report-generation job,
        # which does real PDF/Excel generation) so the test stays fast/offline.
        with patch(
            'module_qhsi.routes.upload_base64_to_cloud',
            return_value=('https://example.com/fake.png', False),
        ) as mock_upload, patch('module_qhsi.routes.process_job') as mock_process_job:
            res = client.post('/qhsi/api/inspection/submit', headers=admin_auth_headers, json=payload)

        assert res.status_code == 200, res.get_json()
        data = res.get_json()
        assert data['success'] is True
        assert data['submission_id']
        assert data['job_id']
        mock_upload.assert_called_once()

        with app.app_context():
            sub = Submission.query.filter_by(submission_id=data['submission_id']).first()
            assert sub is not None
            assert sub.module_type == 'qhsi_inspection'
            job = Job.query.filter_by(job_id=data['job_id']).first()
            assert job is not None
            db.session.delete(job)
            db.session.delete(sub)
            db.session.commit()


# ─── Training CRUD ────────────────────────────────────────────────────────

class TestTrainings:
    def test_list_requires_auth(self, client):
        res = client.get('/qhsi/api/trainings')
        assert res.status_code in (401, 422)

    def test_list_requires_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.get('/qhsi/api/trainings', headers=headers)
        assert res.status_code == 403

    def test_create_missing_fields(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/trainings', headers=admin_auth_headers, json={})
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_invalid_datetime(self, client, admin_auth_headers):
        res = client.post('/qhsi/api/trainings', headers=admin_auth_headers, json={
            'project_name': 'Site Q',
            'title': 'Bad Date Training',
            'scheduled_at': 'not-a-real-date',
        })
        assert res.status_code == 400

    def test_create_requires_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.post('/qhsi/api/trainings', headers=headers, json={
            'project_name': 'Site Q', 'title': 'x', 'scheduled_at': '2026-09-01T10:00:00',
        })
        assert res.status_code == 403

    def test_full_crud_cycle(self, client, admin_auth_headers, app):
        create_res = client.post('/qhsi/api/trainings', headers=admin_auth_headers, json={
            'project_name': 'Site Q',
            'title': 'Fire Safety Briefing',
            'scheduled_at': '2026-09-01T10:00:00',
            'training_type': 'training',
            'duration_minutes': 45,
        })
        assert create_res.status_code == 201, create_res.get_json()
        training = create_res.get_json()['training']
        training_id = training['training_id']
        assert training['status'] == 'scheduled'
        assert training['project_name'] == 'Site Q'
        assert training['duration_minutes'] == 45

        list_res = client.get('/qhsi/api/trainings', headers=admin_auth_headers)
        assert list_res.status_code == 200
        ids = [t['training_id'] for t in list_res.get_json()['trainings']]
        assert training_id in ids

        list_status_res = client.get(
            '/qhsi/api/trainings?status=scheduled', headers=admin_auth_headers
        )
        assert list_status_res.status_code == 200
        assert training_id in [t['training_id'] for t in list_status_res.get_json()['trainings']]

        patch_res = client.patch(
            f'/qhsi/api/trainings/{training_id}',
            headers=admin_auth_headers,
            json={'status': 'completed', 'notes': 'Done'},
        )
        assert patch_res.status_code == 200
        patched = patch_res.get_json()['training']
        assert patched['status'] == 'completed'
        assert patched['notes'] == 'Done'

        delete_res = client.delete(f'/qhsi/api/trainings/{training_id}', headers=admin_auth_headers)
        assert delete_res.status_code == 200
        assert delete_res.get_json()['deleted'] == training_id

        with app.app_context():
            assert QhsiTraining.query.filter_by(training_id=training_id).first() is None

    def test_update_not_found(self, client, admin_auth_headers):
        res = client.patch(
            '/qhsi/api/trainings/no-such-training-id',
            headers=admin_auth_headers,
            json={'status': 'completed'},
        )
        assert res.status_code == 404
        assert res.get_json()['success'] is False

    def test_update_requires_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.patch(
            '/qhsi/api/trainings/whatever',
            headers=headers,
            json={'status': 'completed'},
        )
        assert res.status_code == 403

    def test_delete_not_found(self, client, admin_auth_headers):
        res = client.delete('/qhsi/api/trainings/no-such-training-id', headers=admin_auth_headers)
        assert res.status_code == 404
        assert res.get_json()['success'] is False

    def test_delete_requires_access(self, client, app):
        headers = _qhsi_user_headers(app, client, access_qhsi=False)
        res = client.delete('/qhsi/api/trainings/whatever', headers=headers)
        assert res.status_code == 403
