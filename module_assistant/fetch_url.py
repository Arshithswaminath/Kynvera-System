"""
URL ingestion for the Knowledge Base.

Fetches a web page, strips it to readable text, and builds a no-LLM
extractive summary. SSRF-guarded: only public http(s) hosts are allowed.
Fails soft: raises FetchError with a human-friendly message on problems.
"""
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

from module_assistant.extract import MAX_TEXT_CHARS, _clean
from module_assistant.knowledge import _STOPWORDS

logger = logging.getLogger(__name__)

# Cap how much of the response body we read (defends against huge pages).
MAX_BYTES = 3 * 1024 * 1024  # 3 MB
REQUEST_TIMEOUT = 10  # seconds
USER_AGENT = 'KynveraAssistant/1.0 (+knowledge-base ingestion)'

# Tags whose text is noise, not content.
_DROP_TAGS = ('script', 'style', 'nav', 'footer', 'header', 'aside',
              'noscript', 'form', 'svg', 'button')


class FetchError(Exception):
    """Raised when a URL cannot be fetched or yields no usable text."""


def _is_blocked_host(hostname: str) -> bool:
    """Block loopback/private/link-local/reserved hosts to prevent SSRF."""
    if not hostname:
        return True
    host = hostname.lower().strip('.')
    if host in ('localhost', 'localhost.localdomain'):
        return True
    # Resolve to IPs; if any resolved address is private/reserved, block it.
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        # Could not resolve — treat as unreachable rather than allowing it.
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split('%')[0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    return False


def _validate_url(url: str) -> str:
    url = (url or '').strip()
    if not url:
        raise FetchError('Please provide a URL.')
    if not re.match(r'^https?://', url, re.IGNORECASE):
        # Be forgiving: default to https if the admin omitted the scheme.
        if '://' in url:
            raise FetchError('Only http and https links are supported.')
        url = 'https://' + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ('http', 'https'):
        raise FetchError('Only http and https links are supported.')
    if not parsed.hostname:
        raise FetchError('That does not look like a valid URL.')
    if _is_blocked_host(parsed.hostname):
        raise FetchError('That URL points to a private or unreachable host and was blocked.')
    return url


def _html_to_text(html: str) -> tuple:
    """Return (title, text) from raw HTML, preferring main/article content."""
    try:
        from bs4 import BeautifulSoup
    except Exception as e:  # pragma: no cover - dependency present in prod
        logger.warning('BeautifulSoup unavailable: %s', e)
        return '', _clean(re.sub(r'<[^>]+>', ' ', html or ''))

    try:
        soup = BeautifulSoup(html or '', 'lxml')
    except Exception:
        soup = BeautifulSoup(html or '', 'html.parser')

    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    for tag in soup(_DROP_TAGS):
        tag.decompose()

    main = soup.find('main') or soup.find('article')
    container = main if main is not None else (soup.body or soup)
    text = container.get_text(separator='\n') if container else ''

    # Collapse runs of blank lines / whitespace.
    lines = [ln.strip() for ln in text.splitlines()]
    text = '\n'.join(ln for ln in lines if ln)
    return title, _clean(text)


def fetch_url_text(url: str) -> tuple:
    """Fetch a URL and return (page_title, full_text). Raises FetchError."""
    import requests

    safe_url = _validate_url(url)
    try:
        resp = requests.get(
            safe_url,
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,*/*'},
            stream=True,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        raise FetchError('The site took too long to respond.')
    except requests.exceptions.RequestException as e:
        logger.info('KB link fetch failed for %s: %s', safe_url, e)
        raise FetchError('Could not reach that URL. Check the address and try again.')

    # Guard against redirect landing on a blocked host.
    final_host = urlparse(resp.url).hostname
    if _is_blocked_host(final_host):
        raise FetchError('That URL redirected to a private or unreachable host and was blocked.')

    if resp.status_code >= 400:
        raise FetchError(f'The site returned an error (HTTP {resp.status_code}).')

    ctype = (resp.headers.get('Content-Type') or '').lower()
    if ctype and 'html' not in ctype and 'text' not in ctype and 'xml' not in ctype:
        raise FetchError('That link is not a web page (only HTML/text pages can be read).')

    chunks = []
    total = 0
    try:
        for chunk in resp.iter_content(chunk_size=16384, decode_unicode=False):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= MAX_BYTES:
                break
    finally:
        resp.close()

    encoding = resp.encoding or 'utf-8'
    raw = b''.join(chunks)
    try:
        html = raw.decode(encoding, errors='ignore')
    except (LookupError, TypeError):
        html = raw.decode('utf-8', errors='ignore')

    title, text = _html_to_text(html)
    if not text:
        raise FetchError('No readable text could be extracted from that page.')
    return title, text


_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')


def summarize_extractive(text: str, max_sentences: int = 5) -> str:
    """Build a lightweight extractive summary (lead + top-scoring sentences)."""
    text = (text or '').strip()
    if not text:
        return ''

    # Sentence candidates from the first chunk of the document.
    head = text[:8000]
    raw_sentences = [s.strip() for s in _SENTENCE_SPLIT.split(head.replace('\n', ' ')) if s.strip()]
    sentences = [s for s in raw_sentences if len(s.split()) >= 4]
    if not sentences:
        return _clean(head)[:600]

    # Word-frequency scoring over non-stopword tokens.
    freq = {}
    for word in re.findall(r'[a-z0-9]+', head.lower()):
        if word in _STOPWORDS or len(word) <= 1:
            continue
        freq[word] = freq.get(word, 0) + 1
    if not freq:
        return ' '.join(sentences[:max_sentences])

    max_freq = max(freq.values())
    scored = []
    for idx, sent in enumerate(sentences):
        words = re.findall(r'[a-z0-9]+', sent.lower())
        if not words:
            continue
        score = sum(freq.get(w, 0) for w in words) / max_freq
        # Reward early sentences slightly (lead bias).
        if idx == 0:
            score *= 1.5
        score = score / (len(words) ** 0.5)  # length-normalize
        scored.append((score, idx, sent))

    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = sorted(scored[:max_sentences], key=lambda x: x[1])  # restore reading order
    summary = ' '.join(s for _, _, s in chosen).strip()

    if len(summary) > MAX_TEXT_CHARS:
        summary = summary[:MAX_TEXT_CHARS]
    return summary or _clean(head)[:600]
