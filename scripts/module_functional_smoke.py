#!/usr/bin/env python3
"""Canonical per-module HTTP smoke: hit live routes, save PDF/Excel artifacts.

Usage (server must already be running, typically ./run on :5002):

  CHECK_BASE_URL=http://127.0.0.1:5002 ./venv/bin/python scripts/module_functional_smoke.py

Credentials: CHECK_USERNAME / CHECK_PASSWORD, or DEFAULT_ADMIN_USERNAME /
DEFAULT_ADMIN_PASSWORD from .env. No live email, Drive, or Cloudinary calls.

Outputs:
  smoke_artifacts/<YYYYMMDD_HHMMSS>/   gitignored binaries + 00_summary.json
  docs/smoke/LAST_RUN.md               pass/fail + timings (overwritten)
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLOW_MS = 5000
VERY_SLOW_MS = 15000
PDF_MAGIC = b"%PDF"
XLSX_MAGIC = b"PK"

RESULTS: list[dict] = []
PASS = FAIL = WARN = 0
TOKEN: str | None = None
BASE = "http://127.0.0.1:5002"
OUT: Path = ROOT / "smoke_artifacts" / "pending"


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_script(name: str, filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record(
    module: str,
    name: str,
    ok: bool,
    detail: str = "",
    *,
    warn: bool = False,
    ms: float = 0,
    artifact: str | None = None,
) -> None:
    global PASS, FAIL, WARN
    if warn and not ok:
        WARN += 1
        status = "WARN"
    elif ok:
        PASS += 1
        status = "PASS"
    else:
        FAIL += 1
        status = "FAIL"
    slow = ""
    if ms >= VERY_SLOW_MS:
        slow = " very-slow"
    elif ms >= SLOW_MS:
        slow = " slow"
    RESULTS.append(
        {
            "module": module,
            "name": name,
            "status": status,
            "detail": detail,
            "ms": round(ms, 1),
            "artifact": artifact,
            "slow": slow.strip(),
        }
    )
    extra = f" — {detail}" if detail else ""
    art = f" → {artifact}" if artifact else ""
    print(f"  [{status}] {name}{extra}{art} ({ms:.0f}ms{slow})")


def http(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body=None,
    timeout: int = 60,
    raw_body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, bytes, str, float]:
    headers = {"Accept": "application/json, text/html, application/pdf, */*"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if raw_body is not None:
        data = raw_body
        if content_type:
            headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "") or ""
            return resp.status, raw, ctype, (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b""
        ctype = (exc.headers.get("Content-Type", "") if exc.headers else "") or ""
        return exc.code, raw, ctype, (time.perf_counter() - t0) * 1000
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode(), "", (time.perf_counter() - t0) * 1000


def _json_payload(raw: bytes):
    try:
        return json.loads(raw.decode() or "{}")
    except Exception:
        return {"_raw": raw[:300].decode(errors="replace")}


def page(module: str, path: str, name: str | None = None, allowed=(200,)):
    name = name or f"PAGE {path}"
    status, raw, _ctype, ms = http("GET", path, token=TOKEN, timeout=45)
    ok = status in allowed and len(raw) > 80
    record(module, name, ok, f"HTTP {status} bytes={len(raw)}", ms=ms)
    return ok, status, raw


def api_json(
    module: str,
    method: str,
    path: str,
    name: str | None = None,
    body=None,
    allowed=(200,),
    warn_on=(),
    timeout: int = 60,
):
    name = name or f"{method} {path}"
    status, raw, ctype, ms = http(method, path, token=TOKEN, body=body, timeout=timeout)
    payload = _json_payload(raw) if "json" in (ctype or "").lower() or raw[:1] in (b"{", b"[") else {"_bytes": len(raw)}
    if status in allowed:
        record(module, name, True, f"HTTP {status}", ms=ms)
        return True, status, payload
    if status in warn_on:
        record(module, name, False, f"HTTP {status}: {str(payload)[:160]}", warn=True, ms=ms)
        return False, status, payload
    record(module, name, False, f"HTTP {status}: {str(payload)[:160]}", ms=ms)
    return False, status, payload


def save_bytes(rel: str, data: bytes) -> Path:
    dest = OUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def save_http_binary(
    module: str,
    path: str,
    rel: str,
    magic: bytes,
    name: str | None = None,
    timeout: int = 90,
    warn_on=(),
) -> bool:
    name = name or f"GET {path}"
    status, raw, ctype, ms = http("GET", path, token=TOKEN, timeout=timeout)
    dest = None
    if status == 200 and raw.startswith(magic):
        dest = save_bytes(rel, raw)
        record(
            module,
            name,
            True,
            f"HTTP {status} {len(raw)} bytes ctype={ctype.split(';')[0]}",
            ms=ms,
            artifact=str(dest.relative_to(OUT)),
        )
        return True
    detail = f"HTTP {status} ctype={ctype.split(';')[0]} head={raw[:12]!r}"
    if status in warn_on or (status == 200 and not raw.startswith(magic)):
        record(module, name, False, detail, warn=True, ms=ms)
        return False
    record(module, name, False, detail, ms=ms)
    return False


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(OUT))
    except ValueError:
        return str(path)


# ── sections ────────────────────────────────────────────────────────────────


def section_shell():
    print("\n=== 1) Health, auth, shells ===")
    st, raw, _c, ms = http("GET", "/health")
    payload = _json_payload(raw)
    record("shell", "GET /health", st == 200, f"HTTP {st} {payload.get('status') or payload.get('database')}", ms=ms)
    page("shell", "/", "PAGE /")
    page("shell", "/login", "PAGE /login")

    username = (
        os.environ.get("CHECK_USERNAME")
        or os.environ.get("DEFAULT_ADMIN_USERNAME")
        or ""
    )
    password = (
        os.environ.get("CHECK_PASSWORD")
        or os.environ.get("DEFAULT_ADMIN_PASSWORD")
        or ""
    )
    if not username or not password:
        record("shell", "auth credentials", False, "Set CHECK_USERNAME/CHECK_PASSWORD or DEFAULT_ADMIN_* in .env")
        return False

    global TOKEN
    st, raw, _c, ms = http("POST", "/api/auth/login", body={"username": username, "password": password})
    login = _json_payload(raw)
    if st != 200:
        record("shell", "POST /api/auth/login", False, f"HTTP {st}: {str(login)[:160]}", ms=ms)
        return False
    TOKEN = (
        login.get("access_token")
        or login.get("token")
        or (login.get("data") or {}).get("access_token")
        or (login.get("tokens") or {}).get("access_token")
        or (login.get("tokens") or {}).get("access")
    )
    record("shell", "POST /api/auth/login", bool(TOKEN), "token present" if TOKEN else f"keys={list(login.keys())}", ms=ms)
    if not TOKEN:
        return False
    api_json("shell", "GET", "/api/auth/me")
    for path in ("/dashboard", "/admin", "/admin/dashboard", "/dochub"):
        page("shell", path)
    return True


def section_hr():
    print("\n=== 2) HR ===")
    for path in (
        "/hr/",
        "/hr/my-requests",
        "/hr/pending-review",
        "/hr/approved-forms",
        "/hr/hiring",
        "/hr/leave-tracker",
        "/hr/manpower-tracker",
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
    ):
        page("hr", path)

    api_json("hr", "GET", "/hr/api/notifications/unread-count", warn_on=(404,))
    api_json("hr", "GET", "/hr/api/hiring/candidates", warn_on=(404,))
    api_json("hr", "GET", "/hr/api/leave-tracker/employees", warn_on=(404,))

    save_http_binary("hr", "/hr/api/leave-tracker/export", "hr/xlsx/leave_tracker_export.xlsx", XLSX_MAGIC, warn_on=(400, 404))
    save_http_binary("hr", "/hr/api/leave-tracker/template", "hr/xlsx/leave_log_template.xlsx", XLSX_MAGIC, warn_on=(400, 404))
    save_http_binary("hr", "/hr/api/manpower/export", "hr/xlsx/manpower_export.xlsx", XLSX_MAGIC, warn_on=(400, 404))
    save_http_binary("hr", "/hr/api/manpower/template", "hr/xlsx/manpower_template.xlsx", XLSX_MAGIC, warn_on=(400, 404))
    save_http_binary("hr", "/hr/api/hiring/export", "hr/xlsx/hiring_export.xlsx", XLSX_MAGIC, warn_on=(400, 404))
    save_http_binary("hr", "/hr/api/hiring/import-template", "hr/xlsx/hiring_import_template.xlsx", XLSX_MAGIC, warn_on=(400, 404))

    leave_payload = {
        "form_type": "leave_application",
        "data": {
            "employee_name": "Smoke Test User",
            "employee_id": "SMOKE-001",
            "leave_type": "Annual",
            "from_date": "2026-08-10",
            "to_date": "2026-08-12",
            "reason": "Module functional smoke",
            "number_of_days": 3,
        },
    }
    api_json(
        "hr",
        "POST",
        "/hr/api/submit",
        name="POST /hr/api/submit (leave)",
        body=leave_payload,
        allowed=(200, 201),
        warn_on=(400, 422),
    )

    ok, _st, subs = api_json("hr", "GET", "/hr/api/my-submissions", warn_on=(404,))
    sid = None
    if ok:
        rows = subs.get("submissions") or subs.get("data") or []
        if isinstance(rows, list) and rows:
            sid = rows[0].get("submission_id") or rows[0].get("id")
    if sid:
        save_http_binary("hr", f"/hr/download-pdf/{sid}", f"hr/pdfs/live_{sid}.pdf", PDF_MAGIC, warn_on=(404,))
    else:
        record("hr", "live download-pdf", False, "no HR submission id", warn=True)

    # Offline: every ReportLab HR form (HTTP may not have one of each type).
    t0 = time.perf_counter()
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        hr_forms = _load_script("auto_test_hr_forms", "auto_test_hr_forms.py")
        from module_hr.pdf_service import generate_hr_pdf, get_supported_pdf_forms

        sample = hr_forms._sample_form_data()
        sample.setdefault(
            "asset_handover",
            {
                "transaction_type": "handover",
                "handover_date": date.today().isoformat(),
                "handover_employee_name": "Smoke Handover",
                "handover_employee_id": "SMOKE-H01",
                "handover_department": "operations",
                "handover_designation": "Supervisor",
                "handover_last_day": date.today().isoformat(),
                "takeover_employee_name": "Smoke Takeover",
                "takeover_employee_id": "SMOKE-T01",
                "takeover_department": "operations",
                "takeover_designation": "Technician",
                "items": [
                    {
                        "description": "Laptop",
                        "asset_tag": "AST-1001",
                        "qty": "1",
                        "condition": "Good",
                        "remarks": "Smoke sample",
                    }
                ],
            },
        )
        built = 0
        for form_type in get_supported_pdf_forms():
            if form_type == "leave":
                continue
            form_data = sample.get("leave_application") if form_type == "leave" else sample.get(form_type)
            if not form_data:
                record("hr", f"builder PDF {form_type}", False, "no sample data", warn=True)
                continue
            submission = hr_forms._mock_submission(form_type, form_data)
            buf = BytesIO()
            ok_pdf, err = generate_hr_pdf(submission, buf)
            raw = buf.getvalue()
            if ok_pdf and raw.startswith(PDF_MAGIC):
                dest = save_bytes(f"hr/pdfs/hr_{form_type.replace('_', '-')}.pdf", raw)
                built += 1
                record(
                    "hr",
                    f"builder PDF {form_type}",
                    True,
                    f"{len(raw)} bytes",
                    artifact=_rel(dest),
                )
            else:
                record("hr", f"builder PDF {form_type}", False, err or "not PDF")
        record("hr", "HR PDF builders complete", built >= 11, f"{built} PDFs", ms=(time.perf_counter() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001
        record("hr", "HR PDF builders", False, str(exc), ms=(time.perf_counter() - t0) * 1000)


def section_ticketing():
    print("\n=== 3) Ticketing ===")
    for path in ("/tickets/", "/tickets/list", "/tickets/new", "/tickets/drafts", "/tickets/settings"):
        page("ticketing", path)

    ok_opts, _st, opts = api_json("ticketing", "GET", "/tickets/api/options")
    _okp, _stp, proj_payload = api_json("ticketing", "GET", "/tickets/api/settings/projects")
    projects = proj_payload.get("projects") or []
    if not projects:
        record("ticketing", "tickets.projects.seeded", False, "no projects", warn=True)

    save_http_binary(
        "ticketing",
        "/tickets/api/tickets/export",
        "ticketing/xlsx/ticket_register.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 404),
    )
    save_http_binary(
        "ticketing",
        "/tickets/api/settings/locations/excel-template",
        "ticketing/xlsx/location_template.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 403, 404),
    )

    pid = None
    if projects:
        p0 = projects[0]
        pid = p0.get("id") if isinstance(p0, dict) else None
        if pid:
            save_http_binary(
                "ticketing",
                f"/tickets/api/settings/projects/{pid}/locations/export",
                "ticketing/xlsx/project_locations.xlsx",
                XLSX_MAGIC,
                warn_on=(400, 404),
            )

    options = (opts.get("options") if isinstance(opts, dict) else {}) or {}
    service_group, category, fault_type = "HVAC systems", "Air Conditioner", "Not Cooling"
    cats = options.get("categories") if isinstance(options, dict) else None
    if isinstance(cats, dict) and cats:
        service_group = next(iter(cats.keys()))
        cat_list = cats.get(service_group) or []
        if cat_list:
            category = cat_list[0]
            fault_type = category
    priority = "medium"
    pri_list = options.get("priorities") if isinstance(options, dict) else None
    if isinstance(pri_list, list) and pri_list:
        first = pri_list[0]
        priority = first.get("value") if isinstance(first, dict) else str(first)
    project_name = ""
    if projects:
        p0 = projects[0]
        project_name = (p0.get("name") if isinstance(p0, dict) else str(p0)) or ""

    create_body = {
        "title": f"Module functional smoke {int(time.time())}",
        "project": project_name or "Marina Towers",
        "service_group": service_group,
        "category": category,
        "fault_type": fault_type,
        "priority": priority,
        "work_description": "Automated module functional smoke — safe to close.",
    }
    ok, _st, created = api_json(
        "ticketing",
        "POST",
        "/tickets/api/tickets",
        name="POST /tickets/api/tickets (create)",
        body=create_body,
        allowed=(200, 201),
        warn_on=(400, 422),
    )
    ticket_id = None
    if ok:
        ticket_id = (
            created.get("ticket_id")
            or created.get("id")
            or (created.get("ticket") or {}).get("ticket_id")
            or (created.get("ticket") or {}).get("id")
            or (created.get("data") or {}).get("ticket_id")
        )
    if ticket_id:
        page("ticketing", f"/tickets/{ticket_id}", f"PAGE /tickets/{ticket_id}")
        save_http_binary(
            "ticketing",
            f"/tickets/{ticket_id}/pdf",
            f"ticketing/pdfs/{ticket_id}_report.pdf",
            PDF_MAGIC,
        )
        save_http_binary(
            "ticketing",
            f"/tickets/{ticket_id}/invoice",
            f"ticketing/pdfs/{ticket_id}_invoice.pdf",
            PDF_MAGIC,
            warn_on=(400, 403, 404, 422),
        )
    else:
        record("ticketing", "ticket PDF/invoice", False, "no ticket id to export", warn=True)

    api_json(
        "ticketing",
        "POST",
        "/tickets/api/tickets/triage-preview",
        name="POST triage-preview",
        body={
            "title": "AC not cooling in lobby",
            "description": "HVAC unit blowing warm air near reception.",
            "location": "Building A Lobby",
        },
        allowed=(200,),
        warn_on=(400, 501, 503),
    )


def section_inspection():
    print("\n=== 4) Inspection ===")
    page("inspection", "/inspection/")
    page("inspection", "/inspection/form")
    api_json("inspection", "GET", "/inspection/dropdowns", warn_on=(404,))

    t0 = time.perf_counter()
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from module_inspection.inspection_generators import create_excel_report, create_pdf_report

        hvac_gm = _load_script("auto_test_hvac_gm_workflow", "auto_test_hvac_gm_workflow.py")
        civil_gm = _load_script("auto_test_civil_gm_workflow", "auto_test_civil_gm_workflow.py")
        clean_gm = _load_script("auto_test_cleaning_gm_workflow", "auto_test_cleaning_gm_workflow.py")
        pairs = [
            ("hvac", hvac_gm.sample_hvac_gm_data()),
            ("civil", civil_gm.sample_civil_gm_data()),
            ("cleaning", clean_gm.sample_cleaning_gm_data()),
        ]
        dest_dir = OUT / "inspection"
        dest_dir.mkdir(parents=True, exist_ok=True)
        for slug, data in pairs:
            tmp = dest_dir / f"_tmp_{slug}"
            tmp.mkdir(parents=True, exist_ok=True)
            pdf_path = create_pdf_report(data, str(tmp))
            xls_path = create_excel_report(data, str(tmp))
            for src, kind, magic in ((pdf_path, "pdfs", PDF_MAGIC), (xls_path, "xlsx", XLSX_MAGIC)):
                src_p = Path(src)
                raw = src_p.read_bytes() if src_p.is_file() else b""
                ext = "pdf" if kind == "pdfs" else "xlsx"
                dest = save_bytes(f"inspection/{kind}/{slug}_report.{ext}", raw)
                record(
                    "inspection",
                    f"builder {slug} {ext}",
                    raw.startswith(magic),
                    f"{len(raw)} bytes",
                    artifact=_rel(dest),
                )
            shutil.rmtree(tmp, ignore_errors=True)
        record(
            "inspection",
            "HVAC/Civil/Cleaning builders",
            True,
            "3 PDF + 3 Excel",
            ms=(time.perf_counter() - t0) * 1000,
        )
    except Exception as exc:  # noqa: BLE001
        record("inspection", "inspection builders", False, str(exc), ms=(time.perf_counter() - t0) * 1000)


def section_qhsi():
    print("\n=== 5) QHSI ===")
    page("qhsi", "/qhsi/")
    api_json("qhsi", "GET", "/qhsi/api/stats", warn_on=(404,))
    save_http_binary(
        "qhsi",
        "/qhsi/api/staff-compliance/import-template",
        "qhsi/xlsx/staff_compliance_template.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 404),
    )

    t0 = time.perf_counter()
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from module_qhsi.qhsi_generators import create_excel_report, create_pdf_report

        record_data = {
            "project_name": "Smoke QHSA Site",
            "visit_date": date.today().isoformat(),
            "department": "hvac",
            "inspector_name": "Smoke Inspector",
            "location": "Marina",
            "summary": "Functional smoke sample inspection.",
            "items": [
                {
                    "area": "AHU room",
                    "equipment": "AHU-01",
                    "severity": "Medium",
                    "description": "Filter due for replacement.",
                    "photos": [],
                }
            ],
        }
        pdf_path = OUT / "qhsi" / "pdfs" / "qhsi_inspection.pdf"
        xls_path = OUT / "qhsi" / "xlsx" / "qhsi_inspection.xlsx"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        xls_path.parent.mkdir(parents=True, exist_ok=True)
        create_pdf_report(record_data, str(pdf_path))
        create_excel_report(record_data, str(xls_path))
        raw_pdf = pdf_path.read_bytes() if pdf_path.is_file() else b""
        raw_xls = xls_path.read_bytes() if xls_path.is_file() else b""
        record(
            "qhsi",
            "builder QHSI PDF",
            raw_pdf.startswith(PDF_MAGIC),
            f"{len(raw_pdf)} bytes",
            ms=(time.perf_counter() - t0) * 1000,
            artifact=_rel(pdf_path),
        )
        record(
            "qhsi",
            "builder QHSI Excel",
            raw_xls.startswith(XLSX_MAGIC),
            f"{len(raw_xls)} bytes",
            artifact=_rel(xls_path),
        )
    except Exception as exc:  # noqa: BLE001
        record("qhsi", "QHSI builders", False, str(exc), warn=True, ms=(time.perf_counter() - t0) * 1000)


def section_mmr():
    print("\n=== 6) MMR ===")
    page("mmr", "/admin/mmr/")
    page("mmr", "/admin/mmr-chargeable")
    api_json("mmr", "GET", "/admin/mmr/api/current-upload", warn_on=(404,))
    api_json("mmr", "GET", "/admin/mmr/api/automation-status", warn_on=(404,))

    sample = None
    for cand in [
        ROOT / "tests" / "fixtures" / "mmr" / "cafm_sample.xlsx",
        ROOT / "HR Documents" / "RM Deatils MMR (4).xlsx",
        ROOT / "HR Documents - Copy" / "RM Deatils MMR (4).xlsx",
    ]:
        if cand.exists():
            sample = cand
            break
    if sample is None:
        for cand in ROOT.rglob("*Resolved and Pending Complaints*.xlsx"):
            if "generated" in str(cand) or "smoke_artifacts" in str(cand):
                continue
            sample = cand
            break

    if sample and sample.exists():
        boundary = "----injaazSmokeBoundary"
        file_bytes = sample.read_bytes()
        filename = sample.name
        body_parts = [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        st, raw, _c, ms = http(
            "POST",
            "/admin/mmr/api/upload",
            token=TOKEN,
            raw_body=b"".join(body_parts),
            content_type=f"multipart/form-data; boundary={boundary}",
            timeout=120,
        )
        payload = _json_payload(raw)
        ok = st in (200, 201)
        record(
            "mmr",
            f"POST /admin/mmr/api/upload ({sample.name})",
            ok,
            f"HTTP {st} {str(payload)[:120]}",
            warn=not ok and st in (400, 413, 422),
            ms=ms,
        )
    else:
        record("mmr", "MMR sample xlsx", False, "no CAFM sample file — skip upload", warn=True)

    save_http_binary(
        "mmr",
        "/admin/mmr/api/download-report",
        "mmr/xlsx/mmr_download_report.xlsx",
        XLSX_MAGIC,
        timeout=120,
        warn_on=(400, 404),
    )


def section_procurement():
    print("\n=== 7) Procurement ===")
    page("procurement", "/procurement/")
    page("procurement", "/procurement/materials")
    api_json("procurement", "GET", "/procurement/api/materials", warn_on=(404,))
    save_http_binary(
        "procurement",
        "/procurement/api/sample-excel",
        "procurement/xlsx/procurement_sample.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 404),
    )
    save_http_binary(
        "procurement",
        "/procurement/api/export-excel",
        "procurement/xlsx/procurement_export.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 404),
    )


def section_assets():
    print("\n=== 8) FM Assets ===")
    for path in ("/assets/", "/assets/executive", "/assets/list", "/assets/map", "/assets/new"):
        page("assets", path)
    ok, _st, assets = api_json("assets", "GET", "/assets/api/assets")
    asset_code = None
    if ok:
        items = assets.get("assets") or assets.get("data") or assets.get("items") or []
        if isinstance(items, list) and items:
            a0 = items[0]
            asset_code = a0.get("asset_id") or a0.get("asset_code") or a0.get("code")
            if asset_code:
                page("assets", f"/assets/{asset_code}", f"PAGE /assets/{asset_code}")
                api_json("assets", "GET", f"/assets/api/assets/{asset_code}")
                save_http_binary(
                    "assets",
                    f"/assets/api/assets/{asset_code}/qr-label.pdf",
                    f"assets/pdfs/{asset_code}-qr-label.pdf",
                    PDF_MAGIC,
                    warn_on=(404,),
                )
            else:
                record("assets", "asset detail key", False, f"no asset_id keys={list(a0.keys())}", warn=True)
        else:
            record("assets", "assets.list.nonempty", False, "no assets seeded", warn=True)
    save_http_binary(
        "assets",
        "/assets/api/qr-labels.pdf",
        "assets/pdfs/asset-qr-labels.pdf",
        PDF_MAGIC,
        warn_on=(400, 404),
    )
    api_json("assets", "GET", "/assets/api/kpis", warn_on=(404, 501))


def section_admin():
    print("\n=== 9) Admin ===")
    for path in (
        "/admin/devices",
        "/admin/team-management",
        "/admin/bd",
        "/admin/knowledge-base",
        "/admin/personal-progress",
    ):
        page("admin", path)
    api_json("admin", "GET", "/api/admin/users", warn_on=(404,))
    save_http_binary(
        "admin",
        "/api/admin/devices/sample-excel",
        "admin/xlsx/devices_sample.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 403, 404),
    )
    save_http_binary(
        "admin",
        "/api/admin/technicians/export-template",
        "admin/xlsx/technicians_template.xlsx",
        XLSX_MAGIC,
        warn_on=(400, 403, 404),
    )


def section_files():
    print("\n=== 10) Files ===")
    page("files", "/files/")
    ok, _st, payload = api_json(
        "files",
        "POST",
        "/files/api/save-from-module",
        name="POST save-from-module leave/template",
        body={"module": "leave", "kind": "template"},
        allowed=(200, 201),
        warn_on=(400, 403, 404),
    )
    item = None
    if ok and isinstance(payload, dict):
        data = payload.get("data") or payload
        item = data.get("item") or (data.get("items") or [None])[0]
    item_id = (item or {}).get("id") if isinstance(item, dict) else None
    if item_id:
        save_http_binary(
            "files",
            f"/files/api/items/{item_id}/download",
            "files/leave_template_from_files.xlsx",
            XLSX_MAGIC,
            warn_on=(404,),
        )
    else:
        record("files", "files download after save", False, "no item id from save-from-module", warn=True)


def section_assistant():
    print("\n=== 11) Assistant ===")
    api_json(
        "assistant",
        "POST",
        "/api/assistant/chat",
        name="POST /api/assistant/chat",
        body={"message": "Reply with exactly: smoke-ok"},
        allowed=(200,),
        warn_on=(400, 501, 503),
        timeout=45,
    )


def write_reports() -> None:
    summary = {
        "base": BASE,
        "started": STARTED,
        "finished": datetime.now().isoformat(timespec="seconds"),
        "pass": PASS,
        "fail": FAIL,
        "warn": WARN,
        "slow_ms": SLOW_MS,
        "very_slow_ms": VERY_SLOW_MS,
        "results": RESULTS,
    }
    (OUT / "00_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    by_mod: dict[str, list[dict]] = {}
    for row in RESULTS:
        by_mod.setdefault(row["module"], []).append(row)

    lines = [
        "# Module functional smoke — last run",
        "",
        f"- **When:** {summary['finished']}",
        f"- **Target:** `{BASE}`",
        f"- **Artifacts:** `{OUT.relative_to(ROOT)}`",
        f"- **Totals:** {PASS} passed, {FAIL} failed, {WARN} warnings",
        f"- **Slow flags:** >{SLOW_MS / 1000:.0f}s candidate, >{VERY_SLOW_MS / 1000:.0f}s high",
        "",
        "## Totals by module",
        "",
        "| Module | Pass | Fail | Warn | Slow |",
        "|--------|------|------|------|------|",
    ]
    for mod, rows in by_mod.items():
        p = sum(1 for r in rows if r["status"] == "PASS")
        f = sum(1 for r in rows if r["status"] == "FAIL")
        w = sum(1 for r in rows if r["status"] == "WARN")
        s = sum(1 for r in rows if r["slow"])
        lines.append(f"| {mod} | {p} | {f} | {w} | {s} |")

    slow_rows = [r for r in RESULTS if r["slow"]]
    lines += ["", "## Slow checks", ""]
    if slow_rows:
        lines += ["| Status | Module | Check | ms |", "|--------|--------|-------|----|"]
        for r in sorted(slow_rows, key=lambda x: -x["ms"]):
            lines.append(f"| {r['status']} | {r['module']} | {r['name']} | {r['ms']:.0f} |")
    else:
        lines.append("None above the slow threshold.")

    fail_rows = [r for r in RESULTS if r["status"] == "FAIL"]
    warn_rows = [r for r in RESULTS if r["status"] == "WARN"]
    lines += ["", "## Failures", ""]
    if fail_rows:
        for r in fail_rows:
            lines.append(f"- **{r['module']} / {r['name']}:** {r['detail']}")
    else:
        lines.append("None.")
    lines += ["", "## Warnings", ""]
    if warn_rows:
        for r in warn_rows:
            lines.append(f"- **{r['module']} / {r['name']}:** {r['detail']}")
    else:
        lines.append("None.")

    arts = [r for r in RESULTS if r.get("artifact")]
    lines += ["", "## Saved artifacts", "", "| Module | Check | File |", "|--------|-------|------|"]
    if arts:
        for r in arts:
            lines.append(f"| {r['module']} | {r['name']} | `{r['artifact']}` |")
    else:
        lines.append("| — | none | — |")

    lines += ["", "## All checks", "", "| Status | Module | Check | ms | Detail |", "|--------|--------|-------|----|--------|"]
    for r in RESULTS:
        detail = (r["detail"] or "").replace("|", "/")[:120]
        lines.append(f"| {r['status']} | {r['module']} | {r['name']} | {r['ms']:.0f} | {detail} |")
    lines.append("")

    report_path = ROOT / "docs" / "smoke" / "LAST_RUN.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {report_path.relative_to(ROOT)}")
    print(f"Wrote { (OUT / '00_summary.json').relative_to(ROOT) }")


STARTED = ""


def main() -> int:
    global BASE, OUT, STARTED
    os.chdir(ROOT)
    _load_dotenv()
    BASE = os.environ.get("CHECK_BASE_URL", "http://127.0.0.1:5002").rstrip("/")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT = ROOT / "smoke_artifacts" / stamp
    OUT.mkdir(parents=True, exist_ok=True)
    STARTED = datetime.now().isoformat(timespec="seconds")

    print(f"\n=== Module functional smoke → {BASE}")
    print(f"Artifacts: {OUT.relative_to(ROOT)}\n")

    if not section_shell():
        print("\nCannot continue without login.")
        write_reports()
        return 1

    section_hr()
    section_ticketing()
    section_inspection()
    section_qhsi()
    section_mmr()
    section_procurement()
    section_assets()
    section_admin()
    section_files()
    section_assistant()

    write_reports()
    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {WARN} warnings")
    print("=" * 60)
    if FAIL:
        print("\nFailures:")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"  - {r['module']} / {r['name']}: {r['detail']}")
    if WARN:
        print("\nWarnings:")
        for r in RESULTS:
            if r["status"] == "WARN":
                print(f"  - {r['module']} / {r['name']}: {r['detail']}")
    print()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
