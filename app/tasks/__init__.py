"""Background job helpers (RQ / in-process).

This directory is the ``app.tasks`` package. Do not add a sibling
``app/tasks.py`` file — it shadows the package and breaks imports such as
``app.tasks.sla_jobs``.
"""

from __future__ import annotations

__all__ = ("enqueue_report_job", "process_report_job")


def __getattr__(name: str):
    if name in ("enqueue_report_job", "process_report_job"):
        from app.tasks.visit_report_jobs import enqueue_report_job, process_report_job

        return enqueue_report_job if name == "enqueue_report_job" else process_report_job
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
