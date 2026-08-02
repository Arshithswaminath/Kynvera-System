"""
Per-account login throttle (brute-force lockout).

Complements the per-IP rate limit on /login (which a distributed attacker can
sidestep by rotating IPs) with a per-username sliding window: too many failures
for one account within the window temporarily locks that account, regardless of
source IP.

Storage is in-process (thread-safe), matching how the app's Flask-Limiter falls
back to memory when REDIS_URL is unset. With multiple web workers each keeps its
own counters; a Redis-backed store would make the lockout cross-worker and is a
sensible follow-up. The lock is always time-bounded (never permanent) so a
malicious actor cannot lock a victim out indefinitely.
"""
import threading
import time

# Tuning: lock an account for LOCK_SECONDS after MAX_FAILURES failed attempts
# within WINDOW_SECONDS.
WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 10
LOCK_SECONDS = 15 * 60

_failures = {}   # key -> list[timestamp]
_locks = {}      # key -> unlock_timestamp
_mutex = threading.Lock()


def _normalize(key):
    return (key or '').strip().lower()


def seconds_locked(key):
    """Return remaining lock seconds for an account key, or 0 if not locked."""
    key = _normalize(key)
    if not key:
        return 0
    now = time.time()
    with _mutex:
        until = _locks.get(key)
        if until and until > now:
            return int(until - now) + 1
        if until:
            _locks.pop(key, None)
    return 0


def record_failure(key):
    """Record a failed login for an account key; lock it if the threshold is hit."""
    key = _normalize(key)
    if not key:
        return
    now = time.time()
    with _mutex:
        recent = [t for t in _failures.get(key, []) if t > now - WINDOW_SECONDS]
        recent.append(now)
        _failures[key] = recent
        if len(recent) >= MAX_FAILURES:
            _locks[key] = now + LOCK_SECONDS
            _failures.pop(key, None)


def clear(key):
    """Clear failures/lock for an account key after a successful login."""
    key = _normalize(key)
    if not key:
        return
    with _mutex:
        _failures.pop(key, None)
        _locks.pop(key, None)
