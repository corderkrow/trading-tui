# coderkrow — Brand Design Rules

> These rules govern all AI-generated page content and designs for the coderkrow website.
> Follow every rule strictly. When in doubt, refer back to the source of truth: the imagotipo (mascot + wordmark lockup).

---

## 1. Identity Principles

coderkrow is a tech content brand for developers — not a SaaS product, not a corporate entity.
The visual language must feel **crafted, opinionated, and slightly dark** — like a developer who cares deeply about aesthetics.

### Core traits to express in every design
- **Technical confidence** — precision in spacing, grid, and typography over decorative noise
- **Edge without aggression** — dark, moody palette but never heavy-metal; serious but approachable
- **Minimal chrome, maximal content** — UI stays out of the way; the content is the product
- **Cyber-organic tension** — the crow mascot lives at the intersection of nature and technology; that duality should echo in design choices (organic curves against monospaced code blocks, teal warmth against dark ink)

### What to avoid at all costs
- Generic "developer blog" aesthetics (purple gradients, neon green on black, overused grid patterns)
- Corporate softness (rounded pastel cards, emoji-heavy headings, motivational copy)
- Startup clichés (gradient hero text, floating 3D blobs, stock-photo developer photos)
- Over-animation for its own sake

---

## 2. Color

### Token reference

```css
:root {
  --ck-ink:         #1d1d1b;   /* near-black — primary text, heavy UI elements */
  --ck-teal:        #1a595a;   /* deep forest teal — brand accent, "krow" half */
  --ck-teal-mid:    #2e7f80;   /* mid teal — hover states, interactive elements */
  --ck-teal-light:  #3bb8ba;   /* light teal — badges, highlights, inline accents */
  --ck-cyan:        #00d1d4;   /* goggle cyan — glows, code highlights, "on" states */
  --ck-surface:     #f5f4f0;   /* warm off-white — card surfaces, inputs (light mode) */
  --ck-muted:       #4a4a47;   /* secondary text, captions, metadata */
}
```

### Usage rules

**Primary palette** — only three colors should dominate any composition: `--ck-ink`, `--ck-teal`, and white/off-white. Everything else is supporting detail.

**`--ck-cyan` is a signal color.** Use it sparingly: syntax highlighting, active toggle states, a single decorative glow on the hero, code cursor blinks. Never as a background fill over large areas.

**Color ratios per page/section:**
- Background: white or `--ck-surface` — 70%
- Ink / text elements — 20%
- Teal accents — 8%
- Cyan highlights — 2%

### Theme variants (light / dark)

**Every page and component must ship both a light and a dark variant.** Light is default; dark is not optional-nice-to-have — it is a required deliverable on every build, same as mobile responsiveness.

**Token behavior across themes:**
- `--ck-bg`, `--ck-surface`, `--ck-ink`, `--ck-muted`, `--ck-border` invert per theme
- `--ck-teal`, `--ck-teal-mid`, `--ck-teal-light`, `--ck-cyan` stay **identical** in both themes — the brand accent never shifts hue between light and dark, only the ground it sits on changes
- Code blocks stay dark in both themes (see §5) — they are not part of the light/dark toggle

**Dark mode values:**
```css
--ck-bg:      #111110;   /* near-black — not pure #000 */
--ck-surface: #1a1a18;   /* slightly lighter surface */
--ck-ink:     #e8e6df;   /* warm off-white text */
--ck-muted:   #888780;   /* muted secondary */
--ck-border:  rgba(232,230,223,.07);
```

**Theme resolution order — implement all three layers:**
1. **System default.** `@media (prefers-color-scheme: dark)` sets the theme when the visitor has no saved preference.
2. **Manual override.** A visible toggle (Light / Dark / Auto) lets the visitor override the system setting. Implement with a `data-theme="light"` or `data-theme="dark"` attribute on `<html>`; `:root:not([data-theme="light"])` inside the dark media query lets system-dark apply unless the visitor explicitly chose light, and `:root[data-theme="dark"]` forces dark regardless of system setting.
3. **Persistence.** Store the visitor's manual choice (`localStorage`, key `ck-theme`) so it survives reload and applies before first paint if possible, to avoid a flash of the wrong theme.

```css
:root { /* light values — the defaults */ }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* dark values */ }
}

:root[data-theme="dark"] { /* dark values, forced */ }
```

**Toggle placement and style:** a three-way segmented control (Light / Dark / Auto) in the nav or footer, styled with the standard tag/pill treatment — never an icon-only sun/moon switch with no label, and never a hidden setting buried in a menu.

**Transition:** background and text color transition at `200ms` on theme change. No transition on borders or on the toggle itself snapping state.

