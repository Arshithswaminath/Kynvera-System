"""Parse CRM location SpreadsheetML exports and upsert the ticketing hierarchy.

Expected files (XML SpreadsheetML, often named .xls):
  Property  — Property Code, Property Name, Area, City, Country, Client Name, …
  Zone      — Zone Code, Zone Name, Property
  Sub Zone  — Sub Zone Code, Sub Zone Name, Property, Zone
  BaseUnit  — Base Unit Code, Base Unit Name, Property, Zone, Sub Zone
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, BinaryIO

from app.models import (
    TicketBaseUnit,
    TicketProject,
    TicketProperty,
    TicketSubZone,
    TicketZone,
    db,
)

SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"

PROPERTY_HEADERS = {
    "property code": "code",
    "property name": "name",
    "area": "area",
    "city": "city",
    "country": "country",
    "client name": "client_name",
    "property type": "property_type",
    "criticality": "criticality",
    "ownership type": "ownership_type",
    "intiation date": "initiation_date",  # CRM typo
    "initiation date": "initiation_date",
    "project no": "project_no",
    "plot no": "plot_no",
    "property external reference code": "external_ref",
    "status": "status",
    "latitude": "latitude",
    "lat": "latitude",
    "longitude": "longitude",
    "lng": "longitude",
    "lon": "longitude",
}

ZONE_HEADERS = {
    "zone code": "code",
    "zone name": "name",
    "property": "property",
    "property external reference code": "external_ref",
}

SUBZONE_HEADERS = {
    "sub zone code": "code",
    "sub zone name": "name",
    "property": "property",
    "zone": "zone",
    "property external reference code": "external_ref",
}

UNIT_HEADERS = {
    "base unit code": "code",
    "baseunit code": "code",
    "unit code": "code",
    "base unit name": "name",
    "baseunit name": "name",
    "unit name": "name",
    "property": "property",
    "zone": "zone",
    "sub zone": "sub_zone",
    "sub-zone": "sub_zone",
    "latitude": "latitude",
    "lat": "latitude",
    "longitude": "longitude",
    "lng": "longitude",
    "lon": "longitude",
}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if tag.startswith("{") else tag


def _cell_index(cell) -> int | None:
    raw = cell.attrib.get(f"{{{SS_NS}}}Index") or cell.attrib.get("ss:Index") or cell.attrib.get("Index")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_spreadsheetml(source: str | Path | bytes | BinaryIO) -> tuple[list[str], list[dict[str, str]]]:
    """Return (headers, row dicts) from a SpreadsheetML workbook."""
    if hasattr(source, "read"):
        tree = ET.parse(source)
    elif isinstance(source, (bytes, bytearray)):
        tree = ET.ElementTree(ET.fromstring(source))
    else:
        tree = ET.parse(source)

    root = tree.getroot()
    headers: list[str] = []
    rows: list[dict[str, str]] = []

    for ws in root.iter():
        if _local(ws.tag) != "Worksheet":
            continue
        table = next((c for c in ws if _local(c.tag) == "Table"), None)
        if table is None:
            continue
        for row in table:
            if _local(row.tag) != "Row":
                continue
            cells: dict[int, str] = {}
            col = 0
            for cell in row:
                if _local(cell.tag) != "Cell":
                    continue
                idx = _cell_index(cell)
                col = idx if idx is not None else col + 1
                data_el = next((d for d in cell if _local(d.tag) == "Data"), None)
                val = (data_el.text or "").strip() if data_el is not None else ""
                cells[col] = val
            if not cells:
                continue
            if not headers:
                maxc = max(cells)
                headers = [cells.get(i, "") for i in range(1, maxc + 1)]
                continue
            rec = {h: cells.get(i, "") for i, h in enumerate(headers, 1) if h}
            if any(v for v in rec.values()):
                rows.append(rec)
        if headers or rows:
            break
    return headers, rows


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _fold_place(s: str) -> str:
    s = _norm_key(s)
    s = re.sub(r"^al\s+", "", s)
    s = s.replace("nuaimiya", "nuaimia").replace("nuiymeya", "nuaimia")
    s = s.replace("nakhil", "nakheel")
    return s


def place_similar(a: str, b: str, *, threshold: float = 0.78) -> bool:
    """True when two place strings likely refer to the same site/area."""
    if not a or not b:
        return False
    fa, fb = _fold_place(a), _fold_place(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    if fa in fb or fb in fa:
        return len(min(fa, fb, key=len)) >= 4
    return SequenceMatcher(None, fa, fb).ratio() >= threshold


def _blank(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


def _parse_coord(raw: Any, *, lo: float, hi: float) -> float | None:
    raw = _blank(raw)
    if not raw:
        return None
    try:
        v = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not (lo <= v <= hi):
        return None
    return v


def _apply_row_coords(obj, rec: dict[str, str]) -> None:
    lat = _parse_coord(rec.get("latitude"), lo=-90.0, hi=90.0)
    lng = _parse_coord(rec.get("longitude"), lo=-180.0, hi=180.0)
    if lat is None or lng is None:
        return
    obj.latitude = lat
    obj.longitude = lng


def _parse_date(raw: str | None) -> date | None:
    raw = _blank(raw)
    if not raw:
        return None
    raw = raw.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[:26], fmt).date()
        except ValueError:
            continue
    return None


def _map_row(row: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in row.items():
        dest = mapping.get(_norm_key(k))
        if dest:
            out[dest] = (v or "").strip()
    return out


def detect_kind(headers: list[str]) -> str | None:
    keys = {_norm_key(h) for h in headers if h}
    if "property code" in keys and "property name" in keys:
        return "property"
    if "sub zone code" in keys and "sub zone name" in keys:
        return "sub_zone"
    if "zone code" in keys and "zone name" in keys:
        return "zone"
    if keys & {"base unit code", "baseunit code", "unit code", "base unit name", "unit name"}:
        return "base_unit"
    return None


def _status_active(status: str | None) -> bool:
    s = _norm_key(status or "")
    if not s:
        return True
    return s not in {"inactive", "disabled", "archived", "deleted", "no"}


def _get_by_code(model, code: str | None):
    if not code:
        return None
    return model.query.filter_by(code=code).first()


class _ParentIndex:
    """Resolve a CRM property-name parent onto TicketProperty rows."""

    def __init__(self, properties: list[TicketProperty]):
        self.by_name: dict[str, list[TicketProperty]] = defaultdict(list)
        for p in properties:
            self.by_name[_norm_key(p.name)].append(p)

    def refresh_one(self, prop: TicketProperty):
        bucket = self.by_name[_norm_key(prop.name)]
        if prop not in bucket:
            bucket.append(prop)

    def resolve(
        self,
        property_name: str,
        *,
        zone_name: str = "",
        sub_zone_name: str = "",
    ) -> tuple[TicketProperty | None, str | None]:
        name = _norm_key(property_name)
        if not name:
            return None, "missing property name"
        cands = list(self.by_name.get(name) or [])
        if not cands:
            return None, f"no property named {property_name!r}"
        if len(cands) == 1:
            return cands[0], None

        scored: list[TicketProperty] = []
        for p in cands:
            area = p.area or ""
            if place_similar(area, zone_name) or place_similar(area, sub_zone_name):
                scored.append(p)
        if len(scored) == 1:
            return scored[0], None
        if len(scored) > 1:
            return None, (
                f"ambiguous property {property_name!r} "
                f"(matched {len(scored)} sites by area)"
            )
        return None, (
            f"ambiguous property {property_name!r} "
            f"({len(cands)} sites; area did not match zone/sub-zone)"
        )


def _ensure_project_for_client(client_name: str) -> TicketProject:
    key = _norm_key(client_name)
    existing = TicketProject.query.filter(TicketProject.is_active.is_(True)).all()
    for p in existing:
        if _norm_key(p.client_name or "") == key or _norm_key(p.name or "") == key:
            return p
    proj = TicketProject(name=client_name.strip(), client_name=client_name.strip(), is_active=True)
    db.session.add(proj)
    db.session.flush()
    return proj


def _code_owned_elsewhere(model, code: str | None, parent_field: str, parent_id: int):
    """Return an existing row if `code` is already used under a different parent."""
    if not code:
        return None
    existing = _get_by_code(model, code)
    if existing is not None and getattr(existing, parent_field) != parent_id:
        return existing
    return None


def _goc_zone(property_id: int, name: str, code: str | None = None) -> tuple[TicketZone, bool]:
    created = False
    z = None
    if code:
        z = _get_by_code(TicketZone, code)
        # Never reparent a zone that already belongs to another property.
        if z is not None and z.property_id != property_id:
            z = None
            code = None
    if z is None:
        z = TicketZone.query.filter_by(property_id=property_id, name=name).first()
    if z is None:
        z = TicketZone(property_id=property_id, name=name, code=code, is_active=True)
        db.session.add(z)
        db.session.flush()
        created = True
    else:
        z.name = name or z.name
        if code:
            z.code = code
        z.is_active = True
    return z, created


def _goc_sub_zone(zone_id: int, name: str, code: str | None = None) -> tuple[TicketSubZone, bool]:
    created = False
    sz = None
    if code:
        sz = _get_by_code(TicketSubZone, code)
        if sz is not None and sz.zone_id != zone_id:
            sz = None
            code = None
    if sz is None:
        sz = TicketSubZone.query.filter_by(zone_id=zone_id, name=name).first()
    if sz is None:
        sz = TicketSubZone(zone_id=zone_id, name=name, code=code, is_active=True)
        db.session.add(sz)
        db.session.flush()
        created = True
    else:
        sz.name = name or sz.name
        if code:
            sz.code = code
        sz.is_active = True
    return sz, created


def _goc_unit(sub_zone_id: int, name: str, code: str | None = None) -> tuple[TicketBaseUnit, bool]:
    created = False
    u = None
    if code:
        u = _get_by_code(TicketBaseUnit, code)
        if u is not None and u.sub_zone_id != sub_zone_id:
            u = None
            code = None
    if u is None:
        u = TicketBaseUnit.query.filter_by(sub_zone_id=sub_zone_id, name=name).first()
    if u is None:
        u = TicketBaseUnit(sub_zone_id=sub_zone_id, name=name, code=code, is_active=True)
        db.session.add(u)
        db.session.flush()
        created = True
    else:
        u.name = name or u.name
        if code:
            u.code = code
        u.is_active = True
    return u, created


def import_location_rows(
    *,
    property_rows: list[dict[str, str]] | None = None,
    zone_rows: list[dict[str, str]] | None = None,
    sub_zone_rows: list[dict[str, str]] | None = None,
    base_unit_rows: list[dict[str, str]] | None = None,
    project_id: int | None = None,
    standalone: bool = False,
) -> dict:
    """Upsert hierarchy rows. Merge-only: does not delete existing seed data."""
    counts = {
        "properties_created": 0,
        "properties_updated": 0,
        "zones_created": 0,
        "zones_updated": 0,
        "sub_zones_created": 0,
        "sub_zones_updated": 0,
        "base_units_created": 0,
        "base_units_updated": 0,
        "projects_created": 0,
        "properties_linked": 0,
    }
    unresolved: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    # ── Properties ──────────────────────────────────────────
    for raw in property_rows or []:
        rec = _map_row(raw, PROPERTY_HEADERS)
        code = _blank(rec.get("code"))
        name = _blank(rec.get("name"))
        if not code or not name:
            skipped.append({"level": "property", "reason": "missing code or name", "row": name or code or ""})
            continue
        prop = _get_by_code(TicketProperty, code)
        created = False
        if prop is None:
            prop = TicketProperty(code=code, name=name)
            db.session.add(prop)
            created = True
        prop.name = name
        prop.area = _blank(rec.get("area"))
        prop.city = _blank(rec.get("city"))
        prop.country = _blank(rec.get("country"))
        prop.client_name = _blank(rec.get("client_name"))
        prop.property_type = _blank(rec.get("property_type"))
        prop.criticality = _blank(rec.get("criticality"))
        prop.ownership_type = _blank(rec.get("ownership_type"))
        prop.plot_no = _blank(rec.get("plot_no"))
        prop.external_ref = _blank(rec.get("external_ref"))
        prop.status = _blank(rec.get("status"))
        prop.initiation_date = _parse_date(rec.get("initiation_date"))
        prop.is_active = _status_active(prop.status)
        _apply_row_coords(prop, rec)
        db.session.flush()
        if created:
            if project_id and not standalone:
                prop.project_id = project_id
            counts["properties_created"] += 1
        else:
            counts["properties_updated"] += 1

    db.session.flush()

    index = _ParentIndex(TicketProperty.query.all())
    zone_code_by_pair: dict[tuple[str, str], str] = {}

    # ── Zones from Zone.xls ─────────────────────────────────
    for raw in zone_rows or []:
        rec = _map_row(raw, ZONE_HEADERS)
        code = _blank(rec.get("code"))
        name = _blank(rec.get("name"))
        pname = _blank(rec.get("property"))
        if not name or not pname:
            skipped.append({"level": "zone", "reason": "missing name or property", "row": name or ""})
            continue
        parent, err = index.resolve(pname, zone_name=name)
        if parent is None:
            unresolved.append({"level": "zone", "name": name, "property": pname, "code": code or "", "reason": err or ""})
            continue
        stolen = _code_owned_elsewhere(TicketZone, code, "property_id", parent.id)
        if stolen is not None:
            unresolved.append({
                "level": "zone",
                "name": name,
                "property": pname,
                "code": code or "",
                "reason": f"zone code {code!r} already belongs to another property",
            })
            continue
        z, created = _goc_zone(parent.id, name, code)
        if created:
            counts["zones_created"] += 1
        else:
            counts["zones_updated"] += 1
        if code:
            zone_code_by_pair[(_norm_key(pname), _norm_key(name))] = code

    db.session.flush()

    # ── Sub-zones (synthesize missing zones) ────────────────
    for raw in sub_zone_rows or []:
        rec = _map_row(raw, SUBZONE_HEADERS)
        code = _blank(rec.get("code"))
        name = _blank(rec.get("name"))
        pname = _blank(rec.get("property"))
        zname = _blank(rec.get("zone"))
        if not name or not pname or not zname:
            skipped.append({"level": "sub_zone", "reason": "missing name, property, or zone", "row": name or ""})
            continue
        parent, err = index.resolve(pname, zone_name=zname, sub_zone_name=name)
        if parent is None:
            unresolved.append({
                "level": "sub_zone",
                "name": name,
                "zone": zname,
                "property": pname,
                "code": code or "",
                "reason": err or "",
            })
            continue
        zcode = zone_code_by_pair.get((_norm_key(pname), _norm_key(zname)))
        zone, z_created = _goc_zone(parent.id, zname, zcode)
        if z_created:
            counts["zones_created"] += 1
        stolen = _code_owned_elsewhere(TicketSubZone, code, "zone_id", zone.id)
        if stolen is not None:
            unresolved.append({
                "level": "sub_zone",
                "name": name,
                "zone": zname,
                "property": pname,
                "code": code or "",
                "reason": f"sub-zone code {code!r} already belongs to another zone",
            })
            continue
        sz, created = _goc_sub_zone(zone.id, name, code)
        if created:
            counts["sub_zones_created"] += 1
        else:
            counts["sub_zones_updated"] += 1

    db.session.flush()

    # ── Base units ──────────────────────────────────────────
    for raw in base_unit_rows or []:
        rec = _map_row(raw, UNIT_HEADERS)
        code = _blank(rec.get("code"))
        name = _blank(rec.get("name"))
        pname = _blank(rec.get("property"))
        zname = _blank(rec.get("zone"))
        szname = _blank(rec.get("sub_zone"))
        if not name or not pname or not zname or not szname:
            skipped.append({"level": "base_unit", "reason": "missing parents or name", "row": name or ""})
            continue
        parent, err = index.resolve(pname, zone_name=zname, sub_zone_name=szname)
        if parent is None:
            unresolved.append({
                "level": "base_unit",
                "name": name,
                "sub_zone": szname,
                "zone": zname,
                "property": pname,
                "code": code or "",
                "reason": err or "",
            })
            continue
        zone, z_created = _goc_zone(parent.id, zname)
        if z_created:
            counts["zones_created"] += 1
        sz, sz_created = _goc_sub_zone(zone.id, szname)
        if sz_created:
            counts["sub_zones_created"] += 1
        stolen = _code_owned_elsewhere(TicketBaseUnit, code, "sub_zone_id", sz.id)
        if stolen is not None:
            unresolved.append({
                "level": "base_unit",
                "name": name,
                "sub_zone": szname,
                "zone": zname,
                "property": pname,
                "code": code or "",
                "reason": f"base unit code {code!r} already belongs to another sub-zone",
            })
            continue
        unit, created = _goc_unit(sz.id, name, code)
        _apply_row_coords(unit, rec)
        if created:
            counts["base_units_created"] += 1
        else:
            counts["base_units_updated"] += 1

    # ── Link properties to projects ─────────────────────────
    imported_codes = {
        _blank(_map_row(r, PROPERTY_HEADERS).get("code"))
        for r in (property_rows or [])
    }
    imported_codes.discard(None)
    props = (
        TicketProperty.query.filter(TicketProperty.code.in_(imported_codes)).all()
        if imported_codes else []
    )
    if standalone:
        pass
    elif project_id:
        for prop in props:
            if prop.project_id is None:
                prop.project_id = project_id
                counts["properties_linked"] += 1
    else:
        known_project_ids = {p.id for p in TicketProject.query.all()}
        for prop in props:
            client = _blank(prop.client_name)
            if not client:
                continue
            proj = _ensure_project_for_client(client)
            if proj.id not in known_project_ids:
                counts["projects_created"] += 1
                known_project_ids.add(proj.id)
            if prop.project_id is None:
                prop.project_id = proj.id
                counts["properties_linked"] += 1

    db.session.commit()
    return {
        "counts": counts,
        "unresolved": unresolved,
        "skipped": skipped,
        "unresolved_count": len(unresolved),
    }


def import_location_files(files: dict[str, Path | bytes | None]) -> dict:
    """Parse named SpreadsheetML files and upsert. Keys: property, zone, sub_zone, base_unit."""
    parsed: dict[str, list[dict[str, str]]] = {}
    kinds = {
        "property": PROPERTY_HEADERS,
        "zone": ZONE_HEADERS,
        "sub_zone": SUBZONE_HEADERS,
        "base_unit": UNIT_HEADERS,
    }
    for key in kinds:
        src = files.get(key)
        if not src:
            parsed[key] = []
            continue
        headers, rows = parse_spreadsheetml(src)
        if not headers:
            parsed[key] = []
            continue
        detected = detect_kind(headers)
        if detected and detected != key:
            raise ValueError(f"{key} file looks like a {detected} export (headers: {headers[:6]})")
        parsed[key] = rows

    if not any(parsed.values()):
        raise ValueError("No location rows found. Upload Property / Zone / Sub Zone / BaseUnit SpreadsheetML files.")

    return import_location_rows(
        property_rows=parsed["property"],
        zone_rows=parsed["zone"],
        sub_zone_rows=parsed["sub_zone"],
        base_unit_rows=parsed["base_unit"],
    )
