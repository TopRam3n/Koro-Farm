---
name: KoroFarm Supply Assurance
description: A web system for coordinating and verifying institutional agricultural supply.
colors:
  background: "hsl(160 42% 5%)"
  foreground: "hsl(75 17% 95%)"
  card: "hsl(157 35% 7%)"
  popover: "hsl(156 30% 9%)"
  primary: "hsl(149 55% 53%)"
  secondary: "hsl(155 34% 11%)"
  muted: "hsl(154 29% 12%)"
  muted-foreground: "hsl(154 9% 67%)"
  accent: "hsl(188 66% 52%)"
  success: "hsl(149 55% 53%)"
  warning: "hsl(39 86% 62%)"
  destructive: "hsl(3 73% 61%)"
  border: "hsl(150 12% 19%)"
  sidebar-background: "hsl(158 42% 5%)"
  control-center-background: "hsl(210 7% 8%)"
  control-center-card: "hsl(210 7% 11%)"
  control-center-secondary: "hsl(210 7% 15%)"
  control-center-primary: "hsl(190 48% 60%)"
  control-center-muted-foreground: "hsl(210 8% 68%)"
  control-center-border: "hsl(210 7% 23%)"
typography:
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 600
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
  mono:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
  control-center-body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "12px"
  pill: "9999px"
spacing:
  2: "0.5rem"
  3: "0.75rem"
  4: "1rem"
  5: "1.25rem"
  6: "1.5rem"
  8: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  button-outline:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 16px"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "8px 12px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: "24px"
  status-badge:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "4px 10px"
  badge-pill:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
---

# Design System: KoroFarm Supply Assurance

## Overview

**Creative North Star: "Assurance Control Surface"**

KoroFarm is a dense operational workspace for buyer-side supply coordinators. The visual language is dark, restrained, and evidence-first: forest-green semantic accents sit on near-black surfaces, while thin borders and tonal shifts organize information. A faint square grid appears on the shared body background. Inter carries shared interface text; JetBrains Mono is reserved for identifiers and technical values.

The system should make authoritative state easy to distinguish from derived state and missing evidence. It supports auditable supply planning, governed recovery, and physical fulfilment without implying that a plan is a delivery or presenting automation as a personality. The shared forest-green palette is the current application baseline. The Control Center has a route-scoped slate/cyan variant, an opaque slate canvas that suppresses the grid, and a platform UI font stack; these are local exceptions, not the global palette.

**Key Characteristics:**
- Evidence-first operational density
- Forest-green semantic accents on dark, tonal surfaces
- Thin borders instead of decorative elevation
- Consistent sans-serif UI typography with mono for identifiers
- Explicit status labels alongside color

## Colors

The shared palette uses a green primary and success role, cyan for informational emphasis, amber for warning, and coral-red for destructive or rejection states. Near-black surfaces and cool, low-contrast dividers provide the neutral structure. The frontmatter values are normative.

### Primary
- **Field Green** (`primary`): Primary actions, active navigation, and the shared success state.
- **Current Cyan** (`accent`): Informational and energy emphasis; it is not a success signal.

### Secondary
- **Signal Amber** (`warning`): At-risk and approval-attention states.
- **Harvest Coral** (`destructive`): Errors, escalation, loss, and rejection states.

### Neutral
- **Night Ground** (`background`): The shared application canvas.
- **Canopy Surface** (`card`): Raised content surfaces, primarily through tonal contrast rather than shadow.
- **Deep Sidebar** (`sidebar-background`): Navigation rail separation.
- **Mist Text** (`foreground` / `muted-foreground`): Primary and supporting text.
- **Fine Rule** (`border`): Quiet dividers and component outlines.

### Named Rules
**The State-Color Rule.** Use color for a real status or action role; repeat critical meaning in text or an icon.

**The Scoped-Variant Rule.** Slate/cyan belongs to `.control-center-shell` only. Do not copy it into other routes as if it were a shared token set.

## Typography

**Display Font:** Inter (with ui-sans-serif and system-ui fallbacks)
**Body Font:** Inter (with ui-sans-serif and system-ui fallbacks)
**Label/Mono Font:** JetBrains Mono (for IDs and technical identifiers only)

