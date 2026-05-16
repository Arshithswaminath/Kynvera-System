import logging

logger = logging.getLogger(__name__)

def send_outlook_email(subject, body, attachments, recipient):
    """
    Placeholder. Implement Outlook/SMTP sending here.
    Return a tuple (status_bool, message)
    """
    try:
        # TODO: integrate with real email provider
        logger.info("Pretend sending email to %s with attachments %s", recipient, attachments)
        return True, "sent (mock)"
    except Exception as e:
        logger.exception("Failed to send email: %s", e)
        return False, str(e)