**Never use raw black (#000000) or pure white (#ffffff) for large surfaces in either theme.** Always use the ink/surface/bg tokens — they carry the warm tint that makes the palette cohesive in both modes.

**Tints and alphas — permitted derivations only:**
- `--ck-teal` at 8% opacity → subtle brand-tinted surface (`#1a595a14`)
- `--ck-teal` at 20% opacity → brand border (`#1a595a33`)
- `--ck-ink` at 6% opacity → divider / hairline (`#1d1d1b0f`)
- No other ad-hoc color mixing

---

## 3. Typography

### Font stack

```css
--ck-font-display: "Space Grotesk", "Outfit", sans-serif;
--ck-font-body:    "Space Grotesk", "Outfit", system-ui, sans-serif;
--ck-font-mono:    "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
```

**Space Grotesk is the primary font.** Outfit is the fallback. Both share the rounded geometric sans-serif construction visible in the wordmark. Never substitute Inter, Roboto, or system-ui alone as the primary font — they lack the character that ties back to the logo.

**JetBrains Mono** is the required monospace font for all code. Its ligature support and letter clarity reinforce the "developer who cares about craft" identity.

### Type scale

| Token | Size | Weight | Tracking | Usage |
|---|---|---|---|---|
| `text-display` | 56–72px | 400 | -0.02em | Hero wordmark scale, section landmarks |
| `text-h1` | 40px | 500 | -0.02em | Page titles |
| `text-h2` | 28px | 500 | -0.015em | Section headings |
| `text-h3` | 20px | 500 | -0.01em | Card titles, subsections |
| `text-h4` | 16px | 500 | 0em | Labels, groups |
| `text-body-lg` | 18px | 400 | 0em | Lead paragraphs, featured body |
| `text-body` | 15px | 400 | 0em | Standard body copy |
| `text-small` | 13px | 400 | 0.01em | Captions, metadata, timestamps |
| `text-label` | 11px | 500 | 0.08em | Category tags, overlines (uppercase) |
| `text-code` | 14px | 400 | 0em | Inline and block code |

### Rules

**Weight is binary: 400 or 500.** Never use 600, 700, or bold. The wordmark itself is set at regular (400) — heavy weights break visual consistency with the logo.

**Headings never use all-caps except `text-label`.** Sentence case only for all headings and UI labels.

**Line heights:**
- Display / headings: `1.1`
- Body text: `1.65`
- Code blocks: `1.6`
- UI labels / nav: `1.2`

**Negative tracking at display sizes is mandatory.** `-0.02em` at 56px+ prevents the rounded letterforms from feeling spacey. At body sizes tracking is `0em` or slightly positive.

**The wordmark split rule:** When rendering the brand name in any context (nav logo, footer, metadata), "coder" is always `--ck-ink` and "krow" is always `--ck-teal`. The two-color treatment is non-negotiable in any size above 16px.

---

## 4. Spacing & Layout

### Base unit

All spacing is derived from an **8px base unit**.

```
--ck-space-1:   4px    /* hairline gaps, icon padding */
--ck-space-2:   8px    /* tight internal padding */
--ck-space-3:   12px   /* compact component gaps */
--ck-space-4:   16px   /* standard component padding */
--ck-space-5:   20px   /* comfortable component padding */
--ck-space-6:   24px   /* section-internal spacing */
--ck-space-8:   32px   /* card padding, section gaps */
--ck-space-12:  48px   /* major section rhythm */
--ck-space-16:  64px   /* section vertical padding */
--ck-space-24:  96px   /* hero / landmark spacing */
--ck-space-32: 128px   /* large section separators */
```

### Grid

- **Max content width:** `1200px`
- **Standard columns:** 12-column grid, `24px` gutter
- **Breakpoints:**
  - Mobile: `< 640px` — single column
  - Tablet: `640px – 1024px` — 6-column condensed
  - Desktop: `> 1024px` — full 12-column
- **Content column width:** prose content (articles, video descriptions) caps at `680px` regardless of container — never let line length exceed 75 characters

### Layout rules

**Asymmetry over symmetry for landing sections.** Hero layouts, feature callouts, and about sections should use deliberate visual weight shifts — e.g. a large heading on the left with a thin vertical accent on the right, rather than centered everything.

**Density by hierarchy:** Navigation and metadata are dense. Body content is airy. Hero sections are sparse and typographic. Never apply the same padding rhythm to all sections.

**No full-bleed background fills on interior sections unless they carry real semantic weight** (e.g. a dark-mode testimonial or a code-showcase section). Decorative full-bleed alternating-color rows are a cliché — avoid them.

---

## 5. Components

### Navigation

- Brand logo lockup (mascot + wordmark) on the left, anchored at `32px` height
- Nav links at `text-small` (13px, weight 500), `--ck-muted` color, `--ck-teal` on active/hover
- No dropdown megamenus — flat, single-level nav only
- CTA button in nav (if present): outlined style — `1px solid --ck-teal`, `--ck-teal` text, transparent background, `4px` radius; fills `--ck-teal` on hover with white text

### Buttons

```
Primary:   bg --ck-teal, text white, radius 6px, padding 10px 20px
           hover → bg --ck-teal-mid
           no box-shadow, no gradient

Secondary: bg transparent, border 1px --ck-teal, text --ck-teal, radius 6px
           hover → bg --ck-teal at 8% opacity

Ghost:     bg transparent, no border, text --ck-muted
           hover → text --ck-ink

Danger:    only when destructive; use sparingly; not part of the primary brand vocabulary
```

**No rounded-pill buttons (border-radius: 9999px) for primary actions.** `6–8px` radius only. Pills are permitted only for tag/badge elements.

### Cards

```
Card surface:  bg --ck-surface (light) / bg --ck-surface (dark)
Border:        1px solid --ck-ink at 6% opacity
Border-radius: 10px
Padding:       24px
Hover state:   border-color shifts to --ck-teal at 20% opacity; no lift / box-shadow
```

**No drop shadows on cards.** The border treatment is the only elevation signal. The design uses planarity — everything lives on one surface with borders as delimiters.

### Code blocks

```
Background:   #111110 (dark) / #1a1a18 (always dark — code blocks are always dark-on-dark)
Text:         --ck-surface (#e8e6df)
Accent/keywords: --ck-cyan (#00d1d4)
Strings:      --ck-teal-light (#3bb8ba)
Comments:     --ck-muted (#888780) at 80% opacity
Border-radius: 8px
Padding:      20px 24px
Font:         --ck-font-mono at 14px
```

**Code blocks are always dark**, even on light-mode pages. They are the primary environment where `--ck-cyan` and `--ck-teal-light` appear prominently.

**Inline code** (`` `code` ``): `bg --ck-teal at 8%`, `color --ck-teal`, `border-radius 3px`, `padding 1px 5px`, same mono font at 0.9em.

### Tags & Badges

```
Default tag:  bg --ck-surface, border 1px --ck-ink at 10%, text --ck-muted
              border-radius 9999px, padding 3px 10px, font-size 12px, weight 500

Brand tag:    bg --ck-teal at 10%, border 1px --ck-teal at 20%, text --ck-teal
              (used for video categories, featured labels)

Cyan tag:     bg --ck-cyan at 10%, text --ck-teal (not --ck-cyan directly — too bright as text)
              (used for "new", "live", active state)
```

### Dividers

**Use space, not lines.** Vertical rhythm via `margin` is preferred over `<hr>` elements. When a divider is needed: `1px solid --ck-ink at 6% opacity`. Never a gradient divider.

---

## 6. Iconography

- **Library:** Lucide or Phosphor icons (outline weight only)
- **Size:** 16px for inline UI, 20px for actions, 24px for feature icons, 32px max for decorative
- **Color:** inherits text color by default; may use `--ck-teal` for branded icon moments
- **No icon + label redundancy** — if an icon is self-explanatory (search, close, menu), no label needed; if the action is non-obvious, always pair with a label
- **The crow mascot** is a brand asset, not a generic icon. Use it only in logo lockups, hero sections, and social profile contexts. Never scale it below `40px` or use it in-line with body text.

---

## 7. Imagery & Media

### Illustration / graphics

- Flat vector style, consistent with the mascot's graphic treatment
- Palette must pull from brand tokens — teal, ink, cyan, off-white
- No photorealistic 3D renders or stock photo developer imagery
- Abstract code / terminal UI screenshots are acceptable as supporting visuals if they are authentic (real code, real output)

### Video thumbnails

- Dark background (`#111110`)
- `--ck-teal` or `--ck-cyan` as the primary accent color for title text
- Face shots of the creator are welcome — authenticity over polish
- Consistent typographic treatment: Space Grotesk, two-color wordmark rule applies to any mention of the brand name

### Social embeds (YouTube, TikTok, Instagram)

- Embed containers use the standard card treatment (10px radius, 1px border)
- Platform branding colors are permitted within the embed widget itself — do not override them
- Caption text below embeds: `text-small`, `--ck-muted`

---

## 8. Motion & Animation

coderkrow's stack uses **anime.js**. All animation should feel intentional and developer-crafted — not bouncy, not flashy.

### Principles

- **Enter animations only.** Elements animate in; they do not animate out unless navigating away from a page.
- **Duration:** 200ms–400ms for UI transitions; 500ms–800ms for page-level entrances.
- **Easing:** `easeOut` for enter, `easeIn` for exit. No spring physics on layout elements — use springs only on interactive drag/cursor-follow effects if any.
- **Stagger on lists:** when a grid of cards or a list of items enters, stagger by `60ms` per item, max `400ms` total delay.

### Permitted animations

| Element | Animation |
|---|---|
| Page hero heading | Fade up, `translateY: [16, 0]`, `opacity: [0, 1]`, 600ms easeOutExpo |
| Cards on scroll | Fade up, `translateY: [24, 0]`, `opacity: [0, 1]`, stagger 60ms via `anime.stagger(60)` |
| Nav on scroll | `backgroundColor` opacity fade-in at scroll threshold, 200ms linear |
| CTA button hover | CSS `transform: scale(1.02)`, 150ms ease-out (no anime.js needed for hover) |
| Code block cursor | CSS blink keyframe, 1s step-end infinite, `--ck-cyan` color |
| Tag hover | CSS color + border-color transition, 150ms ease |
| Mascot logo | `translateY: [0, -6]`, `loop: true`, `direction: 'alternate'`, 3000ms easeInOutSine |

### Forbidden animations

- Parallax scrolling on background layers
- Spinning loaders (use skeleton screens or a simple opacity pulse)
- Slide-in drawers / panels on desktop (use in-place expand)
- Any animation that causes layout shift

### Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  /* All transitions collapse to opacity-only at 200ms */
  * { transition-duration: 200ms !important; animation-duration: 200ms !important; }
  /* Transforms are disabled; only opacity changes remain */
}
```

---

## 9. Voice & Content Rules

These rules apply to any copy the agent writes for page headings, CTAs, section labels, and descriptions.

### Tone

- **Direct.** Never pad. "Learn Astro in 20 minutes" beats "Discover the amazing world of Astro with this comprehensive guide."
- **Technical without being exclusive.** Write for working developers, not for beginners who have never opened a terminal, and not for PhDs who want proof of your rigor.
- **First person, singular.** "I build in public." Not "We create content." This is a personal brand.
- **Lower-case brand name always** — `coderkrow`, never `CoderKrow` or `CODERKROW`. The wordmark is always lowercase, even at the start of a sentence when used as a proper noun in running text (use alternate phrasing to avoid sentence-starting the brand name).

### Heading patterns

```
✅ "Building a router from scratch"
✅ "Why I rewrote it in Rust"
✅ "The parts of Astro no one talks about"
✅ "Ship faster. Break less."

