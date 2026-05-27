"""
DB cleanup: replace legacy supervisor_comments value 'Testing' with 'Approved'.

`supervisor_comments` lives inside the JSON `submissions.form_data` column.
This script scans every submission, and where the supervisor_comments value
is exactly 'Testing' (case-insensitive, trimmed), it rewrites it to 'Approved'.

Run modes:
    python scripts/cleanup_supervisor_comments.py            # DRY RUN (default)
    python scripts/cleanup_supervisor_comments.py --apply    # actually persist

Optional flags:
    --from VALUE   override the value to match (default: 'Testing')
    --to   VALUE   override the replacement (default: 'Approved')
    --module hvac_mep|civil|cleaning   restrict to a single module_type
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, Submission
from sqlalchemy.orm.attributes import flag_modified


def normalize(value):
    if value is None:
        return ''
    return str(value).strip().lower()


def run(match_value, replacement, module_filter, apply_changes):
    app = create_app()
    matched = 0
    updated = 0
    skipped_no_form_data = 0
    examples = []

    needle = normalize(match_value)

    with app.app_context():
        q = Submission.query
        if module_filter:
            q = q.filter(Submission.module_type == module_filter)

        for sub in q.yield_per(200):
            form_data = sub.form_data
            if not isinstance(form_data, dict):
                skipped_no_form_data += 1
                continue

            current = form_data.get('supervisor_comments')
            if normalize(current) != needle:
                continue

            matched += 1
            if len(examples) < 10:
                examples.append((sub.submission_id, sub.module_type, current))

            if apply_changes:
                form_data['supervisor_comments'] = replacement
                sub.form_data = form_data
                flag_modified(sub, 'form_data')
                updated += 1

        if apply_changes:
            db.session.commit()

    print('--- DB cleanup: supervisor_comments ---')
    print(f"Match value     : {match_value!r}")
    print(f"Replacement     : {replacement!r}")
    print(f"Module filter   : {module_filter or '(all)'}")
    print(f"Mode            : {'APPLY' if apply_changes else 'DRY RUN'}")
    print(f"Submissions hit : {matched}")
    print(f"Submissions upd : {updated}")
    print(f"Skipped (no JSON form_data): {skipped_no_form_data}")
    if examples:
        print('First matches:')
        for sid, mtype, current in examples:
            print(f'  - {sid}  [{mtype}]  current={current!r}')
    if not apply_changes and matched:
        print('\nRe-run with --apply to persist the changes.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Persist changes (default: dry run).')
    parser.add_argument('--from', dest='match_value', default='Testing',
                        help="Value to match in supervisor_comments (default: 'Testing').")
    parser.add_argument('--to', dest='replacement', default='Approved',
                        help="Replacement value (default: 'Approved').")
    parser.add_argument('--module', dest='module', default=None,
                        choices=['hvac_mep', 'civil', 'cleaning'],
                        help='Optional: restrict to a specific module_type.')
    args = parser.parse_args()

    run(args.match_value, args.replacement, args.module, args.apply)
