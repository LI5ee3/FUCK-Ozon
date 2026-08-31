---
version: 1.5.0
name: oPanel-Design-System
description: "High-density e-commerce analytics system combining Apple HIG minimalism (SF Pro Text, negative tracking, tabular nums, 1px hairlines, 18px cards) with an Open Macaron pastel tone system (five hue shells, light pastel + dark ganache pairs), rigid left/right table alignment, fluid motion, and morphing Tabler icons."

colors:
  # Source of truth: frontend/src/theme/tokens.ts, the --opanel-* variables in
  # frontend/src/styles/tokens.css (:root and :root[data-theme="dark"]), and
  # frontend/src/theme/naive-theme.ts (maps the same tokens onto Naive UI).

  # Brand & Core Interactive (Apple Action Blue)
  primary-light: "#0066CC"
  primary-focus-light: "#0071E3"
  primary-active-light: "#0055B3"
  primary-dark: "#2997FF"
  primary-focus-dark: "#47A7FF"
  primary-active-dark: "#1F7CD6"
  primary-soft-light: "rgba(0, 102, 204, 0.08)"
  primary-soft-dark: "rgba(41, 151, 255, 0.15)"

  # Light Theme Canvas & Surfaces (--opanel-bg / tokens.light.canvas)
  canvas-light: "#F5F5F7"
  panel-light: "rgba(255, 255, 255, 0.88)"
  panel-solid-light: "#FFFFFF"
  panel-hover-light: "#FAFAFC"
  ink-light: "#1D1D1F"
  ink-muted-light: "#6E6E73"
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
    azure:    { hue: "blue",   light: { bg: "#EBF3FF", text: "#0066CC" }, dark: { bg: "#172A46", text: "#6CAFFF" }, role: "GMV, FBP & primary overview metrics" }
    lavender: { hue: "purple", light: { bg: "#F0EDFF", text: "#5944B3" }, dark: { bg: "#312847", text: "#BBA8FF" }, role: "Timeliness, pending, disputes & system config" }
    mint:     { hue: "green",  light: { bg: "#E6F7F0", text: "#127546" }, dark: { bg: "#16382C", text: "#7EE0B3" }, role: "Success, realFBS fulfillment & supply chain" }
    peach:    { hue: "red",    light: { bg: "#FFEBEA", text: "#C42B24" }, dark: { bg: "#3D2226", text: "#FF859F" }, role: "Danger, cancellations, risk & exceptions" }
    butter:   { hue: "amber",  light: { bg: "#FFF5E5", text: "#A85A0D" }, dark: { bg: "#3D2B19", text: "#FFAE61" }, role: "Warning, WHD channel, ads & rates" }

semantic-tones:
  channels:
    FBP: "azure"
    realFBS: "mint"
    WHD: "butter"
  navigation-groups:
    overview:               { label: "业务概览", tone: "azure" }
    advertising:            { label: "广告管理", tone: "butter" }
    fulfillment-exceptions: { label: "履约与异常", tone: "peach" }
    supply-data:            { label: "供应链与数据", tone: "mint" }
    system-config:          { label: "系统配置", tone: "lavender" }

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
    eyebrow:
      size: "11px"
      weight: 650
      tracking: "0.08em"
      transform: "uppercase"
      selector: ".opanel-eyebrow"
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

component-shapes:
  card: "rounded-card"
  inset-surface: "rounded-sm"
  input: "rounded-input"
  select: "rounded-input"
  date-picker: "rounded-input"
  action-button: "rounded-input"
  filter-chip: "rounded-pill"
  date-preset: "rounded-pill"
  segmented-container: "rounded-pill"
  segmented-active: "rounded-pill"
  status-tag: "rounded-pill"
  channel-tag: "rounded-pill"
  icon-button: "rounded-pill"

surfaces:
  canvas:
    background: "canvas"
  primary-panel:
    radius: "rounded-card"
    border: "1px solid hairline"
    shadow: "shadow-sm"
  inset-surface:
    radius: "rounded-sm"
    background: "panel-hover"
    shadow: "none"
  nested-card-depth:
    max: 1

breakpoints:
  compact: "640px"
  navigation-collapse: "800px"
  dense-layout: "1100px"
  wide: "1200px"

layers:
  content: 0
  local-sticky: 2
  app-header: 10
  app-floating: 20
  library-overlay: "managed by Naive UI"

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

# Design Philosophy & System Architecture

