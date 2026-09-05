"""
Kynvera brand kit — logos and colour codes.

Source of truth for identity, colour hex values, and logo files.
CSS tokens live in static/css/design-tokens.css; this module is the
Python catalog used by PDFs and Excel. The brand kit PDF lives in
static/brand/ and is not surfaced in the Files app.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Sequence

COMPANY_NAME = "Kynvera"
COMPANY_NAME_UPPER = "KYNVERA"
TAGLINE = "All Operations. One Platform."
FOOTER_CONFIDENTIAL = "Kynvera — Confidential"
DEFAULT_REPORT_TITLE = "Kynvera Report"
PDF_AUTHOR = "Kynvera"
BRAND_KIT_VERSION = "2.0"
BRAND_KIT_FILENAME = "Kynvera_Brand_Kit.pdf"
BRAND_KIT_DISPLAY_NAME = "Kynvera brand kit"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_ROOT = os.path.join(_ROOT, "static")
# Canonical kit folder — logos + Kynvera_Brand_Kit.pdf (web UI still uses images/kynvera/)
BRAND_DIR = os.path.join(STATIC_ROOT, "brand")
BRAND_KIT_PATH = os.path.join(BRAND_DIR, BRAND_KIT_FILENAME)


def hex_rgb(value: str) -> str:
    """6-char RRGGBB for openpyxl fills (no '#')."""
    return value.lstrip("#").upper()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = hex_rgb(value)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_label(value: str) -> str:
    r, g, b = hex_to_rgb(value)
    return f"R{r} G{g} B{b}"


# ── Colour codes ─────────────────────────────────────────────────────────────
# Coral scale — --color-primary-50 … 950
CORAL = {
    "50": "#fff4ef",
    "100": "#ffe6db",
    "200": "#ffcdb8",
    "300": "#ffb090",
    "400": "#ff9a78",
    "500": "#ff8e68",
    "600": "#f97e54",
    "700": "#e05f36",
    "800": "#c2440c",
    "900": "#9a3609",
    "950": "#5c1f05",
}

BRAND = CORAL["500"]
BRAND_HOVER = CORAL["600"]
BRAND_DARK = CORAL["700"]
BRAND_WASH = CORAL["50"]

NEUTRAL = {
    "0": "#ffffff",
    "50": "#fafafa",
    "100": "#f4f4f5",
    "200": "#e4e4e7",
    "300": "#d4d4d8",
    "400": "#a1a1aa",
    "500": "#71717a",
    "600": "#52525b",
    "700": "#3f3f46",
    "800": "#27272a",
    "900": "#18181b",
    "950": "#09090b",
}

CHROME = {
    "page": "#f7f7f9",
    "surface": "#ffffff",
    "well": "#fafafb",
    "text": "#191b23",
    "text_mid": "#5c616e",
    "text_muted": "#9498a3",
    "hairline": "#e9eaee",
}

SEMANTIC = {
    "success": "#22c55e",
    "success_dark": "#16a34a",
    "warning": "#f59e0b",
    "warning_dark": "#d97706",
    "error": "#ef4444",
    "error_dark": "#dc2626",
    "info": "#3b82f6",
    "info_dark": "#2563eb",
}

WHITE = "#ffffff"
BLACK = "#09090b"

COLOR_SWATCHES: tuple[tuple[str, str, str], ...] = (
    ("Brand / CTA", BRAND, "--color-brand  ·  --color-primary-500"),
    ("Hover", BRAND_HOVER, "--color-brand-light  ·  --color-primary-600"),
    ("Pressed", BRAND_DARK, "--color-brand-dark  ·  --color-primary-700"),
    ("Soft wash", BRAND_WASH, "--color-brand-accent  ·  --color-primary-50"),
    ("Page canvas", CHROME["page"], "--bg-body"),
    ("Surface", CHROME["surface"], "--bg-surface"),
    ("Primary text", CHROME["text"], "--text-dark"),
    ("Secondary text", CHROME["text_mid"], "--text-mid"),
    ("Muted text", CHROME["text_muted"], "--text-muted"),
    ("Hairline", CHROME["hairline"], "--nav-hairline  ·  --border-color"),
    ("Success", SEMANTIC["success"], "--color-success-500"),
    ("Warning", SEMANTIC["warning"], "--color-warning-500"),
    ("Error", SEMANTIC["error"], "--color-error-500"),
    ("Info", SEMANTIC["info"], "--color-info-500"),
)


# ── Logos ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class LogoAsset:
    key: str
    filename: str
    relpath: str
    label: str
    use: str
    kind: str  # mark | mark-size | wordmark | reversed
    kit_filename: str = ""

    @property
    def abs_path(self) -> str:
        return os.path.join(STATIC_ROOT, *self.relpath.split("/"))

    @property
    def files_filename(self) -> str:
        return self.kit_filename or self.filename

    @property
    def exists(self) -> bool:
        return os.path.isfile(self.abs_path)


LOGOS: tuple[LogoAsset, ...] = (
    LogoAsset(
        key="mark",
        filename="kynvera-mark.png",
        relpath="brand/kynvera-mark.png",
        label="App mark",
        use="Primary mark. Nav, app icon, and brand-forward tiles. White K. on coral.",
        kind="mark",
    ),
    LogoAsset(
        key="mark-32",
        filename="kynvera-mark-32.png",
        relpath="brand/kynvera-mark-32.png",
        label="Mark 32×32",
        use="Favicon and compact UI chips.",
        kind="mark-size",
    ),
    LogoAsset(
        key="mark-48",
        filename="kynvera-mark-48.png",
        relpath="brand/kynvera-mark-48.png",
        label="Mark 48×48",
        use="Touch icons and small nav.",
        kind="mark-size",
    ),
    LogoAsset(
        key="mark-96",
        filename="kynvera-mark-96.png",
        relpath="brand/kynvera-mark-96.png",
        label="Mark 96×96",
        use="In-app nav mark (default).",
        kind="mark-size",
    ),
    LogoAsset(
        key="mark-180",
        filename="kynvera-mark-180.png",
        relpath="brand/kynvera-mark-180.png",
        label="Mark 180×180",
        use="Apple touch icon / high-DPI app icon.",
        kind="mark-size",
    ),
    LogoAsset(
        key="wordmark",
        filename="kynvera-wordmark.png",
        relpath="brand/kynvera-wordmark.png",
        label="Wordmark",
        use="About, document headers, and brand-forward surfaces. Do not recolor.",
        kind="wordmark",
    ),
    LogoAsset(
        key="reversed",
        filename="kynvera-mark-reversed.png",
        relpath="brand/kynvera-mark-reversed.png",
        label="Reversed mark",
        use="Dark or photographic backgrounds. White K. only.",
        kind="reversed",
    ),
)

_LOGO_BY_KEY = {logo.key: logo for logo in LOGOS}

WORDMARK_PATH = _LOGO_BY_KEY["wordmark"].abs_path
MARK_PATH = _LOGO_BY_KEY["mark-96"].abs_path
MARK_PATH_FALLBACK = _LOGO_BY_KEY["mark"].abs_path
REVERSED_MARK_PATH = _LOGO_BY_KEY["reversed"].abs_path


def get_logo(key: str) -> LogoAsset | None:
    return _LOGO_BY_KEY.get(key)


def existing_logos() -> list[LogoAsset]:
    return [logo for logo in LOGOS if logo.exists]


def resolve_logo_path(prefer_wordmark: bool = True) -> Optional[str]:
    """First existing logo path for headers (wordmark) or compact slots (mark)."""
    order: Sequence[str] = (
        ("wordmark", "mark-96", "mark") if prefer_wordmark else ("mark-96", "mark", "wordmark")
    )
    for key in order:
        logo = _LOGO_BY_KEY.get(key)
        if logo and logo.exists:
            return logo.abs_path
    return None
