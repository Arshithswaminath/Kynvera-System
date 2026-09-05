#!/usr/bin/env python3
"""Build standalone HTML cards and PNG screenshots for every confirmation prompt.

Reads docs/confirmation-prompts/catalog.json and writes one HTML file + PNG
per prompt, plus an index gallery.

Usage:
  ./venv/bin/python scripts/build_confirmation_prompt_catalog.py
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "docs" / "confirmation-prompts"
CATALOG_PATH = CATALOG_DIR / "catalog.json"

MODULE_LABELS = {
    "admin": "Admin",
    "dashboard": "Dashboard",
    "pwa": "PWA",
    "hr-hiring": "HR Hiring",
    "hr-manpower": "HR Manpower",
    "hr-leave-tracker": "HR Leave Tracker",
    "hr-forms": "HR Forms",
    "files": "Files",
    "submitted-forms": "Submitted Forms",
    "ticketing": "Ticketing",
    "procurement": "Procurement",
    "inspection": "Inspection",
    "dochub": "DocHub",
    "bd": "Business Development",
    "qhse": "QHSE",
    "mmr": "MMR",
    "fm": "Facilities / Digital Twin",
}

CARD_CSS = """
:root {
  --accent: #ff8e68;
  --accent-2: #ff7a50;
  --text: #191b23;
  --muted: #5c616e;
  --danger: #dc2626;
  --danger-hover: #b91c1c;
  --bg: #e8eaef;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  min-height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background:
    linear-gradient(180deg, rgba(25,27,35,.28), rgba(25,27,35,.45)),
    repeating-linear-gradient(-12deg, #f4f5f7 0 18px, #eceef2 18px 36px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem;
}
.card {
  width: min(360px, calc(100vw - 2rem));
  background: #fff;
  border-radius: 14px;
  border: 1px solid #ececef;
  box-shadow: 0 10px 32px rgba(25, 27, 35, 0.18);
  overflow: hidden;
}
.card-header {
  margin: 0;
  padding: 0.95rem 1.2rem;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #fff;
  font-size: 1.02rem;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.01em;
}
.card-body {
  margin: 0;
  padding: 1rem 1.2rem 0.15rem;
  font-size: 0.9rem;
  font-weight: 450;
  line-height: 1.5;
  color: var(--muted);
  white-space: pre-wrap;
}
.card-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.35rem;
  padding: 0.95rem 1.2rem 1.05rem;
}
.btn {
  appearance: none;
  border: none;
  background: transparent;
  cursor: default;
  font-family: inherit;
  font-size: 0.84rem;
  font-weight: 600;
  min-height: 36px;
  padding: 0.4rem 0.95rem;
  border-radius: 9px;
}
.btn-cancel { color: var(--muted); }
.btn-ok {
  background: var(--accent);
  color: #fff;
  font-weight: 650;
}
.btn-danger {
  background: var(--danger);
  color: #fff;
  font-weight: 650;
}
.meta {
  position: fixed;
  left: 1rem;
  bottom: 1rem;
  font-size: 0.72rem;
  color: rgba(255,255,255,.85);
  text-shadow: 0 1px 2px rgba(0,0,0,.35);
  max-width: calc(100vw - 2rem);
}
.meta a { color: #fff; }
"""

INDEX_CSS = """
:root {
  --accent: #ff8e68;
  --text: #191b23;
  --muted: #5c616e;
  --line: #ececef;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: var(--text);
  background: #f6f7f9;
  padding: 2rem 1.25rem 3rem;
  line-height: 1.45;
}
.wrap { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.45rem; margin: 0 0 0.35rem; letter-spacing: -0.02em; }
.lede { color: var(--muted); margin: 0 0 1.5rem; max-width: 46rem; }
.toc { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0 0 2rem; }
.toc a {
  font-size: 0.78rem;
  font-weight: 600;
  color: #7a3b24;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  text-decoration: none;
}
.toc a:hover { border-color: var(--accent); }
h2 {
  font-size: 1.05rem;
  margin: 1.75rem 0 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
}
.count { color: var(--muted); font-weight: 500; font-size: 0.85rem; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
.tile {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  box-shadow: 0 4px 14px rgba(25,27,35,.05);
}
.tile:hover { border-color: var(--accent); }
.tile-shot {
  width: 100%;
  height: 180px;
  object-fit: cover;
  object-position: center;
  background: #cfd2d8;
  display: block;
}
.tile-head {
  background: linear-gradient(135deg, #ff8e68, #ff7a50);
  color: #fff;
  font-weight: 700;
  font-size: 0.88rem;
  padding: 0.7rem 0.85rem;
}
.tile-body {
  padding: 0.75rem 0.85rem 0.35rem;
  color: var(--muted);
  font-size: 0.8rem;
  white-space: pre-wrap;
  flex: 1;
}
.tile-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 0.85rem 0.75rem;
  font-size: 0.72rem;
  color: var(--muted);
}
.pill {
  display: inline-block;
  border-radius: 999px;
  padding: 0.12rem 0.45rem;
  font-weight: 650;
  font-size: 0.68rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.pill-styled { background: #ecfdf3; color: #166534; }
.pill-native { background: #fff7ed; color: #9a3412; }
.actions { color: #7a3b24; font-weight: 600; }
"""


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def message_html(value: str) -> str:
    return esc(value).replace("\n", "<br>")


def card_markup(prompt: dict, *, compact: bool = False) -> str:
    danger = bool(prompt.get("danger"))
    hide_cancel = bool(prompt.get("hide_cancel"))
    ok_class = "btn btn-danger" if danger else "btn btn-ok"
    buttons = []
    if not hide_cancel:
        buttons.append(
            f'<button type="button" class="btn btn-cancel">{esc(prompt.get("cancel") or "Cancel")}</button>'
        )
    buttons.append(
        f'<button type="button" class="{ok_class}">{esc(prompt.get("confirm") or "OK")}</button>'
    )
    header_tag = "h2" if compact else "h1"
    return (
        f'<article class="card">'
        f'<{header_tag} class="card-header">{esc(prompt["title"])}</{header_tag}>'
        f'<p class="card-body">{message_html(prompt.get("message") or "")}</p>'
        f'<div class="card-actions">{"".join(buttons)}</div>'
        f"</article>"
    )


def prompt_page(prompt: dict, catalog_title: str) -> str:
    sources = prompt.get("source") or []
    source_line = ", ".join(sources)
    kind = prompt.get("kind") or "styled"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(prompt["title"])} — {esc(catalog_title)}</title>
  <style>{CARD_CSS}</style>
</head>
<body>
  {card_markup(prompt)}
  <p class="meta">{esc(prompt["module"])} · {esc(kind)} · {esc(source_line)}</p>
</body>
</html>
"""


def index_page(catalog: dict, prompts: list[dict]) -> str:
    title = catalog.get("title") or "Confirmation prompts"
    note = catalog.get("note") or ""
    modules: list[str] = []
    for prompt in prompts:
        mod = prompt["module"]
        if mod not in modules:
            modules.append(mod)

    toc = []
    sections = []
    for mod in modules:
        label = MODULE_LABELS.get(mod, mod)
        group = [p for p in prompts if p["module"] == mod]
        toc.append(f'<a href="#{esc(mod)}">{esc(label)} ({len(group)})</a>')
        tiles = []
        for prompt in group:
            href = f'{esc(mod)}/{esc(prompt["id"])}.html'
            png = f'{esc(mod)}/{esc(prompt["id"])}.png'
            kind = prompt.get("kind") or "styled"
            pill = f'<span class="pill pill-{esc(kind)}">{esc(kind)}</span>'
            actions = esc(prompt.get("confirm") or "OK")
            if not prompt.get("hide_cancel"):
                actions = f'{esc(prompt.get("cancel") or "Cancel")} / {actions}'
            tiles.append(
                f'<a class="tile" href="{href}">'
                f'<img class="tile-shot" src="{png}" alt="{esc(prompt["title"])}">'
                f'<div class="tile-head">{esc(prompt["title"])}</div>'
                f'<div class="tile-foot">{pill}<span class="actions">{actions}</span></div>'
                f"</a>"
            )
        sections.append(
            f'<h2 id="{esc(mod)}">{esc(label)} <span class="count">({len(group)})</span></h2>'
            f'<div class="grid">{"".join(tiles)}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>{INDEX_CSS}</style>
</head>
<body>
  <div class="wrap">
    <h1>{esc(title)}</h1>
    <p class="lede">{esc(note)} {len(prompts)} unique prompts.</p>
    <nav class="toc">{"".join(toc)}</nav>
    {"".join(sections)}
  </div>
</body>
</html>
"""


def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    prompts = catalog.get("prompts") or []
    if not prompts:
        raise SystemExit("catalog.json has no prompts")

    seen: set[tuple[str, str]] = set()
    for prompt in prompts:
        for key in ("id", "module", "title", "message"):
            if not prompt.get(key):
                raise SystemExit(f"prompt missing {key}: {prompt!r}")
        pair = (prompt["module"], prompt["id"])
        if pair in seen:
            raise SystemExit(f"duplicate prompt id {prompt['id']} in {prompt['module']}")
        seen.add(pair)

    # Drop previously generated module folders; keep catalog.json.
    for child in CATALOG_DIR.iterdir():
        if child.name == "catalog.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        elif child.suffix == ".html":
            child.unlink()

    for prompt in prompts:
        module_dir = CATALOG_DIR / prompt["module"]
        module_dir.mkdir(parents=True, exist_ok=True)
        path = module_dir / f"{prompt['id']}.html"
        path.write_text(prompt_page(prompt, catalog.get("title") or "Confirmation prompts"), encoding="utf-8")

    (CATALOG_DIR / "index.html").write_text(index_page(catalog, prompts), encoding="utf-8")
    png_count = _write_screenshots(prompts)
    print(
        f"Wrote {len(prompts)} prompt pages, {png_count} PNGs, and index.html "
        f"under {CATALOG_DIR.relative_to(ROOT)}"
    )
    return 0


def _write_screenshots(prompts: list[dict]) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is required to write PNG screenshots. "
            "Install with: pip install playwright && playwright install chromium"
        ) from exc

    count = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 720, "height": 480},
            device_scale_factor=2,
        )
        for prompt in prompts:
            html_path = (CATALOG_DIR / prompt["module"] / f"{prompt['id']}.html").resolve()
            png_path = CATALOG_DIR / prompt["module"] / f"{prompt['id']}.png"
            page.goto(html_path.as_uri(), wait_until="load")
            page.add_style_tag(content=".meta { display: none !important; }")
            page.locator(".card").wait_for()
            page.screenshot(path=str(png_path), type="png")
            count += 1
        browser.close()
    return count


if __name__ == "__main__":
    raise SystemExit(main())