### 1. Open Macaron × Apple HIG Synergy
- **Open Macaron Tone System**: Replaces sterile, fatiguing dashboard tables with breathable, low-saturation macaron card shells — five distinct hues (azure/lavender/mint/peach/butter), each pairing a pastel background with high-contrast ganache ink in light theme and a deep shell with bright ink in dark theme. One definition per theme in `styles/tokens.css`; no runtime derivation.
- **Apple Architectural Rigor**: 1px crisp hairlines (`rgba(0,0,0,0.08)` / `rgba(255,255,255,0.08)`), negative display tracking (`-0.015em` to `-0.025em`), and 18px card radii.
- **Single Source of Truth Architecture**: Design rules live in `DESIGN.md`, runtime token values in `theme/tokens.ts`, CSS custom properties mirror in `styles/tokens.css`, and Naive UI maps them via `naive-theme.ts`. Never hardcode theme hexes in feature views.

### 2. High-Density Data Clarity
- All numeric metrics, currency amounts, order numbers, and timestamps enforce `font-variant-numeric: tabular-nums` to eliminate visual jitter and guarantee columnar alignment.
- Minimal chrome: decorative containers recede so operational insights take focus.

### 3. Table Alignment & Spatial Rhythm
- **Text Left, Numbers Right, Actions Right**: SKU, titles, and strings align left for scanning; GMV, piece counts, and percentages align right with tabular digits for vertical magnitude comparison; action buttons/columns align right. Status and metadata tags render inline within left/right-aligned cells rather than in a dedicated centered column.
- **8pt Spatial Grid**: Padding, margins, and gaps follow rigid 8px increments (`8px / 16px / 24px / 32px`), with a 4px baseline grid for fine adjustments.
- **Optical Vertical Centering**: Icon-text pairs are optically centered against font x-height to prevent baseline drift.

### 4. Fluid Motion & Morphing Icons
- Transitions use the shared fluid easing `--opanel-ease-fluid: cubic-bezier(0.16, 1, 0.3, 1)`; hover color/background/transform changes always animate, never snap.
- **Press feedback is a scale transform, never a color change** (Apple HIG): containers compress by surface size (0.95–0.995), and any icon inside a pressed button/link compresses to 0.88 — without compounding on surfaces whose container already scales.
- **Icon morphing is a core behavior**: icon state changes (theme toggle, status flips, menu icons) go through `<MorphIcon>` (`frontend/src/shared/components/MorphIcon.vue`), which animates the swap with morphicons' spring physics (shared `snappy` preset) and honors the user's reduced-motion setting.

### 5. KPI Card Anatomy & Grid Standards
All summary cards are Naive UI `NCard` (`:bordered="false"` plus a 1px `--opanel-line` border and `--opanel-shadow-sm` via CSS, 18px radius) sharing one anatomy and a per-domain class prefix:

- **Feature components**: `features/analytics/components/AnalyticsKpiCards.vue`, `features/alerts/components/AlertSummaryCards.vue`, `features/sync/components/SyncSummaryCards.vue`; the Dashboard builds its cards inline on the same pattern (`features/dashboard/dashboard.css`). Domain stylesheets `features/orders/orders.css` and `features/complaints/complaints.css` follow the same conventions.
- **Card Head**: left label `span` (13px, weight 550, muted) + top-right icon badge (`{prefix}-icon-badge`, `32x32px`, 8px radius, tone-tinted).
- **Metric Value (`strong`)**: `{prefix}-kpi-value` — `28px`, weight 750, letter-spacing `-0.025em`, `tabular-nums`. Multi-line money variant: `{prefix}-kpi-money` (15px, column flex).
- **Metric Note (`small`)**: `12px`, muted secondary text.
- **Tone Classes**: cards get the shared bare class `tone-{azure | lavender | mint | peach | butter}` (`styles/components.css`), which sets the macaron shell background and exposes `--tone-ink`; the metric value adds `tone-value` (ganache ink) and the icon badge `tone-badge` (13% ink tint). Feature stylesheets never redefine tone colors.
- **Grid Layout Standards**:
  - **5-Column Grid (`repeat(5, minmax(0, 1fr))`)**: Dashboard KPIs (`.dashboard-kpi-grid`).
  - **4-Column Grid (`repeat(4, minmax(0, 1fr))`)**: Analytics/Risk/Returns/Timeliness KPIs (`.analytics-kpi-grid`).
  - Both collapse responsively on narrow viewports (dashboard → 2 → 1, analytics → 3 → fewer).

