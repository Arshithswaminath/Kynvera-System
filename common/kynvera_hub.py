"""Helpers for the Kynvera hub portal and product-app SSO handoff."""
from __future__ import annotations

from urllib.parse import quote, urlparse

from flask import current_app


def _cfg(key: str, default: str = "") -> str:
    try:
        return (current_app.config.get(key) or default or "").rstrip("/")
    except RuntimeError:
        return (default or "").rstrip("/")


def hub_mode() -> bool:
    return bool(current_app.config.get("KYNVERA_HUB_MODE"))


def home_url() -> str:
    return _cfg("KYNVERA_HOME_URL")


def fire_app_url() -> str:
    return _cfg("KYNVERA_FIRE_APP_URL")


def municipality_app_url() -> str:
    return _cfg("KYNVERA_MUNICIPALITY_APP_URL")


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
    }


def is_safe_external_base(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
