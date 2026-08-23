"""Integration tests for module_inspection/routes.py (Inspection blueprint).

Style follows tests/test_ticket_geocode.py and tests/test_technician_login.py:
class-per-concern, hitting the live Flask routes through the `client` test
client, using the shared fixtures from tests/conftest.py.

## The async ThreadPoolExecutor seam

`/inspection/submit` and `/inspection/submit-with-urls` hand report generation
to an executor (`module_inspection.routes.get_paths()` returns
`current_app.config.get("EXECUTOR")` if the app config has one, else falls
back to the module-level `_FALLBACK_EXECUTOR` — a live `ThreadPoolExecutor`).
Two things make that unsuitable to exercise for real inside a test:

1. It would spawn a background thread; with the test app using
   ``sqlite:///:memory:`` (SQLAlchemy's `SingletonThreadPool` for that URI
   keys the one shared connection off the *thread id*), a worker thread would
   see a **different, empty** in-memory database, well before we even get to
   worrying about slow/flaky sleep-and-poll tests.
2. The real worker (`process_job` -> `common.module_base.process_report_job`)
   generates actual Excel/PDF reports and may attempt Cloudinary/network I/O
   — exactly what we must not do in a test.

So the `synchronous_inspection_job` fixture below patches two seams:

- `current_app.config['EXECUTOR']` -> a tiny in-process `ImmediateExecutor`
  whose `.submit(fn, *a, **kw)` just calls `fn(*a, **kw)` synchronously, on
  the *same* thread as the test, and returns an already-resolved
  `concurrent.futures.Future`. This is exactly the seam `get_paths()` already
  exposes (`app.config.get("EXECUTOR")`), so no monkeypatching of the
  ThreadPoolExecutor object itself is needed.
- `module_inspection.routes.process_job` -> a lightweight stand-in that marks
  the job complete via the real `complete_job_db` (imported into the routes
  module already) with fake report URLs, instead of running the real
  Excel/PDF generation pipeline.

Both patches go through `monkeypatch`, so teardown/restoration is automatic
and no background thread is ever left running between tests.
"""
import io
from concurrent.futures import Future
from datetime import datetime, timezone

import pytest

from module_inspection import routes as insp_routes


