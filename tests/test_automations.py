"""Automations hub: HR daily Excel backup, catch-up guard, scheduler skip in TESTING."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.automations.jobs import HR_DAILY_EXCEL, JOB_CATALOG


def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def hr_auth_headers(app, client):
    from tests.factories import make_user

    with app.app_context():
        user, pwd = make_user(access_hr=True)
        username = user.username
    return _login(client, username, pwd)


def _dubai_today():
    return datetime.now(ZoneInfo('Asia/Dubai')).strftime('%Y-%m-%d')


def _reset_hr_job(app, **overrides):
    from app.automations.jobs import ensure_seed_jobs
    from app.models import AutomationJob, db

    with app.app_context():
        job = ensure_seed_jobs()
        job.enabled = True
        job.save_to_files = True
        job.send_email = True
        job.sync_drive = True
        job.to_emails = 'hr-backup@example.com'
        job.last_success_at = None
        job.last_error = None
        for key, value in overrides.items():
            setattr(job, key, value)
        db.session.commit()
        return job.id


class TestAutomationsPages:
    def test_page_requires_auth(self, client):
        response = client.get('/automations/')
        assert response.status_code in (302, 401, 422)

    def test_page_renders_for_admin(self, client, admin_auth_headers):
        response = client.get('/automations/', headers=admin_auth_headers)
        assert response.status_code == 200
        assert b'Automations' in response.data

    def test_page_renders_for_hr(self, client, hr_auth_headers):
        response = client.get('/automations/', headers=hr_auth_headers)
        assert response.status_code == 200

    def test_page_forbidden_for_plain_user(self, client, auth_headers):
        response = client.get('/automations/', headers=auth_headers)
        assert response.status_code == 403

    def test_api_forbidden_for_plain_user(self, client, auth_headers):
        response = client.get('/automations/api/jobs', headers=auth_headers)
        assert response.status_code == 403


class TestJobCatalog:
    def test_list_seeds_hr_daily_and_coming_soon(self, client, admin_auth_headers):
        response = client.get('/automations/api/jobs', headers=admin_auth_headers)
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        jobs = {row['slug']: row for row in data['jobs']}
        assert HR_DAILY_EXCEL in jobs
        assert jobs[HR_DAILY_EXCEL]['implemented'] is True
        assert jobs[HR_DAILY_EXCEL]['schedule_hour'] == 20
        coming = [row for row in data['jobs'] if not row['implemented']]
        assert coming, 'catalog should list upcoming module exports'
        expected = {row['slug'] for row in JOB_CATALOG}
        assert expected <= set(jobs)

    def test_coming_soon_not_runnable(self, client, admin_auth_headers):
        response = client.post(
            '/automations/api/jobs/procurement_daily_excel/run',
            headers=admin_auth_headers,
        )
        assert response.status_code == 400
        body = response.get_json()
        assert body['success'] is False

    def test_patch_recipients(self, client, app, admin_auth_headers):
        _reset_hr_job(app)
        response = client.patch(
            f'/automations/api/jobs/{HR_DAILY_EXCEL}',
            json={'to_emails': 'ops@example.com, hr@example.com'},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200, response.get_json()
        job = response.get_json()['job']
        assert 'ops@example.com' in job['to_emails']
        listed = client.get('/automations/api/jobs', headers=admin_auth_headers).get_json()
        row = next(j for j in listed['jobs'] if j['slug'] == HR_DAILY_EXCEL)
        assert 'hr@example.com' in row['to_emails']


class TestHrDailyRun:
    def test_run_now_saves_files_emails_skips_drive(self, client, app, admin_auth_headers):
        _reset_hr_job(app, to_emails='backup@example.com')
        sync_item = MagicMock()
        with patch('app.automations.runner.is_email_configured', return_value=True), \
             patch('app.automations.runner.send_email', return_value=True) as send_email, \
             patch('module_files.drive_service.sync_item', sync_item):
            response = client.post(
                f'/automations/api/jobs/{HR_DAILY_EXCEL}/run',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['status'] == 'ok'
        files = data['run']['detail']['files']
        assert len(files) == 3
        day = _dubai_today()
        names = {row['filename'] for row in files}
        assert f'Hiring_Export_{day}.xlsx' in names
        assert f'Leave_Tracker_Export_{day}.xlsx' in names
        assert f'Manpower_Export_{day}.xlsx' in names
        for row in files:
            assert row['item_id']
            assert row['drive'].get('skipped') is True
        email = data['run']['detail']['email']
        assert email['sent'] is True
        assert email.get('skipped') is False
        send_email.assert_called_once()
        args, kwargs = send_email.call_args
        assert args[0] == ['backup@example.com']
        assert kwargs.get('source') == 'hr'
        assert len(kwargs.get('attachments') or []) == 3
        sync_item.assert_not_called()

    def test_run_now_saves_when_email_not_configured(self, client, app, admin_auth_headers):
        _reset_hr_job(app, to_emails='backup@example.com')
        with patch('app.automations.runner.is_email_configured', return_value=False), \
             patch('app.automations.runner.send_email') as send_email:
            response = client.post(
                f'/automations/api/jobs/{HR_DAILY_EXCEL}/run',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['status'] == 'warning'
        assert len(data['run']['detail']['files']) == 3
        assert data['run']['detail']['email'].get('reason') == 'email_not_configured'
        send_email.assert_not_called()

    def test_drive_failure_does_not_fail_job(self, app):
        from app.automations.runner import run_job

        _reset_hr_job(app, to_emails='backup@example.com')
        with app.app_context():
            with patch('app.automations.runner.is_email_configured', return_value=True), \
                 patch('app.automations.runner.send_email', return_value=True), \
                 patch(
                     'module_files.drive_service.drive_status',
                     return_value={'connected': True, 'message': 'ok'},
                 ), \
                 patch(
                     'module_files.drive_service.sync_item',
                     side_effect=RuntimeError('Drive exploded'),
                 ):
                result = run_job(HR_DAILY_EXCEL, trigger='manual')
        assert result['status'] == 'warning'
        assert len(result['run']['detail']['files']) == 3
        assert any('Drive' in w for w in result['warnings'])


class TestCatchupAndScheduler:
    def test_catchup_skips_when_succeeded_today(self, app):
        from app.automations.runner import run_catchup
        from app.models import AutomationRun

        _reset_hr_job(app, last_success_at=datetime.now(timezone.utc).replace(tzinfo=None))
        with app.app_context():
            before = AutomationRun.query.count()
            with patch('app.automations.runner.run_job') as run_job:
                results = run_catchup()
            run_job.assert_not_called()
            after = AutomationRun.query.count()
        assert results[0]['status'] == 'skipped'
        assert after == before

    def test_catchup_runs_when_not_succeeded_today(self, app):
        from app.automations.runner import run_catchup

        yesterday = datetime.now(ZoneInfo('Asia/Dubai')) - timedelta(days=1)
        _reset_hr_job(
            app,
            last_success_at=yesterday.astimezone(timezone.utc).replace(tzinfo=None),
        )
        with app.app_context():
            with patch('app.automations.runner.is_email_configured', return_value=True), \
                 patch('app.automations.runner.send_email', return_value=True), \
                 patch('module_files.drive_service.sync_item'):
                results = run_catchup()
        assert results[0]['status'] in ('ok', 'warning')
        assert results[0]['run']['trigger'] == 'catchup'
        assert len(results[0]['run']['detail']['files']) == 3

    def test_scheduler_not_started_in_testing(self, app):
        from app.automations import scheduler as automations_scheduler

        assert automations_scheduler._scheduler is None
        automations_scheduler.init_scheduler(app)
        assert automations_scheduler._scheduler is None
