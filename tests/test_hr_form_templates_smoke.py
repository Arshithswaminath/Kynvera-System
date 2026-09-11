"""
Smoke: authenticated GET on every HR HTML template route returns 200 and HTML.

Uses in-memory test DB + JWT (see conftest). Complements:
  - pytest tests/test_hr_pdf_all_forms.py (PDF bytes)
  - python scripts/test_all_hr_forms.py --pdf-only (batch PDF files)
  - scripts/hr_ui_three_role_screenshots.py (Playwright against a running server + real users)
"""
from __future__ import annotations

import pytest

# JWT-only form pages (any logged-in user)
HR_FORM_PATHS = [
    "/hr/my-requests",
    "/hr/leave-application-form",
    "/hr/commencement-form",
    "/hr/duty-resumption-form",
    "/hr/contract-renewal-form",
    "/hr/performance-evaluation-form",
    "/hr/grievance-form",
    "/hr/interview-assessment-form",
    "/hr/passport-release-form",
    "/hr/staff-appraisal-form",
    "/hr/station-clearance-form",
    "/hr/visa-renewal-form",
    "/hr/asset-handover-form",
]

HR_FILL_FORM_PATHS = [p for p in HR_FORM_PATHS if p != "/hr/my-requests"]

# Admin can access HR queue pages (see module_hr.routes guards)
HR_ADMIN_PATHS = [
    "/hr/",
    "/hr/pending-review",
    "/hr/approved-forms",
    "/hr/gm-approval",
    "/hr/staffing-assignments",
]


@pytest.mark.parametrize("path", HR_FORM_PATHS)
def test_hr_form_template_returns_html(client, auth_headers, path):
    r = client.get(path, headers=auth_headers)
    assert r.status_code == 200, f"{path}: {r.status_code}"
    body = r.data.lower()
    assert b"<html" in body or b"<!doctype" in body, f"{path}: expected HTML document"


def test_hr_root_redirects_employee_to_my_requests(client, auth_headers):
    """Non-HR users hitting /hr/ are redirected to My Requests."""
    r = client.get("/hr/", headers=auth_headers, follow_redirects=True)
    assert r.status_code == 200
    path = (r.request.path or "").lower()
    assert "my-requests" in path or "request" in r.data.decode("utf-8", errors="ignore").lower()


def test_my_requests_page_is_inbox_not_hub(client, admin_auth_headers):
    r = client.get("/hr/my-requests", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "<title>My Requests" in body
    assert "My submitted requests" in body
    assert "Start a new request" in body


def test_hr_hub_leave_and_manpower_are_not_hiring_kickers(client, admin_auth_headers):
    r = client.get("/hr/", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Hiring &mdash; Leave" not in body
    assert "Hiring &mdash; Manpower" not in body
    assert "Leave &mdash; Tracker" in body
    assert "Manpower &mdash; Board" in body


def test_staffing_assignments_renders_own_page(client, admin_auth_headers):
    r = client.get("/hr/staffing-assignments", headers=admin_auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Staffing Assignments" in body
    assert '<h1 class="hh-title">Staffing Assignments</h1>' in body


@pytest.mark.parametrize("path", HR_ADMIN_PATHS)
def test_hr_admin_pages_return_html(client, admin_auth_headers, path):
    r = client.get(path, headers=admin_auth_headers)
    assert r.status_code == 200, f"{path}: {r.status_code}"
    body = r.data.lower()
    assert b"<html" in body or b"<!doctype" in body, f"{path}: expected HTML document"


@pytest.mark.parametrize("path", HR_FILL_FORM_PATHS)
def test_hr_form_shows_signatures_required(client, auth_headers, path):
    r = client.get(path, headers=auth_headers)
    assert r.status_code == 200, path
    body = r.data.decode("utf-8", errors="ignore")
    assert "Signatures required" in body
    assert 'id="hrSigRequiredBanner"' in body


def test_duty_resumption_employee_cannot_open_rm_gm_hr_pads(client, auth_headers):
    r = client.get("/hr/duty-resumption-form", headers=auth_headers)
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "openSig('employee')" in body
    assert "openSig('rm')" not in body
    assert "openSig('gm')" not in body
    assert "openSig('hr')" not in body
    assert "Signs later in the approval chain" in body
    assert "No signature yet" in body
    assert 'duty-submit-outside-form' not in body
    assert 'id="submitBar"' in body
    submit_idx = body.find('id="submitBar"')
    card_idx = body.find('class="card"')
    card_close_after = body.find("</form>", submit_idx)
    assert card_idx != -1 and submit_idx != -1
    assert submit_idx < card_close_after
