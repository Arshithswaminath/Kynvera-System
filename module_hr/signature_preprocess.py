"""Strip flat UI / PDF preview backgrounds from HR signature raster images (PDF + DOCX)."""


def rgba_make_signature_background_transparent(img_rgba):
    """
    Mutate a PIL RGBA image in place: turn common \"paper\" pixels transparent so
    exported PDF/DOCX show ink on white only (no leftover blue tint from old preview boxes).
    """
    data = img_rgba.load()
    w, h = img_rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = data[x, y]
            if _rgb_is_signature_sheet_background(r, g, b):
                data[x, y] = (0, 0, 0, 0)


def _rgb_is_signature_sheet_background(r, g, b):
    """True for whites, neutral light gr (#f5f5f7), and light blue (#dbeafe-class) flats."""
    mx, mn = max(r, g, b), min(r, g, b)
    if mx < 90:
        return False
    if mn < 62:
        return False
    if mn >= 248:
        return True
    if mn >= 222 and (mx - mn) <= 16:
        return True
    if b >= 225 and r >= 198 and g >= 208 and (b - r) >= 5 and (b - g) >= 4:
        return True
    return False
