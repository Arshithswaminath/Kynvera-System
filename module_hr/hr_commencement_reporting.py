"""
Commencement form — Reporting To signature routing.

After submit, the person named in Reporting To must sign in the PDF block
(``reporting_to_signature`` / ``reporting_sign_date``). They are not added
to the management trail table.

* If that person is already in the submitter's management chain (fixed user
  or designation pool), they sign once in the chain and the signature is
  mirrored into the Reporting To block (dual-role hint).
* Otherwise they receive a pre-chain routed sign-off before management
  approvals begin.
"""
from __future__ import annotations

from typing import Any

from app.models import User, db
from module_hr.hr_management_chain import (
    MGMT_CHAIN_KEY,
    _active_hr_signers,
    _active_users_with_designation,
    user_allowed_to_sign_step,
)
from module_hr.hr_routed_signoffs import _build_signer_slots

REPORTING_TO_SIGNOFF_KEY = "_reporting_to_signoff"


def _signed_at_to_date_str(signed_at: str | None) -> str | None:
    if not signed_at:
        return None
    s = str(signed_at).strip()
    return s[:10] if len(s) >= 10 else None


def mgmt_chain_participant_ids(steps: list[dict[str, Any]]) -> set[int]:
    """User IDs that may sign any step on this chain."""
    ids: set[int] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        mode = step.get("signer_mode")
        if mode == "fixed_user":
            sid = step.get("signer_id")
            if sid is not None:
                try:
                    ids.add(int(sid))
                except (TypeError, ValueError):
                    pass
            continue
        gate = (step.get("designation_gate") or "").strip().lower()
        if gate == "operations_manager":
            for u in _active_users_with_designation("operations_manager"):
                ids.add(int(u.id))
        elif gate == "general_manager":
            for u in _active_users_with_designation("general_manager"):
                ids.add(int(u.id))
        elif gate in ("hr_head_office", "hr_manager"):
            for u in _active_hr_signers():
                ids.add(int(u.id))
    return ids


def find_mgmt_step_for_user(
    steps: list[dict[str, Any]], user_id: int
) -> dict[str, Any] | None:
    """Return the chain step this user is expected to sign, if any."""
    u = db.session.get(User, int(user_id))
    if not u:
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        if user_allowed_to_sign_step(u, step):
            return step
    return None


def dual_role_hint_for_user(form_data: dict[str, Any] | None, user_id: int) -> dict[str, Any] | None:
    """Hint payload for mgmt sign UI when user signs in two PDF places."""
    if not isinstance(form_data, dict):
        return None
    meta = form_data.get(REPORTING_TO_SIGNOFF_KEY)
    if not isinstance(meta, dict) or meta.get("mode") != "dual_role":
        return None
    try:
        if int(meta.get("user_id") or 0) != int(user_id):
            return None
    except (TypeError, ValueError):
        return None
    employee = (form_data.get("employee_name") or "the employee").strip()
    chain_label = (meta.get("chain_step_label") or "management approver").strip()
    return {
        "employee_name": employee,
        "chain_step_label": chain_label,
        "message": (
            f"You are listed as Reporting To for {employee}. When you sign as "
            f"{chain_label}, your signature will also appear in the Reporting To "
            f"block on this commencement form."
        ),
    }


def apply_dual_role_reporting_to_mirror(
    fd: dict[str, Any], user: User, step: dict[str, Any]
) -> None:
    """Copy management step signature into Reporting To fields when dual-role."""
    meta = fd.get(REPORTING_TO_SIGNOFF_KEY)
    if not isinstance(meta, dict) or meta.get("mode") != "dual_role":
        return
    try:
        if int(meta.get("user_id") or 0) != int(user.id):
            return
    except (TypeError, ValueError):
        return
    expected_key = meta.get("chain_step_key")
    if expected_key and step.get("key") != expected_key:
        return
    sig = step.get("signature")
    if not sig:
        return
    fd["reporting_to_signature"] = sig
    fd["reporting_sign_date"] = _signed_at_to_date_str(step.get("signed_at"))


def build_pre_chain_reporting_block(user_ids: list[int]) -> dict[str, Any]:
    signers = _build_signer_slots(user_ids)
    return {
        "v": 1,
        "slots": [
            {
                "key": "reporting_to",
                "label": "Reporting To",
                "signers": signers,
            }
        ],
    }


def resolve_commencement_reporting_to(
    data: dict[str, Any], submitter: User
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    """
    Configure Reporting To sign-off after the management chain is built.

    Returns ``(pre_chain_routed_block, error, meta)``.
    """
    raw_id = data.get("reporting_to_signer_id")
    if raw_id is None:
        alt = data.get("reporting_to_signer_ids")
        if isinstance(alt, list) and alt:
            raw_id = alt[0]
    if raw_id is None or raw_id == "":
        return (
            None,
            (
                "Reporting To: select your manager from the Kynvera account list "
                "so they can sign the Reporting To block."
            ),
            None,
        )

    try:
        rt_uid = int(raw_id)
    except (TypeError, ValueError):
        return None, "Reporting To: invalid signatory selected.", None

    if rt_uid == int(submitter.id):
        return None, "Reporting To: choose someone other than yourself.", None

    rt_user = db.session.get(User, rt_uid)
    if not rt_user or not getattr(rt_user, "is_active", True):
        return None, "Reporting To: selected user is not an active account.", None

    data["reporting_to_signer_id"] = rt_uid
    if not (data.get("reporting_to_name") or "").strip():
        data["reporting_to_name"] = rt_user.full_name or rt_user.username

    meta: dict[str, Any] = {
        "v": 1,
        "user_id": rt_uid,
        "display_name": rt_user.full_name or rt_user.username,
    }

    block = data.get(MGMT_CHAIN_KEY) if isinstance(data.get(MGMT_CHAIN_KEY), dict) else {}
    steps = block.get("steps") if isinstance(block.get("steps"), list) else []

    if steps and rt_uid in mgmt_chain_participant_ids(steps):
        step = find_mgmt_step_for_user(steps, rt_uid)
        meta["mode"] = "dual_role"
        meta["chain_step_key"] = (step or {}).get("key")
        meta["chain_step_label"] = (step or {}).get("pdf_label") or "management approver"
        data[REPORTING_TO_SIGNOFF_KEY] = meta
        data.pop("reporting_to_signature", None)
        data.pop("reporting_sign_date", None)
        return None, None, meta

    meta["mode"] = "pre_chain"
    data[REPORTING_TO_SIGNOFF_KEY] = meta
    data.pop("reporting_to_signature", None)
    data.pop("reporting_sign_date", None)
    return build_pre_chain_reporting_block([rt_uid]), None, meta


def dual_role_notify_message(
    meta: dict[str, Any], employee_name: str, submission_id: str
) -> str:
    chain_label = (meta.get("chain_step_label") or "management approver").strip()
    return (
        f"You are Reporting To for {employee_name} on Commencement Form ({submission_id}). "
        f"You will sign once as {chain_label}; your signature will also fill the Reporting To "
        f"block on the PDF."
    )
