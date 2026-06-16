"""
HR management approval chain (PDF + workflow).

Routing model (fixed three-lane)
--------------------------------
The chain is determined by the submitter's designation, not by walking a
hierarchy. Operations Manager, General Manager and HR are designation pools
(any active user with the right designation can sign). Only the technician's
immediate supervisor is a per-user, admin-assigned signer
(``User.reporting_manager_id``).

Lanes:

* ``technician`` -> Immediate supervisor (fixed per user) -> Operations manager
  (pool) -> General manager (pool) -> HR head office.
* ``supervisor`` -> Operations manager (pool) -> General manager (pool) ->
  HR head office.
* office staff (everyone else, including operations_manager / general_manager /
  hr_manager / employee / bd / procurement / business_development) ->
  General manager (pool) -> HR head office (pool).
* Admin with no profile data continues to bypass the chain to the HR review
  queue (unchanged).

Stored under ``submission.form_data['hr_mgmt_chain']``. Legacy submissions
without this block keep the old flow: ``hr_review`` -> ``gm_review``.
"""
from __future__ import annotations

from typing import Any

from flask import Flask

from app.models import User, Submission, db, Notification
from common.datetime_utils import naive_utc_isoformat_z, utc_now_naive


MGMT_CHAIN_KEY = "hr_mgmt_chain"

TECHNICIAN_DESIGNATION = "technician"
SUPERVISOR_DESIGNATION = "supervisor"

# Workflow step gates (each unique role label maps to a wf status the queue UI filters on).
WF_MGMT_SUP = "hr_mgmt_supervisor"
WF_MGMT_OM = "hr_mgmt_operations_manager"
WF_MGMT_RM = "hr_mgmt_reporting_manager"
WF_MGMT_GM = "hr_mgmt_gm"
WF_MGMT_HR = "hr_mgmt_hr_head_office"
WF_MGMT_ROUTING = "hr_mgmt_routing_approver"

ALL_MGMT_WF_STATUSES = (
    WF_MGMT_SUP,
    WF_MGMT_OM,
    WF_MGMT_RM,
    WF_MGMT_ROUTING,
    WF_MGMT_GM,
    WF_MGMT_HR,
)


def lane_for_user(user: User | None) -> str:
    """Return the approval lane this user belongs to as a submitter."""
    if not user:
        return "office_staff"
    d = (user.designation or "").strip().lower()
    if d == TECHNICIAN_DESIGNATION:
        return "technician"
    if d == SUPERVISOR_DESIGNATION:
        return "supervisor"
    return "office_staff"


def user_is_hr_head(user: User | None) -> bool:
    """Users who may sign or review at the HR head office workflow step."""
    if not user:
        return False
    if user.role == "admin":
        return True
    if getattr(user, "access_hr", False):
        return True
    return _desig(user) in ("hr_manager", "hr")


def _active_hr_manager_users() -> list[User]:
    """Active users with the HR manager designation (official HR head office account)."""
    return _active_users_with_designation("hr_manager")


def _is_legacy_hr_seed_account(user: User) -> bool:
    """Default bootstrap login from ``create_hr_procurement_users`` — not the live HR contact."""
    return (user.username or "").strip().lower() == "hr_manager"


def _canonical_hr_user() -> User | None:
    """
    The HR account shown by name in the sidebar.

    When several users share the ``hr_manager`` designation, prefer a real staff
    account (e.g. Mona) over the legacy seed login ``hr_manager``. Among named
    accounts, the most recently created wins.
    """
    mgrs = _active_hr_manager_users()
    if mgrs:
        if len(mgrs) == 1:
            return mgrs[0]
        named = [u for u in mgrs if not _is_legacy_hr_seed_account(u)]
        pool = named if named else mgrs
        return max(pool, key=lambda u: int(u.id or 0))
    # Fallback: HR module access without a formal designation row yet.
    return (
        User.query.filter(
            User.is_active == True,  # noqa: E712
            User.access_hr == True,  # noqa: E712
            User.role != "admin",
        )
        .order_by(User.full_name, User.username)
        .first()
    )


