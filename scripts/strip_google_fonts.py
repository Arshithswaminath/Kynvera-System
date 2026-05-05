"""Remove Google *text* font bundles from HTML; keep icon fonts (e.g. Material Symbols)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DESIGN = (
    '  <link rel="stylesheet" '
    'href="{{ url_for(\'static\', filename=\'css/design-tokens.css\') }}">\n'
)

PRECONNECT_BLOCK = (
    "    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n"
    "    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n"
)

DIRS = [
    ROOT / "templates",
    ROOT / "module_hr" / "templates",
    ROOT / "module_procurement" / "templates",
    ROOT / "module_mmr" / "templates",
    ROOT / "module_inspection" / "templates",
    ROOT / "module_hvac_mep" / "templates",
    ROOT / "module_civil" / "templates",
    ROOT / "module_cleaning" / "templates",
]


def strip_font_links(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if "fonts.googleapis.com/css2" in line:
            if re.search(r"Material|icon", line, re.I):
                out.append(line)
            # else: drop (Inter, DM Sans, etc.)
            continue
        if re.search(r'preconnect[^>]+fonts\.googleapis\.com', line, re.I):
            continue
        if re.search(r"preconnect[^>]+fonts\.gstatic", line, re.I):
            continue
        out.append(line)
    return "".join(out)


def ensure_preconnect_for_google_fonts(text: str) -> str:
    if "fonts.googleapis.com/css2" not in text:
        return text
    if "fonts.gstatic.com" in text:
        return text
    m = re.search(
        r"(<meta[^>]+name=[\"']viewport[\"'][^>]*>\s*)",
        text,
        re.IGNORECASE,
    )
    if m:
        return text[: m.end()] + PRECONNECT_BLOCK + text[m.end() :]
    return text


def ensure_design_tokens(s: str) -> str:
    if "css/design-tokens.css" in s:
        return s
    m = re.search(
        r"(<meta[^>]+name=[\"']viewport[\"'][^>]*>\s*)",
        s,
        re.IGNORECASE,
    )
    if m:
        return s[: m.end()] + "\n" + DESIGN + s[m.end() :]
    m2 = re.search(r"(<head[^>]*>\s*)", s, re.IGNORECASE)
    if m2:
        return s[: m2.end()] + "\n" + DESIGN + s[m2.end() :]
    return s


def main() -> None:
    n = 0
    for d in DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.html")):
            text = p.read_text(encoding="utf-8")
            orig = text
            text = strip_font_links(text)
            text = ensure_preconnect_for_google_fonts(text)
            if text != orig:
                text = ensure_design_tokens(text)
                p.write_text(text, encoding="utf-8")
                n += 1
    print(f"strip_google_fonts: updated {n} files")


if __name__ == "__main__":
    main()
