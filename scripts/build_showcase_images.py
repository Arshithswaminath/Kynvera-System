#!/usr/bin/env python3
"""Build web-ready screenshots for the public /applications showcase.

Reads captures produced by ``scripts/capture_full_page_screenshots.py`` and
writes downscaled WebP files into ``static/images/kynvera/showcase/`` under the
semantic names that ``common/showcase.py`` expects.

Usage:

    # Operations Suite (this repo's own captures)
    python scripts/build_showcase_images.py --set ops \\
        --source screenshots/full_pages/desktop_1920x1080_20260729_1713

    # Fire System — capture from the Fire worktree first (that script reads routes
    # from the app it imports), then point --source at the folder it produced
    python scripts/build_showcase_images.py --set fire \\
        --source <fire-worktree>/screenshots/full_pages/fire_showcase

    # Any single file, explicit target name
    python scripts/build_showcase_images.py --one path/to/shot.png --as fire-dashboard.webp
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "images" / "kynvera" / "showcase"

TARGET_WIDTH = 1600
WEBP_QUALITY = 82

# source file name in the capture folder -> showcase file name
SETS: dict[str, dict[str, str]] = {
    "ops": {
        "hr.png": "ops-hr.webp",
        "finance.png": "ops-finance.webp",
        "tickets__analytics.png": "ops-tickets-analytics.webp",
        "operations.png": "ops-operations.webp",
        "store__materials.png": "ops-store.webp",
        "workflow__pending-reviews.png": "ops-approvals.webp",
    },
    # Best-guess route names for the Fire System capture; adjust to match that app.
    "fire": {
        "dashboard.png": "fire-dashboard.webp",
        "assets.png": "fire-assets.webp",
        "inspection.png": "fire-inspection.webp",
        "maintenance.png": "fire-maintenance.webp",
        "reports.png": "fire-report.webp",
    },
}


def convert(src: Path, dest_name: str) -> int:
    """Downscale and encode one capture. Returns bytes written."""
    with Image.open(src) as img:
        img = img.convert("RGB")
        if img.width > TARGET_WIDTH:
            height = round(img.height * TARGET_WIDTH / img.width)
            img = img.resize((TARGET_WIDTH, height), Image.LANCZOS)
        dest = OUT_DIR / dest_name
        img.save(dest, "WEBP", quality=WEBP_QUALITY, method=6)
    return dest.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", choices=sorted(SETS), help="named mapping to build")
    parser.add_argument("--source", type=Path, help="capture folder holding the PNGs")
    parser.add_argument("--one", type=Path, help="convert a single file")
    parser.add_argument("--as", dest="as_name", help="showcase file name for --one (e.g. fire-dashboard.webp)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.one:
        if not args.as_name:
            parser.error("--one requires --as")
        if not args.one.is_file():
            print(f"missing: {args.one}")
            return 1
        size = convert(args.one, args.as_name)
        print(f"{args.one.name} -> {args.as_name} ({size // 1024} KB)")
        return 0

    if not args.set or not args.source:
        parser.error("provide --set and --source, or --one with --as")

    if not args.source.is_dir():
        print(f"not a folder: {args.source}")
        return 1

    mapping = SETS[args.set]
    built = skipped = total = 0
    for src_name, dest_name in mapping.items():
        src = args.source / src_name
        if not src.is_file():
            print(f"skip  {src_name} (not in capture folder)")
            skipped += 1
            continue
        size = convert(src, dest_name)
        total += size
        built += 1
        print(f"build {src_name} -> {dest_name} ({size // 1024} KB)")

    print(f"\n{built} built, {skipped} skipped, {total // 1024} KB total in {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
