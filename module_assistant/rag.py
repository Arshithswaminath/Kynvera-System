"""
Retrieve knowledge-base context for LLM-powered assistant replies.
"""
from module_assistant.knowledge import extract_relevant_passage, search_faqs


def retrieve_context(query: str, limit: int = 3) -> list:
    """Top knowledge chunks with enough text for the LLM to reason over."""
    matches = search_faqs(query, limit=limit)
    chunks = []
    for m in matches:
        body = (m.get('answer') or '').strip()
        if len(body) > 500:
            body = extract_relevant_passage(query, body, max_len=600)
        chunks.append({
            'id': m.get('id'),
            'title': m.get('question') or 'Knowledge',
            'source': m.get('source') or 'Injaaz Help',
            'link': m.get('link'),
            'text': body,
            'score': m.get('score', 0),
        })
    return chunks
