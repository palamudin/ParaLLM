# Frontend Foundation

This document is the working guardrail for viewport, layout, accessibility, and front-end to back-end actuation in the ParaLLM shell.

It exists to keep future UI changes grounded in primary documentation instead of taste, drift, or prompt-driven correction.

Companion documents:

- [frontend-control-alignment.md](frontend-control-alignment.md)
  - maps current controls to the design-source ladder
  - defines the flatter replacement shell we should build toward
- [replacement-shell-spec.md](replacement-shell-spec.md)
  - locks the target view structure, visible-by-default sections, and build order

## Goal

The shell should be:

- clear about what action the user is about to trigger
- visually readable on desktop and mobile
- honest about provider/runtime state
- accessible enough that dynamic updates, navigation, and responsive collapse do not hide meaning

## Primary References

### Viewport and responsive layout

- MDN: `<meta name="viewport">`
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport
  - Baseline rule: use `width=device-width, initial-scale=1`
  - Do not disable zoom with `user-scalable=no`

- MDN: Responsive web design
  - https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design
  - Baseline rule: mobile-first layout, content-first collapse, not just cosmetic scaling

- Bootstrap 5.3: Breakpoints
  - https://getbootstrap.com/docs/5.3/layout/breakpoints/
  - Baseline rule: design around Bootstrap's mobile-first breakpoint ladder unless we have a strong reason not to
  - Default tiers:
    - `sm >= 576px`
    - `md >= 768px`
    - `lg >= 992px`
    - `xl >= 1200px`
    - `xxl >= 1400px`

- MDN: Container queries
  - https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries
  - Baseline rule: use container queries for panel-local adaptation when viewport breakpoints are too blunt

### Accessibility and page structure

- W3C WAI: Page regions
  - https://www.w3.org/WAI/tutorials/page-structure/regions/
  - Baseline rule: preserve meaningful `header`, `nav`, `main`, and `aside` structure
  - Collapsed or hidden sections should keep consistent order when visible

- W3C WAI: WCAG 2.2 Reflow understanding
  - https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
  - Baseline rule: target usable reflow at `320 CSS px` wide without loss of content or core function

- W3C APG: Tabs pattern
  - https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
  - Baseline rule: if we use `tablist` semantics, we should implement the pattern properly
  - Otherwise, use plain buttons/segmented controls without pretending they are tabs

- MDN: `aria-live`
  - https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-live
  - Baseline rule: dynamic status should be announced intentionally
  - `polite` for routine state updates
  - `assertive` only for urgent operator-impacting failures

### Forms and control layout

- Bootstrap 5.3: Forms layout
  - https://getbootstrap.com/docs/5.3/forms/layout/
  - Baseline rule: form controls should stack cleanly by default, then expand into grid layouts only where that improves comprehension

## Curated Design Source Hierarchy

The repo also carries a curated source pack at:

- [docs/references/design_sources.csv](references/design_sources.csv)

Use it as a project-specific decision ladder.

### Tier 1: Default references

These should drive most product and interface decisions.

- `WCAG 2.2`
  - accessibility floor
  - acceptance criteria, not optional polish

- `Deque WCAG 2.2 checklist`
  - practical QA pass
  - use for regression and PR review

- `Nielsen Norman Group usability heuristics`
  - use for fast UX sanity checks
  - prefer visibility, recovery, consistency, and clarity over cleverness

- `IBM Carbon`
  - primary enterprise visual and structural reference for this repo
  - especially good for dense dashboards, tables, panels, filters, and restrained admin surfaces

- `Microsoft Fluent 2`
  - use when the product needs to feel natural in Microsoft-heavy environments
  - especially relevant for M365, Entra, Defender, Intune-adjacent flows

- `shadcn/ui`
  - code-first composition reference
  - good for inspectable, modifiable component structure

- `Radix Primitives`
  - behavior reference for complex interaction primitives
  - especially focus, keyboard, dialog, popover, and menu logic

### Tier 2: Strong secondary references

- `GitHub Primer`
  - technical product clarity
  - useful for dev-facing tools, repo surfaces, and dense control bars

- `GOV.UK Design System`
  - best clarity-first reference for forms, validation, and workflow usability

- `USWDS`
  - useful secondary accessible component source for structured public/compliance screens

