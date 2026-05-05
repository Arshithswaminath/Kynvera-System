"""
Redis caching utilities
"""
import logging
import json
import hashlib
from functools import wraps
from flask import current_app

logger = logging.getLogger(__name__)


def get_redis_connection():
    """
    Get Redis connection from app config
    
    Returns:
        redis.Redis instance or None if not configured
    """
    try:
        redis_url = current_app.config.get('REDIS_URL')
        if not redis_url:
            return None
        
        import redis
        return redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


def cache_key(prefix, *args, **kwargs):
    """
    Generate cache key from prefix and arguments
    
    Args:
        prefix: Cache key prefix
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key
    
    Returns:
        str: Cache key
    """
    key_parts = [prefix]
    if args:
        key_parts.append(str(hash(str(args))))
    if kwargs:
        # Sort kwargs for consistent keys
        sorted_kwargs = sorted(kwargs.items())
        key_parts.append(str(hash(str(sorted_kwargs))))
    
    key_string = ':'.join(key_parts)
    return f"injaaz:{key_string}"


def cached(ttl=3600, key_prefix='cache'):
    """
    Decorator to cache function results in Redis
    
    Args:
        ttl: Time to live in seconds (default: 1 hour)
        key_prefix: Prefix for cache key
    
    Usage:
        @cached(ttl=3600, key_prefix='dropdowns')
        def get_dropdown_data(module_type):
            # expensive operation
            return data
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            redis_conn = get_redis_connection()
            
            # If Redis not available, just call function
            if not redis_conn:
                return f(*args, **kwargs)
            
            # Generate cache key
            cache_key_str = cache_key(key_prefix, f.__name__, *args, **kwargs)
            
            # Try to get from cache
            try:
                cached_value = redis_conn.get(cache_key_str)
                if cached_value:
                    logger.debug(f"Cache hit: {cache_key_str}")
                    return json.loads(cached_value)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
            
            # Cache miss - call function
            logger.debug(f"Cache miss: {cache_key_str}")
            result = f(*args, **kwargs)
            
            # Store in cache
            try:
                redis_conn.setex(
                    cache_key_str,
                    ttl,
                    json.dumps(result, default=str)
                )
            except Exception as e:
                logger.warning(f"Cache write error: {e}")
            
            return result
        return wrapper
    return decorator


def invalidate_cache(pattern):
    """
    Invalidate cache entries matching pattern
    
    Args:
        pattern: Redis key pattern (e.g., 'injaaz:dropdowns:*')
    
    Returns:
        int: Number of keys deleted
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        return 0
    
    try:
        keys = redis_conn.keys(pattern)
        if keys:
            return redis_conn.delete(*keys)
        return 0
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")
        return 0

