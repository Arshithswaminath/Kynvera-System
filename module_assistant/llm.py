"""
Optional LLM backend for natural Injaaz assistant replies (RAG over knowledge base).

Providers:
  - claude  (default) — Anthropic API, claude-haiku-4-5 recommended
  - openai            — OpenAI or any OpenAI-compatible endpoint
"""
import logging

logger = logging.getLogger(__name__)

_claude_client = None
_openai_client = None

SYSTEM_PROMPT = """You are the Injaaz Assistant — a helpful, natural chat guide for the Injaaz FM platform and company.

Rules:
- Answer in a friendly, conversational tone (2–5 short paragraphs max unless listing steps).
- Use ONLY facts from the provided Context for company info, policies, locations, and services.
- For Injaaz Application how-to (forms, modules, workflow), use Context first; you may add brief general guidance if Context is thin.
- If Context does not contain the answer, say honestly that you do not have that information yet and suggest raising a ticket or asking an administrator to add it to the knowledge base.
- Never invent addresses, phone numbers, policies, or URLs not supported by Context.
- Do not mention "Context", "knowledge base", or "LLM" to the user.
- Keep answers concise and practical."""


def _build_user_content(message: str, context_chunks: list, user_name: str) -> str:
    if context_chunks:
        parts = []
        for i, c in enumerate(context_chunks, 1):
            title = c.get('title') or f'Source {i}'
            source = c.get('source') or 'Injaaz'
            text = (c.get('text') or '').strip()
            if text:
                parts.append(f'[{title}] ({source})\n{text}')
        context_block = '\n\n---\n\n'.join(parts)
    else:
        context_block = (
            '(No matching knowledge records — answer generally about Injaaz Application '
            'modules or say you need more info.)'
        )

    return (
        f"User name: {user_name}\n\n"
        f"Context:\n{context_block}\n\n"
        f"User message: {message}"
    )


def is_llm_enabled() -> bool:
    try:
        from flask import current_app
        return bool(current_app.config.get('ASSISTANT_LLM_ENABLED'))
    except Exception:
        return False


def _provider() -> str:
    from flask import current_app
    return (current_app.config.get('ASSISTANT_LLM_PROVIDER') or 'claude').strip().lower()


def _get_claude_client():
    global _claude_client
    from flask import current_app
    try:
        import anthropic
    except ImportError:
        return None

    api_key = (current_app.config.get('ANTHROPIC_API_KEY') or '').strip()
    if not api_key:
        return None
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=api_key)
    return _claude_client


def _generate_claude(user_content: str) -> str:
    from flask import current_app
    client = _get_claude_client()
    if not client:
        logger.warning('anthropic package not installed or API key missing')
        return ''

    model = current_app.config.get('ASSISTANT_LLM_MODEL', 'claude-haiku-4-5')
    response = client.messages.create(
        model=model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_content}],
        temperature=0.3,
    )
    parts = []
    for block in response.content:
        if getattr(block, 'type', None) == 'text':
            parts.append(block.text)
    return ''.join(parts).strip()


def _get_openai_client():
    global _openai_client
    from flask import current_app
    try:
        from openai import OpenAI
    except ImportError:
        return None

    api_key = (current_app.config.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return None
    if _openai_client is None:
        base_url = (current_app.config.get('ASSISTANT_LLM_BASE_URL') or '').strip() or None
        _openai_client = OpenAI(api_key=api_key, base_url=base_url)
    return _openai_client


def _generate_openai(user_content: str) -> str:
    from flask import current_app
    client = _get_openai_client()
    if not client:
        logger.warning('openai package not installed or API key missing')
        return ''

    model = current_app.config.get('ASSISTANT_LLM_MODEL', 'gpt-4o-mini')
    response = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content},
        ],
        max_tokens=400,
        temperature=0.3,
    )
    return (response.choices[0].message.content or '').strip()


def generate_reply(message: str, context_chunks: list, user_name: str = 'there') -> str:
    """Return a natural-language reply, or '' if the LLM is unavailable."""
    user_content = _build_user_content(message, context_chunks, user_name)
    try:
        if _provider() == 'openai':
            return _generate_openai(user_content)
        return _generate_claude(user_content)
    except Exception as e:
        logger.error('Assistant LLM call failed: %s', e, exc_info=True)
        return ''
