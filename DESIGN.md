---
version: 1.1.0
name: FUCK-Ozon-Design-System
description: High-density e-commerce analytics system combining Apple HIG minimalism (SF Pro, negative tracking, tabular nums, 1px hairlines, 18px cards) with an Open Macaron Pastel color philosophy (low-saturation harmonic shells with high-contrast text) and tactile spring physics.

colors:
  # Brand & Core Interactive (Apple Action Blue)
  primary: "#0066CC"
  primary-focus: "#0071E3"
  primary-on-dark: "#2997FF"
  primary-soft-light: "rgba(0, 102, 204, 0.08)"
  primary-soft-dark: "rgba(41, 151, 255, 0.15)"

  # Light Theme Canvas & Surfaces
  canvas-light: "#F5F5F7"
  panel-light: "rgba(255, 255, 255, 0.88)"
  panel-solid-light: "#FFFFFF"
  ink-light: "#1D1D1F"
  ink-muted-light: "#7A7A7A"
  line-light: "rgba(0, 0, 0, 0.08)"
  line-highlight-light: "rgba(255, 255, 255, 0.9)"

  # Dark Theme Canvas & Surfaces
  canvas-dark: "#151419"
  panel-dark: "rgba(28, 26, 36, 0.85)"
  panel-solid-dark: "#1E1B26"
  ink-dark: "#F6F5F8"
  ink-muted-dark: "#9E9AA8"
  line-dark: "rgba(255, 255, 255, 0.08)"
  line-highlight-dark: "rgba(255, 255, 255, 0.04)"

  # Open Macaron Pastel System (The Formula)
  # Unrestricted Hue Space. Any hue H derives a harmonious Macaron pair:
  # - Light: Shell L: 94-97%, C: 8-18% | Ganache Text L: 30-42%, C: 40-70% (WCAG AAA)
  # - Dark:  Shell L: 16-24%, C: 8-16% | Frosting Text L: 75-88%, C: 35-65%
  macaron-presets:
    peach:    { light-bg: "#FFEBEA", light-text: "#C42B24", dark-bg: "#3D2226", dark-text: "#FF859F", role: "Orders & Cancellations" }
    mint:     { light-bg: "#E6F7F0", light-text: "#127546", dark-bg: "#16382C", dark-text: "#7EE0B3", role: "Fulfillment & Deliveries" }
    lavender: { light-bg: "#F0EDFF", light-text: "#5944B3", dark-bg: "#312847", dark-text: "#BBA8FF", role: "Disputes & Timeliness" }
    azure:    { light-bg: "#EBF3FF", light-text: "#0066CC", dark-bg: "#172A46", dark-text: "#6CAFFF", role: "GMV & Primary Metrics" }
    butter:   { light-bg: "#FFF5E5", light-text: "#B86614", dark-bg: "#3D2B19", dark-text: "#FFAE61", role: "WHD & Warning States" }
    pistachio:{ light-bg: "#EEF7E8", light-text: "#3B7A20", dark-bg: "#1E3516", dark-text: "#98E07A", role: "Profits & Healthy State" }
    berry:    { light-bg: "#FCEEF6", light-text: "#A8226A", dark-bg: "#381A2B", dark-text: "#F07AB9", role: "Top Products & Highlights" }

  # Status & Feedback Tones
  danger: "#FF3B30"
  danger-soft-light: "#FFEBEA"
  danger-soft-dark: "#451B1C"
  warning: "#FF9500"
  warning-soft-light: "#FFF5E5"
  warning-soft-dark: "#452E15"
  success: "#34C759"
  success-soft-light: "#EAF9ED"
  success-soft-dark: "#193E23"

typography:
  font-family-display: "SF Pro Display, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', Roboto, sans-serif"
  font-family-body: "SF Pro Text, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', Roboto, sans-serif"
  font-family-mono: "'SF Mono', ui-monospace, Menlo, Monaco, Consolas, monospace"

  scale:
    hero-title: { size: "24px", weight: 700, tracking: "-0.025em" }
    panel-title: { size: "16px", weight: 650, tracking: "-0.015em" }
    body: { size: "14px", weight: 400, line-height: 1.5, tracking: "-0.006em" }
    caption: { size: "12px", weight: 500, line-height: 1.4, tracking: "-0.002em" }
    numbers: { font-variant-numeric: "tabular-nums" }

shapes:
  rounded-pill: "9999px"
  rounded-card: "18px"
  rounded-input: "10px"
  rounded-sm: "8px"
  rounded-xs: "4px"

physics:
  ease-apple-spring: "cubic-bezier(0.34, 1.56, 0.64, 1)"
  ease-apple-fluid: "cubic-bezier(0.16, 1, 0.3, 1)"
  active-scale: "scale(0.95)"
  active-scale-card: "scale(0.985)"

iconography:
  system: "Lucide / Tabler Stroke System (24x24, 1.8px default stroke, round cap/join)"
---

# Design Philosophy

### 1. Open Macaron × Apple HIG Synergy
- **Open Macaron Harmonic Palette**: Replaces sterile, fatiguing dashboard tables with breathable, low-saturation pastel cards (Light Shell + High-Contrast Ganache Text). Supports any custom hue via the L/C harmonic formula.
- **Apple Architectural Rigor**: 1px crisp hairlines (`rgba(0,0,0,0.08)`), negative display tracking (`-0.015em` to `-0.025em`), and 18px golden-ratio radii.

### 2. High-Density Data Clarity
- All numeric metrics, currency amounts, order numbers, and timestamps enforce `font-variant-numeric: tabular-nums` to eliminate visual jitter and guarantee columnar alignment.
- Minimal chrome: decorative containers recede so operational insights take focus.

### 3. Tactile Physical Motion
- Touch feedback via immediate `scale(0.95)` press physics.
- Seamless state morphing via `<morph-icon>` powered by Apple spring kinematics.
