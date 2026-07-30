"""
RQ Worker entrypoint (+ optional MMR APScheduler).

Run with:
  python -m app.tasks.worker

Requires REDIS_URL. Set RUN_MMR_SCHEDULER=true on this process when web
WEB_CONCURRENCY > 1 so automations run exactly once.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        raise RuntimeError("REDIS_URL not set — cannot start RQ worker")

    # Build Flask app so job functions that call create_app / use models share config.
    try:
        from kynver import create_app
        app = create_app()
    except Exception:
        logger.exception("kynver.create_app failed; trying legacy shims")
        try:
            from Injaaz import create_app
            app = create_app()
        except Exception:
            from Amaan import create_app
            app = create_app()

    # MMR scheduler is gated inside init_scheduler (RUN_MMR_SCHEDULER / WEB_CONCURRENCY).
    # create_app already attempts init when mmr_bp registers; ensure flag is honored on worker.
    with app.app_context():
        try:
            from module_mmr.scheduler import init_scheduler
            init_scheduler(app)
        except Exception:
            logger.exception("MMR scheduler init on worker failed (continuing with RQ only)")

    from redis import from_url
    from rq import Worker, Queue, Connection

    listen = ['default']
    conn = from_url(redis_url, decode_responses=True)
    logger.info("Starting RQ worker on queues=%s", listen)
    with Connection(conn):
        worker = Worker(list(map(Queue, listen)))
        worker.work()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logger.exception("Worker crashed")
        sys.exit(1)
