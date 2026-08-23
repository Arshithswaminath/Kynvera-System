"""MMR (Report Generation hub) blueprint: upload, dashboard, download, save-to-folder/drive,
email config/presets, automation status/pause/resume, cycles, and send-email.

Integration-style tests hitting the live Flask routes via the test client, following the
mocking conventions used in tests/test_bd_email_automation.py and the general structure of
tests/test_ticket_geocode.py.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from tests.factories import make_user

EXPECTED_COLS = [
    'WorkOrder No', 'Reported Date', 'Priority', 'Work Description',
    'Client', 'Reported By', 'Service Group', 'Assigned Date',
    'Work Start Date', 'Closed By', 'Status', 'Contract', 'BaseUnit', 'Space',
]
MMR_FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'mmr' / 'cafm_sample.xlsx'


def _build_workbook_bytes(rows=None):
    """Tiny in-memory .xlsx matching the CAFM 'Reactive Workorder Details' export shape."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Reactive Workorder Details'
    ws.append(EXPECTED_COLS)
    if rows is None:
        rows = [[
            '10017690', datetime(2026, 7, 15), 'High', 'AC not cooling',
            'Ajman Municipality', 'John Doe', 'HVAC', datetime(2026, 7, 15),
            datetime(2026, 7, 15), 'Jane Smith', 'Closed', 'FM Contract A',
            'Apt No 101', 'Chargeable',
        ]]
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(autouse=True)
def _isolated_generated_dir(app, tmp_path, monkeypatch):
    """Sandbox all MMR file I/O (mmr_latest.xlsx, config/cycle/activity JSON, mmr_reports/) into
    a throwaway tmp_path instead of the real GENERATED_DIR, which holds live dev data."""
    monkeypatch.setitem(app.config, 'GENERATED_DIR', str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def _no_scheduler_races(monkeypatch):
    """The APScheduler background job from module_mmr.scheduler.init_scheduler() is already
    running for the whole test session (started unconditionally in Injaaz.create_app()). Routes
    that call module_mmr.scheduler.update_schedule must not touch that live scheduler/job during
    tests, so stub it out everywhere instead of letting each route reach into the real scheduler."""
    monkeypatch.setattr('module_mmr.scheduler.update_schedule', lambda *a, **kw: None)
    yield


@pytest.fixture
def report_access_headers(app, client):
    """Non-admin user with access_report_generation=True, logged in for real headers."""
    with app.app_context():
        user, password = make_user(role='user', access_report_generation=True)
        username = user.username
    return _login(client, username, password)


@pytest.fixture
def uploaded(client, admin_auth_headers):
    """Upload the sample workbook as admin so subsequent routes have a current file + cycle."""
    payload = MMR_FIXTURE.read_bytes() if MMR_FIXTURE.is_file() else _build_workbook_bytes()
    data = {'file': (BytesIO(payload), 'cafm_export.xlsx')}
    resp = client.post(
        '/admin/mmr/api/upload', data=data, headers=admin_auth_headers,
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard page + access control
# ──────────────────────────────────────────────────────────────────────────────

class TestDashboardAccess:
    def test_requires_auth(self, client):
        """The dashboard is an HTML page route (path has no /api/ segment), so the app's
        custom JWT unauthorized handler (Injaaz.py's unauthorized_callback /
        _is_html_page_request) silently redirects to login instead of returning
        401/422 JSON — that behavior is reserved for /admin/mmr/api/* endpoints."""
        response = client.get('/admin/mmr/')
        assert response.status_code == 302

    def test_admin_ok(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_report_access_user_ok(self, client, report_access_headers):
        response = client.get('/admin/mmr/', headers=report_access_headers)
        assert response.status_code == 200

    def test_forbidden_without_access(self, client, auth_headers):
        response = client.get('/admin/mmr/', headers=auth_headers)
        assert response.status_code == 403

    def test_api_forbidden_without_access_returns_json(self, client, auth_headers):
        response = client.get('/admin/mmr/api/current-upload', headers=auth_headers)
        assert response.status_code == 403
        assert 'error' in response.get_json()

    def test_api_requires_auth(self, client):
        response = client.get('/admin/mmr/api/current-upload')
        assert response.status_code in (401, 422)


# ──────────────────────────────────────────────────────────────────────────────
# Upload / current-upload / clear-upload
# ──────────────────────────────────────────────────────────────────────────────

class TestUpload:
    def test_no_file_provided(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/upload', headers=admin_auth_headers,
                                content_type='multipart/form-data', data={})
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_invalid_extension_rejected(self, client, admin_auth_headers):
        data = {'file': (BytesIO(b'not an excel file'), 'notes.txt')}
        response = client.post('/admin/mmr/api/upload', data=data, headers=admin_auth_headers,
                                content_type='multipart/form-data')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_happy_path_admin(self, client, admin_auth_headers):
        data = {'file': (BytesIO(_build_workbook_bytes()), 'cafm_export.xlsx')}
        response = client.post('/admin/mmr/api/upload', data=data, headers=admin_auth_headers,
                                content_type='multipart/form-data')
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body['success'] is True
        assert body['total'] == 1
        assert body['dashboard']['total'] == 1
        assert body['rows'][0]['Client'] == 'Ajman Municipality'

    def test_happy_path_report_access_user(self, client, report_access_headers):
        data = {'file': (BytesIO(_build_workbook_bytes()), 'cafm_export.xlsx')}
        response = client.post('/admin/mmr/api/upload', data=data, headers=report_access_headers,
                                content_type='multipart/form-data')
        assert response.status_code == 200, response.get_json()

    def test_forbidden_for_standard_user(self, client, auth_headers):
        data = {'file': (BytesIO(_build_workbook_bytes()), 'cafm_export.xlsx')}
        response = client.post('/admin/mmr/api/upload', data=data, headers=auth_headers,
                                content_type='multipart/form-data')
        assert response.status_code == 403

    def test_requires_auth(self, client):
        data = {'file': (BytesIO(_build_workbook_bytes()), 'cafm_export.xlsx')}
        response = client.post('/admin/mmr/api/upload', data=data,
                                content_type='multipart/form-data')
        assert response.status_code in (401, 422)


class TestCurrentUpload:
    def test_no_file_yet(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/current-upload', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['success'] is True
        assert body['has_file'] is False

    def test_after_upload(self, client, admin_auth_headers, uploaded):
        response = client.get('/admin/mmr/api/current-upload', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['has_file'] is True
        assert body['total'] == 1


class TestClearUpload:
    def test_clear_removes_file(self, client, admin_auth_headers, uploaded):
        response = client.post('/admin/mmr/api/clear-upload', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        follow_up = client.get('/admin/mmr/api/current-upload', headers=admin_auth_headers)
        assert follow_up.get_json()['has_file'] is False

    def test_clear_when_nothing_uploaded_is_noop_success(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/clear-upload', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['success'] is True


# ──────────────────────────────────────────────────────────────────────────────
# Download report (single + monthly zip)
# ──────────────────────────────────────────────────────────────────────────────

class TestDownloadReport:
    def test_no_file_uploaded_yet(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/download-report', headers=admin_auth_headers)
        assert response.status_code == 404

    def test_happy_path(self, client, admin_auth_headers, uploaded):
        response = client.get('/admin/mmr/api/download-report', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.mimetype == (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        assert response.data[:2] == b'PK'
        assert len(response.data) > 0

    def test_monthly_no_file_uploaded_yet(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/download-report-monthly', headers=admin_auth_headers)
        assert response.status_code == 404

    def test_monthly_happy_path(self, client, admin_auth_headers, uploaded):
        response = client.get('/admin/mmr/api/download-report-monthly', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.mimetype == 'application/zip'
        assert len(response.data) > 0

    def test_requires_auth(self, client):
        response = client.get('/admin/mmr/api/download-report')
        assert response.status_code in (401, 422)


# ──────────────────────────────────────────────────────────────────────────────
# Save to folder / Save to drive / Report folder
# ──────────────────────────────────────────────────────────────────────────────

class TestSaveToFolder:
    def test_no_file_uploaded_yet(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/save-to-folder', headers=admin_auth_headers, json={})
        assert response.status_code == 400

    def test_happy_path(self, client, admin_auth_headers, uploaded):
        response = client.post('/admin/mmr/api/save-to-folder', headers=admin_auth_headers, json={})
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body['success'] is True
        assert body['filename'].endswith('.xlsx')


class TestSaveToDrive:
    def test_no_file_uploaded_yet(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/save-to-drive', headers=admin_auth_headers, json={})
        assert response.status_code == 400

    def test_happy_path_mocked(self, client, admin_auth_headers, uploaded, monkeypatch, tmp_path):
        """MMR's Save to Drive writes directly to a TrueNAS UNC path (no module_files.drive_service
        dependency in this module) via routes._save_report_to_drive — mock that function directly
        so the test never touches a real network share."""
        fake_path = str(tmp_path / 'drive_fallback' / 'report.xlsx')
        calls = []

        def fake_save_to_drive(report_bytes, filename, save_path=None):
            calls.append((filename, save_path))
            return fake_path, None, False

        monkeypatch.setattr('module_mmr.routes._save_report_to_drive', fake_save_to_drive)

        response = client.post('/admin/mmr/api/save-to-drive', headers=admin_auth_headers, json={})
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body['success'] is True
        assert body['path'] == fake_path
        assert len(calls) == 2  # CAFM path + General CAFM path (default save-to-both behaviour)

    def test_failure_from_both_paths_mocked(self, client, admin_auth_headers, uploaded, monkeypatch):
        monkeypatch.setattr(
            'module_mmr.routes._save_report_to_drive',
            lambda report_bytes, filename, save_path=None: (None, 'network unreachable', False),
        )
        response = client.post('/admin/mmr/api/save-to-drive', headers=admin_auth_headers, json={})
        assert response.status_code == 500
        assert 'error' in response.get_json()


class TestReportFolder:
    def test_list_includes_saved_file(self, client, admin_auth_headers, uploaded):
        save_resp = client.post('/admin/mmr/api/save-to-folder', headers=admin_auth_headers, json={})
        filename = save_resp.get_json()['filename']

        response = client.get('/admin/mmr/api/report-folder', headers=admin_auth_headers)
        assert response.status_code == 200
        names = [f['name'] for f in response.get_json()['files']]
        assert filename in names

    def test_list_empty_when_nothing_saved(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/report-folder', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['files'] == []

    def test_download_saved_file(self, client, admin_auth_headers, uploaded):
        save_resp = client.post('/admin/mmr/api/save-to-folder', headers=admin_auth_headers, json={})
        filename = save_resp.get_json()['filename']

        response = client.get(
            f'/admin/mmr/api/report-folder/download/{filename}', headers=admin_auth_headers
        )
        assert response.status_code == 200
        assert len(response.data) > 0

    def test_download_unknown_file_404(self, client, admin_auth_headers):
        response = client.get(
            '/admin/mmr/api/report-folder/download/does-not-exist.xlsx', headers=admin_auth_headers
        )
        assert response.status_code == 404

    def test_download_rejects_path_traversal(self, client, admin_auth_headers):
        response = client.get(
            '/admin/mmr/api/report-folder/download/..%2F..%2Fetc%2Fpasswd',
            headers=admin_auth_headers,
        )
        assert response.status_code in (400, 404)

    def test_open_saved_file(self, client, admin_auth_headers, uploaded):
        save_resp = client.post('/admin/mmr/api/save-to-folder', headers=admin_auth_headers, json={})
        filename = save_resp.get_json()['filename']

        response = client.get(
            f'/admin/mmr/api/report-folder/open/{filename}', headers=admin_auth_headers
        )
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body['success'] is True
        assert body['total'] == 1

    def test_open_unknown_file_404(self, client, admin_auth_headers):
        response = client.get(
            '/admin/mmr/api/report-folder/open/does-not-exist.xlsx', headers=admin_auth_headers
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Email config + presets + suggestions
# ──────────────────────────────────────────────────────────────────────────────

class TestEmailConfig:
    def test_get_returns_defaults_and_presets(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/email-config', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert 'to' in body and 'cc' in body
        assert 'presets' in body and 'daily' in body['presets'] and 'monthly' in body['presets']
        assert body['custom_presets'] == []

    def test_post_updates_config(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/email-config', headers=admin_auth_headers, json={
            'to': 'dennis@injaaz.ae',
            'cc': 'shakeel@injaaz.ae',
            'schedule_enabled': True,
            'schedule_hour': 9,
            'schedule_minute': 30,
        })
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        follow_up = client.get('/admin/mmr/api/email-config', headers=admin_auth_headers)
        body = follow_up.get_json()
        assert body['to'] == 'dennis@injaaz.ae'
        assert body['schedule_hour'] == 9

    def test_post_rejects_non_injaaz_domain(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/email-config', headers=admin_auth_headers, json={
            'to': 'someone@gmail.com',
        })
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_forbidden_for_standard_user(self, client, auth_headers):
        response = client.get('/admin/mmr/api/email-config', headers=auth_headers)
        assert response.status_code == 403

    def test_requires_auth(self, client):
        response = client.get('/admin/mmr/api/email-config')
        assert response.status_code in (401, 422)


class TestEmailSuggestions:
    def test_returns_suggestions(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/email-suggestions', headers=admin_auth_headers)
        assert response.status_code == 200
        suggestions = response.get_json()['suggestions']
        assert isinstance(suggestions, list)
        assert any(s['email'] == 'dennis@injaaz.ae' for s in suggestions)

    def test_filters_by_query(self, client, admin_auth_headers):
        response = client.get(
            '/admin/mmr/api/email-suggestions?q=dennis', headers=admin_auth_headers
        )
        assert response.status_code == 200
        suggestions = response.get_json()['suggestions']
        assert all('dennis' in s['email'].lower() for s in suggestions)


class TestEmailPresets:
    def test_save_and_delete_preset(self, client, admin_auth_headers):
        create = client.post('/admin/mmr/api/email-presets', headers=admin_auth_headers, json={
            'name': 'Weekly Ops',
            'to': 'dennis@injaaz.ae',
            'cc': '',
            'subject': 'Weekly report',
            'body': 'See attached',
            'report_format': 'daily',
        })
        assert create.status_code == 200, create.get_json()
        presets = create.get_json()['custom_presets']
        assert any(p['name'] == 'Weekly Ops' for p in presets)
        key = next(p['key'] for p in presets if p['name'] == 'Weekly Ops')

        delete = client.delete(f'/admin/mmr/api/email-presets/{key}', headers=admin_auth_headers)
        assert delete.status_code == 200
        assert not any(p['key'] == key for p in delete.get_json()['custom_presets'])

    def test_save_rejects_missing_name(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/email-presets', headers=admin_auth_headers, json={
            'to': 'dennis@injaaz.ae',
        })
        assert response.status_code == 400

    def test_save_rejects_missing_to(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/email-presets', headers=admin_auth_headers, json={
            'name': 'No recipient',
        })
        assert response.status_code == 400

    def test_delete_unknown_preset_404(self, client, admin_auth_headers):
        response = client.delete(
            '/admin/mmr/api/email-presets/does-not-exist', headers=admin_auth_headers
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Automation status / activities / pause / resume
# ──────────────────────────────────────────────────────────────────────────────

class TestAutomationStatus:
    def test_status_disabled_by_default(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/automation-status', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['automation_status'] == 'disabled'
        assert body['excel_uploaded'] is False

    def test_status_reflects_upload(self, client, admin_auth_headers, uploaded):
        response = client.get('/admin/mmr/api/automation-status', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['excel_uploaded'] is True

    def test_activities_default_list(self, client, admin_auth_headers, uploaded):
        response = client.get('/admin/mmr/api/automation-activities', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert isinstance(body['activities'], list)
        assert body['activities']  # upload activity was logged
        assert 'max_id' in body

    def test_activities_live_mode_with_active_cycle(self, client, admin_auth_headers, uploaded):
        response = client.get(
            '/admin/mmr/api/automation-activities?mode=live', headers=admin_auth_headers
        )
        assert response.status_code == 200
        body = response.get_json()
        assert 'live_context' in body
        assert body['live_context']['active_cycle_id'] is not None


class TestAutomationPauseResume:
    def test_pause(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/automation-pause', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json() == {'success': True, 'paused': True}

    def test_resume_without_upload_fails(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/automation-resume', headers=admin_auth_headers)
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_resume_after_upload_succeeds(self, client, admin_auth_headers, uploaded):
        client.post('/admin/mmr/api/automation-pause', headers=admin_auth_headers)
        response = client.post('/admin/mmr/api/automation-resume', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json() == {'success': True, 'paused': False}

    def test_forbidden_for_standard_user(self, client, auth_headers):
        response = client.post('/admin/mmr/api/automation-pause', headers=auth_headers)
        assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Cycles + approve
# ──────────────────────────────────────────────────────────────────────────────

class TestCycles:
    def test_cycles_empty_by_default(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/cycles', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['current'] is None
        assert body['history'] == []

    def test_cycles_current_after_upload(self, client, admin_auth_headers, uploaded):
        response = client.get('/admin/mmr/api/cycles', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['current'] is not None
        assert body['current']['status'] == 'uploaded'

    def test_cycle_detail_unknown_id_404(self, client, admin_auth_headers):
        response = client.get('/admin/mmr/api/cycle/999999/detail', headers=admin_auth_headers)
        assert response.status_code == 404

    def test_cycle_detail_current_cycle(self, client, admin_auth_headers, uploaded):
        cycles = client.get('/admin/mmr/api/cycles', headers=admin_auth_headers).get_json()
        cid = cycles['current']['cycle_id']

        response = client.get(f'/admin/mmr/api/cycle/{cid}/detail', headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.get_json()
        assert body['cycle']['cycle_id'] == cid
        assert isinstance(body['timeline'], list)
        assert isinstance(body['activities'], list)

    def test_approve_current_cycle(self, client, admin_auth_headers, uploaded):
        response = client.post('/admin/mmr/api/approve', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        cycles = client.get('/admin/mmr/api/cycles', headers=admin_auth_headers).get_json()
        assert cycles['current']['status'] == 'approved'

    def test_approve_without_upload_fails(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/approve', headers=admin_auth_headers)
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_double_approve_fails(self, client, admin_auth_headers, uploaded):
        first = client.post('/admin/mmr/api/approve', headers=admin_auth_headers)
        assert first.status_code == 200
        second = client.post('/admin/mmr/api/approve', headers=admin_auth_headers)
        assert second.status_code == 400
        assert second.get_json().get('already_approved') is True


# ──────────────────────────────────────────────────────────────────────────────
# Send email
# ──────────────────────────────────────────────────────────────────────────────

class TestSendEmail:
    def test_no_report_available(self, client, admin_auth_headers):
        response = client.post('/admin/mmr/api/send-email', headers=admin_auth_headers, json={
            'to': 'dennis@injaaz.ae',
            'subject': 'Report',
            'body': 'See attached',
        })
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_missing_to_rejected(self, client, admin_auth_headers, uploaded):
        response = client.post('/admin/mmr/api/send-email', headers=admin_auth_headers, json={
            'to': '',
            'subject': 'Report',
            'body': 'Body',
        })
        assert response.status_code == 400

    def test_rejects_non_injaaz_recipient(self, client, admin_auth_headers, uploaded):
        response = client.post('/admin/mmr/api/send-email', headers=admin_auth_headers, json={
            'to': 'someone@gmail.com',
            'subject': 'Report',
            'body': 'Body',
        })
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_email_not_configured(self, client, admin_auth_headers, uploaded, monkeypatch):
        from common import email_service as es
        monkeypatch.setattr(es, 'is_email_configured', lambda app=None: False)

        response = client.post('/admin/mmr/api/send-email', headers=admin_auth_headers, json={
            'to': 'dennis@injaaz.ae',
            'subject': 'Report',
            'body': 'Body',
        })
        assert response.status_code == 503

    def test_happy_path_mocked_send_completes_cycle_and_logs(
        self, client, app, admin_auth_headers, uploaded, monkeypatch
    ):
        from common import email_service as es

        monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
        monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: True)

        response = client.post('/admin/mmr/api/send-email', headers=admin_auth_headers, json={
            'to': 'dennis@injaaz.ae',
            'cc': 'shakeel@injaaz.ae',
            'subject': 'Daily Report on Resolved and Pending Complaints for {{REPORT_DATE}}',
            'body': 'See attached, dated {{REPORT_DATE}}.',
        })
        assert response.status_code == 200, response.get_json()
        assert response.get_json()['success'] is True

        # Cycle should now be completed (moved to history) and the next upload starts fresh.
        cycles = client.get('/admin/mmr/api/cycles', headers=admin_auth_headers).get_json()
        assert cycles['current'] is None
        assert len(cycles['history']) == 1
        assert cycles['history'][0]['status'] == 'sent'

        with app.app_context():
            from app.models import EmailLog
            row = (
                EmailLog.query.filter_by(source='mmr')
                .order_by(EmailLog.id.desc())
                .first()
            )
            assert row is not None
            assert row.status == 'sent'
            assert 'dennis@injaaz.ae' in (row.to_emails or '')

    def test_send_failure_returns_502(self, client, admin_auth_headers, uploaded, monkeypatch):
        from common import email_service as es
        monkeypatch.setattr(es, 'is_email_configured', lambda app=None: True)
        monkeypatch.setattr(es, '_deliver_email', lambda *a, **k: False)

        response = client.post('/admin/mmr/api/send-email', headers=admin_auth_headers, json={
            'to': 'dennis@injaaz.ae',
            'subject': 'Report',
            'body': 'Body',
        })
        assert response.status_code == 502

    def test_requires_auth(self, client):
        response = client.post('/admin/mmr/api/send-email', json={})
        assert response.status_code in (401, 422)

    def test_forbidden_for_standard_user(self, client, auth_headers, uploaded):
        response = client.post('/admin/mmr/api/send-email', headers=auth_headers, json={
            'to': 'dennis@injaaz.ae',
            'subject': 'Report',
            'body': 'Body',
        })
        assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Background scheduler regression check
# ──────────────────────────────────────────────────────────────────────────────

class TestSchedulerLiveness:
    def test_scheduler_initialized_and_running(self, app):
        """The APScheduler job (module_mmr.scheduler.init_scheduler) is started
        unconditionally from Injaaz.create_app(). This is a lightweight confirmation the
        already-running background thread wasn't silently broken — it does not start/stop
        the scheduler itself (that would race the live instance used by the whole session)."""
        from module_mmr import scheduler as mmr_scheduler

        assert mmr_scheduler._scheduler is not None
        assert mmr_scheduler._scheduler.running is True