**Character:** Compact, neutral sans-serif typography supports repeated operational scanning. Tabular numerals align quantities; mono is a data treatment, not a general technical mood.

The Control Center's route-scoped variant uses the platform UI sans-serif stack for all text; do not treat that override as the shared type token.

### Hierarchy
- **Display** (600, 36px): Used sparingly for primary workspace headings.
- **Headline** (600, 30–36px): Route headings and dominant requirement names.
- **Title** (600, 18–24px): Section titles and panel headings.
- **Body** (400, 14–16px): Descriptions, explanations, and operating copy.
- **Label** (500–600, 11–14px): Field labels, statuses, and metadata. Existing legacy surfaces include smaller 9–10px annotations; these are local exceptions rather than a preferred functional-text size.
- **Mono** (400, 12–14px): Requirement IDs, lot IDs, and technical references.

## Layout

Authenticated workspaces use a persistent left navigation rail and a flexible content region. At desktop widths the shared rail is 256px; the Control Center narrows its scoped rail to 224px and uses slate/cyan tokens. Mobile collapses the rail behind a menu button. Main content uses constrained widths, responsive grids, structured rows, and dense tables where comparison benefits from columns. The common utility spacing follows Tailwind's 4px-based scale; there is no separate custom spacing-token scale.

## Elevation & Depth

The system is flat by default. Tonal surface changes and thin borders distinguish panels and navigation; common operational panels use no shadow. The shared Card primitive has a subtle shadow, and dialogs use stronger elevation to separate a temporary focused task from the workspace. Glow utilities exist in Tailwind configuration but are not part of the observed common surface treatment.

**The Surface-First Rule.** Prefer a small tonal shift and a fine border for persistent groups; reserve shadow for overlays and components whose interaction requires separation.

## Shapes

The base radius is 10px, with 8px controls, 6px compact shapes, and 12px larger dialogs. StatusBadge uses a compact rounded rectangle; the generic Badge primitive is pill-shaped. Panels are typically clipped only when content or a table needs an overflow boundary. Borders are thin and low contrast.

## Components

### Buttons
Buttons use familiar solid, outline, secondary, ghost, destructive, and link variants. The shared primitive is 40px tall with 16px horizontal padding, 14px medium text, an 8px radius, and a visible keyboard focus ring. Larger controls use an 11px height variant.

### Inputs / Fields
Inputs use the canvas color, a border token, 40px height, 12px horizontal padding, and an 8px radius. Focus is communicated with a 2px semantic ring; disabled inputs reduce opacity and disable interaction.

### Cards / Containers
The shared Card uses the card surface, a 10px radius, thin border, and subtle shadow. Operational panels are a flatter custom pattern: card surface, 10px radius, fine border, and usually 20px padding. Avoid nesting either container inside itself.

### Chips
The generic Badge has a pill silhouette and primary, secondary, destructive, and outline variants. The domain StatusBadge is a compact 6px-radius label with a status icon, semantic border/background/text, and normalized uppercase status text.

### Navigation
The shared shell uses grouped, text-labeled links in a fixed desktop rail and a slide-in mobile rail. Active links use a low-opacity primary surface and primary text; hover uses a subtle neutral surface. The command palette is keyboard-openable with Ctrl/Cmd+K and dismissible with Escape.

### Operational Panel
The `operational-panel` pattern groups dense workspace information using a card-toned surface and thin border, without relying on strong shadows. Some route-specific pages intentionally replace this pattern with aligned ledgers or tables.

## Do's and Don'ts

### Do:
- **Do** reserve success, warning, destructive, and informational colors for their semantic roles, with text or icon reinforcement.
- **Do** show unavailable or unverified states as explicit labels; never encode them only in color.
- **Do** use JetBrains Mono for identifiers and tabular numerals for comparable quantities.
- **Do** treat the Control Center slate/cyan palette as route-scoped until the rest of the application implements it.

### Don't:
- **Don't** equate planning coverage with physical fulfilment or imply a state the data does not prove.
- **Don't** use green as a generic decoration or as proof that a consequential recovery action is authorized or executed.
- **Don't** nest cards or use a shadow to replace clear grouping and hierarchy.