### 6. Hairline-First Depth & Chrome
- **Hairlines over shadows**: surfaces are separated by 1px `--opanel-line` borders; shadows exist only as the whisper-soft `--opanel-shadow-sm` on cards. No decorative gradients anywhere.
- **Floating chrome uses backdrop blur**: sticky headers, sidebar, and overlay surfaces apply `backdrop-filter: blur(24px) saturate(180%)` over the translucent panel color — blur is functional (content floats under chrome), not decorative.
- **Focus ring**: keyboard focus (`:focus-visible` on buttons, links, `role="button"/"tab"`) gets `outline: 2px solid var(--opanel-primary-focus)` with `outline-offset: 2px`; text inputs keep Naive UI's own focus border.
- **Scrollbars**: 6px rounded overlay thumbs tinted from `--opanel-muted` (45%, hover 70%), transparent tracks (`styles/base.css`).
- **Global transitions**: background-color/border-color/color/box-shadow/transform transition over `0.16s var(--opanel-ease-fluid)` on buttons, links, cards, tags, inputs, and table cells — state changes animate, never snap. All motion collapses under `prefers-reduced-motion: reduce`.
- **Empty states**: every empty data state renders `shared/components/EmptyState.vue` — a primary-tinted circular icon badge, a bold title, and an optional hint line (or default slot for extra actions). Never use bare `NEmpty`.
- **Loading states**: KPI card grids show `NSkeleton` card skeletons while their data loads (Dashboard, Risk, Alerts summary, Analytics traffic); tables keep Naive UI's built-in loading spinner.

---

### 7. Semantic Colors & Business Tone Mapping
The 5 Macaron tones are directly bound to core business semantics across the entire system. Feature stylesheets must never invent custom color mappings or redefine tone classes.

- **Fulfillment Channels**:
  - `FBP` (Fulfillment by Partner) $\rightarrow$ `azure` (`.tone-azure`, `--opanel-tone-azure-bg`, `--opanel-tone-azure-text`)
  - `realFBS` (Real Fulfillment by Seller) $\rightarrow$ `mint` (`.tone-mint`, `--opanel-tone-mint-bg`, `--opanel-tone-mint-text`)
  - `WHD` (Warehouse Dropship) $\rightarrow$ `butter` (`.tone-butter`, `--opanel-tone-butter-bg`, `--opanel-tone-butter-text`)
- **Navigation Groups** (`frontend/src/app/router/navigation.ts`):
  - **业务概览** (Overview, Orders, Analytics) $\rightarrow$ `azure`
  - **广告管理** (Ads Overview, Campaigns, SKU Ads) $\rightarrow$ `butter`
  - **履约与异常** (Timeliness, Risk, Returns, Alerts, Complaints) $\rightarrow$ `peach`
  - **供应链与数据** (Inventory, Profit, Transfer, Sync) $\rightarrow$ `mint`
  - **系统配置** (Rules, Push Subscriptions, DingTalk) $\rightarrow$ `lavender`
- **Feedback & Status Tags**:
  - `Delivered / Healthy / Success` $\rightarrow$ `mint` (or Naive `success`)
  - `Shipping / In Transit / Warning` $\rightarrow$ `butter` (or Naive `warning`)
  - `Cancelled / Dispute / High Risk` $\rightarrow$ `peach` (or Naive `error` / `.is-danger`)
  - `Pending / Awaiting Action` $\rightarrow$ `lavender`
  - `Neutral / Informational` $\rightarrow$ `azure` (or Naive `info`)

---

### 8. Component Shapes & Surface Hierarchy (Anti-Boxification)
To eliminate the "sterile square dashboard" effect where everything renders as a blocky card inside a blocky card, strictly enforce the following shape semantics and surface hierarchy:

#### A. Component Shape Contracts
| Shape Radius | CSS Value | Assigned Components | Prohibited Uses |
| :--- | :--- | :--- | :--- |
| **Pill (`rounded-pill`)** | `9999px` | Date Presets, Filter Chips, Segmented Containers & Active Sliders, Status Tags, Channel Tags, Round Icon Buttons | Primary Cards, Tables, Modals |
| **Card (`rounded-card`)** | `18px` | Outer KPI Cards, Top-level Feature Panels, Modals | Buttons, Tags, Inset Sub-panels |
| **Input (`rounded-input`)** | `10px` | Text Inputs, Select Dropdowns, DatePickers, Action/Submit Buttons | KPI Cards, Status Tags |
| **Small (`rounded-sm`)** | `8px` | Inset Surfaces, KPI Icon Badges, Table Expandable Details, Nav Items | Main Panels, Outer Cards |
| **Extra-Small (`rounded-xs`)** | `4px` | Tiny Indicators, Compact Progress Bars | Buttons, Cards |

