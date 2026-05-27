import os
import logging
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
import redis
from rq import Queue
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
jwt = JWTManager()

def init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    jwt.init_app(app)

    # Optionally log redis availability on startup
    try:
        conn = get_redis_conn(app)
        if conn:
            logger.info("Redis available at app startup.")
    except Exception:
        logger.exception("Error while initializing Redis at startup.")

# Lazy Redis getter
def get_redis_conn(app=None):
    redis_url = None
    if app:
        redis_url = app.config.get('REDIS_URL')
    if not redis_url:
        redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        return None
    try:
        conn = redis.from_url(redis_url, decode_responses=True)
        conn.ping()
        return conn
    except RedisError:
        logger.exception("Failed to connect to Redis")
        return None
    except Exception:
        logger.exception("Unexpected error connecting to Redis")
        return None

# Lazy RQ Queue getter
def get_rq_queue(app=None):
    if app:
        redis_url = app.config.get('REDIS_URL')
    else:
        redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        return None
    try:
        conn = redis.from_url(redis_url, decode_responses=True)
        q = Queue('default', connection=conn)
        return q
    except Exception:
        logger.exception("Failed to create RQ queue")
        return None