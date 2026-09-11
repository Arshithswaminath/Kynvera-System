"""Keep extra text when normalizing 'Signed & Verified — {name}' comments."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js" / "approval_comment.js"

CASES = [
    ("HR", "HR", "Signed & Verified — HR, approved.", "Signed & Verified — HR — approved."),
    ("HR", "HR", "Signed & Verified — HR — approved.", "Signed & Verified — HR — approved."),
    ("HR", "HR", "Signed & Verified — HR", "Signed & Verified — HR"),
    ("HR", "HR", "Please process today", "Signed & Verified — HR — Please process today"),
    ("HR", "HR", "Signed & Verified please", "Signed & Verified — HR — please"),
    ("Taha Al", "taha", "Signed & Verified — Taha, ok to proceed.", "Signed & Verified — Taha — ok to proceed."),
]


def test_ensure_signed_verified_keeps_appended_note():
    if not JS.is_file():
        pytest.fail(f"missing {JS}")
    script = """
const fs = require('fs');
const vm = require('vm');
const path = process.argv[1];
const cases = JSON.parse(process.argv[2]);
const code = fs.readFileSync(path, 'utf8');
const ctx = {};
ctx.window = ctx;
ctx.globalThis = ctx;
vm.runInNewContext(code, ctx);
const api = ctx.InjaazApprovalComment;
const failures = [];
for (const [fullName, username, inp, want] of cases) {
  api.setUserContext({ full_name: fullName, username: username, default_comment: '' });
  const got = api.ensureSignedVerifiedComment(inp);
  if (got !== want) failures.push({ fullName, inp, want, got });
}
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
}
"""
    r = subprocess.run(
        ["node", "-e", script, str(JS), json.dumps(CASES)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr or r.stdout
