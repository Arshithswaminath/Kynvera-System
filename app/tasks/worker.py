"""
RQ Worker entrypoint.

Run with:
  python -m app.tasks.worker

Or with Docker/Render worker service:
  rq worker default --url $REDIS_URL
"""
from rq import Worker, Queue, Connection
import os
from redis import from_url

listen = ['default']

redis_url = os.environ.get('REDIS_URL')
if not redis_url:
    raise RuntimeError("REDIS_URL not set")

conn = from_url(redis_url, decode_responses=True)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(list(map(Queue, listen)))
        worker.work()