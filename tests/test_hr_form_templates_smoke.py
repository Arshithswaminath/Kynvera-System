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

# Admin can access HR queue pages (see module_hr.routes guards)
HR_ADMIN_PATHS = [
    "/hr/",
    "/hr/pending-review",
    "/hr/approved-forms",
    "/hr/gm-approval",
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


@pytest.mark.parametrize("path", HR_ADMIN_PATHS)
def test_hr_admin_pages_return_html(client, admin_auth_headers, path):
    r = client.get(path, headers=admin_auth_headers)
    assert r.status_code == 200, f"{path}: {r.status_code}"
    body = r.data.lower()
    assert b"<html" in body or b"<!doctype" in body, f"{path}: expected HTML document"
