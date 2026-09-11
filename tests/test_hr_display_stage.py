"""HR list cards show the current approval stage (With HR / With GM / …)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hr_display_js_exposes_stage_label():
    js = (ROOT / "static/js/hr-display.js").read_text(encoding="utf-8")
    assert "function stageLabel" in js
    assert "hr_mgmt_hr_head_office: 'With HR'" in js
    assert "hr_mgmt_gm: 'With GM'" in js


def test_hr_pending_review_cards_include_stage_pill():
    html = (ROOT / "module_hr/templates/hr_pending_review.html").read_text(encoding="utf-8")
    assert "stage-pill" in html
    assert "Stage:" in html
    assert "hrDisplay.stageLabel" in html


def test_hr_gm_approval_cards_include_stage_pill():
    html = (ROOT / "module_hr/templates/hr_gm_approval.html").read_text(encoding="utf-8")
    assert "stage-pill" in html
    assert "hrDisplay.stageLabel" in html
