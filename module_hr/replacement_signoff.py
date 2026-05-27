"""
Backward-compatible façade for routed pre–HR sign-offs.

Core logic lives in module_hr.hr_routed_signoffs.
"""
from __future__ import annotations

from app.models import Submission, User

from module_hr.hr_routed_signoffs import (
    ROUTED_BLOCK_KEY,
    _build_signer_slots,
    _normalize_id_list,
    all_pending_routed_signed,
    apply_routed_signature,
    email_all_routed_assignees,
    migrate_legacy_routed_into_block,
    pending_routed_for_user,
    sync_mirrors_and_pdf_fields,
)


def parse_replacement_signer_ids(payload: dict, submitter_id: int) -> list[int]:
    raw = payload.get("replacement_signer_ids")
    if raw is None and isinstance(payload.get("replacement_signers"), list):
        raw = payload.get("replacement_signers")
    return _normalize_id_list(raw, submitter_id)


def build_replacement_slots(user_ids: list[int]) -> list[dict]:
    return _build_signer_slots(user_ids)


def replacement_signers_from_form_data(form_data: dict, module_type: str | None = None) -> list[dict]:
    if isinstance(form_data, dict) and module_type:
        migrate_legacy_routed_into_block(form_data, module_type)
    if not isinstance(form_data, dict):
        return []
    blk = form_data.get(ROUTED_BLOCK_KEY)
    slots = blk.get("slots") if isinstance(blk, dict) else None
    if isinstance(slots, list):
        for grp in slots:
            if isinstance(grp, dict) and grp.get("key") == "replacement":
                return grp.get("signers") if isinstance(grp.get("signers"), list) else []
    legacy = form_data.get("replacement_signers")
    return legacy if isinstance(legacy, list) else []


def all_replacements_signed(form_data: dict, module_type: str) -> bool:
    if not isinstance(form_data, dict):
        return True
    migrate_legacy_routed_into_block(form_data, module_type)
    return all_pending_routed_signed(form_data, module_type)


def pending_replacement_for_user(
    form_data: dict, user_id: int, module_type: str
) -> dict | None:
    fd = form_data if isinstance(form_data, dict) else {}
    migrate_legacy_routed_into_block(fd, module_type)
    p = pending_routed_for_user(fd, user_id)
    if not p:
        return None
    grp, slot = p
    out = dict(slot)
    out["_slot_key"] = grp.get("key")
    out["_slot_label"] = grp.get("label")
    return out


def apply_replacement_signature(
    submission: Submission,
    user: User,
    signature: str,
    comments: str | None = None,
) -> tuple[bool, str]:
    return apply_routed_signature(submission, user, signature, comments)


def sync_replacement_display_fields(form_data: dict, module_type: str) -> None:
    sync_mirrors_and_pdf_fields(form_data, module_type)


def email_all_replacement_assignees(app, submission: Submission, form_label: str) -> None:
    email_all_routed_assignees(app, submission, form_label)