def _active_hr_signers() -> list[User]:
    """Active users who may sign the HR head office management step."""
    out: list[User] = []
    seen: set[int] = set()
    for u in User.query.filter(User.is_active == True).order_by(  # noqa: E712
        User.full_name, User.username
    ).all():
        if user_is_hr_head(u) and u.id not in seen:
            out.append(u)
            seen.add(u.id)
    return out


def _active_hr_users() -> list[User]:
    """Backward-compatible alias."""
    return _active_hr_signers()


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


def _supervisor_for(submitter: User) -> User | None:
    """Return the active user assigned as reporting manager on the profile, or None."""
    rid = getattr(submitter, "reporting_manager_id", None)
    if not rid:
        return None
    u = db.session.get(User, int(rid))
    if not u or not u.is_active:
        return None
    return u


def _default_reporting_to_prefill(submitter: User) -> dict[str, Any] | None:
    """Reporting To block defaults from the submitter's profile reporting manager."""
    mgr = _supervisor_for(submitter)
    if not mgr:
        return None
    return {
        "id": mgr.id,
        "full_name": mgr.full_name or mgr.username,
        "designation": mgr.designation or "",
        "job_designation": mgr.job_designation or "",
        "phone": mgr.phone or "",
    }


def _active_users_with_designation(designation: str) -> list[User]:
    return (
        User.query.filter(
            User.designation == designation,
            User.is_active == True,  # noqa: E712
        )
        .order_by(User.full_name, User.username)
        .all()
    )


def _people_label(
    users: list[User],
    fallback: str,
    *,
    named_only: bool = False,
) -> tuple[str, str | None]:
    """
    Return ``(who_label, who_detail)`` for a pool of possible signers.

    * 0 users  -> ``(fallback, "No one with this role is set up yet.")``
    * 1 user   -> ``(<full name>, None)``
    * 2-3 users -> ``("<n1>, <n2>", "Either may sign.")``
    * 4+ users -> ``("Any active <fallback>", "<first 3 names> + N more.")``
      unless ``named_only`` is True, in which case all names are listed.
    """
    if not users:
        return fallback, "No one with this role is set up yet."
    names = [(u.full_name or u.username or f"#{u.id}") for u in users]
    if len(names) == 1:
        return names[0], None
    if named_only or len(names) <= 3:
        detail = "Either may sign." if len(names) == 2 else "Any of these may sign."
        return ", ".join(names), detail
    preview = ", ".join(names[:3])
    return f"Any active {fallback}", f"{preview} + {len(names) - 3} more."


# ---------------------------------------------------------------------------
# Chain construction
# ---------------------------------------------------------------------------


def _build_chain_for_submitter(submitter: User) -> tuple[list[dict[str, Any]], str | None]:
    """
    Build the deterministic step list for this submitter's lane.

    Returns ``(steps, setup_error)``. ``setup_error`` is non-None only when the
    submitter cannot proceed (currently: a technician with no valid supervisor
    on profile).
    """
    lane = lane_for_user(submitter)
    steps: list[dict[str, Any]] = []

    if lane == "technician":
        sup = _supervisor_for(submitter)
        if not sup:
            return [], (
                "Your immediate supervisor has not been assigned by an administrator yet. "
                "Ask an administrator to set your Reporting manager on your profile (it must "
                "be a user with the Supervisor designation) before you can submit."
            )
        if _desig(sup) != SUPERVISOR_DESIGNATION:
            return [], (
                "Your account is a Technician but the Reporting manager set on your profile "
                "is not a Supervisor. Ask an administrator to fix it before you can submit."
            )
        if sup.id == submitter.id:
            return [], "You cannot be your own supervisor. Ask an administrator to fix your profile."
        steps.append(
            _step(
                "supervisor",
                WF_MGMT_SUP,
                "Immediate supervisor",
                signer_mode="fixed_user",
                signer_id=sup.id,
            )
        )
        steps.append(
            _step(
                "operations_manager",
                WF_MGMT_OM,
                "Operations manager",
                signer_mode="designation",
                designation_gate="operations_manager",
            )
        )
        steps.append(
            _step(
                "general_manager",
                WF_MGMT_GM,
                "General manager",
                signer_mode="designation",
                designation_gate="general_manager",
            )
        )

    elif lane == "supervisor":
        steps.append(
            _step(
                "operations_manager",
                WF_MGMT_OM,
                "Operations manager",
                signer_mode="designation",
                designation_gate="operations_manager",
            )
        )
        steps.append(
            _step(
                "general_manager",
                WF_MGMT_GM,
                "General manager",
                signer_mode="designation",
                designation_gate="general_manager",
            )
        )

    elif lane == "office_staff":
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
    return steps, None


