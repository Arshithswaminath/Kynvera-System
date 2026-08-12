"""
Workflow Routes - New 5-Stage Approval System
Stage 1: Supervisor/Inspector (creates form)
Stage 2: Operations Manager (reviews, edits, approves)
Stage 3: Business Development + Procurement (parallel review)
Stage 4: General Manager (final approval)
"""
from flask import Blueprint, request, jsonify, current_app, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_, and_, not_, func
from sqlalchemy.orm import joinedload, noload, aliased
from sqlalchemy.orm.attributes import flag_modified
from app.models import db, User, Submission, AuditLog, DocHubDocument, Device, BDProject, Job
from common.error_responses import error_response, success_response
from common.workflow_notifications import send_team_notification
from common.inspection_inapp_notifications import (
    is_inspection_submission,
    notify_inspection_completed,
    notify_inspection_rejected,
    notify_inspection_stage,
)
from common.datetime_utils import utc_now_naive, naive_utc_isoformat_z
from datetime import datetime, timedelta
import copy

from module_hr.hr_management_chain import WF_MGMT_HR, WF_MGMT_RM, WF_MGMT_GM

workflow_bp = Blueprint('workflow_bp', __name__, url_prefix='/api/workflow')

HR_EMPLOYEE_POST_SUBMIT_EDIT_MINUTES = 30


def _hr_reporting_contact_user_ids_for_notification(submission, submitter):
    """Recipients for submitter withdrawal: reporting line from stored chain and/or user profile (deduped)."""
    out: list[int] = []
    seen: set[int] = set()
    fd = _submission_form_data_dict(submission)
    block = fd.get("hr_mgmt_chain")
    if isinstance(block, dict) and block.get("reporting_contact_id") is not None:
        try:
            rid = int(block["reporting_contact_id"])
            if rid > 0 and rid not in seen:
                seen.add(rid)
                out.append(rid)
        except (TypeError, ValueError):
            pass
    if submitter and getattr(submitter, "reporting_manager_id", None):
        try:
            rid = int(submitter.reporting_manager_id)
            if rid > 0 and rid not in seen:
                seen.add(rid)
                out.append(rid)
        except (TypeError, ValueError):
            pass
    return out


def _submission_form_data_dict(submission) -> dict:
    raw = getattr(submission, "form_data", None)
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            import json

            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def _hr_signature_blob_non_empty(val) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return False
        return s.startswith("data:image") and len(s) > 80
    if isinstance(val, dict):
        u = str(val.get("url") or "").strip()
        return len(u) > 40
    return False


def _hr_early_mgmt_signoff_closes_submitter_grace(form_data: dict) -> bool:
    """
    After reporting manager / GM (or technician supervisor/OM) signs on the HR chain—or the
    form stores gm_signature—submitter loses the remaining post-submit grace window immediately.
    """
    if not isinstance(form_data, dict):
        return False
    # Manager / GM line on-body fields (outside chain when used)
    for key in ("gm_signature", "reporting_to_signature", "reporting_manager_signature"):
        if _hr_signature_blob_non_empty(form_data.get(key)):
            return True
    block = form_data.get("hr_mgmt_chain")
    if not isinstance(block, dict) or block.get("v") != 1:
        return False
    steps = block.get("steps")
    if not isinstance(steps, list):
        return False
    for st in steps:
        if not isinstance(st, dict):
            continue
        if str(st.get("wf") or "") == WF_MGMT_HR:
            continue  # HR (head office) sign-off does not end employee grace earlier
        if _hr_signature_blob_non_empty(st.get("signature")):
            return True
    return False


def _hr_submitter_grace_time_still_running(submission) -> bool:
    """True iff within HR_EMPLOYEE_POST_SUBMIT_EDIT_MINUTES of submission.created_at (non-draft)."""
    if getattr(submission, "status", None) == "draft":
        return False
    created = getattr(submission, "created_at", None)
    if created is None:
        return False
    return utc_now_naive() < created + timedelta(minutes=HR_EMPLOYEE_POST_SUBMIT_EDIT_MINUTES)


def _hr_submission_record_finalized_locked(submission) -> bool:
    """HR request fully approved / completed — normal users must not reopen line edits (?edit= / PUT)."""
    if not _is_hr_module_submission(submission):
        return False
    ws = str(getattr(submission, "workflow_status", "") or "").strip().lower()
    st = str(getattr(submission, "status", "") or "").strip().lower()
    if ws == "closed_by_admin":
        return True
    if ws == "withdrawn":
        return True
    if st == "completed":
        return True
    if ws == "approved":
        return True
    return False


def _is_hr_module_submission(submission) -> bool:
    m = submission.module_type or ""
    return isinstance(m, str) and m.startswith("hr_")


def _user_role_lower(user) -> str:
    return str(getattr(user, "role", None) or "").strip().lower()


def _user_desig_lower(user) -> str:
    return str(getattr(user, "designation", None) or "").strip().lower()


def _submitter_can_use_hr_employee_edit_grace_period(user, submission) -> bool:
    if not submission.user_id or submission.user_id != user.id:
        return False
    if submission.status == "draft":
        return False
    fd = _submission_form_data_dict(submission)
    if _hr_early_mgmt_signoff_closes_submitter_grace(fd):
        return False
    return _hr_submitter_grace_time_still_running(submission)


def _hr_submitter_grace_deadline_iso(submission):
    """
    End of the 30-minute post-submit window for the original submitter’s employee self-edits.
    Returned on ?edit= hydration while the window is still open (countdown in UI).
    Omitted (None) once time passes or a reporting manager / GM (or prior chain step) signs.
    """
    if getattr(submission, "status", None) == "draft":
        return None
    fd = _submission_form_data_dict(submission)
    if _hr_early_mgmt_signoff_closes_submitter_grace(fd):
        return None
    if not _hr_submitter_grace_time_still_running(submission):
        return None
    created = getattr(submission, "created_at", None)
    if created is None:
        return None
    deadline = created + timedelta(minutes=HR_EMPLOYEE_POST_SUBMIT_EDIT_MINUTES)
    try:
        return naive_utc_isoformat_z(deadline)
    except Exception:
        return None


def _hr_anytime_line_editor(user, submission) -> bool:
    """Reporting manager of submitter, HR roster, GM, or admin — may edit anytime."""
    if _user_role_lower(user) == "admin":
        return True
    if _user_desig_lower(user) == "general_manager":
        return True
    if getattr(user, "access_hr", False) or _user_desig_lower(user) == "hr_manager":
        return True
    submitter = db.session.get(User, submission.user_id) if submission.user_id else None
    return bool(submitter and submitter.reporting_manager_id == user.id)


def _user_may_edit_hr_record_fields(user) -> bool:
    """HR Review / For HR only — must match `module_hr.routes.user_is_hr_staff` / template `is_hr`.
    Users with only `access_hr` may use HR modules but must not unlock those rows on ?edit= hydrated views."""
    if _user_role_lower(user) == "admin":
        return True
    return _user_desig_lower(user) == "hr_manager"


# Blocks that must not be mutated via PUT /submissions/:id/update — only dedicated
# submit / routed-sign / mgmt-signoff / approve endpoints may write these.
_HR_IMMUTABLE_TRAIL_KEYS = frozenset({
    "_routed_signoffs",
    "hr_mgmt_chain",
    "replacement_signers",
    "_reporting_to_signoff",
})

# Flat signature mirrors: allow setting a new non-empty value, but never clear an
# existing captured signature through the generic update endpoint.
_HR_PRESERVE_NONEMPTY_SIG_KEYS = (
    "gm_signature",
    "reporting_manager_signature",
    "hr_signature",
)


def _submission_stored_form_data_dict(submission) -> dict:
    old = submission.form_data or {}
    if isinstance(old, str):
        try:
            import json as _json

            old = _json.loads(old)
        except Exception:
            old = {}
    return old if isinstance(old, dict) else {}


def _restore_hr_approval_trail_fields(submission, form_data):
    """
    Keep teammate / management approval trail intact across generic form updates.

    Without this, a grace-period submitter or anytime line editor can clear
    `_routed_signoffs` / `hr_mgmt_chain` (or wipe flat GM/RM signatures) via
    form_data / form_data_updates while workflow_status stays unchanged.
    """
    if not isinstance(form_data, dict):
        return form_data
    old = _submission_stored_form_data_dict(submission)
    for key in _HR_IMMUTABLE_TRAIL_KEYS:
        if key in old:
            form_data[key] = copy.deepcopy(old[key])
        else:
            form_data.pop(key, None)
    for key in _HR_PRESERVE_NONEMPTY_SIG_KEYS:
        if _hr_signature_blob_non_empty(old.get(key)) and not _hr_signature_blob_non_empty(
            form_data.get(key)
        ):
            form_data[key] = copy.deepcopy(old[key]) if isinstance(old.get(key), dict) else old[key]
    return form_data


def _enforce_hr_record_fields_in_form_data(user, submission, form_data):
    """
    Non–HR users must not change hr_* keys (HR review / For HR only blocks).
    Strip any hr_* from payload, then restore those keys from stored submission.
    Always restore approval-trail blocks so update cannot wipe teammate/mgmt signs.
    """
    if not _is_hr_module_submission(submission) or not isinstance(form_data, dict):
        return form_data
    if not _user_may_edit_hr_record_fields(user):
        form_data = {k: v for k, v in form_data.items() if not str(k).startswith("hr_")}
        old = _submission_stored_form_data_dict(submission)
        for k, v in old.items():
            if str(k).startswith("hr_"):
                form_data[k] = v
    return _restore_hr_approval_trail_fields(submission, form_data)


def _hr_leave_edit_api_flags(user, submission) -> dict:
    """Hydration hints for HR forms (?edit=) — scoped to Submission row + user.

    Post-submit: original submitter gets HR_EMPLOYEE_POST_SUBMIT_EDIT_MINUTES (see constant),
    unless a reporting manager / GM signature (or an equivalent mgmt-chain step before HR) exists.

    Once that management sign-off exists, employee-facing sections are only editable by admin or
    the designated HR manager; reporting managers / GMs no longer receive can_edit_employee_sections
    (HR-only rows still follow can_edit_hr_sections). PUT /submissions/:id/update remains permissive
    for line editors where historically allowed; UI + save-kind logic reflect these flags.
    """
    if not _is_hr_module_submission(submission):
        return {}
    if getattr(submission, "status", None) == "draft":
        return {
            "can_edit_employee_sections": True,
            "can_edit_hr_sections": _user_may_edit_hr_record_fields(user),
            "employee_edit_until": None,
            "submitter_employee_edit_window_closed": False,
            "submitter_grace_revoked_by_management_signature": False,
            "hr_request_approved_completed": False,
        }
    ws = str(getattr(submission, "workflow_status", "") or "").strip().lower()
    if ws == "withdrawn":
        is_admin = _user_role_lower(user) == "admin"
        return {
            "can_edit_employee_sections": is_admin,
            "can_edit_hr_sections": is_admin,
            "employee_edit_until": None,
            "submitter_employee_edit_window_closed": True,
            "submitter_grace_revoked_by_management_signature": False,
            "hr_request_approved_completed": False,
            "hr_request_withdrawn": True,
        }
    if _hr_submission_record_finalized_locked(submission):
        is_admin = _user_role_lower(user) == "admin"
        return {
            "can_edit_employee_sections": is_admin,
            "can_edit_hr_sections": is_admin,
            "employee_edit_until": None,
            "submitter_employee_edit_window_closed": False,
            "submitter_grace_revoked_by_management_signature": False,
            "hr_request_approved_completed": True,
        }
    anytime = _hr_anytime_line_editor(user, submission)
    grace_allowed = _submitter_can_use_hr_employee_edit_grace_period(user, submission)
    fd = _submission_form_data_dict(submission)
    mgmt_signed = _hr_early_mgmt_signoff_closes_submitter_grace(fd)
    # After RM / GM (or technician supervisor–GM chain before HR), freeze employee-facing fields
    # for everyone except admin / designated HR manager (HR-only zones remain via can_hr).
    if mgmt_signed:
        can_emp = bool(
            _user_role_lower(user) == "admin" or _user_may_edit_hr_record_fields(user)
        )
    else:
        can_emp = bool(anytime or grace_allowed)
    # HR-review / HR-only portions: actual HR roster (or admin), not reporting managers / GM alone.
    can_hr = bool(_user_may_edit_hr_record_fields(user) and (anytime or grace_allowed))
    emp_until = _hr_submitter_grace_deadline_iso(submission)
    submitter_uid = getattr(submission, "user_id", None)
    hint_grace_closed = bool(
        submitter_uid is not None
        and getattr(user, "id", None) == submitter_uid
        and getattr(submission, "status", None) != "draft"
        and not anytime
        and not grace_allowed
    )
    grace_revoked_by_mgmt = bool(
        submitter_uid is not None
        and getattr(user, "id", None) == submitter_uid
        and getattr(submission, "status", None) != "draft"
        and not anytime
        and not grace_allowed
        and _hr_early_mgmt_signoff_closes_submitter_grace(fd)
        and _hr_submitter_grace_time_still_running(submission)
    )
    return {
        "can_edit_employee_sections": can_emp,
        "can_edit_hr_sections": can_hr,
        "employee_edit_until": emp_until,
        "submitter_employee_edit_window_closed": hint_grace_closed,
        "submitter_grace_revoked_by_management_signature": grace_revoked_by_mgmt,
        "hr_request_approved_completed": False,
    }


HR_REVISION_AUDIT_CAP = 400

# Client must never override server-owned post-submit audit metadata (HR merge path).
_HR_REVISION_AUDIT_KEYS = frozenset(
    {
        "submission_form_revision_history",
        "submission_form_revision_count",
        "submission_form_revision_at",
        "submission_form_revision_by_id",
        "submission_form_revision_by_name",
    }
)


def _pop_hr_revision_audit_from_updates(updates: dict) -> None:
    if not isinstance(updates, dict):
        return
    for k in _HR_REVISION_AUDIT_KEYS:
        updates.pop(k, None)


def _stamp_hr_submission_revision_history(form_data: dict, user) -> None:
    now = utc_now_naive()
    ts = naive_utc_isoformat_z(now)
    by_name = (user.full_name or user.username or "").strip() or (user.username or "")
    try:
        prev = int(form_data.get("submission_form_revision_count") or 0)
    except (TypeError, ValueError):
        prev = 0
    new_count = prev + 1
    form_data["submission_form_revision_count"] = new_count
    form_data["submission_form_revision_at"] = ts
    form_data["submission_form_revision_by_id"] = user.id
    form_data["submission_form_revision_by_name"] = by_name

    entry = {
        "save_index": new_count,
        "at": ts,
        "by_id": user.id,
        "by_name": by_name,
    }
    hist = form_data.get("submission_form_revision_history")
    if not isinstance(hist, list):
        hist = []
    hist = list(hist)
    hist.append(entry)
    if len(hist) > HR_REVISION_AUDIT_CAP:
        hist = hist[-HR_REVISION_AUDIT_CAP:]
    form_data["submission_form_revision_history"] = hist


def _ensure_items_photos(form_data):
    """Convert photo_urls to photos for items/work_items (HVAC/Civil). Mutates form_data in place."""
    if not isinstance(form_data, dict):
        return
    for key in ('items', 'work_items'):
        items = form_data.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if 'photo_urls' in item and isinstance(item['photo_urls'], list):
                item['photos'] = [{"saved": None, "path": None, "url": u, "is_cloud": True} for u in item['photo_urls'] if u]
            elif 'photos' not in item or not item.get('photos'):
                item['photos'] = []


def _preserve_submitter_signature_before_supervisor_signoff(form_data, submission) -> None:
    """
    Legacy inspection forms stored the submitter's first signature in supervisor_signature.
    Before the supervisor's sign-off overwrites that field, copy it to tech_signature once.
    """
    if not isinstance(form_data, dict):
        return
    if _hr_signature_blob_non_empty(form_data.get('tech_signature')) or _hr_signature_blob_non_empty(
        form_data.get('submitter_signature')
    ):
        return
    old_sup = form_data.get('supervisor_signature')
    if not _hr_signature_blob_non_empty(old_sup):
        return
    if getattr(submission, 'supervisor_reviewed_at', None):
        return
    preserved = copy.deepcopy(old_sup) if isinstance(old_sup, dict) else old_sup
    form_data['tech_signature'] = preserved
    if not form_data.get('submitter_signature'):
        form_data['submitter_signature'] = preserved


def _preserve_submitter_comments_before_supervisor_signoff(form_data, submission) -> None:
    """Copy legacy submitter comment into submitter_comments before supervisor overwrites supervisor_comments."""
    if not isinstance(form_data, dict):
        return
    existing = form_data.get('submitter_comments')
    if existing is not None and str(existing).strip():
        return
    if getattr(submission, 'supervisor_reviewed_at', None):
        return
    legacy = form_data.get('supervisor_comments') or form_data.get('general_comments')
    if legacy is not None and str(legacy).strip() and str(legacy).strip().lower() != 'none':
        form_data['submitter_comments'] = str(legacy).strip()


def _merge_items_with_photos(existing_list, payload_list, key='work_items'):
    """
    Merge existing items with payload items: combine photo_urls, prefer payload for other fields.
    Preserves previously submitted form data (old images, etc.) and adds updates.
    """
    if not isinstance(existing_list, list):
        existing_list = []
    if not isinstance(payload_list, list):
        payload_list = []
    existing_list = [dict(x) for x in existing_list]
    payload_list = [dict(x) for x in payload_list]
    n = max(len(existing_list), len(payload_list))
    merged = []
    for i in range(n):
        base = existing_list[i] if i < len(existing_list) else {}
        upd = payload_list[i] if i < len(payload_list) else {}
        item = dict(base)
        item.update(upd)
        # Combine photo_urls from both (existing + new), dedupe
        existing_urls = []
        if base.get('photo_urls') and isinstance(base['photo_urls'], list):
            existing_urls = [u for u in base['photo_urls'] if u]
        if base.get('photos') and isinstance(base['photos'], list):
            for p in base['photos']:
                u = p.get('url') if isinstance(p, dict) else (p if isinstance(p, str) else None)
                if u and u not in existing_urls:
                    existing_urls.append(u)
        new_urls = []
        if upd.get('photo_urls') and isinstance(upd['photo_urls'], list):
            new_urls = [u for u in upd['photo_urls'] if u]
        if upd.get('photos') and isinstance(upd['photos'], list):
            for p in upd['photos']:
                u = p.get('url') if isinstance(p, dict) else (p if isinstance(p, str) else None)
                if u and u not in new_urls:
                    new_urls.append(u)
        all_urls = list(dict.fromkeys(existing_urls + new_urls))
        item['photo_urls'] = all_urls
        merged.append(item)
    return merged


def get_module_functions(module_type):
    """
    Get module-specific functions for signature handling and job processing.
    Returns (save_signature_dataurl, get_paths, process_job) functions.
    """
    # Unified inspection (+ legacy trade types) share one implementation
    if module_type in ('inspection', 'hvac_mep', 'hvac', 'civil', 'cleaning'):
        from module_inspection.routes import save_signature_dataurl, get_paths, process_job
        return save_signature_dataurl, get_paths, process_job
    elif module_type == 'qhsi_inspection':
        from module_qhsi.routes import save_signature_dataurl, get_paths, process_job
        return save_signature_dataurl, get_paths, process_job
    else:
        raise ValueError(f"Unknown module type: {module_type}")

