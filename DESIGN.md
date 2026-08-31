---
version: 2.0.0
name: oPanel-Design-System
description: "Apple-based design language for a high-density e-commerce operations workspace, extended with oPanel's Open Macaron identity, business semantic tones, and resilient UI/UX rules."
authority:
  foundation: "Apple DESIGN.md"
  product-identity: "oPanel Open Macaron and high-density data-workspace rules"
  ux-supplement: "UI UX Pro Max — UI/UX quality guidance only"
  motion: "oPanel Motion / Physics rules in this document"
---

# oPanel Design System

This document is the upstream design specification for oPanel. It describes
how oPanel should be designed, not what any existing implementation happens to
render. New screens and future frontends must use this document as their design
contract.

## 1. Design Sources & Authority

The sources have a strict relationship:

1. **Apple DESIGN.md is the foundation.** It supplies the base visual language:
   quiet chrome, clear typography, restrained surfaces, hairlines, purposeful
   whitespace, precise alignment, and coherent light/dark expression.
2. **oPanel is the product identity.** Open Macaron tones, Apple Action Blue,
   high-density e-commerce operations, business semantics, tabular data,
   KPI-oriented summaries, existing chart language, and the existing icon
   system define what makes oPanel oPanel.
3. **UI UX Pro Max is a quality supplement.** Use its applicable guidance for
   information hierarchy, anti-boxification, content resilience, responsive
   behavior, accessibility, forms, feedback, navigation, tables, chart choice,
   and UX anti-patterns.

The supplement must not redefine oPanel's visual system. Do not use it to
automatically choose a new UI style, brand style, font family, color palette,
radius system, shadow system, or icon family. Do not turn oPanel into Material,
Fluent, Polaris, a generic SaaS dashboard, a Bento dashboard, Glassmorphism,
or a generic Tailwind admin UI.

