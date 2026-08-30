---
version: 1.4.0
name: oPanel-Design-System
description: "High-density e-commerce analytics system combining Apple HIG minimalism (SF Pro Text, negative tracking, tabular nums, 1px hairlines, 18px cards) with an Open Macaron pastel tone system (five hue shells, light pastel + dark ganache pairs), rigid left/right table alignment, fluid motion, and morphing Tabler icons."

colors:
  # Source of truth: frontend/src/theme/tokens.ts, the --opanel-* variables in
  # frontend/src/styles/tokens.css (:root and :root[data-theme="dark"]), and
  # frontend/src/theme/naive-theme.ts (maps the same tokens onto Naive UI).

  # Brand & Core Interactive (Apple Action Blue)
  primary-light: "#0066CC"
  primary-focus-light: "#0071E3"
  primary-dark: "#2997FF"
  primary-focus-dark: "#47A7FF"
  primary-soft-light: "rgba(0, 102, 204, 0.08)"
  primary-soft-dark: "rgba(41, 151, 255, 0.15)"

  # Light Theme Canvas & Surfaces (--opanel-bg / tokens.light.canvas)
  canvas-light: "#F5F5F7"
  panel-light: "rgba(255, 255, 255, 0.88)"
  panel-solid-light: "#FFFFFF"
  panel-hover-light: "#FAFAFC"
  ink-light: "#1D1D1F"
  ink-muted-light: "#7A7A7A"
  line-light: "rgba(0, 0, 0, 0.08)"

  # Dark Theme Canvas & Surfaces
  canvas-dark: "#151419"
  panel-dark: "rgba(28, 26, 36, 0.85)"
  panel-solid-dark: "#1E1B26"
  panel-hover-dark: "#262330"
  ink-dark: "#F6F5F8"
  ink-muted-dark: "#9E9AA8"
  line-dark: "rgba(255, 255, 255, 0.08)"

  # Status & Feedback Tones (iOS system colors; dark values from tokens.ts)
  danger-light: "#FF3B30"
  danger-dark: "#FF453A"
  warning-light: "#FF9500"
  warning-dark: "#FF9F0A"
  success-light: "#34C759"
  success-dark: "#32D74B"

  # Macaron Tone System — the only tone mechanism. Five distinct hue shells,
  # each a light pastel background with high-contrast ganache ink text, and a
  # dark deep background with bright ink. Values live in theme/tokens.ts and
  # the --opanel-tone-*-bg/-text variables in styles/tokens.css; applied via
  # the shared .tone-* classes in styles/components.css. Never hardcode or
  # re-derive these hexes in feature CSS.
  tones:
    azure:    { hue: "blue",   light: { bg: "#EBF3FF", text: "#0066CC" }, dark: { bg: "#172A46", text: "#6CAFFF" }, role: "GMV & primary metrics" }
    lavender: { hue: "purple", light: { bg: "#F0EDFF", text: "#5944B3" }, dark: { bg: "#312847", text: "#BBA8FF" }, role: "Timeliness, pending & disputes" }
    mint:     { hue: "green",  light: { bg: "#E6F7F0", text: "#127546" }, dark: { bg: "#16382C", text: "#7EE0B3" }, role: "Success, fulfillment & healthy state" }
    peach:    { hue: "red",    light: { bg: "#FFEBEA", text: "#C42B24" }, dark: { bg: "#3D2226", text: "#FF859F" }, role: "Danger, cancellations & risk" }
    butter:   { hue: "amber",  light: { bg: "#FFF5E5", text: "#B86614" }, dark: { bg: "#3D2B19", text: "#FFAE61" }, role: "Warning, rates & payout states" }

alignment:
  grid-unit: "8px"
  baseline-grid: "4px"
  columns:
    text: "left"
    numeric: "right"
    actions: "right"
  status: "status tags render inline inside left/right-aligned content cells; no dedicated centered status column"
  tabular-nums: true
  optical-icon-centering: true