# Valid designations for workflow
VALID_DESIGNATIONS = [
    'supervisor',
    'operations_manager',
    'business_development',
    'procurement',
    'general_manager'
]

# Workflow status progression
WORKFLOW_STAGES = {
    'submitted': 'operations_manager_review',
    'operations_manager_review': 'operations_manager_approved',
    'operations_manager_approved': 'bd_procurement_review',
    'bd_procurement_review': 'general_manager_review',  # After both BD & Procurement approve
    'general_manager_review': 'general_manager_approved',
    'general_manager_approved': 'completed'
}


def log_audit(user_id, action, resource_type=None, resource_id=None, details=None):
    """Create audit log entry"""
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to create audit log: {str(e)}")
        db.session.rollback()


def get_user_pending_submissions(user):
    """Get submissions pending for a user's designation"""
    designation = user.designation
    base_filter = Submission.workflow_status != 'closed_by_admin'
    
    if designation == 'operations_manager':
        return Submission.query.filter(
            base_filter,
            Submission.workflow_status == 'operations_manager_review'
        ).order_by(Submission.created_at.desc()).all()
    
    elif user.is_bd_inspection_reviewer():
        return Submission.query.filter(
            base_filter,
            Submission.workflow_status == 'bd_procurement_review',
            or_(
                Submission.business_dev_approved_at.is_(None),
                Submission.business_dev_approved_at == None
            )
        ).order_by(Submission.created_at.desc()).all()
    
    elif designation == 'procurement':
        return Submission.query.filter(
            base_filter,
            Submission.workflow_status == 'bd_procurement_review',
            or_(
                Submission.procurement_approved_at.is_(None),
                Submission.procurement_approved_at == None
            )
        ).order_by(Submission.created_at.desc()).all()
    
    elif designation == 'general_manager':
        return Submission.query.filter(
            base_filter,
            Submission.workflow_status == 'general_manager_review'
        ).order_by(Submission.created_at.desc()).all()
    
    elif designation in ('supervisor', 'manager'):
        # Supervisors / site managers: technician forms awaiting their review, plus own drafts/rejected.
        return Submission.query.filter(
            base_filter,
            or_(
                and_(
                    Submission.supervisor_id == user.id,
                    Submission.workflow_status.in_([
                        'supervisor_review', 'supervisor_notified', 'submitted'
                    ]),
                ),
                and_(
                    Submission.user_id == user.id,
                    Submission.workflow_status.in_(['draft', 'rejected']),
                ),
            ),
        ).order_by(Submission.created_at.desc()).all()
    
    return []


# Workflow stages strictly after each reviewer has completed sign-off (inspection chain).
_INSP_PAST_SUPERVISOR = (
    'operations_manager_review', 'operations_manager_approved',
    'bd_procurement_review', 'general_manager_review', 'completed',
)


def _inspection_reviewed_clauses_for_user(user):
    """SQLAlchemy OR clauses: inspection forms this user has signed off on."""
    uid = user.id
    d = (getattr(user, 'designation') or '').strip().lower()
    clauses = []

    if d in ('supervisor', 'manager'):
        clauses.append(and_(
            Submission.supervisor_id == uid,
            or_(
                Submission.supervisor_reviewed_at.isnot(None),
                Submission.workflow_status.in_(_INSP_PAST_SUPERVISOR),
            ),
        ))

    if d == 'operations_manager':
        clauses.append(and_(
            Submission.operations_manager_id == uid,
            Submission.operations_manager_approved_at.isnot(None),
        ))

    try:
        is_bd = user.is_bd_inspection_reviewer()
    except Exception:
        is_bd = d == 'business_development'
    if is_bd:
        clauses.append(and_(
            Submission.business_dev_id == uid,
            Submission.business_dev_approved_at.isnot(None),
        ))

    if d == 'procurement':
        clauses.append(and_(
            Submission.procurement_id == uid,
            Submission.procurement_approved_at.isnot(None),
        ))

    if d == 'general_manager':
        clauses.append(and_(
            Submission.general_manager_id == uid,
            Submission.general_manager_approved_at.isnot(None),
        ))

    return clauses


def _query_inspection_reviewed_for_user(user, list_opts):
    """All inspection submissions the user has signed off on (any applicable role)."""
    if (getattr(user, 'role') or '').strip().lower() == 'admin':
        return (
            Submission.query.options(*list_opts)
            .filter(
                _filter_inspection(),
                Submission.workflow_status.in_(['completed', 'closed_by_admin', 'rejected']),
            )
            .order_by(Submission.updated_at.desc())
            .limit(200)
            .all()
        )

    clauses = _inspection_reviewed_clauses_for_user(user)
    if not clauses:
        return []

    return (
        Submission.query.options(*list_opts)
        .filter(_filter_inspection(), or_(*clauses))
        .order_by(Submission.updated_at.desc())
        .all()
    )


def can_edit_submission(user, submission):
    """Check if user can edit a submission based on current workflow stage"""
    if str(getattr(user, "role", None) or "").strip().lower() == "admin":
        return True
    
    designation = user.designation
    status = submission.workflow_status

    if status == 'closed_by_admin':
        return False

    # HR forms: submitter has a short grace window; RM / HR / GM have broader access via _hr_anytime_line_editor.
    if _is_hr_module_submission(submission):
        if _hr_submission_record_finalized_locked(submission):
            return False
        if _submitter_can_use_hr_employee_edit_grace_period(user, submission):
            return True
        if _hr_anytime_line_editor(user, submission):
            return True
    
    # Allow any user to edit their own drafts
    if status == 'draft':
        is_own_submission = (
            (hasattr(submission, 'supervisor_id') and submission.supervisor_id == user.id) or
            (submission.user_id == user.id)
        )
        if is_own_submission:
            return True
    
    # Supervisor can edit their own submissions if:
    # - Status is draft (user's own draft)
    # - Status is submitted/rejected (initial state)
    # - Status is operations_manager_review but not yet approved (allows updates before review)
    if designation == 'supervisor':
        is_assigned_reviewer = (
            hasattr(submission, 'supervisor_id') and submission.supervisor_id == user.id
        )
        is_own_submission = (
            is_assigned_reviewer or (submission.user_id == user.id)
        )

        if not is_own_submission:
            return False

        # Technician submission awaiting this supervisor's review
        if is_assigned_reviewer and status in ('supervisor_review', 'supervisor_notified', 'submitted'):
            return True

        # Supervisor's own submission (submitter is also supervisor)
        if status in ['draft', 'submitted', 'rejected', None]:
            return True
        if status == 'operations_manager_review' and not submission.operations_manager_approved_at:
            return True
        return False
    
    # Operations Manager can edit during their review stage
    # Allow if status is operations_manager_review, OR if OM is assigned but hasn't approved yet
    # Also allow OM to re-edit after approval (like supervisor resubmissions)
    if designation == 'operations_manager':
        # Primary case: Status is at OM review stage
        if status == 'operations_manager_review':
            current_app.logger.info(f"✅ OM {user.id} can edit submission {submission.submission_id} - status is operations_manager_review")
            return True
        
        # Secondary case: OM is assigned to this submission and hasn't approved yet
        if hasattr(submission, 'operations_manager_id') and submission.operations_manager_id == user.id:
            if not submission.operations_manager_approved_at:
                current_app.logger.info(f"✅ OM {user.id} can edit submission {submission.submission_id} - assigned and not yet approved")
                return True
            # Allow OM to re-edit their own reviewed submissions (even after approval)
            # This allows OM to update comments/signature like supervisors can resubmit
            current_app.logger.info(f"✅ OM {user.id} can edit submission {submission.submission_id} - assigned OM can re-edit")
            return True
        
        # Tertiary case: Status is at later stages but OM wants to review/edit from history
        # Allow OM to access any submission that has passed through OM review stage
        if status in ['bd_procurement_review', 'general_manager_review', 'completed']:
            current_app.logger.info(f"✅ OM {user.id} can edit submission {submission.submission_id} - OM can review completed submissions")
            return True
        
        current_app.logger.warning(f"❌ OM {user.id} cannot edit submission {submission.submission_id} - status: {status}, assigned: {getattr(submission, 'operations_manager_id', None)}, approved: {getattr(submission, 'operations_manager_approved_at', None)}")
        return False
    
    # Business Development can edit during BD/Procurement review stage
    # Also allow BD to re-edit after approval or in later stages
    if user.is_bd_inspection_reviewer():
        if status == 'bd_procurement_review':
            return True
        # Allow BD to edit at later stages (GM review, completed)
        if status in ['general_manager_review', 'completed']:
            return True
        return False
    
    # Procurement can edit during BD/Procurement review stage
    # Also allow Procurement to re-edit after approval or in later stages
    if designation == 'procurement':
        if status == 'bd_procurement_review':
            return True
        # Allow Procurement to edit at later stages (GM review, completed)
        if status in ['general_manager_review', 'completed']:
            return True
        return False
    
    # General Manager can edit during their review stage and after completion
    if designation == 'general_manager':
        if status in ['general_manager_review', 'completed']:
            return True
        return False
    
    return False


@workflow_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def workflow_dashboard():
    """Workflow dashboard page for all roles"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return render_template('access_denied.html', 
                                 module='Workflow',
                                 message='User not found.'), 404
        
        if not hasattr(user, 'designation') or user.designation not in VALID_DESIGNATIONS:
            if user.role != 'admin':
                return render_template('access_denied.html',
                                     module='Workflow',
                                     message='You must have a valid designation assigned to access workflow.'), 403
        
        return render_template('workflow_dashboard.html', 
                             user_designation=user.designation or 'admin',
                             user_role=user.role,
                             user_name=user.full_name or user.username)
    except Exception as e:
        current_app.logger.error(f"Error loading workflow dashboard: {str(e)}", exc_info=True)
        return render_template('access_denied.html',
                             module='Workflow',
                             message='Error loading dashboard.'), 500


@workflow_bp.route('/history', methods=['GET'])
@jwt_required()
def history_page():
    """Render the Review History page"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return render_template('access_denied.html', module='Workflow', message='User not found.'), 404
            
        if not hasattr(user, 'designation') or user.designation not in VALID_DESIGNATIONS:
            if user.role != 'admin':
                return render_template('access_denied.html',
                                     module='Workflow',
                                     message='You must have a valid designation to access workflow history.'), 403
        
        is_supervisor = user.designation == 'supervisor'
        return render_template('workflow_history.html', 
                             user_designation=user.designation or 'admin',
                             user_name=user.full_name or user.username,
                             is_supervisor=is_supervisor)
    except Exception as e:
        current_app.logger.error(f"Error loading history page: {str(e)}", exc_info=True)
        return render_template('access_denied.html', module='Workflow', message='Error loading history page.'), 500


@workflow_bp.route('/submissions/pending', methods=['GET'])
@jwt_required()
def get_pending_submissions():
    """Get pending submissions for current user based on their designation"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if not hasattr(user, 'designation') or not user.designation:
            if user.role != 'admin':
                return error_response('No designation assigned', status_code=403, error_code='NO_DESIGNATION')
            # Admin sees all pending - use eager loading for user relationship
            submissions = Submission.query.options(
                joinedload(Submission.user)
            ).filter(
                Submission.workflow_status.notin_(['completed', 'closed_by_admin', 'rejected'])
            ).order_by(Submission.created_at.desc()).all()
        else:
            submissions = get_user_pending_submissions(user)
        
        result = []
        for submission in submissions:
            # Use eager-loaded user if available, otherwise query
            sub_user = getattr(submission, 'user', None) or (db.session.get(User, submission.user_id) if submission.user_id else None)
            sub_dict = submission.to_dict()
            sub_dict['user'] = sub_user.to_dict() if sub_user else None
            sub_dict['can_edit'] = can_edit_submission(user, submission)
            result.append(sub_dict)
        
        return success_response({
            'submissions': result,
            'count': len(result)
        })
    except Exception as e:
        current_app.logger.error(f"Error getting pending submissions: {str(e)}", exc_info=True)
        return error_response('Failed to get pending submissions', status_code=500, error_code='DATABASE_ERROR')


INSPECTION_MODULE_TYPES = ('inspection', 'hvac_mep', 'civil', 'cleaning', 'qhsi_inspection', 'qhsi_staff_compliance')
INSPECTION_HISTORY_DESIGNATIONS = (
    'supervisor',
    'operations_manager',
    'business_development',
    'procurement',
    'general_manager',
)


def _filter_inspection():
    return Submission.module_type.in_(INSPECTION_MODULE_TYPES)


def _filter_hr():
    return Submission.module_type.like('hr_%')


def _user_has_inspection_history_access(user) -> bool:
    if not user:
        return False
    if getattr(user, 'role', None) == 'admin':
        return True
    d = (getattr(user, 'designation', None) or '').strip().lower()
    if d in INSPECTION_HISTORY_DESIGNATIONS:
        return True
    if bool(getattr(user, 'access_business_development', False)):
        return True
    try:
        return bool(user.is_bd_inspection_reviewer())
    except Exception:
        return False


def _inspection_history_query_for_user(base_query, user):
    """Inspection history: pending at the user's stage plus forms they already reviewed."""
    if not user:
        return None
    if getattr(user, 'role', None) == 'admin':
        return base_query.filter(_filter_inspection())

    d = (getattr(user, 'designation', None) or '').strip().lower()
    base = base_query.filter(_filter_inspection())

    if d == 'supervisor':
        return base.filter(or_(Submission.supervisor_id == user.id, Submission.user_id == user.id))

    if d == 'operations_manager':
        # Pending OM queue is not scoped by operations_manager_id (set only after sign-off).
        return base.filter(or_(
            Submission.workflow_status == 'operations_manager_review',
            Submission.operations_manager_id == user.id,
        ))

    if d == 'procurement':
        return base.filter(or_(
            and_(
                Submission.workflow_status == 'bd_procurement_review',
                Submission.procurement_approved_at.is_(None),
            ),
            Submission.procurement_id == user.id,
        ))

    if d == 'general_manager':
        return base.filter(or_(
            Submission.workflow_status == 'general_manager_review',
            Submission.workflow_status == 'general_manager_approved',
            Submission.workflow_status == 'completed',
            Submission.general_manager_id == user.id,
        ))

    is_bd = (
        d == 'business_development'
        or bool(getattr(user, 'access_business_development', False))
        or (hasattr(user, 'is_bd_inspection_reviewer') and user.is_bd_inspection_reviewer())
    )
    if is_bd:
        return base.filter(or_(
            and_(
                Submission.workflow_status == 'bd_procurement_review',
                Submission.business_dev_approved_at.is_(None),
            ),
            Submission.business_dev_id == user.id,
        ))

    return None


def _my_submissions_filter(user_id):
    """Submissions created by this user (canonical submitter = user_id on the record)."""
    try:
        uid = int(user_id) if user_id is not None else -1
    except (TypeError, ValueError):
        uid = -1
    return Submission.user_id == uid


def _user_sees_org_wide_submissions(user, scope: str) -> bool:
    """Organization-wide Submitted forms list (all users' rows)."""
    if not user:
        return False
    if _user_role_lower(user) == 'admin':
        return True
    if scope in ('all', 'hr'):
        if _user_desig_lower(user) == 'hr_manager':
            return True
        if _user_desig_lower(user) == 'general_manager':
            return True
        if getattr(user, 'access_hr', False):
            return True
    return False


def _hr_submissions_list_query_for_user(base_query, user, scope: str = 'hr'):
    """HR rows on Submitted forms: privileged viewers see all; others see only what they submitted."""
    if not user:
        return None
    q = base_query.filter(_filter_hr())
    if _user_sees_org_wide_submissions(user, scope):
        return q
    return q.filter(_my_submissions_filter(user.id))


def _inspection_submissions_list_query_for_user(base_query, user, scope: str = 'inspection'):
    """Inspection rows on Submitted forms: admin sees all; others see only what they submitted."""
    if not user:
        return None
    q = base_query.filter(_filter_inspection())
    if _user_sees_org_wide_submissions(user, scope):
        return q
    return q.filter(_my_submissions_filter(user.id))


def _hr_latest_activity_from_form_data(form_data, workflow_status, submission_status):
    """Most recent HR sign-off / revision event for submitted-forms cards."""
    try:
        from module_hr.hr_signoff_activity import compute_hr_signoff_activity, _event_sort_ts
    except Exception:
        return None
    if isinstance(form_data, str):
        try:
            import json as _json
            form_data = _json.loads(form_data)
        except Exception:
            form_data = {}
    if not isinstance(form_data, dict):
        form_data = {}
    activities, _fp = compute_hr_signoff_activity(form_data, workflow_status, submission_status)
    if not activities:
        return None
    latest = max(activities, key=lambda e: _event_sort_ts((e or {}).get('at')))
    return {
        'label': latest.get('label'),
        'actor': latest.get('actor'),
        'at': latest.get('at'),
        'detail': (latest.get('detail') or '').strip() or None,
        'kind': latest.get('kind'),
    }


def _build_live_activity_feed(submissions_list, limit=30):
    """Cross-form activity stream for org-wide submitted-forms view."""
    feed = []
    for sub in submissions_list or []:
        la = sub.get('latest_activity')
        if not la or not la.get('at'):
            continue
        try:
            from module_hr.hr_signoff_activity import _event_sort_ts
            at_ts = _event_sort_ts(la.get('at'))
        except Exception:
            at_ts = 0.0
        feed.append({
            'submission_id': sub.get('submission_id'),
            'module_name': sub.get('module_name') or sub.get('module'),
            'submitted_by_display': sub.get('submitted_by_display'),
            'workflow_status': sub.get('workflow_status'),
            'activity': la,
            'at_ts': at_ts,
        })
    feed.sort(key=lambda row: row.get('at_ts') or 0.0, reverse=True)
    return feed[:limit]


def _submission_successfully_finished():
    """Terminal success states (inspection: completed; HR: approved; other modules: completed/approved)."""
    return or_(
        and_(_filter_hr(), Submission.workflow_status == 'approved'),
        and_(_filter_inspection(), Submission.workflow_status == 'completed'),
        and_(not_(_filter_hr()), not_(Submission.module_type.in_(INSPECTION_MODULE_TYPES)),
             Submission.workflow_status.in_(['completed', 'approved']))
    )


def _forms_needing_completion_count():
    """Submissions not yet successfully finished (excludes rejected/closed)."""
    terminal_done = _submission_successfully_finished()
    closed = Submission.workflow_status.in_(['rejected', 'closed_by_admin'])
    return Submission.query.filter(not_(or_(terminal_done, closed))).count()


def _count_inspection(global_scope=True, supervisor_id=None):
    q = Submission.query.filter(_filter_inspection())
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    return q.count()


def _count_hr(global_scope=True, supervisor_id=None):
    q = Submission.query.filter(_filter_hr())
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    return q.count()


def _count_completed_success(global_scope=True, supervisor_id=None):
    q = Submission.query.filter(_submission_successfully_finished())
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    return q.count()


def _count_total_for_rate(global_scope=True, supervisor_id=None):
    q = Submission.query
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    return q.count()