❌ "Unlock the power of modern web development"
❌ "Your Ultimate Guide to TypeScript"
❌ "Welcome to my coding journey!"
❌ "Empowering developers worldwide"
```

### CTA copy

- Primary CTA: action verbs, no filler — "Watch now", "Read post", "Copy snippet"
- Secondary CTA: "See all videos", "Browse by topic"
- No exclamation marks on CTAs
- No "Click here" or "Learn more" alone without context

### Metadata & timestamps

- Dates: `Jun 29, 2026` — no ordinals, no spelled-out months in dense contexts
- Read time: "8 min read" — always lowercase, no period
- View counts: abbreviated — "12.4K views", not "12,432 views"
- Tags: lowercase, no hashtag prefix in UI — `astro`, `typescript`, `web-performance`

---

## 10. Do / Don't Reference

| Do | Don't |
|---|---|
| Use `--ck-teal` for interactive elements | Use teal as a background on large sections |
| Keep headings at weight 400–500 | Add `font-weight: 700` or `bold` anywhere |
| Use `--ck-cyan` for code highlights and active states | Use cyan as paragraph text or on large fills |
| Always show the mascot at ≥ 40px | Crop, recolor, or restyle the crow mascot |
| Dark backgrounds on code blocks always | Light-mode code blocks |
| Sentence case on all headings | Title Case on headings |
| `coderkrow` lowercase everywhere | `CoderKrow`, `CODERKROW`, `Coderkrow` |
| Space Grotesk as display/body font | Inter, Roboto, Arial, or generic sans-serif |
| JetBrains Mono for all code | Courier, Monaco, or monospace fallback-only |
| 8px-based spacing grid | Arbitrary spacing values (e.g. `13px`, `22px`) |
| Border-radius `6–12px` on components | `border-radius: 9999px` on non-pill elements |
| Flat, planarity-based UI (no shadows) | Drop shadows, blur backgrounds, card lifts |
| Authentic developer screenshots | Stock photos of keyboards / screens |
| Reduced motion compliance | Ignoring `prefers-reduced-motion` |
| Ship light + dark, with a visible toggle | Ship one theme only, or a hidden/icon-only toggle |

---

## 11. Prohibited Patterns

The following must **never appear** in any generated design or content:

1. Purple or violet as any part of the color palette
2. Gradient text (especially multi-color gradient on headings)
3. Glassmorphism / frosted blur card surfaces
4. Neumorphic soft-shadow UI
5. Parallax hero backgrounds
6. Animated gradient mesh backgrounds
7. AI-generated photorealistic imagery
8. Any font other than Space Grotesk / Outfit / JetBrains Mono
9. Animated emoji or Lottie decoration
10. Social proof layouts with fake-looking star ratings or avatar clusters

---
