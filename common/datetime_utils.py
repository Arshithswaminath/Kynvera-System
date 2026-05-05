"""
UTC helpers for naive DateTime columns (legacy schema stores UTC without tzinfo).
Prefer this over datetime.utcnow() (deprecated in Python 3.12+).
"""
from datetime import datetime, timezone


def utc_now_naive():
    """Current UTC time as naive datetime, matching existing DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
