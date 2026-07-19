#!/usr/bin/env python3
"""Shared helpers for the PDF / Excel / email document test suites."""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import date, datetime, timedelta
from io import BytesIO


def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ensure_root_on_path() -> str:
    root = project_root()
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def make_outdir(prefix: str) -> str:
    root = ensure_root_on_path()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(root, "test_output", f"{prefix}_{stamp}")
    os.makedirs(path, exist_ok=True)
    return path


def load_script(name: str, filename: str):
    path = os.path.join(project_root(), "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def is_pdf_bytes(data: bytes) -> bool:
    return bool(data) and data[:4] == b"%PDF"


def write_stream(path: str, stream) -> int:
    if hasattr(stream, "getvalue"):
        data = stream.getvalue()
    elif hasattr(stream, "read"):
        stream.seek(0)
        data = stream.read()
    else:
        data = stream
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


class SuiteResult:
    def __init__(self, name: str):
        self.name = name
        self.ok: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.skipped: list[tuple[str, str]] = []

    def pass_(self, label: str):
        self.ok.append(label)
        print(f"  [OK]   {label}")

    def fail(self, label: str, err: str):
        self.failed.append((label, err))
        print(f"  [FAIL] {label}: {err}")

    def skip(self, label: str, reason: str):
        self.skipped.append((label, reason))
        print(f"  [SKIP] {label}: {reason}")

    def summary(self) -> int:
        print(
            f"\n{self.name}: {len(self.ok)} OK, {len(self.failed)} FAIL, "
            f"{len(self.skipped)} SKIP"
        )
        if self.failed:
            for label, err in self.failed:
                print(f"  - {label}: {err}")
        return 1 if self.failed else 0


# ── tiny PNG data-URL used as photo / signature placeholders ─────────────────
PNG_1X1 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def inspection_sample_data() -> dict:
    """Fire Systems sample payload enriched for Service Report page 1 + page 2."""
    mod = load_script("test_inspection_forms", "test_inspection_forms.py")
    data = dict(mod.HVAC_DATA)
    data["submission_id"] = "FS-TEST-0001"
    data["technician_name"] = "Arshith Technician"
    data["tech_signature"] = PNG_1X1
    data["job_name"] = "Fire Systems Inspection"
    data["materials_required"] = [
        {
            "name": "Smoke detector head",
            "brand": "Apollo",
            "uom": "pcs",
            "quantity": 2,
            "unit_price": 85.0,
        }
    ]
    return {"hvac": data}


def pdf_page_count(path: str) -> int:
    from pypdf import PdfReader
    return len(PdfReader(path).pages)


def fake_user(name="Arshith Swaminath P", email="arshith@injaaz.ae", designation="supervisor"):
    u = types.SimpleNamespace()
    u.id = 1
    u.full_name = name
    u.username = "arshith"
    u.email = email
    u.designation = designation
    u.role = "user"
    u.is_active = True
    return u


def fake_ticket(**overrides):
    now = datetime.utcnow()
    attended = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
    completed = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    reporter = fake_user("Arshith Reporter", designation="employee")
    supervisor = fake_user("Arshith Supervisor", designation="supervisor")
    technician = fake_user("Arshith Technician", designation="technician")
    t = types.SimpleNamespace(
        ticket_id="TKT-TEST-001",
        title="AHU filter replacement — Tower A",
        project="Ajman Tower",
        service_group="HVAC",
        category="Preventive",
        fault_type="Filter clogged",
        priority="high",
        status="closed",
        reporter=reporter,
        supervisor=supervisor,
        technician=technician,
        assigned_to=supervisor,
        property_name="Ajman Tower",
        zone="Floor 3",
        sub_zone="Mechanical Room",
        base_unit="AHU-01",
        work_description="Replaced clogged filters and cleaned coils.",
        is_chargeable=True,
        created_at=now - timedelta(days=2),
        closed_at=now,
        # Stored as ISO strings (matches SQLite TEXT columns used by service_report)
        site_attended_at=attended,
        work_completed_at=completed,
        technician_resolution_notes="Filters replaced successfully.",
        service_report_notes="Client satisfied with work.",
        service_report_data=None,
        client_mobile="+971 50 123 4567",
        technician_id_no="TECH-001",
        total_cost=450.0,
        projected_cost=500.0,
        close_signed_by="Arshith Supervisor",
        close_signed_role="supervisor",
        close_notes="Work completed and verified.",
        close_signature=PNG_1X1,
        client_signature=PNG_1X1,
        client_signed_by="Demo Client",
        source_inspection_notif_id=None,
        ticket_project=None,
        manpower=types.SimpleNamespace(all=lambda: []),
    )
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def fake_materials():
    return [
        types.SimpleNamespace(
            material_name="HEPA Filter 24x24",
            quantity=2,
            unit="pcs",
            unit_price=75.0,
            total_price=150.0,
            notes="Standard replacement",
        ),
        types.SimpleNamespace(
            material_name="Coil Cleaner",
            quantity=1,
            unit="L",
            unit_price=45.0,
            total_price=45.0,
            notes="",
        ),
    ]


def fake_manpower():
    return [
        types.SimpleNamespace(
            worker_name="Arshith Technician",
            hours=4.0,
            rate_per_hour=50.0,
            total_cost=200.0,
            work_date=date.today(),
        )
    ]


def fake_cheque():
    item = types.SimpleNamespace(
        sn=1,
        supplier="Emirates Supplies LLC",
        amount=2500.0,
        cheque_date=date.today(),
        remarks="Spare parts — HVAC Q2",
    )
    return types.SimpleNamespace(
        reference_no="CHQ-TEST-0001",
        status="pending_verification",
        requested_date=date.today(),
        office="Head Office",
        department="Operations",
        items=[item],
        total_amount=2500.0,
        requested_by_name="Arshith Swaminath P",
        verified_by_name=None,
        verified_date=None,
        approved_by_name=None,
        approved_date=None,
        requested_signature=None,
        verified_signature=None,
        approved_signature=None,
        attached_documents="Quotation.pdf\nDelivery note.pdf",
    )


def fake_trading_invoice():
    client = types.SimpleNamespace(
        client_name="Demo Client LLC",
        contact_person="Ahmed Al-Rashid",
        billing_address="Sheikh Zayed Road",
        city="Dubai",
        country="UAE",
        phone="+971 4 123 4567",
        email="arshith@injaaz.ae",
    )
    items = [
        types.SimpleNamespace(
            material_name="Filter Kit",
            description="AHU filter set",
            quantity=5,
            unit="set",
            unit_price=120.0,
            total_price=600.0,
        ),
        types.SimpleNamespace(
            material_name="Belt Drive",
            description="V-belt A-size",
            quantity=2,
            unit="pcs",
            unit_price=35.0,
            total_price=70.0,
        ),
    ]
    invoice = types.SimpleNamespace(
        invoice_no="TRD-INV-TEST-001",
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        status="issued",
        subtotal=670.0,
        tax_pct=5.0,
        tax_amount=33.5,
        grand_total=703.5,
        notes="Test trading invoice — suite sample data.",
    )
    return invoice, client, items


def sample_finance_payload() -> dict:
    """Synthetic finance dashboard payload (no DB required)."""
    today = date.today()
    row = {
        "ticket_id": "TKT-TEST-001",
        "title": "AHU filter replacement — Tower A",
        "project": "Ajman Tower",
        "property": "Ajman Tower",
        "account_handler": "Arshith",
        "status": "closed",
        "is_chargeable": True,
        "amount": 450.0,
        "invoice_ref": "INV-TEST-001",
        "date": today.isoformat(),
        "gm_rejected": False,
    }
    return {
        "summary": {
            "period_label": today.strftime("%B %Y"),
            "period_start": today.replace(day=1).isoformat(),
            "period_end": today.isoformat(),
            "created_count": 1,
            "created_value": 450.0,
            "registered_count": 1,
            "registered_value": 450.0,
            "not_registered_count": 0,
            "not_registered_value": 0.0,
            "rejected_count": 0,
            "rejected_value": 0.0,
            "closed_jobs_count": 1,
            "closed_jobs_value": 450.0,
            "closed_invoiced_count": 1,
            "closed_invoiced_value": 450.0,
            "closed_not_invoiced_count": 0,
            "closed_not_invoiced_value": 0.0,
            "closed_rejected_count": 0,
            "filters": {
                "project": "",
                "account_handler": "",
                "month": today.strftime("%Y-%m"),
                "date_from": "",
                "date_to": "",
            },
        },
        "created": [row],
        "registered": [row],
        "not_registered": [],
        "rejected": [],
        "closed_jobs": [row],
    }


def sample_ticketing_report_rows(key: str) -> tuple[list, list]:
    """Minimal rows + summary chips [(label, value), ...] for each REPORT_SPECS key."""
    if key == "work_orders":
        rows = [{
            "ticket_id": "TKT-TEST-001",
            "title": "AHU filter replacement",
            "project": "Ajman Tower",
            "service_group": "HVAC",
            "priority": "High",
            "status": "Closed",
            "supervisor": "Arshith Supervisor",
            "technician": "Arshith Technician",
            "created": date.today().isoformat(),
            "closed": date.today().isoformat(),
        }]
        summary = [("Total", 1), ("Closed", 1), ("Open", 0)]
    elif key == "financial":
        rows = [{
            "ticket_id": "TKT-TEST-001",
            "project": "Ajman Tower",
            "title": "AHU filter replacement",
            "total_cost": 250.0,
            "actual_price": 250.0,
            "markup_pct": 20.0,
            "selling_price": 300.0,
            "margin": 50.0,
            "invoice_ref": "INV-TEST-001",
            "closed": date.today().isoformat(),
        }]
        summary = [("Revenue", "300.00"), ("Cost", "250.00"), ("Margin", "50.00")]
    elif key == "projects":
        rows = [{
            "project": "Ajman Tower",
            "total": 3,
            "open": 1,
            "closed": 2,
            "revenue": 900.0,
            "cost": 700.0,
            "margin": 200.0,
            "avg_close_days": "2.5",
        }]
        summary = [("Projects", 1), ("Revenue", "900.00")]
    elif key == "team":
        rows = [{
            "name": "Arshith Technician",
            "role": "Technician",
            "assigned": 5,
            "completed": 4,
            "hours": "18",
            "labour_cost": 900.0,
        }]
        summary = [("Members", 1), ("Hours", "18")]
    else:  # materials
        rows = [{
            "material": "HEPA Filter 24x24",
            "unit": "pcs",
            "quantity": "10",
            "avg_price": 75.0,
            "spend": 750.0,
            "tickets": 4,
        }]
        summary = [("Materials", 1), ("Spend", "750.00")]
    return rows, summary


def sample_asset_handover_data() -> dict:
    return {
        "transaction_type": "both",
        "handover_date": date.today().isoformat(),
        "handover_employee_name": "Ahmed Hassan",
        "handover_employee_id": "INJ-0042",
        "handover_department": "operations",
        "handover_designation": "Facility Supervisor",
        "handover_last_day": date.today().isoformat(),
        "takeover_employee_name": "Sara Mohammed",
        "takeover_employee_id": "INJ-0099",
        "takeover_department": "operations",
        "takeover_designation": "Facility Supervisor",
        "items": [
            {
                "description": "Laptop — Dell Latitude",
                "asset_tag": "AST-1001",
                "quantity": "1",
                "condition": "good",
                "remarks": "Charger included",
            },
            {
                "description": "Access card",
                "asset_tag": "AST-2044",
                "quantity": "1",
                "condition": "good",
                "remarks": "",
            },
        ],
        "additional_remarks": "Suite sample — assets transferred on site.",
        "handover_signature": PNG_1X1,
        "takeover_signature": PNG_1X1,
        "hr_signature": PNG_1X1,
    }


def bytes_io() -> BytesIO:
    return BytesIO()
