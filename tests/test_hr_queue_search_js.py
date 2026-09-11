"""HR queue search matches employee, form reference, and form type."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPLAY_JS = ROOT / "static" / "js" / "hr-display.js"
SEARCH_JS = ROOT / "static" / "js" / "hr_queue_search.js"

ITEMS = [
    {
        "submission_id": "HR-LEAVE_APPLICATION-3F9A6A1C",
        "module_type": "hr_leave_application",
        "submitter_name": "Arshith",
        "form_data": {"employee_name": "Arshith", "leave_type": "sick", "employee_id": "E15"},
    },
    {
        "submission_id": "HR-PASSPORT_RELEASE-52032DBF",
        "module_type": "hr_passport_release",
        "submitter_display": "Arshith",
        "form_data": {"employee_name": "Arshith"},
    },
    {
        "submission_id": "HR-VISA_RENEWAL-8861C8D4",
        "module_type": "hr_visa_renewal",
        "submitter_name": "Arshith Swaminath",
        "form_data": {"employee_name": "Arshith Swaminath"},
    },
]


def test_queue_search_matches_employee_ref_and_type():
    assert DISPLAY_JS.is_file()
    assert SEARCH_JS.is_file()
    script = r"""
const fs = require('fs');
const vm = require('vm');
const displayPath = process.argv[1];
const searchPath = process.argv[2];
const items = JSON.parse(process.argv[3]);
const ctx = {};
ctx.window = ctx;
ctx.globalThis = ctx;
vm.runInNewContext(fs.readFileSync(displayPath, 'utf8'), ctx);
vm.runInNewContext(fs.readFileSync(searchPath, 'utf8'), ctx);
const api = ctx.HrQueueSearch;
const ids = (q) => api.filter(items, q).map((s) => s.submission_id);
const failures = [];
function expect(q, want) {
  const got = ids(q);
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    failures.push({ q, want, got });
  }
}
expect('', items.map((s) => s.submission_id));
expect('Arshith', items.map((s) => s.submission_id));
expect('3F9A6A1C', ['HR-LEAVE_APPLICATION-3F9A6A1C']);
expect('HR · 3F9A6A1C', ['HR-LEAVE_APPLICATION-3F9A6A1C']);
expect('leave', ['HR-LEAVE_APPLICATION-3F9A6A1C']);
expect('Leave Application', ['HR-LEAVE_APPLICATION-3F9A6A1C']);
expect('passport', ['HR-PASSPORT_RELEASE-52032DBF']);
expect('visa', ['HR-VISA_RENEWAL-8861C8D4']);
expect('swaminath', ['HR-VISA_RENEWAL-8861C8D4']);
expect('e15', ['HR-LEAVE_APPLICATION-3F9A6A1C']);
expect('arshith leave', ['HR-LEAVE_APPLICATION-3F9A6A1C']);
expect('zzzz-no-match', []);
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}
"""
    r = subprocess.run(
        ["node", "-e", script, str(DISPLAY_JS), str(SEARCH_JS), json.dumps(ITEMS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr or r.stdout


def test_queue_pages_include_search_field():
    pages = {
        ROOT / "module_hr/templates/hr_pending_review.html": "pendingListSearch",
        ROOT / "module_hr/templates/hr_approved_forms.html": "approvedListSearch",
        ROOT / "module_hr/templates/hr_gm_approval.html": "pendingListSearch",
        ROOT / "module_hr/templates/hr_my_requests.html": "myRequestsSearch",
    }
    for path, input_id in pages.items():
        html = path.read_text(encoding="utf-8")
        assert input_id in html, f"{path.name} missing {input_id}"
        assert "hr_queue_search.js" in html, f"{path.name} missing hr_queue_search.js"
        assert "Search employee, form, or type" in html
