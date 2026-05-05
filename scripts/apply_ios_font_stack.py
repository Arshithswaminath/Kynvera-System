"""Replace webfont stacks in font-family declarations with the iOS / system UI stack."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STACK = (
    "-apple-system, BlinkMacSystemFont, "
    '"SF Pro Text", "SF Pro Display", system-ui, '
    '"Segoe UI", Roboto, "Helvetica Neue", sans-serif'
)

SCOPES = [
    ROOT / "templates",
    ROOT / "static",
    ROOT / "module_hr" / "templates",
    ROOT / "module_procurement" / "templates",
    ROOT / "module_mmr" / "templates",
    ROOT / "module_inspection" / "templates",
    ROOT / "module_hvac_mep" / "templates",
    ROOT / "module_civil" / "templates",
    ROOT / "module_cleaning" / "templates",
]

# Match a font-family: ... ; (single line; multi-line rare in this codebase)
FF_DECL = re.compile(
    r"font-family\s*:\s*[^;]+;",
    re.IGNORECASE | re.MULTILINE,
)


def should_replace_value(val: str) -> bool:
    v = val
    if "Material" in v:
        return False
    return bool(
        re.search(
            r"('Inter'|\"Inter\"|Inter,|Inter\s|Inter\s*;|"
            r"DM Sans|Manrope|Plus Jakarta|Grape Nuts|Cabinet|Fraunces|"
            r"JetBrains|Fira Code)",
            v,
        )
    )


def repl_decl(m: re.Match[str]) -> str:
    full = m.group(0)
    val_part = m.group(0)
    # Extract value between : and ;
    inner = re.search(r"font-family\s*:\s*([^;]+);", val_part, re.I)
    if not inner:
        return full
    if not should_replace_value(inner.group(1)):
        return full
    return f"font-family: {STACK};"


def process_text(text: str) -> str:
    text = FF_DECL.sub(repl_decl, text)
    text = re.sub(
        r'font-family="[^"]*(?:DM Sans|Inter)[^"]*"',
        'font-family="-apple-system,BlinkMacSystemFont,sans-serif"',
        text,
    )
    return text


def main() -> None:
    n = 0
    for scope in SCOPES:
        if not scope.exists():
            continue
        for p in scope.rglob("*.html"):
            t = p.read_text(encoding="utf-8")
            nt = process_text(t)
            if nt != t:
                p.write_text(nt, encoding="utf-8")
                n += 1
        for p in scope.rglob("*.css"):
            t = p.read_text(encoding="utf-8")
            nt = process_text(t)
            if nt != t:
                p.write_text(nt, encoding="utf-8")
                n += 1
    print(f"apply_ios_font_stack: updated {n} files")


if __name__ == "__main__":
    main()
