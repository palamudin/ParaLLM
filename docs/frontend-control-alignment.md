# Frontend Control Alignment

This document translates the design-source ladder into concrete shell decisions for ParaLLM.

It treats `index_old.html` as the legacy fallback and `index.html` as the replacement shell we should continue refining.

## Decision

The current UI should be treated as:

- `index_old.html`: legacy shell, stable enough to keep as fallback
- `index.html`: replacement shell, the right surface to keep refining

The preferred path is:

1. keep the current shell working
2. stop deepening its nesting
3. build a replacement shell against the rules in:
   - [frontend-foundation.md](frontend-foundation.md)
   - [replacement-shell-spec.md](replacement-shell-spec.md)
   - [docs/references/design_sources.csv](references/design_sources.csv)

## Core Layout Rule

Use the visual hierarchy:

1. `shell`
2. `section`
3. `item`

Then stop.

The replacement shell should avoid:

- panel inside panel
- collapsible inside panel inside collapsible
- popup help inside already dense forms
- multiple equal-weight control surfaces competing on the same screen

## Source Ladder For This Repo

When controls conflict, use this order:

1. `WCAG 2.2 + Deque`
2. `NN/g`
3. `IBM Carbon`
4. `Fluent 2` when Microsoft-adjacent behavior matters
5. `shadcn/ui + Radix` for control composition and interaction behavior
6. `GOV.UK` for form clarity, validation, and recovery

## Current Shell Read

The current shell is strong on backend actuation and weak on visual hierarchy.

The main problem is not color, spacing, or typography. The main problem is over-nesting:

- `Home` nests runtime, workers, topology, chat, eval, and judge into one view
- `Settings` nests provider access, runtime controls, and help popups too deeply
- `Debug` repeats the same wrapper pattern even though it is secondary by nature
- the header behaves like a mini dashboard before the actual workspace begins

## Current Control Audit

### Header status pills

Current pattern:

- `workspace-pill-row`
- many equal-weight status pills before the main work surface

Relevant source guidance:

- `NN/g`: visibility of system status is good, but not if status overwhelms the task
- `Carbon`: status should support the workflow, not become a competing dashboard

Target:

- shrink to a smaller run-status strip
- show only the high-value fields by default:
  - task
  - active mode
  - progress
  - elapsed
- move secondary telemetry behind an expand action or debug surface

### Sidebar navigation

Current pattern:

- simple, workable, mostly clear

Relevant source guidance:

- `Carbon`: stable app shell and predictable sectioning
- `Primer`: technical product clarity and compact navigation

Target:

- keep the sidebar model
- keep the current view count small
- do not turn navigation into nested accordions

### Home controls

Current pattern:

- one large collapsible contains:
  - quick profile
  - workers
  - topology
- chat and evaluation surfaces sit below, but the view still feels control-heavy

Relevant source guidance:

- `NN/g`: recognition over recall, visible next action
- `Carbon`: one primary task per page region
- `GOV.UK`: plain-language setup, obvious actions, low mystery

Target:

- replace the large control block with one flat `Run contract` section
- the user should immediately understand:
  - what pressing `Send` will do
  - which provider/model path will execute
  - whether they are using `Para`, `Direct`, `Judge`, or some combination
- move worker and topology inspection into separate secondary sections, not the main run setup strip

### Inline help popups

Current pattern:

- many small `Info` triggers with popup text embedded inside dense surfaces

Relevant source guidance:

- `GOV.UK`: explain directly near the field
- `NN/g`: minimize hidden explanation burden
- `Radix`: complex overlays only when the interaction genuinely needs them

Target:

- prefer section intro copy over field-by-field popups
- reserve popovers for genuinely optional expert detail
- avoid requiring hover or repeated clicking just to understand the screen

### Settings controls

Current pattern:

- provider access
- runtime controls
- many advanced toggles
- many help popups

Relevant source guidance:

- `GOV.UK`: form clarity and recovery
- `Carbon`: disciplined grouping in admin/configuration screens
- `Fluent 2`: enterprise settings should feel ordered and scannable

Target:

- flatten into 3 top-level sections:
  - `Provider access`
  - `Runtime profile`
  - `Tools and limits`
- each section gets:
  - one plain-language intro
  - one control grid
  - advanced details only if truly needed

### Review and Scores

Current pattern:

- powerful, but source and outcome hierarchy can still be improved

Relevant source guidance:

- `Primer`: technical clarity
- `Carbon`: dense comparison layout
- `WCAG`: status and contrast must remain readable

Target:

- make provenance obvious:
  - exact prompt
  - exact response
  - exact lane/stage
- use visual contrast to separate:
  - para
  - direct
  - judge
- use restrained winner/loser hue, not decorative saturation

## Replacement Shell Structure

The replacement shell should use this shape:

### 1. App shell

- sidebar navigation
- compact status strip
- one active view at a time

### 2. Home

- `Run contract`
- `Conversation`
- `Supporting controls`

`Run contract` should be the first thing the operator sees.

It should answer:

- which engine path is active
- which providers/models are active
- whether direct/para/judge are armed
- whether tools/research are allowed
- what limits or policies apply

### 3. Repo

- repo graph and review tooling should live inside the replacement shell
- standalone repo tooling can remain as fallback, but not as the primary navigation path

### 4. Review

- exact prompt
- exact response
- normalized view
- raw view
- actuation trace

### 5. Scores

- side-by-side answer comparison
- judge outcome
- explicit provenance

### 6. Settings

- provider access
- runtime profile
- tools and limits

### 7. Debug

- session operations
- logs and traces

This should stay intentionally secondary.

## Migration Rules

When building the replacement shell:

- do not rewrite backend contracts to fit the UI
- keep V1 shell as fallback until replacement reaches parity
- prefer deleting wrappers over styling them harder
- prefer fewer controls visible by default
- prefer section-level explanation over popup-level explanation

## Acceptance Criteria

The new shell is on the right track when:

- a user can understand `Send` without opening a control wall
- no view requires more than 2 framed visual levels at once
- the main action of each view is obvious within a few seconds
- `Review` and `Scores` tell the truth without digging
- `Settings` reads like configuration, not like debug archaeology

## Immediate Next Steps

1. Mark the current shell as `legacy` in docs and planning.
2. Build a flatter replacement `Home` first.
3. Keep `Review` and `Scores` functionally rich, but visually clearer.
4. Only after the replacement shell proves parity should the legacy shell be retired from the main path.
