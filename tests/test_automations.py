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
        job.export_modules = None
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
        assert b'autoRunModal' in response.data
        assert b'<dialog' in response.data
        assert b'Recent runs' in response.data

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

    def test_patch_schedule_time(self, client, app, admin_auth_headers):
        _reset_hr_job(app, schedule_hour=20, schedule_minute=0)
        response = client.patch(
            f'/automations/api/jobs/{HR_DAILY_EXCEL}',
            json={'schedule_hour': 8, 'schedule_minute': 30},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200, response.get_json()
        job = response.get_json()['job']
        assert job['schedule_hour'] == 8
        assert job['schedule_minute'] == 30

    def test_list_includes_hr_module_choices(self, client, admin_auth_headers):
        response = client.get('/automations/api/jobs', headers=admin_auth_headers)
        jobs = {row['slug']: row for row in response.get_json()['jobs']}
        hr = jobs[HR_DAILY_EXCEL]
        assert hr['export_modules'] == ['hiring', 'leave', 'manpower']
        assert [row['id'] for row in hr['module_choices']] == ['hiring', 'leave', 'manpower']

    def test_patch_export_modules(self, client, app, admin_auth_headers):
        _reset_hr_job(app)
        response = client.patch(
            f'/automations/api/jobs/{HR_DAILY_EXCEL}',
            json={'export_modules': ['hiring', 'leave']},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200, response.get_json()
        job = response.get_json()['job']
        assert job['export_modules'] == ['hiring', 'leave']

    def test_patch_export_modules_rejects_empty(self, client, app, admin_auth_headers):
        _reset_hr_job(app)
        response = client.patch(
            f'/automations/api/jobs/{HR_DAILY_EXCEL}',
            json={'export_modules': []},
            headers=admin_auth_headers,
        )
        assert response.status_code == 400


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
        assert email['outcome'] == 'sent'
        assert email['recipients'] == ['backup@example.com']
        assert email['subject'].startswith('HR daily backup')
        assert len(email.get('attachment_names') or []) == 3
        assert data['run']['view']['email']['line'].startswith('Sent to backup@example.com')
        send_email.assert_called_once()
        args, kwargs = send_email.call_args
        assert args[0] == ['backup@example.com']
        assert kwargs.get('source') == 'hr'
        assert kwargs.get('related_id') == f"automation_run:{data['run']['id']}"
        html = kwargs.get('html_body') or ''
        assert 'HR daily backup' in html
        assert 'Hiring' in html
        assert 'Leave' in html
        assert 'Manpower' in html
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
        assert data['run']['detail']['email']['recipients'] == ['backup@example.com']
        assert data['run']['detail']['email']['outcome'] == 'skipped'
        send_email.assert_not_called()

    def test_run_now_email_has_excel_only(self, client, app, admin_auth_headers):
        _reset_hr_job(app, to_emails='backup@example.com')
        with patch('app.automations.runner.is_email_configured', return_value=True), \
             patch('app.automations.runner.send_email', return_value=True) as send_email, \
             patch('app.automations.hr_snapshot_pdf.build_hr_ui_snapshot_pdf') as snapshot, \
             patch('module_files.drive_service.sync_item'):
            response = client.post(
                f'/automations/api/jobs/{HR_DAILY_EXCEL}/run',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['status'] == 'ok'
        names = {row['filename'] for row in data['run']['detail']['files']}
        assert all(name.endswith('.xlsx') for name in names)
        assert not any(name.endswith('.pdf') for name in names)
        snapshot.assert_not_called()
        attached = send_email.call_args.kwargs.get('attachments') or []
        assert attached
        assert all(str(a.get('filename') or '').endswith('.xlsx') for a in attached)
        html = send_email.call_args.kwargs.get('html_body') or ''
        assert 'PDF' not in html

    def test_run_now_respects_selected_modules(self, client, app, admin_auth_headers):
        _reset_hr_job(app, to_emails='backup@example.com', export_modules='hiring')
        with patch('app.automations.runner.is_email_configured', return_value=True), \
             patch('app.automations.runner.send_email', return_value=True) as send_email, \
             patch('app.automations.hr_snapshot_pdf.build_hr_ui_snapshot_pdf') as snapshot, \
             patch('module_files.drive_service.sync_item'):
            response = client.post(
                f'/automations/api/jobs/{HR_DAILY_EXCEL}/run',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        names = {row['filename'] for row in data['run']['detail']['files']}
        day = _dubai_today()
        assert f'Hiring_Export_{day}.xlsx' in names
        assert f'Leave_Tracker_Export_{day}.xlsx' not in names
        assert f'Manpower_Export_{day}.xlsx' not in names
        assert not any(name.endswith('.pdf') for name in names)
        snapshot.assert_not_called()
        html = send_email.call_args.kwargs.get('html_body') or ''
        assert 'Hiring' in html
        assert 'Manpower' not in html

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


class TestHrUiSnapshotPdf:
    def test_snapshot_pages_filter_by_module(self):
        from app.automations.hr_snapshot_pdf import snapshot_pages_for_modules

        pages = snapshot_pages_for_modules(['hiring'])
        assert pages
        assert all(p['module'] == 'hiring' for p in pages)
        mixed = snapshot_pages_for_modules(['hiring', 'manpower'])
        assert {p['module'] for p in mixed} == {'hiring', 'manpower'}
        assert all('leave' not in p['key'] for p in mixed)
        assert snapshot_pages_for_modules([]) == snapshot_pages_for_modules(None)

    def test_snapshot_disabled_in_testing(self):
        from app.automations.hr_snapshot_pdf import snapshot_enabled

        assert snapshot_enabled() is False

    def test_compose_snapshot_pdf_has_cover_and_module_pages(self):
        from io import BytesIO

        from PIL import Image
        from pypdf import PdfReader

        from app.automations.hr_snapshot_pdf import compose_snapshot_pdf

        def _png(color):
            image = Image.new('RGB', (1600, 1000), color)
            buf = BytesIO()
            image.save(buf, format='PNG')
            return buf.getvalue()

        pdf = compose_snapshot_pdf(
            [
                {'key': 'hiring', 'title': 'Hiring — Documents', 'subtitle': 'Onboarding', 'png': _png((255, 142, 104))},
                {'key': 'leave', 'title': 'Leave Tracker', 'subtitle': 'Sick & annual', 'png': _png((250, 250, 251))},
                {'key': 'manpower', 'title': 'Manpower Tracker', 'subtitle': 'Vacancies', 'png': _png((25, 27, 35))},
            ],
            day='2026-08-27',
            tz_label='GST',
        )
        assert pdf.startswith(b'%PDF')
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 4
        text = '\n'.join((page.extract_text() or '') for page in reader.pages)
        assert 'Daily snapshot' in text
        assert 'Hiring' in text
        assert 'Leave Tracker' in text
        assert 'Manpower Tracker' in text

    def test_compose_splits_tall_screenshot_across_pages(self):
        from io import BytesIO

        from PIL import Image
        from pypdf import PdfReader

        from app.automations.hr_snapshot_pdf import compose_snapshot_pdf

        image = Image.new('RGB', (1600, 5000), (250, 250, 251))
        buf = BytesIO()
        image.save(buf, format='PNG')
        pdf = compose_snapshot_pdf(
            [{'key': 'leave_sick', 'group': 'Leave', 'title': 'Leave Tracker — Sick Leave',
              'subtitle': 'Excel: Sick Leave', 'png': buf.getvalue()}],
            day='2026-08-27',
            tz_label='GST',
        )
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) >= 3
        text = '\n'.join((page.extract_text() or '') for page in reader.pages)
        assert '1 of ' in text


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

    def test_catchup_records_error_when_run_job_raises(self, app):
        from app.automations.runner import run_catchup

        _reset_hr_job(app, last_success_at=None, schedule_hour=0, schedule_minute=0)
        with app.app_context():
            with patch(
                'app.automations.runner.run_job',
                side_effect=RuntimeError("Can't reconnect until invalid transaction is rolled back"),
            ):
                results = run_catchup()
        assert results[0]['status'] == 'error'
        assert results[0]['slug'] == HR_DAILY_EXCEL
        assert 'reconnect' in results[0]['message']

    def test_catchup_runs_when_not_succeeded_today(self, app):
        from app.automations.runner import run_catchup

        yesterday = datetime.now(ZoneInfo('Asia/Dubai')) - timedelta(days=1)
        _reset_hr_job(
            app,
            last_success_at=yesterday.astimezone(timezone.utc).replace(tzinfo=None),
            schedule_hour=0,
            schedule_minute=0,
        )
        with app.app_context():
            with patch('app.automations.runner.is_email_configured', return_value=True), \
                 patch('app.automations.runner.send_email', return_value=True), \
                 patch('module_files.drive_service.sync_item'):
                results = run_catchup()
        assert results[0]['status'] in ('ok', 'warning')
        assert results[0]['run']['trigger'] == 'catchup'
        assert len(results[0]['run']['detail']['files']) == 3

    def test_catchup_skips_before_scheduled_time(self, app):
        from app.automations.runner import run_catchup

        now = datetime(2026, 9, 3, 10, 0, tzinfo=ZoneInfo('Asia/Dubai'))
        _reset_hr_job(app, last_success_at=None, schedule_hour=11, schedule_minute=10)
        with app.app_context():
            with patch('app.automations.runner.run_job') as run_job:
                results = run_catchup(now_local=now)
            run_job.assert_not_called()
        assert results[0]['status'] == 'skipped'
        assert 'Not due' in results[0]['message']

    def test_tick_uses_scheduler_trigger_on_scheduled_minute(self, app):
        from app.automations.runner import run_scheduler_tick

        now = datetime(2026, 9, 3, 11, 10, 20, tzinfo=ZoneInfo('Asia/Dubai'))
        _reset_hr_job(app, last_success_at=None, schedule_hour=11, schedule_minute=10)
        with app.app_context():
            with patch('app.automations.runner.run_job', return_value={'slug': HR_DAILY_EXCEL, 'status': 'ok'}) as run_job:
                results = run_scheduler_tick(now_local=now)
        run_job.assert_called_once_with(HR_DAILY_EXCEL, trigger='scheduler')
        assert results[0]['status'] == 'ok'

    def test_tick_catchup_after_scheduled_minute_if_missed(self, app):
        from app.automations.runner import run_scheduler_tick

        now = datetime(2026, 9, 3, 12, 6, tzinfo=ZoneInfo('Asia/Dubai'))
        _reset_hr_job(app, last_success_at=None, schedule_hour=11, schedule_minute=10)
        with app.app_context():
            with patch('app.automations.runner.run_job', return_value={'slug': HR_DAILY_EXCEL, 'status': 'ok'}) as run_job:
                run_scheduler_tick(now_local=now)
        run_job.assert_called_once_with(HR_DAILY_EXCEL, trigger='catchup')

    def test_tick_skips_when_already_succeeded(self, app):
        from app.automations.runner import run_scheduler_tick

        now = datetime(2026, 9, 3, 12, 6, tzinfo=ZoneInfo('Asia/Dubai'))
        _reset_hr_job(
            app,
            last_success_at=datetime(2026, 9, 3, 11, 10, tzinfo=timezone.utc).replace(tzinfo=None),
            schedule_hour=11,
            schedule_minute=10,
        )
        with app.app_context():
            with patch('app.automations.runner.run_job') as run_job:
                results = run_scheduler_tick(now_local=now)
            run_job.assert_not_called()
        assert results[0]['status'] == 'skipped'

    def test_scheduler_not_started_in_testing(self, app):
        from app.automations import scheduler as automations_scheduler

        assert automations_scheduler._scheduler is None
        automations_scheduler.init_scheduler(app)
        assert automations_scheduler._scheduler is None


class TestRunRecordAndDetailApi:
    def test_email_off_records_recipients_status_ok(self, client, app, admin_auth_headers):
        _reset_hr_job(app, to_emails='me@example.com', send_email=False)
        with patch('app.automations.runner.is_email_configured', return_value=True), \
             patch('app.automations.runner.send_email') as send_email:
            response = client.post(
                f'/automations/api/jobs/{HR_DAILY_EXCEL}/run',
                headers=admin_auth_headers,
            )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['status'] == 'ok'
        email = data['run']['detail']['email']
        assert email['reason'] == 'send_email_off'
        assert email['outcome'] == 'skipped'
        assert email['recipients'] == ['me@example.com']
        assert data['run']['view']['email']['line'] == 'Email off'
        send_email.assert_not_called()

    def test_list_normalizes_legacy_run_detail(self, client, app, admin_auth_headers):
        from app.models import AutomationJob, AutomationRun, db

        _reset_hr_job(app)
        with app.app_context():
            job = AutomationJob.query.filter_by(slug=HR_DAILY_EXCEL).first()
            run = AutomationRun(
                job_id=job.id,
                trigger='manual',
                status='ok',
                detail={
                    'files': [{'filename': 'Hiring_Export_2026-08-22.xlsx', 'item_id': 1}],
                    'email': {
                        'sent': True,
                        'skipped': False,
                        'recipients': ['old@example.com'],
                    },
                    'warnings': [],
                    'dubai_date': '2026-08-22',
                },
            )
            db.session.add(run)
            db.session.commit()
            run_id = run.id
        listed = client.get('/automations/api/jobs', headers=admin_auth_headers).get_json()
        row = next(item for item in listed['runs'] if item['id'] == run_id)
        assert row['view']['email']['outcome'] == 'sent'
        assert row['view']['email']['recipients'] == ['old@example.com']
        assert row['view']['email']['line'] == 'Sent to old@example.com'
        assert row['view']['files'][0]['download_url'] == '/files/api/items/1/download'

    def test_get_run_detail_includes_email_log(self, client, app, admin_auth_headers):
        from app.automations.run_record import related_id_for_run
        from app.models import AutomationJob, AutomationRun, EmailLog, db

        _reset_hr_job(app)
        with app.app_context():
            job = AutomationJob.query.filter_by(slug=HR_DAILY_EXCEL).first()
            run = AutomationRun(
                job_id=job.id,
                trigger='manual',
                status='ok',
                detail={
                    'files': [{'filename': 'Hiring_Export_2026-08-24.xlsx', 'item_id': 9}],
                    'email': {
                        'sent': True,
                        'skipped': False,
                        'recipients': ['ops@example.com'],
                        'subject': 'HR daily backup — 2026-08-24',
                    },
                    'warnings': [],
                    'dubai_date': '2026-08-24',
                },
            )
            db.session.add(run)
            db.session.commit()
            related_id = related_id_for_run(run.id)
            email = dict((run.detail or {}).get('email') or {})
            email['related_id'] = related_id
            detail = dict(run.detail or {})
            detail['email'] = email
            run.detail = detail
            db.session.add(EmailLog(
                status='sent',
                source='hr',
                subject='HR daily backup — 2026-08-24',
                to_emails='ops@example.com',
                related_id=related_id,
                attachment_count=3,
            ))
            db.session.commit()
            run_id = run.id
        response = client.get(f'/automations/api/runs/{run_id}', headers=admin_auth_headers)
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body['run']['view']['email']['recipients'] == ['ops@example.com']
        assert body['run']['view']['email_log']['status'] == 'sent'
        assert body['run']['view']['email_log']['related_id'] == f'automation_run:{run_id}'

    def test_get_run_forbidden_for_plain_user(self, client, auth_headers):
        response = client.get('/automations/api/runs/1', headers=auth_headers)
        assert response.status_code == 403

    def test_get_run_missing(self, client, admin_auth_headers):
        response = client.get('/automations/api/runs/999999', headers=admin_auth_headers)
        assert response.status_code == 404
