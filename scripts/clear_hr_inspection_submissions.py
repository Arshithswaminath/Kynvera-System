"""
Delete submission rows so dashboards and “All Submissions” show a clean slate.

Modes (pick one).
  Default: HR (hr_*) + inspection (hvac_mep, civil, cleaning).
  --inspection-only / --hr-only: subset.
  --all --yes: every row in `submissions` (catalog_material, procurement, etc.) — IRREVERSIBLE.

Examples (project root; stop `python Injaaz.py` if SQLite reports "database is locked"):
  python scripts/clear_hr_inspection_submissions.py --inspection-only
  python scripts/clear_hr_inspection_submissions.py --hr-only
  python scripts/clear_hr_inspection_submissions.py
  python scripts/clear_hr_inspection_submissions.py --all --yes

Also deletes notifications whose submission_id matches removed rows,
and removes local File.file_path files under this project when present.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import or_

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Injaaz import create_app  # noqa: E402
from app.models import db, File, Notification, Submission  # noqa: E402

INSPECTION_MODULES = ("hvac_mep", "civil", "cleaning")


def _unlink_local_files(file_rows: list[File]) -> tuple[int, int]:
    removed, missing = 0, 0
    for f in file_rows:
        p = getattr(f, "file_path", None)
        if not p or not isinstance(p, str):
            continue
        ap = os.path.normpath(os.path.abspath(p))
        proj = os.path.normpath(PROJECT_ROOT)
        if not ap.startswith(proj):
            continue
        try:
            if os.path.isfile(ap):
                os.remove(ap)
                removed += 1
            else:
                missing += 1
        except OSError:
            missing += 1
    return removed, missing


def _mode_filter(inspection_only: bool, hr_only: bool):
    if inspection_only:
        return Submission.module_type.in_(INSPECTION_MODULES)
    if hr_only:
        return Submission.module_type.startswith("hr_")
    return or_(
        Submission.module_type.startswith("hr_"),
        Submission.module_type.in_(INSPECTION_MODULES),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear submissions from the database.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--inspection-only",
        action="store_true",
        help="Only HVAC/Civil/Cleaning.",
    )
    g.add_argument("--hr-only", action="store_true", help="Only submissions with module_type hr_*.")
    g.add_argument(
        "--all",
        action="store_true",
        help="Delete ALL submissions (every module_type). Requires --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm irreversible delete (required when using --all).",
    )
    args = parser.parse_args()

    if args.all and not args.yes:
        print("Refusing: --all deletes every submission. Re-run with --yes to confirm.")
        return 2

    app = create_app()
    with app.app_context():
        if args.all:
            mode_label = "all submissions"
            query = Submission.query
        else:
            mode_label = (
                "inspection (HVAC / Civil / Cleaning)"
                if args.inspection_only
                else "HR"
                if args.hr_only
                else "HR + inspection (HVAC / Civil / Cleaning)"
            )
            query = Submission.query.filter(_mode_filter(args.inspection_only, args.hr_only))

        subs = query.all()
        if not subs:
            print(f"No {mode_label} found; nothing to do.")
            return 0

        sub_pk = [s.id for s in subs]
        file_rows = File.query.filter(File.submission_id.in_(sub_pk)).all()

        id_strs = [s.submission_id for s in subs]
        notif_n = 0
        if id_strs:
            # Chunk IN lists for very large deletes (SQLite param limit ~999 typical)
            chunk = 400
            for i in range(0, len(id_strs), chunk):
                part = id_strs[i : i + chunk]
                notif_n += Notification.query.filter(Notification.submission_id.in_(part)).delete(
                    synchronize_session=False
                )

        rm_files, miss_files = _unlink_local_files(file_rows)
        n = len(subs)
        for s in subs:
            db.session.delete(s)
        db.session.commit()

        print(f"Deleted {n} {mode_label}.")
        print(f"Removed {notif_n} notification row(s) referencing those submission IDs.")
        print(f"Local files removed: {rm_files}; paths not found or skipped: {miss_files}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
