"""
Background job helpers: prefer RQ when Redis is available, otherwise fall back
to ThreadPoolExecutor / daemon thread / synchronous call so local/dev keeps working.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def enqueue_or_run(
    func: Callable,
    *args: Any,
    executor=None,
    use_thread: bool = True,
    sync: bool = False,
    job_timeout: int = 600,
    description: str = '',
    **kwargs: Any,
):
    """
    Run ``func`` via RQ if a queue is available; otherwise use executor, thread, or sync.

    Returns the RQ Job, Future, Thread, or the sync return value.
    """
    from app.extensions import get_rq_queue

    label = description or getattr(func, '__name__', 'job')
    q = get_rq_queue()
    if q is not None:
        try:
            job = q.enqueue(func, *args, job_timeout=job_timeout, **kwargs)
            logger.info("Enqueued RQ job %s (%s)", getattr(job, 'id', '?'), label)
            return job
        except Exception:
            logger.exception("RQ enqueue failed for %s — falling back", label)

    if executor is not None:
        try:
            future = executor.submit(func, *args, **kwargs)
            logger.info("Submitted %s to ThreadPoolExecutor", label)
            return future
        except Exception:
            logger.exception("Executor submit failed for %s — falling back", label)

    if sync or not use_thread:
        logger.info("Running %s synchronously", label)
        return func(*args, **kwargs)

    thread = threading.Thread(
        target=func, args=args, kwargs=kwargs, daemon=True, name=f"injaaz-{label}"
    )
    thread.start()
    logger.info("Started background thread for %s", label)
    return thread
