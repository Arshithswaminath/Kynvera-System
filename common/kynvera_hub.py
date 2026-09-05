"""Helpers for the Kynvera marketing site and product-app host split."""
from __future__ import annotations

from urllib.parse import quote, urlparse

from flask import current_app, has_request_context, request


def _cfg(key: str, default: str = "") -> str:
    try:
        return (current_app.config.get(key) or default or "").rstrip("/")
    except RuntimeError:
        return (default or "").rstrip("/")


def hub_mode() -> bool:
    return bool(current_app.config.get("KYNVERA_HUB_MODE"))


def marketing_only() -> bool:
    """True on the kynvera-marketing deploy (kynvera.net landing site)."""
    try:
        return bool(current_app.config.get("KYNVERA_MARKETING_ONLY"))
    except RuntimeError:
        return False


def request_hostname() -> str:
    if not has_request_context():
        return ""
    return (request.host or "").split(":")[0].lower()


def is_local_hostname(host: str) -> bool:
    h = (host or "").lower()
    return h in ("localhost", "127.0.0.1", "::1") or h.endswith(".local")


def marketing_hosts() -> set[str]:
    raw = _cfg("KYNVERA_MARKETING_HOSTS", "kynvera.net,www.kynvera.net")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_marketing_host(host: str | None = None) -> bool:
    """True on kynvera.net / www — the public marketing site."""
    if marketing_only():
        return True
    return (host or request_hostname()) in marketing_hosts()


def is_operations_host(host: str | None = None) -> bool:
    """True on operations.kynvera.net (and any non-marketing, non-local host).

    Localhost stays a combined preview: landing at / and the app at /login.
    """
    h = (host or request_hostname()).lower()
    if not h or is_local_hostname(h):
        return False
    return h not in marketing_hosts()


def marketing_url() -> str:
    return _cfg("KYNVERA_HOME_URL") or "https://kynvera.net"


def operations_url() -> str:
    return _cfg("APP_BASE_URL") or "https://operations.kynvera.net"


def operations_login_url() -> str:
    return operations_url().rstrip("/") + "/login"


def staff_login_url() -> str:
    """Sign-in href: absolute product URL on the marketing site, /login on operations."""
    if marketing_only() or is_marketing_host():
        return operations_login_url()
    return "/login"


def staff_forgot_url() -> str:
    if marketing_only() or is_marketing_host():
        return operations_url().rstrip("/") + "/forgot-password"
    return "/forgot-password"


def auth_home_url() -> str:
    """Back-to-home from login: the landing on this host."""
    return "/"


def home_url() -> str:
    """In-app 'Kynvera Home' — the public marketing site, not this product host."""
    if hub_mode():
        return _cfg("KYNVERA_HOME_URL") or marketing_url()
    return marketing_url()


def fire_app_url() -> str:
    return _cfg("KYNVERA_FIRE_APP_URL")


def municipality_app_url() -> str:
    return _cfg("KYNVERA_MUNICIPALITY_APP_URL")


def app_name() -> str:
    """Product display name for this deployment (shown under the mobile menu bar)."""
    try:
        name = (current_app.config.get("KYNVERA_APP_NAME") or "").strip()
    except RuntimeError:
        name = ""
    return name or "Kynvera"


def sanitize_next_path(next_path: str | None, default: str = "/dashboard") -> str:
    """Allow only same-origin relative paths (no scheme, no //open-redirect)."""
    raw = (next_path or "").strip() or default
    if not raw.startswith("/") or raw.startswith("//"):
        return default
    if "\\" in raw or ":" in raw.split("?", 1)[0]:
        return default
    return raw


def build_sso_launch_url(app_base_url: str, access_token: str, next_path: str = "/dashboard") -> str:
    """Build product-app SSO consume URL with token handoff."""
    base = (app_base_url or "").rstrip("/")
    if not base:
        return ""
    safe_next = sanitize_next_path(next_path)
    return f"{base}/sso/consume?token={quote(access_token, safe='')}&next={quote(safe_next, safe='/?&=')}"


def hub_public_config() -> dict:
    return {
        "hub_mode": hub_mode(),
        "home_url": home_url(),
        "fire_app_url": fire_app_url(),
        "municipality_app_url": municipality_app_url(),
        "app_name": app_name(),
    }


def is_safe_external_base(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
