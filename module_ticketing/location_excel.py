"""Excel template / export / import for the location hierarchy.

Workbook sheets (headers match CRM SpreadsheetML imports):
  Property   — Property Code, Property Name, Area, City, Country, Client Name, Status, Latitude, Longitude
  Zone       — Zone Code, Zone Name, Property
  Sub Zone   — Sub Zone Code, Sub Zone Name, Property, Zone
  Base Unit  — Base Unit Code, Base Unit Name, Property, Zone, Sub Zone, Latitude, Longitude
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any, BinaryIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from module_ticketing.location_catalog import detect_kind, import_location_rows

HEADER_FILL = PatternFill("solid", fgColor="FF8E68")
HEADER_FONT = Font(bold=True, color="FFFFFF")
THIN = Border(
    left=Side(style="thin", color="E9EAEE"),
    right=Side(style="thin", color="E9EAEE"),
    top=Side(style="thin", color="E9EAEE"),
    bottom=Side(style="thin", color="E9EAEE"),
)

SHEETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Property", "property", (
        "Property Code", "Property Name", "Area", "City", "Country", "Client Name", "Status",
        "Latitude", "Longitude",
    )),
    ("Zone", "zone", ("Zone Code", "Zone Name", "Property")),
    ("Sub Zone", "sub_zone", ("Sub Zone Code", "Sub Zone Name", "Property", "Zone")),
    ("Base Unit", "base_unit", (
        "Base Unit Code", "Base Unit Name", "Property", "Zone", "Sub Zone",
        "Latitude", "Longitude",
    )),
)

SHEET_KIND = {
    "property": "property",
    "zone": "zone",
    "sub zone": "sub_zone",
    "subzone": "sub_zone",
    "base unit": "base_unit",
    "baseunit": "base_unit",
}

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cell(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _coord_cell(v: Any) -> str:
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):.6f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _cell(v)


def tree_to_rows(properties: list[dict] | None) -> dict[str, list[dict[str, str]]]:
    """Flatten a location-tree payload into sheet row dicts."""
    out: dict[str, list[dict[str, str]]] = {
        "property": [],
        "zone": [],
        "sub_zone": [],
        "base_unit": [],
    }
    for prop in properties or []:
        out["property"].append({
            "Property Code": _cell(prop.get("code")),
            "Property Name": _cell(prop.get("name")),
            "Area": _cell(prop.get("area")),
            "City": _cell(prop.get("city")),
            "Country": _cell(prop.get("country")),
            "Client Name": _cell(prop.get("client_name")),
            "Status": _cell(prop.get("status")) or ("Active" if prop.get("is_active", True) else "Inactive"),
            "Latitude": _coord_cell(prop.get("latitude")),
            "Longitude": _coord_cell(prop.get("longitude")),
        })
        pname = _cell(prop.get("name"))
        for zone in prop.get("zones") or []:
            zname = _cell(zone.get("name"))
            out["zone"].append({
                "Zone Code": _cell(zone.get("code")),
                "Zone Name": zname,
                "Property": pname,
            })
            for sz in zone.get("sub_zones") or []:
                szname = _cell(sz.get("name"))
                out["sub_zone"].append({
                    "Sub Zone Code": _cell(sz.get("code")),
                    "Sub Zone Name": szname,
                    "Property": pname,
                    "Zone": zname,
                })
                for unit in sz.get("base_units") or []:
                    out["base_unit"].append({
                        "Base Unit Code": _cell(unit.get("code")),
                        "Base Unit Name": _cell(unit.get("name")),
                        "Property": pname,
                        "Zone": zname,
                        "Sub Zone": szname,
                        "Latitude": _coord_cell(unit.get("latitude")),
                        "Longitude": _coord_cell(unit.get("longitude")),
                    })
    return out


def _style_header(ws: Worksheet, cols: int) -> None:
    for col in range(1, cols + 1):
        cell = ws.cell(1, col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(cols)}1"
    ws.row_dimensions[1].height = 22


def _write_sheet(ws: Worksheet, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    for i, h in enumerate(headers, 1):
        ws.cell(1, i, h)
    _style_header(ws, len(headers))
    for r, rec in enumerate(rows, 2):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(r, c, rec.get(h, "") or "")
            cell.border = THIN
            cell.alignment = Alignment(vertical="center")
    widths = [max(12, min(36, len(h) + 4)) for h in headers]
    for rec in rows[:80]:
        for i, h in enumerate(headers):
            widths[i] = max(widths[i], min(40, len(_cell(rec.get(h))) + 2))
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_instructions(ws: Worksheet) -> None:
    ws["A1"] = "Location Excel — how to use"
    ws["A1"].font = Font(bold=True, size=14, color="111827")
    lines = [
        "1. Fill the Property, Zone, Sub Zone, and Base Unit sheets. Keep the orange header row.",
        "2. Every row needs a unique code and a name. Child rows must use the parent names exactly.",
        "3. Example: Property “HQ Building”, Zone “First Floor”, Sub Zone “Meeting Rooms”, Base Unit “Boardroom”.",
        "4. Save as .xlsx, then use Import on the Locations page. Existing codes are updated; new codes are created.",
        "5. Optional Latitude / Longitude on Property and Base Unit sheets pin the site on New Work Order and ticket maps.",
        "6. Export downloads the locations currently on this page in the same layout, including map pins.",
        "7. Leave unused sheets empty (headers only) if you are not changing that level.",
    ]
    for i, line in enumerate(lines, 3):
        ws[f"A{i}"] = line
        ws[f"A{i}"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[i].height = 32
    ws.column_dimensions["A"].width = 110


def build_location_workbook(properties: list[dict] | None = None) -> BytesIO:
    """Build a template (empty sheets) or an export of the given tree."""
    rows = tree_to_rows(properties)
    wb = Workbook()
    inst = wb.active
    inst.title = "Instructions"
    _write_instructions(inst)
    for title, kind, headers in SHEETS:
        ws = wb.create_sheet(title)
        _write_sheet(ws, headers, rows.get(kind) or [])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _sheet_kind(title: str, headers: list[str]) -> str | None:
    detected = detect_kind(headers)
    if detected:
        return detected
    key = re.sub(r"\s+", " ", (title or "").strip().lower())
    return SHEET_KIND.get(key)


def parse_location_xlsx(source: bytes | BinaryIO) -> dict[str, list[dict[str, str]]]:
    """Read Property / Zone / Sub Zone / Base Unit sheets into import row dicts."""
    data = source.read() if hasattr(source, "read") else source
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    parsed: dict[str, list[dict[str, str]]] = {
        "property": [],
        "zone": [],
        "sub_zone": [],
        "base_unit": [],
    }
    try:
        for ws in wb.worksheets:
            rows_iter = ws.iter_rows(values_only=True)
            try:
                header_row = next(rows_iter)
            except StopIteration:
                continue
            headers = [_cell(c) for c in header_row]
            if not any(headers):
                continue
            kind = _sheet_kind(ws.title, headers)
            if kind not in parsed:
                continue
            for raw in rows_iter:
                rec: dict[str, str] = {}
                empty = True
                for h, v in zip(headers, raw or ()):
                    if not h:
                        continue
                    val = _cell(v)
                    rec[h] = val
                    if val:
                        empty = False
                if not empty:
                    parsed[kind].append(rec)
    finally:
        wb.close()
    if not any(parsed.values()):
        raise ValueError("No location rows found. Use the Excel template sheets: Property, Zone, Sub Zone, Base Unit.")
    return parsed


def import_location_xlsx(
    source: bytes | BinaryIO,
    *,
    project_id: int | None = None,
    standalone: bool = False,
) -> dict:
    parsed = parse_location_xlsx(source)
    return import_location_rows(
        property_rows=parsed["property"],
        zone_rows=parsed["zone"],
        sub_zone_rows=parsed["sub_zone"],
        base_unit_rows=parsed["base_unit"],
        project_id=project_id,
        standalone=standalone,
    )


def download_filename(label: str, *, kind: str = "locations") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (label or "locations").strip().lower()).strip("_") or "locations"
    return f"{slug}_{kind}.xlsx"