- `Atlassian Design System`
  - workflow-heavy UI reference
  - useful for task/ticket/operations tooling

- `Material 3`
  - use for layout rhythm and modern component polish
  - avoid drifting into consumer-mobile aesthetics for dense enterprise tools

- `Apple HIG`
  - use for hierarchy, restraint, and subtle depth
  - not as a literal admin dashboard template

### Tier 3: Supplemental references

- `UX4G Handbook`
  - formal process and rationale support

- `MOSIP UI Guidelines`
  - inclusive-design checklist for mixed-skill user surfaces

- `Jonelle Boyd UI Design System Guidelines`
  - field notes for table-heavy business UI

- code repos for `Carbon` and `GOV.UK`
  - inspect implementation patterns when behavior is unclear

## Practical Source Policy

When making frontend decisions in this repo:

1. Use `WCAG + Deque` for accessibility acceptance.
2. Use `NN/g` for usability judgment.
3. Use `Carbon` as the default enterprise visual/system reference.
4. Use `Fluent 2` where Microsoft-adjacent alignment matters.
5. Use `shadcn/ui + Radix` style composition/behavior as implementation guidance when relevant.
6. Use `GOV.UK` when the problem is form clarity, validation, and user recovery.

If sources conflict:

- accessibility standards beat visual preference
- operator clarity beats decorative ambition
- enterprise restraint beats novelty for core workflow surfaces
- component truth beats bespoke invention unless bespoke clearly improves usability

## Repo Implications

### 1. Viewport is correct, keep it simple

Current shell files already use:

- `index.html`
- `webviewindex.html`

with:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
```

This should remain the default unless we have a very specific documented reason to change it.

### 2. Do not "scale" the UI to solve density

If the interface feels crowded, fix:

- hierarchy
- collapse behavior
- panel priority
- overflow strategy

Do not solve it with:

- browser zoom tricks
- CSS zoom
- global transform scaling

### 3. Home needs one dominant action

`Home` is primarily an actuation surface.

The user should be able to answer:

- what will happen if I press `Send`?
- which provider/model path will execute?
- am I in `V1` or `V2`?
- am I getting `Para`, `Direct`, and/or `Judge`?

Any UI element that does not help answer those questions is secondary on `Home`.

### 4. Tabs must be real tabs or not tabs

Current shell uses tab-like controls for:

- engine version
- front canvas mode

If we keep ARIA tab semantics, implement them per APG:

- proper keyboard navigation
- clear active tab to tabpanel relationship
- consistent focus behavior

If we do not want full tab behavior, use plain buttons and remove fake tab semantics.

### 5. Dynamic status must map to urgency

Use `aria-live` intentionally:

- routine banners, progress, and non-blocking state: `polite`
- hard failures or operator-critical interruptions: `assertive`

Do not make every status update urgent.

### 6. Responsive collapse should preserve meaning

At narrow widths or short heights:

- the operator path stays visible first
- secondary diagnostics collapse
- debug mechanics move behind disclosure
- content order stays stable

This matters more than preserving identical desktop composition.

### 7. Provider truth must stay visible

Provider UI should reflect actual runtime posture:

- `primary`
- `deferred`
- `local later`

The user should not need repo history to understand whether a provider is on the main path.

## Acceptance Criteria For The Next UI Pass

### Layout and viewport

- No core view should require horizontal scrolling at `320 CSS px` width
  - exception: intentionally scrollable technical surfaces like code blocks or graph canvases
- `Home`, `Review`, and `Scores` should remain usable at `768px` width without hidden primary actions
- Dense control rails should collapse before chat/output becomes unusable

### Semantics and accessibility

- Landmark structure remains meaningful
- Fake tabs are either upgraded to real tabs or downgraded to honest buttons
- Dynamic status updates use appropriate `aria-live` behavior

### Actuation clarity

- `Home` shows a compact run contract before `Send`
- `Review` shows exact prompt and exact response clearly
- `Scores` shows lane source and winner state clearly

## Immediate Build Direction

For the next pass, prioritize:

1. `Home` run-contract panel
2. provider status badges and truth labels
3. `Scores` winner/loser emphasis
4. height-aware collapse of non-essential diagnostics
5. semantic cleanup of tab-like controls

That order should improve both usability and honesty without requiring a full redesign.
