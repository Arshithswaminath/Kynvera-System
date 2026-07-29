# Kynvera Design System

**Version:** 2.0 — Coral theme  
**Source of truth:** `static/css/design-tokens.css`  
**App chrome aliases:** `static/css/dashboard.css`  
**Public landing:** `static/css/landing.css`

Kynvera’s visual language is a **light, product-first UI** with a single strong accent: **coral**. Surfaces stay cool and neutral; coral is reserved for actions, focus, and brand moments.

---

## Brand personality

| Trait | How it shows up |
| --- | --- |
| Clean & operational | White cards, light gray page canvas, quiet borders |
| Warm accent | Coral CTAs, focus rings, assistant pill, progress |
| System-native in-app | SF Pro / system UI stack (Apple-first, cross-platform fallbacks) |
| Slightly expressive on marketing | Sora + DM Sans on the public landing; Caveat for authorship |

**Do:** keep coral as the only loud color; prefer soft shadows and calm motion.  
**Don’t:** introduce purple gradients, heavy glow, or competing accent hues in core chrome.

---

## Logo & assets

| Asset | Path | Use |
| --- | --- | --- |
| Mark | `static/images/kynvera/kynvera-mark*.png` | App nav, favicon-scale marks (32 / 48 / 96 / 180) |
| Wordmark | `static/images/kynvera/kynvera-wordmark.png` | About and brand-forward surfaces |
| Auth panel art | `static/images/auth/auth-brand-panel.png` | Auth / brand panel imagery |

- **In-app nav:** mark by default.  
- **About:** full wordmark.  
- Keep clear space around the mark; don’t recolor the logo outside approved brand coral / white treatments.

---

## Color

### Brand (coral)

| Token | Hex | Role |
| --- | --- | --- |
| `--color-brand` / `--color-primary-500` | `#ff8e68` | Primary brand & CTA |
| `--color-brand-light` / `--color-primary-600` | `#f97e54` | Hover |
| `--color-brand-dark` / `--color-primary-700` | `#e05f36` | Active / pressed |
| `--color-brand-accent` / `--color-primary-50` | `#fff4ef` | Soft wash / tinted backgrounds |

Full coral scale: `50` → `950` in `design-tokens.css` (`#fff4ef` … `#5c1f05`).

### Neutrals

Zinc-style neutrals from white (`#ffffff`) through `#fafafa` / `#f4f4f5` to near-black (`#18181b` / `#09090b`).

### App chrome (dashboard)

| Token | Hex | Role |
| --- | --- | --- |
| `--bg-body` | `#f7f7f9` | Page canvas |
| `--bg-surface` / `--bg-card` | `#ffffff` | Cards, panels |
| `--bg-light` | `#fafafb` | Subtle fills, hover wells |
| `--text-dark` | `#191b23` | Primary text |
| `--text-mid` | `#5c616e` | Secondary |
| `--text-muted` | `#9498a3` | Hints, meta |
| `--nav-hairline` / `--border-color` | `#e9eaee` | Nav & toolbar dividers |

### Semantic

| Role | Examples |
| --- | --- |
| Success | `#22c55e` family |
| Warning | `#f59e0b` family |
| Error | `#ef4444` family |
| Info | `#3b82f6` family |

### Landing-only accents

Public landing (`landing.css`) stays coral-led, with soft atmospheric washes (coral, warm gold, muted teal) for background blobs only — not for primary controls.

---

## Typography

### In-app (product UI)

```text
--font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
             "SF Pro", ui-sans-serif, system-ui, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, sans-serif
```

- Body / UI / display in-app all resolve to this stack.  
- Mono: SF Mono / platform monospace for codes and IDs.  
- Footer “built by” name: **Caveat** (`--font-footer-author`), colored with brand coral.

### Scale (modular ~1.25)

| Token | Size |
| --- | --- |
| `--text-xs` | 0.75rem (12px) |
| `--text-sm` | 0.875rem (14px) |
| `--text-base` | 1rem (16px) |
| `--text-lg` | 1.125rem (18px) |
| `--text-xl` | 1.25rem (20px) |
| `--text-2xl` … `--text-6xl` | 1.5rem → 3.75rem |

