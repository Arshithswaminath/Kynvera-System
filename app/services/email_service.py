import logging
import os

logger = logging.getLogger(__name__)


def _minimal_mail_app():
    """
    Build a bare Flask app carrying only the MAIL_* config (same env keys as
    config.py) so common.email_service.send_email can run outside a request
    context (background threads / RQ workers).
    """
    from flask import Flask

    app = Flask(__name__)
    app.config.update(
        MAIL_SERVER=os.getenv("MAIL_SERVER"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
        MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "true").lower() == "true",
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", "noreply@injaaz.com"),
        BREVO_API_KEY=os.getenv("BREVO_API_KEY"),
        MAILJET_API_KEY=os.getenv("MAILJET_API_KEY"),
        MAILJET_SECRET_KEY=os.getenv("MAILJET_SECRET_KEY"),
    )
    return app


def send_outlook_email(subject, body, attachments, recipient):
    """
    Send an email via the shared service in common/email_service.py
    (Brevo HTTPS, Mailjet HTTPS, or SMTP — whichever is configured).
    Return a tuple (status_bool, message).
    """
    try:
        if not recipient:
            return False, "no recipient provided"

        from flask import has_app_context

        from common.email_service import send_email

        attachments = [p for p in (attachments or []) if p and os.path.exists(p)]

        if has_app_context():
            ok = send_email(recipient, subject, body, attachments=attachments, source='other')
        else:
            with _minimal_mail_app().app_context():
                ok = send_email(recipient, subject, body, attachments=attachments, source='other')

        if ok:
            logger.info("Email sent to %s with %d attachment(s)", recipient, len(attachments))
            return True, "sent"
        logger.warning("Email send failed for %s (see common.email_service logs)", recipient)
        return False, "send failed"
    except Exception as e:
        logger.exception("Failed to send email: %s", e)
        return False, str(e)
