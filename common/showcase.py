"""Content for the public product showcase at ``/applications``.

Single source of truth for product copy, capability bullets, module tiles and
screenshot manifests. Screenshots live in ``static/images/kynvera/showcase/``
and are built from ``screenshots/`` by ``scripts/build_showcase_images.py``.

``showcase_apps()`` drops screenshot entries whose file is not on disk yet, so a
product with no captures renders its CSS mock instead of broken images.
"""
from __future__ import annotations

from pathlib import Path

SHOWCASE_DIR = Path(__file__).resolve().parent.parent / "static" / "images" / "kynvera" / "showcase"

# Every shot is captured at 1920x1080 and downscaled to this width by the build script.
SHOT_WIDTH = 1600
SHOT_HEIGHT = 900

# PLACEHOLDER: swap for the real sales inbox, phone and meeting link before launch.
CONTACT = {
    "email": "hello@kynvera.com",
    "phone_display": "+971 50 000 0000",
    "phone_href": "+971500000000",
    "whatsapp": "971500000000",
    "meeting_url": "",
    "location": "Dubai & Ajman, United Arab Emirates",
}

FIRE_SYSTEM = {
    "slug": "fire-system",
    "name": "Fire System",
    "kicker": "Fire protection & life safety",
    "tagline": "Every asset, inspection and certificate on one record",
    "summary": (
        "Built for fire-fighting and fire-protection contractors. Site visits, servicing and "
        "certification stay attached to the same asset history, from the first survey to the "
        "signed-off report."
    ),
    "icon": "flame",
    "icon_image": "images/kynvera/apps/fire-system-128.png",
    "launch_endpoint": "launch_fire",
    "mock": "fire",
    "capabilities": [
        "Asset and site register with panels, devices and drawings",
        "Inspections and servicing captured on site, from any device",
        "Scheduled maintenance with automatic due and overdue alerts",
        "Certificates and reports generated from the same record",
    ],
    # PLACEHOLDER: add stats once the Fire deployment numbers are agreed.
    "stats": [],
    "modules": [],
    # Files land here once Fire System is captured; until then the CSS mock renders.
    "shots": [
        {"file": "fire-dashboard.webp", "title": "Dashboard", "caption": "Live view of what is due, overdue and in progress across every site."},
        {"file": "fire-assets.webp", "title": "Asset register", "caption": "Panels, devices and drawings kept against the site they belong to."},
        {"file": "fire-inspection.webp", "title": "Inspection", "caption": "Field checklists with photos and signatures captured on site."},
        {"file": "fire-maintenance.webp", "title": "Maintenance schedule", "caption": "Planned servicing with automatic reminders before anything lapses."},
        {"file": "fire-report.webp", "title": "Report output", "caption": "Branded, signed reports produced straight from the inspection record."},
    ],
}

OPERATIONS_SUITE = {
    "slug": "operations-suite",
    "name": "Operations Suite",
    "kicker": "Company-wide operations",
    "tagline": "The whole back office, running in one application",
    "summary": (
        "HR, finance, operations, stores, inspections and service tickets in a single system, "
        "sharing one set of people, roles and approvals. Originally built for a municipality "
        "operation and now available to any company running field teams."
    ),
    "icon": "building",
    "icon_image": "images/kynvera/apps/ajman-municipality-128.png",
    "launch_endpoint": "launch_municipality",
    "mock": "municipality",
    "capabilities": [
        "Eight modules on one login, one role model and one audit trail",
        "Approval routing built into every form, with email at each stage",
        "Service tickets measured on SLA, bottlenecks and team performance",
        "Invoices, cheques, contracts and reports produced from live data",
    ],
    "stats": [
        {"value": "8", "label": "modules, one login"},
        {"value": "12", "label": "HR forms, all routed"},
        {"value": "1", "label": "shared audit trail"},
    ],
    "modules": [
        {"icon": "users", "name": "HR", "desc": "Twelve forms from leave to visa renewal, each with its own approval chain and generated documents."},
        {"icon": "wallet", "name": "Finance", "desc": "Invoice queue, ERP references, contract management and monthly reporting."},
        {"icon": "clock", "name": "Operations", "desc": "Overtime, timesheets, attendance, trading invoices, clients and cheque preparation."},
        {"icon": "box", "name": "Store", "desc": "Material catalogue with departmental pricing, property records and set builds."},
        {"icon": "clipboard", "name": "Inspection", "desc": "HVAC, civil and cleaning inspections completed in the field with photos and signatures."},
        {"icon": "ticket", "name": "Service Tickets", "desc": "Work orders through their full status queue, with SLA analytics and team performance."},
        {"icon": "docs", "name": "DocHub", "desc": "Controlled documents and templates available to the teams entitled to them."},
        {"icon": "shield", "name": "Admin & BD", "desc": "Users, entitlements, devices, business development pipeline and quotations."},
    ],
    "hero_shot": {"file": "ops-finance.webp", "title": "Finance & invoicing"},
    "shots": [
        {"file": "ops-hr.webp", "title": "HR modules", "caption": "Every HR form in one place, with pending review and approval queues on top."},
        {"file": "ops-finance.webp", "title": "Finance & invoicing", "caption": "Invoice queue with the workflow pipeline and live activity beside it."},
        {"file": "ops-tickets-analytics.webp", "title": "Ticket analytics", "caption": "SLA breach risk, stage bottlenecks and median close time by priority."},
        {"file": "ops-operations.webp", "title": "Operations hub", "caption": "Overtime, timesheets, attendance, invoices, clients and cheques."},
        {"file": "ops-store.webp", "title": "Material catalogue", "caption": "Full material master with brand, department, unit and price."},
        {"file": "ops-approvals.webp", "title": "Approvals", "caption": "Everything awaiting your signature, grouped by the day it was submitted."},
    ],
}

SHOWCASE_APPS = [FIRE_SYSTEM, OPERATIONS_SUITE]

OUTCOMES = [
    {"value": "One", "label": "sign-in", "desc": "Both applications open from the same account, with access granted per product."},
    {"value": "Field", "label": "first", "desc": "Built mobile-first, so work captured on site shows up in the office immediately."},
    {"value": "Every", "label": "step logged", "desc": "Submissions, reviews and approvals recorded with the user, time and stage."},
    {"value": "Yours", "label": "to shape", "desc": "Forms, roles and approval chains configured around how your teams already work."},
]


def _exists(file_name: str) -> bool:
    return (SHOWCASE_DIR / file_name).is_file()


def showcase_apps() -> list[dict]:
    """Products with screenshot entries filtered down to files present on disk."""
    resolved = []
    for app in SHOWCASE_APPS:
        shots = [shot for shot in app.get("shots", []) if _exists(shot["file"])]
        hero = app.get("hero_shot")
        if hero and not _exists(hero["file"]):
            hero = None
        if hero is None and shots:
            hero = shots[0]
        resolved.append({**app, "shots": shots, "hero_shot": hero})
    return resolved