#### B. Surface Hierarchy & Depth Rules
1. **Canvas (`--opanel-bg`)**: The background layer (`#F5F5F7` / `#151419`).
2. **Primary Panel (`--opanel-panel-solid`)**: 18px card radius, 1px `--opanel-line` border, `--opanel-shadow-sm`.
3. **Inset Surface (`--opanel-panel-hover`)**: 8px radius (`rounded-sm`), subtle tinted/translucent background, **no box shadow**, optional 1px hairline border.
4. **Anti-Boxification Rule (Max Card Depth = 1)**:
   > **Never nest a bordered 18px/10px Card inside another Card.**
   > Internal structure within a panel must be achieved using **dividers, whitespace (8px grid), subtle typography scale, and lightweight inset surfaces** (`background: var(--opanel-panel-hover)` with 8px radius).

---

### 9. Data Visualization & ECharts Contract
All charts (e.g. `OrderTrendChart.vue`, `AdsTrendChart.vue`) adhere to a unified visual contract mirroring Apple HIG and Macaron tokens:

- **ECharts Theme Mapping**:
  - **Font**: `fontFamily: macaronTokens.fontFamily` (SF Pro Text stack).
  - **Grid & Split lines**: `splitLine: { lineStyle: { color: colors.line, type: "dashed" } }`.
  - **Axes**: `axisLine: { lineStyle: { color: colors.line } }`, `axisTick: { show: false }`, `axisLabel: { color: colors.muted }`.
  - **Series Lines**: `smooth: true`, `symbol: "circle"`, `symbolSize: 7`, `lineStyle: { width: 2.5 }`.
  - **Area Gradient**: Area fill uses series primary color with opacity `0.12` in Light Theme and `0.20` in Dark Theme.
- **Apple-Style Tooltip Anatomy (`.dashboard-chart-tooltip`)**:
  - `backgroundColor: colors.panelSolid`, `borderColor: colors.line`, `borderWidth: 1`.
  - Content structure: Header date + status badge, bold total headline (`font-size: 16px`, `tabular-nums`), hairline divider (`margin: 8px 0`), followed by channel/metric breakdown rows with 7px circular color dots (`.dashboard-chart-tooltip-dot--fbp/fbs/whd`).
- **Multi-Series Colors**: Multi-metric charts must consume Macaron tones (`azure` for primary, `mint` for secondary, `butter` for tertiary, `peach` for comparison/cost).

---

### 10. Filter Toolbar & Segmented Controls
Every list and analytics view features a standardized top toolbar:

- **Layout**: `display: flex; align-items: center; justify-content: space-between; gap: 8px 12px; flex-wrap: wrap; margin-bottom: 16px;`.
- **Date Presets & Segmented Controls**:
  - Render as pill capsules (`rounded-pill`).
  - Active preset gets solid/tinted background with bold ganache text (`font-weight: 650`); inactive presets remain ghost/muted with soft hover.
  - Never render date presets as disjointed square buttons.
- **Search & Select Inputs**:
  - Inputs (`NInput`) and Selects (`NSelect`) use `10px` radius (`rounded-input`).
  - Search inputs must feature a leading search icon, clear button (`clearable`), and automatic 300ms debounce.
- **Live Status Indicator**:
  - Real-time/sync status tags feature a 7px pulsing dot (`.dashboard-data-dot`) with a 2px semi-transparent ring.

---

### 11. Complex Data Tables & Inset Panels
- **Table Density**: High-density display with fixed header support (`sticky`), row padding `10px 14px`.
- **Column Alignment**: Text strings left, numeric values and currency amounts right (`tabular-nums`), action buttons right.
- **Inline Status & Channel Tags**: Render as pill tags (`rounded-pill`, padding `2px 8px`, font size `11.5px`) directly inside text or numeric cells. Do not create dedicated centered status columns.
- **Expandable Rows & Detail Sub-panels (e.g. `OrderDetailPanel.vue`)**:
  - The expansion container uses `background: var(--opanel-panel-hover)` and `border-radius: var(--opanel-radius-sm)`.
  - Inner information uses a multi-column grid with labeled key-value rows (`label: muted 12px`, `value: text 13px tabular-nums`).
  - Embedded sub-tables must NOT have outer card borders or redundant shadows.

---

