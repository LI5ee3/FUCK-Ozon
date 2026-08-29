---
version: 1.3.0
name: oPanel-Design-System
description: "High-density e-commerce analytics system combining Apple HIG minimalism (SF Pro Text, negative tracking, tabular nums, 1px hairlines, 18px cards) with low-saturation harmonic card tints derived from semantic colors via color-mix, rigid left/right table alignment, fluid motion, and morphing Tabler icons."

colors:
  # Source of truth: frontend/src/theme/tokens.ts, the --opanel-* variables in
  # frontend/src/style.css (:root and :root[data-theme="dark"]), and
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

  # Card Tint System — the only tone mechanism. There are no fixed pastel hex
  # presets and no per-theme dark variants; card backgrounds and icon badges
  # are derived at runtime from the semantic variables above:
  #   card background: color-mix(in srgb, <source var> N%, var(--opanel-panel-solid))
  #   icon badge:      color-mix(in srgb, <status var> 13%, transparent) or var(--opanel-primary-soft)
  tones:
    azure:    { source: "--opanel-primary", background: "10%", badge: "var(--opanel-primary-soft)" }
    blue:     { source: "--opanel-primary", background: "6%",  badge: "var(--opanel-primary-soft)" }
    lavender: { source: "--opanel-primary", background: "7%",  badge: "var(--opanel-primary-soft)" }
    mint:     { source: "--opanel-success", background: "8%",  badge: "success 13%" }
    peach:    { source: "--opanel-danger",  background: "8%",  badge: "danger 13%" }

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
  # One stack for all text (style.css body); no separate display face is loaded.
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
  # Fluid easing is the only easing in the codebase (--opanel-ease-fluid).
  ease-fluid: "cubic-bezier(0.16, 1, 0.3, 1)"
  # Press feedback is per-component, not a global spring curve:
  #   sidebar footer buttons scale(0.95), menu items scale(0.97), drag panels scale(0.995)
  press-scale: "0.95 – 0.995 depending on component"
  # Icon state changes morph via <MorphIcon>; motion respects the user's
  # reduced-motion preference (reduced-motion="user").
  icon-morph: "src/components/MorphIcon.vue (morphicons/vue)"

iconography:
  system: "Tabler Icons 24x24 stroke paths — hand-curated registry in frontend/src/icons/tabler.ts (add new icons there), rendered through frontend/src/components/MorphIcon.vue, a thin wrapper over morphicons/vue MorphIcon"
  stroke: "views pass stroke-width 1.8–2; component default is 1.5"
  morphing: "icon swaps animate as morphs; honors prefers-reduced-motion"
---

# Design Philosophy

### 1. Tint-Harmonic Palette × Apple HIG Synergy
- **Open Macaron Harmonic Tints**: Replaces sterile, fatiguing dashboard tables with breathable, low-saturation card shells derived from the semantic status colors via `color-mix`, so light and dark themes adapt automatically from one definition. High-contrast ink text sits on every shell.
- **Apple Architectural Rigor**: 1px crisp hairlines (`rgba(0,0,0,0.08)` / `rgba(255,255,255,0.08)`), negative display tracking (`-0.015em` to `-0.025em`), and 18px card radii.
- **Single Token Source**: `frontend/src/theme/tokens.ts` (consumed by `naive-theme.ts` for Naive UI overrides) and the `--opanel-*` variables in `frontend/src/style.css` mirror each other; never hardcode theme hexes in views.

### 2. High-Density Data Clarity
- All numeric metrics, currency amounts, order numbers, and timestamps enforce `font-variant-numeric: tabular-nums` to eliminate visual jitter and guarantee columnar alignment.
- Minimal chrome: decorative containers recede so operational insights take focus.

### 3. Rigid Table Alignment & Spatial Rhythm
- **Text Left, Numbers Right, Actions Right**: SKU, titles, and strings align left for scanning; GMV, piece counts, and percentages align right with tabular digits for vertical magnitude comparison; action buttons/columns align right. Status and metadata tags render inline within left/right-aligned cells rather than in a dedicated centered column.
- **8pt Spatial Grid**: Padding, margins, and gaps follow rigid 8px increments (`8px / 16px / 24px / 32px`).
- **Optical Vertical Centering**: Icon-text pairs are optically centered against font x-height to prevent baseline drift.

### 4. Fluid Motion & Morphing Icons
- Transitions use the shared fluid easing `--opanel-ease-fluid: cubic-bezier(0.16, 1, 0.3, 1)`.
- Press feedback is tactile but per-component (scale 0.95–0.995 depending on surface size); there is no global spring curve.
- **Icon morphing is a core behavior**: icon state changes (theme toggle, status flips, menu icons) go through `<MorphIcon>` (`frontend/src/components/MorphIcon.vue`), which animates the swap as a morph and honors the user's reduced-motion setting.

### 5. NCard KPI Card Anatomy & Grid Standards
All summary cards are Naive UI `NCard` (`:bordered="false"` plus a 1px `--opanel-line` border and `--opanel-shadow-sm` via CSS, 18px radius) sharing one anatomy and a per-domain class prefix:

- **Shared components**: `components/AnalyticsKpiCards.vue` (reused by Risk, Returns, Timeliness, and Complaints through the shared `views/analytics.css`), `components/AlertSummaryCards.vue`, `components/SyncSummaryCards.vue`; the Dashboard builds its cards inline on the same pattern (`views/dashboard.css`). Domain stylesheets `orders.css` and `complaints.css` follow the same conventions — complaints adds deadline badges, copy buttons, and compensation previews on the same primitives.
- **Card Head**: left label `span` (13px, weight 550, muted) + top-right icon badge (`{prefix}-icon-badge`, `32x32px`, 8px radius, tone-tinted).
- **Metric Value (`strong`)**: `{prefix}-kpi-value` — `28px`, weight 750, letter-spacing `-0.025em`, `tabular-nums`. Multi-line money variant: `{prefix}-kpi-money` (15px, column flex).
- **Metric Note (`small`)**: `12px`, muted secondary text.
- **Tone Classes**: `{prefix}-tone-{azure | blue | lavender | mint | peach}` apply the color-mix formulas defined in `colors.tones` above; icon badges re-tint via 13% transparent mixes of the matching status variable.
- **Grid Layout Standards**:
  - **5-Column Grid (`repeat(5, minmax(0, 1fr))`)**: Dashboard KPIs (`.dashboard-kpi-grid`).
  - **4-Column Grid (`repeat(4, minmax(0, 1fr))`)**: Analytics/Risk/Returns/Timeliness KPIs (`.analytics-kpi-grid`).
  - Both collapse responsively on narrow viewports (dashboard → 2 → 1, analytics → 3 → fewer).
