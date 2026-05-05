#!/usr/bin/env python3
"""
Capture screenshots for Injaaz HTML routes.

Two modes:
  --segmented (default): fixed viewport, scroll down step-by-step, one PNG per viewport
                       (better on Windows than a single ultra-tall full_page PNG).
  --full-page:         one Playwright full_page screenshot per URL.

Prerequisites:
    pip install playwright
    playwright install chromium

Usage (app must be running, e.g. python Injaaz.py):

    python scripts/capture_full_page_screenshots.py \\
        --base-url http://127.0.0.1:5000 \\
        --stamp my_run \\
        --login-user admin --login-password 'Admin@123'
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.getLogger().setLevel(logging.WARNING)

SKIP_PATH_SUBSTRINGS = (
    "/api/auth",
    "/api/admin",
    "/api/docs",
    "/api/reports",
    "/hr/api/",
    "/admin/mmr/api/",
    "/procurement/api/",
    "/health",
    "/manifest.json",
    "/favicon.ico",
)
SKIP_SUFFIXES = ("/dropdowns",)
SKIP_EXACT = {
    "/bd/email-module/attachments",
}

SKIP_ENDPOINT_PREFIXES = (
    "static",
)


def _should_capture_path(path: str) -> bool:
    if path in SKIP_EXACT:
        return False
    if path.startswith("/api/workflow/"):
        return path in ("/api/workflow/dashboard", "/api/workflow/history")
    p = path.lower()
    for s in SKIP_PATH_SUBSTRINGS:
        if s in p:
            return False
    for s in SKIP_SUFFIXES:
        if p.endswith(s):
            return False
    return True


def collect_paths(app) -> list[tuple[str, str]]:
    from flask import url_for

    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    with app.app_context():
        with app.test_request_context("/"):
            for rule in app.url_map.iter_rules():
                if "GET" not in rule.methods:
                    continue
                ep = rule.endpoint or ""
                if ep.startswith(SKIP_ENDPOINT_PREFIXES):
                    continue
                if rule.endpoint == "static":
                    continue

                args = set(rule.arguments)
                defaults = dict(rule.defaults or {})
                required = args - set(defaults.keys())
                if required:
                    continue

                try:
                    path = url_for(rule.endpoint, **defaults)
                except Exception:
                    continue

                if not path.startswith("/"):
                    continue
                if not _should_capture_path(path):
                    continue

                norm = path.rstrip("/") or "/"
                if norm in seen:
                    continue
                seen.add(norm)
                out.append((rule.endpoint, path))

    out.sort(key=lambda x: x[1])
    # Capture /logout last so it does not clear auth for other pages (if it clears storage)
    logout = [t for t in out if t[1] == "/logout"]
    rest = [t for t in out if t[1] != "/logout"]
    return rest + logout


def path_to_basename(path: str) -> str:
    base = path.strip("/") or "index"
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", base.replace("/", "__"))
    if len(safe) > 160:
        safe = safe[:160]
    return safe


def login_playwright(page, base: str, username: str, password: str, timeout_ms: int) -> None:
    """Log in via the real login form so localStorage gets access/refresh tokens."""
    page.goto(f"{base}/login", wait_until="load", timeout=timeout_ms)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#login-btn")
    # Login script waits ~1s before redirect
    page.wait_for_url(re.compile(r".*/dashboard.*"), timeout=timeout_ms)
    page.wait_for_load_state("load")


def capture_segmented(
    page,
    out_dir: Path,
    basename: str,
    wait_ms: int,
) -> int:
    """
    Scroll by viewport height; save viewport-sized PNGs: {basename}_seg000.png, ...
    Returns number of segments written.
    """
    page.wait_for_timeout(wait_ms)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(200)

    vh = page.evaluate(
        "() => window.innerHeight || document.documentElement.clientHeight || 800"
    )
    total = page.evaluate(
        """() => Math.max(
            document.body ? document.body.scrollHeight : 0,
            document.documentElement.scrollHeight,
            document.body ? document.body.offsetHeight : 0
        )"""
    )
    vh = max(int(vh), 400)
    total = max(int(total), 1)

    n = 0
    y = 0
    while True:
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(350)
        seg_path = out_dir / f"{basename}_seg{n:03d}.png"
        page.screenshot(path=str(seg_path), full_page=False)
        n += 1
        if y + vh >= total:
            break
        y += vh

    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshots of Injaaz routes (segmented or full-page).")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="App base URL (no trailing slash)")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "screenshots" / "full_pages",
        help="Output root; a subfolder is created per --stamp",
    )
    parser.add_argument("--stamp", default=None, help="Subfolder name (default: UTC timestamp)")
    parser.add_argument(
        "--viewport",
        default="1280x800",
        help="WxH viewport for segmented mode (default desktop 1280x800)",
    )
    parser.add_argument(
        "--full-page",
        action="store_true",
        help="One tall PNG per URL (Playwright full_page). Default is scroll segments.",
    )
    parser.add_argument("--login-user", default="admin", help="Username for /login")
    parser.add_argument("--login-password", default="Admin@123", help="Password for /login")
    parser.add_argument("--no-login", action="store_true", help="Do not log in (public pages only)")
    parser.add_argument("--storage-state", type=Path, default=None, help="Optional Playwright storage JSON")
    parser.add_argument("--wait-ms", type=int, default=1200, help="Wait after load before measuring/screenshot")
    parser.add_argument("--timeout-ms", type=int, default=120_000, help="Navigation timeout")
    parser.add_argument("--dry-run", action="store_true", help="List URLs only")
    args = parser.parse_args()

    segmented = not args.full_page

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Install: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    from Injaaz import create_app

    app = create_app()
    routes = collect_paths(app)

    stamp = args.stamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_root: Path = args.out_dir / stamp
    out_root.mkdir(parents=True, exist_ok=True)

    vw, vh = 1280, 800
    if "x" in args.viewport.lower():
        parts = args.viewport.lower().split("x", 1)
        vw, vh = int(parts[0]), int(parts[1])

    out_root.joinpath("_urls.txt").write_text(
        "\n".join(f"{path}\t{ep}" for ep, path in routes) + "\n",
        encoding="utf-8",
    )
    meta = out_root / "_capture_mode.txt"
    meta.write_text(
        f"segmented={segmented}\nviewport={vw}x{vh}\nlogin={not args.no_login}\n",
        encoding="utf-8",
    )

    print(f"Routes: {len(routes)} | Output: {out_root} | mode={'segmented' if segmented else 'full_page'}")
    if args.dry_run:
        for ep, path in routes:
            print(f"  {path}  ({ep})")
        return 0

    base = args.base_url.rstrip("/")
    failures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context_kwargs: dict = {
            "viewport": {"width": vw, "height": vh},
            "device_scale_factor": 1,
        }
        if args.storage_state and args.storage_state.is_file():
            context_kwargs["storage_state"] = str(args.storage_state)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        if not args.no_login:
            try:
                login_playwright(page, base, args.login_user, args.login_password, args.timeout_ms)
                print(f"Logged in as {args.login_user!r}")
            except Exception as e:
                print(f"Login failed: {e}", file=sys.stderr)
                context.close()
                browser.close()
                return 3

        for ep, path in routes:
            url = f"{base}{path}"
            basename = path_to_basename(path)
            try:
                page.goto(url, wait_until="load", timeout=args.timeout_ms)
                if segmented:
                    n = capture_segmented(page, out_root, basename, args.wait_ms)
                    print(f"OK  {path} -> {basename}_seg000..seg{n-1:03d}.png ({n} segments)")
                else:
                    target = out_root / f"{basename}.png"
                    page.wait_for_timeout(args.wait_ms)
                    page.screenshot(path=str(target), full_page=True)
                    print(f"OK  {path} -> {basename}.png")
            except Exception as e:
                print(f"ERR {path}: {e}", file=sys.stderr)
                failures.append((path, str(e)))

        context.close()
        browser.close()

    if failures:
        (out_root / "_failures.txt").write_text(
            "\n".join(f"{p}\t{e}" for p, e in failures) + "\n",
            encoding="utf-8",
        )
        print(f"Failures: {len(failures)}")
        return 2

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