### 12. Modals, Drawers & System Feedback
- **Modals (`NModal`)**: 18px border radius, solid panel background, 1px `--opanel-line` border, backdrop blur on mask (`backdrop-filter: blur(12px)`).
- **Drawers (`NDrawer`)**: Docked to right viewport edge, translucent panel background with `backdrop-filter: blur(24px) saturate(180%)`.
- **Action Buttons Layout**: Footer action buttons align right: `Cancel` (Quaternary/Default, left) and `Confirm/Save` (Primary Action Blue, right). Destructive actions use `Danger` red button.
- **Feedback Hierarchy**:
  - `useMessage` (Toast): Transient feedback (success/copy/info), auto-dismissing in 2.5s–3s.
  - `NAlert`: In-page persistent error or warning banners with soft background and 10px radius.
  - `useDialog`: Irreversible actions (e.g. Delete, Logout, Sync Reset) requiring explicit user confirmation.

---

### 13. Responsive & Density Strategy
Responsive behavior follows explicit semantic breakpoints rather than ad-hoc pixel values:

| Breakpoint Key | Value | Semantic Layout Behavior |
| :--- | :--- | :--- |
| **`compact`** | `< 640px` | Mobile portrait: Single-column KPI cards, toolbar stacks vertically, tables scroll horizontally with sticky action column. |
| **`navigation-collapse`**| `< 800px` | Tablet / small laptop: Sidebar collapses to 0-width (trigger bar / drawer mode), header actions wrap, KPI cards collapse to 2 columns. |
| **`dense-layout`** | `< 1100px` | Medium desktop: 5-column KPI cards gracefully fold to 3 or 2 columns; table secondary columns hide or move to detail expansion. |
| **`wide`** | `> 1200px` | Full high-density view: Full 5-col / 4-col KPI grids, expanded multi-column data tables, side-by-side analytics charts. |

---

### 14. Interaction States, Copy & Accessibility
- **Disabled State**: Elements with `disabled` or `aria-disabled="true"` receive `opacity: 0.45` and `cursor: not-allowed`. Hover and active transforms are suppressed.
- **One-Click Copy Interaction**: Order numbers, SKUs, and tracking numbers feature a compact copy icon button (`16x16px` icon). Clicking triggers `<MorphIcon>` morphing to a checkmark for 700ms and fires `message.success("已复制")`.
- **Skeleton Standard**:
  - KPI Cards: Head title skeleton (`width: 60px; height: 14px`), Value skeleton (`.kpi-skeleton-value`, `height: 28px; width: 120px`).
  - Tables: 5 rows of `NSkeleton` with matching column widths.
  - Charts: Rounded 18px card containing a pulse skeleton rectangle.
- **Accessibility (A11y)**:
  - Every interactive icon-only button must provide `aria-label` and `title`.
  - All color pairings (Light Ganache on Pastel, Dark Ink on Deep Shell) must strictly pass WCAG AA contrast ratio ($\ge 4.5:1$).

---

### 15. Elevation, Layering & Single Source of Truth

Shadow tokens preserve two elevations in both themes: `shadowSm` mirrors `--opanel-shadow-sm` for cards; `shadow` mirrors the existing `--opanel-shadow` for medium elevation.

#### A. Logical Z-Index Layering
To prevent collisions between custom styling and UI library portals:
```yaml
layers:
  content: 0              # Normal page layout elements
  local-sticky: 2         # Sidebar sticky footer, table sticky headers
  app-header: 10          # Sticky top navigation header
  app-floating: 20        # Floating action bars, toolbars
  library-overlay:        # Managed entirely by Naive UI (Dropdown 1000, Modal 2000, Message 3000)
```

#### B. Single Source of Truth Architectural Contract
| Layer | File / Location | Responsibility |
| :--- | :--- | :--- |
| **Specification Truth** | `DESIGN.md` | Single source of truth for design rules, component anatomy, token semantics, and anti-patterns. |
| **Runtime Value Truth** | `frontend/src/theme/tokens.ts` | TypeScript token definitions consumed by JS/TS logic and theme builders. |
| **CSS Token Mirror** | `frontend/src/styles/tokens.css` | CSS Custom Properties (`--opanel-*`) mirroring `tokens.ts` for styling. |
| **UI Library Adapter** | `frontend/src/theme/naive-theme.ts` | Maps tokens directly into Naive UI `GlobalThemeOverrides`. |
| **Feature Views** | `frontend/src/features/*` | Pure consumers of tokens and shared components; prohibited from re-declaring semantic hexes or ad-hoc shapes. |
