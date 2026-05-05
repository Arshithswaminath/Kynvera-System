# Main Dashboard Background – Design Reference

This document captures the main dashboard background styling used across the Injaaz platform (main dashboard, HR module, Inspection Form, Procurement, and Review History).

## Overview

The background combines:
1. **Gradient colors** – soft off-white to light green
2. **Green grid pattern** – subtle grid overlay that fades gradually
3. **Glow orb** – soft green tint in the top-left area

---

## Color Values

### Base Gradient
```css
linear-gradient(160deg, #f5f9f6 0%, #fafbfa 50%, #f8faf8 100%)
```
- **Top:** `#f5f9f6` (very light green-white)
- **Middle:** `#fafbfa` (off-white)
- **Bottom:** `#f8faf8` (light grey-green)

### Radial Accents
```css
radial-gradient(ellipse 70% 60% at 0% 50%, rgba(18, 84, 53, 0.1) 0%, transparent 70%)
radial-gradient(ellipse 40% 40% at 100% 10%, rgba(18, 84, 53, 0.05) 0%, transparent 60%)
```
- Primary green: `rgba(18, 84, 53, 0.1)` – top-left
- Secondary green: `rgba(18, 84, 53, 0.05)` – top-right

### Body / Content Area
- `#f8faf8` – matches the gradient bottom for seamless merge

---

## Green Grid Pattern

### Grid Lines
```css
background-image:
  linear-gradient(rgba(18, 84, 53, 0.04) 1px, transparent 1px),
  linear-gradient(90deg, rgba(18, 84, 53, 0.04) 1px, transparent 1px);
background-size: 48px 48px;
```

### Grid Fade (No Hard Line)
The grid fades gradually from top to bottom so it merges with the content area:
```css
mask-image: linear-gradient(to bottom, black 0%, black 45%, transparent 95%);
-webkit-mask-image: linear-gradient(to bottom, black 0%, black 45%, transparent 95%);
```

---

## Glow Orb (Optional Decorative Element)
```css
background: radial-gradient(circle, rgba(18, 84, 53, 0.12) 0%, transparent 65%);
/* Position: top 20%, left -8%; size: 420px × 420px */
```

---

## Full CSS (Hero Section)

```css
.hero {
  background:
    radial-gradient(ellipse 70% 60% at 0% 50%, rgba(18, 84, 53, 0.1) 0%, transparent 70%),
    radial-gradient(ellipse 40% 40% at 100% 10%, rgba(18, 84, 53, 0.05) 0%, transparent 60%),
    linear-gradient(160deg, #f5f9f6 0%, #fafbfa 50%, #f8faf8 100%);
  position: relative;
  overflow: hidden;
}

.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(18, 84, 53, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(18, 84, 53, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(to bottom, black 0%, black 45%, transparent 95%);
  -webkit-mask-image: linear-gradient(to bottom, black 0%, black 45%, transparent 95%);
  pointer-events: none;
  z-index: 0;
}
```

---

## Implementation

- **Source:** `static/css/dashboard.css`
- **Classes:** `.hero`, `.hero.hr-hero`, `.hero.inspection-hero`, `.hero.proc-hero`, `.hero.review-hero`
- **HR Module:** Uses `hero hero-split hr-hero` on the dashboard header

---

*Last updated: March 2026*
