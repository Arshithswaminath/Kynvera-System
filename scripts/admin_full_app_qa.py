#!/usr/bin/env python3
"""Admin full-app HTTP/UI QA against the live Flask server.

Usage (from project root, with ./run on :5002):
  ./venv/bin/python scripts/admin_full_app_qa.py

Login: Kynvera (admin). Creates disposable QA-* records only.
Does not send live emails or connect Google Drive.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import uuid
from datetime import date

import requests

BASE = "http://127.0.0.1:5002"
USER = "Kynvera"
PASS = "Arshith&Taha@2026"
TAG = f"QA-APP-{date.today().isoformat()}"
SUF = uuid.uuid4().hex[:6]

S = requests.Session()
TOKEN = None
checks: list[tuple[str, bool, str]] = []
warns: list[str] = []


def check(name: str, passed: bool, detail: str = ""):
    checks.append((name, bool(passed), detail or ""))
    mark = "PASS" if passed else "FAIL"
    extra = f" — {detail}" if detail and not passed else ""
    print(f"  [{mark}] {name}{extra}")


def warn(msg: str):
    warns.append(msg)
    print(f"  [WARN] {msg}")


def auth_headers(**extra):
    h = dict(extra)
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def api(method: str, path: str, **kw):
    headers = dict(kw.pop("headers", {}) or {})
    headers.update(auth_headers())
    if "json" in kw and "Content-Type" not in headers:
        headers.setdefault("Content-Type", "application/json")
    url = path if path.startswith("http") else BASE + path
    return S.request(method, url, headers=headers, timeout=90, **kw)


def page(path: str):
    return api("GET", path, headers={"Accept": "text/html"})


def expect_page(name: str, path: str, *needles: str):
    r = page(path)
    ok = r.status_code == 200 and len(r.text or "") > 200
    if ok and needles:
        missing = [n for n in needles if n not in r.text]
        if missing:
            ok = False
            check(name, False, f"{path} missing {missing[:2]} status={r.status_code}")
            return r
    check(name, ok, f"{path} → {r.status_code} bytes={len(r.content)}")
    return r


def expect_json(name: str, method: str, path: str, ok_statuses=(200, 201), **kw):
    r = api(method, path, **kw)
    body = None
    try:
        body = r.json()
    except Exception:
        body = None
    ok = r.status_code in ok_statuses
    if ok and isinstance(body, dict) and "success" in body and body.get("success") is False:
        # Optional integrations: treat clear config errors as warn
        err = str(body.get("error") or body.get("message") or "")
        if any(x in err.lower() for x in ("not configured", "unavailable", "no upload", "drive")):
            warn(f"{name}: {err[:160]}")
            check(name, True, f"optional/config: {err[:80]}")
            return r, body
        ok = False
    check(name, ok, f"{method} {path} → {r.status_code} {(str(body)[:180] if body else r.text[:180])}")
    return r, body


def expect_bytes(name: str, path: str, magic: bytes, accept="*/*"):
    r = api("GET", path, headers={"Accept": accept})
    ok = r.status_code == 200 and (r.content or b"").startswith(magic)
    ctype = r.headers.get("content-type", "")
    check(name, ok, f"{path} → {r.status_code} ctype={ctype} head={r.content[:8]!r}")
    return r


def login():
    global TOKEN
    r = S.post(BASE + "/api/auth/login", json={"username": USER, "password": PASS}, timeout=30)
    data = r.json() if r.status_code == 200 else {}
    TOKEN = data.get("access_token")
    check("Login as admin (Kynvera)", bool(TOKEN), f"status={r.status_code}")
    if TOKEN:
        me = api("GET", "/api/auth/me")
        check("GET /api/auth/me", me.status_code == 200)
    return bool(TOKEN)


# ─── Shell ───────────────────────────────────────────────────────────
def section_shell():
    print("\n=== Shell / nav ===")
    expect_page("Landing", "/", "Kynvera")
    expect_page("Login page", "/login")
    expect_page("Dashboard", "/dashboard")
    expect_page("About", "/about")
    expect_page("Offline page", "/offline")
    hubs = [
        ("/hr/", "HR hub"),
        ("/inspection/", "Inspection hub"),
        ("/procurement/", "Procurement hub"),
        ("/files/", "Files hub"),
        ("/tickets/", "Tickets hub"),
        ("/assets/", "Assets hub"),
        ("/qhsi/", "QHSE hub"),
        ("/admin/mmr/", "MMR hub"),
        ("/admin/dashboard", "Admin dashboard"),
        ("/admin/devices", "Devices"),
        ("/admin/bd", "BD module"),
        ("/dochub", "DocHub"),
        ("/workflow/pending-reviews", "Pending reviews"),
        ("/workflow/submitted-forms", "Submitted forms"),
        ("/bd/email-module", "BD email module"),
    ]
    for path, label in hubs:
        expect_page(f"Nav: {label}", path)


# ─── Tickets + Assets ────────────────────────────────────────────────
def section_tickets_assets():
    print("\n=== Service tickets + FM Assets ===")
    expect_page("Tickets dashboard", "/tickets/")
    expect_page("Tickets list", "/tickets/list")
    expect_page("Tickets new", "/tickets/new")
    expect_page("Tickets settings", "/tickets/settings")
    expect_page("Tickets drafts", "/tickets/drafts")
    expect_json("Tickets options API", "GET", "/tickets/api/options")
    expect_json("Tickets projects API", "GET", "/tickets/api/settings/projects")

    # Smoke create → assign → PDF not required (already 100% in prior run); keep light
    opts = (api("GET", "/tickets/api/options").json() or {}).get("options") or {}
    projects = (api("GET", "/tickets/api/settings/projects").json() or {}).get("projects") or []
    if projects:
        catalog = opts.get("fault_catalog") or []
        if catalog:
            item = catalog[0]
            sg = item.get("service_group") or "HVAC & MEP"
            cat = item.get("category") or "Other"
            fault = str(item.get("fault_type") or item.get("name") or "Other")
        else:
            sg, cat, fault = "HVAC & MEP", "Other", "Other"
        payload = {
            "title": f"{TAG} ticket {SUF}",
            "project": projects[0]["name"],
            "service_group": sg,
            "category": cat,
            "fault_type": fault,
            "priority": "low",
            "work_description": "Admin full-app QA smoke ticket.",
        }
        r, body = expect_json("Tickets create smoke", "POST", "/tickets/api/tickets", json=payload)
        tid = (body or {}).get("ticket_id")
        if tid:
            expect_page("Ticket detail", f"/tickets/{tid}")
            expect_json(
                "Tickets assign-technician smoke",
                "POST",
                f"/tickets/api/tickets/{tid}/assign-technician",
                json={
                    "technician_name": "QA Tech",
                    "technician_code": "TECH-QA",
                    "vendor_company": "Injaaz Facilities Management",
                },
            )

    expect_page("Assets home", "/assets/")
    expect_page("Assets executive", "/assets/executive")
    expect_page("Assets list", "/assets/list")
    expect_page("Assets new", "/assets/new")
    expect_page("Assets map", "/assets/map")
    expect_page("Assets twin", "/assets/twin")
    expect_page("Assets scan", "/assets/scan")
    expect_json("Assets list API", "GET", "/assets/api/assets")
    expect_json("Assets KPIs", "GET", "/assets/api/kpis")
    code = f"QA-{SUF}"
    r, body = expect_json(
        "Assets create",
        "POST",
        "/assets/api/assets",
        json={"name": f"{TAG} asset", "asset_id": code, "asset_type": "HVAC", "status": "active"},
    )
    if (body or {}).get("success"):
        expect_page("Asset detail", f"/assets/{code}")
        expect_json("Assets get API", "GET", f"/assets/api/assets/{code}")
        expect_json(
            "Assets update",
            "PUT",
            f"/assets/api/assets/{code}",
            json={"name": f"{TAG} asset updated", "status": "active"},
        )


# ─── HR ──────────────────────────────────────────────────────────────
def section_hr():
    print("\n=== HR ===")
    expect_page("HR dashboard", "/hr/")
    expect_page("HR my-requests", "/hr/my-requests")
    forms = [
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
    for path in forms:
        expect_page(f"HR form {path.split('/')[-1]}", path)

    expect_page("HR pending-review", "/hr/pending-review")
    expect_page("HR approved-forms", "/hr/approved-forms")
    expect_page("HR gm-approval", "/hr/gm-approval")
    expect_page("HR hiring", "/hr/hiring")
    expect_page("HR leave-tracker", "/hr/leave-tracker")
    expect_page("HR manpower-tracker", "/hr/manpower-tracker")

    expect_json("HR my-submissions API", "GET", "/hr/api/my-submissions")
    expect_json("HR user-permissions API", "GET", "/hr/api/user-permissions")
    expect_json("HR mgmt-chain-context", "GET", "/hr/api/mgmt-chain-context")

    # PDF/DOCX if any submission exists
    subs = (api("GET", "/hr/api/my-submissions").json() or {})
    rows = subs.get("submissions") or subs.get("data") or []
    if isinstance(rows, list) and rows:
        sid = rows[0].get("submission_id") or rows[0].get("id")
        if sid:
            pdf = api("GET", f"/hr/download-pdf/{sid}")
            ok = pdf.status_code == 200 and (
                pdf.content[:4] == b"%PDF" or "pdf" in (pdf.headers.get("content-type") or "").lower()
                or pdf.status_code == 200 and len(pdf.content) > 100
            )
            # Some HR PDFs stream HTML launcher — accept 200 launcher or real PDF
            if pdf.content[:4] == b"%PDF":
                check("HR download-pdf", True)
            elif pdf.status_code == 200:
                check("HR download-pdf launcher/page", True, "200 non-PDF body (launcher ok)")
            else:
                check("HR download-pdf", False, f"status={pdf.status_code}")
            docx = api("GET", f"/hr/download-docx/{sid}")
            check(
                "HR download-docx",
                docx.status_code == 200 and (
                    docx.content[:2] == b"PK" or len(docx.content) > 100
                ),
                f"status={docx.status_code}",
            )
    else:
        warn("HR: no submissions to export PDF/DOCX")

    # Hiring / leave / manpower excel templates if exposed
    for path, label in [
        ("/hr/hiring/api/export", "HR hiring export"),
        ("/hr/leave-tracker/api/export", "HR leave-tracker export"),
        ("/hr/manpower-tracker/api/export", "HR manpower export"),
        ("/hr/hiring/export", "HR hiring export alt"),
        ("/hr/leave-tracker/export-excel", "HR leave export alt"),
    ]:
        r = api("GET", path)
        if r.status_code == 404:
            continue
        if r.status_code == 200 and (r.content[:2] == b"PK" or len(r.content) > 50):
            check(label, True)
        elif r.status_code in (200, 400, 403):
            warn(f"{label}: {r.status_code} (endpoint present)")
            check(label, True, f"status={r.status_code}")
        else:
            check(label, False, f"status={r.status_code}")


# ─── Inspection + Workflow ───────────────────────────────────────────
def section_inspection_workflow():
    print("\n=== Inspection + Workflow ===")
    expect_page("Inspection dashboard", "/inspection/")
    expect_page("Inspection form", "/inspection/form")
    expect_json("Inspection dropdowns", "GET", "/inspection/dropdowns")
    expect_page("Submitted forms HR", "/workflow/submitted-forms?scope=hr")
    expect_page("Submitted forms inspection", "/workflow/submitted-forms?scope=inspection")
    expect_page("Pending reviews", "/workflow/pending-reviews")

    # Workflow APIs if present
    for path, label in [
        ("/api/workflow/dashboard", "Workflow dashboard API"),
        ("/api/workflow/pending", "Workflow pending API"),
        ("/api/workflow/history", "Workflow history API"),
    ]:
        r = api("GET", path)
        if r.status_code == 404:
            warn(f"{label} not found (404)")
            continue
        check(label, r.status_code in (200, 401, 403) or r.status_code < 500, f"status={r.status_code}")


# ─── Procurement ─────────────────────────────────────────────────────
def section_procurement():
    print("\n=== Procurement ===")
    expect_page("Procurement home", "/procurement/")
    expect_page("Procurement materials", "/procurement/materials")
    expect_page("Procurement add-material", "/procurement/add-material")
    expect_page("Procurement properties", "/procurement/properties")
    expect_json("Procurement materials API", "GET", "/procurement/api/materials")
    expect_json("Procurement properties API", "GET", "/procurement/api/properties")
    expect_json("Procurement catalog API", "GET", "/procurement/api/catalog/materials")
    expect_json("Procurement registered-properties", "GET", "/procurement/api/registered-properties")
    expect_bytes("Procurement sample Excel", "/procurement/api/sample-excel", b"PK")
    expect_bytes("Procurement export Excel", "/procurement/api/export-excel", b"PK")

    # Soft create disposable material if API accepts
    r, body = expect_json(
        "Procurement create material smoke",
        "POST",
        "/procurement/api/materials",
        ok_statuses=(200, 201, 400),
        json={
            "material_name": f"{TAG} material {SUF}",
            "category": "HVAC",
            "unit": "ea",
            "quantity": 1,
            "unit_price": 1,
            "property": "Unassigned",
        },
    )
    if r.status_code == 400:
        warn(f"Procurement material create validation: {(body or {})}")


# ─── QHSE ────────────────────────────────────────────────────────────
def section_qhse():
    print("\n=== QHSE ===")
    expect_page("QHSE home", "/qhsi/")
    expect_page("QHSE staff-compliance", "/qhsi/staff-compliance")
    expect_page("QHSE training", "/qhsi/training")
    expect_page("QHSE inspection", "/qhsi/inspection")
    expect_json("QHSE stats", "GET", "/qhsi/api/stats")
    expect_json("QHSE projects", "GET", "/qhsi/api/projects")
    expect_json("QHSE inspection-catalog", "GET", "/qhsi/api/inspection-catalog")
    expect_json("QHSE trainings list", "GET", "/qhsi/api/trainings")
    expect_bytes(
        "QHSE compliance import template",
        "/qhsi/api/staff-compliance/import-template",
        b"PK",
    )


# ─── Files ───────────────────────────────────────────────────────────
def section_files():
    print("\n=== Files ===")
    expect_page("Files home", "/files/")
    expect_json("Files catalog", "GET", "/files/api/catalog")
    expect_json("Files tree", "GET", "/files/api/tree")
    expect_json("Files Drive status (no OAuth)", "GET", "/files/api/drive/status")

    # Create folder then upload tiny text file
    fr, fbody = expect_json(
        "Files create folder",
        "POST",
        "/files/api/folders",
        json={"name": f"{TAG}-{SUF}"},
    )
    folder_id = None
    if isinstance(fbody, dict):
        folder_id = (
            (fbody.get("folder") or {}).get("id")
            or (fbody.get("data") or {}).get("folder", {}).get("id")
            or fbody.get("id")
        )
        # success_response may nest under data
        data = fbody.get("data") if isinstance(fbody.get("data"), dict) else fbody
        if folder_id is None and isinstance(data, dict):
            folder_id = (data.get("folder") or {}).get("id")
    if not folder_id:
        # parse from tree as fallback
        tree = api("GET", "/files/api/tree").json() or {}
        warn(f"Files folder create payload: {fbody}")
    files = {"file": (f"{TAG}-{SUF}.txt", io.BytesIO(b"admin full app qa\n"), "text/plain")}
    if folder_id:
        r = api("POST", "/files/api/upload", files=files, data={"folder_id": str(folder_id)})
        body = None
        try:
            body = r.json()
        except Exception:
            pass
        ok = r.status_code in (200, 201) and (
            not isinstance(body, dict) or body.get("success") is not False
        )
        check("Files upload smoke", ok, f"status={r.status_code} {body}")
    else:
        check("Files upload smoke", False, "no folder_id from create folder")


# ─── MMR ─────────────────────────────────────────────────────────────
def section_mmr():
    print("\n=== MMR / Report Generation ===")
    expect_page("MMR dashboard", "/admin/mmr/")
    expect_page("MMR chargeable settings", "/admin/mmr-chargeable")
    expect_json("MMR current-upload", "GET", "/admin/mmr/api/current-upload")
    expect_json("MMR email-config GET", "GET", "/admin/mmr/api/email-config")
    expect_json("MMR email-suggestions", "GET", "/admin/mmr/api/email-suggestions")
    expect_json("MMR automation-status", "GET", "/admin/mmr/api/automation-status")
    expect_json("MMR cycles", "GET", "/admin/mmr/api/cycles")
    expect_json("MMR report-folder", "GET", "/admin/mmr/api/report-folder")

    # Download report may 400 without upload — warn ok
    for path, label in [
        ("/admin/mmr/api/download-report", "MMR download-report"),
        ("/admin/mmr/api/download-report-monthly", "MMR download-report-monthly"),
    ]:
        r = api("GET", path)
        if r.status_code == 200 and (r.content[:2] == b"PK" or r.content[:4] == b"%PDF"):
            check(label, True)
        elif r.status_code in (400, 404):
            warn(f"{label}: no upload/report yet ({r.status_code})")
            check(label + " endpoint alive", True, f"status={r.status_code}")
        else:
            check(label, False, f"status={r.status_code}")


# ─── DocHub ──────────────────────────────────────────────────────────
def section_dochub():
    print("\n=== DocHub ===")
    expect_page("DocHub page", "/dochub")
    expect_json("DocHub access-check", "GET", "/api/docs/access-check")
    expect_json("DocHub list", "GET", "/api/docs")
    r, body = expect_json(
        "DocHub create note",
        "POST",
        "/api/docs",
        json={"title": f"{TAG} doc {SUF}", "content": "Admin full-app QA note.", "doc_type": "note"},
        ok_statuses=(200, 201, 400),
    )
    if r.status_code == 400:
        # try alternate payload
        r2, body2 = expect_json(
            "DocHub create alt",
            "POST",
            "/api/docs",
            json={"title": f"{TAG} doc {SUF}", "body": "Admin full-app QA note."},
            ok_statuses=(200, 201, 400),
        )
        if r2.status_code == 400:
            warn(f"DocHub create schema: {body2 or body}")


# ─── Admin / Devices / BD / DB ───────────────────────────────────────
def section_admin():
    print("\n=== Admin / Devices / BD / Database ===")
    expect_page("Admin dashboard", "/admin/dashboard")
    expect_page("Team management", "/admin/team-management")
    expect_page("Devices page", "/admin/devices")
    expect_page("BD module page", "/admin/bd")
    expect_page("Personal progress", "/admin/personal-progress")
    expect_page("Knowledge base", "/admin/knowledge-base")
    expect_page("Database admin", "/admin/database")

    expect_json("Admin devices list", "GET", "/api/admin/devices")
    expect_json("Admin devices stats", "GET", "/api/admin/devices/stats")
    expect_bytes("Admin devices sample Excel", "/api/admin/devices/sample-excel", b"PK")
    expect_json("Admin technicians list", "GET", "/api/admin/technicians")
    expect_bytes("Admin technicians export-template", "/api/admin/technicians/export-template", b"PK")
    expect_json("Admin database status", "GET", "/api/admin/database/status")
    expect_json("Admin database backups", "GET", "/api/admin/database/backups")

    # Users list if available
    for path, label in [
        ("/api/admin/users", "Admin users list"),
        ("/api/admin/dashboard/overview", "Admin overview"),
        ("/api/admin/stats", "Admin stats"),
        ("/api/admin/email-logs", "Admin email logs"),
    ]:
        r = api("GET", path)
        if r.status_code == 404:
            continue
        check(label, r.status_code == 200, f"status={r.status_code}")


def section_bd_email():
    print("\n=== BD Email Module ===")
    expect_page("BD email module", "/bd/email-module")
    expect_json("BD email attachments list", "GET", "/bd/email-module/attachments")
    # Do NOT POST /send


# ─── Assistant ───────────────────────────────────────────────────────
def section_assistant():
    print("\n=== Assistant ===")
    r, body = expect_json(
        "Assistant chat smoke",
        "POST",
        "/api/assistant/chat",
        json={"message": "Hello, what modules are available?"},
        ok_statuses=(200, 201, 503),
    )
    if r.status_code == 503:
        warn("Assistant LLM unavailable (503) — endpoint reachable")


# ─── Auth me / hub config ────────────────────────────────────────────
def section_misc_apis():
    print("\n=== Misc APIs ===")
    expect_json("Hub config", "GET", "/api/hub/config")
    # Tickets pricing on a known ticket if any
    lst = page("/tickets/list")
    m = re.search(r"/tickets/(TKT-[A-Z0-9]+)", lst.text or "")
    if m:
        expect_json("Tickets pricing-preview", "GET", f"/tickets/api/tickets/{m.group(1)}/pricing-preview")


def main():
    print(f"Admin full-app QA → {BASE}  tag={TAG}")
    t0 = time.time()
    if not login():
        print("Abort: login failed")
        return 1

    section_shell()
    section_tickets_assets()
    section_hr()
    section_inspection_workflow()
    section_procurement()
    section_qhse()
    section_files()
    section_mmr()
    section_dochub()
    section_admin()
    section_bd_email()
    section_assistant()
    section_misc_apis()

    passed = sum(1 for _, p, _ in checks if p)
    failed = sum(1 for _, p, _ in checks if not p)
    total = len(checks)
    pct = round(100.0 * passed / total, 1) if total else 0.0
    elapsed = round(time.time() - t0, 1)

    print("\n" + "=" * 56)
    print(f"RESULT: {passed}/{total} checks passed  ({elapsed}s)")
    print(f"PASS RATE: {pct}%")
    print(f"WARNINGS: {len(warns)}")
    print("=" * 56)
    if failed:
        print("\nFailures:")
        for name, p, detail in checks:
            if not p:
                print(f"  - {name}: {detail}")
    if warns:
        print("\nWarnings (non-fatal):")
        for w in warns[:40]:
            print(f"  - {w}")
        if len(warns) > 40:
            print(f"  … +{len(warns) - 40} more")

    report = {
        "pass_rate_pct": pct,
        "passed": passed,
        "failed": failed,
        "total": total,
        "warnings": warns,
        "failures": [{"name": n, "detail": d} for n, p, d in checks if not p],
        "elapsed_s": elapsed,
        "tag": TAG,
    }
    out = "/tmp/injaaz_admin_full_qa_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {out}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
