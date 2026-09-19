---
name: web-design-guidelines
description: "Review and enforce Web Interface Guidelines compliance. Covers accessibility, focus states, forms, animation, typography, content handling, images, performance, dark mode, touch & interaction, and anti-patterns. Use when asked to 'review my UI', 'check accessibility', 'audit design', 'review UX', 'design best practices', or when implementing any modern web interface."
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Expert rules and audits for modern web interface engineering and design quality.

## Core Directives & Rules

### 1. Accessibility (a11y)
- **Icon-only buttons:** Must have `aria-label`.
- **Form controls:** Require associated `<label>` (using `htmlFor` or wrapping) or `aria-label`.
- **Interactive elements:** Require proper keyboard handlers (`onKeyDown` / `onKeyUp` for Enter/Space).
- **Semantics:** Use `<button>` for actions, `<a>` / `<Link>` for navigation. Never `<div onClick>`.
- **Images:** Must have `alt` attribute (use `alt=""` if strictly decorative).
- **Decorative icons:** Must have `aria-hidden="true"`.
- **Dynamic / Async updates:** Toasts, alerts, and inline validation require `aria-live="polite"`.
- **Heading hierarchy:** Hierarchical `<h1>` through `<h6>`. Main content areas should support skip-links.
- **Anchors:** Apply `scroll-margin-top` on heading anchors to avoid sticky header clipping.

### 2. Focus States
- **Visible focus:** All interactive elements must have visible focus: `focus-visible:ring-*` or distinct outline.
- **Never suppress outlines:** Never write `outline: none` or `outline-none` without an explicit `:focus-visible` replacement.
- **Click vs keyboard:** Use `:focus-visible` over `:focus` to prevent unsightly rings on mouse clicks.
- **Compound controls:** Use `:focus-within` on parent containers for combined input/button groups.
- **Sticky overlays:** Sticky navigation bars, floating headers, or modals must never cover focused elements.

### 3. Forms & Inputs
- **Autocomplete & names:** Inputs need appropriate `autocomplete` attributes and clear `name` attributes.
- **Input types:** Use semantic `type` (`email`, `tel`, `url`, `number`) and appropriate `inputmode`.
- **Never block paste:** Never call `e.preventDefault()` on `onPaste`.
- **Spellcheck:** Disable spellcheck on emails, tokens, usernames, code fields (`spellCheck={false}` or `spellcheck="false"`).
- **Hit targets:** Checkbox/radio labels and controls share a single continuous hit target (no dead gaps).
- **Submissions:** Submit buttons stay enabled until request starts; show clear loading spinners during requests.
- **Error feedback:** Errors appear inline next to offending fields; focus first errored input on submission failure.
- **Placeholders:** End with `…` and show an example pattern, not just duplicate labels.
- **Unsaved changes:** Warn before navigation when form has unsaved modifications.

### 4. Animation & Motion
- **Reduced motion:** Always respect `prefers-reduced-motion` (disable or provide instant fade variant).
- **GPU compositing:** Animate `transform` and `opacity` only. Avoid animating `width`, `height`, `top`, `left`, `margin`.
- **No wild transitions:** Never write `transition: all`. Explicitly list transitioned properties (e.g. `transition: opacity 0.2s ease, transform 0.2s ease`).
- **Transform origins:** Always explicitly specify `transform-origin` when scaling or rotating.
- **Interruptible:** Animations must gracefully handle interruption and mid-flight user clicks.
- **Autoplay control:** Decorative loops over 5 seconds must have pause controls or stop under reduced-motion.

### 5. Typography & Formatting
- **Ellipsis:** Use the single unicode character `…` rather than three dots `...`.
- **Quotes:** Use typographic curly quotes `“` `”` and `‘` `’` where appropriate.
- **Non-breaking spaces:** Use non-breaking spaces for units (`10&nbsp;MB`, `100&nbsp;ms`), keyboard shortcuts (`⌘&nbsp;K`), and short brand titles.
- **Loading states:** Always append `…` (`"Loading…"`, `"Authenticating…"`, `"Saving…"`).
- **Tabular figures:** Use `font-variant-numeric: tabular-nums` for timers, scoreboards, tables, and number tickers.
- **Headings:** Use `text-wrap: balance` or `text-wrap: pretty` on headers to prevent single-word orphan lines.

### 6. Content Handling & Layout
- **Overflow defense:** Text containers handling dynamic or external content must have `truncate`, `line-clamp-*`, or `break-words`.
- **Flex truncation:** Flex child containers require `min-w-0` to allow child text truncation without blowing out the flex layout.
- **Empty states:** Always design explicit, attractive empty states; never render broken or hollow layouts for empty lists.
- **Safe areas:** Full-bleed fixed/sticky layouts must account for `env(safe-area-inset-*)` on mobile viewports.
- **No accidental horizontal scroll:** Use `overflow-x: hidden` on viewport roots and check absolute positioned elements.

### 7. Performance & Assets
- **Image dimensions:** `<img>` elements must have explicit `width` and `height` or `aspect-ratio` to prevent Cumulative Layout Shift (CLS).
- **Lazy loading:** Below-the-fold media must use `loading="lazy"`.
- **Critical hero assets:** Above-the-fold hero graphics must use `fetchpriority="high"`.
- **Video over GIF:** Use `<video autoplay muted loop playsinline>` with MP4/WebM instead of heavy animated GIFs.
- **DOM reads:** Never interleave DOM style writes and layout reads (`offsetHeight`, `getBoundingClientRect`) in loops or render passes.

### 8. Dark Mode & Theming
- **Color scheme:** Always declare `color-scheme: dark` (or `light dark`) on `<html>` for dark themes so native scrollbars, inputs, and form controls adapt.
- **Theme color:** Synchronize `<meta name="theme-color">` with the page background color.
- **Contrast:** Ensure text meets WCAG AA standards (minimum 4.5:1 for normal text, 3:1 for large text).

### 9. Anti-Patterns to Flag & Eliminate
- Disabling zoom with `user-scalable=no` or `maximum-scale=1`.
- `transition: all`.
- `outline: none` without `:focus-visible` styling.
- `<div>` or `<span>` elements acting as buttons without keyboard or ARIA support.
- Hardcoded date/number formats without locale-aware formatters.
- Unconstrained cards inside cards inside cards.
