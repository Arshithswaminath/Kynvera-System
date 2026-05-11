"""
HR sign-off activity timeline for live updates on ?edit= views.

Derives a chronological event list from submission.form_data (no image payloads in the API).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from common.datetime_utils import normalize_legacy_hr_iso_to_utc_z

# Mirrors workflow access VALID_DESIGNATIONS for HR activity polling.

_WORKFLOW_LABELS: dict[str, str] = {
    "replacement_signoff": "Awaiting colleague / coverage signatures",
    "hr_mgmt_supervisor": "Awaiting reporting supervisor sign-off",
    "hr_mgmt_operations_manager": "Awaiting operations manager sign-off",
    "hr_mgmt_reporting_manager": "Awaiting reporting manager sign-off",
    "hr_mgmt_gm": "Awaiting general manager sign-off",
    "hr_mgmt_hr_head_office": "With HR (head office) for final sign-off",
    "hr_review": "With HR for review",
    "gm_review": "With general manager for review",
    "approved": "Approved — workflow complete",
    "completed": "Completed",
}


def hr_workflow_status_label(workflow_status: str | None, submission_status: str | None) -> str:
    w = (workflow_status or "").strip().lower()
    s = (submission_status or "").strip().lower()
    if w == "withdrawn":
        return "Withdrawn"
    if w in ("approved",) or s in ("completed",):
        return _WORKFLOW_LABELS.get(w) or "Approved — workflow complete"
    return _WORKFLOW_LABELS.get(w) or "In progress"


def _actor_routed(s: dict[str, Any]) -> str:
    return (
        (s.get("signed_by_name") or s.get("display_name") or s.get("username") or "").strip()
        or "Signatory"
    )


def _event_sort_ts(at: Any) -> float:
    """
    Monotonic instant for ordering timeline events.

    ``form_data`` timestamps mix ``datetime.isoformat()`` shapes (space vs ``T``,
    with/without ``Z``). Lexicographic sort on raw strings mis-orders them; we
    normalize then compare as UTC epoch seconds.
    """
    s = str(at or "").strip()
    if not s:
        return 0.0
    z = normalize_legacy_hr_iso_to_utc_z(s)
    to_parse = z if z else s.replace(" ", "T", 1)
    try:
        if to_parse.endswith("Z"):
            dt = datetime.fromisoformat(to_parse[:-1]).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        dt = datetime.fromisoformat(to_parse)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _dedupe_events(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in raw:
        t = (
            str(e.get("kind") or ""),
            str(e.get("at") or ""),
            str(e.get("actor") or ""),
            str(e.get("label") or ""),
        )
        if t in seen:
            continue
        seen.add(t)
        out.append(e)
    return out


def _mgmt_chain_has_signed_steps(chain: dict[str, Any]) -> bool:
    steps = chain.get("steps")
    if not isinstance(steps, list):
        return False
    return any(isinstance(st, dict) and bool(st.get("signature")) for st in steps)


def compute_hr_signoff_activity(
    form_data: dict[str, Any] | None,
    workflow_status: str | None,
    submission_status: str | None,
) -> tuple[list[dict[str, Any]], str]:
    fd = form_data if isinstance(form_data, dict) else {}
    raw: list[dict[str, Any]] = []

    sub_at = fd.get("submitted_at")
    if sub_at:
        who = (fd.get("submitted_by_name") or "").strip() or "Submitter"
        raw.append(
            {
                "kind": "submitted",
                "at": str(sub_at).strip(),
                "label": "Form submitted",
                "actor": who,
                "detail": "",
            }
        )

    routed = fd.get("_routed_signoffs")
    if isinstance(routed, dict):
        slots = routed.get("slots")
        if isinstance(slots, list):
            for grp in slots:
                if not isinstance(grp, dict):
                    continue
                label = (grp.get("label") or grp.get("key") or "Colleague").strip()
                signers = grp.get("signers")
                if not isinstance(signers, list):
                    continue
                for s in signers:
                    if not isinstance(s, dict) or not s.get("signature"):
                        continue
                    raw.append(
                        {
                            "kind": "colleague_signed",
                            "at": str(s.get("signed_at") or "").strip(),
                            "label": f"{label} signed",
                            "actor": _actor_routed(s),
                            "detail": (s.get("comments") or "").strip(),
                        }
                    )

    routed_had_replacement = False
    if isinstance(routed, dict):
        for g in routed.get("slots") or []:
            if isinstance(g, dict) and g.get("key") == "replacement":
                routed_had_replacement = True
                break
    if not routed_had_replacement:
        legacy_rep = fd.get("replacement_signers")
        if isinstance(legacy_rep, list):
            for s in legacy_rep:
                if not isinstance(s, dict) or not s.get("signature"):
                    continue
                raw.append(
                    {
                        "kind": "colleague_signed",
                        "at": str(s.get("signed_at") or "").strip(),
                        "label": "Coverage / replacement signed",
                        "actor": (
                            (s.get("display_name") or s.get("username") or "").strip() or "Colleague"
                        ),
                        "detail": (s.get("comments") or "").strip(),
                    }
                )

    chain = fd.get("hr_mgmt_chain")
    use_chain = isinstance(chain, dict) and _mgmt_chain_has_signed_steps(chain)
    if use_chain and isinstance(chain, dict):
        steps = chain.get("steps")
        if isinstance(steps, list):
            for st in steps:
                if not isinstance(st, dict) or not st.get("signature"):
                    continue
                pdf_label = (st.get("pdf_label") or st.get("key") or "Management").strip()
                who = (st.get("signed_by_name") or "").strip() or "Signatory"
                raw.append(
                    {
                        "kind": "management_signed",
                        "at": str(st.get("signed_at") or "").strip(),
                        "label": f"{pdf_label} signed off",
                        "actor": who,
                        "detail": (st.get("comments") or "").strip(),
                    }
                )
    else:
        if fd.get("gm_signature") and fd.get("gm_approved_at"):
            raw.append(
                {
                    "kind": "management_signed",
                    "at": str(fd.get("gm_approved_at") or "").strip(),
                    "label": "General manager signed off",
                    "actor": (fd.get("gm_approved_by_name") or "").strip() or "General manager",
                    "detail": (fd.get("gm_comments") or "").strip(),
                }
            )
        if fd.get("hr_signature") and fd.get("hr_reviewed_at"):
            raw.append(
                {
                    "kind": "management_signed",
                    "at": str(fd.get("hr_reviewed_at") or "").strip(),
                    "label": "HR signed off",
                    "actor": (fd.get("hr_reviewed_by_name") or "").strip() or "HR",
                    "detail": (fd.get("hr_comments") or fd.get("hr_remarks") or "").strip(),
                }
            )

    raw = _dedupe_events(raw)

    # Chronological ascending, then reverse so UI reads top = latest (end),
    # bottom = earliest (start).
    raw.sort(
        key=lambda e: (
            _event_sort_ts(e.get("at")),
            str(e.get("kind") or ""),
            str(e.get("label") or ""),
        )
    )
    display = list(reversed(raw))

    wf = (workflow_status or "").strip()
    st = (submission_status or "").strip()
    canonical_events = sorted(
        (
            (
                str(e.get("kind") or ""),
                str(e.get("at") or ""),
                str(e.get("actor") or ""),
                str(e.get("label") or ""),
                (str(e.get("detail") or ""))[:800],
            )
            for e in raw
        ),
        key=lambda x: (x[1], x[0], x[2]),
    )
    payload = {
        "wf": wf,
        "st": st,
        "ev": canonical_events,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    display_out: list[dict[str, Any]] = []
    for e in display:
        ee = dict(e)
        at_raw = ee.get("at")
        if at_raw:
            normalized = normalize_legacy_hr_iso_to_utc_z(str(at_raw).strip())
            if normalized:
                ee["at"] = normalized
        display_out.append(ee)

    return display_out, fingerprint
