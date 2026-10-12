---
name: Luminous Minimal
colors:
  surface: '#fbf8fc'
  surface-dim: '#dcd9dd'
  surface-bright: '#fbf8fc'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f2f7'
  surface-container: '#f0edf1'
  surface-container-high: '#eae7eb'
  surface-container-highest: '#e4e1e6'
  on-surface: '#1b1b1e'
  on-surface-variant: '#41474e'
  inverse-surface: '#303033'
  inverse-on-surface: '#f3f0f4'
  outline: '#71787f'
  outline-variant: '#c0c7d0'
  surface-tint: '#1c6390'
  primary: '#004163'
  on-primary: '#ffffff'
  primary-container: '#075985'
  on-primary-container: '#96cfff'
  inverse-primary: '#90cdff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#5c3400'
  on-tertiary: '#ffffff'
  tertiary-container: '#7c4800'
  on-tertiary-container: '#ffbc77'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cbe6ff'
  primary-fixed-dim: '#90cdff'
  on-primary-fixed: '#001e31'
  on-primary-fixed-variant: '#004b72'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#ffdcbd'
  tertiary-fixed-dim: '#ffb86e'
  on-tertiary-fixed: '#2c1600'
  on-tertiary-fixed-variant: '#693c00'
  background: '#fbf8fc'
  on-background: '#1b1b1e'
  surface-variant: '#e4e1e6'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Manrope
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1'
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 8px
  sm: 16px
  md: 24px
  lg: 48px
  xl: 80px
  container-max: 1280px
  gutter: 24px
---

## Brand & Style
The design system embodies a "Quiet Premium" philosophy. It is tailored for high-end SaaS, fintech, or architectural portfolios where clarity and focus are paramount. The brand personality is disciplined, sophisticated, and intentionally understated, evoking an emotional response of calm confidence and precision.

The design style is **Ultra-Minimalist** with a focus on high-contrast ratios. It prioritizes expansive whitespace (airiness), exceptional typography, and a strategic use of a single accent color to guide the user's eye. The interface should feel like a gallery space—neutral, structured, and allowing the content to be the primary focus.

## Colors
The palette is strictly monochromatic, utilizing a scale of high-contrast grays from pure white (#ffffff) to deep ink (#0f172a). 

- **Primary Accent:** A professional, sophisticated deep blue (#075985) is used sparingly for primary actions, active states, and critical indicators.
- **Surface Strategy:** Backgrounds are kept white to maximize the sense of "air." Secondary surfaces use a very light gray (#f4f4f5) to create subtle containment without heavy borders.
- **Contrast:** Text is consistently rendered in high-contrast neutral-900 (#18181b) to ensure maximum legibility and a sharp, "ink-on-paper" feel.

## Typography
Typography is the primary driver of hierarchy in this design system. 
- **Headlines:** Use **Manrope** for its modern, balanced, and technical proportions. Tracking is slightly tightened on larger sizes to maintain a cohesive "lockup" feel.
- **Body:** **Inter** provides a systematic, utilitarian clarity for long-form text and interface elements.
- **Technical/Labels:** **JetBrains Mono** is used for small labels, metadata, and status indicators to add a touch of "precision engineering" to the aesthetic. These should frequently be set in uppercase with increased letter spacing.

## Layout & Spacing
The layout follows a **Fixed Grid** philosophy on desktop to maintain a controlled, editorial appearance. 
- **Grid:** A 12-column grid with generous 24px gutters. 
- **Margins:** Desktop margins are dynamic but start at a minimum of 48px to ensure content never feels crowded against the viewport edge.
- **Rhythm:** An 8px linear scale is used for component-level spacing, while a more aggressive exponential scale (48px, 80px, 120px) is used for section vertical padding to reinforce the "airy" brand promise.
- **Mobile:** On mobile, the grid collapses to 4 columns with 16px margins, and vertical spacing is reduced by one step in the scale.

## Elevation & Depth
In keeping with ultra-minimalism, depth is conveyed through **Tonal Layering** and **Low-Contrast Outlines** rather than heavy shadows.
- **Layers:** Most elements sit directly on the background. Raised elements (like cards) are defined by a 1px border (#e4e4e7) or a subtle change in surface color (#f4f4f5).
- **Shadows:** When necessary for functional overlays (menus, modals), use a single "Ambient Shadow"—a very large blur (32px), zero spread, and extremely low opacity (4-6% black) to simulate a soft natural light source.
- **Focus:** Interactive elements use a sharp, 2px primary blue outline when focused, ensuring accessibility without compromising the clean lines.

## Shapes
The shape language is **Soft (Level 1)**. This subtle rounding (4px for standard elements) removes the harshness of pure 90-degree corners while maintaining a professional, structured, and architectural feel. 
- Large containers (cards) use `rounded-lg` (8px).
- Small elements (checkboxes, tags) use `rounded` (4px).
- Avoid pill-shaped or fully circular elements except for avatars, as they conflict with the grid-based, disciplined aesthetic.

## Components
- **Buttons:** Primary buttons are solid deep blue with white text. Secondary buttons are ghost-style with a 1px neutral-200 border and neutral-900 text. Use "Manrope SemiBold" for button labels to differentiate from body text.
- **Inputs:** Clean, 1px bordered boxes. On focus, the border transitions to the primary deep blue. Place labels strictly above the field using the JetBrains Mono "label-sm" style.
- **Chips/Tags:** Subdued gray backgrounds (#f4f4f5) with neutral-600 text. Only use the accent blue for "active" or "selected" filter states.
- **Cards:** No shadows. Use a 1px border (#e4e4e7) and generous internal padding (min 24px).
- **Lists:** Use light horizontal dividers (1px, #f4f4f5). High-contrast text for primary items and neutral-500 for secondary metadata.
- **Data Tables:** High-density but clear. Use a subtle gray header background and ensure plenty of horizontal padding within cells.