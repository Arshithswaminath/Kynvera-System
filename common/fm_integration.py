"""Shared FM helpers: audit, webhooks, API-key auth."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import request, jsonify, g, current_app

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fm_log_audit(user_id, action, resource_type=None, resource_id=None, details=None):
    try:
        from app.models import db, AuditLog
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            ip_address=request.remote_addr if request else None,
            user_agent=(request.headers.get('User-Agent') if request else None),
            details=details,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as exc:
        logger.warning('FM audit log failed: %s', exc)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256((raw_key or '').encode('utf-8')).hexdigest()


def create_api_key(name: str, created_by: int = None):
    from app.models import db, IntegrationApiKey
    raw = 'inj_' + secrets.token_urlsafe(32)
    prefix = raw[:12]
    row = IntegrationApiKey(
        name=name,
        key_prefix=prefix,
        key_hash=hash_api_key(raw),
        is_active=True,
        created_by=created_by,
    )
    db.session.add(row)
    db.session.commit()
    return row, raw


def verify_api_key(raw_key: str):
    from app.models import IntegrationApiKey
    if not raw_key or not raw_key.startswith('inj_'):
        return None
    prefix = raw_key[:12]
    candidates = IntegrationApiKey.query.filter_by(key_prefix=prefix, is_active=True).all()
    digest = hash_api_key(raw_key)
    for row in candidates:
        if hmac.compare_digest(row.key_hash, digest):
            row.last_used_at = _utcnow()
            try:
                from app.models import db
                db.session.commit()
            except Exception:
                pass
            return row
    return None


def jwt_or_api_key_required(fn):
    """Allow JWT (flask-jwt-extended) OR X-API-Key header."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.headers.get('x-api-key')
        if api_key:
            row = verify_api_key(api_key.strip())
            if row:
                g.api_key = row
                g.auth_via = 'api_key'
                return fn(*args, **kwargs)
            return jsonify({'success': False, 'error': 'Invalid API key'}), 401
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        try:
            verify_jwt_in_request()
            g.auth_via = 'jwt'
            g.jwt_identity = get_jwt_identity()
        except Exception:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return fn(*args, **kwargs)
    return wrapper


def dispatch_webhooks(event: str, payload: dict):
    """Fire-and-forget POST to active outbound webhooks matching event.

    Hook rows are read on the caller's thread (which has an app context);
    only the HTTP POSTs run on the background thread.
    """
    try:
        from app.models import OutboundWebhook
        hooks = [
            {'id': h.id, 'target_url': h.target_url, 'secret': h.secret, 'events': h.events or []}
            for h in OutboundWebhook.query.filter_by(is_active=True).all()
        ]
    except Exception as exc:
        logger.warning('dispatch_webhooks query error: %s', exc)
        return
    hooks = [
        h for h in hooks
        if not h['events'] or event in h['events'] or '*' in h['events']
    ]
    if not hooks:
        return

    def _run():
        for hook in hooks:
            headers = {'Content-Type': 'application/json', 'X-Injaaz-Event': event}
            if hook['secret']:
                headers['X-Injaaz-Secret'] = hook['secret']
            body = {'event': event, 'payload': payload, 'ts': _utcnow().isoformat()}
            try:
                requests.post(hook['target_url'], json=body, headers=headers, timeout=8)
            except Exception as exc:
                logger.warning('Webhook %s failed: %s', hook['id'], exc)

    try:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
    except Exception as exc:
        logger.warning('Could not start webhook thread: %s', exc)
