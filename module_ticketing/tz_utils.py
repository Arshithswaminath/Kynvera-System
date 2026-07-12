"""Timezone display helpers for the ticketing module.

All ticket timestamps are stored as naive UTC in the database (see
`app.models._utcnow`). The UAE-based teams need to *see* Gulf Standard Time
(UTC+4, no DST) in the UI, PDFs, and emails. Storage stays UTC everywhere —
only convert right before formatting/displaying a value.
"""
from datetime import datetime, timedelta

GST_OFFSET = timedelta(hours=4)


def to_gst(dt):
    """Return `dt` shifted from naive-UTC to naive Gulf Standard Time.

    Non-datetime values (None, date, str, etc.) are returned unchanged so
    this can be called defensively on values of uncertain type.
    """
    if dt is None or not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt + GST_OFFSET
