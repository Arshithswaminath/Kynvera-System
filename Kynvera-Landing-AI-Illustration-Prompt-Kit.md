# Kynvera Landing Page — AI Illustration Prompt Kit

**Target:** the "Classic" UI (`templates/landing.html`, `landing.css`) — not the Bold or Motion variants.
**Reference style:** the "Built Kindly"-style illustrations you shared (flat vector, cream background, coral accent, thin black outlines, sage-green squiggles). Your `Motion` variant already reverse-engineered this style in hand-coded SVG — we're now porting the *look* to Classic using real AI-generated art instead of hand-drawn SVG.

Classic's current palette:
- Shell/background: `#e8e8e7` (light grey)
- Card: `#ffffff`
- Ink (text/lines): `#121212` / `#3a3a38`
- Accent: `#ff8e68` (coral) / `#e05f36` (deep coral)

Since Classic's background is grey/white rather than cream, generate every image with a **transparent or white background** so it drops cleanly onto `.l-card` / `.l-canvas` without a mismatched color box around it.

---

## 1. Master style prompt (use as a prefix on every image)

Paste this before every scene-specific prompt below. It's what keeps 10 separate generations looking like one illustration set.

> Flat 2D vector illustration, minimalist corporate/SaaS style. Clean black ink outlines, 2–3px consistent line weight, no gradients, no drop shadows, no photorealism, no 3D render. Rounded, friendly character design: simple dot eyes, small smile, soft rounded body shapes, no detailed faces. Limited palette only: white/transparent background, coral-orange accent `#FF8E68` and `#E05F36`, charcoal-black linework `#121212`, muted sage-green `#6E9184` used sparingly for small accents (squiggles, leaves, checkmarks). Generous negative space around the subject, no clutter, no background pattern, no text, no logos, no watermark. Consistent character proportions and line weight across the set — same illustration family as Storyset/unDraw-style startup illustrations.

**Negative prompt (apply to all):** `text, logos, watermark, photorealistic, 3D render, gradient, drop shadow, glossy, plastic sheen, extra limbs, busy background, clutter, low detail linework, sketchy`

---

## 2. Consistency method (read this before generating)

Flat-vector character consistency across many separate prompts is the hard part — generic models drift in color and line weight. Recommended approach:

1. **Generate the hero image first** and treat it as the "master" reference.
2. **Lock a style reference** for every image after that:
   - **Recraft V3** — best fit here; has a "Style" / brand-kit feature that locks palette + line weight across a whole generation batch. Recommended primary tool.
   - **Midjourney v6/v7** — use `--sref <url-of-approved-hero-image>` plus `--style raw` off, on every subsequent prompt.
   - **Ideogram 3.0** — decent fallback for simple icon-style pieces (the 3 pillar icons).
3. **For video** (if you also want a short motion/looping hero): feed the finished flat illustration into an image-to-video tool — **Runway Gen-4** or **Kling 2.1** — with *low* motion strength. Flat vector art warps/melts under heavy AI-video motion, so keep it subtle (see §5).

---

## 3. Image list, placement, and prompts

10 images total, but only **6 unique compositions** — the 3 "Platform" pillar icons are simple variations of one icon template, so they can be batched quickly once the style is locked.

| # | Section (id) | Placement | Size / aspect | Purpose |
|---|---|---|---|---|
| 1 | Hero (`.l-hero`) | Beside or behind the headline "All your operations run on one platform" | 4:3, ~1200×900 | Primary visual anchor — first thing visitors see |
| 2 | Applications → Fire System (`#applications`, `.l-showcase-copy`) | Small accent beside the bullet checklist, or subtle background behind the device mockup | 4:5, ~700×900 | Reinforces the Fire System tab |
| 3 | Applications → Ajman Municipality (`#applications`, `.l-showcase-copy`) | Same position, Municipality panel | 4:5, ~700×900 | Reinforces the Municipality tab |
| 4 | Platform pillar 1 — "Unified access" (`#platform`, `.l-pillar`) | Small icon above/beside the pillar heading | 1:1, ~400×400 | Matches the reference's icon-card pattern (e.g. "Strategic Foundations") |
| 5 | Platform pillar 2 — "Field-ready workflows" (`#platform`, `.l-pillar`) | Same | 1:1, ~400×400 | Same |
| 6 | Platform pillar 3 — "Clear accountability" (`#platform`, `.l-pillar`) | Same | 1:1, ~400×400 | Same |
| 7 | How it works (`#how-it-works`) | Wide banner above or behind the 3-step list | 3:1 or 16:9, ~1800×600 | One connected scene showing the sign-in → open app → keep moving journey |
| 8 | Pricing (`#pricing`) | Beside the section heading / eyebrow | 4:3, ~800×600 | Growth metaphor for "start small, add as you grow" |
| 9 | FAQ (`#faqs`) | Beside the "Questions, answered" heading | 1:1, ~500×500 | Light, approachable support visual |
| 10 | Closing CTA (final `.l-cta-card` before footer) | Full-bleed background behind "Ready to run everything from one place?" | 21:9 or 3:1, ~2400×900 | Big optimistic banner, matches the reference balloon/landscape scene |

