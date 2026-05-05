import os
import json
import tempfile
import redis

REDIS_URL = os.environ.get('REDIS_URL', '')
use_redis = bool(REDIS_URL)

if use_redis:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        redis_client = None
else:
    redis_client = None

def save_report_state(report_id, data):
    if redis_client:
        redis_client.set(f"report_state:{report_id}", json.dumps(data))
    else:
        path = os.path.join(tempfile.gettempdir(), f"{report_id}.json")
        with open(path, 'w') as f:
            json.dump(data, f)

def get_report_state(report_id):
    if redis_client:
        raw = redis_client.get(f"report_state:{report_id}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None
    else:
        path = os.path.join(tempfile.gettempdir(), f"{report_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return None