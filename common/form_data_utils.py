"""
SQLAlchemy JSON column helpers for submission.form_data.

Mutating the same dict instance as submission.form_data often does not persist;
always copy before writing, or use sqlalchemy.orm.attributes.flag_modified.
"""


def shallow_copy_form_data(submission):
    """
    Shallow copy of submission.form_data for safe assignment back to submission.form_data.
    `submission` is any object with a .form_data attribute (e.g. Submission).
    """
    fd = getattr(submission, "form_data", None)
    if not fd:
        return {}
    if isinstance(fd, dict):
        return dict(fd)
    return {}
