"""
In-app notifications for inspection form approval workflow.

Mirrors HR management sign-off notifications (bell dropdown): reviewers receive
"Inspection form — your approval" when a submission reaches their stage; the
submitter is notified on final approval or rejection.
"""
from __future__ import annotations

from sqlalchemy import or_

from app.models import Notification, User, db

INSPECTION_MODULE_TYPES = frozenset({
    'inspection', 'hvac_mep', 'civil', 'cleaning',
})

MODULE_DISPLAY = {
    'inspection': 'Inspection',
    'hvac_mep': 'Inspection',
    'civil': 'Inspection',
    'cleaning': 'Inspection',
}


def is_inspection_submission(submission) -> bool:
    return (getattr(submission, 'module_type', None) or '') in INSPECTION_MODULE_TYPES


def _module_display(module_type: str | None) -> str:
    return MODULE_DISPLAY.get(module_type or '', module_type or 'Inspection')


def _user_display(user) -> str | None:
    if not user:
        return None
    return getattr(user, 'full_name', None) or getattr(user, 'username', None)


def _submitter_name(submission) -> str:
    for uid in (getattr(submission, 'user_id', None), getattr(submission, 'supervisor_id', None)):
        if uid:
            u = db.session.get(User, uid)
            nm = _user_display(u)
            if nm:
                return nm
    return 'Supervisor'


def _submitter_user_id(submission) -> int | None:
    return getattr(submission, 'user_id', None) or getattr(submission, 'supervisor_id', None)


def _notify(user_id: int, title: str, message: str, n_type: str, submission_id: str) -> None:
    db.session.add(
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=n_type,
            submission_id=submission_id,
        )
    )


def _notify_users(users, title: str, message: str, n_type: str, submission_id: str) -> None:
    seen: set[int] = set()
    for u in users:
        if not u or u.id in seen:
            continue
        seen.add(u.id)
        _notify(u.id, title, message, n_type, submission_id)


def _supervisor_recipients_for(submission):
    """Supervisors who should receive the inspection review notification.

    Order: assigned supervisor on the submission → team supervisor for the
    technician submitter → broadcast to every active supervisor (same pattern
    as the ticketing supervisor queue).
    """
    recipients: list[User] = []
    seen: set[int] = set()

    def _add(u):
        if u and u.is_active and u.id not in seen:
            seen.add(u.id)
            recipients.append(u)

    sup_id = getattr(submission, 'supervisor_id', None)
    if sup_id:
        _add(db.session.get(User, sup_id))

    submitter_id = getattr(submission, 'user_id', None)
    if submitter_id:
        try:
            from app.models import TicketSupervisorTeam
            entry = TicketSupervisorTeam.query.filter_by(
                technician_id=submitter_id, is_active=True
            ).first()
            if entry:
                _add(db.session.get(User, entry.supervisor_id))
        except Exception:
            pass

    if not recipients:
        for u in User.query.filter(
            User.is_active == True,  # noqa: E712
            User.designation == 'supervisor',
        ).all():
            _add(u)

    return recipients


def _submitter_is_technician(submission) -> bool:
    uid = getattr(submission, 'user_id', None)
    if not uid:
        return False
    u = db.session.get(User, uid)
    if not u:
        return False
    des = (getattr(u, 'designation', None) or '').strip().lower()
    role = (getattr(u, 'role', None) or '').strip().lower()
    return des == 'technician' or (des not in ('supervisor', 'operations_manager', 'general_manager') and role == 'user')


def _operations_managers():
    return User.query.filter(
        User.is_active == True,  # noqa: E712
        or_(User.designation == 'operations_manager', User.role == 'admin'),
    ).all()


def _bd_reviewers():
    out = []
    for u in User.query.filter(User.is_active == True).all():  # noqa: E712
        if u.is_bd_inspection_reviewer() or getattr(u, 'designation', None) == 'business_development':
            out.append(u)
    return out


def _procurement_users():
    return User.query.filter(
        User.is_active == True,  # noqa: E712
        or_(User.designation == 'procurement', User.role == 'admin'),
    ).all()


def _general_managers():
    return User.query.filter(
        User.is_active == True,  # noqa: E712
        or_(User.designation == 'general_manager', User.role == 'admin'),
    ).all()


def _notify_supervisor_stage(submission, submitter: str, mod: str, sid: str) -> None:
    recipients = _supervisor_recipients_for(submission)
    if not recipients:
        return
    title = f'Inspection Form Queued: {sid}'
    msg = (
        f'{submitter} — {mod}. '
        'This form is in your supervisor queue — open it to review, comment, and sign.'
    )
    _notify_users(recipients, title, msg, 'inspection_approval_pending', sid)


def notify_inspection_stage(submission, stage: str | None = None) -> None:
    """
    Queue in-app notifications for the given workflow stage.
    Caller should commit the session (same transaction as the workflow update).
    """
    if not is_inspection_submission(submission):
        return

    stage = stage or (submission.workflow_status or '')
    sid = submission.submission_id
    submitter = _submitter_name(submission)
    mod = _module_display(submission.module_type)
    title = 'Inspection form — your approval'

    if stage in ('supervisor_review', 'supervisor_notified'):
        _notify_supervisor_stage(submission, submitter, mod, sid)
        return

    # Legacy / in-flight technician submissions still marked 'submitted'
    if stage == 'submitted' and (
        getattr(submission, 'supervisor_id', None) or _submitter_is_technician(submission)
    ):
        _notify_supervisor_stage(submission, submitter, mod, sid)
        return

    if stage in ('submitted', 'operations_manager_review'):
        msg = (
            f'{submitter} — {mod} ({sid}). '
            'Your review is required at the Operations Manager stage.'
        )
        _notify_users(_operations_managers(), title, msg, 'inspection_approval_pending', sid)
        return

    if stage == 'bd_procurement_review':
        base = f'{submitter} — {mod} ({sid}). Your review is required'
        if not submission.business_dev_approved_at:
            _notify_users(
                _bd_reviewers(),
                title,
                f'{base} (Business Development).',
                'inspection_approval_pending',
                sid,
            )
        if not submission.procurement_approved_at:
            _notify_users(
                _procurement_users(),
                title,
                f'{base} (Procurement).',
                'inspection_approval_pending',
                sid,
            )
        return

    if stage == 'general_manager_review':
        msg = (
            f'{submitter} — {mod} ({sid}). '
            'Your final approval is required as General Manager.'
        )
        _notify_users(_general_managers(), title, msg, 'inspection_approval_pending', sid)


def notify_inspection_completed(submission) -> None:
    if not is_inspection_submission(submission):
        return
    uid = _submitter_user_id(submission)
    if not uid:
        return
    sid = submission.submission_id
    mod = _module_display(submission.module_type)
    _notify(
        uid,
        'Inspection form approved',
        f'Your {mod} form ({sid}) is fully approved. All signatures received.',
        'inspection_approved',
        sid,
    )


def notify_inspection_rejected(submission, reason: str = '') -> None:
    if not is_inspection_submission(submission):
        return
    uid = _submitter_user_id(submission)
    if not uid:
        return
    sid = submission.submission_id
    mod = _module_display(submission.module_type)
    suffix = f' Reason: {reason}' if reason else ''
    _notify(
        uid,
        'Inspection form rejected',
        f'Your {mod} form ({sid}) was rejected and sent back for revision.{suffix}',
        'inspection_rejected',
        sid,
    )