If sources appear to conflict, preserve the Apple foundation and the verified
oPanel identity; apply UI UX Pro Max only where it improves UI/UX quality
without changing those identities. The motion boundary is defined in
[Motion / Physics](#14-motion--physics) and is not supplied by UI UX Pro Max.

Reference sources:

- [Apple DESIGN.md](https://getdesign.md/apple/design-md)
- [UI UX Pro Max Skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)

## 2. Design Philosophy

### Apple Foundation

oPanel uses Apple's visual restraint as its chassis: UI chrome recedes, text
and data remain crisp, surfaces are calm, and every visual treatment must have
a job. Hairlines, surface changes, alignment, and whitespace carry more weight
than decoration. Apple-style clarity is adapted for operations rather than
copied as a consumer product page.

### oPanel Identity

oPanel is an Open Macaron, high-density e-commerce operations workspace. Its
pastel-to-ganache light/dark pairs, five business tones, compact analytical
summaries, structured tables, KPI reading, and existing charts are product
identity—not optional themes and not recommendations to be replaced.

### Data First

The interface helps an operator answer three questions quickly:

1. What is happening now?
2. What needs attention?
3. What action or detail comes next?

Core metrics, status, time range, business context, and the primary action must
remain easy to find. Decorative composition must never compete with operational
meaning.

### High Density with Breathing Room

High density means more useful information per viewport, not smaller unreadable
text or tighter unrelated blocks. Keep related data close, separate unrelated
groups with whitespace, preserve the 8pt rhythm, and allow long content to
reflow. Dense tables may be compact; their hierarchy and scanability must stay
calm.

### Clarity Before Ornament

Use the smallest visual vocabulary that communicates context, state, value, and
action. Color is a semantic reinforcement, not a substitute for structure or
copy. A number, table, or plain label is preferable to a decorative widget
that conveys no additional decision value.

### Anti-Boxification as a Core Principle

The page is not a collection of equally weighted boxes. Do not create a new
bordered card merely because content needs grouping. Prefer whitespace,
typography hierarchy, dividers, alignment, section spacing, subtle background
difference, and lightweight inset surfaces.

The forbidden default is:

```text
Card
 ├── Card
 ├── Card
 │    └── Card
 └── Card
```

**Maximum Card Nesting Depth = 1.** Not every section needs a Card, not every
KPI needs equal visual weight, not every data block needs a border, and a page
must not become an equal-weight square grid.

## 3. Foundations

### 3.1 Colors and Semantic Tones

The existing oPanel palette is normative. Light and dark values are paired
expressions of the same role; do not invent feature-specific replacements.

#### Core and Surface Tokens

| Role | Light | Dark | Use |
|---|---|---|---|
| Apple Action Blue | `#0066CC` | `#2997FF` | Primary action, links, selected interactive emphasis |
| Focus Blue | `#0071E3` | `#47A7FF` | Visible keyboard focus |
| Active Blue | `#0055B3` | `#1F7CD6` | Existing active action tone |
| Soft Action Blue | `rgba(0, 102, 204, 0.08)` | `rgba(41, 151, 255, 0.15)` | Subtle interactive surface |
| Canvas | `#F5F5F7` | `#151419` | Page background |
| Panel | `rgba(255, 255, 255, 0.88)` | `rgba(28, 26, 36, 0.85)` | Translucent primary surface |
| Panel Solid | `#FFFFFF` | `#1E1B26` | Opaque surface and overlays |
| Panel Hover / Inset | `#FAFAFC` | `#262330` | Lightweight inset or hover surface |
| Ink | `#1D1D1F` | `#F6F5F8` | Primary text |
| Muted Ink | `#6E6E73` | `#9E9AA8` | Secondary text, never for critical meaning alone |
| Hairline | `rgba(0, 0, 0, 0.08)` | `rgba(255, 255, 255, 0.08)` | Dividers and quiet boundaries |
| Danger | `#FF3B30` | `#FF453A` | Destructive, error, exception |
| Warning | `#FF9500` | `#FF9F0A` | Warning, attention, pending risk |
| Success | `#34C759` | `#32D74B` | Successful, healthy, complete |

#### Open Macaron Tone System

These five tones are the only oPanel tone mechanism. Each tone has a light
pastel shell with high-contrast text and a dark deep shell with bright text.

| Tone | Light background / text | Dark background / text | Product role |
|---|---|---|---|
| Azure | `#EBF3FF` / `#0066CC` | `#172A46` / `#6CAFFF` | GMV, FBP, primary overview metrics |
| Lavender | `#F0EDFF` / `#5944B3` | `#312847` / `#BBA8FF` | Timeliness, pending, disputes, system configuration |
| Mint | `#E6F7F0` / `#127546` | `#16382C` / `#7EE0B3` | Success, realFBS fulfillment, supply chain |
| Peach | `#FFEBEA` / `#C42B24` | `#3D2226` / `#FF859F` | Danger, cancellations, risk, exceptions |
| Butter | `#FFF5E5` / `#A85A0D` | `#3D2B19` / `#FFAE61` | Warning, WHD, advertising, rates |

#### Business Mapping

| Business meaning | Tone |
|---|---|
| `FBP` / Fulfillment by Partner | Azure |
| `realFBS` / Real Fulfillment by Seller | Mint |
| `WHD` / Warehouse Dropship | Butter |
| Business overview | Azure |
| Advertising management | Butter |
| Fulfillment and exceptions | Peach |
| Supply chain and data | Mint |
| System configuration | Lavender |

Use existing semantic mappings consistently. `Delivered`, `Healthy`, and
`Success` use Mint; `Shipping`, `In Transit`, and `Warning` use Butter;
`Cancelled`, `Dispute`, and `High Risk` use Peach; `Pending` and `Awaiting
Action` use Lavender; neutral informational states use Azure. Every state also
needs a readable label, icon, shape, position, or other non-color signal.

### 3.2 Typography

The typography direction is SF Pro Text and the system fallback stack. Do not
introduce a second brand type system. Display text uses the existing negative
tracking to create an Apple-like compact cadence; small text must remain
readable and must not be tightened into illegibility.

```text
SF Pro Text, -apple-system, BlinkMacSystemFont, 'PingFang SC',
'Segoe UI', Roboto, sans-serif
```

Use the following scale as the shared hierarchy:

| Role | Size | Weight | Line height | Tracking | Notes |
|---|---:|---:|---:|---:|---|
| Eyebrow / context | 11px | 650 | 1.3 | `0.08em` | Uppercase only where language permits |
| Page title | 24px | 700 | 1.15 | `-0.025em` | Primary page identity |
| Panel title | 16px | 650 | 1.3 | `-0.015em` | Section and panel heading |
| KPI value | 28px | 750 | 1.15 | `-0.025em` | Always tabular numerals |
| Body | 14px | 400 | 1.5 | `-0.006em` | Default operational copy |
| Caption | 12px | 500 | 1.4 | `-0.002em` | Supporting metadata |

Rules:

- Use `font-variant-numeric: tabular-nums` for metrics, currency, counts,
  percentages, timestamps, and comparable numeric table values.
- Use the same hierarchy across a page; do not create arbitrary one-off sizes.
- Negative tracking is for display and larger headings; never use it to make
  12px or smaller text denser.
- Natural wrapping is preferred to forced line breaks. Headings may use
  balanced wrapping as a progressive enhancement, but must work without it.
- Keep a readable fallback stack for Chinese, English, and Russian. Do not
  assume one script's glyph width or line height.
- Use the existing SF Mono / system monospace stack only when a fixed-width
  identifier or code-like value benefits from it; typography must not make
  identifiers harder to scan.

### 3.3 Spacing and Rhythm

- The structural grid is 8px: `8 / 16 / 24 / 32px` are the default spacing
  steps.
- The fine baseline is 4px for icon alignment, compact controls, and
  typographic adjustments.
- `12px`, `20px`, and similar values are allowed only when they preserve a
  real control, text, or optical requirement; they do not create a new grid.
- Use spacing to show grouping: smaller gaps for related content, larger gaps
  between concepts, and section spacing for major changes in purpose.
- Do not use equal gaps everywhere when the information relationships are not
  equal.

### 3.4 Alignment

| Content | Alignment |
|---|---|
| Natural-language text | Left |
| Numeric values and currency | Right |
| Row and group actions | Right |
| Status and metadata | Inline in the owning left/right-aligned cell |

Use optical icon centering against the text x-height. Alignment is a scanning
tool: preserve it even when a visual composition would look more symmetrical
with centered content.

### 3.5 Shapes

The existing radius system is intentionally small:

| Token | Value | Assigned use |
|---|---:|---|
| Pill | `9999px` | Filter chips, date presets, segmented controls, status/channel tags |
| Card | `18px` | Outer KPI cards, top-level panels, modals |
| Input | `10px` | Inputs, selects, date controls, action buttons |
| Inset | `8px` | Inset surfaces, icon badges, expandable details, compact nav items |
| Fine | `4px` | Tiny indicators and compact progress elements |

Do not create arbitrary radii or use pill geometry on primary panels, tables,
or modals. Shape communicates component role and must remain consistent in
both themes.

### 3.6 Surfaces, Elevation, and Layering

Use surfaces in this order:

1. **Canvas:** page background.
2. **Primary panel:** use an 18px radius, a 1px oPanel hairline, and the
   existing whisper-soft oPanel card shadow only when an outer panel is truly
   needed.
3. **Inset surface:** use an 8px radius, a subtle panel-hover difference, and
   no shadow. An optional hairline may clarify a real boundary.
4. **Flat section:** use no border or shadow when whitespace and typography
   already express the relationship.

Hairlines come before shadows. No decorative gradients. Backdrop blur is
allowed only for functional floating chrome where content passes beneath it;
it is not a general surface treatment. Shadows must not be used to give every
block equal weight.

The logical layer order is:

```text
content       0
local-sticky  2
app-header    10
app-floating  20
library-overlay  managed by the UI layer
```

Sticky and overlay layers must reserve space, respect safe areas, and never
hide content or keyboard focus.

### 3.7 Iconography

Retain the existing curated Tabler-style 24x24 stroke icon system. Use one
coherent icon family, consistent optical weight, and the existing morphing icon
behavior. Typical view stroke width remains `1.8–2`; compact controls may use
the system default where optical balance requires it.

Icons have a semantic role:

- A decorative icon supports visible copy and may be hidden from the
  accessibility tree.
- An informational icon conveys independent meaning and needs a text
  equivalent.
- An interactive icon is a control and needs a clear accessible name.

Do not replace the existing icon identity with emojis, mixed icon families, or
an automatically selected external library.

## 4. Information Architecture

### 4.1 Content Hierarchy

Every screen establishes hierarchy before choosing components. The preferred
visual hierarchy order is:

1. **Position** — put the most important content where reading begins.
2. **Typography** — use title, weight, and line height to show importance.
3. **Spacing** — group related content and separate concepts.
4. **Size** — reserve larger values for genuinely higher priority.
5. **Contrast** — make critical content readable without shouting.
6. **Surface** — use a panel or inset only when it clarifies ownership.
7. **Color** — reinforce semantic meaning last, never carry hierarchy alone.

Do not invert this order by decorating secondary content with louder colors or
putting every block into a card.

### 4.2 Primary, Secondary, and Tertiary

| Level | Meaning | Typical content |
|---|---|---|
| Primary | The user's current operational goal and its immediate decision | Page context, core KPI, primary status, main content, primary action |
| Secondary | Evidence and controls that support the primary decision | Filters, comparison metrics, trend analysis, supporting actions |
| Tertiary | Detail needed for confirmation, audit, or follow-up | Metadata, rare actions, extended identifiers, explanatory notes |

Not every KPI is primary. Not every action has the same urgency. A page must
make the primary level visually and spatially dominant while keeping secondary
and tertiary information discoverable.

### 4.3 Progressive Disclosure

Show the primary decision path by default. Reveal secondary analysis through
well-labeled sections, tabs, filters, expansion, or a drawer. Put tertiary
detail behind an explicit detail affordance when it would otherwise crowd the
main task.

Progressive disclosure reduces cognitive load; it must not delete critical
business meaning. The full value of a critical ID, status explanation, error,
or required action must remain reachable by keyboard, pointer, and touch.

### 4.4 Page Anatomy

The following is a semantic template, not a mechanical requirement that every
page contain every region:

```text
Page
├── Page Header
│   ├── Eyebrow / Context
│   ├── Title
│   └── Page Actions
│
├── Primary Summary
│
├── Primary Controls / Filters
│
├── Primary Content
│
├── Secondary Analysis
│
└── Detail / Supporting Content
```

Page title, navigation context, summary, controls, and content should use
consistent semantics. Choose only the regions needed to answer the page's
business question.

## 5. Layout & Responsive Design

### 5.1 Layout Rules

- Use the 8px structural grid and content-driven sizing.
- Dense operational regions may use the available width; explanatory prose
  should avoid excessively long lines and generally stay near 65–75 characters
  per line.
- Let content determine height. Do not use fixed-height boxes that clip text,
  errors, badges, or user-entered values.
- Keep the primary reading path stable as the viewport changes.
- A layout is successful when it preserves priority and meaning, not when all
  desktop columns remain visible.

### 5.2 Existing Breakpoint System

Retain oPanel's established semantic breakpoints. Do not replace them with
values selected by an external style catalog.

| Key | Threshold | Semantic behavior |
|---|---|---|
| `compact` | `< 640px` | Single-column summaries; toolbar stacks; tables use a bounded horizontal-scroll region or a detail alternative |
| `navigation-collapse` | `< 800px` | Navigation collapses to its existing compact/drawer expression; header actions wrap; summaries reduce columns |
| `dense-layout` | `< 1100px` | Summary grids fold; secondary table columns hide or move into detail; analytical columns remain readable |
| `wide` | `> 1200px` | Established high-density summary grids and side-by-side analysis may be used where content supports them |

### 5.3 Responsive Priority

Responsive design is not a smaller desktop UI. At a narrow viewport preserve
content in this order:

1. Primary content
2. Primary status
3. Primary action
4. Secondary content
5. Supporting detail

Secondary content may wrap, stack, collapse, move into a detail view, or use
progressive disclosure. Do not remove critical business information only to
make the page look clean.

### 5.4 Overflow, Sticky Elements, and Scaling

- The page itself must not acquire accidental horizontal overflow.
- If a table cannot fit, scroll the table region rather than the whole page;
  keep its header, columns, and action affordances understandable.
- Prefer `wrap > truncate > clip` for ordinary content. See
  [Content Resilience](#7-content-resilience) for identifier rules.
- Sticky headers, action bars, and navigation must not cover the first/last
  content, a focused control, or an error message. Reserve space and account
  for safe areas.
- Layouts must remain understandable under browser zoom, text scaling, and
  user spacing overrides. Use fluid sizing and content-driven height.
- Do not rely on hover for information or action discovery; narrow and touch
  contexts have no hover.

## 6. Component Contracts

Components are chosen after information hierarchy is established. A component
must communicate a stable semantic role and must not introduce a new visual
system for one feature.

### KPI

- Use a KPI for a decision-relevant summary, not as a decorative statistic.
- Anatomy: context/label, value, period or comparison when meaningful, and an
  optional status, note, or action.
- Values use the shared type scale and tabular numerals. Currency and long
  values may use a deliberate multi-line treatment rather than shrinking.
- Primary KPIs receive the strongest position and type. Supporting KPIs may be
  quieter or grouped without equal borders.
- Wide layouts may use oPanel's established five-column dashboard or
  four-column analytical summary patterns when the content supports them; the
  pattern is not a mandate to give every metric equal weight.

### Card and Panel

- Use an 18px primary card only for an independently understood group.
- Maximum Card Nesting Depth = 1.
- Use dividers, whitespace, headings, alignment, or an 8px inset surface for
  internal grouping.
- A card may be omitted when the canvas and section rhythm already establish
  ownership.

### Table

Use the table contract in [Data Tables](#10-data-tables). Tables are a primary
information surface, not a card grid.

### Toolbar and Filter

- Keep the toolbar near the primary content and let it wrap naturally.
- Group controls by task: search, date range, scope, status, and primary
  actions should not become an unstructured control strip.
- Search has a clear affordance and a clear/reset action where applicable.
- Date presets and filters use the existing pill grammar. Do not turn a
  segmented choice into unrelated square buttons.
- Controls need visible labels or an accessible equivalent; placeholder text is
  not a label.

### Segmented Control

- Use for mutually exclusive options of the same level and purpose.
- Keep the container pill-shaped, with a clearly distinguishable active state
  using contrast, type, position, or an indicator in addition to color.
- Preserve native keyboard semantics, selected/pressed state, and visible
  focus.

### Tags, Badges, and Chips

- A badge communicates state or count; a chip represents a value or filter; an
  interactive chip is a real control. Do not make every pill clickable.
- Use the existing semantic tones and the pill radius. Preserve the complete
  label whenever practical.
- A collection wraps or provides an operable `+n` disclosure. Never force a
  collection into one clipped row.
- Do not shrink text indefinitely to fit tags on one line. Full values remain
  available to keyboard, pointer, and touch users.

### Forms, Modal, and Drawer

Use visible labels, helper text, inline validation, focus management, and
feedback rules from [Forms & Feedback](#9-forms--feedback). Modals and drawers
are for focused work, not for hiding normal page hierarchy.

- Modals use the existing 18px card geometry, solid panel treatment, and
  hairline boundary. The mask may use functional backdrop blur.
- Drawers retain the existing right-docked, translucent floating-chrome
  expression and must not obscure the page context without a clear title.
- Footer actions align consistently: Cancel/default on the left of the action
  group, primary Confirm/Save on the right; destructive actions use the danger
  semantic.
- Dialogs must provide an accessible name, logical focus entry, visible focus,
  and a predictable close/return path.

### Empty, Error, and Loading States

- Empty states explain what is absent and what the user can do next when an
  action exists.
- Error states identify what failed, why it matters, and how to recover.
- Loading states preserve the intended layout and show meaningful progress or
  busy status. Do not leave a blank page or let replacement content cause
  avoidable layout jumps.
- The same hierarchy and semantic tones apply to all three states in light and
  dark themes.

## 7. Content Resilience

Content is part of the layout. Chinese, English, Russian, user-created names,
and operational identifiers must all be treated as first-class inputs.

### 7.1 Ordinary Text

Use this priority:

```text
wrap > truncate > clip
```

- Let headings, labels, descriptions, table text, helper text, and errors
  wrap naturally.
- Truncate only when a bounded compact treatment is necessary and the full
  value has a visible, operable disclosure path.
- Never clip important meaning merely to preserve a uniform card height.
- Do not use a global `word-break: break-all` strategy; it damages natural
  language scanning.
- Do not rely on forced `<br>` or blanket non-breaking spaces to control the
  final line of a heading.

### 7.2 Identifiers and Long Tokens

SKU, Order ID, Tracking Number, campaign name, shop name, URLs, and other
identifier-like values must be safely displayable.

- Safe wrapping is preferred when it improves completeness.
- Ellipsis is allowed for a bounded cell only when the full value can be
  copied, inspected, expanded, or disclosed by keyboard, pointer, and touch.
- Identifier-scoped breaking at safe boundaries or anywhere may be used as a
  fallback; never apply that behavior to all prose.
- Critical identifiers should have a direct copy affordance and a complete
  view. A shortened ID without disclosure is a defect.
- Long names may occupy more lines; do not force them into a misleading
  single-line shape.

### 7.3 Tags, Badges, and User Input

- Keep a single compact label whole on one line when practical.
- Let collections wrap. Do not reduce font size below a readable level to keep
  tags in one row.
- If truncation is unavoidable, provide a full-value route that works without
  hover-only behavior.
- User input, validation copy, and helper text must be allowed to grow the
  control or section.
- Badge and count updates need contextual meaning; a bare changing number is
  not sufficient when it could be ambiguous.

### 7.4 Localization and Text Scaling

- Design for Chinese, English, and Russian without assuming Chinese is the
  shortest or default string.
- Allow longer translated labels in navigation, buttons, filters, statuses,
  tables, and dialogs.
- Keep meaning and action priority consistent across locales; do not hide a
  critical action because a translation is longer.
- Under browser zoom, text scaling, or user spacing overrides, content may grow
  vertically. It must not become clipped, overlap, or force an unexplained
  horizontal page scroll.

## 8. Navigation & Wayfinding

- The current page and its business context must be obvious from the page
  title and navigation state.
- The selected navigation item needs a visible state that is not color alone.
- Group navigation by understandable business hierarchy. Avoid a crowded list
  where every destination has equal emphasis.
- Navigation labels and page titles should use consistent semantics; a deep
  system setting must still show where it belongs.
- Use breadcrumbs or another equivalent context path when depth makes the
  parent relationship meaningful. Flat pages do not need decorative crumbs.
- Do not make essential navigation information understandable only on hover.
- Preserve a predictable back/return path and keep meaningful filter or detail
  context discoverable when moving through a page hierarchy.
- In collapsed navigation, preserve the same destination names, selected state,
  and context; changing viewport must not change the information architecture.

## 9. Forms & Feedback

### Form Structure

- Every input has a visible label. Placeholder text is supplemental and never
  replaces the label.
- Provide helper text when format, scope, side effects, or required behavior
  is not obvious.
- Mark required fields clearly and use suitable input types and keyboards.
- Group fields by the user's task, not by implementation order.

### Validation and Errors

- Validate on blur or at an appropriate point while the user is editing; do
  not wait until submit for errors that can be explained earlier.
- Place a specific inline error next to the invalid field and connect it to the
  field. State where the error is, why it occurred, and how to fix it.
- A complex form may also provide an error summary at the top. The summary
  links to fields and receives focus after a failed submit; it does not replace
  inline errors.
- An error cannot be represented only by a red border, red text, or a toast.
- Error announcements must be available to assistive technology without
  unexpectedly moving the user's focus during ordinary editing.

### Control States

- Disabled controls remain visibly disabled, suppress unavailable actions, and
  retain an accessible explanation where needed. The existing oPanel disabled
  treatment is approximately `opacity: 0.45` with no active/hover transform.
- A submitting action disables duplicate submission and exposes a loading
  state while preserving its purpose.
- A successful save, copy, or sync action receives concise confirmation and a
  stable final state.
- Destructive or irreversible actions are clearly named and require explicit
  confirmation. The confirmation explains the consequence; do not use a vague
  "OK" alone.

### Empty, Error, Loading, and Transient Feedback

- Empty content explains the state and gives the next useful action when one
  exists.
- Persistent errors stay near the affected content and provide recovery,
  retry, or help when applicable.
- Loading feedback preserves layout focus and exposes a meaningful busy state.
  Skeletons are preferred for stable content regions; a compact spinner may
  serve a local action.
- Toasts are for transient, non-critical feedback such as copy or success and
  may auto-dismiss in the existing oPanel window of approximately 2.5–3
  seconds. Critical errors and required decisions persist until understood or
  explicitly dismissed.
- Multi-step operations expose current progress and the ability to recover or
  go back where applicable.

## 10. Data Tables

Tables are a primary oPanel surface for high-density operations.

### Alignment and Numerals

```text
Text    → Left
Numbers → Right
Actions → Right
```

Use `font-variant-numeric: tabular-nums` for numeric values, currencies,
counts, percentages, timestamps, and comparable values. Right alignment makes
magnitude comparison easier; do not center numeric columns for decoration.

Status tags stay inline inside the owning text or numeric cell. Do not create a
separate centered status column merely to make the table look balanced.

### Density and Columns

- Preserve high-density row rhythm while maintaining readable type and enough
  target area for row actions.
- Use clear headers and a stable reading order. Sort, filter, and selection
  states need visible and accessible indicators.
- Long text has a deliberate wrap, bounded ellipsis, or detail strategy.
- Important identifiers can be copied and can be fully inspected.
- Column hiding is based on information priority: hide secondary context first,
  never the only column that explains a critical business meaning.
- At narrow widths, a bounded horizontal-scroll table or an equivalent detail
  layout is valid. The main page must not break, and the user must understand
  that additional columns exist.
- Sticky headers or action columns must not cover rows, focus, errors, or the
  table's horizontal-scroll affordance.

### Detail Rows and Inset Information

Expandable details use an 8px inset surface with labeled key/value alignment.
An embedded detail table has no redundant outer card border or shadow. Do not
turn each row, cell group, or expansion into another 18px card.

## 11. Data Visualization UX

Retain the existing ECharts/oPanel visual language: SF Pro Text typography,
quiet axes and hairlines, restrained grid lines, readable labels, shared
Macaron/semantic colors, and precise operational tooltips. A chart is a tool
for a business question, not a decoration added to make a dashboard look full.

### Chart Selection

| Relationship | Preferred chart | Rule |
|---|---|---|
| Time series | Line chart | Use when change over time or rate matters |
| Time series with meaningful accumulated area | Area chart | Use only when the filled area adds meaning; otherwise use a line |
| Category comparison | Bar chart | Compare discrete magnitudes; prefer horizontal bars for long labels or ranking |
| Composition | Stacked bar | Show composition across groups or time |
| Composition with few categories | Donut / pie | Use only for a small number of categories when proportion is the point |
| Distribution | Histogram / box plot | Show spread, outliers, or distribution shape |
| Relationship | Scatter plot | Show correlation, clusters, or outliers |
| Ranking | Horizontal bar | Show ordered categories and readable labels |

Do not use 3D charts. Do not use decorative gauges. Do not add a complex
visual when a simple number or table answers the question better. Keep pie or
donut categories few, label values directly where possible, and switch to a
bar/table when exact comparison is the real task.

### Chart Readability and Access

- Tooltips provide exact values, the relevant date/category, and meaningful
  series context; approximate hover-only information is insufficient.
- Legends use clear names and remain understandable in light and dark themes.
- Never distinguish series only by hue. Reinforce differences with direct
  labels, line styles, marker shapes, patterns, or a visible data table.
- A chart with high data density prioritizes legibility, readable axes, and
  aggregation over visual effects or excessive series.
- Provide a concise textual summary or visible data-table fallback when the
  chart carries an important decision.
- Use existing oPanel series roles: Azure for primary, Mint for secondary,
  Butter for tertiary, Peach for comparison/cost, and Lavender only where its
  business meaning is relevant. Do not introduce a new chart palette.

## 12. Accessibility

Accessibility is a first-class design requirement, not a final cosmetic pass.

### Contrast

- Normal text meets WCAG AA at **4.5:1 or higher** against its surface.
- Important boundaries, focus indicators, selected-state indicators, and
  non-text UI graphics meet **3:1 or higher**.
- Check both light and dark pairings, including muted text, disabled states,
  badges, inset surfaces, table dividers, and focus rings.

### Keyboard and Focus

- Every interactive element is keyboard reachable.
- Focus order follows the visual and task order; do not create a keyboard trap
  or an illogical custom tab sequence.
- Every interactive element has a visible focus state. The existing focus
  expression is a 2px Focus Blue outline with a 2px offset where the control
  permits it.
- Modal and drawer controls receive logical focus entry and return focus
  predictably on close.
- Sticky headers, footers, banners, and drawers must not fully obscure focus;
  reserve scroll space and keep the focused control at least partially visible.

### Icon Semantics and Color

- Decorative icons with equivalent visible text may be hidden from the
  accessibility tree.
- Informational icons need an accessible text equivalent; a tooltip alone is
  not enough if it is unavailable to keyboard or touch users.
- Interactive icon-only controls need a clear accessible name, an adequate
  target, visible focus, and a predictable state.
- Never communicate Success, Warning, Error, Risk, Selected, or channel state
  by color alone. Pair color with text, icon, shape, position, or pattern.

### Structure, Targets, and Reflow

- Use meaningful headings, landmarks, labels, and semantic controls.
- Use a web pointer target of at least 24 CSS px where applicable, with a
  comfortable touch target near 44px when the context allows; adjacent targets
  need clear separation.
- Text and controls reflow under zoom, text scaling, and user spacing settings.
- Meaningful imagery has a text alternative; decorative imagery is marked as
  decorative.
- Do not make an essential action or explanation hover-only.
- Respect the user's reduced-motion preference under the existing oPanel rules;
  the final semantic state, content, and focus must remain correct.

## 13. UI / UX Anti-Patterns

The following are prohibited unless a documented product constraint makes the
specific exception necessary and the full meaning remains accessible:

### Structure and Hierarchy

- Card inside Card or more than one bordered card depth
- Every section is a card
- Equal visual weight everywhere
- Decorative dashboard clutter
- Unnecessary containers used instead of spacing, alignment, or dividers
- Excessive centered content when left/right scanning is more appropriate

### Layout and Content

- Fixed-width layouts that cause page overflow
- Clipping ordinary text without a recovery path
- Truncating critical IDs without copy, expansion, or full-value disclosure
- Shrinking tags indefinitely to force one row
- Removing critical information only for visual cleanliness
- Desktop UI merely scaled down for mobile
- Sticky UI that covers content, errors, or focus
- Global `word-break: break-all` applied to natural language

### Semantics and Accessibility

- Center-aligned numeric columns
- Color-only states
- Placeholder-only labels
- Icon-only controls without accessible labels
- Invisible focus or removed focus outlines without a replacement
- Tiny interaction targets or tightly packed adjacent targets
- Information or navigation that can only be understood on hover
- Errors shown only as a red border, red color, or silent failure

### Visual System

- Unnecessary gradients
- Arbitrary semantic colors
- Arbitrary radius
- Arbitrary shadows or equal-elevation shadows on every block
- Excessive low-contrast muted text
- Mixing multiple icon families
- Automatically replacing the Open Macaron, Apple, or existing oPanel visual
  system with an external recommendation

### Data and Charts

- Charts used only as decoration
- 3D charts or ornamental gauges
- Complex charts where a number or table is clearer
- Series or statuses distinguished only by color
- Excessive centering used to make a dense table look symmetrical

## 14. Motion / Physics

This section preserves the existing oPanel motion system. It is not derived
from, and must not be rewritten using, UI UX Pro Max motion guidance.

- The shared oPanel fluid easing is
  `cubic-bezier(0.16, 1, 0.3, 1)`.
- Existing oPanel spring physics use the `snappy` preset (`ζ=0.73`, fast with
  subtle overshoot); existing `smooth` and `bouncy` variants remain available
  where already appropriate.
- Press feedback is a scale transform rather than a color-only change:
  containers use the existing `0.95–0.995` range by surface size, and icons
  inside interactive elements use `0.88` unless the container already scales.
- Existing icon state changes use the oPanel morphing icon behavior and retain
  the existing spring treatment.
- Existing oPanel transitions remain the shared `0.16s` fluid transition for
  applicable color, background, border, shadow, and transform state changes.
- All existing motion honors the user's reduced-motion preference and presents
  the final readable state when motion is reduced.

UI UX Pro Max contributes **no** Animation Guidelines, GSAP guidance, motion
presets, animation durations, animation easings, spring recommendations,
transition recommendations, page transitions, stagger rules, shared-element
animation, animation hierarchy, or animation-performance recommendations to
oPanel. Do not add them through this document.

## 15. Design Authority / Source of Truth

- `DESIGN.md` is the normative source for visual language, tokens, semantic
  meaning, component contracts, content behavior, responsive priority, and
  accessibility requirements.
- Any runtime token layer must mirror the values and semantics here. Feature
  work must consume the system rather than inventing new colors, radii,
  shadows, type scales, or icon families.
- This document is intentionally implementation-independent. A component or
  screen is not compliant merely because it matches an existing file; it is
  compliant when it satisfies the contracts here.
- When adding a new visual treatment, first reuse an existing token, surface,
  shape, hierarchy level, or semantic tone. Add a new rule only when the
  product meaning cannot be represented by the existing system.
- Apple remains the base design language, oPanel remains the visual identity,
  and UI UX Pro Max remains a UI/UX quality supplement. No later external
  catalog silently outranks this authority order.

## 16. UI / UX Definition of Done

### Visual Hierarchy

- [ ] The page has an explicit Primary content region.
- [ ] Secondary content does not compete with Primary content.
- [ ] No unnecessary Card was introduced.
- [ ] There is no obvious boxification or excessive nested surface structure.
- [ ] Spacing communicates relationships between content groups.

### Typography

- [ ] The shared type scale and SF Pro Text direction are used consistently.
- [ ] Comparable numbers use tabular figures.
- [ ] Long text can reflow without clipping or overlap.
- [ ] Critical content has no meaningless truncation.

### Color

- [ ] Existing Apple and Open Macaron semantic tones are used.
- [ ] Status meaning does not depend on color alone.
- [ ] Light and dark expressions remain readable.

### Layout

- [ ] There is no accidental page-level horizontal overflow.
- [ ] Information priority remains understandable at each viewport.
- [ ] Sticky UI does not obscure content or focus.
- [ ] Narrow layouts are not merely scaled-down desktop UI.

### Accessibility

- [ ] All interactive elements are keyboard reachable.
- [ ] Focus is visible and not obscured.
- [ ] Icon semantics are correct.
- [ ] Text and important non-text contrast meet the stated thresholds.
- [ ] Color is not the only indicator of state.

### Forms

- [ ] Every input has a visible label.
- [ ] Invalid fields have inline, specific errors.
- [ ] Helper text is present where needed.
- [ ] Destructive actions are clearly distinguished and confirmed.

### Tables

- [ ] Text is left-aligned.
- [ ] Numbers are right-aligned.
- [ ] Actions are right-aligned.
- [ ] Comparable numeric values use tabular numerals.
- [ ] Long identifiers can be copied and fully viewed.

### Data Visualization

- [ ] The chart type matches the data relationship and business question.
- [ ] The legend is clear, or direct labels provide equivalent context.
- [ ] Tooltips provide precise values and meaningful context.
- [ ] The chart is not being used only as decoration.