def build_interview_chain_after_interviewer(
    next_approver_id: int,
    *,
    submitter_id: int | None,
    interviewer_id: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Interview assessment: interviewer picks the next approver at sign time.
    Chain is always: chosen colleague → GM (pool) → HR head office (pool).
    """
    try:
        na_id = int(next_approver_id)
        iv_id = int(interviewer_id)
    except (TypeError, ValueError):
        return [], "Invalid next approver."

    if na_id == iv_id:
        return [], "You cannot forward the form to yourself."
    if submitter_id is not None and na_id == int(submitter_id):
        return [], "You cannot forward the form back to the person who submitted it."

    approver = db.session.get(User, na_id)
    if not approver or not approver.is_active:
        return [], "Selected next approver is not an active user."

    steps = [
        _step(
            "routing_approver",
            WF_MGMT_ROUTING,
            approver.full_name or approver.username or "Next approver",
            signer_mode="fixed_user",
            signer_id=approver.id,
        ),
        _step(
            "general_manager",
            WF_MGMT_GM,
            "General manager",
            signer_mode="designation",
            designation_gate="general_manager",
        ),
        _step(
            "hr_head_office",
            WF_MGMT_HR,
            "HR (head office)",
            signer_mode="designation",
            designation_gate="hr_head_office",
        ),
    ]
    return steps, None


def apply_interview_chain_after_interviewer(
    form_data: dict[str, Any],
    next_approver_id: int,
    *,
    submitter_id: int | None,
    interviewer_id: int,
) -> str | None:
    """Write hr_mgmt_chain after interviewer sign. Returns error message or None."""
    steps, err = build_interview_chain_after_interviewer(
        next_approver_id,
        submitter_id=submitter_id,
        interviewer_id=interviewer_id,
    )
    if err:
        return err

    approver = db.session.get(User, int(next_approver_id))
    approver_name = (approver.full_name or approver.username) if approver else "Next approver"

    form_data["next_approver_signer_id"] = int(next_approver_id)
    form_data["next_approver_name"] = approver_name
    form_data[MGMT_CHAIN_KEY] = {
        "v": 1,
        "lane": "interview_routing",
        "current_index": 0,
        "steps": steps,
        "reporting_contact_id": int(next_approver_id),
        "reporting_contact_name": approver_name,
        "pdf_hints": [],
    }
    form_data["interview_routing"] = {
        "v": 1,
        "deferred": False,
        "resolved_at": naive_utc_isoformat_z(utc_now_naive()),
        "next_approver_signer_id": int(next_approver_id),
        "next_approver_name": approver_name,
    }
    return None


def interview_routing_deferred_at_submit() -> dict[str, Any]:
    """Marker stored on interview submit until the interviewer signs and picks routing."""
    return {"v": 1, "deferred": True}


# Kept for backward compatibility with older call sites (lane, rc_id, om_id).
def build_chain_for_lane(
    lane: str,
    reporting_contact_id: int,
    operations_manager_id: int | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    rc = db.session.get(User, reporting_contact_id)
    if not rc:
        return [], []
    steps, _err = _build_chain_for_submitter(rc)
    return steps, []


def init_management_chain_on_submit(
    data: dict[str, Any],
    submitter: User,
) -> str | None:
    """
    Build the hr_mgmt_chain block from the submitter's lane.
    All signer IDs come from admin-assigned profile data — client picks are ignored.
    """
    # Strip any legacy/client picker fields — routing is fully derived server-side.
    for legacy_key in (
        "mgmt_supervisor_signer_id",
        "mgmt_reporting_manager_signer_id",
        "mgmt_operations_manager_signer_id",
    ):
        data.pop(legacy_key, None)

    # Admins with no supervisor on profile continue to bypass the chain straight to HR review.
    if getattr(submitter, "role", None) == "admin" and _supervisor_for(submitter) is None:
        data.pop(MGMT_CHAIN_KEY, None)
        return None

    steps, setup_err = _build_chain_for_submitter(submitter)
    if setup_err:
        return setup_err
    if not steps:
        return "Could not build the management approval chain. Contact support."

    sup_step = next(
        (s for s in steps if s.get("key") == "supervisor" and s.get("signer_mode") == "fixed_user"),
        None,
    )
    data[MGMT_CHAIN_KEY] = {
        "v": 1,
        "lane": lane_for_user(submitter),
        "current_index": 0,
        "steps": steps,
        "reporting_contact_id": (sup_step or {}).get("signer_id"),
        "reporting_contact_name": (sup_step or {}).get("pdf_label"),
        "pdf_hints": [],
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
    if gate == "operations_manager":
        return _desig(user) == "operations_manager"
    if gate == "general_manager":
        return _desig(user) == "general_manager"
    if gate == "hr_head_office" or gate == "hr_manager":
        return user_is_hr_head(user)
    return False


def user_mgmt_chain_completed_step(user: User | None, fd: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the management-chain step this user already signed, if any."""
    if not user or not has_management_chain(fd):
        return None
    uid = int(user.id)
    steps = (fd.get(MGMT_CHAIN_KEY) or {}).get("steps") or []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if not step.get("signature"):
            continue
        try:
            if int(step.get("signed_by_id") or 0) == uid:
                return step
        except (TypeError, ValueError):
            pass
    return None


def user_is_mgmt_chain_participant(user: User | None, fd: dict[str, Any] | None) -> bool:
    """
    True when the user belongs on this submission's management chain: assigned to a
    step (fixed user or designation pool) or already recorded as a signer on any step.
    """
    if not user or not has_management_chain(fd):
        return False
    uid = int(user.id)
    steps = (fd.get(MGMT_CHAIN_KEY) or {}).get("steps") or []
    for step in steps:
        if not isinstance(step, dict):
            continue
        try:
            if int(step.get("signed_by_id") or 0) == uid:
                return True
        except (TypeError, ValueError):
            pass
        if user_allowed_to_sign_step(user, step):
            return True
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
    if gate == "operations_manager":
        for u in _active_users_with_designation("operations_manager"):
            _notify_user(app, u.id, title, msg, submission_id, n_type)
        return
    if gate == "general_manager":
        for u in _active_users_with_designation("general_manager"):
            _notify_user(app, u.id, title, msg, submission_id, n_type)
        return
    if gate == "hr_head_office" or gate == "hr_manager":
        for u in _active_hr_signers():
            if u.role != "admin":
                _notify_user(app, u.id, title, msg, submission_id, n_type)
        return


def attach_submission_enter_management(fd: dict[str, Any], submission_id: str) -> str | None:
    """Return workflow_status for first mgmt step, or None if no chain."""
    return first_management_workflow_status(fd)


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

    # Mirror legacy GM fields for any step that also covers GM duties.
    if step.get("also_mirrors_gm_fields"):
        fd["gm_signature"] = step["signature"]
        fd["gm_comments"] = step["comments"]
        fd["gm_approved_by_id"] = user.id
        fd["gm_approved_by_name"] = step["signed_by_name"]
        fd["gm_approved_at"] = step["signed_at"]
        submission.general_manager_id = user.id
        submission.general_manager_approved_at = utc_now_naive()
        submission.general_manager_comments = step["comments"]

    if submission.module_type == "hr_commencement":
        from module_hr.hr_commencement_reporting import apply_dual_role_reporting_to_mirror

        apply_dual_role_reporting_to_mirror(fd, user, step)

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


# ---------------------------------------------------------------------------
# Sidebar UI context
# ---------------------------------------------------------------------------


_LANE_INTRO = {
    "technician": (
        "You are a Technician. Your form is signed in order by your immediate "
        "supervisor, the Operations Manager, the General Manager, and finally HR."
    ),
    "supervisor": (
        "You are a Supervisor. Your form is signed in order by the Operations "
        "Manager, the General Manager, and finally HR."
    ),
    "office_staff": (
        "You are office staff. Your form is signed by the General Manager and then HR."
    ),
}

_LANE_FLOW = {
    "technician": "Immediate supervisor -> Operations manager -> General manager -> HR",
    "supervisor": "Operations manager -> General manager -> HR",
    "office_staff": "General manager -> HR",
    "interview_routing": "Interviewer sign -> Next approver (chosen at sign) -> General manager -> HR",
}


def get_interview_routing_ui_context() -> dict[str, Any]:
    """Sidebar preview for interview assessment (chain deferred until interviewer signs)."""
    return {
        "success": True,
        "lane": "interview_routing",
        "lane_intro": (
            "Interview assessment: the assigned interviewer signs first and chooses who "
            "receives the form next. It then goes to the General Manager and HR head office."
        ),
        "lane_flow": _LANE_FLOW["interview_routing"],
        "chain": [
            {
                "key": "interviewer",
                "role_label": "Interviewer",
                "who_label": "Assigned at submit",
                "who_detail": "Signs digitally before management approval begins.",
                "signer_mode": "routed",
                "missing": False,
            },
            {
                "key": "routing_approver",
                "role_label": "Next approver",
                "who_label": "Chosen by interviewer",
                "who_detail": "Selected when the interviewer signs.",
                "signer_mode": "fixed_user",
                "missing": False,
            },
            {
                "key": "general_manager",
                "role_label": "General manager",
                "who_label": "Any active GM",
                "who_detail": "Designation pool sign-off.",
                "signer_mode": "designation",
                "missing": False,
            },
            {
                "key": "hr_head_office",
                "role_label": "HR (head office)",
                "who_label": "HR head office",
                "who_detail": "Final sign-off.",
                "signer_mode": "designation",
                "missing": False,
            },
        ],
        "supervisor": None,
        "default_reporting_to": None,
        "missing_pools": [],
        "setup_error": None,
        "admin_profile_bypass": False,
        "interview_routing_preview": True,
    }


def _chain_descriptor(submitter: User, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal steps to the sidebar's role+name descriptors."""
    om_pool = _active_users_with_designation("operations_manager")
    gm_pool = _active_users_with_designation("general_manager")
    hr_display = _canonical_hr_user()

    out: list[dict[str, Any]] = []
    for s in steps:
        key = s.get("key")
        if key == "supervisor":
            sup = db.session.get(User, int(s.get("signer_id") or 0)) if s.get("signer_id") else None
            who_label = (
                (sup.full_name or sup.username) if sup else "Not assigned"
            )
            out.append({
                "key": key,
                "role_label": "Immediate supervisor",
                "who_label": who_label,
                "who_detail": "Your reporting supervisor (assigned by admin).",
                "signer_mode": s.get("signer_mode"),
                "signer_id": s.get("signer_id"),
                "missing": sup is None,
            })
        elif key == "operations_manager":
            who_label, who_detail = _people_label(om_pool, "Operations Manager")
            out.append({
                "key": key,
                "role_label": "Operations manager",
                "who_label": who_label,
                "who_detail": who_detail,
                "signer_mode": "designation",
                "missing": not om_pool,
            })
        elif key == "general_manager":
            who_label, who_detail = _people_label(gm_pool, "General Manager")
            out.append({
                "key": key,
                "role_label": "General manager",
                "who_label": who_label,
                "who_detail": who_detail,
                "signer_mode": "designation",
                "missing": not gm_pool,
            })
        elif key == "hr_head_office":
            if hr_display:
                who_label = hr_display.full_name or hr_display.username or "HR manager"
                who_detail = "HR head office (final sign-off)."
                missing = False
            else:
                who_label = "Not assigned"
                who_detail = "Ask an administrator to create an HR manager account."
                missing = True
            out.append({
                "key": key,
                "role_label": "HR (head office)",
                "who_label": who_label,
                "who_detail": who_detail,
                "signer_mode": "designation",
                "signer_id": hr_display.id if hr_display else None,
                "missing": missing,
            })
        elif key == "routing_approver":
            uid = s.get("signer_id")
            u = db.session.get(User, int(uid)) if uid else None
            who_label = (u.full_name or u.username) if u else "Not assigned"
            out.append({
                "key": key,
                "role_label": "Next approver",
                "who_label": who_label,
                "who_detail": "Chosen by the interviewer when signing.",
                "signer_mode": "fixed_user",
                "signer_id": uid,
                "missing": u is None,
            })
        else:
            out.append({
                "key": key,
                "role_label": s.get("pdf_label") or "Reporting manager",
                "who_label": "Assigned signer",
                "who_detail": None,
                "signer_mode": s.get("signer_mode"),
                "missing": False,
            })
    return out


def get_mgmt_chain_ui_context(submitter: User | None) -> dict[str, Any]:
    """Routing preview for the HR submit sidebar (Box 2)."""
    if not submitter:
        return {"success": False, "error": "Not authenticated"}

    lane = lane_for_user(submitter)

    # Admin shortcut — bypasses the chain.
    default_reporting_to = _default_reporting_to_prefill(submitter)

    if getattr(submitter, "role", None) == "admin" and _supervisor_for(submitter) is None:
        return {
            "success": True,
            "lane": lane,
            "lane_intro": (
                "As an administrator with no supervisor on your profile, this submission "
                "skips the management chain and goes straight to the HR review queue."
            ),
            "lane_flow": "Direct to HR review",
            "chain": [],
            "supervisor": None,
            "default_reporting_to": default_reporting_to,
            "missing_pools": [],
            "setup_error": None,
            "admin_profile_bypass": True,
        }

    steps, setup_err = _build_chain_for_submitter(submitter)

    if setup_err and lane == "technician":
        sup_assigned = _supervisor_for(submitter)
        return {
            "success": True,
            "lane": lane,
            "lane_intro": _LANE_INTRO.get(lane),
            "lane_flow": _LANE_FLOW.get(lane),
            "chain": [],
            "supervisor": {
                "assigned": bool(sup_assigned),
                "id": sup_assigned.id if sup_assigned else None,
                "full_name": (sup_assigned.full_name or sup_assigned.username) if sup_assigned else None,
                "designation": (sup_assigned.designation if sup_assigned else None),
                "job_designation": (sup_assigned.job_designation or "") if sup_assigned else None,
                "phone": (sup_assigned.phone or "") if sup_assigned else None,
            },
            "default_reporting_to": default_reporting_to,
            "missing_pools": [],
            "setup_error": setup_err,
            "admin_profile_bypass": False,
        }

    chain = _chain_descriptor(submitter, steps)

    sup_descriptor = None
    if lane == "technician":
        sup_step = next((c for c in chain if c.get("key") == "supervisor"), None)
        if sup_step:
            sup_obj = _supervisor_for(submitter)
            sup_descriptor = {
                "assigned": not sup_step.get("missing"),
                "id": sup_obj.id if sup_obj else None,
                "full_name": sup_step.get("who_label") if not sup_step.get("missing") else None,
                "designation": "supervisor",
                "job_designation": (sup_obj.job_designation or "") if sup_obj else None,
                "phone": (sup_obj.phone or "") if sup_obj else None,
            }

    # Warn when a non-fixed pool we depend on is empty.
    missing_pools: list[str] = []
    for c in chain:
        if c.get("signer_mode") == "designation" and c.get("missing"):
            missing_pools.append(c.get("role_label"))

    return {
        "success": True,
        "lane": lane,
        "lane_intro": _LANE_INTRO.get(lane),
        "lane_flow": _LANE_FLOW.get(lane),
        "chain": chain,
        "supervisor": sup_descriptor,
        "default_reporting_to": default_reporting_to,
        "missing_pools": missing_pools,
        "setup_error": None,
        "admin_profile_bypass": False,
    }