def _today_str():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def inspection_tmp_dirs(monkeypatch, app, tmp_path):
    """Redirect GENERATED_DIR/UPLOADS_DIR/JOBS_DIR to a throwaway tmp_path
    for the duration of a test, instead of writing into the repo's real
    (gitignored) generated/ folder."""
    gen_dir = tmp_path / 'generated'
    uploads_dir = gen_dir / 'uploads'
    jobs_dir = gen_dir / 'jobs'
    for d in (gen_dir, uploads_dir, jobs_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setitem(app.config, 'GENERATED_DIR', str(gen_dir))
    monkeypatch.setitem(app.config, 'UPLOADS_DIR', str(uploads_dir))
    monkeypatch.setitem(app.config, 'JOBS_DIR', str(jobs_dir))
    yield {'GENERATED_DIR': str(gen_dir), 'UPLOADS_DIR': str(uploads_dir), 'JOBS_DIR': str(jobs_dir)}


@pytest.fixture
def synchronous_inspection_job(monkeypatch, app):
    """See module docstring: makes /submit and /submit-with-urls process
    their background job inline, synchronously, without a real executor
    thread or real report generation."""

    class ImmediateExecutor:
        def submit(self, fn, *args, **kwargs):
            future = Future()
            try:
                future.set_result(fn(*args, **kwargs))
            except Exception as exc:  # pragma: no cover - defensive
                future.set_exception(exc)
            return future

    monkeypatch.setitem(app.config, 'EXECUTOR', ImmediateExecutor())

    def _fake_process_job(sub_id, job_id, config, flask_app):
        with flask_app.app_context():
            insp_routes.complete_job_db(job_id, {
                'excel': 'https://example.com/fake_report.xlsx',
                'excel_filename': 'fake_report.xlsx',
                'pdf': 'https://example.com/fake_report.pdf',
                'pdf_filename': 'fake_report.pdf',
            })

    monkeypatch.setattr(insp_routes, 'process_job', _fake_process_job)
    yield


@pytest.fixture
def fake_cloud_upload(monkeypatch):
    """Stand in for common.utils.save_uploaded_file_cloud so /upload-photo
    never attempts a real Cloudinary/network call."""

    def _fake_upload(file_storage, uploads_dir, folder="uploads"):
        return {
            'url': f'https://fake-cdn.example.com/{folder}/{file_storage.filename}',
            'public_id': 'fake_public_id',
            'is_cloud': True,
            'filename': file_storage.filename,
        }

    monkeypatch.setattr(insp_routes, 'save_uploaded_file_cloud', _fake_upload)
    yield _fake_upload


@pytest.fixture
def inspection_cleanup(app):
    """Track DB rows created ad-hoc by a test and remove them on teardown so
    the session-scoped `app`/DB stays clean for other tests in the run."""
    ids = {'jobs': [], 'submissions': [], 'users': []}
    yield ids
    from app.models import db, Job, Submission, User
    with app.app_context():
        for job_id in ids['jobs']:
            j = Job.query.filter_by(job_id=job_id).first()
            if j:
                db.session.delete(j)
        for sub_id in ids['submissions']:
            s = Submission.query.filter_by(submission_id=sub_id).first()
            if s:
                db.session.delete(s)
        for uid in ids['users']:
            u = db.session.get(User, uid)
            if u:
                db.session.delete(u)
        db.session.commit()


# ---------------------------------------------------------------------------
# Authentication gate
# ---------------------------------------------------------------------------

class TestAuthRequired:
    """All /inspection/* routes require @jwt_required(). Unlike ticketing's
    /tickets/api/... routes (which return 401/422 JSON because they contain
    '/api/' in the path), Injaaz.py's `_is_html_page_request()` treats any
    path *without* '/api/' as an HTML page navigation (Injaaz.py:246-258).
    Since every /inspection/... route is registered without '/api/' in its
    path, a missing/invalid JWT hits `unauthorized_callback` /
    `invalid_token_callback` (Injaaz.py:281-293), which — finding no refresh
    cookie either — redirects to the login page with 302, instead of
    returning a 401/422 JSON error. That is real, deliberate app-wide
    behavior (not a bug in module_inspection), so these tests assert the
    actual 302 redirect rather than a JSON 401/422.
    """

    def test_dropdowns_requires_auth(self, client):
        response = client.get('/inspection/dropdowns')
        assert response.status_code == 302

    def test_submit_requires_auth(self, client):
        response = client.post('/inspection/submit', data={'site_name': 'X'})
        assert response.status_code == 302

    def test_status_requires_auth(self, client):
        response = client.get('/inspection/status/job_doesnotexist')
        assert response.status_code == 302

    def test_upload_photo_requires_auth(self, client):
        response = client.post('/inspection/upload-photo', data={})
        assert response.status_code == 302

    def test_save_draft_requires_auth(self, client):
        response = client.post('/inspection/save-draft', json={'foo': 'bar'})
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# GET /inspection/dropdowns
# ---------------------------------------------------------------------------

class TestDropdowns:
    def test_returns_dropdown_data(self, client, auth_headers):
        response = client.get('/inspection/dropdowns', headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, dict)
        # dropdown_data.json ships with a fixed set of category keys.
        assert 'HVAC' in data


# ---------------------------------------------------------------------------
# POST /inspection/save-draft
# ---------------------------------------------------------------------------

class TestSaveDraft:
    def test_creates_draft(self, client, auth_headers, inspection_tmp_dirs):
        response = client.post(
            '/inspection/save-draft',
            headers=auth_headers,
            json={'site_name': 'Draft Site', 'items': []},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
        assert data['draft_id'].startswith('draft_')
        import os
        draft_path = os.path.join(inspection_tmp_dirs['GENERATED_DIR'], 'drafts', f"{data['draft_id']}.json")
        assert os.path.exists(draft_path)


# ---------------------------------------------------------------------------
# POST /inspection/submit
# ---------------------------------------------------------------------------

class TestSubmit:
    def test_missing_site_name_returns_400(self, client, auth_headers, inspection_tmp_dirs):
        response = client.post(
            '/inspection/submit',
            headers=auth_headers,
            data={'visit_date': _today_str()},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'site name' in data['error'].lower()

    def test_invalid_date_format_returns_400(self, client, auth_headers, inspection_tmp_dirs):
        response = client.post(
            '/inspection/submit',
            headers=auth_headers,
            data={'site_name': 'Bad Date Site', 'visit_date': 'not-a-date'},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'date' in data['error'].lower()

    def test_happy_path_returns_job_that_completes(
        self, client, admin_auth_headers, inspection_tmp_dirs, synchronous_inspection_job, inspection_cleanup,
    ):
        response = client.post(
            '/inspection/submit',
            headers=admin_auth_headers,
            data={
                'site_name': 'HVAC Site Test',
                'visit_date': _today_str(),
                'items_count': '0',
                'category': 'HVAC',
            },
        )
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['status'] == 'queued'
        assert data['job_id']
        assert data['submission_id']
        inspection_cleanup['submissions'].append(data['submission_id'])
        inspection_cleanup['jobs'].append(data['job_id'])

        # Because the executor ran synchronously (see synchronous_inspection_job),
        # the job is already in a terminal state by the time we poll — no
        # sleep loop needed.
        status_response = client.get(f"/inspection/status/{data['job_id']}", headers=admin_auth_headers)
        assert status_response.status_code == 200
        status_data = status_response.get_json()
        assert status_data['status'] == 'completed'
        assert status_data['progress'] == 100
        assert status_data['result_data']['pdf'] == 'https://example.com/fake_report.pdf'
        assert status_data['result_data']['excel'] == 'https://example.com/fake_report.xlsx'


# ---------------------------------------------------------------------------
# GET /inspection/status/<job_id>
# ---------------------------------------------------------------------------

class TestStatus:
    def test_unknown_job_returns_404(self, client, auth_headers):
        response = client.get('/inspection/status/job_does_not_exist_123', headers=auth_headers)
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False


# ---------------------------------------------------------------------------
# Download routes
# ---------------------------------------------------------------------------

class TestDownload:
    def test_download_file_unknown_job_returns_404(self, client, auth_headers):
        response = client.get('/inspection/download/job_does_not_exist_123/pdf', headers=auth_headers)
        assert response.status_code == 404

    def test_download_by_submission_invalid_file_type_returns_400(self, client, auth_headers):
        response = client.get('/inspection/download/submission/sub_does_not_exist/txt', headers=auth_headers)
        assert response.status_code == 400

    def test_download_by_submission_not_ready_returns_404(self, client, admin_auth_headers, app, inspection_cleanup):
        with app.app_context():
            submission = insp_routes.create_submission_db(
                module_type='inspection',
                form_data={'site_name': 'No Report Yet', 'visit_date': _today_str(), 'items': []},
                site_name='No Report Yet',
                visit_date=_today_str(),
            )
            sub_id = submission.submission_id
        inspection_cleanup['submissions'].append(sub_id)

        response = client.get(f'/inspection/download/submission/{sub_id}/pdf', headers=admin_auth_headers)
        assert response.status_code == 404

    def test_download_local_pdf_and_excel_magic_bytes(
        self, client, admin_auth_headers, app, inspection_tmp_dirs, inspection_cleanup,
    ):
        """Real builder output served through GET /inspection/download/<job>/pdf|excel."""
        import os

        from module_inspection.inspection_generators import create_excel_report, create_pdf_report

        gen_dir = inspection_tmp_dirs['GENERATED_DIR']
        sample = {
            'site_name': 'HTTP Download Site',
            'visit_date': _today_str(),
            'items': [{'asset': 'AHU-01', 'system': 'HVAC', 'description': 'Filter check'}],
        }
        pdf_path = create_pdf_report(sample, gen_dir)
        xls_path = create_excel_report(sample, gen_dir)
        pdf_name = os.path.basename(pdf_path)
        xls_name = os.path.basename(xls_path)

        with app.app_context():
            submission = insp_routes.create_submission_db(
                module_type='inspection',
                form_data=sample,
                site_name=sample['site_name'],
                visit_date=sample['visit_date'],
            )
            job = insp_routes.create_job_db(submission)
            insp_routes.complete_job_db(job.job_id, {
                'pdf': f'http://127.0.0.1/generated/{pdf_name}',
                'pdf_filename': pdf_name,
                'excel': f'http://127.0.0.1/generated/{xls_name}',
                'excel_filename': xls_name,
            })
            job_id = job.job_id
            sub_id = submission.submission_id
        inspection_cleanup['jobs'].append(job_id)
        inspection_cleanup['submissions'].append(sub_id)

        pdf_resp = client.get(f'/inspection/download/{job_id}/pdf', headers=admin_auth_headers)
        assert pdf_resp.status_code == 200, pdf_resp.get_json()
        assert pdf_resp.data[:4] == b'%PDF'

        xls_resp = client.get(f'/inspection/download/{job_id}/excel', headers=admin_auth_headers)
        assert xls_resp.status_code == 200, xls_resp.get_json()
        assert xls_resp.data[:2] == b'PK'

        via_sub = client.get(f'/inspection/download/submission/{sub_id}/pdf', headers=admin_auth_headers)
        assert via_sub.status_code in (200, 302)



# ---------------------------------------------------------------------------
# POST /inspection/upload-photo
# ---------------------------------------------------------------------------

class TestUploadPhoto:
    def test_missing_file_returns_400(self, client, auth_headers, inspection_tmp_dirs):
        response = client.post('/inspection/upload-photo', headers=auth_headers, data={})
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_happy_path_uploads_once(self, client, auth_headers, inspection_tmp_dirs, fake_cloud_upload):
        response = client.post(
            '/inspection/upload-photo',
            headers=auth_headers,
            data={'photo': (io.BytesIO(b'fake-image-bytes'), 'site.jpg')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['url'].startswith('https://fake-cdn.example.com/')
        assert data['filename'] == 'site.jpg'


# ---------------------------------------------------------------------------
# POST /inspection/submit-with-urls
# ---------------------------------------------------------------------------

class TestSubmitWithUrls:
    def test_happy_path_returns_job_that_completes(
        self, client, admin_auth_headers, inspection_tmp_dirs, synchronous_inspection_job, inspection_cleanup,
    ):
        payload = {
            'site_name': 'Pre-uploaded Photos Site',
            'visit_date': _today_str(),
            'category': 'HVAC',
            'items': [
                {
                    'asset': 'AC-Unit-1',
                    'system': 'HVAC',
                    'description': 'Rooftop condenser',
                    'photo_urls': ['https://cdn.example.com/photo1.jpg'],
                }
            ],
        }
        response = client.post('/inspection/submit-with-urls', headers=admin_auth_headers, json=payload)
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        assert data['status'] == 'ok'
        assert data['job_id']
        assert data['submission_id']
        inspection_cleanup['submissions'].append(data['submission_id'])
        inspection_cleanup['jobs'].append(data['job_id'])

        status_response = client.get(f"/inspection/status/{data['job_id']}", headers=admin_auth_headers)
        assert status_response.status_code == 200
        assert status_response.get_json()['status'] == 'completed'


# ---------------------------------------------------------------------------
# POST /inspection/add-photos-to-item
# ---------------------------------------------------------------------------

class TestAddPhotosToItem:
    def test_missing_fields_returns_400(self, client, auth_headers):
        response = client.post('/inspection/add-photos-to-item', headers=auth_headers, json={})
        assert response.status_code == 400

    def test_item_index_out_of_range_returns_400(self, client, admin_auth_headers, app, inspection_cleanup):
        with app.app_context():
            submission = insp_routes.create_submission_db(
                module_type='inspection',
                form_data={'site_name': 'No Items', 'visit_date': _today_str(), 'items': []},
                site_name='No Items',
                visit_date=_today_str(),
            )
            sub_id = submission.submission_id
        inspection_cleanup['submissions'].append(sub_id)

        response = client.post(
            '/inspection/add-photos-to-item',
            headers=admin_auth_headers,
            json={'submission_id': sub_id, 'item_index': 0, 'photo_urls': ['https://cdn.example.com/x.jpg']},
        )
        assert response.status_code == 400

    def test_happy_path_adds_photo_urls(self, client, admin_auth_headers, app, inspection_cleanup):
        with app.app_context():
            submission = insp_routes.create_submission_db(
                module_type='inspection',
                form_data={
                    'site_name': 'Has One Item',
                    'visit_date': _today_str(),
                    'items': [{'asset': 'AC-1', 'system': 'HVAC', 'description': 'Unit', 'photos': []}],
                },
                site_name='Has One Item',
                visit_date=_today_str(),
            )
            sub_id = submission.submission_id
        inspection_cleanup['submissions'].append(sub_id)

        response = client.post(
            '/inspection/add-photos-to-item',
            headers=admin_auth_headers,
            json={
                'submission_id': sub_id,
                'item_index': 0,
                'photo_urls': ['https://cdn.example.com/p1.jpg', 'https://cdn.example.com/p2.jpg'],
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['total_photos'] == 2
        assert len(data['photos']) == 2


# ---------------------------------------------------------------------------
# GET /inspection/ and GET /inspection/form
# ---------------------------------------------------------------------------

class TestDashboardAndForm:
    def test_dashboard_renders_for_user_with_access(self, client, admin_auth_headers):
        response = client.get('/inspection/', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_dashboard_without_access_hits_missing_redirect_import_bug(self, client, auth_headers):
        """KNOWN BUG: module_inspection/routes.py:184-194 `inspection_dashboard()`
        calls `redirect(...)` on the "no access" branch, but `redirect` is never
        imported at module scope in routes.py (only `Blueprint, current_app,
        render_template, request, jsonify, url_for, send_from_directory,
        send_file, Response` are imported at the top of the file, and `redirect`
        is only imported locally inside other view functions such as `index()`
        and `download_by_submission()`). For a user who lacks Inspection access
        (module_inspection/routes.py:192-193), this raises a NameError instead
        of redirecting, which Flask surfaces as a 500. This test documents the
        current (buggy) behavior rather than the intended one.
        """
        response = client.get('/inspection/', headers=auth_headers)
        assert response.status_code == 500

    def test_form_access_denied_for_user_without_access(self, client, auth_headers):
        response = client.get('/inspection/form', headers=auth_headers)
        assert response.status_code == 403

    def test_form_renders_for_admin(self, client, admin_auth_headers):
        response = client.get('/inspection/form', headers=admin_auth_headers)
        assert response.status_code == 200