def _completion_rate_pct(global_scope=True, supervisor_id=None):
    total = _count_total_for_rate(global_scope, supervisor_id)
    if not total:
        return 0
    done = _count_completed_success(global_scope, supervisor_id)
    return min(100, round(done / total * 100))


def _inspection_my_submission_rows(user_id):
    """Inspection forms this user submitted — shared by hero stats and my-submissions own rows."""
    return Submission.query.filter(
        _filter_inspection(),
        _my_submissions_filter(user_id),
    ).all()


def _inspection_hero_metrics(user):
    """Inspection hero widget: only forms this user submitted (not org-wide or reviewer queue)."""
    rows = _inspection_my_submission_rows(user.id)
    total = len(rows)
    pending = sum(
        1 for s in rows
        if (s.workflow_status or '') not in ('completed', 'closed_by_admin', 'rejected')
    )
    approved = sum(1 for s in rows if (s.workflow_status or '') == 'completed')
    rate = min(100, round(approved / total * 100)) if total else 0
    return {
        'forms_submitted': total,
        'pending': pending,
        'approved': approved,
        'rate': rate,
    }


def _count_inspection_my(user_id):
    return len(_inspection_my_submission_rows(user_id))


def _count_inspection_pending_my(user_id):
    rows = _inspection_my_submission_rows(user_id)
    return sum(
        1 for s in rows
        if (s.workflow_status or '') not in ('completed', 'closed_by_admin', 'rejected')
    )


def _count_inspection_approved_my(user_id):
    rows = _inspection_my_submission_rows(user_id)
    return sum(1 for s in rows if (s.workflow_status or '') == 'completed')


def _inspection_completion_rate_my(user_id):
    rows = _inspection_my_submission_rows(user_id)
    total = len(rows)
    if not total:
        return 0
    approved = sum(1 for s in rows if (s.workflow_status or '') == 'completed')
    return min(100, round(approved / total * 100))


def _count_hr_my(user_id):
    return Submission.query.filter(_filter_hr(), _my_submissions_filter(user_id)).count()


def _count_completed_success_my(user_id):
    return Submission.query.filter(_submission_successfully_finished(), _my_submissions_filter(user_id)).count()


def _completion_rate_pct_my(user_id):
    total = Submission.query.filter(_my_submissions_filter(user_id)).count()
    if not total:
        return 0
    done = Submission.query.filter(_submission_successfully_finished(), _my_submissions_filter(user_id)).count()
    return min(100, round(done / total * 100))


def _employment_tenure_days_user(user):
    """Calendar days with company inclusive of start day; None if not set."""
    from datetime import date as date_cls, datetime as dt_cls
    d = getattr(user, 'employment_start_date', None)
    if d is None:
        return None
    if isinstance(d, dt_cls):
        d = d.date()
    elif not isinstance(d, date_cls):
        return None
    today = date_cls.today()
    if d > today:
        return 1
    return (today - d).days + 1


def _dashboard_stat_href(label):
    """Map dashboard stat label to the most relevant module URL."""
    if not label:
        return '/workflow/submitted-forms'
    L = (label or '').strip().lower()
    if 'inspection' in L:
        return '/inspection/'
    if 'hr form' in L or 'my hr' in L:
        return '/hr/'
    if 'document' in L:
        return '/dochub'
    if 'device' in L:
        return '/admin/devices'
    if 'active user' in L:
        return '/admin/team-management'
    if 'days with injaaz' in L:
        return '/workflow/submitted-forms'
    if 'annual leave' in L or 'sick leave' in L or 'leave left' in L:
        return None  # opened via profile modal on dashboard
    if 'material' in L or 'catalog' in L:
        return '/procurement/'
    if 'project' in L or 'rfp' in L or 'pipeline' in L:
        return '/admin/bd'
    if 'pending' in L and ('sign' in L or 'review' in L):
        return '/workflow/pending-reviews'
    if 'forms to complete' in L:
        return '/workflow/pending-reviews'
    if 'completed' in L or 'completion rate' in L:
        return '/workflow/submitted-forms'
    if 'form' in L:
        return '/workflow/submitted-forms'
    return '/workflow/submitted-forms'


def _metric(label, value, **extra):
    """Hero stat card payload with navigation href."""
    payload = {'label': label, 'value': value, 'href': _dashboard_stat_href(label)}
    payload.update(extra)
    return payload


def _days_with_injaaz_metric(user):
    """Single hero card dict: tenure formatted as '1 year, 15 days'; None if no employment_start_date."""
    from datetime import date as _date_cls, datetime as _dt_cls
    d = getattr(user, 'employment_start_date', None)
    if d is None:
        return None
    if isinstance(d, _dt_cls):
        d = d.date()
    elif not isinstance(d, _date_cls):
        return None
    today = _date_cls.today()
    if d > today:
        return None
    years = today.year - d.year - (1 if (today.month, today.day) < (d.month, d.day) else 0)
    if years > 0:
        anniversary = d.replace(year=d.year + years)
        remaining = (today - anniversary).days
        if remaining == 0:
            value = f'{years} {"year" if years == 1 else "years"}'
        else:
            value = f'{years} {"year" if years == 1 else "years"}, {remaining} {"day" if remaining == 1 else "days"}'
    else:
        total = (today - d).days + 1
        value = f'{total} {"day" if total == 1 else "days"}'
    try:
        joined_date = f'{d.day} {d.strftime("%b %Y")}'
    except Exception:
        joined_date = str(d)[:10]
    annual = getattr(user, 'annual_leave_days', None)
    other = getattr(user, 'other_leave_days', None)
    return {
        'label': 'Days with Injaaz',
        'value': value,
        'href': _dashboard_stat_href('Days with Injaaz'),
        'joined_date': joined_date,
        'annual_leave_days': annual,
        'other_leave_days': other,
    }


def _inspection_stats_scope(user):
    """(global_scope, supervisor_id) for inspection KPI queries — mirrors main dashboard supervisor scoping."""
    if user.role == 'admin':
        return True, None
    des = (user.designation or '').strip().lower()
    if des == 'supervisor':
        return False, user.id
    return True, None


def _count_inspection_approved(global_scope=True, supervisor_id=None):
    q = Submission.query.filter(
        _filter_inspection(),
        Submission.workflow_status == 'completed',
    )
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    return q.count()


def _inspection_unique_submitters(global_scope=True, supervisor_id=None):
    q = db.session.query(
        func.count(func.distinct(func.coalesce(Submission.user_id, Submission.supervisor_id)))
    ).filter(
        _filter_inspection(),
        or_(Submission.user_id.isnot(None), Submission.supervisor_id.isnot(None)),
    )
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    return int(q.scalar() or 0)


def _inspection_completion_rate_pct(global_scope=True, supervisor_id=None):
    q = Submission.query.filter(_filter_inspection())
    if not global_scope and supervisor_id is not None:
        q = q.filter(Submission.supervisor_id == supervisor_id)
    total = q.count()
    if not total:
        return 0
    done = q.filter(Submission.workflow_status == 'completed').count()
    return min(100, round(done / total * 100))


def _inspection_pending_count_for_user(user):
    if user.role == 'admin':
        return Submission.query.filter(
            _filter_inspection(),
            Submission.workflow_status.notin_(['completed', 'closed_by_admin', 'rejected']),
        ).count()
    pending = get_user_pending_submissions(user) or []
    return sum(1 for s in pending if (s.module_type or '') in INSPECTION_MODULE_TYPES)


def _dashboard_persona(user):
    """Which hero metrics set to show on the main dashboard."""
    des = (user.designation or '').strip().lower()
    if user.role == 'admin' or des == 'general_manager':
        return 'admin_gm'
    if user.role != 'admin' and user.is_bd_inspection_reviewer():
        return 'bd'
    # Procurement & store — before HR so users with both flags get store metrics
    if des in ('procurement', 'store', 'warehouse', 'store_keeper') or getattr(user, 'access_procurement_module', False):
        return 'procurement_store'
    if des in ('supervisor', 'operations_manager'):
        return 'supervisor_ops'
    # HR-focused roles (not supervisors / BD / GM already handled)
    if des in ('hr_manager', 'hr') or (
        getattr(user, 'access_hr', False)
        and des not in ('supervisor', 'operations_manager', 'procurement', 'general_manager', 'business_development', 'store', 'warehouse', 'store_keeper')
    ):
        return 'hr'
    return 'default'


def _hero_metrics_for_user(user, persona):
    """Build four {label, value} stat cards for the dashboard hero widget."""
    insp_all = _count_inspection(global_scope=True)
    hr_all = _count_hr(global_scope=True)
    materials_count = Submission.query.filter(Submission.module_type == 'catalog_material').count()
    forms_to_complete = _forms_needing_completion_count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_hr_review = Submission.query.filter(
        _filter_hr(),
        Submission.workflow_status == 'hr_review'
    ).count()
    docs_count = DocHubDocument.query.count()
    devices_count = Device.query.count()
    total_projects = BDProject.query.count()
    rfps_pipeline = BDProject.query.filter(
        or_(BDProject.stage == 'proposal', BDProject.status == 'proposal')
    ).count()

    sup_id = user.id
    is_supervisor = (user.designation or '').strip().lower() == 'supervisor'
    use_sup_scope = persona == 'supervisor_ops' and is_supervisor

    def insp_val():
        if use_sup_scope:
            return _count_inspection(global_scope=False, supervisor_id=sup_id)
        return insp_all

    def hr_val():
        if use_sup_scope:
            return _count_hr(global_scope=False, supervisor_id=sup_id)
        return hr_all

    def completed_val():
        if use_sup_scope:
            return _count_completed_success(global_scope=False, supervisor_id=sup_id)
        return _count_completed_success(global_scope=True)

    def rate_val():
        if use_sup_scope:
            return _completion_rate_pct(global_scope=False, supervisor_id=sup_id)
        return _completion_rate_pct(global_scope=True)

    if persona == 'admin_gm':
        tenure_card = _days_with_injaaz_metric(user)
        fourth = tenure_card if tenure_card else _metric('Forms to complete', str(forms_to_complete))
        return [
            _metric('Inspection forms submitted', str(insp_all)),
            _metric('HR forms submitted', str(hr_all)),
            _metric('Active users', str(active_users)),
            fourth,
        ]
    if persona == 'procurement_store':
        tenure_card = _days_with_injaaz_metric(user)
        fourth = tenure_card if tenure_card else _metric('Forms to complete', str(forms_to_complete))
        return [
            _metric('Materials in catalog', str(materials_count)),
            _metric('Inspection forms submitted', str(insp_all)),
            _metric('HR forms submitted', str(hr_all)),
            fourth,
        ]
    if persona == 'supervisor_ops':
        tenure_card = _days_with_injaaz_metric(user)
        fourth = tenure_card if tenure_card else _metric('Completion rate', f'{rate_val()}%')
        return [
            _metric('Inspection forms submitted', str(insp_val())),
            _metric('HR forms submitted', str(hr_val())),
            _metric('Completed forms', str(completed_val())),
            fourth,
        ]
    if persona == 'bd':
        tenure_card = _days_with_injaaz_metric(user)
        fourth = tenure_card if tenure_card else _metric('HR forms submitted', str(hr_all))
        return [
            _metric('Total projects', str(total_projects)),
            _metric('RFPs in pipeline', str(rfps_pipeline)),
            _metric('Inspection forms submitted', str(insp_all)),
            fourth,
        ]
    if persona == 'hr':
        tenure_card = _days_with_injaaz_metric(user)
        fourth = tenure_card if tenure_card else _metric('Pending forms to sign', str(pending_hr_review))
        return [
            _metric('HR forms submitted', str(hr_all)),
            _metric('Documents submitted', str(docs_count)),
            _metric('Total devices', str(devices_count)),
            fourth,
        ]
    # default: personal stats (employees / users without org-wide dashboard role)
    uid = user.id
    tenure_card = _days_with_injaaz_metric(user)
    fourth = tenure_card if tenure_card else _metric('My completion rate', f'{_completion_rate_pct_my(uid)}%')
    return [
        _metric('My inspection forms', str(_count_inspection_my(uid))),
        _metric('My HR forms', str(_count_hr_my(uid))),
        _metric('My forms completed', str(_count_completed_success_my(uid))),
        fourth,
    ]


