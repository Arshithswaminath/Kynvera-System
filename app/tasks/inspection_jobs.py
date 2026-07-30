"""
Pickle-safe RQ job entrypoints for inspection report generation and email notify.

These recreate an app context so workers (and thread fallbacks) do not need a
live Flask app object passed across process boundaries.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _create_app():
    """Prefer kynver factory; fall back to legacy shims."""
    try:
        from kynver import create_app
        return create_app()
    except Exception:
        logger.exception("kynver.create_app failed; trying legacy shims")
        try:
            from Injaaz import create_app
            return create_app()
        except Exception:
            from Amaan import create_app
            return create_app()


def run_hvac_process_job(sub_id: str, job_id: str):
    app = _create_app()
    with app.app_context():
        from module_hvac_mep.routes import process_job
        process_job(sub_id, job_id, app.config, app)


def run_inspection_submitted_notify(submission_id: str, submitter_id=None):
    app = _create_app()
    with app.app_context():
        from app.models import db, User, Submission
        from common.workflow_notifications import send_inspection_submitted

        submission = Submission.query.filter_by(submission_id=submission_id).first()
        if not submission:
            # Some installs use numeric id
            try:
                submission = db.session.get(Submission, int(submission_id))
            except (TypeError, ValueError):
                submission = None
        if not submission:
            logger.warning("inspection notify: submission %s not found", submission_id)
            return False
        submitter = None
        if submitter_id is not None:
            try:
                submitter = db.session.get(User, int(submitter_id))
            except (TypeError, ValueError):
                submitter = User.query.get(submitter_id)
        return bool(send_inspection_submitted(submission, submitter))


def run_send_email_job(recipient, subject, body, html_body=None, cc=None):
    """Thin wrapper so RQ can import a stable module path for email sends."""
    app = _create_app()
    with app.app_context():
        from common.email_service import send_email
        return send_email(
            recipient, subject, body, html_body=html_body, cc=cc, attachments=None
        )


def enqueue_inspection_process(module_type: str, sub_id: str, job_id: str, executor=None):
    """Queue Fire Systems process_job via RQ (executor/thread fallback)."""
    from app.tasks.job_runner import enqueue_or_run

    if module_type != 'hvac_mep':
        logger.warning("No inspection process job for module_type=%s", module_type)
        return None
    return enqueue_or_run(
        run_hvac_process_job,
        sub_id,
        job_id,
        executor=executor,
        description=f'{module_type}-process-{job_id}',
    )