typography:
  # One stack for all text (styles/base.css body); no separate display face is loaded.
  font-family-body: "SF Pro Text, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', Roboto, sans-serif"
  font-family-mono: "'SF Mono', ui-monospace, Menlo, Monaco, Consolas, monospace"

  scale:
    hero-title:
      size: "24px"
      weight: 700
      tracking: "-0.025em"
      selector: ".opanel-heading h1"
    panel-title:
      size: "16px"
      weight: 650
      tracking: "-0.015em"
    kpi-value:
      size: "28px"
      weight: 750
      tracking: "-0.025em"
      line-height: 1.15
      font-variant-numeric: "tabular-nums"
    body:
      size: "14px"
      weight: 400
      line-height: 1.5
      tracking: "-0.006em"
    caption:
      size: "12px"
      weight: 500
      line-height: 1.4
      tracking: "-0.002em"
    numbers:
      font-variant-numeric: "tabular-nums"

shapes:
  rounded-pill: "9999px"
  rounded-card: "18px"
  rounded-input: "10px"
  rounded-sm: "8px"
  rounded-xs: "4px"

physics:
  # Fluid easing is the only CSS easing (--opanel-ease-fluid); icon morphs use
  # morphicons' spring physics with the shared "snappy" preset.
  ease-fluid: "cubic-bezier(0.16, 1, 0.3, 1)"
  spring: "snappy (ζ=0.73, fast with subtle overshoot) — smooth/bouncy available per-call"
  # Press feedback = scale transform, never a color change (Apple HIG):
  #   containers: sidebar footer buttons scale(0.95), menu items scale(0.97), drag panels scale(0.995)
  #   icons: .morph-icon inside any clicked button/link scales to 0.88 (excluded where the container already scales)
  press-scale: "containers 0.95 – 0.995; icons 0.88 inside interactive elements"
  # Icon state changes morph via <MorphIcon>; motion respects the user's
  # reduced-motion preference (reduced-motion="user").
  icon-morph: "src/shared/components/MorphIcon.vue (morphicons/vue)"

iconography:
  system: "Tabler Icons 24x24 stroke paths — hand-curated registry in frontend/src/shared/icons/tabler.ts (add new icons there), rendered through frontend/src/shared/components/MorphIcon.vue, a thin wrapper over morphicons/vue MorphIcon"
  stroke: "views pass stroke-width 1.8–2; component default is 1.5"
  morphing: "icon swaps animate as spring morphs (snappy preset); press feedback scales the icon to 0.88 while active; honors prefers-reduced-motion"
---

# Design Philosophy

### 1. Open Macaron × Apple HIG Synergy
- **Open Macaron Tone System**: Replaces sterile, fatiguing dashboard tables with breathable, low-saturation macaron card shells — five distinct hues (azure/lavender/mint/peach/butter), each pairing a pastel background with high-contrast ganache ink in light theme and a deep shell with bright ink in dark theme. One definition per theme in `styles/tokens.css`; no runtime derivation.
- **Apple Architectural Rigor**: 1px crisp hairlines (`rgba(0,0,0,0.08)` / `rgba(255,255,255,0.08)`), negative display tracking (`-0.015em` to `-0.025em`), and 18px card radii.
- **Single Token Source**: `frontend/src/theme/tokens.ts` (consumed by `naive-theme.ts` for Naive UI overrides) and the `--opanel-*` variables in `frontend/src/styles/tokens.css` mirror each other; never hardcode theme hexes in views.

### 2. High-Density Data Clarity
- All numeric metrics, currency amounts, order numbers, and timestamps enforce `font-variant-numeric: tabular-nums` to eliminate visual jitter and guarantee columnar alignment.
- Minimal chrome: decorative containers recede so operational insights take focus.

### 3. Rigid Table Alignment & Spatial Rhythm
- **Text Left, Numbers Right, Actions Right**: SKU, titles, and strings align left for scanning; GMV, piece counts, and percentages align right with tabular digits for vertical magnitude comparison; action buttons/columns align right. Status and metadata tags render inline within left/right-aligned cells rather than in a dedicated centered column.
- **8pt Spatial Grid**: Padding, margins, and gaps follow rigid 8px increments (`8px / 16px / 24px / 32px`).
- **Optical Vertical Centering**: Icon-text pairs are optically centered against font x-height to prevent baseline drift.

