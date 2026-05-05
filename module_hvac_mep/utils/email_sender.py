# Dummy email sender for cloud deployment (no SMTP dependency)
INTERNAL_RECIPIENTS = ["arshith@injaaz.ae"]

def send_outlook_email(subject, body, attachments=None, to_address=None):
    # Log and return success so callers proceed
    print("DUMMY EMAIL: subject:", subject)
    print("to:", to_address or INTERNAL_RECIPIENTS)
    if attachments:
        print("attachments:", len(attachments))
    return True, "Email bypassed (dummy)"