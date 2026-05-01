# Replacement Shell Spec

This is the build contract for the replacement ParaLLM shell.

It sits between:

- [frontend-foundation.md](frontend-foundation.md)
- [frontend-control-alignment.md](frontend-control-alignment.md)

The purpose of this document is to lock:

- the basic frame of the web presentation
- the dominant function of each view
- what must be visible by default
- what must stay secondary
- the order in which we should build

This is intentionally product- and workflow-first. It is not a CSS spec.

## Ground Rule

We agree on frame and function before styling.

Do not start by changing:

- colors
- shadows
- animations
- badge variants
- decorative density

Start by locking:

- app frame
- view purposes
- visible-by-default sections
- interaction truth

## Shell Principles

The replacement shell should be:

- easy to understand in under 10 seconds
- honest about what will happen when the user acts
- visually flatter than the legacy shell
- dense when useful, not dense by accident
- consistent across desktop and smaller viewports

## Visual Hierarchy Rule

Allowed hierarchy:

1. `app shell`
2. `section`
3. `item`

Avoid:

- panel inside panel
- collapsible inside collapsible
- multiple sibling dashboards at the same hierarchy level
- hidden explanation as the default way to understand a screen

## Primary Views

The replacement shell has 6 primary views:

1. `Home`
2. `Repo`
3. `Review`
4. `Scores`
5. `Settings`
6. `Debug`

The app may keep the existing legacy shell alive during migration, but this is the target structure.

## App Frame

### Required frame

- left navigation rail
- compact global status strip
- single active main view

### Global status strip

Must show, by default:

- current task or idle state
- current mode or run type
- progress
- elapsed

May show secondarily:

- worker count
- memory version
- job id
- secondary telemetry

### Navigation

Keep navigation flat:

- `Home`
- `Repo`
- `Review`
- `Scores`
- `Settings`
- `Debug`

No nested nav trees for this shell generation.

## Home

### Purpose

`Home` is the actuation surface.

The user should be able to answer, without opening a control wall:

- what will happen if I press `Send`?
- which engine path is active?
- which provider/model path is active?
- whether direct/para/judge are armed
- what constraints, tools, or limits currently apply

### Required visible sections

1. `Run contract`
2. `Conversation`
3. `Supporting controls`

### Run contract

This is the first-class section on `Home`.

It should show:

- engine version
- active provider and model
- direct/para/judge mode
- tools or research posture
- active limits or profile
- a short plain-language summary of the current run path

It should not require popups to understand.

### Conversation

This is the second major section.

It should contain:

- conversation thread
- input composer
- send action

The composer must remain visible without scrolling through dense control blocks first.

### Supporting controls

This section can contain:

- worker or lane summary
- topology or architecture summary
- selected advanced runtime controls

But it must stay secondary to `Run contract` and `Conversation`.

### Home anti-patterns

Do not:

- place eval and judge as nested sub-workspaces inside the main chat hierarchy
- lead with a large collapsible control wall
- require the user to open multiple help popups to understand the active path

## Repo

### Purpose

`Repo` is the in-shell code and graph review surface.

It exists so repository inspection, graph traversal, and code-orientation tools stay inside the main shell instead of splitting the operator into a separate disconnected page.

### Required visible sections

1. `Repo review viewport`
2. `Context note or toolbar`

### Repo priorities

The page should:

- stay inside the same shell frame
- preserve navigation continuity
- let the user inspect repo structure without losing Home, Review, or Scores context

### Repo migration rule

For the first pass, embedding the existing repo-review tool is acceptable.

Longer term, the preferred end state is:

- shared shell frame
- shared status language
- repo-review controls visually aligned with the rest of the replacement shell

## Review

### Purpose

`Review` is the truth surface.

It exists so the user can inspect what really happened.

### Required visible sections

1. `Exact prompt`
2. `Exact response`
3. `Normalized answer`
4. `Raw answer`
5. `Actuation trace`

### Review priorities

The page should make it obvious:

- what was sent
- what came back
- which lane or stage produced it
- whether the UI is showing normalized text or raw provider output

### Review anti-patterns

Do not:

- hide provenance behind multiple clicks
- mix raw and normalized views without clear labels
- make the user guess which stage they are looking at

## Scores

### Purpose

`Scores` is the decision surface for comparisons.

It exists to compare:

- `Para`
- `Direct`
- `Judge`

### Required visible sections

1. `Comparison header`
2. `Answer A / Answer B or Para / Direct panes`
3. `Judge outcome`
4. `Source provenance`

### Scores priorities

The page should make it obvious:

- which answer belongs to which lane
- who won and why
- where the compared outputs came from

### Scores presentation rules

- winner/loser hue should be restrained
- source labels should be explicit
- judge reasoning should be easy to scan

## Settings

### Purpose

`Settings` is the configuration surface.

It should feel like orderly configuration, not archaeology.

### Required visible sections

1. `Provider access`
2. `Runtime profile`
3. `Tools and limits`

### Provider access

Must make clear:

- which providers are primary
- which are deferred
- which are local-later
- where credentials come from

### Runtime profile

Must make clear:

- active quality or cost posture
- active engine defaults
- the practical effect of the profile

### Tools and limits

Must make clear:

- what inspection/research/tools are allowed
- what scopes or limits apply

### Settings anti-patterns

Do not:

- bury normal configuration behind debug framing
- explain each field only through popups
- mix operationally critical settings with rarely-used diagnostics by default

## Debug

### Purpose

`Debug` is the operator and QA support surface.

It is intentionally secondary.

### Required visible sections

1. `Session operations`
2. `Logs and traces`

### Debug rule

If something is only needed for:

- QA
- diagnosis
- manual intervention
- runtime forensics

it belongs here before it belongs on `Home`.

## Help Model

Preferred order:

1. section intro copy
2. inline field hint if necessary
3. popover only for optional expert detail

The replacement shell should reduce dependency on popup help.

## Mobile and Narrow Viewport Behavior

At narrow widths or short heights:

- `Run contract` stays visible ahead of secondary controls
- conversation stays easy to reach
- secondary diagnostics collapse first
- content order does not become confusing

Do not solve density with scale tricks.

## Build Order

### Phase 1: Agreement

Lock:

- this shell spec
- view purposes
- section list per view
- visible-by-default rules

### Phase 2: Static replacement frame

Build:

- new app shell frame
- new `Home` structure
- placeholder `Repo`, `Review`, `Scores`, `Settings`, `Debug` sections

Without full live wiring first.

### Phase 3: Home wiring

Wire the replacement `Home` to real backend state so the run contract tells the truth.

### Phase 4: Review and Scores wiring

Attach real provenance, answer comparison, and judge outcomes.

### Phase 5: Settings and Debug flattening

Move configuration and diagnostics into the new frame without reintroducing nesting.

### Phase 6: Legacy retirement decision

Only once the replacement shell has parity should the legacy shell stop being the default surface.

## Done Criteria

We can call the replacement shell direction correct when:

- the operator can understand the active run path quickly
- the main action of each view is obvious
- provenance is easy to inspect
- config is understandable without popup archaeology
- the UI feels flatter, calmer, and more intentional than the legacy shell