Weights: 300–800 via `--font-light` … `--font-extrabold`.  
Default body: 16px, `--leading-normal` (1.5).

### Public landing

| Role | Family |
| --- | --- |
| Body | DM Sans |
| Display | Sora |
| Hand / signature | Caveat |

---

## Spacing

Base unit **4px**. Tokens: `--space-1` (4px) through `--space-32` (128px).  
Prefer the scale over arbitrary values for padding, gaps, and margins.

---

## Radius

| Token | Value | Typical use |
| --- | --- | --- |
| `--radius-lg` / app `--radius-sm` | 8px | Compact controls |
| App `--radius-md` | 12px | Inputs, chips |
| App `--radius-lg` | 16px | Cards, panels |
| App `--radius-xl` | 20px | Large surfaces |
| `--radius-full` | 9999px | Pills, circular icon buttons |

Nav icon rail and similar icon-only actions use **circular** 36×36 targets with matched 20px glyphs.

---

## Elevation

Soft, low-contrast shadows — product, not theatrical:

- `--shadow-xs` → `--shadow-2xl` for neutral depth  
- `--shadow-primary`: coral-tinted lift on brand actions (`rgb(255 142 104 / 0.25)`)

Hairline borders (`#e9eaee` / neutral-200) often beat heavy shadows for separation.

---

## Motion

| Token | Guidance |
| --- | --- |
| Durations | Prefer 150–300ms for UI; avoid long decorative loops |
| Easing | `--ease-out`, `--ease-in-out`; app also uses spring-like curves sparingly |
| Reduced motion | Honored via `prefers-reduced-motion` (animations/transitions collapsed) |

Motion should clarify hierarchy (open/close, focus, progress) — not decorate every surface.

---

## Interaction & accessibility

- **Focus:** `:focus-visible` uses **2px solid brand coral** with offset.  
- **Touch:** aim for ≥44×44px targets on mobile; compact icon rails use consistent 36×36 with adequate spacing.  
- **Inputs:** 16px font size on mobile to avoid iOS zoom.  
- **Contrast:** dark ink on light surfaces; white text on solid coral CTAs.

---

## Component patterns (how the brand shows up)

| Pattern | Treatment |
| --- | --- |
| Primary button | Solid coral → hover `#f97e54`; white label; soft coral shadow optional |
| Secondary / ghost | White or transparent, neutral border, coral on hover/focus |
| Links & active nav | Coral or coral tint, not underline-heavy chrome |
| Progress / steppers | Coral fill or coral→coral-light gradient |
| Assistant entry | Coral filled circle (icon-only on compact nav) |
| Forms (HR etc.) | Coral headers / primary actions; neutral grouped sections |
| Toasts / badges | Semantic colors; unread badges often error red |

---

## Themes

- **Default product experience:** light mode (`--bg-body: #f7f7f9`).  
- Dark tokens exist (`[data-theme="dark"]`, `.dark`, and system `prefers-color-scheme`) — brand coral remains the interactive accent.  
- Prefer explicit light chrome for core operational modules unless a surface is designed for dark.

---

## File map

| File | Responsibility |
| --- | --- |
| `static/css/design-tokens.css` | Global tokens, semantic colors, base type, focus, reduced motion |
| `static/css/dashboard.css` | App shell, nav, dashboard surfaces |
| `static/css/landing.css` | Public landing / login light theme (scoped under `.landing`) |
| `static/css/assistant.css` | Assistant widget & nav assistant control |
| `static/css/auth.css` | Auth shells (may use darker shell; don’t leak into landing) |
| Module CSS (`hr-forms-unified.css`, `ticketing.css`, …) | Module-specific layouts using the same coral + neutral vocabulary |

When adding UI, **consume tokens** (`--color-brand`, `--bg-body`, `--radius-*`, `--font-sans`) instead of hard-coding one-off hex values.

---

## Quick reference

```text
Brand coral     #ff8e68
Hover           #f97e54
Pressed         #e05f36
Soft wash       #fff4ef
Page canvas     #f7f7f9
Surface         #ffffff
Primary text    #191b23
Border/hairline #e9eaee
```

**One-line summary:** light neutral workspace, system typography, coral only where it means *action* or *brand*.
