"""
Keyword-based knowledge search for the Kynvera assistant (no embeddings).
Merges built-in faqs.json with admin-managed KnowledgeBaseEntry records.
"""
import json
import logging
import os
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

_FAQS_CACHE: Optional[list] = None
_DB_CACHE: Optional[list] = None

# DB (admin) knowledge wins ties against built-in FAQs.
DB_PRIORITY_BOOST = 3.0

# Minimum score before we treat a match as worth answering (avoids brand-only hits).
MIN_RELEVANCE_SCORE = 4.0

# Query tokens that are too generic to count as a "specific" intent on their own.
_GENERIC_BRAND_TOKENS = {'kynvera', 'amaan', 'application', 'platform', 'app', 'fm', 'amaanfm'}

_LINK_BODY_SEPARATOR = '--- Full page content ---'

_STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'i', 'me',
    'my', 'we', 'our', 'you', 'your', 'it', 'its', 'this', 'that', 'there',
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how', 'of',
    'at', 'by', 'for', 'with', 'about', 'into', 'through', 'during', 'to',
    'from', 'in', 'on', 'and', 'or', 'but', 'if', 'so', 'as',
}


def _faqs_path() -> str:
    return os.path.join(os.path.dirname(__file__), 'knowledge', 'faqs.json')


def load_faqs() -> list:
    global _FAQS_CACHE
    if _FAQS_CACHE is not None:
        return _FAQS_CACHE
    path = _faqs_path()
    with open(path, 'r', encoding='utf-8') as f:
        _FAQS_CACHE = json.load(f)
    return _FAQS_CACHE


def load_db_entries() -> list:
    """Load active admin knowledge records mapped to the FAQ shape. Cached."""
    global _DB_CACHE
    if _DB_CACHE is not None:
        return _DB_CACHE

    entries = []
    try:
        from app.models import KnowledgeBaseEntry
        rows = KnowledgeBaseEntry.query.filter(KnowledgeBaseEntry.is_active.is_(True)).all()
        for row in rows:
            if row.source_type == 'link':
                source_label = 'Web (link)'
                link = row.source_url or row.answer_link or None
            else:
                source_label = row.category or 'Knowledge Base'
                link = row.answer_link or None
            entries.append({
                'id': f'kb-{row.id}',
                'question': row.title,
                'answer': row.content or '',
                'keywords': row.keyword_list(),
                'tags': [row.category] if row.category else [],
                'source': source_label,
                'link': link,
                'is_db': True,
            })
    except Exception as e:
        # Table may not exist yet, or no app context — degrade gracefully.
        logger.debug('KB DB entries unavailable: %s', e)
        entries = []

    _DB_CACHE = entries
    return _DB_CACHE


def invalidate_cache():
    """Drop the cached DB knowledge records so the next search reloads them."""
    global _DB_CACHE
    _DB_CACHE = None


def _all_knowledge() -> list:
    return load_faqs() + load_db_entries()


def _tokenize(text: str) -> set:
    return {
        t for t in re.findall(r'[a-z0-9]+', (text or '').lower())
        if t not in _STOPWORDS and len(t) > 1
    }


def _excerpt(text: str, length: int = 600) -> str:
    text = (text or '').strip()
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '…'


def _token_variants(token: str) -> set:
    """Simple singular/plural so 'locations' also matches 'location'."""
    variants = {token}
    if token.endswith('ies') and len(token) > 4:
        variants.add(token[:-3] + 'y')
    elif token.endswith('s') and len(token) > 3:
        variants.add(token[:-1])
    elif not token.endswith('s'):
        variants.add(token + 's')
    return variants


def _specific_tokens(q_tokens: set) -> set:
    return {t for t in q_tokens if t not in _GENERIC_BRAND_TOKENS}


