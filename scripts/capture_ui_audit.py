#!/usr/bin/env python3
"""Dump UI screenshots of every Kynvera module page, size, zoom, and popup.

Prerequisites:
  - App running (./run → http://127.0.0.1:5002)
  - pip install playwright && playwright install chromium

Usage:
  ./venv/bin/python scripts/capture_ui_audit.py
  ./venv/bin/python scripts/capture_ui_audit.py --base-url http://127.0.0.1:5002
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.getLogger().setLevel(logging.WARNING)

VIEWPORTS: list[tuple[str, int, int]] = [
    ("desktop", 1440, 900),
    ("laptop", 1280, 800),
    ("tablet", 768, 1024),
    ("mobile", 390, 844),
]
HUB_ZOOMS = (75, 125)
DEFAULT_WAIT_MS = 600
NAV_TIMEOUT_MS = 25_000
TICKET_PATH_SKIP = {"new", "list", "drafts", "settings"}

SKIP_CLICK_RE = re.compile(
    r"\b(logout|log out|download|export|print|submit|save|send|confirm|yes,? delete|"
    r"delete permanently|apply import|place order|receive goods)\b",
    re.I,
)
OPEN_CLICK_RE = re.compile(
    r"\b(add|new|create|edit|import|filter|review|more|hold|reopen|revoke|"
    r"approve|enroll|manage|upload|rename|log leave|new request|new folder)\b",
    re.I,
)

OVERLAY_JS = """() => {
  const sels = [
    '.modal.active', '.modal.show',
    '.hh-modal-backdrop.open', '.hh-modal:not([hidden])',
    '.lt-modal:not([hidden])',
    '.tkt-modal-backdrop.open', '.tkt-modal-backdrop:not([hidden]):not([aria-hidden="true"])',
    '.contact-modal.active', '#profileModal.active',
    'dialog[open]',
    '.modal-overlay.active', '.modal-overlay[style*="flex"]',
    '.files-modal-backdrop:not([hidden])', '#filesModalBackdrop:not([hidden])',
    '.dm-modal-overlay.active', '.dm-modal-overlay.open',
    '.kb-modal-overlay.active', '.kb-modal-overlay.open',
    '.db-modal-overlay.active', '.db-modal-overlay.open',
    '.signoff-modal-overlay.active', '#signoffModalOverlay.active',
    '.twin-confirm.open', '.twin-confirm-card',
    '.bf-modal-veil.active', '#bfModal.active',
    '.pd-panel-open',
    '.mobile-menu-drawer.open', '#mobileMenuDrawer.open',
    '.dh-sidebar.open', '#filesOverlay.open', '#dhOverlay.open',
    '#hhSidebarOverlay.open', '#tktDhOverlay.open', '#adminDhOverlay.open',
    '#qhseDhOverlay.open',
    '.ol-preview-backdrop.open',
    '.success-bg.active', '.success-overlay.active',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (!el) continue;
    const st = window.getComputedStyle(el);
    if (st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0') return true;
  }
  return false;
}"""

CLOSE_OVERLAYS_JS = """() => {
  document.querySelectorAll('dialog[open]').forEach((d) => { try { d.close(); } catch (e) {} });
  const kill = [
    'active', 'open', 'show',
  ];
  document.querySelectorAll(
    '.modal, .hh-modal-backdrop, .tkt-modal-backdrop, .contact-modal, .modal-overlay, ' +
    '.dm-modal-overlay, .kb-modal-overlay, .db-modal-overlay, .bf-modal-veil, ' +
    '.signoff-modal-overlay, .ol-preview-backdrop, .success-bg, .success-overlay, ' +
    '.twin-confirm, #mobileMenuDrawer, #filesOverlay, #dhOverlay, #hhSidebarOverlay, ' +
    '#tktDhOverlay, #adminDhOverlay, #qhseDhOverlay, #mobileOverlay'
  ).forEach((el) => {
    kill.forEach((c) => el.classList.remove(c));
    if (el.hasAttribute('hidden')) el.hidden = true;
    if (el.getAttribute('aria-hidden') === 'false') el.setAttribute('aria-hidden', 'true');
  });
  document.querySelectorAll('.lt-modal, .hh-modal').forEach((el) => { el.hidden = true; });
  document.body.classList.remove('modal-open', 'no-scroll', 'noscroll');
  document.body.style.overflow = '';
}"""


def _safe(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip("/_") or "index")
    return s[:160]


def _path_name(path: str) -> str:
    base = path.split("?")[0].strip("/") or "index"
    return _safe(base.replace("/", "__"))


def log(msg: str) -> None:
    print(msg, flush=True)


def is_good_shot(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 1500 and "ERROR" not in path.name


def install_api_stubs(context, auth_me_body: str | None) -> None:
    """Replay /api/auth/me and silence notification polling so Flask rate limits are not burned."""

    def handler(route) -> None:
        url = route.request.url
        if "/api/auth/me" in url and auth_me_body:
            route.fulfill(status=200, content_type="application/json", body=auth_me_body)
            return
        if "unread-count" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"success":true,"count":0,"unread":0}',
            )
            return
        route.continue_()

    context.route("**/api/auth/me*", handler)
    context.route("**/*unread-count*", handler)


# module, name, path (or callable later), hub?
STATIC_PAGES: list[tuple[str, str, str, bool]] = [
    ("00_shell", "landing", "/", True),
    ("00_shell", "login", "/login", False),
    ("00_shell", "register", "/register", False),
    ("00_shell", "offline", "/offline", False),
    ("00_shell", "dashboard", "/dashboard", True),
    ("01_hr", "hub", "/hr/", True),
    ("01_hr", "my_requests", "/hr/my-requests", False),
    ("01_hr", "form_leave", "/hr/leave-application-form", False),
    ("01_hr", "form_commencement", "/hr/commencement-form", False),
    ("01_hr", "form_duty_resumption", "/hr/duty-resumption-form", False),
    ("01_hr", "form_contract_renewal", "/hr/contract-renewal-form", False),
    ("01_hr", "form_performance", "/hr/performance-evaluation-form", False),
    ("01_hr", "form_grievance", "/hr/grievance-form", False),
    ("01_hr", "form_interview", "/hr/interview-assessment-form", False),
    ("01_hr", "form_passport", "/hr/passport-release-form", False),
    ("01_hr", "form_appraisal", "/hr/staff-appraisal-form", False),
    ("01_hr", "form_station_clearance", "/hr/station-clearance-form", False),
    ("01_hr", "form_visa", "/hr/visa-renewal-form", False),
    ("01_hr", "form_asset_handover", "/hr/asset-handover-form", False),
    ("01_hr", "pending_review", "/hr/pending-review", False),
    ("01_hr", "approved_forms", "/hr/approved-forms", False),
    ("01_hr", "gm_approval", "/hr/gm-approval", False),
    ("01_hr", "hiring", "/hr/hiring", False),
    ("01_hr", "offer_letters", "/hr/hiring/offer-letters", False),
    ("01_hr", "leave_tracker", "/hr/leave-tracker", False),
    ("01_hr", "leave_repeat_sick", "/hr/leave-tracker/repeat-sick", False),
    ("01_hr", "leave_sick_trends", "/hr/leave-tracker/sick-trends", False),
    ("01_hr", "manpower", "/hr/manpower-tracker", False),
    ("02_tickets", "hub", "/tickets/", True),
    ("02_tickets", "list", "/tickets/list", False),
    ("02_tickets", "new", "/tickets/new", False),
    ("02_tickets", "drafts", "/tickets/drafts", False),
    ("02_tickets", "settings", "/tickets/settings", False),
    ("02_tickets", "locations_standalone", "/tickets/settings/locations/standalone", False),
    ("03_assets", "hub", "/assets/", True),
    ("03_assets", "executive", "/assets/executive", False),
    ("03_assets", "list", "/assets/list", False),
    ("03_assets", "new", "/assets/new", False),
    ("03_assets", "map", "/assets/map", False),
    ("03_assets", "twin", "/assets/twin", False),
    ("03_assets", "scan", "/assets/scan", False),
    ("04_procurement", "hub", "/procurement/", True),
    ("04_procurement", "materials", "/procurement/materials", False),
    ("04_procurement", "add_material", "/procurement/add-material", False),
    ("04_procurement", "properties", "/procurement/properties", False),
    ("04_procurement", "catalog_hvac", "/procurement/catalog/HVAC", False),
    ("04_procurement", "catalog_cleaning", "/procurement/catalog/Cleaning", False),
    ("04_procurement", "catalog_electrical", "/procurement/catalog/Electrical", False),
    ("04_procurement", "catalog_plumbing", "/procurement/catalog/Plumbing", False),
    ("04_procurement", "suppliers", "/procurement/suppliers", False),
    ("04_procurement", "purchase_requests", "/procurement/purchase-requests", False),
    ("04_procurement", "refill", "/procurement/refill", False),
    ("04_procurement", "log", "/procurement/log", False),
    ("04_procurement", "email_settings", "/procurement/email-settings", False),
    ("05_inspection", "hub", "/inspection/", True),
    ("05_inspection", "form", "/inspection/form", False),
    ("06_qhse", "hub", "/qhsi/", True),
    ("06_qhse", "staff_compliance", "/qhsi/staff-compliance", False),
    ("06_qhse", "training", "/qhsi/training", False),
    ("06_qhse", "inspection", "/qhsi/inspection", False),
    ("07_files", "hub", "/files/", True),
    ("08_mmr", "hub", "/admin/mmr/", True),
    ("08_mmr", "chargeable", "/admin/mmr-chargeable", False),
    ("09_automations", "hub", "/automations/", True),
    ("10_dochub", "hub", "/dochub", True),
    ("11_admin", "hub", "/admin/dashboard", True),
    ("11_admin", "email_log", "/admin/dashboard?focus=email-log", False),
    ("11_admin", "devices", "/admin/devices", False),
    ("11_admin", "bd", "/admin/bd", False),
    ("11_admin", "personal_progress", "/admin/personal-progress", False),
    ("11_admin", "team", "/admin/team-management", False),
    ("11_admin", "knowledge_base", "/admin/knowledge-base", False),
    ("11_admin", "database", "/admin/database", False),
    ("12_workflow", "pending", "/workflow/pending-reviews", False),
    ("12_workflow", "submitted_hr", "/workflow/submitted-forms?scope=hr", False),
    ("12_workflow", "submitted_inspection", "/workflow/submitted-forms?scope=inspection", False),
    ("12_workflow", "dashboard", "/api/workflow/dashboard", False),
    ("12_workflow", "history", "/api/workflow/history", False),
    ("13_bd", "email_module", "/bd/email-module", True),
]

# path-prefix → list of {name, click?, js?, wait?}
POPUPS: dict[str, list[dict[str, str]]] = {
    "/dashboard": [
        {"name": "profile", "js": "typeof openProfileModal==='function' && openProfileModal()", "wait": "#profileModal.active"},
        {"name": "todo", "click": "#todoToggle, [data-todo-toggle], .todo-nav-btn, button[aria-label*='To-do' i]", "wait": "#todoPanel, .todo-panel-pop"},
    ],
    "/hr/hiring": [
        {"name": "add_candidate", "click": "#hhAddBtnToolbar, #hhAddBtn", "wait": "#hhAddModal.open"},
    ],
    "/hr/hiring/offer-letters": [
        {"name": "add_letter", "click": "#olAddBtn", "wait": "#olFormModal.open, #olFormModal"},
    ],
    "/hr/leave-tracker": [
        {"name": "log_leave", "click": "#ltLogLeaveBtn", "wait": "#ltLogModal"},
        {"name": "add_employee", "click": "#ltAddEmpBtn", "wait": "#ltEmpModal"},
        {"name": "add_plan", "click": "#ltAddPlanBtn", "wait": "#ltPlanModal"},
        {"name": "add_month_card", "click": "#ltAddMonthCard", "wait": "#ltAddCardModal"},
    ],
    "/hr/manpower-tracker": [
        {"name": "add_assignment", "click": "#mpAddBtn", "wait": "#mpAddModal"},
        {"name": "import", "click": "#mpImportBtn", "wait": "#mpImportModal"},
        {"name": "link_candidate", "click": "#mpLinkBtn", "wait": "#mpLinkModal"},
    ],
    "/hr/pending-review": [
        {"name": "review", "click": ".review-card button, .review-card, [data-review]", "wait": "#reviewModal.show, #reviewModal.modal"},
    ],
    "/hr/leave-application-form": [
        {"name": "signature", "click": "[data-open-signature], .sig-open, button:has-text('Sign')", "wait": "#sigmBg, #sigBg, .sigm-modal"},
    ],
    "/tickets/new": [
        {"name": "project_search", "click": "#projectSearch, #projectInput, input[name='project']", "wait": "#projectSearchDropdown, .tkt-ac-dropdown"},
    ],
    "/tickets/settings": [
        {"name": "add_project", "click": "#addProjectBtn, button:has-text('Add project'), button:has-text('New project')", "wait": "#addProjectModal, .proj-ios-modal"},
    ],
    "/procurement/purchase-requests": [
        {"name": "new_pr", "click": "#newPrBtn", "wait": "#newPrModal.show, #newPrModal"},
    ],
    "/procurement/properties": [
        {"name": "add_property", "click": "#addPropertyBtn, button:has-text('Add property')", "wait": "#addPropertyModal.show, #addPropertyModal"},
    ],
    "/procurement/suppliers": [
        {"name": "add_supplier", "click": "#addSupplierBtn, button:has-text('Add supplier')", "wait": "#addModal.show, #addModal"},
    ],
    "/procurement/catalog/HVAC": [
        {"name": "add_material", "click": "#addCatalogBtn, button:has-text('Add material')", "wait": "#catalogMaterialModal.show, #catalogMaterialModal"},
    ],
    "/files/": [
        {"name": "new_folder", "click": "#filesNewFolderBtn", "wait": "#filesModalBackdrop"},
    ],
    "/dochub": [
        {"name": "new_doc", "click": "#dhNewDocBtn", "wait": "#dhNewDocModal"},
        {"name": "upload", "click": "#dhUploadBtn, button:has-text('Upload')", "wait": "#dhUploadModal"},
    ],
    "/admin/dashboard": [
        {"name": "create_user", "js": "typeof openCreateUserModal==='function' && openCreateUserModal()", "wait": "#createUserModal.active"},
        {"name": "profile", "js": "typeof openProfileModal==='function' && openProfileModal()", "wait": "#profileModal.active"},
    ],
    "/admin/devices": [
        {"name": "enroll", "click": "#enrollBtn, button:has-text('Enroll')", "wait": "#enrollModal"},
    ],
    "/admin/knowledge-base": [
        {"name": "add_text", "click": "#kbAddTextBtn, button:has-text('Add text')", "wait": "#kbTextModal"},
        {"name": "upload", "click": "#kbUploadBtn, button:has-text('Upload')", "wait": "#kbUploadModal"},
        {"name": "add_link", "click": "#kbAddLinkBtn, button:has-text('Add link')", "wait": "#kbLinkModal"},
    ],
    "/admin/database": [
        {"name": "confirm", "click": "button:has-text('Backup'), button:has-text('Reset')", "wait": "#dbConfirmModal"},
    ],
    "/admin/personal-progress": [
        {"name": "add_project", "click": "#ppAddBtn, button:has-text('Add project'), button:has-text('New project')", "wait": "#ppModal"},
    ],
    "/admin/bd": [
        {"name": "new_deal", "click": "button:has-text('New'), button:has-text('Add project')", "wait": "#bfModal"},
    ],
    "/admin/team-management": [
        {"name": "add_tech", "click": "button:has-text('Add'), #addTechBtn", "wait": "#techModal, #createLoginModal"},
    ],
    "/admin/mmr/": [
        {"name": "download_mode", "click": "button:has-text('Download'), #downloadBtn", "wait": "#downloadModeModal"},
        {"name": "report_settings", "click": "button:has-text('Settings'), #reportSettingsBtn", "wait": "#reportSettingsModal"},
    ],
    "/inspection/form": [
        {"name": "signoff", "click": "#signoffBtn, button:has-text('Sign-off'), button:has-text('Sign off')", "wait": "#signoffModalOverlay"},
    ],
    "/automations/": [
        {"name": "run_record", "click": "tr.auto-run-row", "wait": "#autoRunModal"},
    ],
    "/bd/email-module": [
        {"name": "group", "click": "button:has-text('Add group'), #addGroupBtn", "wait": "#groupModal"},
    ],
}

DETAIL_POPUPS: dict[str, list[dict[str, str]]] = {
    "ticket_detail": [
        {"name": "hold", "click": "#holdTicketBtn", "wait": "#holdTicketModal"},
        {"name": "cancel", "click": "#cancelTicketBtn", "wait": "#cancelTicketModal"},
        {"name": "reopen", "click": "#reopenTicketBtn", "wait": "#reopenTicketModal"},
        {"name": "location", "click": "#ticketLocationMapHit, #ticketLocationBtn", "wait": "#ticketLocationModal"},
        {"name": "submit_sup", "click": "#submitSupBtn, button:has-text('Submit to supervisor')", "wait": "#submitSupModal"},
        {"name": "ops_close", "click": "#opsCloseBtn", "wait": "#opsCloseModal"},
        {"name": "sup_close", "click": "#supCloseBtn", "wait": "#supCloseModal"},
        {"name": "revoke", "click": "#revokeStageBtn", "wait": "#revokeStageModal"},
    ],
    "pr_detail": [
        {"name": "gm_review", "click": "#gmReviewBtn, button:has-text('Review')", "wait": "#gmReviewModal.show, #gmReviewModal"},
    ],
    "property_detail": [
        {"name": "add_material", "click": "button:has-text('Add material')", "wait": "#addMaterialModal.show, #addMaterialModal"},
        {"name": "from_sites", "click": "button:has-text('From other sites'), button:has-text('Share')", "wait": "#fromSitesModal.show, #fromSitesModal"},
        {"name": "issue", "click": "button:has-text('Issue')", "wait": "#issueModal.show, #issueModal"},
        {"name": "icon", "click": "#iconPickerBtn, button:has-text('Icon')", "wait": "#iconPickerModal.show, #iconPickerModal"},
    ],
    "twin": [
        {"name": "confirm", "click": "button:has-text('Open'), .twin-open-btn", "wait": "#twinConfirm, .twin-confirm-card"},
    ],
}


def login_playwright(page, base: str, username: str, password: str, timeout_ms: int) -> None:
    page.goto(f"{base}/login", wait_until="load", timeout=timeout_ms)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#login-btn")
    page.wait_for_url(re.compile(r".*/dashboard.*"), timeout=timeout_ms)
    page.wait_for_load_state("load")


def api_json(page, path: str) -> Any:
    return page.evaluate(
        """async (path) => {
          const t = localStorage.getItem('access_token') || '';
          const r = await fetch(path, {
            headers: { Authorization: 'Bearer ' + t, Accept: 'application/json' },
          });
          try { return await r.json(); } catch (e) { return { _status: r.status }; }
        }""",
        path,
    )


def first_of(obj: Any, *keys: str) -> Any:
    if isinstance(obj, list) and obj:
        return obj[0]
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if v and not isinstance(v, (list, dict)):
            return v
    return None


def discover_ids(page, base: str, skipped: list[str]) -> dict[str, str]:
    ids: dict[str, str] = {}

    def take(label: str, path: str, *keys: str) -> None:
        try:
            body = api_json(page, path)
        except Exception as exc:
            skipped.append(f"{label}: api {path} failed ({exc})")
            return
        row = first_of(body, *keys) if not isinstance(body, list) else (body[0] if body else None)
        if isinstance(row, dict):
            if label == "asset" and row.get("asset_id"):
                ids["asset"] = str(row["asset_id"])
            elif label == "candidate" and row.get("id") is not None:
                ids["candidate"] = str(row["id"])
            elif label == "pr" and (row.get("public_id") or row.get("id")):
                ids["pr"] = str(row.get("public_id") or row.get("id"))
            elif label == "property" and row.get("name"):
                ids["property"] = str(row["name"])
            elif label == "plan":
                if row.get("id") is not None:
                    ids["plan"] = str(row["id"])
                if row.get("project_id") not in (None, ""):
                    ids["twin_project"] = str(row["project_id"])
            elif label == "ticket_project" and row.get("id") is not None:
                ids["ticket_project"] = str(row["id"])
            elif label == "hr_sub" and row.get("submission_id"):
                ids["hr_sub"] = str(row["submission_id"])
        elif row:
            ids[label] = str(row)

    take("asset", "/assets/api/assets", "assets")
    take("candidate", "/hr/api/hiring/candidates", "candidates")
    take("pr", "/procurement/api/purchase-requests", "requests")
    take("property", "/procurement/api/properties", "properties")
    take("plan", "/assets/api/floor-plans", "plans")
    take("ticket_project", "/tickets/api/settings/projects", "projects")
    take("hr_sub", "/hr/api/my-submissions", "submissions", "data")

    try:
        page.goto(f"{base}/tickets/list", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(600)
        hrefs = page.eval_on_selector_all(
            'a[href*="/tickets/"]',
            "els => els.map(e => e.getAttribute('href') || '')",
        )
        skip_exact = {"/tickets/", "/tickets/list", "/tickets/new", "/tickets/drafts", "/tickets/settings"}
        for href in hrefs or []:
            path = href.split("?")[0]
            m = re.match(r"^/tickets/([^/]+)$", path)
            if (
                m
                and path not in skip_exact
                and m.group(1) not in TICKET_PATH_SKIP
                and not path.startswith("/tickets/api")
            ):
                ids["ticket"] = m.group(1)
                break
    except Exception as exc:
        skipped.append(f"ticket: list scrape failed ({exc})")

    try:
        page.goto(f"{base}/tickets/drafts", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(500)
        hrefs = page.eval_on_selector_all(
            'a[href*="/tickets/"]',
            "els => els.map(e => e.getAttribute('href') || '')",
        )
        for href in hrefs or []:
            m = re.search(r"/tickets/([^/]+)/review", href or "")
            if m:
                ids["draft"] = m.group(1)
                break
            m2 = re.match(r"^/tickets/([^/]+)$", (href or "").split("?")[0])
            if m2 and m2.group(1) not in TICKET_PATH_SKIP:
                ids["draft"] = m2.group(1)
                break
    except Exception as exc:
        skipped.append(f"draft: scrape failed ({exc})")

    return ids


def build_pages(ids: dict[str, str], skipped: list[str]) -> list[tuple[str, str, str, bool]]:
    pages = list(STATIC_PAGES)
    extra: list[tuple[str, str, str, bool]] = []

    def need(key: str, module: str, name: str, path: str) -> None:
        if ids.get(key):
            extra.append((module, name, path, False))
        else:
            skipped.append(f"{name}: no {key} in live data")

    need("ticket", "02_tickets", "ticket_detail", f"/tickets/{ids.get('ticket', '')}")
    if ids.get("draft"):
        extra.append(("02_tickets", "draft_review", f"/tickets/drafts/{ids['draft']}/review", False))
    else:
        skipped.append("draft_review: no draft ticket")
    need("ticket_project", "02_tickets", "project_locations", f"/tickets/settings/locations/{ids.get('ticket_project', '')}")
    need("asset", "03_assets", "asset_detail", f"/assets/{ids.get('asset', '')}")
    need("asset", "03_assets", "asset_edit", f"/assets/{ids.get('asset', '')}/edit")
    need("asset", "03_assets", "asset_public_tag", f"/assets/tag/{ids.get('asset', '')}")
    need("twin_project", "03_assets", "twin_project", f"/assets/twin/project/{ids.get('twin_project', '')}")
    need("plan", "03_assets", "twin_plan", f"/assets/twin/plan/{ids.get('plan', '')}")
    if ids.get("property"):
        extra.append(("04_procurement", "property_detail", f"/procurement/property/{quote(ids['property'], safe='')}", False))
    else:
        skipped.append("property_detail: no property")
    need("pr", "04_procurement", "pr_detail", f"/procurement/purchase-requests/{ids.get('pr', '')}")
    need("candidate", "01_hr", "candidate_detail", f"/hr/hiring/candidates/{ids.get('candidate', '')}")
    if ids.get("hr_sub"):
        extra.append(("01_hr", "print", f"/hr/print/{ids['hr_sub']}", False))
    return pages + extra


def shot_path(out: Path, module: str, name: str, viewport: str, zoom: int, kind: str, extra: str = "") -> Path:
    folder = out / module
    folder.mkdir(parents=True, exist_ok=True)
    bits = [name, viewport, f"z{zoom}", kind]
    if extra:
        bits.append(_safe(extra))
    return folder / ("__".join(bits) + ".png")


def goto(page, base: str, path: str, wait_ms: int) -> None:
    page.goto(f"{base}{path}", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    page.wait_for_timeout(wait_ms)


def set_zoom(page, zoom: int) -> None:
    page.evaluate(
        """(z) => {
          document.documentElement.style.zoom = String(z / 100);
        }""",
        zoom,
    )
    page.wait_for_timeout(250)


def capture_page(page, dest_full: Path, dest_view: Path | None) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(150)
    if dest_view is not None:
        page.screenshot(path=str(dest_view), full_page=False)
    page.screenshot(path=str(dest_full), full_page=True)


def close_overlays(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
        page.evaluate(CLOSE_OVERLAYS_JS)
        page.wait_for_timeout(150)
        page.keyboard.press("Escape")
    except Exception:
        pass


def try_click(page, selector: str) -> bool:
    for part in [p.strip() for p in selector.split(",") if p.strip()]:
        loc = page.locator(part).first
        try:
            if loc.count() == 0:
                continue
            loc.scroll_into_view_if_needed(timeout=1500)
            loc.click(timeout=2500, force=True)
            return True
        except Exception:
            continue
    return False


def wait_overlay(page, wait_sel: str, timeout: int = 2500) -> bool:
    if wait_sel:
        for part in [p.strip() for p in wait_sel.split(",") if p.strip()]:
            try:
                loc = page.locator(part).first
                loc.wait_for(state="visible", timeout=timeout)
                return True
            except Exception:
                continue
    try:
        page.wait_for_function(OVERLAY_JS, timeout=timeout)
        return True
    except Exception:
        return False


def capture_popup(page, dest: Path, spec: dict[str, str]) -> bool:
    close_overlays(page)
    opened = False
    if spec.get("js"):
        try:
            page.evaluate(f"() => {{ {spec['js']}; }}")
            opened = True
        except Exception:
            opened = False
    if not opened and spec.get("click"):
        opened = try_click(page, spec["click"])
    if not opened:
        return False
    page.wait_for_timeout(350)
    if not wait_overlay(page, spec.get("wait") or ""):
        close_overlays(page)
        return False
    page.screenshot(path=str(dest), full_page=False)
    close_overlays(page)
    return True


def heuristic_popups(page, dest_dir: Path, module: str, name: str, viewport: str, captured: list[str]) -> int:
    n = 0
    try:
        handles = page.locator("button:visible").all()[:40]
    except Exception:
        return 0
    seen: set[str] = set()
    for btn in handles:
        try:
            text = (btn.inner_text(timeout=400) or "").strip()
        except Exception:
            continue
        if not text or len(text) > 48:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        if SKIP_CLICK_RE.search(text):
            continue
        if not OPEN_CLICK_RE.search(text):
            continue
        try:
            typ = btn.get_attribute("type") or "button"
            if typ.lower() == "submit":
                continue
        except Exception:
            pass
        close_overlays(page)
        try:
            btn.scroll_into_view_if_needed(timeout=800)
            btn.click(timeout=1500, force=True)
        except Exception:
            continue
        page.wait_for_timeout(300)
        try:
            visible = page.evaluate(OVERLAY_JS)
        except Exception:
            visible = False
        if visible:
            extra = _safe(f"btn_{text[:32]}")
            dest = shot_path(dest_dir, module, name, viewport, 100, "view", extra)
            try:
                page.screenshot(path=str(dest), full_page=False)
                captured.append(str(dest.relative_to(dest_dir)))
                n += 1
            except Exception:
                pass
        close_overlays(page)
        if n >= 8:
            break
    return n


def capture_mobile_drawer(page, dest_dir: Path, module: str, name: str, captured: list[str]) -> None:
    toggles = [
        "#mobileMenuToggle",
        ".dh-sidebar-toggle",
        "#hhSidebarToggle",
        "#filesSidebarToggle",
        ".proc-sidebar-toggle",
        "#tktSidebarToggle",
        "#fmSidebarToggle",
        "#qhseSidebarToggle",
        "#adminSidebarToggle",
        "button[aria-label*='menu' i]",
        "button[aria-label*='sidebar' i]",
    ]
    for sel in toggles:
        if try_click(page, sel):
            page.wait_for_timeout(400)
            dest = shot_path(dest_dir, module, name, "mobile", 100, "view", "drawer")
            try:
                page.screenshot(path=str(dest), full_page=False)
                captured.append(str(dest.relative_to(dest_dir)))
            except Exception:
                pass
            close_overlays(page)
            return


def popups_for_path(path: str, name: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    bare = path.split("?")[0]
    if bare in POPUPS:
        specs.extend(POPUPS[bare])
    elif bare.rstrip("/") in POPUPS:
        specs.extend(POPUPS[bare.rstrip("/")])
    for prefix, items in POPUPS.items():
        if prefix != bare and bare.rstrip("/") == prefix.rstrip("/"):
            specs.extend(items)
    if name in DETAIL_POPUPS:
        specs.extend(DETAIL_POPUPS[name])
    # de-dupe by name
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in specs:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        out.append(s)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Full UI screenshot dump (pages, sizes, zoom, popups).")
    parser.add_argument("--base-url", default="http://127.0.0.1:5002")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "screenshots")
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--login-user", default="Kynvera")
    parser.add_argument("--login-password", default="Arshith&Taha@2026")
    parser.add_argument("--wait-ms", type=int, default=DEFAULT_WAIT_MS)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse --stamp folder; skip shots that already exist (ignore *ERROR*).",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    stamp = args.stamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out: Path = args.out_dir / f"ui_audit_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    if args.resume:
        for err in out.rglob("*ERROR*.png"):
            try:
                err.unlink()
            except OSError:
                pass
    base = args.base_url.rstrip("/")

    captured: list[str] = []
    skipped: list[str] = []
    failures: list[str] = []
    native_dialogs: list[str] = []
    counts: dict[str, int] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        boot = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        boot.add_init_script(
            "document.documentElement.style.setProperty('scroll-behavior','auto');"
        )
        page = boot.new_page()
        page.set_default_timeout(8_000)

        def on_dialog(dialog) -> None:
            native_dialogs.append(f"{page.url}\t{dialog.type}\t{dialog.message}")
            try:
                dialog.dismiss()
            except Exception:
                pass

        page.on("dialog", on_dialog)

        try:
            login_playwright(page, base, args.login_user, args.login_password, NAV_TIMEOUT_MS)
            log(f"Logged in as {args.login_user!r}")
        except Exception as exc:
            print(f"Login failed: {exc}", file=sys.stderr)
            browser.close()
            return 3

        auth_me_body = None
        try:
            auth_me_body = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('access_token') || '';
                  const r = await fetch('/api/auth/me', {
                    headers: { Authorization: 'Bearer ' + t, Accept: 'application/json' },
                  });
                  return await r.text();
                }"""
            )
        except Exception as exc:
            log(f"Could not prime /api/auth/me: {exc}")

        ids = discover_ids(page, base, skipped)
        (out / "_ids.json").write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
        log(f"Resolved IDs: {ids}")
        state = boot.storage_state()
        boot.close()

        pages = build_pages(ids, skipped)
        public_first = [p for p in pages if p[2] in ("/", "/login", "/register", "/offline")]
        authed = [p for p in pages if p not in public_first]
        # Public pages: capture once logged-out via a fresh context, then authed pages.

        def run_pass(context_pages: list[tuple[str, str, str, bool]], logged_in: bool) -> None:
            for vp_name, vw, vh in VIEWPORTS:
                ctx = browser.new_context(
                    viewport={"width": vw, "height": vh},
                    device_scale_factor=1,
                    storage_state=state if logged_in else None,
                    reduced_motion="reduce",
                )
                ctx.add_init_script(
                    "document.documentElement.style.setProperty('scroll-behavior','auto');"
                )
                install_api_stubs(ctx, auth_me_body)
                p = ctx.new_page()
                p.set_default_timeout(8_000)
                p.on("dialog", on_dialog)
                if logged_in:
                    try:
                        p.goto(f"{base}/dashboard", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                        p.wait_for_timeout(250)
                    except Exception:
                        pass

                for module, name, path, is_hub in context_pages:
                    zooms = [100]
                    if vp_name == "desktop" and is_hub:
                        zooms = [100, *HUB_ZOOMS]
                    for zoom in zooms:
                        dest_full = shot_path(out, module, name, vp_name, zoom, "full")
                        dest_view = (
                            shot_path(out, module, name, vp_name, zoom, "view")
                            if vp_name == "desktop" and zoom == 100
                            else None
                        )
                        popup_specs = popups_for_path(path, name) if vp_name == "desktop" and zoom == 100 else []
                        popup_dests = [
                            shot_path(out, module, name, vp_name, 100, "view", spec["name"])
                            for spec in popup_specs
                        ]
                        drawer_dest = (
                            shot_path(out, module, name, "mobile", 100, "view", "drawer")
                            if vp_name == "mobile" and is_hub
                            else None
                        )
                        need_page = not is_good_shot(dest_full)
                        need_popups = any(not is_good_shot(d) for d in popup_dests)
                        need_drawer = bool(drawer_dest) and not is_good_shot(drawer_dest)
                        if args.resume and not need_page and not need_popups and not need_drawer:
                            log(f"SKIP {vp_name} z{zoom} {path}")
                            continue
                        try:
                            goto(p, base, path, args.wait_ms)
                            if zoom != 100:
                                set_zoom(p, zoom)
                            else:
                                set_zoom(p, 100)
                            if need_page:
                                capture_page(p, dest_full, dest_view if dest_view and not is_good_shot(dest_view) else None)
                                captured.append(str(dest_full.relative_to(out)))
                                if dest_view and is_good_shot(dest_view):
                                    captured.append(str(dest_view.relative_to(out)))
                                counts[module] = counts.get(module, 0) + 1
                                log(f"OK  {vp_name} z{zoom} {path} -> {dest_full.name}")
                            else:
                                log(f"OK  {vp_name} z{zoom} {path} (page exists, extras)")

                            if need_popups:
                                for spec, dest in zip(popup_specs, popup_dests):
                                    if is_good_shot(dest):
                                        continue
                                    try:
                                        if capture_popup(p, dest, spec):
                                            captured.append(str(dest.relative_to(out)))
                                            counts[module] = counts.get(module, 0) + 1
                                            log(f"    popup {spec['name']}")
                                    except Exception as exc:
                                        failures.append(f"{path} popup {spec['name']}: {exc}")
                                if not args.resume:
                                    heuristic_popups(p, out, module, name, vp_name, captured)

                            if need_drawer and drawer_dest is not None:
                                capture_mobile_drawer(p, out, module, name, captured)

                            set_zoom(p, 100)
                            close_overlays(p)
                        except Exception as exc:
                            failures.append(f"{vp_name} z{zoom} {path}: {exc}")
                            log(f"ERR {vp_name} {path}: {exc}")
                ctx.close()

        # Logged-out public pages at all viewports (no popups except login).
        run_pass(public_first, logged_in=False)
        run_pass(authed, logged_in=True)
        browser.close()

    (out / "_manifest.txt").write_text("\n".join(captured) + "\n", encoding="utf-8")
    (out / "_skipped.txt").write_text("\n".join(skipped) + "\n", encoding="utf-8")
    (out / "_failures.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")
    (out / "_native_dialogs.txt").write_text("\n".join(native_dialogs) + "\n", encoding="utf-8")

    print("\n=== UI audit capture ===", flush=True)
    print(f"Output: {out}", flush=True)
    print(f"PNGs this run: {len(captured)}", flush=True)
    live = len(list(out.rglob("*.png")))
    print(f"PNGs on disk: {live}", flush=True)
    for mod in sorted(counts):
        print(f"  {mod}: {counts[mod]}", flush=True)
    print(
        f"Skipped: {len(skipped)} | Failures: {len(failures)} | Native dialogs: {len(native_dialogs)}",
        flush=True,
    )
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