@workflow_bp.route('/dashboard-stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """Role-aware stats for the dashboard hero widget."""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        persona = _dashboard_persona(user)
        hero_metrics = _hero_metrics_for_user(user, persona)

        # Pending count (same logic as pending submissions) — legacy / other UIs
        if user.role == 'admin':
            pending_count = Submission.query.filter(
                Submission.workflow_status.notin_(['completed', 'closed_by_admin', 'rejected'])
            ).count()
        else:
            pending_subs = get_user_pending_submissions(user)
            pending_count = len(pending_subs) if pending_subs else 0

        if user.designation == 'supervisor':
            forms_submitted = Submission.query.filter(
                Submission.supervisor_id == user.id
            ).count()
        elif persona == 'default':
            forms_submitted = Submission.query.filter(_my_submissions_filter(user.id)).count()
        else:
            forms_submitted = Submission.query.count()

        active_users = User.query.filter_by(is_active=True).count() if user.role == 'admin' else 0

        if persona == 'default':
            total_submissions = Submission.query.filter(_my_submissions_filter(user.id)).count()
            completed_count = Submission.query.filter(
                _submission_successfully_finished(),
                _my_submissions_filter(user.id),
            ).count()
        else:
            total_submissions = Submission.query.count()
            completed_count = Submission.query.filter(_submission_successfully_finished()).count()
        completion_rate = round((completed_count / total_submissions * 100) if total_submissions else 0)

        start_date = getattr(user, 'employment_start_date', None)
        start_date_str = None
        if start_date is not None:
            try:
                from datetime import datetime as _dt_cls2
                if isinstance(start_date, _dt_cls2):
                    start_date = start_date.date()
                start_date_str = f'{start_date.day} {start_date.strftime("%b %Y")}'
            except Exception:
                start_date_str = str(start_date)[:10]

        return success_response({
            'dashboard_role': persona,
            'hero_metrics': hero_metrics,
            'forms_submitted': forms_submitted,
            'pending_review': pending_count,
            'active_users': active_users,
            'completion_rate': min(100, completion_rate),
            'employment_start_date': start_date_str,
        })
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard stats: {str(e)}", exc_info=True)
        return error_response('Failed to get dashboard stats', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/inspection-dashboard-stats', methods=['GET'])
@jwt_required()
def get_inspection_dashboard_stats():
    """HVAC/Civil/Cleaning-only metrics for the Inspection module hero widget."""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        metrics = _inspection_hero_metrics(user)
        hero_metrics = [
            {'label': 'Forms submitted', 'value': str(metrics['forms_submitted'])},
            {'label': 'Pending inspections', 'value': str(metrics['pending'])},
            {'label': 'Approved inspections', 'value': str(metrics['approved'])},
            {'label': 'Completion rate', 'value': f"{metrics['rate']}%"},
        ]
        return success_response({'hero_metrics': hero_metrics})
    except Exception as e:
        current_app.logger.error(f"Error getting inspection dashboard stats: {str(e)}", exc_info=True)
        return error_response(
            'Failed to get inspection dashboard stats', status_code=500, error_code='DATABASE_ERROR'
        )


def _signature_url_from_field(form_data, key, alt_key=None):
    """Resolve a signature field to a short URL string for history list (not full base64)."""
    if not isinstance(form_data, dict):
        return None
    sig = form_data.get(key) or (form_data.get(alt_key) if alt_key else None)
    if not sig:
        return None
    if isinstance(sig, dict) and sig.get('url'):
        return sig.get('url')
    if isinstance(sig, str) and (sig.startswith('http') or sig.startswith('/') or sig.startswith('data:')):
        return sig[:500] if sig.startswith('data:') else sig  # cap huge data URLs in list payload
    return None


def _parse_form_data_dict(raw):
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            import json
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _admin_reviewers_for_history(submission):
    """Reviewer summary for admin review history (no verbose logging)."""
    form_data = _parse_form_data_dict(submission.form_data)
    reviewers = []

    om_has_approved = bool(submission.operations_manager_approved_at or submission.operations_manager_id)
    om_comments = submission.operations_manager_comments
    om_sig_url = _signature_url_from_field(form_data, 'operations_manager_signature', 'opMan_signature')
    if om_has_approved or om_comments or om_sig_url:
        reviewers.append({
            'role': 'Operations Manager',
            'comments': om_comments,
            'signature_url': om_sig_url,
            'approved_at': submission.operations_manager_approved_at.isoformat() if submission.operations_manager_approved_at else None
        })

    bd_has_approved = bool(submission.business_dev_approved_at or submission.business_dev_id)
    bd_comments = submission.business_dev_comments
    bd_sig_url = _signature_url_from_field(form_data, 'business_dev_signature')
    if bd_has_approved or bd_comments or bd_sig_url:
        reviewers.append({
            'role': 'Business Development',
            'comments': bd_comments,
            'signature_url': bd_sig_url,
            'approved_at': submission.business_dev_approved_at.isoformat() if submission.business_dev_approved_at else None
        })

    po_has_approved = bool(submission.procurement_approved_at or submission.procurement_id)
    po_comments = submission.procurement_comments
    po_sig_url = _signature_url_from_field(form_data, 'procurement_signature')
    if po_has_approved or po_comments or po_sig_url:
        reviewers.append({
            'role': 'Procurement',
            'comments': po_comments,
            'signature_url': po_sig_url,
            'approved_at': submission.procurement_approved_at.isoformat() if submission.procurement_approved_at else None
        })

    gm_has_approved = bool(submission.general_manager_approved_at or submission.general_manager_id)
    gm_comments = submission.general_manager_comments
    gm_sig_url = _signature_url_from_field(form_data, 'general_manager_signature')
    if gm_has_approved or gm_comments or gm_sig_url:
        reviewers.append({
            'role': 'General Manager',
            'comments': gm_comments,
            'signature_url': gm_sig_url,
            'approved_at': submission.general_manager_approved_at.isoformat() if submission.general_manager_approved_at else None
        })

    return reviewers


@workflow_bp.route('/submissions/history', methods=['GET'])
@jwt_required()
def get_history_submissions():
    """Get all relevant submissions for user (reviewed and pending). Optimized: no form_data blob, no N+1 jobs."""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)

        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        # Eager-load submitter; do not load jobs relationship (avoids N+1 per row)
        list_opts = (
            joinedload(Submission.user),
            noload(Submission.jobs),
        )

        # Review history is inspection-only for all roles.
        if user.role == 'admin':
            q = Submission.query.options(*list_opts).filter(_filter_inspection()).order_by(Submission.created_at.desc())
        elif not hasattr(user, 'designation') or not user.designation:
            return error_response('No designation assigned', status_code=403, error_code='NO_DESIGNATION')
        else:
            designation = user.designation
            base_query = Submission.query.options(*list_opts).filter(_filter_inspection())

            if designation == 'supervisor':
                q = base_query.filter(
                    Submission.supervisor_id == user.id
                ).order_by(Submission.created_at.desc())
            elif designation == 'operations_manager':
                q = base_query.filter(
                    Submission.operations_manager_id == user.id
                ).order_by(Submission.created_at.desc())
            elif user.is_bd_inspection_reviewer():
                q = base_query.filter(
                    Submission.business_dev_id == user.id
                ).order_by(Submission.created_at.desc())
            elif designation == 'procurement':
                q = base_query.filter(
                    Submission.procurement_id == user.id
                ).order_by(Submission.created_at.desc())
            elif designation == 'general_manager':
                q = base_query.filter(
                    or_(
                        Submission.workflow_status == 'general_manager_review',
                        Submission.workflow_status == 'general_manager_approved',
                        Submission.workflow_status == 'completed',
                        Submission.general_manager_id == user.id
                    )
                ).order_by(Submission.created_at.desc())
            else:
                q = None

        if user.role == 'admin' or (user.designation and user.designation != ''):
            submissions = q.all() if q is not None else []
        else:
            submissions = []

        result = []
        for submission in submissions:
            sub_user = getattr(submission, 'user', None) or (db.session.get(User, submission.user_id) if submission.user_id else None)
            # List view: omit form_data (often MB of base64) and skip Job queries
            sub_dict = submission.to_dict(include_form_data=False, include_latest_job=False)
            sub_dict['user'] = sub_user.to_dict() if sub_user else None

            if user.role == 'admin':
                sub_dict['reviewers'] = _admin_reviewers_for_history(submission)

            result.append(sub_dict)

        return success_response({
            'submissions': result,
            'count': len(result)
        })
    except Exception as e:
        current_app.logger.error(f"Error getting history submissions: {str(e)}", exc_info=True)
        return error_response('Failed to get submission history', status_code=500, error_code='DATABASE_ERROR')


def _attach_latest_job_ids(serialized, submission_rows):
    """Batch-load latest completed report job_id for PDF/Excel download links."""
    if not serialized or not submission_rows:
        return
    sub_ids = [s.id for s in submission_rows if getattr(s, 'id', None)]
    if not sub_ids:
        return
    job_rows = (
        Job.query.filter(Job.submission_id.in_(sub_ids), Job.status == 'completed')
        .order_by(Job.submission_id, Job.completed_at.desc().nullslast(), Job.id.desc())
        .with_entities(Job.submission_id, Job.job_id)
        .all()
    )
    latest = {}
    for sid, jid in job_rows:
        if sid not in latest:
            latest[sid] = jid
    for item, sub in zip(serialized, submission_rows):
        item['latest_job_id'] = latest.get(sub.id)


@workflow_bp.route('/submissions/my-trail', methods=['GET'])
@jwt_required()
def get_my_trail():
    """
    Full live trail for the current user: every submission that has touched them,
    split into 'pending' (needs their action) and 'reviewed' (already actioned).
    Covers both inspection and HR forms.
    """
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        list_opts = (joinedload(Submission.user), noload(Submission.jobs))
        designation = (getattr(user, 'designation', None) or '').strip().lower()
        is_admin = (getattr(user, 'role', None) or '').strip().lower() == 'admin'

        # ── helpers ───────────────────────────────────────────────────────────
        def _serial(submission):
            sub_user = getattr(submission, 'user', None) or (
                db.session.get(User, submission.user_id) if submission.user_id else None
            )
            d = submission.to_dict(include_form_data=False, include_latest_job=False)
            d['user'] = sub_user.to_dict() if sub_user else None
            return d

        # ── pending (awaiting this user's action) ────────────────────────────
        # Inspection pending — reuse existing designation logic
        insp_pending_rows = get_user_pending_submissions(user) if not is_admin else (
            Submission.query.options(*list_opts)
            .filter(_filter_inspection(),
                    Submission.workflow_status.notin_(['completed', 'closed_by_admin', 'rejected']))
            .order_by(Submission.created_at.desc()).all()
        )

        # HR pending — by designation/role
        SubmitterAlias = aliased(User)
        hr_pending_rows = []

        if is_admin:
            hr_pending_rows = (
                Submission.query.options(*list_opts)
                .filter(_filter_hr(),
                        Submission.workflow_status.notin_(['approved', 'completed', 'closed_by_admin', 'rejected']))
                .order_by(Submission.created_at.desc()).all()
            )
        elif designation == 'general_manager':
            # GM-role submissions (legacy gm_review + management-chain GM step)
            _gm_rows = (
                Submission.query.options(*list_opts)
                .filter(_filter_hr(),
                        Submission.workflow_status.in_(['gm_review', WF_MGMT_GM]))
                .order_by(Submission.created_at.desc()).all()
            )
            # GM may also be the Reporting Manager for some employees
            _rm_rows = (
                Submission.query.options(*list_opts)
                .join(SubmitterAlias, Submission.user_id == SubmitterAlias.id)
                .filter(_filter_hr(),
                        Submission.workflow_status == WF_MGMT_RM,
                        SubmitterAlias.reporting_manager_id == user.id)
                .order_by(Submission.created_at.desc()).all()
            )
            # Deduplicate while preserving order (GM rows first)
            _seen_ids: set = set()
            hr_pending_rows = []
            for _s in _gm_rows + _rm_rows:
                if _s.id not in _seen_ids:
                    _seen_ids.add(_s.id)
                    hr_pending_rows.append(_s)
        elif designation in ('hr_manager',) or getattr(user, 'access_hr', False):
            hr_pending_rows = (
                Submission.query.options(*list_opts)
                .filter(_filter_hr(),
                        Submission.workflow_status.in_(['hr_review', WF_MGMT_HR]))
                .order_by(Submission.created_at.desc()).all()
            )
        else:
            # Reporting manager: submitter's reporting_manager_id == user.id
            hr_pending_rows = (
                Submission.query.options(*list_opts)
                .join(SubmitterAlias, Submission.user_id == SubmitterAlias.id)
                .filter(_filter_hr(),
                        Submission.workflow_status == WF_MGMT_RM,
                        SubmitterAlias.reporting_manager_id == user.id)
                .order_by(Submission.created_at.desc()).all()
            )

        pending_ids = {s.id for s in insp_pending_rows + hr_pending_rows}
        pending_rows = insp_pending_rows + hr_pending_rows
        pending = [_serial(s) for s in pending_rows]
        _attach_latest_job_ids(pending, pending_rows)

        # ── reviewed (already actioned by this user) ─────────────────────────
        insp_reviewed_rows = _query_inspection_reviewed_for_user(user, list_opts)
        hr_reviewed_rows = []

        # HR reviewed
        if is_admin:
            hr_reviewed_rows = (
                Submission.query.options(*list_opts)
                .filter(_filter_hr(),
                        Submission.workflow_status.in_(['approved', 'completed', 'closed_by_admin', 'rejected']))
                .order_by(Submission.updated_at.desc()).limit(200).all()
            )
        elif designation == 'general_manager':
            # Only HR submissions this GM actually approved or rejected (not every org-wide HR row)
            hr_reviewed_rows = (
                Submission.query.options(*list_opts)
                .filter(
                    _filter_hr(),
                    or_(
                        and_(
                            Submission.general_manager_id == user.id,
                            Submission.general_manager_approved_at.isnot(None),
                        ),
                        and_(
                            Submission.workflow_status == 'rejected',
                            Submission.rejected_by_id == user.id,
                        ),
                    ),
                )
                .order_by(Submission.updated_at.desc())
                .all()
            )
        elif designation in ('hr_manager',) or getattr(user, 'access_hr', False):
            hr_reviewed_rows = (
                Submission.query.options(*list_opts)
                .filter(_filter_hr(),
                        Submission.workflow_status.in_(['approved', 'completed', 'rejected']))
                .order_by(Submission.updated_at.desc()).all()
            )
        else:
            # RM: forms submitted by their direct reports, past the RM stage
            hr_reviewed_rows = (
                Submission.query.options(*list_opts)
                .join(SubmitterAlias, Submission.user_id == SubmitterAlias.id)
                .filter(_filter_hr(),
                        SubmitterAlias.reporting_manager_id == user.id,
                        Submission.workflow_status.notin_(
                            [WF_MGMT_RM, 'submitted', 'draft']))
                .order_by(Submission.updated_at.desc()).all()
            )

        # Deduplicate — exclude anything already listed as pending
        reviewed_rows = [s for s in insp_reviewed_rows + hr_reviewed_rows if s.id not in pending_ids]
        reviewed = [_serial(s) for s in reviewed_rows]
        _attach_latest_job_ids(reviewed, reviewed_rows)

        return success_response({
            'pending':  pending,
            'reviewed': reviewed,
            'pending_count':  len(pending),
            'reviewed_count': len(reviewed),
        })

    except Exception as e:
        current_app.logger.error(f"Error building my-trail: {str(e)}", exc_info=True)
        return error_response('Failed to build trail', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/my-submissions', methods=['GET'])
@jwt_required()
def get_my_submissions():
    """Get submitted forms in one module: HR and/or inspection based on user access."""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        # Get filter parameter (all, submitted, draft)
        status_filter = request.args.get('status', 'all')
        scope = str(request.args.get('scope', 'all') or 'all').strip().lower()
        if scope not in ('all', 'hr', 'inspection'):
            scope = 'all'

        try:
            from module_hr.routes import get_form_type_display as _hr_module_title
        except Exception:
            def _hr_module_title(mt):
                if not mt:
                    return 'HR Form'
                s = str(mt).replace('hr_', '').replace('_', ' ')
                return (s.title() + ' (HR)') if s else 'HR Form'

        base_query = Submission.query.options(joinedload(Submission.user))

        def _apply_status(q):
            if q is None:
                return None
            if status_filter == 'draft':
                return q.filter_by(status='draft')
            if status_filter == 'submitted':
                return q.filter(Submission.status != 'draft')
            return q

        submissions = []
        include_hr = scope in ('all', 'hr')
        include_inspection = scope in ('all', 'inspection')

        org_wide = _user_sees_org_wide_submissions(user, scope)

        if include_hr:
            hr_q = _apply_status(_hr_submissions_list_query_for_user(base_query, user, scope))
            if hr_q is not None:
                submissions.extend(hr_q.all())

        if include_inspection:
            ins_own_q = _apply_status(_inspection_submissions_list_query_for_user(base_query, user, scope))
            if ins_own_q is not None:
                submissions.extend(ins_own_q.all())

        dedup = {}
        for s in submissions:
            dedup[s.submission_id] = s
        submissions = sorted(
            dedup.values(),
            key=lambda s: s.updated_at or s.created_at or datetime.min,
            reverse=True,
        )
        if org_wide:
            list_scope = 'all'
        else:
            list_scope = 'mixed' if (include_hr and include_inspection) else ('hr' if include_hr else 'inspection')

        inspections_map = {
            'hvac': 'Inspection',
            'inspection': 'Inspection',
            'hvac_mep': 'Inspection',
            'civil': 'Inspection',
            'cleaning': 'Inspection',
            'qhsi_inspection': 'QHSA Site Inspection',
            'qhsi_staff_compliance': 'Staff Compliance (QHSI)',
        }

        submissions_list = []
        for submission in submissions:
            sub_dict = submission.to_dict()
            mt = submission.module_type
            sub_dict['module_name'] = (
                inspections_map.get(mt)
                or (_hr_module_title(mt) if (mt or '').startswith('hr_') else (mt or 'Form'))
            )
            u_rel = getattr(submission, 'user', None)
            sub_dict['submitted_by_display'] = (u_rel.full_name or u_rel.username) if u_rel else None
            sub_dict['submitted_by_username'] = u_rel.username if u_rel else None
            
            # Extract reviewer comments and signatures from form_data for display
            form_data = submission.form_data if submission.form_data else {}
            if isinstance(form_data, str):
                try:
                    import json
                    form_data = json.loads(form_data)
                except:
                    form_data = {}
            
            # Add reviewer information
            reviewers = []
            
            # Operations Manager
            # Only show if OM has actually approved (has approved_at) or has signature/comments
            # STRICT: Only use model field - never fallback to form_data to avoid mixing supervisor comments
            om_has_approved = bool(submission.operations_manager_approved_at or submission.operations_manager_id)
            # Only use the database field - do NOT fallback to form_data to prevent supervisor comments from appearing
            om_comments = submission.operations_manager_comments if submission.operations_manager_comments else None
            
            om_sig = form_data.get('operations_manager_signature') or form_data.get('opMan_signature') if isinstance(form_data, dict) else None
            om_sig_url = None
            if om_sig:
                om_sig_url = om_sig.get('url') if isinstance(om_sig, dict) and om_sig.get('url') else (om_sig if isinstance(om_sig, str) and (om_sig.startswith('http') or om_sig.startswith('/') or om_sig.startswith('data:')) else None)
            
            if om_has_approved or om_comments or om_sig_url:
                reviewers.append({
                    'role': 'Operations Manager',
                    'comments': om_comments,  # Use extracted comments (model field prioritized)
                    'signature_url': om_sig_url,
                    'approved_at': submission.operations_manager_approved_at.isoformat() if submission.operations_manager_approved_at else None
                })
            
            # Business Development
            # Prioritize model field over form_data
            bd_has_approved = bool(submission.business_dev_approved_at or submission.business_dev_id)
            bd_comments = submission.business_dev_comments
            if not bd_comments and isinstance(form_data, dict):
                form_bd_comments = form_data.get('business_dev_comments')
                # Verify it's not supervisor comments
                supervisor_comments = form_data.get('supervisor_comments', '')
                if form_bd_comments and form_bd_comments != supervisor_comments:
                    bd_comments = form_bd_comments
            
            bd_sig = form_data.get('business_dev_signature') if isinstance(form_data, dict) else None
            bd_sig_url = None
            if bd_sig:
                bd_sig_url = bd_sig.get('url') if isinstance(bd_sig, dict) and bd_sig.get('url') else (bd_sig if isinstance(bd_sig, str) and (bd_sig.startswith('http') or bd_sig.startswith('/') or bd_sig.startswith('data:')) else None)
            
            if bd_has_approved or bd_comments or bd_sig_url:
                reviewers.append({
                    'role': 'Business Development',
                    'comments': bd_comments,
                    'signature_url': bd_sig_url,
                    'approved_at': submission.business_dev_approved_at.isoformat() if submission.business_dev_approved_at else None
                })
            
            # Procurement
            # Prioritize model field over form_data
            po_has_approved = bool(submission.procurement_approved_at or submission.procurement_id)
            po_comments = submission.procurement_comments
            if not po_comments and isinstance(form_data, dict):
                form_po_comments = form_data.get('procurement_comments')
                # Verify it's not supervisor comments
                supervisor_comments = form_data.get('supervisor_comments', '')
                if form_po_comments and form_po_comments != supervisor_comments:
                    po_comments = form_po_comments
            
            po_sig = form_data.get('procurement_signature') if isinstance(form_data, dict) else None
            po_sig_url = None
            if po_sig:
                po_sig_url = po_sig.get('url') if isinstance(po_sig, dict) and po_sig.get('url') else (po_sig if isinstance(po_sig, str) and (po_sig.startswith('http') or po_sig.startswith('/') or po_sig.startswith('data:')) else None)
            
            if po_has_approved or po_comments or po_sig_url:
                reviewers.append({
                    'role': 'Procurement',
                    'comments': po_comments,
                    'signature_url': po_sig_url,
                    'approved_at': submission.procurement_approved_at.isoformat() if submission.procurement_approved_at else None
                })
            
            # General Manager
            # Prioritize model field over form_data
            gm_has_approved = bool(submission.general_manager_approved_at or submission.general_manager_id)
            gm_comments = submission.general_manager_comments
            if not gm_comments and isinstance(form_data, dict):
                form_gm_comments = form_data.get('general_manager_comments')
                # Verify it's not supervisor comments
                supervisor_comments = form_data.get('supervisor_comments', '')
                if form_gm_comments and form_gm_comments != supervisor_comments:
                    gm_comments = form_gm_comments
            
            gm_sig = form_data.get('general_manager_signature') if isinstance(form_data, dict) else None
            gm_sig_url = None
            if gm_sig:
                gm_sig_url = gm_sig.get('url') if isinstance(gm_sig, dict) and gm_sig.get('url') else (gm_sig if isinstance(gm_sig, str) and (gm_sig.startswith('http') or gm_sig.startswith('/') or gm_sig.startswith('data:')) else None)
            
            if gm_has_approved or gm_comments or gm_sig_url:
                reviewers.append({
                    'role': 'General Manager',
                    'comments': gm_comments,
                    'signature_url': gm_sig_url,
                    'approved_at': submission.general_manager_approved_at.isoformat() if submission.general_manager_approved_at else None
                })
            
            sub_dict['reviewers'] = reviewers
            
            # Extract photos and signatures from form_data for display
            photos = []
            supervisor_signature = None
            
            if isinstance(form_data, dict):
                # Extract photos - handle different module formats
                if submission.module_type in ['civil', 'cleaning']:
                    # Civil and Cleaning: photos might be in work_items or directly in form_data
                    if 'work_items' in form_data and isinstance(form_data['work_items'], list):
                        for item in form_data['work_items']:
                            if isinstance(item, dict) and 'photos' in item:
                                item_photos = item.get('photos', [])
                                if isinstance(item_photos, list):
                                    photos.extend(item_photos)
                    elif 'photo_urls' in form_data and isinstance(form_data['photo_urls'], list):
                        photos = form_data['photo_urls']
                    elif 'photos' in form_data and isinstance(form_data['photos'], list):
                        photos = form_data['photos']
                elif submission.module_type in ['hvac', 'hvac_mep']:
                    # HVAC: photos are in items array
                    if 'items' in form_data and isinstance(form_data['items'], list):
                        for item in form_data['items']:
                            if isinstance(item, dict) and 'photos' in item:
                                item_photos = item.get('photos', [])
                                if isinstance(item_photos, list):
                                    photos.extend(item_photos)
                
                # Extract supervisor signature
                supervisor_sig = form_data.get('supervisor_signature') or form_data.get('supervisorSignature')
                if supervisor_sig:
                    if isinstance(supervisor_sig, dict):
                        supervisor_signature = supervisor_sig.get('url') or supervisor_sig.get('path')
                    elif isinstance(supervisor_sig, str) and (supervisor_sig.startswith('http') or supervisor_sig.startswith('/') or supervisor_sig.startswith('data:')):
                        supervisor_signature = supervisor_sig
            
            # Normalize photo URLs - extract URLs from photo objects
            photo_urls = []
            for photo in photos[:10]:  # Limit to first 10 for preview
                if isinstance(photo, dict):
                    url = photo.get('url') or photo.get('path')
                    if url:
                        photo_urls.append(url)
                elif isinstance(photo, str) and (photo.startswith('http') or photo.startswith('/') or photo.startswith('data:')):
                    photo_urls.append(photo)
            
            sub_dict['photos'] = photo_urls
            sub_dict['photo_count'] = len(photos)  # Total count
            sub_dict['supervisor_signature'] = supervisor_signature

            if (mt or '').startswith('hr_'):
                sub_dict['can_withdraw_hr'] = bool(
                    submission.user_id == user.id
                    and submission.status != 'draft'
                    and not _hr_submission_record_finalized_locked(submission)
                )
                sub_dict['latest_activity'] = _hr_latest_activity_from_form_data(
                    form_data, submission.workflow_status, submission.status
                )
            else:
                sub_dict['can_withdraw_hr'] = False
                sub_dict['latest_activity'] = None

            submissions_list.append(sub_dict)

        live_activity_feed = _build_live_activity_feed(submissions_list) if org_wide else []
        
        return success_response({
            'submissions': submissions_list,
            'count': len(submissions_list),
            'list_scope': list_scope,
            'org_wide': org_wide,
            'live_activity_feed': live_activity_feed,
            'poll_interval_seconds': 15 if org_wide else 30,
            'visible_modules': {
                'hr': bool(include_hr),
                'inspection': bool(include_inspection),
            },
            'requested_scope': scope,
        })
    except Exception as e:
        current_app.logger.error(f"Error getting my submissions: {str(e)}", exc_info=True)
        return error_response('Failed to get submissions', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>', methods=['GET'])
@jwt_required()
def get_submission_detail(submission_id):
    """Get detailed submission information"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        # Use eager loading to fetch all related users in one query.
        # Note: the procurement relationship backref on Submission is 'procurement_user'
        # (not 'procurement') — see User.procurement_submissions backref in models.py.
        submission = Submission.query.options(
            joinedload(Submission.user),
            joinedload(Submission.supervisor),
            joinedload(Submission.operations_manager),
            joinedload(Submission.business_dev),
            joinedload(Submission.procurement_user),
            joinedload(Submission.general_manager)
        ).filter_by(submission_id=submission_id).first()
        
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Check access permissions (include submitter via user_id for HR forms and others)
        has_access = (
            str(getattr(user, "role", None) or "").strip().lower() == "admin"
            or submission.supervisor_id == user.id
            or submission.user_id == user.id
            or (user.designation and user.designation in VALID_DESIGNATIONS)
            or (_is_hr_module_submission(submission) and _hr_anytime_line_editor(user, submission))
        )
        if not has_access and _is_hr_module_submission(submission):
            from module_hr.hr_management_chain import user_is_mgmt_chain_participant

            fd = _submission_form_data_dict(submission)
            if user_is_mgmt_chain_participant(user, fd):
                has_access = True
        
        if not has_access:
            return error_response('Access denied', status_code=403, error_code='UNAUTHORIZED')
        
        sub_dict = submission.to_dict()
        sub_dict['can_edit'] = can_edit_submission(user, submission)
        if _is_hr_module_submission(submission):
            sub_dict.update(_hr_leave_edit_api_flags(user, submission))
        
        # Add user details (using eager-loaded relationships)
        sub_dict['user'] = submission.user.to_dict() if submission.user else None
        sub_dict['supervisor'] = submission.supervisor.to_dict() if submission.supervisor else None
        sub_dict['operations_manager'] = submission.operations_manager.to_dict() if submission.operations_manager else None
        sub_dict['business_dev'] = submission.business_dev.to_dict() if submission.business_dev else None
        sub_dict['procurement'] = submission.procurement_user.to_dict() if submission.procurement_user else None
        sub_dict['general_manager'] = submission.general_manager.to_dict() if submission.general_manager else None
        
        return success_response(sub_dict)
    except Exception as e:
        current_app.logger.error(f"Error getting submission detail: {str(e)}", exc_info=True)
        return error_response('Failed to get submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/save-draft', methods=['POST'])
@jwt_required()
def save_draft():
    """Save a form as draft (for all users)"""
    try:
        import uuid
        from datetime import datetime
        
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        data = request.get_json() or {}
        
        # Get or create submission_id
        submission_id = data.get('submission_id') or data.get('draft_id')
        module_type = data.get('module_type', 'hvac_mep')
        form_data = data.get('form_data', {})
        site_name = data.get('site_name') or form_data.get('site_name', 'Draft')
        visit_date_str = data.get('visit_date') or form_data.get('visit_date')
        
        # Parse visit date
        visit_date = None
        if visit_date_str:
            try:
                visit_date = datetime.strptime(visit_date_str, '%Y-%m-%d').date()
            except:
                pass
        
        # Check if we're updating an existing draft
        existing_submission = None
        if submission_id:
            existing_submission = Submission.query.filter_by(submission_id=submission_id).first()
        
        if existing_submission:
            # Update existing draft
            if existing_submission.status != 'draft':
                return error_response('Cannot update a submitted form as draft. Use edit instead.', 
                                    status_code=400, error_code='INVALID_STATUS')
            
            # Verify ownership (HR drafts may use user_id only; inspector drafts often set supervisor_id)
            is_admin = str(getattr(user, "role", None) or "").strip().lower() == "admin"
            if (
                not is_admin
                and getattr(existing_submission, "user_id", None) != user.id
                and getattr(existing_submission, "supervisor_id", None) != user.id
            ):
                return error_response(
                    "You can only update your own drafts",
                    status_code=403,
                    error_code="FORBIDDEN",
                )
            
            existing_submission.form_data = form_data
            existing_submission.site_name = site_name
            existing_submission.visit_date = visit_date
            existing_submission.updated_at = utc_now_naive()
            
            db.session.commit()
            
            current_app.logger.info(f"Updated draft {submission_id} for user {user_id}")
            
            return success_response({
                'message': 'Draft updated successfully',
                'submission_id': existing_submission.submission_id,
                'status': 'draft'
            })
        else:
            # Create new draft
            new_submission_id = f"draft_{uuid.uuid4().hex[:12]}"
            
            new_submission = Submission(
                submission_id=new_submission_id,
                user_id=user.id,
                supervisor_id=user.id,  # Even for reviewers, track who created the draft
                module_type=module_type,
                site_name=site_name,
                visit_date=visit_date,
                status='draft',
                workflow_status='draft',
                form_data=form_data,
                created_at=utc_now_naive(),
                updated_at=utc_now_naive()
            )
            
            db.session.add(new_submission)
            db.session.commit()
            
            current_app.logger.info(f"Created new draft {new_submission_id} for user {user_id}")
            
            return success_response({
                'message': 'Draft saved successfully',
                'submission_id': new_submission_id,
                'status': 'draft'
            })
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving draft: {str(e)}", exc_info=True)
        return error_response('Failed to save draft', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/draft/<submission_id>', methods=['DELETE'])
@jwt_required()
def delete_draft(submission_id):
    """Delete a draft submission"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        
        if not submission:
            return error_response('Draft not found', status_code=404, error_code='NOT_FOUND')
        
        if submission.status != 'draft':
            return error_response('Can only delete drafts', status_code=400, error_code='INVALID_STATUS')
        
        is_admin = str(getattr(user, "role", None) or "").strip().lower() == "admin"
        if (
            not is_admin
            and getattr(submission, "user_id", None) != user.id
            and getattr(submission, "supervisor_id", None) != user.id
        ):
            return error_response(
                "You can only delete your own drafts",
                status_code=403,
                error_code="FORBIDDEN",
            )
        
        db.session.delete(submission)
        db.session.commit()
        
        current_app.logger.info(f"Deleted draft {submission_id} for user {user_id}")
        
        return success_response({'message': 'Draft deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting draft: {str(e)}", exc_info=True)
        return error_response('Failed to delete draft', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/approve-supervisor', methods=['POST'])
@jwt_required()
def approve_supervisor_resubmission(submission_id):
    """Supervisor resubmits/approves their own submission (allows editing and regeneration)"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if user.designation != 'supervisor' and user.role != 'admin':
            return error_response('Only supervisors can resubmit their own forms', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Verify this is the supervisor's own submission
        is_own_submission = (
            (hasattr(submission, 'supervisor_id') and submission.supervisor_id == user.id) or
            (submission.user_id == user.id)
        )
        
        if not is_own_submission and user.role != 'admin':
            return error_response('You can only resubmit your own submissions', 
                                status_code=403, error_code='UNAUTHORIZED')
        
        # Allow sign-off / resubmission at the supervisor or initial stages, or
        # while still at operations_manager_review (so long as OM hasn't approved).
        if submission.workflow_status not in [
            'submitted', 'rejected', 'supervisor_review', 'supervisor_notified', None
        ] and not (
            submission.workflow_status == 'operations_manager_review' and not submission.operations_manager_approved_at
        ):
            return error_response('Submission cannot be resubmitted at this stage', 
                                status_code=400, error_code='INVALID_STATUS')
        
        # Extract data
        comments = data.get('comments', '') or data.get('supervisor_comments', '')
        signature = data.get('signature', '') or data.get('supervisor_signature', '')
        verified = data.get('verified', False)
        form_data_updates = data.get('form_data', {})
        
        # Update form_data - use a copy to avoid mutating ORM-held dict (SQLAlchemy JSON)
        _raw = submission.form_data if submission.form_data else {}
        if isinstance(_raw, str):
            try:
                import json
                form_data = json.loads(_raw)
            except Exception:
                form_data = {}
        else:
            form_data = copy.deepcopy(_raw) if isinstance(_raw, dict) else {}
        
        # Preserve existing reviewer data (OM, BD, PO, GM) and work_items/items before updating
        existing_om_comments = form_data.get('operations_manager_comments')
        existing_om_signature = form_data.get('operations_manager_signature') or form_data.get('opMan_signature')
        existing_bd_comments = form_data.get('business_dev_comments')
        existing_bd_signature = form_data.get('business_dev_signature')
        existing_procurement_comments = form_data.get('procurement_comments')
        existing_procurement_signature = form_data.get('procurement_signature')
        existing_gm_comments = form_data.get('general_manager_comments')
        existing_gm_signature = form_data.get('general_manager_signature')
        existing_work_items = form_data.get('work_items')
        existing_items = form_data.get('items')
        
        # Update with new form_data
        if form_data_updates:
            form_data.update(form_data_updates)
        
        # Merge work_items / items: keep previously submitted form + updates (old images + new)
        if existing_work_items is not None or form_data.get('work_items'):
            merged_wi = _merge_items_with_photos(
                existing_work_items or [],
                form_data.get('work_items') or [],
                'work_items'
            )
            form_data['work_items'] = merged_wi
            current_app.logger.info(f"✅ Merged work_items for supervisor resubmission: {len(merged_wi)} items")
        if existing_items is not None or form_data.get('items'):
            merged_items = _merge_items_with_photos(
                existing_items or [],
                form_data.get('items') or [],
                'items'
            )
            form_data['items'] = merged_items
            current_app.logger.info(f"✅ Merged items (HVAC) for supervisor resubmission: {len(merged_items)} items")
        
        # Ensure photo_urls → photos for generators
        _ensure_items_photos(form_data)
        
        # Update supervisor data
        _preserve_submitter_comments_before_supervisor_signoff(form_data, submission)
        if comments:
            form_data['supervisor_comments'] = comments
            submission.supervisor_comments = comments
        
        if signature:
            # Legacy: keep submitter signature in tech_signature before supervisor overwrites supervisor_signature
            _preserve_submitter_signature_before_supervisor_signoff(form_data, submission)
            # Process and save supervisor signature
            save_signature_dataurl, get_paths_fn, _ = get_module_functions(submission.module_type)
            GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
            
            sig_filename, sig_path, sig_url = save_signature_dataurl(
                signature, 
                UPLOADS_DIR, 
                prefix="supervisor_sig"
            )
            
            if sig_url:
                form_data['supervisor_signature'] = {
                    'url': sig_url,
                    'path': sig_path,
                    'saved': sig_filename,
                    'is_cloud': sig_url.startswith('http') and 'cloudinary' in sig_url
                }
                current_app.logger.info(f"✅ Saved supervisor signature for resubmission {submission_id}")
        
        if verified:
            form_data['supervisor_verified'] = True
        
        # Restore reviewer data if it was lost
        if existing_om_comments and not form_data.get('operations_manager_comments'):
            form_data['operations_manager_comments'] = existing_om_comments
        if existing_om_signature and not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
            form_data['operations_manager_signature'] = existing_om_signature
        if existing_bd_comments and not form_data.get('business_dev_comments'):
            form_data['business_dev_comments'] = existing_bd_comments
        if existing_bd_signature and not form_data.get('business_dev_signature'):
            form_data['business_dev_signature'] = existing_bd_signature
        if existing_procurement_comments and not form_data.get('procurement_comments'):
            form_data['procurement_comments'] = existing_procurement_comments
        if existing_procurement_signature and not form_data.get('procurement_signature'):
            form_data['procurement_signature'] = existing_procurement_signature
        if existing_gm_comments and not form_data.get('general_manager_comments'):
            form_data['general_manager_comments'] = existing_gm_comments
        if existing_gm_signature and not form_data.get('general_manager_signature'):
            form_data['general_manager_signature'] = existing_gm_signature
        
        submission.form_data = form_data
        submission.supervisor_id = user.id
        submission.supervisor_reviewed_at = utc_now_naive()
        
        # After supervisor sign-off, advance the form to the Operations Manager stage.
        submission.workflow_status = 'operations_manager_review'
        
        submission.updated_at = utc_now_naive()
        flag_modified(submission, 'form_data')
        if is_inspection_submission(submission) and submission.workflow_status in (
            'submitted', 'operations_manager_review'
        ):
            notify_inspection_stage(submission, submission.workflow_status)
        db.session.commit()
        
        # Regenerate PDF and Excel documents with updated data
        job_id = None
        try:
            from common.db_utils import create_job_db
            from app.models import Job
            _, get_paths_fn, process_job_fn = get_module_functions(submission.module_type)
            
            # Delete old jobs to force regeneration
            old_jobs = Job.query.filter_by(submission_id=submission.id).all()
            for old_job in old_jobs:
                db.session.delete(old_job)
            db.session.commit()
            
            # Create new job for regeneration
            new_job = create_job_db(submission)
            job_id = new_job.job_id
            
            GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
            
            if EXECUTOR:
                EXECUTOR.submit(
                    process_job_fn,
                    submission.submission_id,
                    job_id,
                    current_app.config,
                    current_app._get_current_object()
                )
                current_app.logger.info(f"✅ Regeneration job {job_id} queued for supervisor resubmission - submission {submission_id} ({submission.module_type})")
            else:
                current_app.logger.error("ThreadPoolExecutor not available for document regeneration")
        except Exception as regen_err:
            current_app.logger.error(f"Error queuing regeneration job after supervisor resubmission: {regen_err}", exc_info=True)
        
        log_audit(user_id, 'supervisor_resubmitted', 'submission', submission_id, {
            'comments': comments,
            'has_signature': bool(signature),
            'verified': verified
        })

        send_team_notification(submission, user, "Supervisor signed")
        
        return success_response({
            'submission': submission.to_dict(),
            'message': 'Form resubmitted successfully. PDF and Excel reports are being regenerated with your updates.' + (' Documents are being regenerated.' if job_id else ''),
            'job_id': job_id,
            'regenerating': bool(job_id)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in supervisor resubmission: {str(e)}", exc_info=True)
        return error_response('Failed to resubmit submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/approve-ops-manager', methods=['POST'])
@jwt_required()
def approve_operations_manager(submission_id):
    """Operations Manager approves submission"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if user.designation != 'operations_manager' and user.role != 'admin':
            return error_response('Only Operations Manager can approve at this stage', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Allow OM to approve at operations_manager_review stage OR re-approve at bd_procurement_review
        # (OM can edit their review even after form moves to BD/Procurement stage, as long as they haven't started approving)
        if submission.workflow_status not in ['operations_manager_review', 'bd_procurement_review']:
            return error_response('Submission is not at Operations Manager review stage', 
                                status_code=400, error_code='INVALID_STATUS')
        
        # Check if BD or Procurement has already started reviewing - if so, OM can no longer edit
        if submission.workflow_status == 'bd_procurement_review':
            bd_started = submission.business_dev_approved_at is not None
            proc_started = submission.procurement_approved_at is not None
            if bd_started or proc_started:
                return error_response('Cannot modify review after BD/Procurement has started reviewing', 
                                    status_code=400, error_code='ALREADY_APPROVED_BY_NEXT_STAGE')
        
        # Extract data
        comments = data.get('comments', '')
        signature = data.get('signature', '')
        form_data_updates = data.get('form_data', {})
        
        # Log incoming data for debugging
        current_app.logger.info(f"🔍 Operations Manager approval request for submission {submission_id}:")
        current_app.logger.info(f"  - Comments provided: {bool(comments and comments.strip())} (length: {len(comments) if comments else 0})")
        current_app.logger.info(f"  - Signature provided: {bool(signature and signature.strip())} (type: {type(signature).__name__}, length: {len(str(signature)) if signature else 0})")
        if signature and signature.strip():
            current_app.logger.info(f"  - Signature preview: {str(signature)[:50]}...")
        current_app.logger.info(f"  - form_data_updates keys: {list(form_data_updates.keys())[:20] if form_data_updates else 'none'}")
        
        # Log form_data_updates for OM signature debugging
        if form_data_updates:
            if form_data_updates.get('operations_manager_signature'):
                current_app.logger.info(f"✅ Found operations_manager_signature in form_data_updates (type: {type(form_data_updates.get('operations_manager_signature')).__name__})")
            if form_data_updates.get('opMan_signature'):
                current_app.logger.info(f"✅ Found opMan_signature in form_data_updates (type: {type(form_data_updates.get('opMan_signature')).__name__})")
        
        # Check if signature is in form_data_updates (might be sent there instead of top-level)
        if not signature or not signature.strip():
            if form_data_updates.get('opMan_signature'):
                signature = form_data_updates.get('opMan_signature')
                current_app.logger.info(f"✅ Using Operations Manager signature from form_data_updates.opMan_signature")
            elif form_data_updates.get('operations_manager_signature'):
                signature = form_data_updates.get('operations_manager_signature')
                current_app.logger.info(f"✅ Using Operations Manager signature from form_data_updates.operations_manager_signature")
        
        # Update submission model fields
        submission.operations_manager_id = user.id
        submission.operations_manager_comments = comments
        submission.operations_manager_approved_at = utc_now_naive()
        
        # Log what we're saving to model fields
        current_app.logger.info(f"💾 Saving OM data to model fields:")
        current_app.logger.info(f"  - operations_manager_id: {user.id}")
        current_app.logger.info(f"  - operations_manager_comments: {comments[:80] if comments else 'None'}")
        current_app.logger.info(f"  - operations_manager_approved_at: {utc_now_naive()}")
        
        submission.workflow_status = 'operations_manager_approved'
        
        # Update form_data if provided - use a copy to avoid mutating ORM-held dict (SQLAlchemy JSON)
        _raw = submission.form_data if submission.form_data else {}
        if isinstance(_raw, str):
            try:
                import json
                form_data = json.loads(_raw)
            except Exception:
                form_data = {}
        else:
            form_data = copy.deepcopy(_raw) if isinstance(_raw, dict) else {}
        
        # Preserve existing Operations Manager data before updating (in case form_data_updates overwrites it)
        existing_om_comments = form_data.get('operations_manager_comments')
        existing_om_signature = form_data.get('operations_manager_signature') or form_data.get('opMan_signature')
        
        # Check if OM data is in form_data_updates (from payload)
        om_comments_in_payload = form_data_updates.get('operations_manager_comments') if form_data_updates else None
        om_sig_in_payload = form_data_updates.get('operations_manager_signature') or form_data_updates.get('opMan_signature') if form_data_updates else None
        
        if form_data_updates:
            # Merge form_data_updates
            form_data.update(form_data_updates)
            current_app.logger.info(f"✅ Updated form_data with form_data_updates for submission {submission_id}")
            if om_comments_in_payload:
                current_app.logger.info(f"✅ Operations Manager comments found in payload: {len(str(om_comments_in_payload))} chars")
            if om_sig_in_payload:
                current_app.logger.info(f"✅ Operations Manager signature found in payload: {type(om_sig_in_payload).__name__}")
        
        # CRITICAL: Ensure OM data from payload is saved (if OM is submitting)
        # This handles the case where OM data is in form_data_updates but might be lost
        if om_comments_in_payload:
            form_data['operations_manager_comments'] = om_comments_in_payload
            current_app.logger.info(f"✅ Saved Operations Manager comments from payload to form_data")
        elif existing_om_comments:
            form_data['operations_manager_comments'] = existing_om_comments
        
        if om_sig_in_payload:
            form_data['operations_manager_signature'] = om_sig_in_payload
            form_data['opMan_signature'] = om_sig_in_payload
            current_app.logger.info(f"✅ Saved Operations Manager signature from payload to form_data")
        elif existing_om_signature:
            form_data['operations_manager_signature'] = existing_om_signature
            if 'opMan_signature' not in form_data:
                form_data['opMan_signature'] = existing_om_signature
        
        # Always save Operations Manager comments to form_data for next reviewers
        # Use new comments if provided, otherwise preserve existing
        if comments and comments.strip():
            form_data['operations_manager_comments'] = comments
            current_app.logger.info(f"✅ Saved Operations Manager comments to form_data for submission {submission_id}")
        elif existing_om_comments:
            # Preserve existing comments if no new ones provided
            form_data['operations_manager_comments'] = existing_om_comments
            current_app.logger.info(f"✅ Preserved existing Operations Manager comments in form_data")
        
        # Process and upload Operations Manager signature if provided
        if signature and signature.strip() and signature.startswith('data:image'):
            # Signature is a data URL - need to upload it to cloud storage
            try:
                save_sig_fn, get_paths_fn, _ = get_module_functions(submission.module_type)
                GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
                
                fname, fpath, url = save_sig_fn(signature, UPLOADS_DIR, prefix="opman_sig")
                if url:
                    # Save as object format for consistency with other signatures
                    sig_obj = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
                    form_data['operations_manager_signature'] = sig_obj
                    form_data['opMan_signature'] = sig_obj  # Also save with alternate key
                    current_app.logger.info(f"✅ Operations Manager signature uploaded and saved to form_data (URL: {url[:80]}...)")
                    current_app.logger.info(f"✅ Set both operations_manager_signature and opMan_signature keys")
                else:
                    # Upload failed, save as data URL string as fallback
                    form_data['operations_manager_signature'] = signature
                    form_data['opMan_signature'] = signature
                    current_app.logger.warning(f"⚠️ Operations Manager signature upload failed, saving as data URL for submission {submission_id}")
                    current_app.logger.warning(f"Set both keys with data URL fallback")
            except Exception as e:
                current_app.logger.error(f"❌ Error uploading Operations Manager signature: {e}")
                import traceback
                current_app.logger.error(traceback.format_exc())
                # Fallback: save as data URL string
                form_data['operations_manager_signature'] = signature
                form_data['opMan_signature'] = signature
                current_app.logger.warning(f"⚠️ Saving Operations Manager signature as data URL due to upload error")
                current_app.logger.warning(f"Set both keys due to error")
        elif signature and signature.strip():
            # Signature is already a URL or object format
            # Handle both string URLs and object formats
            if isinstance(signature, dict):
                form_data['operations_manager_signature'] = signature
                form_data['opMan_signature'] = signature
            elif isinstance(signature, str):
                form_data['operations_manager_signature'] = signature
                form_data['opMan_signature'] = signature
            current_app.logger.info(f"✅ Saved Operations Manager signature to form_data (already processed format)")
            current_app.logger.info(f"✅ Set both operations_manager_signature and opMan_signature keys")
        elif existing_om_signature:
            # Preserve existing signature if no new one provided
            form_data['operations_manager_signature'] = existing_om_signature
            form_data['opMan_signature'] = existing_om_signature  # Also set alternate key
            current_app.logger.info(f"✅ Preserved existing Operations Manager signature in form_data")
            current_app.logger.info(f"✅ Set both operations_manager_signature and opMan_signature keys")
        else:
            current_app.logger.warning(f"⚠️ No Operations Manager signature provided for submission {submission_id}")
            current_app.logger.warning(f"  - signature value: {repr(signature) if signature else 'None'}")
            current_app.logger.warning(f"  - existing_om_signature: {repr(existing_om_signature) if existing_om_signature else 'None'}")
        
        # Ensure work_items/items have photos for Civil/HVAC generators (payload sends photo_urls)
        _ensure_items_photos(form_data)
        
        # Log final form_data keys for debugging
        current_app.logger.info(f"🔍 Final form_data keys after Operations Manager approval: {list(form_data.keys())[:30]}")
        current_app.logger.info(f"  - operations_manager_comments in form_data: {bool(form_data.get('operations_manager_comments'))} (value: {repr(form_data.get('operations_manager_comments'))[:50] if form_data.get('operations_manager_comments') else 'None'})")
        current_app.logger.info(f"  - operations_manager_signature in form_data: {bool(form_data.get('operations_manager_signature'))}")
        current_app.logger.info(f"  - opMan_signature in form_data: {bool(form_data.get('opMan_signature'))}")
        if form_data.get('operations_manager_signature'):
            sig_val = form_data.get('operations_manager_signature')
            if isinstance(sig_val, dict):
                current_app.logger.info(f"  - operations_manager_signature type: dict, url: {sig_val.get('url', 'N/A')[:80] if sig_val.get('url') else 'N/A'}")
            else:
                current_app.logger.info(f"  - operations_manager_signature type: {type(sig_val).__name__}, preview: {str(sig_val)[:80] if sig_val else 'N/A'}")
        
        # CRITICAL: Verify comments and signature are actually set before committing
        if not form_data.get('operations_manager_comments'):
            current_app.logger.error(f"❌ CRITICAL: operations_manager_comments is NOT in form_data before commit!")
            current_app.logger.error(f"  - comments variable: {repr(comments)[:100]}")
            current_app.logger.error(f"  - existing_om_comments: {repr(existing_om_comments)[:100] if existing_om_comments else 'None'}")
        if not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
            current_app.logger.error(f"❌ CRITICAL: No OM signature keys in form_data before commit!")
            current_app.logger.error(f"  - signature variable: {repr(signature)[:100]}")
            current_app.logger.error(f"  - existing_om_signature: {repr(existing_om_signature)[:100] if existing_om_signature else 'None'}")
        
        submission.form_data = form_data
        flag_modified(submission, 'form_data')
        
        # Move to BD/Procurement review
        submission.workflow_status = 'bd_procurement_review'
        submission.updated_at = utc_now_naive()
        
        # Log final state before commit
        current_app.logger.info(f"💾 About to commit to database:")
        current_app.logger.info(f"  - Model operations_manager_comments: {bool(submission.operations_manager_comments)} ({len(submission.operations_manager_comments) if submission.operations_manager_comments else 0} chars)")
        current_app.logger.info(f"  - form_data operations_manager_comments: {bool(form_data.get('operations_manager_comments'))}")
        current_app.logger.info(f"  - form_data operations_manager_signature: {bool(form_data.get('operations_manager_signature'))}")
        current_app.logger.info(f"  - flag_modified called: True")
        
        if is_inspection_submission(submission):
            notify_inspection_stage(submission, 'bd_procurement_review')
        db.session.commit()
        
        # Verify after commit
        db.session.refresh(submission)
        current_app.logger.info(f"✅ Committed to database. Verifying:")
        current_app.logger.info(f"  - Model operations_manager_comments after commit: {bool(submission.operations_manager_comments)}")
        current_app.logger.info(f"  - form_data type after commit: {type(submission.form_data)}")
        if isinstance(submission.form_data, dict):
            current_app.logger.info(f"  - form_data operations_manager_comments after commit: {bool(submission.form_data.get('operations_manager_comments'))}")
            current_app.logger.info(f"  - form_data operations_manager_signature after commit: {bool(submission.form_data.get('operations_manager_signature'))}")
        
        # Regenerate documents for all modules (to include Operations Manager comments/signature)
        # This ensures Supervisor and all subsequent reviewers see the updated form with OM's changes
        job_id = None
        try:
            from common.db_utils import create_job_db
            from app.models import Job
            _, get_paths_fn, process_job_fn = get_module_functions(submission.module_type)
            
            # Delete old jobs to force regeneration
            old_jobs = Job.query.filter_by(submission_id=submission.id).all()
            for old_job in old_jobs:
                db.session.delete(old_job)
            db.session.commit()
            
            # Create new job for regeneration
            new_job = create_job_db(submission)
            job_id = new_job.job_id
            
            GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
            
            if EXECUTOR:
                EXECUTOR.submit(
                    process_job_fn,
                    submission.submission_id,
                    job_id,
                    current_app.config,
                    current_app._get_current_object()
                )
                current_app.logger.info(f"✅ Regeneration job {job_id} queued for Operations Manager approval - submission {submission_id} ({submission.module_type})")
            else:
                current_app.logger.error("ThreadPoolExecutor not available for document regeneration")
        except Exception as regen_err:
            current_app.logger.error(f"Error queuing regeneration job after OM approval: {regen_err}", exc_info=True)
        
        log_audit(user_id, 'operations_manager_approved', 'submission', submission_id, {
            'comments': comments,
            'has_signature': bool(signature)
        })

        send_team_notification(submission, user, "Operations Manager signed")
        
        return success_response({
            'submission': submission.to_dict(),
            'message': 'Approved successfully. Forwarded to Business Development and Procurement.' + (' Documents are being regenerated.' if job_id else ''),
            'job_id': job_id,
            'regenerating': bool(job_id)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in ops manager approval: {str(e)}", exc_info=True)
        return error_response('Failed to approve submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/approve-bd', methods=['POST'])
@jwt_required()
def approve_business_development(submission_id):
    """Business Development approves submission"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if user.role != 'admin' and not user.is_bd_inspection_reviewer():
            return error_response('Only Business Development can approve at this stage', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Allow BD to approve at bd_procurement_review stage OR re-approve at general_manager_review
        # (BD can edit their review even after form moves to GM stage, as long as GM hasn't approved)
        if submission.workflow_status not in ['bd_procurement_review', 'general_manager_review']:
            return error_response('Submission is not at BD/Procurement review stage', 
                                status_code=400, error_code='INVALID_STATUS')
        
        # Check if GM has already approved - if so, BD can no longer edit
        if submission.workflow_status == 'general_manager_review' and submission.general_manager_approved_at:
            return error_response('Cannot modify review after General Manager has approved', 
                                status_code=400, error_code='ALREADY_APPROVED_BY_GM')
        
        # Note: Removed "Already approved" check to allow BD to re-approve/update their review
        
        comments = data.get('comments', '')
        signature = data.get('signature', '')
        form_data_updates = data.get('form_data', {})
        
        # Log incoming data for debugging
        current_app.logger.info(f"🔍 Business Development approval request for submission {submission_id}:")
        current_app.logger.info(f"  - Comments provided: {bool(comments and comments.strip())} (length: {len(comments) if comments else 0})")
        current_app.logger.info(f"  - Signature provided: {bool(signature and signature.strip())} (type: {type(signature).__name__}, length: {len(str(signature)) if signature else 0})")
        current_app.logger.info(f"  - form_data_updates keys: {list(form_data_updates.keys())[:20] if form_data_updates else 'none'}")
        
        # Check if signature or comments are in form_data_updates
        if not signature or not str(signature).strip():
            signature = form_data_updates.get('business_dev_signature') or form_data_updates.get('businessDevSignature') or ''
            if signature:
                current_app.logger.info(f"✅ Using BD signature from form_data_updates")
        if not comments or not str(comments).strip():
            comments = form_data_updates.get('business_dev_comments') or form_data_updates.get('businessDevComments') or ''
            if comments:
                current_app.logger.info(f"✅ Using BD comments from form_data_updates")
        
        if not signature:
            signature = ''
        if not comments:
            comments = ''
        
        # Update submission
        submission.business_dev_id = user.id
        submission.business_dev_comments = comments
        submission.business_dev_approved_at = utc_now_naive()
        
        _raw = submission.form_data if submission.form_data else {}
        if isinstance(_raw, str):
            try:
                import json
                form_data = json.loads(_raw)
            except Exception:
                form_data = {}
        else:
            form_data = copy.deepcopy(_raw) if isinstance(_raw, dict) else {}
        
        existing_om_comments = form_data.get('operations_manager_comments')
        existing_om_signature = form_data.get('operations_manager_signature') or form_data.get('opMan_signature')
        current_app.logger.info(f"🔍 BD Approval: Preserving Operations Manager data before update:")
        current_app.logger.info(f"  - Existing OM comments: {bool(existing_om_comments)}")
        current_app.logger.info(f"  - Existing OM signature: {bool(existing_om_signature)}")
        
        # Also preserve other reviewer data
        existing_supervisor_comments = form_data.get('supervisor_comments')
        existing_supervisor_signature = form_data.get('supervisor_signature')
        
        if form_data_updates:
            # Merge form_data_updates, but preserve critical reviewer data
            form_data.update(form_data_updates)
            current_app.logger.info(f"✅ Updated form_data with BD's form_data_updates for submission {submission_id}")
        
        # Restore Operations Manager data if it was lost during update
        if existing_om_comments and not form_data.get('operations_manager_comments'):
            form_data['operations_manager_comments'] = existing_om_comments
            current_app.logger.info(f"✅ Restored Operations Manager comments after BD update")
        if existing_om_signature and not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
            form_data['operations_manager_signature'] = existing_om_signature
            current_app.logger.info(f"✅ Restored Operations Manager signature after BD update")
        
        # Restore supervisor data if it was lost (shouldn't happen, but be safe)
        if existing_supervisor_comments and not form_data.get('supervisor_comments'):
            form_data['supervisor_comments'] = existing_supervisor_comments
        if existing_supervisor_signature and not form_data.get('supervisor_signature'):
            form_data['supervisor_signature'] = existing_supervisor_signature
        
        # Always save BD comments and signature to form_data for next reviewers
        if comments:
            form_data['business_dev_comments'] = comments
            current_app.logger.info(f"✅ Saved BD comments to form_data")
        if signature:
            # Process and upload BD signature if it's a data URL
            if signature and signature.strip() and signature.startswith('data:image'):
                try:
                    save_sig_fn, get_paths_fn, _ = get_module_functions(submission.module_type)
                    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
                    
                    fname, fpath, url = save_sig_fn(signature, UPLOADS_DIR, prefix="bd_sig")
                    if url:
                        form_data['business_dev_signature'] = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
                        current_app.logger.info(f"✅ BD signature uploaded and saved to form_data (URL: {url[:80]}...)")
                    else:
                        form_data['business_dev_signature'] = signature
                        current_app.logger.warning(f"⚠️ BD signature upload failed, saving as data URL")
                except Exception as e:
                    current_app.logger.error(f"❌ Error uploading BD signature: {e}")
                    form_data['business_dev_signature'] = signature
            else:
                form_data['business_dev_signature'] = signature
                current_app.logger.info(f"✅ Saved BD signature to form_data")
        
        # Log final state to verify Operations Manager data is preserved
        current_app.logger.info(f"🔍 BD Approval: Final form_data state:")
        current_app.logger.info(f"  - operations_manager_comments: {bool(form_data.get('operations_manager_comments'))}")
        current_app.logger.info(f"  - operations_manager_signature: {bool(form_data.get('operations_manager_signature'))}")
        current_app.logger.info(f"  - business_dev_comments: {bool(form_data.get('business_dev_comments'))}")
        current_app.logger.info(f"  - business_dev_signature: {bool(form_data.get('business_dev_signature'))}")
        
        submission.form_data = form_data
        flag_modified(submission, 'form_data')
        
        # Check if both BD and Procurement have approved
        if submission.procurement_approved_at:
            submission.workflow_status = 'general_manager_review'
            message = 'Approved successfully. Both BD and Procurement approved. Forwarded to General Manager.'
        else:
            message = 'Approved successfully. Waiting for Procurement approval.'
        
        submission.updated_at = utc_now_naive()
        if is_inspection_submission(submission) and submission.workflow_status == 'general_manager_review':
            notify_inspection_stage(submission, 'general_manager_review')
        db.session.commit()
        
        # Regenerate documents for all modules (to include BD comments/signature)
        # This ensures Supervisor, OM, and all subsequent reviewers see the updated form with BD's changes
        job_id = None
        try:
            from common.db_utils import create_job_db
            from app.models import Job
            _, get_paths_fn, process_job_fn = get_module_functions(submission.module_type)

            # Delete old jobs to force regeneration
            old_jobs = Job.query.filter_by(submission_id=submission.id).all()
            for old_job in old_jobs:
                db.session.delete(old_job)
            db.session.commit()

            # Create new job for regeneration
            new_job = create_job_db(submission)
            job_id = new_job.job_id

            GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
            if EXECUTOR:
                EXECUTOR.submit(
                    process_job_fn,
                    submission.submission_id,
                    job_id,
                    current_app.config,
                    current_app._get_current_object()
                )
                current_app.logger.info(f"✅ Regeneration job {job_id} queued for BD approval - submission {submission_id} ({submission.module_type})")
            else:
                current_app.logger.error("ThreadPoolExecutor not available for BD document regeneration")
        except Exception as regen_err:
            current_app.logger.error(f"Error queuing regeneration job after BD approval: {regen_err}", exc_info=True)
        
        log_audit(user_id, 'business_dev_approved', 'submission', submission_id, {'comments': comments})

        send_team_notification(submission, user, "Business Development signed")
        
        return success_response({
            'submission': submission.to_dict(),
            'message': message,
            'job_id': job_id,
            'regenerating': bool(job_id)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in BD approval: {str(e)}", exc_info=True)
        return error_response('Failed to approve submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/approve-procurement', methods=['POST'])
@jwt_required()
def approve_procurement(submission_id):
    """Procurement approves submission"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if user.designation != 'procurement' and user.role != 'admin':
            return error_response('Only Procurement can approve at this stage', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Allow Procurement to approve at bd_procurement_review stage OR re-approve at general_manager_review
        # (Procurement can edit their review even after form moves to GM stage, as long as GM hasn't approved)
        if submission.workflow_status not in ['bd_procurement_review', 'general_manager_review']:
            return error_response('Submission is not at BD/Procurement review stage', 
                                status_code=400, error_code='INVALID_STATUS')
        
        # Check if GM has already approved - if so, Procurement can no longer edit
        if submission.workflow_status == 'general_manager_review' and submission.general_manager_approved_at:
            return error_response('Cannot modify review after General Manager has approved', 
                                status_code=400, error_code='ALREADY_APPROVED_BY_GM')
        
        # Note: Removed "Already approved" check to allow Procurement to re-approve/update their review
        
        comments = data.get('comments', '')
        signature = data.get('signature', '')
        form_data_updates = data.get('form_data', {})
        if not signature or not str(signature).strip():
            signature = form_data_updates.get('procurement_signature') or form_data_updates.get('procurementSignature') or ''
        if not signature:
            signature = ''
        
        # Update submission
        submission.procurement_id = user.id
        submission.procurement_comments = comments
        submission.procurement_approved_at = utc_now_naive()
        
        _raw = submission.form_data if submission.form_data else {}
        if isinstance(_raw, str):
            try:
                import json
                form_data = json.loads(_raw)
            except Exception:
                form_data = {}
        else:
            form_data = copy.deepcopy(_raw) if isinstance(_raw, dict) else {}
        
        existing_om_comments = form_data.get('operations_manager_comments')
        existing_om_signature = form_data.get('operations_manager_signature') or form_data.get('opMan_signature')
        existing_bd_comments = form_data.get('business_dev_comments')
        existing_bd_signature = form_data.get('business_dev_signature')
        current_app.logger.info(f"🔍 Procurement Approval: Preserving reviewer data before update:")
        current_app.logger.info(f"  - Existing OM comments: {bool(existing_om_comments)}")
        current_app.logger.info(f"  - Existing OM signature: {bool(existing_om_signature)}")
        current_app.logger.info(f"  - Existing BD comments: {bool(existing_bd_comments)}")
        current_app.logger.info(f"  - Existing BD signature: {bool(existing_bd_signature)}")
        
        if form_data_updates:
            form_data.update(form_data_updates)
            current_app.logger.info(f"✅ Updated form_data with Procurement's form_data_updates for submission {submission_id}")
        
        # Restore Operations Manager data if it was lost during update
        if existing_om_comments and not form_data.get('operations_manager_comments'):
            form_data['operations_manager_comments'] = existing_om_comments
            current_app.logger.info(f"✅ Restored Operations Manager comments after Procurement update")
        if existing_om_signature and not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
            form_data['operations_manager_signature'] = existing_om_signature
            current_app.logger.info(f"✅ Restored Operations Manager signature after Procurement update")
        
        # Restore Business Development data if it was lost during update
        if existing_bd_comments and not form_data.get('business_dev_comments'):
            form_data['business_dev_comments'] = existing_bd_comments
            current_app.logger.info(f"✅ Restored Business Development comments after Procurement update")
        if existing_bd_signature and not form_data.get('business_dev_signature'):
            form_data['business_dev_signature'] = existing_bd_signature
            current_app.logger.info(f"✅ Restored Business Development signature after Procurement update")
        
        # Always save Procurement comments and signature to form_data for next reviewers
        if comments:
            form_data['procurement_comments'] = comments
            current_app.logger.info(f"✅ Saved Procurement comments to form_data")
        if signature:
            # Process and upload Procurement signature if it's a data URL
            if signature and signature.strip() and signature.startswith('data:image'):
                try:
                    save_sig_fn, get_paths_fn, _ = get_module_functions(submission.module_type)
                    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
                    
                    fname, fpath, url = save_sig_fn(signature, UPLOADS_DIR, prefix="procurement_sig")
                    if url:
                        form_data['procurement_signature'] = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
                        current_app.logger.info(f"✅ Procurement signature uploaded and saved to form_data (URL: {url[:80]}...)")
                    else:
                        form_data['procurement_signature'] = signature
                        current_app.logger.warning(f"⚠️ Procurement signature upload failed, saving as data URL")
                except Exception as e:
                    current_app.logger.error(f"❌ Error uploading Procurement signature: {e}")
                    form_data['procurement_signature'] = signature
            else:
                form_data['procurement_signature'] = signature
                current_app.logger.info(f"✅ Saved Procurement signature to form_data")
        
        # Log final state to verify BD data is preserved
        current_app.logger.info(f"🔍 Procurement Approval: Final form_data state:")
        current_app.logger.info(f"  - operations_manager_comments: {bool(form_data.get('operations_manager_comments'))}")
        current_app.logger.info(f"  - operations_manager_signature: {bool(form_data.get('operations_manager_signature'))}")
        current_app.logger.info(f"  - business_dev_comments: {bool(form_data.get('business_dev_comments'))}")
        current_app.logger.info(f"  - business_dev_signature: {bool(form_data.get('business_dev_signature'))}")
        current_app.logger.info(f"  - procurement_comments: {bool(form_data.get('procurement_comments'))}")
        current_app.logger.info(f"  - procurement_signature: {bool(form_data.get('procurement_signature'))}")
        
        submission.form_data = form_data
        flag_modified(submission, 'form_data')
        
        # Check if both BD and Procurement have approved
        if submission.business_dev_approved_at:
            submission.workflow_status = 'general_manager_review'
            message = 'Approved successfully. Both BD and Procurement approved. Forwarded to General Manager.'
        else:
            message = 'Approved successfully. Waiting for Business Development approval.'
        
        submission.updated_at = utc_now_naive()
        if is_inspection_submission(submission) and submission.workflow_status == 'general_manager_review':
            notify_inspection_stage(submission, 'general_manager_review')
        db.session.commit()
        
        # Regenerate documents for all modules (to include Procurement comments/signature)
        # This ensures Supervisor, OM, BD, and all subsequent reviewers see the updated form with Procurement's changes
        job_id = None
        try:
            from common.db_utils import create_job_db
            from app.models import Job
            _, get_paths_fn, process_job_fn = get_module_functions(submission.module_type)

            # Delete old jobs to force regeneration
            old_jobs = Job.query.filter_by(submission_id=submission.id).all()
            for old_job in old_jobs:
                db.session.delete(old_job)
            db.session.commit()

            # Create new job for regeneration
            new_job = create_job_db(submission)
            job_id = new_job.job_id

            GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
            if EXECUTOR:
                EXECUTOR.submit(
                    process_job_fn,
                    submission.submission_id,
                    job_id,
                    current_app.config,
                    current_app._get_current_object()
                )
                current_app.logger.info(f"✅ Regeneration job {job_id} queued for Procurement approval - submission {submission_id} ({submission.module_type})")
            else:
                current_app.logger.error("ThreadPoolExecutor not available for Procurement document regeneration")
        except Exception as regen_err:
            current_app.logger.error(f"Error queuing regeneration job after Procurement approval: {regen_err}", exc_info=True)
        
        log_audit(user_id, 'procurement_approved', 'submission', submission_id, {'comments': comments})

        send_team_notification(submission, user, "Procurement signed")
        
        return success_response({
            'submission': submission.to_dict(),
            'message': message,
            'job_id': job_id,
            'regenerating': bool(job_id)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in Procurement approval: {str(e)}", exc_info=True)
        return error_response('Failed to approve submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/approve-gm', methods=['POST'])
@jwt_required()
def approve_general_manager(submission_id):
    """General Manager gives final approval"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if user.designation != 'general_manager' and user.role != 'admin':
            return error_response('Only General Manager can approve at this stage', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Allow GM to approve at general_manager_review stage OR re-approve when completed
        # (GM can edit their review even after form is completed as the final approver)
        if submission.workflow_status not in ['general_manager_review', 'completed']:
            return error_response('Submission is not at General Manager review stage', 
                                status_code=400, error_code='INVALID_STATUS')
        
        comments = data.get('comments', '')
        signature = data.get('signature', '')
        form_data_updates = data.get('form_data', {})
        if not signature or not str(signature).strip():
            signature = form_data_updates.get('general_manager_signature') or form_data_updates.get('generalManagerSignature') or ''
        if not signature:
            signature = ''
        
        # Update submission
        submission.general_manager_id = user.id
        submission.general_manager_comments = comments
        submission.general_manager_approved_at = utc_now_naive()
        submission.workflow_status = 'completed'
        submission.status = 'completed'
        
        _raw = submission.form_data if submission.form_data else {}
        if isinstance(_raw, str):
            try:
                import json
                form_data = json.loads(_raw)
            except Exception:
                form_data = {}
        else:
            form_data = copy.deepcopy(_raw) if isinstance(_raw, dict) else {}
        
        existing_om_comments = form_data.get('operations_manager_comments')
        existing_om_signature = form_data.get('operations_manager_signature') or form_data.get('opMan_signature')
        existing_bd_comments = form_data.get('business_dev_comments')
        existing_bd_signature = form_data.get('business_dev_signature')
        existing_procurement_comments = form_data.get('procurement_comments')
        existing_procurement_signature = form_data.get('procurement_signature')
        
        current_app.logger.info(f"🔍 General Manager Approval: Preserving reviewer data before update:")
        current_app.logger.info(f"  - Existing OM comments: {bool(existing_om_comments)}")
        current_app.logger.info(f"  - Existing OM signature: {bool(existing_om_signature)}")
        current_app.logger.info(f"  - Existing BD comments: {bool(existing_bd_comments)}")
        current_app.logger.info(f"  - Existing BD signature: {bool(existing_bd_signature)}")
        current_app.logger.info(f"  - Existing Procurement comments: {bool(existing_procurement_comments)}")
        current_app.logger.info(f"  - Existing Procurement signature: {bool(existing_procurement_signature)}")
        
        if form_data_updates:
            form_data.update(form_data_updates)
            current_app.logger.info(f"✅ Updated form_data with General Manager's form_data_updates for submission {submission_id}")
        
        # Restore Operations Manager data if it was lost during update
        if existing_om_comments and not form_data.get('operations_manager_comments'):
            form_data['operations_manager_comments'] = existing_om_comments
            current_app.logger.info(f"✅ Restored Operations Manager comments after General Manager update")
        if existing_om_signature and not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
            form_data['operations_manager_signature'] = existing_om_signature
            current_app.logger.info(f"✅ Restored Operations Manager signature after General Manager update")
        
        # Restore Business Development data if it was lost during update
        if existing_bd_comments and not form_data.get('business_dev_comments'):
            form_data['business_dev_comments'] = existing_bd_comments
            current_app.logger.info(f"✅ Restored Business Development comments after General Manager update")
        if existing_bd_signature and not form_data.get('business_dev_signature'):
            form_data['business_dev_signature'] = existing_bd_signature
            current_app.logger.info(f"✅ Restored Business Development signature after General Manager update")
        
        # Restore Procurement data if it was lost during update
        if existing_procurement_comments and not form_data.get('procurement_comments'):
            form_data['procurement_comments'] = existing_procurement_comments
            current_app.logger.info(f"✅ Restored Procurement comments after General Manager update")
        if existing_procurement_signature and not form_data.get('procurement_signature'):
            form_data['procurement_signature'] = existing_procurement_signature
            current_app.logger.info(f"✅ Restored Procurement signature after General Manager update")
        
        # Always save General Manager comments and signature to form_data
        if comments:
            form_data['general_manager_comments'] = comments
            current_app.logger.info(f"✅ Saved General Manager comments to form_data")
        if signature:
            # Process and upload General Manager signature if it's a data URL
            if signature and signature.strip() and signature.startswith('data:image'):
                try:
                    save_sig_fn, get_paths_fn, _ = get_module_functions(submission.module_type)
                    GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
                    
                    fname, fpath, url = save_sig_fn(signature, UPLOADS_DIR, prefix="gm_sig")
                    if url:
                        form_data['general_manager_signature'] = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
                        current_app.logger.info(f"✅ General Manager signature uploaded and saved to form_data (URL: {url[:80]}...)")
                    else:
                        form_data['general_manager_signature'] = signature
                        current_app.logger.warning(f"⚠️ General Manager signature upload failed, saving as data URL")
                except Exception as e:
                    current_app.logger.error(f"❌ Error uploading General Manager signature: {e}")
                    form_data['general_manager_signature'] = signature
            else:
                form_data['general_manager_signature'] = signature
                current_app.logger.info(f"✅ Saved General Manager signature to form_data")
        
        # Log final state
        current_app.logger.info(f"🔍 General Manager Approval: Final form_data state:")
        current_app.logger.info(f"  - operations_manager_comments: {bool(form_data.get('operations_manager_comments'))}")
        current_app.logger.info(f"  - operations_manager_signature: {bool(form_data.get('operations_manager_signature'))}")
        current_app.logger.info(f"  - business_dev_comments: {bool(form_data.get('business_dev_comments'))}")
        current_app.logger.info(f"  - business_dev_signature: {bool(form_data.get('business_dev_signature'))}")
        current_app.logger.info(f"  - procurement_comments: {bool(form_data.get('procurement_comments'))}")
        current_app.logger.info(f"  - procurement_signature: {bool(form_data.get('procurement_signature'))}")
        current_app.logger.info(f"  - general_manager_comments: {bool(form_data.get('general_manager_comments'))}")
        current_app.logger.info(f"  - general_manager_signature: {bool(form_data.get('general_manager_signature'))}")
        
        submission.form_data = form_data
        flag_modified(submission, 'form_data')
        submission.updated_at = utc_now_naive()
        if is_inspection_submission(submission):
            notify_inspection_completed(submission)
        db.session.commit()
        
        # Regenerate documents for all modules (to include General Manager comments/signature and all previous reviewers)
        # This ensures all users (Supervisor, OM, BD, Procurement) see the final version with all signatures
        job_id = None
        try:
            from common.db_utils import create_job_db
            from app.models import Job
            _, get_paths_fn, process_job_fn = get_module_functions(submission.module_type)
            
            # Delete old jobs to force regeneration
            old_jobs = Job.query.filter_by(submission_id=submission.id).all()
            for old_job in old_jobs:
                db.session.delete(old_job)
            db.session.commit()
            
            # Create new job for regeneration
            new_job = create_job_db(submission)
            job_id = new_job.job_id
            
            GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
            
            if EXECUTOR:
                EXECUTOR.submit(
                    process_job_fn,
                    submission.submission_id,
                    job_id,
                    current_app.config,
                    current_app._get_current_object()
                )
                current_app.logger.info(f"✅ Regeneration job {job_id} queued for General Manager approval - submission {submission_id} ({submission.module_type})")
            else:
                current_app.logger.error("ThreadPoolExecutor not available for document regeneration")
        except Exception as regen_err:
            current_app.logger.error(f"Error queuing regeneration job after GM approval: {regen_err}", exc_info=True)
        
        log_audit(user_id, 'general_manager_approved', 'submission', submission_id, {
            'comments': comments,
            'has_signature': bool(signature)
        })

        if is_inspection_submission(submission):
            send_team_notification(submission, user, "General Manager signed — Form Completed")
        
        return success_response({
            'submission': submission.to_dict(),
            'message': 'Final approval completed. Submission is now complete.' + (' Documents are being regenerated with all signatures.' if job_id else ''),
            'job_id': job_id,
            'regenerating': bool(job_id)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in GM approval: {str(e)}", exc_info=True)
        return error_response('Failed to approve submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/reject', methods=['POST'])
@jwt_required()
def reject_submission(submission_id):
    """Reject submission at any stage and send back to supervisor"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        reason = data.get('reason', '')
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if not reason:
            return error_response('Rejection reason is required', status_code=400, error_code='MISSING_REASON')
        
        if user.designation not in VALID_DESIGNATIONS and user.role != 'admin':
            return error_response('Invalid designation for rejection', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Record rejection details
        previous_stage = submission.workflow_status
        submission.workflow_status = 'rejected'
        submission.rejection_stage = previous_stage
        submission.rejection_reason = reason
        submission.rejected_at = utc_now_naive()
        submission.rejected_by_id = user.id
        submission.updated_at = utc_now_naive()
        if is_inspection_submission(submission):
            notify_inspection_rejected(submission, reason)
        
        db.session.commit()
        
        log_audit(user_id, 'reject_submission', 'submission', submission_id, {
            'reason': reason,
            'rejected_by': user.designation or user.role,
            'stage': submission.rejection_stage
        })
        
        return success_response({
            'submission': submission.to_dict(),
            'message': 'Submission rejected and sent back to supervisor for revision.'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error rejecting submission: {str(e)}", exc_info=True)
        return error_response('Failed to reject submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/withdraw', methods=['POST'])
@jwt_required()
def withdraw_hr_submission(submission_id):
    """Original HR submitter withdraws before final approval; notifies reporting manager / supervisor (in-app)."""
    try:
        from module_hr.routes import create_notification, get_form_type_display

        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        if not _is_hr_module_submission(submission):
            return error_response(
                'Withdraw is only available for HR forms',
                status_code=400,
                error_code='INVALID_MODULE',
            )
        if submission.user_id != user.id:
            return error_response(
                'Only the employee who submitted this form may withdraw it',
                status_code=403,
                error_code='FORBIDDEN',
            )
        if getattr(submission, 'status', None) == 'draft':
            return error_response(
                'Use delete draft instead of withdraw',
                status_code=400,
                error_code='INVALID_STATUS',
            )
        if _hr_submission_record_finalized_locked(submission):
            return error_response(
                'This request cannot be withdrawn (already approved, withdrawn, or completed)',
                status_code=400,
                error_code='NOT_WITHDRAWABLE',
            )

        fd = copy.deepcopy(_submission_form_data_dict(submission))
        now_iso = naive_utc_isoformat_z(utc_now_naive())
        fd['withdrawn_at'] = now_iso
        fd['withdrawn_by_user_id'] = user.id
        fd['withdrawn_by_display'] = (user.full_name or user.username or '').strip() or user.username

        submission.form_data = fd
        submission.workflow_status = 'withdrawn'
        submission.updated_at = utc_now_naive()
        flag_modified(submission, 'form_data')

        submitter_row = submission.user_id and db.session.get(User, submission.user_id)
        form_label = get_form_type_display(submission.module_type)
        ids = _hr_reporting_contact_user_ids_for_notification(submission, submitter_row or user)
        display_name = fd.get('employee_name') or (submitter_row and (submitter_row.full_name or submitter_row.username)) or user.username

        for rid in ids:
            target = db.session.get(User, rid)
            if not target or not getattr(target, 'is_active', True):
                continue
            create_notification(
                user_id=rid,
                title='HR form withdrawn by employee',
                message=(
                    f'{display_name} withdrew their {form_label} ({submission.submission_id}). '
                    'No further approval action is needed on this request.'
                ),
                notification_type='hr_submitter_withdrawn',
                submission_id=submission.submission_id,
            )

        db.session.commit()
        log_audit(user_id, 'hr_submitter_withdraw', 'submission', submission_id, {})

        return success_response(
            {'submission': submission.to_dict(include_form_data=False, include_latest_job=False)},
            message='Request withdrawn. Your reporting manager was notified.',
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error('Error withdrawing HR submission: %s', str(e), exc_info=True)
        return error_response('Failed to withdraw submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/update', methods=['PUT'])
@jwt_required()
def update_submission(submission_id):
    """Update submission form data (for edits during review)"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Log permission check details for debugging
        current_app.logger.info(f"🔍 UPDATE permission check for submission {submission_id}:")
        current_app.logger.info(f"  - User: {user.id} ({user.username})")
        current_app.logger.info(f"  - User designation: {user.designation}")
        current_app.logger.info(f"  - User role: {user.role}")
        current_app.logger.info(f"  - Submission status: {submission.workflow_status}")
        current_app.logger.info(f"  - Assigned OM: {getattr(submission, 'operations_manager_id', None)}")
        current_app.logger.info(f"  - OM approved at: {getattr(submission, 'operations_manager_approved_at', None)}")
        
        if not can_edit_submission(user, submission):
            current_app.logger.error(f"❌ Permission denied for user {user.id} ({user.designation}) to edit submission {submission_id}")
            return error_response('You do not have permission to edit this submission', 
                                status_code=403, error_code='UNAUTHORIZED')
        
        current_app.logger.info(f"✅ Permission granted for user {user.id} ({user.designation}) to edit submission {submission_id}")
        
        # Check if supervisor is updating their own submission
        # Allow updates if status is draft/submitted/rejected OR if in operations_manager_review but not yet approved
        is_supervisor_own_update = (
            user.designation == 'supervisor' and 
            hasattr(submission, 'supervisor_id') and 
            submission.supervisor_id == user.id and
            (
                submission.workflow_status in ['draft', 'submitted', 'rejected'] or
                (submission.workflow_status == 'operations_manager_review' and not submission.operations_manager_approved_at)
            )
        )
        
        # Also check if this is ANY user updating their own draft
        # Check both user_id and supervisor_id since drafts may use either
        is_own_draft_update = (
            submission.workflow_status == 'draft' and
            (submission.user_id == user.id or 
             (hasattr(submission, 'supervisor_id') and submission.supervisor_id == user.id))
        )
        
        current_app.logger.info(f"🔍 Draft check: status={submission.workflow_status}, user_id={submission.user_id}, supervisor_id={getattr(submission, 'supervisor_id', None)}, current_user={user.id}, is_own_draft={is_own_draft_update}")
        
        # Update form_data - accept full form_data or updates
        if 'form_data' in data:
            # Get existing form_data to preserve Operations Manager and other reviewer data
            _raw_existing = submission.form_data if submission.form_data else {}
            if isinstance(_raw_existing, str):
                try:
                    import json
                    existing_form_data = json.loads(_raw_existing)
                except Exception:
                    existing_form_data = {}
            else:
                existing_form_data = copy.deepcopy(_raw_existing) if isinstance(_raw_existing, dict) else {}
            
            # CRITICAL: Preserve all reviewer data before update (OM, BD, Procurement, Supervisor)
            existing_om_comments = existing_form_data.get('operations_manager_comments')
            existing_om_signature = existing_form_data.get('operations_manager_signature') or existing_form_data.get('opMan_signature')
            existing_bd_comments = existing_form_data.get('business_dev_comments')
            existing_bd_signature = existing_form_data.get('business_dev_signature')
            existing_procurement_comments = existing_form_data.get('procurement_comments')
            existing_procurement_signature = existing_form_data.get('procurement_signature')
            existing_supervisor_comments = existing_form_data.get('supervisor_comments')
            existing_supervisor_signature = existing_form_data.get('supervisor_signature')
            existing_work_items = existing_form_data.get('work_items')
            existing_items = existing_form_data.get('items')
            
            # If full form_data is provided, use it directly (like admin endpoint)
            # Use deepcopy to avoid mutating the request data
            incoming_form_data = data['form_data']
            if isinstance(incoming_form_data, dict):
                form_data = copy.deepcopy(incoming_form_data)
            elif isinstance(incoming_form_data, str):
                try:
                    form_data = json.loads(incoming_form_data)
                except Exception:
                    form_data = {}
            else:
                form_data = {}
            
            # Supervisor own update or draft submission: merge work_items/items so we keep previously submitted form + updates
            if is_supervisor_own_update or is_own_draft_update:
                if existing_work_items is not None or form_data.get('work_items'):
                    merged_wi = _merge_items_with_photos(
                        existing_work_items or [],
                        form_data.get('work_items') or [],
                        'work_items'
                    )
                    form_data['work_items'] = merged_wi
                    current_app.logger.info(f"✅ Merged work_items in update_submission for {submission_id}: {len(merged_wi)} items")
                if existing_items is not None or form_data.get('items'):
                    merged_items = _merge_items_with_photos(
                        existing_items or [],
                        form_data.get('items') or [],
                        'items'
                    )
                    form_data['items'] = merged_items
                    current_app.logger.info(f"✅ Merged items (HVAC) in update_submission for {submission_id}: {len(merged_items)} items")
            
            # Ensure all reviewer data is preserved if not in new form_data
            # Also ensure current reviewer's data from payload is saved (for OM/BD/PO/GM submitting)
            if isinstance(form_data, dict):
                # Operations Manager data: preserve existing OR use payload data (if OM is submitting)
                if user.designation == 'operations_manager':
                    # OM is submitting - ensure their data from payload is saved
                    if form_data.get('operations_manager_comments'):
                        current_app.logger.info(f"✅ Saving Operations Manager comments from payload in update_submission for {submission_id}")
                    elif existing_om_comments:
                        form_data['operations_manager_comments'] = existing_om_comments
                        current_app.logger.info(f"✅ Preserved existing Operations Manager comments in update_submission for {submission_id}")
                    
                    if form_data.get('operations_manager_signature') or form_data.get('opMan_signature'):
                        current_app.logger.info(f"✅ Saving Operations Manager signature from payload in update_submission for {submission_id}")
                    elif existing_om_signature:
                        form_data['operations_manager_signature'] = existing_om_signature
                        current_app.logger.info(f"✅ Preserved existing Operations Manager signature in update_submission for {submission_id}")
                else:
                    # Not OM - preserve existing OM data if not in payload
                    if existing_om_comments and not form_data.get('operations_manager_comments'):
                        form_data['operations_manager_comments'] = existing_om_comments
                        current_app.logger.info(f"✅ Preserved Operations Manager comments in update_submission for {submission_id}")
                    if existing_om_signature and not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
                        form_data['operations_manager_signature'] = existing_om_signature
                        current_app.logger.info(f"✅ Preserved Operations Manager signature in update_submission for {submission_id}")
                
                # Preserve Business Development data
                if existing_bd_comments and not form_data.get('business_dev_comments'):
                    form_data['business_dev_comments'] = existing_bd_comments
                    current_app.logger.info(f"✅ Preserved Business Development comments in update_submission for {submission_id}")
                if existing_bd_signature and not form_data.get('business_dev_signature'):
                    form_data['business_dev_signature'] = existing_bd_signature
                    current_app.logger.info(f"✅ Preserved Business Development signature in update_submission for {submission_id}")
                
                # Preserve Procurement data (unless Procurement is the one updating)
                if user.designation != 'procurement':
                    if existing_procurement_comments and not form_data.get('procurement_comments'):
                        form_data['procurement_comments'] = existing_procurement_comments
                        current_app.logger.info(f"✅ Preserved Procurement comments in update_submission for {submission_id}")
                    if existing_procurement_signature and not form_data.get('procurement_signature'):
                        form_data['procurement_signature'] = existing_procurement_signature
                        current_app.logger.info(f"✅ Preserved Procurement signature in update_submission for {submission_id}")
                
                # Preserve Supervisor data
                if existing_supervisor_comments and not form_data.get('supervisor_comments'):
                    form_data['supervisor_comments'] = existing_supervisor_comments
                    current_app.logger.info(f"✅ Preserved Supervisor comments in update_submission for {submission_id}")
                if existing_supervisor_signature and not form_data.get('supervisor_signature'):
                    form_data['supervisor_signature'] = existing_supervisor_signature
                    current_app.logger.info(f"✅ Preserved Supervisor signature in update_submission for {submission_id}")
                existing_tech_signature = existing_form_data.get('tech_signature') or existing_form_data.get('submitter_signature')
                if existing_tech_signature and not _hr_signature_blob_non_empty(form_data.get('tech_signature')):
                    form_data['tech_signature'] = existing_tech_signature
                    current_app.logger.info(f"✅ Preserved Submitter (tech) signature in update_submission for {submission_id}")
                existing_submitter_comments = existing_form_data.get('submitter_comments') or existing_form_data.get('general_comments')
                if existing_submitter_comments and not (form_data.get('submitter_comments') or '').strip():
                    form_data['submitter_comments'] = existing_submitter_comments
                    current_app.logger.info(f"✅ Preserved Submitter comments in update_submission for {submission_id}")
            
            _ensure_items_photos(form_data)
            
            # If supervisor is updating their own submission or submitting a draft, ensure signature is saved
            if (is_supervisor_own_update or is_own_draft_update) and isinstance(form_data, dict):
                existing_comment = form_data.get('supervisor_comments', '')
                if existing_comment and '[Form updated by supervisor with new details]' not in existing_comment:
                    form_data['supervisor_comments'] = existing_comment + '\n\n[Form updated by supervisor with new details]'
                elif not existing_comment:
                    form_data['supervisor_comments'] = '[Form updated by supervisor with new details]'
                
                # Process supervisor signature - upload if it's a new data URL
                _preserve_submitter_comments_before_supervisor_signoff(form_data, submission)
                _preserve_submitter_signature_before_supervisor_signoff(form_data, submission)
                supervisor_sig_data = form_data.get('supervisor_signature', '')
                if supervisor_sig_data and isinstance(supervisor_sig_data, str) and supervisor_sig_data.startswith('data:image'):
                    # New signature provided as data URL - need to upload it
                    try:
                        save_sig_fn, get_paths_fn, _ = get_module_functions(submission.module_type)
                        GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
                        
                        fname, fpath, url = save_sig_fn(supervisor_sig_data, UPLOADS_DIR, prefix="supervisor_sig")
                        if url:
                            form_data['supervisor_signature'] = {"saved": fname, "path": fpath, "url": url, "is_cloud": True}
                            current_app.logger.info(f"✅ Supervisor signature uploaded and saved for submission {submission_id}")
                        else:
                            current_app.logger.warning(f"⚠️ Supervisor signature upload failed for submission {submission_id}")
                            # Preserve old signature if upload fails
                            old_form_data = submission.form_data if submission.form_data else {}
                            if old_form_data.get('supervisor_signature'):
                                form_data['supervisor_signature'] = old_form_data['supervisor_signature']
                    except Exception as e:
                        current_app.logger.error(f"❌ Error uploading supervisor signature: {e}")
                        # Preserve old signature if upload fails
                        old_form_data = submission.form_data if submission.form_data else {}
                        if old_form_data.get('supervisor_signature'):
                            form_data['supervisor_signature'] = old_form_data['supervisor_signature']
                elif 'supervisor_signature' in form_data and form_data['supervisor_signature']:
                    # Signature is already in form_data (object format), ensure it's preserved
                    current_app.logger.info(f"✅ Supervisor signature preserved in form_data for submission {submission_id}")
                else:
                    # No new signature provided - preserve existing one
                    old_form_data = submission.form_data if submission.form_data else {}
                    if old_form_data.get('supervisor_signature'):
                        form_data['supervisor_signature'] = old_form_data['supervisor_signature']
                        current_app.logger.info(f"✅ Preserving existing supervisor signature for submission {submission_id}")
                    else:
                        current_app.logger.warning(f"⚠️ No supervisor signature found for submission {submission_id}")
            
            if isinstance(form_data, dict) and _is_hr_module_submission(submission):
                form_data = _enforce_hr_record_fields_in_form_data(user, submission, form_data)

            submission.form_data = form_data
            flag_modified(submission, 'form_data')
        elif 'form_data_updates' in data:
            # Otherwise merge updates (backward compatibility)
            form_data_updates = data.get('form_data_updates', {})
            if isinstance(form_data_updates, dict) and _is_hr_module_submission(submission):
                _pop_hr_revision_audit_from_updates(form_data_updates)
            # Deepcopy so merge cannot clobber submission.form_data before trail restore.
            _raw_fd = submission.form_data if submission.form_data else {}
            if isinstance(_raw_fd, str):
                try:
                    import json
                    form_data = json.loads(_raw_fd)
                except Exception:
                    form_data = {}
            elif isinstance(_raw_fd, dict):
                form_data = copy.deepcopy(_raw_fd)
            else:
                form_data = {}
            
            # CRITICAL: Preserve Operations Manager data before merging updates
            existing_om_comments = form_data.get('operations_manager_comments')
            existing_om_signature = form_data.get('operations_manager_signature') or form_data.get('opMan_signature')
            
            form_data.update(form_data_updates)
            
            # Restore Operations Manager data if it was lost during update
            if existing_om_comments and not form_data.get('operations_manager_comments'):
                form_data['operations_manager_comments'] = existing_om_comments
                current_app.logger.info(f"✅ Restored Operations Manager comments after form_data_updates merge for {submission_id}")
            if existing_om_signature and not form_data.get('operations_manager_signature') and not form_data.get('opMan_signature'):
                form_data['operations_manager_signature'] = existing_om_signature
                current_app.logger.info(f"✅ Restored Operations Manager signature after form_data_updates merge for {submission_id}")
            
            if isinstance(form_data, dict) and _is_hr_module_submission(submission):
                form_data = _enforce_hr_record_fields_in_form_data(user, submission, form_data)

            submission.form_data = form_data
            flag_modified(submission, 'form_data')
        
        if ('form_data' in data or 'form_data_updates' in data) and _is_hr_module_submission(submission):
            fd = submission.form_data
            if isinstance(fd, dict):
                _stamp_hr_submission_revision_history(fd, user)
                flag_modified(submission, 'form_data')
        if 'site_name' in data:
            submission.site_name = data['site_name']
        if 'visit_date' in data:
            try:
                submission.visit_date = datetime.strptime(data['visit_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass  # Invalid date, skip
        
        # If supervisor is updating their own submission or user is submitting their draft,
        # move it to Operations Manager review
        # This ensures updated forms are sent for review with new changes
        if is_supervisor_own_update or is_own_draft_update:
            # If this was a draft, also change the main status from 'draft' to 'submitted'
            if submission.status == 'draft':
                submission.status = 'submitted'
                current_app.logger.info(f"✅ Submission {submission_id} status changed from 'draft' to 'submitted'")
            
            # Change workflow_status to operations_manager_review so it goes to Operations Manager
            submission.workflow_status = 'operations_manager_review'
            current_app.logger.info(f"✅ Submission {submission_id} workflow_status changed to 'operations_manager_review'")
        
        submission.updated_at = utc_now_naive()
        if (
            is_inspection_submission(submission)
            and (is_supervisor_own_update or is_own_draft_update)
        ):
            notify_inspection_stage(submission, 'operations_manager_review')
        db.session.commit()
        
        # Regenerate documents if this is a supervisor updating their own submission,
        # a user submitting their draft, or if it's being updated by a reviewer
        job_id = None
        should_regenerate = is_supervisor_own_update or is_own_draft_update or user.is_bd_inspection_reviewer() or user.designation in ['operations_manager', 'procurement', 'general_manager']
        if should_regenerate:
            try:
                from common.db_utils import create_job_db
                from app.models import Job
                _, get_paths_fn, process_job_fn = get_module_functions(submission.module_type)
                
                # Delete old jobs to force regeneration
                old_jobs = Job.query.filter_by(submission_id=submission.id).all()
                for old_job in old_jobs:
                    db.session.delete(old_job)
                db.session.commit()
                
                # Create new job for regeneration
                new_job = create_job_db(submission)
                job_id = new_job.job_id
                
                GENERATED_DIR, UPLOADS_DIR, JOBS_DIR, EXECUTOR = get_paths_fn()
                
                if EXECUTOR:
                    EXECUTOR.submit(
                        process_job_fn,
                        submission.submission_id,
                        job_id,
                        current_app.config,
                        current_app._get_current_object()
                    )
                    current_app.logger.info(f"✅ Regeneration job {job_id} queued for submission {submission_id} ({submission.module_type})")
                else:
                    current_app.logger.error("ThreadPoolExecutor not available for document regeneration")
            except Exception as regen_err:
                current_app.logger.error(f"Error queuing regeneration job after update_submission: {regen_err}", exc_info=True)
        
        log_audit(user_id, 'update_submission', 'submission', submission_id)
        
        return success_response({
            'submission': submission.to_dict(),
            'message': 'Submission updated successfully. Documents are being regenerated.' if job_id else 'Submission updated successfully',
            'job_id': job_id,
            'regenerating': bool(job_id)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating submission: {str(e)}", exc_info=True)
        return error_response('Failed to update submission', status_code=500, error_code='DATABASE_ERROR')


@workflow_bp.route('/submissions/<submission_id>/resubmit', methods=['POST'])
@jwt_required()
def resubmit_submission(submission_id):
    """Resubmit a rejected submission (supervisor only)"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        data = request.get_json() or {}
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        if user.designation != 'supervisor' and user.role != 'admin':
            return error_response('Only supervisors can resubmit rejected submissions', 
                                status_code=403, error_code='INVALID_DESIGNATION')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        if submission.workflow_status != 'rejected':
            return error_response('Only rejected submissions can be resubmitted', 
                                status_code=400, error_code='INVALID_STATUS')
        
        if submission.supervisor_id != user.id and user.role != 'admin':
            return error_response('You can only resubmit your own submissions', 
                                status_code=403, error_code='UNAUTHORIZED')
        
        # Update form_data if provided
        form_data_updates = data.get('form_data', {})
        if form_data_updates:
            form_data = submission.form_data if submission.form_data else {}
            form_data.update(form_data_updates)
            submission.form_data = form_data
        
        # Reset workflow to start
        submission.workflow_status = 'operations_manager_review'
        submission.rejection_stage = None
        submission.rejection_reason = None
        submission.rejected_at = None
        submission.rejected_by_id = None
        submission.updated_at = utc_now_naive()
        if is_inspection_submission(submission):
            notify_inspection_stage(submission, 'operations_manager_review')
        
        db.session.commit()
        
        log_audit(user_id, 'resubmit_submission', 'submission', submission_id)
        
        return success_response({
            'submission': submission.to_dict(),
            'message': 'Submission resubmitted successfully. Sent to Operations Manager.'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resubmitting submission: {str(e)}", exc_info=True)
        return error_response('Failed to resubmit submission', status_code=500, error_code='DATABASE_ERROR')


# Legacy compatibility endpoints (deprecated but kept for backwards compatibility)
@workflow_bp.route('/submissions/<submission_id>/approve', methods=['POST'])
@jwt_required()
def legacy_approve_submission(submission_id):
    """Legacy approval endpoint - routes to appropriate new endpoint"""
    try:
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')
        
        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            return error_response('Submission not found', status_code=404, error_code='NOT_FOUND')
        
        # Check if supervisor is resubmitting their own form
        is_supervisor_own = (
            user.designation == 'supervisor' and 
            hasattr(submission, 'supervisor_id') and 
            submission.supervisor_id == user.id
        )
        
        # Allow the supervisor to sign off / resubmit at the supervisor stage,
        # initial drafts, or while still at OM review (before OM approval).
        is_supervisor_review_stage = (
            user.designation == 'supervisor'
            and submission.workflow_status in ('supervisor_review', 'supervisor_notified')
            and (not hasattr(submission, 'supervisor_id') or submission.supervisor_id in (None, user.id))
        )
        if (is_supervisor_own or is_supervisor_review_stage) and (
            submission.workflow_status in ['submitted', 'rejected', 'supervisor_review', 'supervisor_notified', None] or
            (submission.workflow_status == 'operations_manager_review' and not submission.operations_manager_approved_at)
        ):
            return approve_supervisor_resubmission(submission_id)
        
        # Route to appropriate endpoint based on current workflow status
        if submission.workflow_status == 'operations_manager_review':
            return approve_operations_manager(submission_id)
        elif submission.workflow_status == 'bd_procurement_review':
            if user.is_bd_inspection_reviewer():
                return approve_business_development(submission_id)
            elif user.designation == 'procurement':
                return approve_procurement(submission_id)
        elif submission.workflow_status == 'general_manager_review':
            return approve_general_manager(submission_id)
        else:
            return error_response('Invalid workflow status for approval', 
                                status_code=400, error_code='INVALID_STATUS')
    except Exception as e:
        current_app.logger.error(f"Error in legacy approval: {str(e)}", exc_info=True)
        return error_response('Failed to process approval', status_code=500, error_code='DATABASE_ERROR')
