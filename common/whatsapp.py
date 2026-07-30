"""WhatsApp notification helper (Civil Defense reminders).

Env:
  WHATSAPP_ENABLED=1
  WHATSAPP_API_URL=...
  WHATSAPP_API_TOKEN=...
  WHATSAPP_FROM=...  (optional)
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)


def is_whatsapp_configured() -> bool:
    if str(os.environ.get('WHATSAPP_ENABLED', '')).strip().lower() not in ('1', 'true', 'yes'):
        return False
    return bool(os.environ.get('WHATSAPP_API_URL') and os.environ.get('WHATSAPP_API_TOKEN'))


def send_whatsapp_message(to_numbers: Iterable[str], body: str) -> dict:
    numbers = []
    for raw in to_numbers or []:
        n = str(raw or '').strip()
        if n:
            numbers.append(n)
    if not numbers:
        return {'sent': 0, 'failed': 0, 'skipped': True, 'detail': 'no recipients'}
    if not is_whatsapp_configured():
        logger.info(
            'WhatsApp skipped (not configured): %s recipients — %s',
            len(numbers), (body or '')[:120],
        )
        return {'sent': 0, 'failed': 0, 'skipped': True, 'detail': 'whatsapp not configured'}

    try:
        import requests
    except ImportError:
        return {'sent': 0, 'failed': len(numbers), 'skipped': True, 'detail': 'requests missing'}

    url = os.environ['WHATSAPP_API_URL'].rstrip('/')
    token = os.environ['WHATSAPP_API_TOKEN']
    from_id = os.environ.get('WHATSAPP_FROM') or ''
    sent = failed = 0
    for num in numbers:
        try:
            resp = requests.post(
                url,
                json={'to': num, 'body': body, 'from': from_id},
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                timeout=20,
            )
            if 200 <= resp.status_code < 300:
                sent += 1
            else:
                failed += 1
                logger.warning('WhatsApp send failed %s → %s', num, resp.status_code)
        except Exception as exc:
            failed += 1
            logger.warning('WhatsApp send error to %s: %s', num, exc)
    return {'sent': sent, 'failed': failed, 'skipped': False, 'detail': 'ok'}
