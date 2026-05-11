"""
Central configuration and logic for HR pre–HR routed signatures (coverage, reporting
officers, evaluator, grievance parties, etc.).

Payload:
- Per-slot IDs: `<slot>_signer_ids` (e.g. replacement_signer_ids, reporting_officer_signer_ids).
- Optional batched dict: routed_signer_ids = { "<slot_key>": [user_id, …], … }

Stored in submission.form_data as _routed_signoffs = { "v": 1, "slots": [ ... ] }.
Legacy submissions may only have replacement_signers — migrate on read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Flask
from sqlalchemy.orm.attributes import flag_modified

from app.models import User, Submission, db
from common.datetime_utils import naive_utc_isoformat_z, utc_now_naive


ROUTED_BLOCK_KEY = "_routed_signoffs"


@dataclass(frozen=True)
class RoutedSignatorySlot:
    """One routable signature role for a module."""

    key: str
    label_public: str
    request_payload_keys: tuple[str, ...]
    clear_when_routed: tuple[str, ...] = ()
    pdf_merge_field: str | None = None
    signer_list_mirror_key: str | None = None
    allow_multiple_signers: bool = True


# Full module_type as stored on Submission.module_type → ordered slots (any may be omitted on submit).
HR_ROUTED_SIGNATORY_SLOTS: dict[str, tuple[RoutedSignatorySlot, ...]] = {
    "hr_leave_application": (
        RoutedSignatorySlot(
            key="replacement",
            label_public="Coverage / replacement",
            request_payload_keys=("replacement_signer_ids",),
            clear_when_routed=("replacement_signature",),
            pdf_merge_field=None,
            signer_list_mirror_key="replacement_signers",
            allow_multiple_signers=True,
        ),
    ),
    "hr_commencement": (
        RoutedSignatorySlot(
            key="reporting_officer",
            label_public="Reporting officer",
            request_payload_keys=("reporting_officer_signer_ids", "reporting_signer_ids"),
            clear_when_routed=("reporting_to_signature",),
            pdf_merge_field="reporting_to_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=False,
        ),
    ),
    "hr_grievance": (
        RoutedSignatorySlot(
            key="second_party",
            label_public="Respondent / 2nd party",
            request_payload_keys=("second_party_signer_ids",),
            clear_when_routed=("second_party_signature",),
            pdf_merge_field="second_party_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=True,
        ),
        RoutedSignatorySlot(
            key="hod",
            label_public="Engineer / QHSE / HOD",
            request_payload_keys=("hod_signer_ids",),
            clear_when_routed=("hod_signature",),
            pdf_merge_field="hod_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=True,
        ),
    ),
    "hr_performance_evaluation": (
        RoutedSignatorySlot(
            key="evaluator",
            label_public="Evaluator",
            request_payload_keys=("evaluator_signer_ids",),
            clear_when_routed=("evaluator_signature",),
            pdf_merge_field="evaluator_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=False,
        ),
        RoutedSignatorySlot(
            key="incharge",
            label_public="In-charge / engineer",
            request_payload_keys=("incharge_signer_ids",),
            clear_when_routed=("incharge_signature",),
            pdf_merge_field="incharge_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=False,
        ),
    ),
    "hr_contract_renewal": (
        RoutedSignatorySlot(
            key="evaluator",
            label_public="Contract evaluator",
            request_payload_keys=("evaluator_signer_ids",),
            clear_when_routed=("evaluator_signature",),
            pdf_merge_field="evaluator_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=False,
        ),
    ),
    "hr_interview_assessment": (
        RoutedSignatorySlot(
            key="interviewer",
            label_public="Interviewer",
            request_payload_keys=("interviewer_signer_ids",),
            clear_when_routed=("interviewer_signature",),
            pdf_merge_field="interviewer_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=False,
        ),
    ),
    "hr_staff_appraisal": (
        RoutedSignatorySlot(
            key="reviewer_appraiser",
            label_public="Reviewer / appraiser",
            request_payload_keys=("appraiser_signer_ids", "reviewer_signer_ids"),
            clear_when_routed=("hr_signature",),
            pdf_merge_field="hr_signature",
            signer_list_mirror_key=None,
            allow_multiple_signers=False,
        ),
    ),
}


def routed_slots(module_type: str) -> tuple[RoutedSignatorySlot, ...]:
    return HR_ROUTED_SIGNATORY_SLOTS.get(module_type, ())


def strip_teammate_signatures_from_submitter_payload(
    payload: dict, module_type: str
) -> None:
    """Remove signature image fields meant for routed colleagues — submitter cannot forge these."""
    keys: set[str] = set()
    for slot in routed_slots(module_type):
        keys.update(slot.clear_when_routed)
        if slot.pdf_merge_field:
            keys.add(slot.pdf_merge_field)
    # Appraiser/HR slot reuses hr_signature; real HR may sign on submit when is_hr — do not strip.
    if module_type == "hr_staff_appraisal":
        keys.discard("hr_signature")
    for k in keys:
        payload.pop(k, None)


def _normalize_id_list(raw: Any, submitter_id: int) -> list[int]:
    ids: list[int] = []
    if raw is None:
        return ids
    if not isinstance(raw, list):
        return ids
    for item in raw:
        uid = None
        if isinstance(item, dict):
            uid = item.get("user_id") or item.get("id")
        else:
            uid = item
        try:
            n = int(uid)
        except (TypeError, ValueError):
            continue
        if n == int(submitter_id):
            continue
        if n not in ids:
            ids.append(n)
    return ids


def _ids_for_slot(
    payload: dict,
    routed_map: dict | None,
    slot: RoutedSignatorySlot,
    submitter_id: int,
) -> list[int]:
    raw = None
    if routed_map and isinstance(routed_map, dict) and slot.key in routed_map:
        raw = routed_map[slot.key]
    if raw is None:
        for k in slot.request_payload_keys:
            if k in payload:
                raw = payload.get(k)
                break
    return _normalize_id_list(raw, submitter_id)


def _build_signer_slots(user_ids: list[int]) -> list[dict]:
    out: list[dict] = []
    for uid in user_ids:
        u = db.session.get(User, uid)
        if not u or not getattr(u, "is_active", True):
            continue
        out.append(
            {
                "user_id": int(u.id),
                "display_name": u.full_name or u.username,
                "username": u.username,
                "email": u.email,
                "signed_at": None,
                "signature": None,
                "comments": None,
            }
        )
    return out


def migrate_legacy_routed_into_block(form_data: dict, module_type: str) -> None:
    """If only legacy replacement_signers exists, wrap into ROUTED_BLOCK_KEY."""
    if not isinstance(form_data, dict):
        return
    if form_data.get(ROUTED_BLOCK_KEY):
        return
    legacy = form_data.get("replacement_signers")
    if isinstance(legacy, list) and legacy and module_type == "hr_leave_application":
        form_data[ROUTED_BLOCK_KEY] = {
            "v": 1,
            "slots": [
                {
                    "key": "replacement",
                    "label": "Coverage / replacement",
                    "signers": legacy,
                }
            ],
        }


def routed_block_slots(form_data: dict) -> list[dict]:
    blk = form_data.get(ROUTED_BLOCK_KEY)
    if not isinstance(blk, dict):
        return []
    sl = blk.get("slots")
    return sl if isinstance(sl, list) else []


def all_pending_routed_signed(form_data: dict, module_type: str) -> bool:
    migrate_legacy_routed_into_block(form_data, module_type)
    slots_runtime = routed_block_slots(form_data)
    if not slots_runtime:
        legacy = form_data.get("replacement_signers")
        if isinstance(legacy, list) and legacy:
            for s in legacy:
                if not (s.get("signature") and s.get("signed_at")):
                    return False
        return True
    for grp in slots_runtime:
        signers = grp.get("signers") if isinstance(grp, dict) else None
        if not isinstance(signers, list):
            continue
        for s in signers:
            if not (s.get("signature") and s.get("signed_at")):
                return False
    return True


def pending_routed_for_user(form_data: dict, user_id: int) -> tuple[dict, dict] | None:
    """
    Find first pending signer row for user. Returns (slot_group_dict, signer_dict) or None.
    slot_group_dict includes key, label, signers list.
    """
    uid = int(user_id)
    for grp in routed_block_slots(form_data):
        if not isinstance(grp, dict):
            continue
        for s in grp.get("signers") or []:
            if int(s.get("user_id") or 0) != uid:
                continue
            if s.get("signature") and s.get("signed_at"):
                continue
            return grp, s
    return None


def apply_routed_signature(
    submission: Submission,
    user: User,
    signature: str,
    comments: str | None = None,
) -> tuple[bool, str]:
    if submission.workflow_status != "replacement_signoff":
        return False, "This form is not awaiting teammate signatures"

    fd = submission.form_data
    if not isinstance(fd, dict):
        return False, "Invalid form data"

    migrate_legacy_routed_into_block(fd, submission.module_type)

    pend = pending_routed_for_user(fd, user.id)
    if not pend:
        return False, "You are not listed as a pending signatory for this form"

    grp, slot = pend
    slot["signature"] = signature
    slot["signed_at"] = naive_utc_isoformat_z(utc_now_naive())
    slot["signed_by_id"] = user.id
    slot["signed_by_name"] = user.full_name or user.username
    if comments is not None:
        slot["comments"] = (comments or "").strip() or None

    submission.form_data = fd
    flag_modified(submission, "form_data")
    sync_mirrors_and_pdf_fields(fd, submission.module_type)
    return True, ""


def sync_mirrors_and_pdf_fields(form_data: dict, module_type: str) -> None:
    """Keep replacement_signers + single merged signature fields aligned with routed state."""
    for grp in routed_block_slots(form_data):
        key = grp.get("key")
        signers = grp.get("signers") if isinstance(grp.get("signers"), list) else []
        defs = {s.key: s for s in routed_slots(module_type)}
        cfg = defs.get(key)
        if not cfg:
            continue
        if cfg.signer_list_mirror_key == "replacement_signers":
            form_data["replacement_signers"] = signers
            names = [s.get("display_name") or s.get("username") or "" for s in signers]
            form_data["replacement_name"] = ", ".join(n for n in names if n)
        filled = [
            s
            for s in signers
            if isinstance(s, dict) and s.get("signature") and s.get("signed_at")
        ]
        all_done = signers and len(filled) == len(signers)
        if all_done and cfg.pdf_merge_field and filled:
            form_data[cfg.pdf_merge_field] = filled[-1].get("signature")


def collect_routed_signoffs_from_submit(
    payload: dict,
    submitter_id: int,
    module_type: str,
) -> tuple[dict[str, Any] | None, list[str], str | None]:
    """
    Build _routed_signoffs from JSON body. Returns (block, keys_to_strip_from_payload, error).
    """
    defs = routed_slots(module_type)
    if not defs:
        return None, [], None

    routed_map = payload.get("routed_signer_ids")
    if routed_map is not None and not isinstance(routed_map, dict):
        routed_map = None

    slots_out: list[dict] = []
    strip: list[str] = []
    attempted = False

    for slot_cfg in defs:
        ids_req = _ids_for_slot(payload, routed_map, slot_cfg, submitter_id)
        if not ids_req:
            continue
        attempted = True
        if not slot_cfg.allow_multiple_signers and len(ids_req) > 1:
            return None, strip, f"{slot_cfg.label_public}: choose only one teammate."
        signers = _build_signer_slots(ids_req)
        if not signers:
            return (
                None,
                strip,
                f"{slot_cfg.label_public}: none of the selected colleagues are active user accounts.",
            )
        slots_out.append(
            {
                "key": slot_cfg.key,
                "label": slot_cfg.label_public,
                "signers": signers,
            }
        )
        strip.extend(slot_cfg.clear_when_routed)

    if not attempted:
        return None, [], None

    block = {"v": 1, "slots": slots_out}
    return block, strip, None


def merge_routed_into_form_data_inplace(data: dict, block: dict, module_type: str) -> None:
    """After submit attaches block; sync mirrors/pdf merge fields."""
    data[ROUTED_BLOCK_KEY] = block
    sync_mirrors_and_pdf_fields(data, module_type)


def flatten_signers_notify(block: dict) -> list[dict]:
    out: list[dict] = []
    slots: list | None = block.get("slots") if isinstance(block, dict) else None
    if not isinstance(slots, list):
        return out
    for grp in slots:
        if not isinstance(grp, dict):
            continue
        key = grp.get("key") or ""
        label = grp.get("label") or key
        for s in grp.get("signers") or []:
            if isinstance(s, dict) and s.get("user_id"):
                row = dict(s)
                row["_slot_key"] = key
                row["_slot_label"] = label
                out.append(row)
    return out


def send_slot_assignment_email(
    app: Flask,
    recipient: User,
    submission: Submission,
    submitter_name: str,
    form_label: str,
    slot_label: str,
) -> None:
    from flask import request

    from common.email_service import is_email_configured, send_email

    if not recipient.email or not is_email_configured(app):
        return

    try:
        base = (request.url_root or "").rstrip("/")
    except RuntimeError:
        base = (app.config.get("PREFERRED_URL_SCHEME") or "https") + "://" + (
            app.config.get("SERVER_NAME") or "localhost"
        )

    link = f"{base}/hr/replacement-sign/{submission.submission_id}"
    subj = f"Action required: sign HR form ({submission.submission_id})"
    body = (
        f"Hello {recipient.full_name or recipient.username},\n\n"
        f"{submitter_name} submitted {form_label} and listed you to sign as: {slot_label}.\n"
        f"Please open Injaaz and add your signature:\n{link}\n\n"
        f"Reference: {submission.submission_id}\n"
    )
    html = (
        f"<p>Hello <strong>{recipient.full_name or recipient.username}</strong>,</p>"
        f"<p>{submitter_name} submitted <strong>{form_label}</strong> and listed you to sign as "
        f"<strong>{slot_label}</strong>.</p>"
        f"<p><a href=\"{link}\">Open form to sign</a></p>"
        f"<p style=\"color:#64748b;font-size:12px\">Reference: {submission.submission_id}</p>"
    )
    try:
        send_email(recipient.email, subj, body, html_body=html)
    except Exception:
        app.logger.exception("routed signoff email failed for user %s", recipient.id)


def email_all_routed_assignees(app: Flask, submission: Submission, form_label: str) -> None:
    fd = submission.form_data or {}
    submitter_id = submission.user_id
    submitter = db.session.get(User, submitter_id) if submitter_id else None
    submitter_name = (
        fd.get("submitted_by_name")
        or (submitter.full_name if submitter else None)
        or (submitter.username if submitter else None)
        or "A colleague"
    )
    blk = fd.get(ROUTED_BLOCK_KEY) or {}
    for row in flatten_signers_notify(blk):
        uid = row.get("user_id")
        if not uid:
            continue
        u = db.session.get(User, int(uid))
        if not u:
            continue
        send_slot_assignment_email(
            app,
            u,
            submission,
            submitter_name,
            form_label,
            row.get("_slot_label") or "Signatory",
        )