### 4. Fluid Motion & Morphing Icons
- Transitions use the shared fluid easing `--opanel-ease-fluid: cubic-bezier(0.16, 1, 0.3, 1)`; hover color/background/transform changes always animate, never snap.
- **Press feedback is a scale transform, never a color change** (Apple HIG): containers compress by surface size (0.95–0.995), and any icon inside a pressed button/link compresses to 0.88 — without compounding on surfaces whose container already scales.
- **Icon morphing is a core behavior**: icon state changes (theme toggle, status flips, menu icons) go through `<MorphIcon>` (`frontend/src/shared/components/MorphIcon.vue`), which animates the swap with morphicons' spring physics (shared `snappy` preset) and honors the user's reduced-motion setting.

### 5. NCard KPI Card Anatomy & Grid Standards
All summary cards are Naive UI `NCard` (`:bordered="false"` plus a 1px `--opanel-line` border and `--opanel-shadow-sm` via CSS, 18px radius) sharing one anatomy and a per-domain class prefix:

- **Feature components**: `features/analytics/components/AnalyticsKpiCards.vue`, `features/alerts/components/AlertSummaryCards.vue`, `features/sync/components/SyncSummaryCards.vue`; the Dashboard builds its cards inline on the same pattern (`features/dashboard/dashboard.css`). Domain stylesheets `features/orders/orders.css` and `features/complaints/complaints.css` follow the same conventions — complaints adds deadline badges, copy buttons, and compensation previews on the same primitives.
- **Card Head**: left label `span` (13px, weight 550, muted) + top-right icon badge (`{prefix}-icon-badge`, `32x32px`, 8px radius, tone-tinted).
- **Metric Value (`strong`)**: `{prefix}-kpi-value` — `28px`, weight 750, letter-spacing `-0.025em`, `tabular-nums`. Multi-line money variant: `{prefix}-kpi-money` (15px, column flex).
- **Metric Note (`small`)**: `12px`, muted secondary text.
- **Tone Classes**: cards get the shared bare class `tone-{azure | lavender | mint | peach | butter}` (`styles/components.css`), which sets the macaron shell background and exposes `--tone-ink`; the metric value adds `tone-value` (ganache ink) and the icon badge `tone-badge` (13% ink tint). Feature stylesheets never redefine tone colors.
- **Grid Layout Standards**:
  - **5-Column Grid (`repeat(5, minmax(0, 1fr))`)**: Dashboard KPIs (`.dashboard-kpi-grid`).
  - **4-Column Grid (`repeat(4, minmax(0, 1fr))`)**: Analytics/Risk/Returns/Timeliness KPIs (`.analytics-kpi-grid`).
  - Both collapse responsively on narrow viewports (dashboard → 2 → 1, analytics → 3 → fewer).

### 6. Hairline-First Depth, Focus & Chrome
- **Hairlines over shadows**: surfaces are separated by 1px `--opanel-line` borders; shadows exist only as the whisper-soft `--opanel-shadow-sm` on cards. No decorative gradients anywhere.
- **Floating chrome uses backdrop blur**: sticky headers, sidebar, and overlay surfaces apply `backdrop-filter: blur(24px) saturate(180%)` over the translucent panel color — blur is functional (content floats under chrome), not decorative.
- **Focus ring**: keyboard focus (`:focus-visible` on buttons, links, `role="button"/"tab"`) gets `outline: 2px solid var(--opanel-primary-focus)` with `outline-offset: 2px`; text inputs keep Naive UI's own focus border.
- **Scrollbars**: 6px rounded overlay thumbs tinted from `--opanel-muted` (45%, hover 70%), transparent tracks (`styles/base.css`).
- **Global transitions**: background-color/border-color/color/box-shadow/transform transition over `0.16s var(--opanel-ease-fluid)` on buttons, links, cards, tags, inputs, and table cells — state changes animate, never snap. All motion collapses under `prefers-reduced-motion: reduce`.
- **Empty states**: every empty data state renders `shared/components/EmptyState.vue` — a primary-tinted circular icon badge, a bold title, and an optional hint line (or default slot for extra actions). Never use bare `NEmpty`.
- **Loading states**: KPI card grids show `NSkeleton` card skeletons while their data loads (Dashboard, Risk, Alerts summary, Analytics traffic); tables keep Naive UI's built-in loading spinner.
