"""Load bundled fault-code catalog (spreadsheet → JSON) for work order classification."""

from __future__ import annotations

import json
from pathlib import Path

_CACHE: dict | None | bool = False  # False = not attempted; None = missing file


def invalidate_bundle_cache() -> None:
    global _CACHE
    _CACHE = False


def load_bundle() -> dict | None:
    """
    Return bundle dict with fault_catalog, categories_by_service_group, service_groups,
    or None if no data file.
    """
    global _CACHE
    if _CACHE is not False:
        return None if _CACHE is None else _CACHE

    path = Path(__file__).resolve().parent / "data" / "fault_codes.json"
    if not path.exists():
        _CACHE = None
        return None

    raw = json.loads(path.read_text(encoding="utf-8"))
    cat_map = raw.get("categories_by_service_group") or {}
    sgs = sorted(cat_map.keys(), key=str.lower)

    _CACHE = {
        "fault_catalog": raw.get("fault_catalog") or [],
        "categories_by_service_group": cat_map,
        "service_groups": sgs,
        "catalog_source_file": raw.get("source_file"),
        "catalog_version": raw.get("version", 1),
    }
    return _CACHE
