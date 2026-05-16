"""
Build module_ticketing/data/fault_codes.json from the Injaaz fault-code spreadsheet.

The distributed .xls is often XML SpreadsheetML; parsing lives in module_ticketing.fault_catalog_build.
Usage:
  python scripts/build_fault_catalog.py [path/to/Fault_Code.xls]

Default source (if present): module_ticketing/data/Fault_Code.xls
Otherwise: Downloads path on Windows — override with CLI arg.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from module_ticketing.fault_catalog_build import DEFAULT_JSON_PATH, rebuild_from_path


def default_source_path() -> Path | None:
    bundled = ROOT / "module_ticketing" / "data" / "Fault_Code.xls"
    if bundled.exists():
        return bundled
    home = Path.home() / "Downloads" / "Fault Code.xls"
    if home.exists():
        return home
    return None


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else default_source_path()
    if not src or not src.exists():
        print(
            "Fault spreadsheet not found. Pass path as argv[1] or place module_ticketing/data/Fault_Code.xls",
            file=sys.stderr,
        )
        return 1
    n = rebuild_from_path(src, src.name)
    print(f"Wrote {n} rows to {DEFAULT_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
