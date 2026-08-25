---
version: 1.0.0
name: FUCK-Ozon-Design-System
description: An Apple-inspired, high-density e-commerce analytics dashboard system. Combines Apple's crisp minimalism (SF Pro typography with negative display tracking, Action Blue primary accents, 1px hairlines, and 18px utility cards) with Lucide stroke iconography and Macaron physical spring micro-interactions.

colors:
  # Brand & Primary Interactive (Apple Action Blue)
  primary: "#0066CC"
  primary-focus: "#0071E3"
  primary-on-dark: "#2997FF"
  primary-soft-light: "rgba(0, 102, 204, 0.08)"
  primary-soft-dark: "rgba(41, 151, 255, 0.15)"

  # Light Theme Canvas & Surfaces
  canvas-light: "#F5F5F7"                # Signature Apple Parchment background
  panel-light: "rgba(255, 255, 255, 0.88)" # Frosted glass panel
  panel-solid-light: "#FFFFFF"          # Crisp white card surface
  ink-light: "#1D1D1F"                  # Apple signature near-black text
  ink-muted-light: "#7A7A7A"            # Secondary text & subtle captions
  line-light: "rgba(0, 0, 0, 0.08)"     # 1px hairline border
  line-highlight-light: "rgba(255, 255, 255, 0.9)"

  # Dark Theme Canvas & Surfaces
  canvas-dark: "#151419"                 # Deep neutral dark canvas
  panel-dark: "rgba(28, 26, 36, 0.85)"  # Frosted dark panel
  panel-solid-dark: "#1E1B26"           # Dark surface card
  ink-dark: "#F6F5F8"                   # High-contrast crisp white text
  ink-muted-dark: "#9E9AA8"             # Muted dark copy
  line-dark: "rgba(255, 255, 255, 0.08)" # 1px dark hairline border
  line-highlight-dark: "rgba(255, 255, 255, 0.04)"

  # E-commerce Business Channel Tokens
  channel-fbp: "#0066CC"                # FBP Blue
  channel-fbp-bg-light: "#EBF3FF"
  channel-fbp-bg-dark: "#172A46"

  channel-fbs: "#1B8255"                # realFBS Green
  channel-fbs-bg-light: "#E6F7F0"
  channel-fbs-bg-dark: "#16382C"

  channel-whd: "#B86614"                # WHD Amber / Orange
  channel-whd-bg-light: "#FFF3E6"
  channel-whd-bg-dark: "#3D2B19"

  # Status & Feedback Tones
  danger: "#FF3B30"                     # Apple System Red
  danger-soft-light: "#FFEBEA"
  danger-soft-dark: "#451B1C"

  warning: "#FF9500"                    # Apple System Orange
  warning-soft-light: "#FFF5E5"
  warning-soft-dark: "#452E15"

  success: "#34C759"                    # Apple System Green
  success-soft-light: "#EAF9ED"
  success-soft-dark: "#193E23"

typography:
  font-family-display: "SF Pro Display, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', Roboto, sans-serif"
  font-family-body: "SF Pro Text, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', Roboto, sans-serif"
  font-family-mono: "'SF Mono', ui-monospace, Menlo, Monaco, Consolas, monospace"

  # Scale & Tracking
  hero-title:
    fontSize: 24px
    fontWeight: 700
    letterSpacing: -0.025em
  panel-title:
    fontSize: 16px
    fontWeight: 650
    letterSpacing: -0.015em
  body:
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: -0.006em
  caption:
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: -0.002em
  numbers:
    fontVariantNumeric: "tabular-nums"

shapes:
  rounded-pill: 9999px                  # Primary CTAs, active status chips, picker triggers
  rounded-card: 18px                    # Apple Store utility cards, major dashboard panels
  rounded-input: 10px                   # Form fields, search inputs, dropdown menus
  rounded-sm: 8px                       # Utility buttons, table action chips, badge counters
  rounded-xs: 4px                       # Micro tags and indicator dots

physics:
  ease-apple-spring: "cubic-bezier(0.34, 1.56, 0.64, 1)"
  ease-apple-fluid: "cubic-bezier(0.16, 1, 0.3, 1)"
  ease-apple-press: "cubic-bezier(0.2, 0, 0, 1)"
  active-scale: "scale(0.95)"           # Button & chip active press feedback
  active-scale-card: "scale(0.985)"

iconography:
  system: Lucide / Tabler Stroke System
  viewBox: "0 0 24 24"
  strokeWidthDefault: 1.8
  strokeWidthNav: 1.5
  strokeWidthMicro: 2.0
  strokeLinecap: round
  strokeLinejoin: round
---

# Design Principles

### 1. Minimal UI Chrome, Maximum Data Clarity
UI containers recede so that analytics, order timelines, and inventory decisions take the spotlight. 
Borders are crisp 1px hairlines (`rgba(0,0,0,0.08)`); heavy shadows are replaced by subtle depth (`0 4px 20px rgba(0,0,0,0.04)`).

### 2. Typographic Rhythm & Tabular Numbers
- Displays and section headlines feature Apple's signature negative letter-spacing (`-0.015em` to `-0.025em`).
- All numeric metrics, currency values, quantities, dates, and order numbers use `font-variant-numeric: tabular-nums` to ensure exact column alignment and zero visual jitter.

### 3. Tactile Physical Feedback
- Interactive buttons and clickable cards provide immediate physical press confirmation via `transform: scale(0.95)`.
- Custom `<morph-icon>` elements morph fluidly between states (e.g. ChevronDown ↔ ChevronUp, Sun ↔ Moon, Sync ↔ Check) powered by Apple spring physics.

### 4. Cohesive Channel Hierarchy
E-commerce channels (FBP, realFBS, WHD) and fulfillment stages are color-coded consistently using soft pastel badges and distinct contrast accents.
