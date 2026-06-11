"""
Retrieve knowledge-base context for LLM-powered assistant replies.

Sources fed to the LLM:
  1. Built-in FAQs + admin knowledge records (text, uploaded docs, fetched links)
  2. Published DocHub documents the user can access
  3. Fallback digest of everything admins have shared, so the model always
     knows what knowledge exists even when keyword matching misses.
"""
import logging
import re

from module_assistant.knowledge import (
    extract_relevant_passage,
    get_faq_by_id,
    load_db_entries,
    search_faqs,
)

logger = logging.getLogger(__name__)

# How much text per chunk the LLM gets (chars).
MAX_CHUNK_LEN = 1200
DIGEST_CHUNK_LEN = 400


def _excerpt(text: str, length: int) -> str:
    text = (text or '').strip()
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '…'


def _kb_chunks(query: str, limit: int) -> list:
    """Top knowledge matches with full-length passages (not card-sized excerpts)."""
    matches = search_faqs(query, limit=limit)
    chunks = []
    for m in matches:
        full = get_faq_by_id(m.get('id') or '') or {}
        body = (full.get('answer') or m.get('answer') or '').strip()
        if len(body) > MAX_CHUNK_LEN:
            body = extract_relevant_passage(query, body, max_len=MAX_CHUNK_LEN)
        chunks.append({
            'id': m.get('id'),
            'title': m.get('question') or 'Knowledge',
            'source': m.get('source') or 'Injaaz Help',
            'link': m.get('link'),
            'text': body,
            'score': m.get('score', 0),
        })
    return chunks


def _dochub_chunks(query: str, user, limit: int = 2) -> list:
    """Published DocHub documents matching the query, scoped to the user's access."""
    if user is None:
        return []
    try:
        from sqlalchemy import or_

        from app.models import DocHubDocument
        from module_assistant.tools import _has_dochub_access, _score_document

        if not _has_dochub_access(user):
            return []

        docs = (
            DocHubDocument.query.filter(
                DocHubDocument.status == 'published',
                or_(DocHubDocument.inline_asset.is_(False), DocHubDocument.inline_asset.is_(None)),
            ).all()
        )
        scored = []
        for doc in docs:
            sc = _score_document(doc, query)
            if sc >= 3.0:
                scored.append((sc, doc))
        scored.sort(key=lambda x: x[0], reverse=True)

        chunks = []
        for sc, doc in scored[:limit]:
            text = re.sub(r'<[^>]+>', ' ', doc.content or '')
            text = re.sub(r'\s+', ' ', text).strip()
            if not text:
                continue
            if len(text) > MAX_CHUNK_LEN:
                text = extract_relevant_passage(query, text, max_len=MAX_CHUNK_LEN)
            chunks.append({
                'id': f'doc-{doc.id}',
                'title': doc.title,
                'source': f"DocHub — {doc.category or 'Internal'}",
                'link': f'/api/docs/{doc.id}/preview',
                'text': text,
                'score': sc,
            })
        return chunks
    except Exception as e:
        logger.debug('DocHub context unavailable: %s', e)
        return []


def _knowledge_digest(limit: int = 6) -> list:
    """
    Compact digest of admin-shared knowledge (records, uploads, links).
    Used when keyword matching finds nothing, so the LLM still sees what
    has been shared instead of answering blind.
    """
    chunks = []
    try:
        for e in load_db_entries()[:limit]:
            body = (e.get('answer') or '').strip()
            if not body:
                continue
            chunks.append({
                'id': e.get('id'),
                'title': e.get('question') or 'Knowledge',
                'source': e.get('source') or 'Knowledge Base',
                'link': e.get('link'),
                'text': _excerpt(body, DIGEST_CHUNK_LEN),
                'score': 0,
            })
    except Exception as e:
        logger.debug('Knowledge digest unavailable: %s', e)
    return chunks


def retrieve_context(query: str, limit: int = 4, user=None) -> list:
    """All relevant context for the LLM: knowledge records, links, and DocHub docs."""
    chunks = _kb_chunks(query, limit=limit)
    chunks.extend(_dochub_chunks(query, user, limit=2))

    if not chunks:
        chunks = _knowledge_digest()

    return chunks
