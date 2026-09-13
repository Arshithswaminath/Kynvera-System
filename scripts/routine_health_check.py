#!/usr/bin/env python3
"""Scheduled read-only health check for the live Kynvera Operations app.

Runs as a Render Cron Job (see docs/smoke/ROUTINE_CHECK.md for setup). Reuses
the http/page/api_json/save_http_binary/record helpers from
scripts/module_functional_smoke.py, but only exercises safe GET routes —
no ticket creation, no HR submission, no MMR upload, no chat session. Exits
non-zero if anything fails, so Render marks the run "Failed" and (once
notifications are enabled on the cron job) alerts on it.

Env vars:
  CHECK_BASE_URL     default https://operations.kynvera.net
  CHECK_USERNAME     login username
  CHECK_PASSWORD     login password
  CHECK_MFA_SECRET   TOTP secret (base32), if the account has MFA enabled
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_smoke_module():
    path = ROOT / "scripts" / "module_functional_smoke.py"
    spec = importlib.util.spec_from_file_location("module_functional_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = load_smoke_module()
    mod._load_dotenv()
    mod.BASE = os.environ.get("CHECK_BASE_URL", "https://operations.kynvera.net").rstrip("/")
    mod.OUT = Path("/tmp") / "routine_health_check_artifacts"
    mod.OUT.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Routine health check -> {mod.BASE} ===\n")

    if not mod.section_shell():
        print("\nCannot continue without login.")
        return 1

    print("\n=== HR ===")
    for path in (
        "/hr/", "/hr/my-requests", "/hr/pending-review", "/hr/approved-forms",
        "/hr/hiring", "/hr/leave-tracker", "/hr/employee-list", "/hr/manpower-tracker",
        "/hr/leave-application-form",
    ):
        mod.page("hr", path)
    mod.api_json("hr", "GET", "/hr/api/notifications/unread-count", warn_on=(404,))
    mod.api_json("hr", "GET", "/hr/api/hiring/candidates", warn_on=(404,))
    mod.api_json("hr", "GET", "/hr/api/leave-tracker/employees", warn_on=(404,))
    mod.api_json("hr", "GET", "/hr/api/my-submissions", warn_on=(404,))

    print("\n=== Ticketing ===")
    for path in ("/tickets/", "/tickets/list", "/tickets/new", "/tickets/drafts", "/tickets/settings"):
        mod.page("ticketing", path)
    mod.api_json("ticketing", "GET", "/tickets/api/options")
    _ok, _st, list_html = mod.page("ticketing", "/tickets/list", "PAGE /tickets/list (scrape)")
    ticket_id = None
    if list_html:
        m = re.search(rb"TKT-[0-9A-F]{6,10}", list_html)
        if m:
            ticket_id = m.group(0).decode()
    if ticket_id:
        mod.page("ticketing", f"/tickets/{ticket_id}", f"PAGE /tickets/{ticket_id} (existing)")
    else:
        mod.record("ticketing", "existing ticket detail", False, "no ticket id found on /tickets/list", warn=True)

    print("\n=== Inspection / QHSI / MMR / Procurement ===")
    mod.page("inspection", "/inspection/")
    mod.api_json("inspection", "GET", "/inspection/dropdowns", warn_on=(404,))
    mod.page("qhsi", "/qhsi/")
    mod.api_json("qhsi", "GET", "/qhsi/api/stats", warn_on=(404,))
    mod.page("mmr", "/admin/mmr/")
    mod.api_json("mmr", "GET", "/admin/mmr/api/current-upload", warn_on=(404,))
    mod.page("procurement", "/procurement/")
    mod.api_json("procurement", "GET", "/procurement/api/materials", warn_on=(404,))

    print("\n=== FM Assets ===")
    for path in ("/assets/", "/assets/executive", "/assets/list", "/assets/map"):
        mod.page("assets", path)
    ok, _st, assets = mod.api_json("assets", "GET", "/assets/api/assets")
    if ok:
        items = assets.get("assets") or assets.get("data") or assets.get("items") or []
        if isinstance(items, list) and items:
            code = items[0].get("asset_id") or items[0].get("asset_code") or items[0].get("code")
            if code:
                mod.page("assets", f"/assets/{code}", f"PAGE /assets/{code}")

    print("\n=== Admin, BD, Devices, Workflow, DocHub ===")
    for path in (
        "/admin", "/admin/dashboard", "/dochub", "/admin/devices",
        "/admin/team-management", "/admin/bd", "/bd/email-module",
        "/workflow/pending-reviews", "/workflow/submitted-forms",
    ):
        mod.page("admin", path)
    mod.api_json("admin", "GET", "/api/admin/users", warn_on=(404,))
    mod.api_json("admin", "GET", "/api/workflow/dashboard-stats", warn_on=(404,))

    print("\n=== Files, Assistant, Notifications ===")
    mod.page("files", "/files/")
    mod.api_json("assistant", "GET", "/api/assistant/sessions/current", warn_on=(404, 401))
    mod.api_json("notifications", "GET", "/hr/api/notifications", warn_on=(403, 404))
    mod.page("notifications", "/admin/email-notifications")

    print("\n" + "=" * 70)
    print(f"RESULTS: {mod.PASS} passed, {mod.FAIL} failed, {mod.WARN} warnings")
    print("=" * 70)

    by_module: dict[str, dict[str, int]] = {}
    for r in mod.RESULTS:
        d = by_module.setdefault(r["module"], {"PASS": 0, "FAIL": 0, "WARN": 0})
        d[r["status"]] = d.get(r["status"], 0) + 1
    print("\nBy module:")
    for m, counts in by_module.items():
        print(f"  {m:14s} pass={counts.get('PASS',0):3d} fail={counts.get('FAIL',0):3d} warn={counts.get('WARN',0):3d}")

    if mod.FAIL:
        print("\nFailures:")
        for r in mod.RESULTS:
            if r["status"] == "FAIL":
                print(f"  - {r['module']} / {r['name']}: {r['detail']}")

    return 1 if mod.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