def _intent_tokens(query: str) -> set:
    """
    Recover intent from phrases stopwords would hide (e.g. 'where is' → location).
    No LLM — pattern-based only.
    """
    q = (query or '').lower()
    tokens = set()
    if re.search(r'\b(where\s+(is|are)|location|locations|located|offices?|head\s*office)\b', q):
        tokens.update({'location', 'located', 'office'})
    if re.search(r'\b(address|mailing|postal)\b', q):
        tokens.add('address')
    if re.search(r'\b(how\s+do|how\s+to|how\s+can|how\s+should)\b', q):
        tokens.update({'how', 'steps', 'guide'})
    return tokens


def _effective_specific_tokens(query: str) -> set:
    """Tokens that express what the user actually wants (not just the brand name)."""
    return _specific_tokens(_tokenize(query)) | _intent_tokens(query)


def _is_definition_faq(question: str, faq_id: str = '') -> bool:
    q = (question or '').lower()
    return faq_id == 'what_is_amaan' or q.startswith('what is ') or q.startswith("what's ")


# Detect real addresses / places in fetched page text (not the word "location" itself).
_LOCATION_CONTENT_RE = re.compile(
    r'\b('
    r'ajman|dubai|abu\s+dhabi|sharjah|ras\s+al\s+khaimah|fujairah|umm\s+al\s+quwain|'
    r'uae|u\.a\.e\.|emirates|united\s+arab\s+emirates|'
    r'p\.?\s*o\.?\s*box|po\s+box|'
    r'\d{1,4}\s+\w+\s+(street|st|road|rd|avenue|ave|lane|way|boulevard|blvd)'
    r')\b',
    re.IGNORECASE,
)


def _has_location_content(text: str) -> bool:
    return bool(_LOCATION_CONTENT_RE.search(text or ''))


def _has_location_intent(query: str) -> bool:
    return bool(_intent_tokens(query) & {'location', 'located', 'office', 'address'})


def _extract_location_snippet(text: str, max_len: int = 400) -> str:
    """Pull a tight address line from fetched page text."""
    text = (text or '').strip()
    if not text:
        return ''
    for part in re.split(r'[\n.]+', text):
        part = part.strip()
        if part and _has_location_content(part):
            return _excerpt(part, max_len)
    match = _LOCATION_CONTENT_RE.search(text)
    if match:
        start = max(0, match.start() - 60)
        end = min(len(text), match.end() + 100)
        return _excerpt(text[start:end].strip(), max_len)
    return _excerpt(text, max_len)


def _record_covers_location_intent(question: str, answer: str, keywords: list, tags: list) -> bool:
    blob = ' '.join([question, answer] + keywords + tags)
    if _has_location_content(blob):
        return True
    return any(
        _token_hits_record(tok, question, answer, keywords, tags)
        for tok in ('location', 'located', 'office', 'address')
    )


def _record_text_blob(faq: dict) -> str:
    parts = [
        faq.get('question') or '',
        faq.get('answer') or '',
        ' '.join(faq.get('keywords') or []),
        ' '.join(faq.get('tags') or []),
    ]
    return ' '.join(parts).lower()


def _token_in_text(tok: str, text: str) -> bool:
    text = (text or '').lower()
    for variant in _token_variants(tok):
        if re.search(r'\b' + re.escape(variant) + r'\b', text):
            return True
    return False


def _token_hits_record(tok: str, question: str, answer: str, keywords: list, tags: list) -> bool:
    for hay in [question, answer] + keywords + tags:
        if _token_in_text(tok, hay):
            return True
    return False


def _split_passages(text: str) -> list:
    text = (text or '').strip()
    if not text:
        return []
    if _LINK_BODY_SEPARATOR in text:
        summary, _, body = text.partition(_LINK_BODY_SEPARATOR)
        chunks = []
        if summary.strip():
            chunks.append(summary.strip())
        if body.strip():
            chunks.extend(p.strip() for p in re.split(r'\n{2,}', body) if p.strip())
        return chunks or [text]
    parts = re.split(r'\n{2,}|\.\s+', text)
    return [p.strip() for p in parts if p.strip()] or [text]


