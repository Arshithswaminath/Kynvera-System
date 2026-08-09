# Legacy stub kept for backwards compatibility. The production email pipeline
# lives in common/email_service.py (Mailjet / SMTP); this module just
# logs and returns success so any old call sites do not raise.
import logging

logger = logging.getLogger(__name__)

INTERNAL_RECIPIENTS = ["arshith@injaaz.ae"]


def send_outlook_email(subject, body, attachments=None, to_address=None):
    logger.debug(
        "Dummy email bypassed (legacy stub). subject=%r to=%r attachments=%d",
        subject,
        to_address or INTERNAL_RECIPIENTS,
        len(attachments) if attachments else 0,
    )
    return True, "Email bypassed (dummy)"