"""
HR management approval chain (PDF + workflow).

Technicians: Reporting supervisor (admin: user.reporting_manager_id, Supervisor) → Operations Manager
  (picker) → GM (skipped if supervisor is GM) → HR (head office).
Employees:   Reporting manager (admin-only profile) → GM (skipped if they are the GM) → HR (head office).

Stored in submission.form_data['hr_mgmt_chain']. Legacy submissions without this block
keep the old flow: hr_review → gm_review.
"""
from __future__ import annotations

from typing import Any

from flask import Flask

from app.models import User, Submission, db, Notification
from common.datetime_utils import naive_utc_isoformat_z, utc_now_naive


MGMT_CHAIN_KEY = "hr_mgmt_chain"

TECHNICIAN_DESIGNATION = "technician"

# workflow_status values for gated steps (GM only sees gm step, etc.)
WF_MGMT_SUP = "hr_mgmt_supervisor"
WF_MGMT_OM = "hr_mgmt_operations_manager"
WF_MGMT_RM = "hr_mgmt_reporting_manager"
WF_MGMT_GM = "hr_mgmt_gm"
WF_MGMT_HR = "hr_mgmt_hr_head_office"

ALL_MGMT_WF_STATUSES = (
    WF_MGMT_SUP,
    WF_MGMT_OM,
    WF_MGMT_RM,
    WF_MGMT_GM,
    WF_MGMT_HR,
)


def lane_for_user(user: User | None) -> str:
    if user and (user.designation or "").strip().lower() == TECHNICIAN_DESIGNATION:
        return "technician"
    return "employee"


def user_is_hr_head(user: User | None) -> bool:
    if not user:
        return False
    if user.role == "admin":
        return True
    if getattr(user, "access_hr", False):
        return True
    return (user.designation or "").strip().lower() == "hr_manager"


def user_is_gm(user: User | None) -> bool:
    if not user:
        return False
    return user.role == "admin" or (user.designation or "").strip().lower() == "general_manager"


def _desig(u: User) -> str:
    return (u.designation or "").strip().lower()


def _step(
    key: str,
    wf: str,
    pdf_label: str,
    *,
    signer_mode: str,
    signer_id: int | None = None,
    designation_gate: str | None = None,
    also_mirrors_gm_fields: bool = False,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "key": key,
        "wf": wf,
        "pdf_label": pdf_label,
        "signer_mode": signer_mode,
        "signer_id": signer_id,
        "designation_gate": designation_gate,
        "comments": "",
        "signature": "",
        "signed_at": None,
        "signed_by_id": None,
        "signed_by_name": None,
    }
    if also_mirrors_gm_fields:
        d["also_mirrors_gm_fields"] = True
    return d


def _reporting_contact(submitter: User) -> User | None:
    rid = getattr(submitter, "reporting_manager_id", None)
    if not rid:
        return None
    u = db.session.get(User, int(rid))
    if not u or not u.is_active:
        return None
    return u


def _is_general_manager_designation(u: User | None) -> bool:
    return bool(u and _desig(u) == "general_manager")


