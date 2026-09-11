"""Per-form signature requirements shown on HR fill pages.

Management-chain length depends on the submitter's lane (technician / supervisor /
office staff) and whether a reporting manager is assigned. This catalog covers
the on-form / routed extras; chain steps come from ``get_mgmt_chain_ui_context``.
"""
from __future__ import annotations

from typing import Any

# Path fragment → form_type (same values as submit ``form_type``).
PATH_TO_FORM_TYPE: tuple[tuple[str, str], ...] = (
    ("/hr/leave-application-form", "leave_application"),
    ("/hr/commencement-form", "commencement"),
    ("/hr/duty-resumption-form", "duty_resumption"),
    ("/hr/contract-renewal-form", "contract_renewal"),
    ("/hr/performance-evaluation-form", "performance_evaluation"),
    ("/hr/grievance-form", "grievance"),
    ("/hr/interview-assessment-form", "interview_assessment"),
    ("/hr/passport-release-form", "passport_release"),
    ("/hr/staff-appraisal-form", "staff_appraisal"),
    ("/hr/station-clearance-form", "station_clearance"),
    ("/hr/visa-renewal-form", "visa_renewal"),
    ("/hr/asset-handover-form", "asset_handover"),
    ("/hr/termination-form", "termination"),
    ("/hr/long-vacation-form", "long_vacation"),
    ("/hr/leave-form", "leave"),
    ("/hr/asset-form", "asset"),
)

# you_now_count: signatures the submitter captures on this page.
# extras: additional people who sign on their own device (or a peer pad), not the chain.
FORM_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "leave_application": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [
            {
                "label": "Coverage colleague(s)",
                "optional": True,
                "note": "Only if you choose Yes — each person signs on their own device before the chain continues.",
            }
        ],
        "step2": (
            "Fill in leave details, add your employee signature, then submit. "
            "Coverage colleagues (if any) and the management chain sign later — see Signature status for the count."
        ),
    },
    "leave": {
        "you_now": None,
        "you_now_count": 0,
        "extras": [],
        "step2": "Submit this request. Your management chain signs after you submit.",
    },
    "duty_resumption": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [],
        "step2": (
            "Add your employee signature, then submit. Reporting manager, GM, and HR "
            "sign later in the approval chain — not on this page."
        ),
    },
    "visa_renewal": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [],
        "step2": "Add your employee signature, then submit. The management chain signs after you submit.",
    },
    "commencement": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [
            {
                "label": "Reporting To",
                "optional": False,
                "note": "Signs on their device. If they are already in your chain they sign once.",
            }
        ],
        "step2": (
            "Add your employee signature, then submit. Your Reporting To manager signs next "
            "(combined with the chain if they already appear there)."
        ),
    },
    "grievance": {
        "you_now": "Your complainant signature",
        "you_now_count": 1,
        "extras": [],
        "step2": "Add your complainant signature, then submit. HR and GM sign later in the approval chain.",
    },
    "passport_release": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [],
        "step2": "Add your employee signature, then submit. GM and HR sign later in the approval chain.",
    },
    "performance_evaluation": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [],
        "step2": "Add your employee signature, then submit. GM and HR sign later in the approval chain.",
    },
    "station_clearance": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [],
        "step2": "Add your employee signature, then submit. HR signs later in the approval chain.",
    },
    "asset_handover": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [
            {
                "label": "Taking-over employee",
                "optional": True,
                "note": "May sign on this page if they are with you; otherwise they can sign later.",
            }
        ],
        "step2": (
            "List assets, add your employee signature, then submit. The taking-over employee may sign here; "
            "HR signs later in the chain."
        ),
    },
    "asset": {
        "you_now": None,
        "you_now_count": 0,
        "extras": [],
        "step2": "Submit this request. Your management chain signs after you submit.",
    },
    "staff_appraisal": {
        "you_now": "Your employee signature",
        "you_now_count": 1,
        "extras": [
            {
                "label": "Appraiser / reviewer",
                "optional": True,
                "note": "Designate them to sign on their device before HR. Optional if HR will appraise directly.",
            }
        ],
        "step2": (
            "Add your employee signature, then submit. A designated appraiser (if you pick one) signs next, then the chain."
        ),
    },
    "contract_renewal": {
        "you_now": None,
        "you_now_count": 0,
        "extras": [
            {
                "label": "Contract evaluator",
                "optional": False,
                "note": "Signs on their device after you submit.",
            }
        ],
        "step2": "Designate the contract evaluator (they sign on their device), then submit. The management chain follows.",
    },
    "interview_assessment": {
        "you_now": None,
        "you_now_count": 0,
        "extras": [
            {
                "label": "Interviewer",
                "optional": False,
                "note": "Signs on their device, then chooses who receives the form next. Always finishes with GM and HR.",
            }
        ],
        "step2": "Assign the interviewer (they sign on their device). After they route the form it always finishes with GM and HR.",
    },
    "termination": {
        "you_now": None,
        "you_now_count": 0,
        "extras": [],
        "step2": "Submit this request. Your management chain signs after you submit.",
    },
    "long_vacation": {
        "you_now": None,
        "you_now_count": 0,
        "extras": [],
        "step2": "Submit this request. Your management chain signs after you submit.",
    },
}

_DEFAULT_SPEC: dict[str, Any] = {
    "you_now": "Your signature",
    "you_now_count": 1,
    "extras": [],
    "step2": "Add your signature if this form has a pad, then submit. The management chain signs after you submit.",
}


def form_type_from_path(path: str) -> str:
    p = (path or "").split("?", 1)[0]
    for fragment, form_type in PATH_TO_FORM_TYPE:
        if fragment in p:
            return form_type
    return ""


def spec_for_form_type(form_type: str | None) -> dict[str, Any]:
    key = (form_type or "").strip()
    spec = FORM_REQUIREMENTS.get(key)
    if spec:
        return spec
    return dict(_DEFAULT_SPEC)


def summarize_required_signatures(
    form_type: str | None,
    chain: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return counts for UI: you + required extras + management chain."""
    spec = spec_for_form_type(form_type)
    steps = [c for c in (chain or []) if isinstance(c, dict)]
    extra_required = sum(1 for e in spec.get("extras") or [] if not e.get("optional"))
    extra_optional = sum(1 for e in spec.get("extras") or [] if e.get("optional"))
    you = int(spec.get("you_now_count") or 0)
    chain_n = len(steps)
    return {
        "form_type": form_type or "",
        "you_now": spec.get("you_now"),
        "you_now_count": you,
        "extras": list(spec.get("extras") or []),
        "extra_required_count": extra_required,
        "extra_optional_count": extra_optional,
        "chain_count": chain_n,
        "chain_roles": [c.get("role_label") or "Signer" for c in steps],
        "min_total": you + extra_required + chain_n,
        "step2": spec.get("step2") or _DEFAULT_SPEC["step2"],
    }
