"""Parse fault spreadsheets and persist module_ticketing/data/fault_codes.json."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}

DEFAULT_JSON_PATH = Path(__file__).resolve().parent / "data" / "fault_codes.json"


def _row_vals(row) -> list[str]:
    out: list[str] = []
    for cell in row.findall("ss:Cell", NS):
        data = cell.find("ss:Data", NS)
        out.append((data.text or "").strip() if data is not None else "")
    return out


def _dur_to_int(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    m = re.match(r"^(\d+)", raw)
    return int(m.group(1)) if m else None


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def suggested_title_display(name: str) -> str:
    n = _normalize(name).rstrip(".").strip()
    return n or ""


def suggested_work_description(
    *,
    name: str,
    fault_category: str,
    service_group: str,
    duration_mins: int | None,
    root_cause: str,
) -> str:
    lines = [
        "Technician checklist — investigate and confirm:",
        f"• Service group: {service_group}",
        f"• Category: {fault_category}",
        f"• Reported symptom / defect: {_normalize(name)}",
    ]
    if duration_mins is not None:
        lines.append(f"• Reference duration (minutes, informational): {duration_mins}")
    rc = _normalize(root_cause)
    if rc and rc.lower() != "not applicable":
        lines.append(f"• Root cause applicability guidance: {rc}")
    lines.extend(
        [
            "",
            "Document verified root cause, corrective actions, parts/tools used, and any follow-up required.",
            "If escalation is needed, capture photos and asset/equipment tag details.",
        ]
    )
    return "\n".join(lines)


def parse_fault_spreadsheet(path: Path) -> list[dict]:
    tree = ET.parse(path)
    rows_xml = tree.findall(".//ss:Row", NS)
    if not rows_xml:
        raise ValueError("No rows found (expected Spreadsheet XML).")
    hdr = _row_vals(rows_xml[0])
    expect = {"Fault Code", "Fault Code Name", "Fault Category", "Service Group"}
    if not expect.intersection(hdr):
        raise ValueError(f"Unexpected header row (need fault columns): {hdr}")

    idx = {h.strip(): i for i, h in enumerate(hdr) if h}
    ic = idx.get("Fault Code")
    iname = idx.get("Fault Code Name")
    icat = idx.get("Fault Category")
    isg = idx.get("Service Group")
    idur = idx.get("Duration (in mins)")
    irc = idx.get("Root Cause Applicability")
    if None in (ic, iname, icat, isg):
        raise ValueError(f"Missing required columns in: {hdr}")

    out_rows: list[dict] = []
    for seq, row in enumerate(rows_xml[1:], start=1):
        vals = _row_vals(row)
        if not vals or not vals[ic]:
            continue
        code = _normalize(vals[ic])
        name = _normalize(vals[iname]) if len(vals) > iname else ""
        cat = _normalize(vals[icat]) if len(vals) > icat else ""
        sg = _normalize(vals[isg]) if len(vals) > isg else ""
        dur_raw = vals[idur] if idur is not None and len(vals) > idur else ""
        dur = _dur_to_int(dur_raw)
        root = _normalize(vals[irc]) if irc is not None and len(vals) > irc else ""

        fault_pick = f"{code}: {name}"[:512]
        name_disp = name or code
        st = suggested_title_display(name_disp)
        wd = suggested_work_description(
            name=name_disp,
            fault_category=cat,
            service_group=sg,
            duration_mins=dur,
            root_cause=root,
        )

        out_rows.append(
            {
                "catalog_id": seq,
                "fault_code": code,
                "fault_code_name": name,
                "fault_category": cat,
                "service_group": sg,
                "duration_mins": dur,
                "root_cause_applicability": root or None,
                "fault_pick_value": fault_pick,
                "search_label": f"{name} · {cat} · {sg}" if name else f"{cat} · {sg}",
                "suggested_title": st[:255],
                "suggested_work_description": wd,
            }
        )
    return out_rows


def build_categories_index(rows: list[dict]) -> dict[str, list[str]]:
    buckets: dict[str, set[str]] = {}
    for r in rows:
        sg = r["service_group"]
        if not sg:
            continue
        buckets.setdefault(sg, set()).add(r["fault_category"])
    return {k: sorted(filter(None, v)) for k, v in sorted(buckets.items(), key=lambda x: x[0].lower())}


def build_fault_bundle(rows: list[dict], source_filename: str) -> dict:
    return {
        "version": 1,
        "source_file": source_filename,
        "fault_catalog": rows,
        "categories_by_service_group": build_categories_index(rows),
    }


def persist_fault_bundle(bundle: dict, dest_path: Path | None = None) -> Path:
    path = dest_path or DEFAULT_JSON_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    from module_ticketing import fault_catalog

    fault_catalog.invalidate_bundle_cache()

    return path


def rebuild_from_path(upload_path: Path, source_filename: str, dest_path: Path | None = None) -> int:
    rows = parse_fault_spreadsheet(upload_path)
    bundle = build_fault_bundle(rows, source_filename or upload_path.name)
    persist_fault_bundle(bundle, dest_path or DEFAULT_JSON_PATH)
    return len(rows)
