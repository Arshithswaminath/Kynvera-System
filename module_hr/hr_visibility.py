"""
HR pending-queue visibility.

Org-wide HR inbox is admin / designation hr_manager only.
Bare Module Access `access_hr` does not unlock other people's forms.
"""
from __future__ import annotations

from app.models import Submission, User
from module_hr.hr_management_chain import (
    ALL_MGMT_WF_STATUSES,
    WF_MGMT_GM,
    WF_MGMT_HR,
    pending_management_step_for_user,
)
from module_hr.replacement_signoff import pending_replacement_for_user


_HR_REVIEW_STATUSES = frozenset({"hr_review", WF_MGMT_HR})
_GM_REVIEW_STATUSES = frozenset({"gm_review", WF_MGMT_GM})
_TERMINAL_STATUSES = frozenset(
    {"approved", "completed", "closed_by_admin", "rejected", "withdrawn"}
)


def _role_is_admin(user: User | None) -> bool:
    return bool(user and str(user.role or "").strip().lower() == "admin")


def _desig(user: User | None) -> str:
    return ((user.designation or "") if user else "").strip().lower()


def user_sees_org_wide_hr_inbox(user: User | None) -> bool:
    """Full Pending HR Review inbox (not bare access_hr)."""
    if not user:
        return False
    if _role_is_admin(user):
        return True
    return _desig(user) == "hr_manager"


def user_sees_org_wide_gm_inbox(user: User | None) -> bool:
    if not user:
        return False
    if _role_is_admin(user):
        return True
    return _desig(user) == "general_manager"


def _is_hr_submission(submission: Submission | None) -> bool:
    return bool(submission and (submission.module_type or "").startswith("hr_"))


def user_is_pending_assignee(user: User | None, submission: Submission | None) -> bool:
    """True when this user must sign now (mgmt chain or replacement/routed)."""
    if not user or not _is_hr_submission(submission):
        return False
    fd = submission.form_data if isinstance(submission.form_data, dict) else {}
    status = submission.workflow_status or ""

    if status == "replacement_signoff":
        if pending_replacement_for_user(fd, user.id, submission.module_type or ""):
            return True

    if status in ALL_MGMT_WF_STATUSES or status in ("hr_review", "gm_review"):
        if pending_management_step_for_user(fd, status, user):
            return True

    return False


def user_can_see_hr_submission(user: User | None, submission: Submission | None) -> bool:
    """
    Whether the user may see this HR submission in pending/review lists.

    Org-wide: admin, hr_manager (all), GM (GM-stage forms).
    Personal: submitter, current signature assignee, named replacement/routed signer.
    """
    if not user or not _is_hr_submission(submission):
        return False

    status = (submission.workflow_status or "").strip()

    if _role_is_admin(user):
        return True

    if _desig(user) == "hr_manager":
        return True

    if _desig(user) == "general_manager" and status in _GM_REVIEW_STATUSES:
        return True

    if submission.user_id == user.id:
        return True

    if user_is_pending_assignee(user, submission):
        return True

    return False


def filter_hr_submissions_for_user(
    user: User | None, submissions: list[Submission]
) -> list[Submission]:
    if not user:
        return []
    if user_sees_org_wide_hr_inbox(user):
        return list(submissions)
    return [s for s in submissions if user_can_see_hr_submission(user, s)]


def filter_pending_hr_review_actionable(
    user: User | None, submissions: list[Submission]
) -> list[Submission]:
    """
    Pending HR Review inbox: only forms this user can act on now.
    Org-wide HR sees all hr_review / HO rows; others only if they are the current signer.
    Submitters do not appear here solely as owners.
    """
    if not user:
        return []
    if user_sees_org_wide_hr_inbox(user):
        return list(submissions)
    return [s for s in submissions if user_is_pending_assignee(user, s)]


def pending_hr_review_sign_meta(
    user: User | None, submission: Submission | None
) -> dict:
    """can_sign + sign_mode for Pending HR Review UI."""
    if not user or not _is_hr_submission(submission):
        return {"can_sign": False, "sign_mode": None}
    status = (submission.workflow_status or "").strip()
    fd = submission.form_data if isinstance(submission.form_data, dict) else {}

    if status == WF_MGMT_HR:
        pend = pending_management_step_for_user(fd, status, user)
        return {
            "can_sign": bool(pend),
            "sign_mode": "mgmt_hr_ho",
        }

    if status == "hr_review":
        # Legacy forward-to-GM path: only org-wide HR may approve via hr_approve.
        return {
            "can_sign": user_sees_org_wide_hr_inbox(user),
            "sign_mode": "legacy_hr",
        }

    return {"can_sign": False, "sign_mode": None}


def user_has_visible_pending_hr_review(user: User | None) -> bool:
    """True if Pending HR Review page/API would return at least one actionable row."""
    if not user:
        return False
    if user_sees_org_wide_hr_inbox(user):
        return True
    rows = (
        Submission.query.filter(
            Submission.module_type.like("hr_%"),
            Submission.workflow_status.in_(list(_HR_REVIEW_STATUSES)),
        )
        .order_by(Submission.created_at.desc())
        .limit(200)
        .all()
    )
    return any(user_is_pending_assignee(user, s) for s in rows)


def collect_personalized_hr_pending(user: User | None, limit: int = 300) -> list[Submission]:
    """HR forms awaiting this user's signature (mgmt / replacement), not org-wide."""
    if not user:
        return []
    statuses = list(ALL_MGMT_WF_STATUSES) + ["replacement_signoff", "hr_review", "gm_review"]
    rows = (
        Submission.query.filter(
            Submission.module_type.like("hr_%"),
            Submission.workflow_status.in_(statuses),
            Submission.workflow_status.notin_(list(_TERMINAL_STATUSES)),
        )
        .order_by(Submission.created_at.desc())
        .limit(limit)
        .all()
    )
    return [s for s in rows if user_is_pending_assignee(user, s)]