def extract_relevant_passage(query: str, text: str, max_len: int = 600) -> str:
    """Pick the passage in a long document that best matches the query (no LLM)."""
    text = (text or '').strip()
    if not text:
        return ''
    if len(text) <= max_len:
        return text

    if _has_location_intent(query):
        return _extract_location_snippet(text, max_len)

    q_tokens = _effective_specific_tokens(query) or _tokenize(query)
    if not q_tokens:
        return _excerpt(text, max_len)

    best_score = -1.0
    best_passage = ''
    for passage in _split_passages(text):
        passage_lower = passage.lower()
        score = 0.0
        for tok in q_tokens:
            if _token_in_text(tok, passage_lower):
                score += 2.0
        if score > best_score:
            best_score = score
            best_passage = passage

    if best_score > 0:
        return _excerpt(best_passage, max_len)
    return _excerpt(text, max_len)


def is_confident_match(query: str, match: Optional[dict]) -> bool:
    """True when the top match is specific enough to answer (not just a brand hit)."""
    if not match or match.get('score', 0) < MIN_RELEVANCE_SCORE:
        return False

    specific = _effective_specific_tokens(query)
    if not specific:
        return True

    full = get_faq_by_id(match.get('id', '')) or match
    blob = _record_text_blob(full)
    if _has_location_intent(query) and _has_location_content(blob):
        return True
    for tok in specific:
        if _token_in_text(tok, blob):
            return True
    return False


def search_faqs(query: str, limit: int = 2) -> List[dict]:
    """Return top knowledge matches (built-in FAQs + admin records) for a query."""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    q_lower = query.lower()
    intent = _intent_tokens(query)
    specific = _effective_specific_tokens(query)
    scored = []
    for faq in _all_knowledge():
        score = 0.0
        question = (faq.get('question') or '').lower()
        answer = (faq.get('answer') or '').lower()
        keywords = [k.lower() for k in (faq.get('keywords') or [])]
        tags = [t.lower() for t in (faq.get('tags') or [])]
        faq_id = faq.get('id') or ''

        for tok in set(q_tokens) | intent:
            if _token_in_text(tok, question):
                score += 3.0
            if _token_in_text(tok, answer):
                score += 1.5
            if any(_token_in_text(tok, k) for k in keywords):
                score += 4.0
            if any(_token_in_text(tok, t) for t in tags):
                score += 2.0

        # Reward records that cover the user's specific intent (e.g. "locations"), not just "amaan".
        for tok in specific:
            if _token_hits_record(tok, question, answer, keywords, tags):
                score += 6.0

        if q_lower in question:
            score += 8.0

        # Location questions: reward pages that contain a real address (e.g. fetched injaaz.ae link).
        if _has_location_intent(query) and _record_covers_location_intent(question, answer, keywords, tags):
            score += 14.0

        # Penalise records that miss every specific query token (e.g. generic "What is Kynvera?").
        elif specific and not any(_token_hits_record(tok, question, answer, keywords, tags) for tok in specific):
            score -= 12.0

        # "Where is Kynvera?" must not return a "What is Kynvera?" definition card.
        if intent & {'location', 'located', 'office'} and _is_definition_faq(question, faq_id):
            score -= 20.0

        if score > 0:
            if faq.get('is_db'):
                score += DB_PRIORITY_BOOST
            scored.append((score, faq))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for sc, faq in scored[:limit]:
        full_answer = faq.get('answer') or ''
        answer = (
            extract_relevant_passage(query, full_answer)
            if len(full_answer) > 700
            else _excerpt(full_answer)
        )
        results.append({
            'id': faq.get('id'),
            'question': faq.get('question'),
            'answer': answer,
            'source': faq.get('source', 'Kynvera Help'),
            'link': faq.get('link'),
            'is_db': bool(faq.get('is_db')),
            'score': sc,
        })
    return results


def get_faq_by_id(faq_id: str) -> Optional[dict]:
    for faq in _all_knowledge():
        if faq.get('id') == faq_id:
            return faq
    return None
