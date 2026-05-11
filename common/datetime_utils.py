"""
UTC helpers for naive DateTime columns (legacy schema stores UTC without tzinfo).
Prefer this over datetime.utcnow() (deprecated in Python 3.12+).

API consumers (JavaScript `Date`) assume ISO strings without an offset are *local*
time — always emit an explicit UTC suffix (`Z`) for naive UTC timestamps.
"""
import re
from datetime import datetime, timezone


def naive_utc_isoformat_z(dt):
    """Serialize naive UTC datetime for JSON, e.g. ``2026-05-06T06:51:00Z``."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(sep="T") + "Z"


def format_naive_utc_in_dubai(dt, fmt="%d/%m/%Y %H:%M"):
    """Interpret naive DB datetimes as UTC wall time; display string in Asia/Dubai (GST)."""
    if dt is None:
        return None
    try:
        from zoneinfo import ZoneInfo

        dubai = ZoneInfo("Asia/Dubai")
    except Exception:
        return dt.strftime(fmt)
    utc_v = dt
    if getattr(utc_v, "tzinfo", None) is not None:
        utc_v = utc_v.astimezone(timezone.utc).replace(tzinfo=None)
    aware = utc_v.replace(tzinfo=timezone.utc)
    return aware.astimezone(dubai).strftime(fmt)


def format_now_in_dubai(fmt="%d/%m/%Y %H:%M"):
    """Current instant formatted in Asia/Dubai."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Dubai")).strftime(fmt)
    except Exception:
        return datetime.now().strftime(fmt)


def utc_now_naive():
    """Current UTC time as naive datetime, matching existing DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_legacy_hr_iso_to_utc_z(val: str | None) -> str | None:
    """
    Normalize timestamps stored in HR ``form_data`` for API/UI consumers.

    Legacy values used ``datetime.now().isoformat()`` with no timezone (wall clock on the UAE host,
    i.e. Asia/Dubai). New values use UTC with ``Z`` from ``naive_utc_isoformat_z``.

    Returns canonical UTC ISO ending in ``Z``, or ``None`` if ``val`` should be left unchanged
    (empty, date-only, or unparsable).
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s_norm = s.replace(" ", "T", 1)

    if re.search(r"[zZ]$", s_norm):
        core = s_norm[:-1]
        try:
            dt = datetime.fromisoformat(core)
        except ValueError:
            return None
        if getattr(dt, "tzinfo", None) is not None:
            utc_naive = dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            utc_naive = dt
        return utc_naive.isoformat(sep="T") + "Z"

    if re.search(r"[+-]\d{2}:?\d{2}$", s_norm):
        try:
            dt = datetime.fromisoformat(s_norm)
        except ValueError:
            return None
        if getattr(dt, "tzinfo", None) is None:
            return None
        utc_naive = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return utc_naive.isoformat(sep="T") + "Z"

    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", s_norm):
        return None
    try:
        dt_naive = datetime.fromisoformat(s_norm)
    except ValueError:
        return None
    if getattr(dt_naive, "tzinfo", None) is not None:
        return None
    try:
        from zoneinfo import ZoneInfo

        dubai = ZoneInfo("Asia/Dubai")
    except Exception:
        return None
    aware = dt_naive.replace(tzinfo=dubai)
    utc_naive = aware.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_naive.isoformat(sep="T") + "Z"


def parse_employment_start_date(val):
    """Return None when val is omitted or cleared; parse YYYY-MM-DD; raises ValueError if invalid."""
    from datetime import date as date_cls, datetime as dt_cls
    if val in (None, ''):
        return None
    if isinstance(val, date_cls) and not isinstance(val, dt_cls):
        return val
    s = str(val).strip()[:10]
    try:
        return dt_cls.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('employment_start_date must be YYYY-MM-DD')
