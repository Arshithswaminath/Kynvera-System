#!/usr/bin/env python3
"""Desktop marketing screenshots for mockups and social posts.

Requires the app on http://127.0.0.1:5002 and Playwright Chromium.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "screenshots" / "marketing_desktop"
BASE = "http://127.0.0.1:5002"
USER = "Kynvera"
PASS = "Arshith&Taha@2026"
W, H = 1440, 900
SCALE = 2
NAV_MS = 30_000

PUBLIC = [
    ("01_landing_hero", "/", "viewport"),
    ("02_landing_platform", "/", "section:#platform"),
    ("03_landing_modules", "/", "section:#modules"),
    ("04_landing_footer", "/", "footer"),
    ("05_landing_full", "/", "full"),
    ("06_login", "/login", "viewport"),
]

APP = [
    ("10_dashboard", "/dashboard"),
    ("11_hr", "/hr/"),
    ("12_tickets", "/tickets/"),
    ("13_fm_assets", "/assets/"),
    ("14_procurement", "/procurement/"),
    ("15_procurement_catalog", "/procurement/catalog/Electrical"),
    ("16_purchase_requests", "/procurement/purchase-requests"),
    ("17_inspection", "/inspection/"),
    ("18_qhsi", "/qhsi/"),
    ("19_files", "/files/"),
    ("20_dochub", "/dochub"),
    ("21_mmr", "/admin/mmr/"),
    ("22_automations", "/automations/"),
    ("23_admin", "/admin/dashboard"),
    ("24_manpower", "/hr/manpower-tracker"),
    ("25_pending_reviews", "/workflow/pending-reviews"),
    ("26_bd", "/admin/bd"),
]

HIDE_JS = """() => {
  const sels = [
    '.injaaz-assistant', '#assistantFab', '#injaazAssistant', '#assistantPanel',
    '.notification-badge', '#navNotifBadge', '.nav-notif-badge',
    '#pwa-install-btn', '.pwa-install-slot',
  ];
  for (const s of sels) {
    document.querySelectorAll(s).forEach((el) => {
      el.style.setProperty('display', 'none', 'important');
      el.setAttribute('hidden', '');
    });
  }
}"""

SETTLE_JS = """async () => {
  if (document.fonts && document.fonts.ready) {
    try { await document.fonts.ready; } catch (e) {}
  }
  const imgs = Array.from(document.images || []);
  await Promise.all(imgs.map((img) => {
    if (img.complete) return Promise.resolve();
    return new Promise((res) => {
      img.addEventListener('load', res, { once: true });
      img.addEventListener('error', res, { once: true });
      setTimeout(res, 2500);
    });
  }));
}"""


def shot_path(name: str) -> Path:
    return OUT / f"{name}.png"


def settle(page) -> None:
    page.wait_for_timeout(500)
    page.evaluate(SETTLE_JS)
    page.evaluate(HIDE_JS)
    page.wait_for_timeout(250)


def capture_landing_kind(page, kind: str, dest: Path) -> None:
    page.goto(f"{BASE}/", wait_until="load", timeout=NAV_MS)
    settle(page)
    if kind == "viewport":
        page.screenshot(path=str(dest), full_page=False)
        return
    if kind == "full":
        page.screenshot(path=str(dest), full_page=True)
        return
    if kind == "footer":
        loc = page.locator(".lp-footer")
        loc.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        page.evaluate(SETTLE_JS)
        loc.screenshot(path=str(dest))
        return
    if kind.startswith("section:"):
        sel = kind.split(":", 1)[1]
        loc = page.locator(sel).first
        loc.scroll_into_view_if_needed()
        page.wait_for_timeout(350)
        loc.screenshot(path=str(dest))
        return
    page.screenshot(path=str(dest), full_page=False)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    skipped: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=SCALE,
            color_scheme="light",
        )
        page = context.new_page()

        for name, path, kind in PUBLIC:
            dest = shot_path(name)
            try:
                if path == "/":
                    capture_landing_kind(page, kind, dest)
                else:
                    page.goto(f"{BASE}{path}", wait_until="load", timeout=NAV_MS)
                    settle(page)
                    page.screenshot(path=str(dest), full_page=False)
                saved.append(dest.name)
                print("saved", dest.name)
            except Exception as exc:
                skipped.append(f"{name}: {exc}")
                print("skip", name, exc)

        page.goto(f"{BASE}/login", wait_until="load", timeout=NAV_MS)
        page.fill("#username", USER)
        page.fill("#password", PASS)
        page.click("#login-btn")
        page.wait_for_url(re.compile(r".*/dashboard.*"), timeout=NAV_MS)
        page.wait_for_load_state("load")
        settle(page)

        for name, path in APP:
            dest = shot_path(name)
            try:
                page.goto(f"{BASE}{path}", wait_until="load", timeout=NAV_MS)
                settle(page)
                page.screenshot(path=str(dest), full_page=False)
                saved.append(dest.name)
                print("saved", dest.name)
            except PlaywrightTimeout as exc:
                skipped.append(f"{name}: timeout {exc}")
                print("skip", name, "timeout")
            except Exception as exc:
                skipped.append(f"{name}: {exc}")
                print("skip", name, exc)

        browser.close()

    print(f"\n{len(saved)} files in {OUT}")
    if skipped:
        print("skipped:", *skipped, sep="\n  ")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