def build_chain_for_lane(
    lane: str,
    reporting_contact_id: int,
    operations_manager_id: int | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    operations_manager_id — required for technician lane only.
    Returns (steps, pdf_hint_lines).
    """
    hints: list[str] = []
    rc = db.session.get(User, reporting_contact_id)
    if not rc:
        return [], []

    rc_is_gm = _is_general_manager_designation(rc)

    if lane == "technician":
        if operations_manager_id is None:
            return [], []
        if rc_is_gm:
            hints.append(
                "Your reporting supervisor is the General Manager — their sign-off counts as both "
                "reporting supervisor and GM on this trail (no duplicate GM step)."
            )
        om_user = db.session.get(User, operations_manager_id)
        if not om_user:
            return [], []

        steps: list[dict[str, Any]] = [
            _step(
                "supervisor",
                WF_MGMT_SUP,
                "Reporting supervisor",
                signer_mode="fixed_user",
                signer_id=reporting_contact_id,
                also_mirrors_gm_fields=rc_is_gm,
            ),
            _step(
                "operations_manager",
                WF_MGMT_OM,
                "Operations manager",
                signer_mode="fixed_user",
                signer_id=operations_manager_id,
            ),
        ]
        if not rc_is_gm:
            steps.append(
                _step(
                    "general_manager",
                    WF_MGMT_GM,
                    "General manager",
                    signer_mode="designation",
                    designation_gate="general_manager",
                )
            )
        steps.append(
            _step(
                "hr_head_office",
                WF_MGMT_HR,
                "HR (head office)",
                signer_mode="designation",
                designation_gate="hr_head_office",
            )
        )
        return steps, hints

    # employee lane — reporting manager only from profile, then optional GM pool, then HR
    if rc_is_gm:
        hints.append(
            "Your reporting manager is the General Manager — one signature covers both steps on this form."
        )

    steps_e: list[dict[str, Any]] = [
        _step(
            "reporting_manager",
            WF_MGMT_RM,
            "Reporting manager",
            signer_mode="fixed_user",
            signer_id=reporting_contact_id,
            also_mirrors_gm_fields=rc_is_gm,
        ),
    ]
    if not rc_is_gm:
        steps_e.append(
            _step(
                "general_manager",
                WF_MGMT_GM,
                "General manager",
                signer_mode="designation",
                designation_gate="general_manager",
            )
        )
    steps_e.append(
        _step(
            "hr_head_office",
            WF_MGMT_HR,
            "HR (head office)",
            signer_mode="designation",
            designation_gate="hr_head_office",
        )
    )
    return steps_e, hints


def _parse_pick(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def init_management_chain_on_submit(
    data: dict[str, Any],
    submitter: User,
) -> str | None:
    """
    Validate picks, mutate data with hr_mgmt_chain. Returns error message or None.
    Reporting supervisor / manager comes from submitter.reporting_manager_id (admin).
    Technicians also submit operations_manager from the form.
    """
    lane = lane_for_user(submitter)
    # Never trust client for reporting line
    data.pop("mgmt_supervisor_signer_id", None)
    data.pop("mgmt_reporting_manager_signer_id", None)
    om_raw = _parse_pick(data.pop("mgmt_operations_manager_signer_id", None))

    contact = _reporting_contact(submitter)
    # Admins may lack a reporting line; submitting without hr_mgmt_chain is allowed (straight to HR review).
    if getattr(submitter, "role", None) == "admin" and contact is None:
        data.pop(MGMT_CHAIN_KEY, None)
        return None

    if not contact:
        return (
            "A reporting manager / supervisor must be assigned to your account in Admin before you can "
            "submit (Admin → Users → your profile → Reporting manager)."
        )
    if contact.id == submitter.id:
        return "Invalid reporting line: you cannot be your own reporting manager. Ask an administrator to fix this."

    if lane == "technician":
        if _desig(contact) != "supervisor":
            return (
                "For technicians, Admin must set your Reporting manager to your reporting supervisor "
                "(a user with Supervisor designation)."
            )
        if not om_raw:
            return "Please select the operations manager for this request."
        u_om = db.session.get(User, om_raw)
        if not u_om or not u_om.is_active:
            return "Invalid operations manager selected."
        if om_raw == submitter.id:
            return "You cannot assign yourself as operations manager."
        if contact.id == om_raw:
            return "Reporting supervisor and operations manager must be different people."
        if _desig(u_om) != "operations_manager":
            return "Operations manager must be a user with Operations Manager designation."
        chain_steps, hints = build_chain_for_lane("technician", contact.id, om_raw)
    else:
        chain_steps, hints = build_chain_for_lane("employee", contact.id, None)

    if not chain_steps:
        return "Could not build approval chain. Contact support."

    data[MGMT_CHAIN_KEY] = {
        "v": 1,
        "lane": lane,
        "current_index": 0,
        "steps": chain_steps,
        "reporting_contact_id": contact.id,
        "reporting_contact_name": contact.full_name or contact.username,
        "pdf_hints": hints,
    }
    return None


def has_management_chain(fd: dict[str, Any] | None) -> bool:
    if not isinstance(fd, dict):
        return False
    block = fd.get(MGMT_CHAIN_KEY)
    return isinstance(block, dict) and block.get("v") == 1 and isinstance(block.get("steps"), list)


def first_management_workflow_status(fd: dict[str, Any]) -> str | None:
    if not has_management_chain(fd):
        return None
    steps = fd[MGMT_CHAIN_KEY]["steps"]
    if not steps:
        return None
    return steps[0]["wf"]


def current_step(block: dict[str, Any]) -> dict[str, Any] | None:
    idx = block.get("current_index", 0)
    steps = block.get("steps") or []
    if idx < 0 or idx >= len(steps):
        return None
    return steps[idx]


def user_allowed_to_sign_step(user: User, step: dict[str, Any]) -> bool:
    if user.role == "admin":
        return True
    mode = step.get("signer_mode")
    if mode == "fixed_user":
        return int(step.get("signer_id") or -1) == user.id
    gate = (step.get("designation_gate") or "").strip().lower()
    if gate == "general_manager":
        return _desig(user) == "general_manager"
    if gate == "hr_head_office":
        return user_is_hr_head(user)
    return False


def pending_management_step_for_user(
    fd: dict[str, Any] | None, workflow_status: str | None, user: User | None
) -> dict[str, Any] | None:
    """If this user may sign now, return {step, label, submission_id context from caller}."""
    if not user or not has_management_chain(fd) or not workflow_status:
        return None
    block = fd[MGMT_CHAIN_KEY]
    step = current_step(block)
    if not step:
        return None
    if step.get("wf") != workflow_status:
        return None
    if step.get("signature"):
        return None
    if not user_allowed_to_sign_step(user, step):
        return None
    return {
        "step_key": step.get("key"),
        "pdf_label": step.get("pdf_label"),
        "step": step,
    }


def _notify_user(app: Flask, uid: int, title: str, message: str, submission_id: str, n_type: str):
    n = Notification(
        user_id=uid,
        title=title,
        message=message,
        notification_type=n_type,
        submission_id=submission_id,
    )
    db.session.add(n)


def notify_submitter_management_final(
    app: Flask,
    submission: Submission,
    *,
    completed: bool,
    rejected: bool = False,
    reason: str | None = None,
) -> None:
    """Notify original submitter after chain completes or rejects."""
    if not submission.user_id:
        return
    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    form_type_display = (submission.module_type or "HR").replace("hr_", "").replace("_", " ").title()
    sid = submission.submission_id
    if rejected:
        _notify_user(
            app,
            submission.user_id,
            "HR request rejected",
            f"Your {form_type_display} ({sid}) was rejected during management sign-off. {reason or ''}".strip(),
            sid,
            "hr_rejected",
        )
        return
    if completed:
        _notify_user(
            app,
            submission.user_id,
            "HR request approved",
            f"Your {form_type_display} ({sid}) is fully approved (all management signatures received).",
            sid,
            "hr_approved",
        )


def notify_current_management_signers(app: Flask, submission: Submission) -> None:
    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    if not has_management_chain(fd):
        return
    block = fd[MGMT_CHAIN_KEY]
    step = current_step(block)
    if not step or step.get("signature"):
        return
    submission_id = submission.submission_id
    form_type_display = (submission.module_type or "HR").replace("hr_", "").replace("_", " ").title()
    employee_name = (
        fd.get("employee_name") or fd.get("complainant_name") or fd.get("requester") or "Employee"
    )
    title = "HR form — your management sign-off"
    msg = f"{employee_name} — {form_type_display} ({submission_id}). Your signature is required for the official PDF trail."
    n_type = "hr_mgmt_chain_signoff"

    mode = step.get("signer_mode")
    if mode == "fixed_user":
        try:
            uid = int(step.get("signer_id"))
        except (TypeError, ValueError):
            app.logger.warning(
                "mgmt chain notify skipped: invalid signer_id %r submission=%s",
                step.get("signer_id"),
                submission_id,
            )
            return
        recipient = db.session.get(User, uid)
        if not recipient:
            app.logger.warning(
                "mgmt chain notify skipped: user id=%s missing submission=%s",
                uid,
                submission_id,
            )
            return
        if not recipient.is_active:
            app.logger.warning(
                "mgmt chain notify target user id=%s inactive submission=%s (notification still queued)",
                uid,
                submission_id,
            )
        _notify_user(app, uid, title, msg, submission_id, n_type)
        return
    gate = (step.get("designation_gate") or "").lower()
    if gate == "general_manager":
        for u in User.query.filter(
            User.designation == "general_manager",
            User.is_active == True,  # noqa: E712
        ).all():
            _notify_user(app, u.id, title, msg, submission_id, n_type)
        return
    if gate == "hr_head_office":
        q = User.query.filter(User.is_active == True)  # noqa: E712
        ids = []
        for u in q.all():
            if user_is_hr_head(u) and u.id not in ids:
                ids.append(u.id)
                _notify_user(app, u.id, title, msg, submission_id, n_type)


def attach_submission_enter_management(fd: dict[str, Any], submission_id: str) -> str | None:
    """Return workflow_status for first mgmt step, or None if no chain."""
    ws = first_management_workflow_status(fd)
    return ws


def apply_management_signature(
    submission: Submission,
    user: User,
    signature: str,
    comments: str | None,
    form_data_hr: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Apply signature for the current management step. Advance workflow or complete.
    """
    from common.form_data_utils import shallow_copy_form_data as _mutable_form_data

    fd = _mutable_form_data(submission)
    if not has_management_chain(fd):
        return False, "This submission does not use the management chain."
    wf = submission.workflow_status
    if wf not in ALL_MGMT_WF_STATUSES:
        return False, "This submission is not awaiting a management sign-off."

    block = fd[MGMT_CHAIN_KEY]
    idx = int(block.get("current_index") or 0)
    steps = block.get("steps") or []
    if idx >= len(steps):
        return False, "Nothing to sign."
    step = steps[idx]
    if step.get("wf") != wf:
        return False, "Workflow step mismatch."
    if step.get("signature"):
        return False, "This step is already signed."
    if not user_allowed_to_sign_step(user, step):
        return False, "You are not authorised to sign this step."

    if not signature or not isinstance(signature, str) or not signature.startswith("data:image"):
        return False, "A signature image is required."

    step["signature"] = signature.strip()
    step["comments"] = (comments or "").strip()
    step["signed_at"] = naive_utc_isoformat_z(utc_now_naive())
    step["signed_by_id"] = user.id
    step["signed_by_name"] = user.full_name or user.username

    # Mirror legacy PDF fields used by existing builders
    # Mirror legacy GM fields when RM/supervisor step covers GM (combined sign-off)
    if step.get("also_mirrors_gm_fields"):
        fd["gm_signature"] = step["signature"]
        fd["gm_comments"] = step["comments"]
        fd["gm_approved_by_id"] = user.id
        fd["gm_approved_by_name"] = step["signed_by_name"]
        fd["gm_approved_at"] = step["signed_at"]
        submission.general_manager_id = user.id
        submission.general_manager_approved_at = utc_now_naive()
        submission.general_manager_comments = step["comments"]

    key = step.get("key")
    # Duty Resumption (and previews) read `reporting_manager_signature` on the body; chain-only RM breaks hydration.
    if key in ("reporting_manager", "supervisor"):
        fd["reporting_manager_signature"] = step["signature"]
    if key == "general_manager":
        fd["gm_signature"] = step["signature"]
        fd["gm_comments"] = step["comments"]
        fd["gm_approved_by_id"] = user.id
        fd["gm_approved_by_name"] = step["signed_by_name"]
        fd["gm_approved_at"] = step["signed_at"]
        submission.general_manager_id = user.id
        submission.general_manager_approved_at = utc_now_naive()
        submission.general_manager_comments = step["comments"]
    elif key == "hr_head_office":
        fd["hr_signature"] = step["signature"]
        fd["hr_comments"] = step["comments"]
        fd["hr_reviewed_by_id"] = user.id
        fd["hr_reviewed_by_name"] = step["signed_by_name"]
        fd["hr_reviewed_at"] = step["signed_at"]
        if isinstance(form_data_hr, dict):
            for k, v in form_data_hr.items():
                fd[k] = v
        submission.operations_manager_id = user.id
        submission.operations_manager_approved_at = utc_now_naive()
        submission.operations_manager_comments = step["comments"]

    idx_next = idx + 1
    block["current_index"] = idx_next
    submission.form_data = fd

    if idx_next >= len(steps):
        submission.workflow_status = "approved"
        submission.status = "completed"
    else:
        submission.workflow_status = steps[idx_next]["wf"]

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(submission, "form_data")
    return True, None


def reject_management_submission(submission: Submission, user: User, reason: str) -> tuple[bool, str | None]:
    """Reject during an open management step (current signer only)."""
    from common.form_data_utils import shallow_copy_form_data as _mutable_form_data

    fd = _mutable_form_data(submission)
    if not has_management_chain(fd):
        return False, "This submission does not use the management chain."
    wf = submission.workflow_status
    if wf not in ALL_MGMT_WF_STATUSES:
        return False, "This submission is not in a rejectable management state."

    block = fd[MGMT_CHAIN_KEY]
    idx = int(block.get("current_index") or 0)
    steps = block.get("steps") or []
    step = steps[idx] if idx < len(steps) else None
    if not step or step.get("signature"):
        return False, "Invalid step."
    if not user_allowed_to_sign_step(user, step):
        return False, "You are not authorised to reject at this stage."

    reason = (reason or "").strip() or "Rejected"
    step["comments"] = f"Rejected: {reason}"

    rejection_key = f"mgmt_rejected_at_{step.get('key')}"
    fd[rejection_key] = naive_utc_isoformat_z(utc_now_naive())
    fd[f"mgmt_rejected_by_id_{step.get('key')}"] = user.id
    fd[f"mgmt_rejected_reason_{step.get('key')}"] = reason

    submission.form_data = fd
    submission.workflow_status = "rejected"
    submission.status = "rejected"
    submission.rejection_reason = reason
    submission.rejected_at = utc_now_naive()
    submission.rejected_by_id = user.id

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(submission, "form_data")
    return True, None


def submissions_pending_management_for_user_query(user: User):
    """SQLAlchemy query base — filter in Python for signer_id match."""
    return Submission.query.filter(
        Submission.module_type.like("hr_%"),
        Submission.workflow_status.in_(ALL_MGMT_WF_STATUSES),
    ).order_by(Submission.created_at.desc())


def get_mgmt_chain_ui_context(submitter: User | None) -> dict[str, Any]:
    """Reporting line comes from Admin (user.reporting_manager_id) only."""
    if not submitter:
        return {"success": False, "error": "Not authenticated"}

    lane = lane_for_user(submitter)
    c = _reporting_contact(submitter)
    if getattr(submitter, "role", None) == "admin" and c is None:
        return {
            "success": True,
            "lane": lane,
            "needs_operations_manager": False,
            "has_reporting_contact": False,
            "reporting_contact_is_general_manager": False,
            "reporting_contact": None,
            "technician_supervisor_valid": True,
            "setup_error": None,
            "admin_profile_bypass": True,
        }

    rm_is_gm = _is_general_manager_designation(c) if c else False
    technician_supervisor_ok = bool(c and lane == "technician" and _desig(c) == "supervisor")

    rc_payload = None
    if c:
        rc_payload = {
            "id": c.id,
            "full_name": c.full_name or c.username,
            "designation": c.designation,
        }

    err = None
    if lane == "technician" and c and _desig(c) != "supervisor":
        err = (
            "Your account is Technician, but Reporting manager must be your reporting supervisor "
            "(a user with Supervisor designation). Ask an administrator to update your profile."
        )
    elif not c:
        err = "Reporting manager must be set on your user profile by an administrator before submitting HR forms."

    return {
        "success": True,
        "lane": lane,
        "needs_operations_manager": lane == "technician",
        "has_reporting_contact": c is not None,
        "reporting_contact_is_general_manager": rm_is_gm,
        "reporting_contact": rc_payload,
        "technician_supervisor_valid": technician_supervisor_ok,
        "setup_error": err,
    }