### Scene prompts (append each to the master style prompt in §1)

**1 — Hero**
> Two coworkers at a shared desk looking at a large monitor showing a simple dashboard with a donut chart and a small bar chart. The left person is seated, typing at a keyboard. The right person stands, one arm raised in a cheerful wave, small celebratory marks floating above their hand. Two small floating UI cards — one with a settings/gear icon, one with a checkmark — float near the monitor.

**2 — Fire System accent**
> A field inspector wearing a small vest, holding a tablet, standing beside a simple fire-extinguisher icon and a floating checklist card with a checkmark, one hand pointing at the card.

**3 — Municipality accent**
> An office reviewer seated at a desk, stamping a document, a small stack of folders beside them and a floating approval checkmark card above the desk.

**4 — Pillar icon: Unified access**
> A single simple key unlocking a rounded padlock, held by a small stylised hand, soft radiating halo shape behind it, centered icon composition with wide margins.

**5 — Pillar icon: Field-ready workflows**
> A stylised hand holding a small tablet displaying a checklist, one small curved arrow beside it suggesting motion/flow, centered icon composition with wide margins.

**6 — Pillar icon: Clear accountability**
> A rounded shield with a checkmark inside it, a small magnifying glass resting beside the shield, centered icon composition with wide margins.

**7 — How it works (wide banner)**
> A connected three-stage journey across a wide horizontal scene: a door with a key floating beside it (sign in), a dotted path leading to a laptop screen opening an app icon (open an application), a dotted path leading to a checklist with a completed checkmark and a small flag (keep work moving). One continuous dotted line links all three stages left to right.

**8 — Pricing**
> A person watering a small potted plant with three leaves of increasing size, a small coin or price-tag icon resting near the base of the pot, suggesting steady growth.

**9 — FAQ**
> A person sitting cross-legged with a laptop on their knees, a large friendly question mark floating beside them, one small speech bubble containing a checkmark.

**10 — Closing CTA banner**
> A wide, airy landscape: rolling hills, two simple stylised cypress trees, one hot-air balloon drifting in the sky, soft rounded clouds, a single winding path leading toward the horizon. Open composition with plenty of sky left empty for headline text to sit on top of.

---

## 4. Export settings

- Format: PNG with transparent background where the composition allows it (hero, accents, pillar icons, FAQ). The wide banners (How it works, Closing CTA) can keep a soft off-white fill since they'll span full width.
- Resolution: export at 2x the target display size for retina screens, then compress for web (WebP, matching the existing `static/images/kynvera/showcase/*.webp` pattern already used on the Applications section).
- Save into `static/images/kynvera/illustrations/` so they sit alongside the existing `apps/` and `showcase/` folders.

---

## 5. Optional: turning any image into a short looping video

Only worth doing for the **Hero** or **Closing CTA** banner — a static illustration is fine everywhere else.

> Take the finished flat-illustration PNG as the input frame for an image-to-video model (Runway Gen-4 or Kling 2.1). Prompt: "Subtle looping motion only: the raised-arm character gently waves once, the small chart bars on the monitor animate up and down slightly, clouds or leaves drift very slowly in the background. Camera fully static, no zoom, no cuts, seamless 4-second loop, preserve flat 2D vector art style exactly, do not let character proportions warp or morph." Set motion strength to low, duration 4–6 seconds, loop enabled.

---

## Summary

- 10 images across 6 unique compositions cover every section of the Classic landing page that currently has no visual (hero, both app tabs, all 3 platform pillars, how-it-works, pricing, FAQ, closing CTA).
- Generate the hero first, lock it as a style reference (Recraft style / Midjourney `--sref`), then batch the rest against that reference for consistency.
- Keep video to the hero and/or closing banner only, with low motion strength, since flat vector art distorts easily under heavier AI video motion.
