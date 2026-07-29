"""
Optional LLM backend for natural Injaaz assistant replies (RAG over knowledge base).

Providers:
  - claude  (default) — Anthropic API, claude-haiku-4-5 recommended
  - openai            — OpenAI or any OpenAI-compatible endpoint

Also exposes generate_structured() for FM triage / prediction JSON calls.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

_claude_client = None
_openai_client = None


class StructuredLLMError(Exception):
    """Raised when a structured LLM call fails or returns invalid JSON."""

SYSTEM_PROMPT = """You are the Injaaz Assistant — a helpful, natural chat guide for the Injaaz FM platform and company.

Rules:
- Answer in a friendly, conversational tone (2–5 short paragraphs max unless listing steps).
- Use ONLY facts from the provided Context for company info, policies, locations, and services.
- "User account data" contains live, accurate facts about the signed-in user (their profile, module access, forms, leave, tickets). Use it confidently to answer personal questions like "what modules do I have access to?", "how many forms have I submitted?", or "when was my last leave?" — never say you lack visibility into their account.
- For Injaaz Application how-to (forms, modules, workflow), use Context first; you may add brief general guidance if Context is thin.
- If neither Context nor the account data contains the answer, say honestly that you do not have that information yet and suggest raising a ticket or asking an administrator.
- Never invent addresses, phone numbers, policies, or URLs not supported by Context.
- Do not mention "Context", "knowledge base", "account data", or "LLM" to the user.
- Write in plain text only — no markdown symbols like ** or ##. Use simple dashes for lists.
- Keep answers concise and practical."""


def _build_user_content(message: str, context_chunks: list, user_name: str, account_context: str = '') -> str:
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

    account_block = (
        f"User account data (live, accurate — scoped to the signed-in user):\n{account_context}\n\n"
        if account_context else ''
    )

    return (
        f"User name: {user_name}\n\n"
        f"{account_block}"
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
        max_tokens=600,
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
        max_tokens=600,
        temperature=0.3,
    )
    return (response.choices[0].message.content or '').strip()


def generate_reply(message: str, context_chunks: list, user_name: str = 'there', account_context: str = '') -> str:
    """Return a natural-language reply, or '' if the LLM is unavailable."""
    user_content = _build_user_content(message, context_chunks, user_name, account_context)
    try:
        if _provider() == 'openai':
            return _generate_openai(user_content)
        return _generate_claude(user_content)
    except Exception as e:
        logger.error('Assistant LLM call failed: %s', e, exc_info=True)
        return ''


def _strip_json_fences(text: str) -> str:
    text = (text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def _validate_against_schema(data: dict, schema: dict) -> dict:
    """Lightweight required-key + type checks. schema keys map to expected Python types or tuples."""
    if not isinstance(data, dict):
        raise StructuredLLMError('Response is not a JSON object')
    required = schema.get('required') or []
    properties = schema.get('properties') or schema
    # Support both {"required": [...], "properties": {...}} and flat {key: type}
    if 'properties' not in schema and 'required' not in schema:
        properties = schema
        required = list(schema.keys())
    for key in required:
        if key not in data:
            raise StructuredLLMError(f'Missing required key: {key}')
    for key, expected in properties.items():
        if key not in data:
            continue
        value = data[key]
        if expected is None:
            continue
        if isinstance(expected, tuple):
            if not isinstance(value, expected) and not (value is None and type(None) in expected):
                raise StructuredLLMError(f'Key {key} has wrong type')
        elif expected is list:
            if not isinstance(value, list):
                raise StructuredLLMError(f'Key {key} must be a list')
        elif expected is dict:
            if not isinstance(value, dict):
                raise StructuredLLMError(f'Key {key} must be an object')
        elif expected in (str, int, float, bool):
            if expected is float and isinstance(value, int):
                data[key] = float(value)
            elif not isinstance(value, expected) and value is not None:
                # Allow int for numeric fields that came as strings
                if expected is int and isinstance(value, str) and value.isdigit():
                    data[key] = int(value)
                elif expected is float and isinstance(value, str):
                    try:
                        data[key] = float(value)
                    except ValueError as exc:
                        raise StructuredLLMError(f'Key {key} must be {expected.__name__}') from exc
                else:
                    raise StructuredLLMError(f'Key {key} must be {expected.__name__}')
    return data


def _raw_completion(system_prompt: str, user_content: str, model: str = None, max_tokens: int = 1200) -> str:
    from flask import current_app
    model = model or current_app.config.get('ASSISTANT_LLM_MODEL') or (
        'claude-haiku-4-5' if _provider() != 'openai' else 'gpt-4o-mini'
    )
    if _provider() == 'openai':
        client = _get_openai_client()
        if not client:
            raise StructuredLLMError('OpenAI client unavailable')
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content},
            ],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return (response.choices[0].message.content or '').strip()

    client = _get_claude_client()
    if not client:
        raise StructuredLLMError('Claude client unavailable — check ANTHROPIC_API_KEY')
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_content}],
        temperature=0.1,
    )
    parts = []
    for block in response.content:
        if getattr(block, 'type', None) == 'text':
            parts.append(block.text)
    return ''.join(parts).strip()


def generate_structured(system_prompt: str, user_content: str, schema: dict, model: str = None) -> dict:
    """Call the configured LLM and parse a strict-JSON response validated against schema.

    Raises StructuredLLMError on unavailable client, malformed JSON, or schema mismatch.
    """
    if not is_llm_enabled():
        raise StructuredLLMError('LLM is disabled')

    full_system = (
        (system_prompt or '').strip()
        + '\n\nYou MUST respond with ONLY valid JSON. No prose, no markdown fences, no commentary.'
    )
    try:
        raw = _raw_completion(full_system, user_content, model=model)
    except StructuredLLMError:
        raise
    except Exception as exc:
        logger.error('Structured LLM call failed: %s', exc, exc_info=True)
        raise StructuredLLMError(str(exc)) from exc

    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Try to extract first {...} block
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if not match:
            raise StructuredLLMError(f'Invalid JSON from LLM: {exc}') from exc
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc2:
            raise StructuredLLMError(f'Invalid JSON from LLM: {exc2}') from exc2

    return _validate_against_schema(data, schema)
