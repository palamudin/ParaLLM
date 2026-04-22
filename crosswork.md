# Crosswork Coordination Board

Last updated: 2026-04-22 14:25:59 -07:00 (America/Los_Angeles)
Repo: `C:\xampp\htdocs\loop`

## Shared Goal
Apply proven dashboard design and architecture patterns from AdminLTE and ClankerCloud-style infrastructure visualization to ParaLLM without destabilizing active runtime work.

## Evidence Snapshot (for both agents)
- Local theme reference folder is AdminLTE `v4.0.0-rc7` (`C:\Temp\AdminLTE-master`), not v3.
- ParaLLM UI is currently monolithic:
  - `assets/app.css` ~2,935 lines
  - `assets/app.js` ~5,549 lines
  - `index.html` ~797 lines
- `assets/app.js` currently contains duplicate function definitions (later ones override earlier ones), e.g.:
  - `renderHomeRuntimeControls` at lines `1317`, `1461`, `3726`
  - `renderQualityProfileCards` at lines `1405`, `1549`
  - `renderHomeWorkerControls` at lines `3231`, `3344`
  - `buildWorkerControlCard` at lines `3294`, `3600`

## Design Direction
1. Keep existing product identity (agentic operations workspace), but tighten UI architecture to AdminLTE-grade consistency.
2. Add a focused, high-signal graph/topology surface inspired by ClankerCloud (context map, dependencies, status overlays), not a full visual clone.
3. Prioritize readability and operator decisions over decorative effects.

## Lane Ownership (no overlap)

### Lane A (Codex)
Owns visual system and component styling:
- `assets/app.css`
- `index.html` (structure + semantic wrappers only)
- optional new files under `assets/ui/` for modular CSS split

Responsibilities:
- Token system normalization (spacing, radius, elevation, color semantics)
- AdminLTE-style layout consistency (shell, cards, sections, side rail behavior)
- Visualization container scaffolding and CSS states (idle/warn/error/active)

### Lane B (GPT-5.4 High Reasoning)
Owns frontend behavior architecture:
- `assets/app.js`
- optional new files under `assets/js/` for split modules

Responsibilities:
- De-duplicate render functions and consolidate view-state logic
- Introduce module boundaries (api, state, render, events, view adapters)
- Wire visualization data contracts and state updates

### Shared / Review-only (both may read, only one edits at a time)
- `README.md`
- `project.md`
- `agent-skills-plan.md`

## Integration Contract
- Lane A does not change API request/response semantics.
- Lane B does not rename CSS hooks without adding a migration map in this file first.
- Any DOM contract changes must be recorded in section `DOM Contract Changes` before merge.

## DOM Contract Changes
- Home controls moved from right rail into a top collapsible block in Home:
  - wrapper: `details.home-controls-collapsible`
  - summary row: `.home-controls-summary`
  - control grid container: `.home-controls-grid`
- Chat panel is now the dominant Home surface under the collapsible controls (`.home-layout-chat-focused`).
- Added architecture preview widget IDs/hooks:
  - `#topologyNodeCount`
  - `#topologyEdgeCount`
  - `#topologyActiveCount`
- Footer architecture changed to collapsible body + persistent spend strip:
  - wrapper details: `#workspaceFooterDetails.workspace-footer-details`
  - collapsible summary: `.workspace-footer-summary`
  - collapsible body: `.workspace-footer-body`
  - checkpoints container: `#footerCheckpointList` (unchanged id)
  - loop elapsed status: `#footerLoopElapsed` (new id)
  - persistent expenditure strip: `.workspace-status-card-spend` with existing usage ids
- Branding/title labels updated:
  - sidebar brand mark/title now `ParaLLM`
  - workspace header title now `Super reasoning`
- Explanatory copy under Home control titles moved from static paragraphs to hover popups (`.inline-help-popup`) in:
  - `home-controls-summary` title
  - `Live topology` title

## Execution Plan (phased)

### Phase 1: Stabilize foundations
- Remove duplicate JS function definitions and dead overrides.
- Freeze and document core class naming convention for shell/panel/card/control states.
- Build a minimal style inventory map (current classes -> target component groups).

### Phase 2: Componentize UI shell
- Split monolithic CSS into clear bundles (`tokens`, `layout`, `components`, `states`).
- Align shell spacing and card composition with AdminLTE consistency principles.
- Keep Bootstrap utility interoperability intact.

### Phase 3: Agentic topology visualization
- Add a dedicated "Architecture / Topology" panel in Home or Review.
- Start with graph primitives:
  - nodes: commander, workers, summarizer, tools
  - edges: data/control flow
  - states: queued, running, completed, blocked
- Add hover detail panel tied to existing runtime metadata.

### Phase 4: Validation and hardening
- Responsive checks (desktop + mobile breakpoints).
- Accessibility pass (keyboard flow + contrast + reduced motion).
- QA smoke against existing scripts (`scripts/qa_check.py` and relevant live checks).

## Coordination Protocol
- Before starting a task: add an entry to `Active Work`.
- When blocked: add a short blocker note with owner and timestamp.
- When done: move item to `Completed` and include touched files.

## Action Log
- [2026-04-22 13:33 -07:00][Codex] Brought up local stack at `http://127.0.0.1:8787/` and verified HTTP `200`.
- [2026-04-22 13:40 -07:00][Codex] Added Home rail "Live topology" architecture preview panel scaffold in `index.html`.
- [2026-04-22 13:44 -07:00][Codex] Added topology visualization styles and panel elevation/token refinements in `assets/app.css`.
- [2026-04-22 13:49 -07:00][Codex] Refactored Home to chat-first layout with non-intrusive collapsible controls block under header.
- [2026-04-22 13:51 -07:00][Codex] Confirmed user preference: keep `crosswork.md` updated on every action.
- [2026-04-22 13:52 -07:00][Codex] Added responsive behavior for the new controls block (`2-col` medium, `1-col` small, compact summary on mobile).
- [2026-04-22 13:52 -07:00][Codex] Verified live page serves updated Home layout at `http://127.0.0.1:8787/` (`home-controls-ok` marker check).
- [2026-04-22 13:52 -07:00][Codex] Captured current UI screenshot to `C:\Temp\loop-home-chat-focused.png` for visual sanity check.
- [2026-04-22 13:53 -07:00][Codex] Ran quick encoding sanity scan on `index.html`; no malformed apostrophe sequences remain.
- [2026-04-22 13:53 -07:00][Codex] Confirmed new Home hooks/classes exist in source (`home-controls-*`, `topology-*`) for runtime wiring compatibility.
- [2026-04-22 13:53 -07:00][Codex] Re-validated local server remains active on `127.0.0.1:8787` after layout/CSS edits.
- [2026-04-22 13:54 -07:00][Codex] Ran `python scripts/qa_check.py`; overall harness failed only on `python-crossover` auth mutation check (`HTTP 409`, env-backed secret mode), not on frontend syntax/layout edits.
- [2026-04-22 13:54 -07:00][Codex] Accepted new UI request: make header thinner, remove subtitle copy, and compress top status pills into a single row.
- [2026-04-22 13:55 -07:00][Codex] Removed subtitle paragraph from header markup to reduce top-bar height.
- [2026-04-22 13:56 -07:00][Codex] Compressed header and status-pill CSS: smaller paddings/fonts, single-row pill lane with horizontal overflow instead of wrapping.
- [2026-04-22 13:56 -07:00][Codex] Reduced mobile header title override to stay consistent with slimmer desktop header.
- [2026-04-22 13:57 -07:00][Codex] Captured refreshed header screenshot at `C:\Temp\loop-header-thin-pass.png` for visual validation after compact pass.
- [2026-04-22 14:00 -07:00][Codex] Inspected current footer structure and bindings (`index.html`, `assets/app.css`, `assets/app.js`) for requested collapsible checkpoints/runtime + always-visible expenditure redesign.
- [2026-04-22 14:00 -07:00][Codex] Replaced footer markup with collapsible body (`details`) containing checkpoints first and current task/loop time underneath; moved expenditure to an always-visible full-width line.
- [2026-04-22 14:01 -07:00][Codex] Added footer collapse/spend styles and one-line expenditure strip behavior in `assets/app.css`.
- [2026-04-22 14:02 -07:00][Codex] Wired loop elapsed footer value in `syncWorkspaceStatus()` via new `#footerLoopElapsed` binding in `assets/app.js`.
- [2026-04-22 14:02 -07:00][Codex] Validation: `node --check assets/app.js` passed; new footer ids/classes confirmed via ripgrep; server still listening on `127.0.0.1:8787`.
- [2026-04-22 14:06 -07:00][Codex] Accepted naming/compactness request: brand area -> ParaLLM, header title -> Super reasoning, and explanatory text under section titles moved to hover info popups.
- [2026-04-22 14:07 -07:00][Codex] Applied requested copy/label updates in `index.html` and replaced visible explanatory paragraphs with hover-info popups for Home controls and topology.
- [2026-04-22 14:07 -07:00][Codex] Validation: live content probe confirms `ParaLLM`, `Super reasoning`, and workspace controls hover-info hook strings are served at `http://127.0.0.1:8787/`.
- [2026-04-22 14:07 -07:00][Codex] Captured visual check screenshot at `C:\Temp\loop-brand-hover-info-pass.png`.
- [2026-04-22 14:08 -07:00][Codex] Accepted follow-up header-controls request: force single-row control lane and further reduce control visual size.
- [2026-04-22 14:09 -07:00][Codex] Updated header-controls CSS lane to true one-row flow (theme toggle + pills) with additional size reduction for pills/toggle text and paddings.
- [2026-04-22 14:09 -07:00][Codex] Aligned responsive overrides (`<=1100`, `<=720`) to preserve one-row behavior and avoid oversized full-width toggle buttons.
- [2026-04-22 14:10 -07:00][Codex] Validation: updated header-control selectors confirmed in `assets/app.css`; server remains live on `127.0.0.1:8787`.
- [2026-04-22 14:10 -07:00][Codex] Captured quick visual snapshots at `C:\Temp\loop-header-controls-onerow-minified.png` and `C:\Temp\loop-header-controls-onerow-minified-2.png` (operator modal still overlays primary view).
- [2026-04-22 14:11 -07:00][Codex] Accepted chat-font tuning request: make chat UI text slightly smaller with ChatGPT-like readability baseline.
- [2026-04-22 14:12 -07:00][Codex] Applied subtle chat-font reduction in `assets/app.css` for conversation thread/messages/meta tags and composer textarea (`~15px` equivalent via `0.9375rem`).
- [2026-04-22 14:12 -07:00][Codex] Validation: updated chat-font selectors confirmed via ripgrep; local server remains live on `127.0.0.1:8787`.
- [2026-04-22 14:13 -07:00][Codex] Regression report received: user sees blank/non-rendering webapp. Started incident triage (HTTP 200, listener alive, JS syntax check currently passes).
- [2026-04-22 14:15 -07:00][Codex] User supplied browser console error: `workerProvider is not defined` in `renderQualityProfileCards` (`assets/app.js`). Started targeted JS hotfix.
- [2026-04-22 14:16 -07:00][Codex] Patched `renderQualityProfileCards` in `assets/app.js` so `workerProvider`/`summarizerProvider` and profile model configs are defined before use; `node --check assets/app.js` passes.
- [2026-04-22 14:17 -07:00][Codex] Added cache-busting query params to `index.html` asset includes (`assets/app.css`, `assets/app.js`) to force clients off stale bundles after runtime error regression.
- [2026-04-22 14:18 -07:00][Codex] Validation pass complete: homepage serves new asset versions and `assets/app.js` syntax check remains green (`INDEX_ASSET_BUST_OK`, `APP_JS_SYNTAX_OK`).
- [2026-04-22 14:19 -07:00][Codex] Accepted new UI request: reorient `Eval`, `Settings`, and `Debug` into full-width, collapsible group layout similar to Home dashboard.
- [2026-04-22 14:19 -07:00][Codex] Audited `index.html` + `assets/app.css` section structure for `data-view=\"settings\"`, `data-view=\"debug\"`, and `data-view=\"eval\"` to prepare non-breaking DOM refactor.
- [2026-04-22 14:23 -07:00][Codex] Refactored `index.html` structure for `settings`, `debug`, and `eval` views into Home-style `details` group containers with collapsible summaries while preserving existing ids and JS bindings.
- [2026-04-22 14:24 -07:00][Codex] Added new shared collapsible group styling in `assets/app.css` (`.view-group-*`) and switched `settings/debug/eval` layouts to full-width stack flow with grouped sub-grids.
- [2026-04-22 14:25 -07:00][Codex] Responsive pass: wired new group grids into mobile breakpoints and validated live HTML/CSS hooks + JS syntax (`GROUP_LAYOUT_MARKUP_OK`, `APP_JS_SYNTAX_OK`).
- [2026-04-22 14:25 -07:00][Codex] Replaced non-ASCII collapse caret glyphs with ASCII `v` in `index.html` group summaries to keep encoding safe across environments.
- [2026-04-22 14:12 -07:00][GPT-5.4 High Reasoning] Starting provider/runtime/skills batch. First write set is `runtime/engine.py`, `.agents/persona-skill-map.json`, new provider skills under `.agents/skills/`, and `backend/tests/test_runtime_auth.py`. No CSS or markup changes planned in this batch.
- [2026-04-22 14:18 -07:00][GPT-5.4 High Reasoning] Added provider supplement skills and provider-to-skill mapping under `.agents/`. Next write set is runtime transport and prompt loading only; still no CSS or HTML work planned.
- [2026-04-22 14:24 -07:00][GPT-5.4 High Reasoning] Entering runtime transport work in `runtime/engine.py`: adding xAI Responses support plus Anthropic or MiniMax Messages-compatible support. Still avoiding `assets/app.css` and `index.html`.
- [2026-04-22 14:35 -07:00][GPT-5.4 High Reasoning] Runtime transport adapters are in progress in `runtime/engine.py`. Next substep is provider-aware prompt skill loading for commander, workers, commander-review, and summarizer.
- [2026-04-22 14:41 -07:00][GPT-5.4 High Reasoning] Resynced with current `crosswork.md`, `runtime/engine.py`, and `assets/app.js`. Next write set is runtime prompt skill injection first, then functional-only provider wiring in `assets/app.js`. Still avoiding CSS/HTML lanes.
- [2026-04-22 14:43 -07:00][GPT-5.4 High Reasoning] Beginning prompt wiring in `runtime/engine.py`: attaching provider-aware shared context and persona skills to commander, commander-review, workers, and summarizer instructions.
- [2026-04-22 14:47 -07:00][GPT-5.4 High Reasoning] Runtime prompt wiring landed in `runtime/engine.py`. Next write set is functional-only provider UX in `assets/app.js`: provider catalogs, defaults, capability gating, and quality-profile behavior.
- [2026-04-22 14:55 -07:00][GPT-5.4 High Reasoning] Starting `assets/app.js` provider UX patch. Scope: expand provider catalogs beyond OpenAI or Ollama, retarget auth assignment previews by provider, and auto-disable unsupported research/tool toggles when provider changes.
- [2026-04-22 15:01 -07:00][GPT-5.4 High Reasoning] Frontend provider UX patch is in progress. Final substep for this batch is server-side capability enforcement in `backend/app/control.py` and `backend/app/settings.py` so unsupported tool flags cannot persist through direct payloads.
- [2026-04-22 15:06 -07:00][GPT-5.4 High Reasoning] Provider UX and backend capability guards are in place. Final runtime touch for this batch is exposing active skill names in stage metadata so provider-specific prompt changes are visible in Review artifacts.
- [2026-04-22 15:11 -07:00][GPT-5.4 High Reasoning] Found active duplicate overrides in `assets/app.js`. Final frontend fix is patching the last `renderHomeRuntimeControls` definition so provider-aware profile details are not shadowed by an older copy.
- [2026-04-22 15:14 -07:00][GPT-5.4 High Reasoning] Pre-verification bug catch: renamed a shadowed `showMessage` parameter inside provider capability enforcement before running checks.
- [2026-04-22 15:16 -07:00][GPT-5.4 High Reasoning] Entering verification. Running JS syntax and the targeted Python backend/runtime tests before any final cleanup.
- [2026-04-22 15:17 -07:00][GPT-5.4 High Reasoning] Verification surfaced 2 expected test mismatches: old assertions assumed unsupported provider features stay enabled in draft/runtime state. Updating tests to the new provider-capability contract now.
- [2026-04-22 15:19 -07:00][GPT-5.4 High Reasoning] Updated the failing tests to assert provider capability gating for Ollama. Re-running the same verification set now.
- [2026-04-22 15:25 -07:00][GPT-5.4 High Reasoning] Extending the provider pass one step further based on official docs: Ollama gets structured local function-tool loops (local files/GitHub), while live web search stays disabled. Updating runtime, frontend capability maps, and tests together.

## Active Work
- [A][Codex][2026-04-22 13:51 -07:00] Finalizing chat-first Home CSS polish and responsive behavior after collapsible controls refactor.
- [B][GPT-5.4 High Reasoning][2026-04-22 14:07 PT] Claimed provider/runtime/skills integration lane. Planned touch set: `runtime/engine.py`, `backend/app/settings.py`, `backend/app/control.py`, `.agents/*`, `backend/tests/*`, and functional-only updates in `assets/app.js`. Avoiding `assets/app.css` and `index.html` unless a DOM contract change becomes unavoidable.

## Blockers
- `qa_check.py` currently reports expected `python-crossover` auth mutation conflict when secret backend is `env` (`/v1/auth/keys` returns `409`).

## Completed
- [A][Codex][2026-04-22] Audited AdminLTE structure and ClankerCloud-style interaction model; captured transfer-ready improvement themes.
- [A][Codex][2026-04-22 13:33 -07:00] Started and validated local server on `127.0.0.1:8787`.
- [A][Codex][2026-04-22 13:49 -07:00] Delivered initial chat-first dashboard structure (collapsible top controls + topology panel scaffold).
2026-04-22 Codex: Resuming provider-vendor wiring pass. Next batch is Ollama tool-loop completion in `runtime/engine.py`, test expectation reconciliation, then verification. Avoiding CSS/visual files except for any unavoidable provider UX bugfixes already in `assets/app.js`.
2026-04-22 Codex: Confirmed current official docs support the intended transport split: Anthropic/MiniMax via Messages-compatible tool loop, xAI via Responses/tooling, Ollama via local `/api/chat` function tools. Patching the remaining Ollama dispatcher branch now.
2026-04-22 Codex: Editing `runtime/engine.py` plus provider runtime tests together. Scope is backend/runtime only: allow Ollama function tools, continue rejecting hosted-style non-function tools, and reconcile Ollama capability expectations in `test_control.py` / `test_settings.py`.
2026-04-22 Codex: Runtime patch is in. Starting verification on `runtime/engine.py`, provider auth/runtime tests, and JS syntax for `assets/app.js`. No visual-file edits in this batch.
2026-04-22 Codex: Verification passed (`node --check assets/app.js` and targeted backend unittest suite). Running a final consistency sweep for stale provider-doc text before I wrap this batch.
2026-04-22 Codex: Found stale provider-status text in `README.md` and `project.md`. Updating those docs only to reflect that Anthropic/xAI/MiniMax live adapters are now wired and Ollama supports local function tools but still not hosted web search.
2026-04-22 Codex: Final grep pass for stale provider claims is running now, then this backend/runtime batch is ready to hand off cleanly.
2026-04-22 Codex: Investigating API key group UI after recent refactor. Focus is settings/auth behavior only: read `crosswork.md`, inspect current `assets/app.js` + backend auth/backend-status path, and fix "local env" / add-key mismatch without changing the current visual styling.
2026-04-22 Codex: Root cause found. Current local session has `Auth.txt`, but unset `LOOP_SECRET_BACKEND` still defaults to `env`, which makes the browser key editor read-only. Patching backend topology defaulting so existing local `Auth*.txt` files imply `local_file` unless an explicit backend or provider env keys are present.
2026-04-22 Codex: Backend defaulting patch landed in `backend/app/config.py` with infra coverage. Verifying that local roots with existing `Auth*.txt` files now surface `local_file` and re-enable browser-side key editing without UI style changes.
2026-04-22 Codex: Verification passed in-process (`local_file`, `writable=true`, `keyCount=6` at repo root). Checking whether the currently running server on `127.0.0.1:8787` has auto-reloaded or needs a restart for the browser to see the fix.
2026-04-22 Codex: Live server did not auto-reload; `/v1/auth/status` still reports the stale `env` backend from the old process. Inspecting the local Python process command line now so I can restart the control-plane cleanly.
2026-04-22 Codex: Found a second root cause in `scripts/run_local_stack.py`: it was forcing `LOOP_SECRET_BACKEND=env` by default into child processes. Patching the launcher now so unset backend means "let the app infer" instead of hard-locking env mode.
2026-04-22 Codex: Launcher patch landed. Verifying `scripts/run_local_stack.py` now leaves `LOOP_SECRET_BACKEND` unset by default, then restarting the local stack so `/v1/auth/status` reflects the corrected backend in-browser.
2026-04-22 Codex: Launcher verification passed. Recycling the old `run_local_stack.py` + backend processes and starting a fresh local stack with the same no-arg command so auth status updates live.
2026-04-22 Codex: Starting credential-storage refactor per user request. Goal is to make a real secret-manager-backed path the primary persistent provider-key store so keys survive restarts without relying on `Auth*.txt` or reboot-time env injection. Scope is backend secret storage, control-plane auth status/mutation flow, launcher/docs/tests, and minimal functional JS only if needed. No CSS changes planned.
2026-04-22 Codex: Pausing the broader refactor for a validation gate per user request. Next step is a smoke test plus one minimal live-auth-path test against the current `Auth.txt` flow before proceeding further, since concurrent-agent editing may have destabilized the running session.
2026-04-22 Codex: Smoke gate in progress. `/health` and `/v1/auth/status` are healthy on the current local stack and show `local_file` + writable OpenAI keys from `Auth.txt`. Full QA suite found one stale expectation in `backend/tests/test_app.py` that still assumes the old local `env` default. Preparing a minimal live-auth-path check now.
2026-04-22 Codex: Using the repo’s existing `scripts/qa_live_check.py` harness for the live-auth-path validation. Running the minimal reversible live smoke against the current `Auth.txt` setup now rather than inventing a custom flow.
2026-04-22 Codex: `qa_live_check.py` reached the live path but failed on an outdated stage order (`summarizer` before `commander_review`), not on auth. Running the same live validation manually with the current target sequence now to confirm that `Auth.txt` still powers real authenticated calls.
2026-04-22 Codex: Manual live validation is using the current target order `commander -> A -> B -> commander_review -> summarizer`, with web research disabled to keep spend minimal while still proving real authenticated provider calls.
2026-04-22 Codex: Switching to repo-maintainer audit mode per user request after crash/memory loss. Next batch is a whole-repo consistency sweep against `README.md` and `project.md`, then a full test run and targeted cleanup for anything clearly out of alignment.
2026-04-22 Codex: Expanding the maintainer audit to include `git log` and recent commit diffs so repo history, current docs, and present implementation are reviewed together instead of relying on lost chat context.
2026-04-22 Codex: Commit history review completed for orientation: Python-first cutover -> secret backend hardening -> provider abstraction -> vendor-neutral skills. Current drift scan already found stale assumptions in docs/tests/live QA around local secret defaults and target sequencing. Running the test gate now from that maintainer baseline.
2026-04-22 Codex: Maintainer conclusion from docs/history/tests: the recent implicit `Auth.txt -> local_file` local default drift does not match the repo’s intended direction. Reverting that drift and fixing the stale live-smoke target order now before re-running the test gate.
2026-04-22 Codex: Reverted the temporary local default drift in `backend/app/config.py` and `scripts/run_local_stack.py`, removed the contradictory infra tests, and updated `scripts/qa_live_check.py` to include `commander_review` in the live target sequence. Re-running the test gate now.
2026-04-22 Codex: Maintainer test gate is green (`unittest`, `qa_check --skip-smoke`, JS syntax). Running one final live smoke against the currently running `Auth.txt` session with the fixed target order to confirm a real authenticated path before wrapping the audit.
2026-04-22 Codex: Live smoke did not fail on auth or target order; it hit an already-active autonomous loop in the current workspace. Inspecting live state and, if safe, cancelling that loop before one last rerun of the same bounded smoke.
2026-04-22 Codex: Follow-up maintainer sweep completed. Current local server still serves the older `local_file` state and reports an active task `t-20260422-150621-6a9010`, so live verification remains blocked by runtime state rather than repo code health.
2026-04-22 Codex: Confirmed the repo baseline is green from disk (`python -m unittest`, `python scripts/qa_check.py --skip-smoke --no-restart-runtime`, and `node --check assets/app.js`). Also flagged duplicate function definitions in `assets/app.js` as a follow-up maintainability cleanup for the refactor branch.
2026-04-22 Codex: Starting duplicate-UI cleanup per user request. Scope is functional JS only: inspect duplicate definitions in `assets/app.js`, keep the newest UI-oriented versions, remove stale predecessors, and leave `assets/app.css` / visual styling untouched.
2026-04-22 Codex: Duplicate-state cleanup completed in `assets/app.js`. Removed stale shadow copies of `renderHomeRuntimeControls`, `renderQualityProfileCards`, `renderHomeWorkerControls`, and `buildWorkerControlCard`, keeping only the newest provider-aware/status-aware versions so the UI state has one authoritative renderer per surface.
2026-04-22 Codex: Verification after duplicate cleanup is green (`node --check assets/app.js` and `python -m unittest`). No CSS or HTML changes in this batch.
2026-04-22 Codex: Investigating footer `error` after `Sync Active`. Current runtime state shows no running job; loop is `error` with `job-20260422-150621-113382` and dispatch is idle. Found a state bug: `Sync Active` rebuilds draft from the active task in `backend/app/settings.py`, which can erase newly staged workers.
2026-04-22 Codex: Patching the sync path so staged draft worker roster is preserved and applied intentionally instead of being clobbered by the old active task state. Scope is backend settings logic and tests only.
2026-04-22 Codex: Sync-path patch landed in `backend/app/settings.py` with coverage in `backend/tests/test_settings.py`. `apply_runtime_settings()` now preserves staged draft workers instead of overwriting draft from `activeTask`. Verified with `python -m unittest backend.tests.test_settings` and full `python -m unittest` (109 tests).
2026-04-22 Codex: Operator-state note: there is currently no running job. Footer `error` is coming from the last loop record (`job-20260422-150621-113382`), which failed with `Worker A is not aligned with commander round 2.` Step history shows worker `C` was added repeatedly, then a later runtime sync collapsed the state back to a 2-worker draft before this patch.
2026-04-22 Codex: Starting operator reset + live validation batch. Next steps: use the supported session/state reset endpoints, restart the local stack so the running server picks up the sync-path patch, run a fresh 1-round / 2-worker live smoke, then update `README.md` to document the new provider/runtime skill pack before commit/push.
2026-04-22 Codex: Confirmed the current local stack is a single `scripts/run_local_stack.py` process. Restarting it on the explicit `local_file` backend so the fresh validation run still sees the existing provider keys in `Auth*.txt` while loading the latest backend code.
2026-04-22 Codex: Local stack restart succeeded. Proceeding with a full workspace state reset so the stale errored loop/job no longer owns the footer before the fresh live loop validation.
2026-04-22 Codex: Workspace state reset completed. Launching a fresh live task with the canonical 2-worker roster (`A` proponent, `B` sceptic) and a single auto-loop round to validate end-to-end job state after the sync-path patch.
2026-04-22 Codex: Fresh 1-round / 2-worker live loop reproduced a backend/runtime contract bug. Control plane is healthy on `local_file`, but the background loop immediately failed before any calls with `Live run requires OpenAI keys from the env secret backend...`, which means the subprocess path is not inheriting the selected secret backend correctly.
2026-04-22 Codex: Patching loop-job launch to pass the resolved secret backend/auth path explicitly into the subprocess environment instead of relying on inherited shell state. This should make control-plane auth state and background-loop auth state match.
2026-04-22 Codex: Loop-job env pinning patch landed in `backend/app/jobs.py` with coverage in `backend/tests/test_jobs.py`. Targeted and full test suites are green. Restarting the local stack again so the live loop runner uses the new launcher code before repeating the same validation run.
2026-04-22 Codex: Repeated the same fresh 1-round / 2-worker live loop after restart and still reproduced the `env secret backend` failure with zero calls made. The launcher env is no longer the only suspect; tracing the runtime live-execution secret-resolution path now.
2026-04-22 Codex: Likely process-level cause found: killing `scripts/run_local_stack.py` on Windows may leave the real `python -m backend.app` child orphaned and still serving stale code. Auditing and fully recycling backend/loop-worker processes before the next validation run.
2026-04-22 Codex: Confirmed via bind logs: a stale orphaned `python -m backend.app` process was still holding port `8787`, so `run_local_stack.py` restarts were not actually replacing the live server. Switching to a direct `backend.app` launch with explicit env for the rest of this validation batch.
2026-04-22 Codex: Direct backend launch is now authoritative: `python -m backend.app` on port `8787` with `secretBackend=local_file` and no orphaned wrapper process. Re-running the same reset + 1-round / 2-worker live loop on this known-good server.
2026-04-22 Codex: Fresh live validation passed on the direct backend. The 1-round / 2-worker loop completed with `status=completed`, workers `A,B`, and live usage recorded across commander, both workers, commander review, and summarizer. Moving to README updates for the new skill packs before commit/push.
2026-04-22 Codex: `README.md` now documents the shared advisor skills plus the provider/runtime-specific skill layer (`openai`, `anthropic`, `xai`, `minimax`, `ollama`). Final repo check and commit/push are next.
2026-04-22 Codex: Final gate is green: `python -m unittest` (110 tests), `node --check assets/app.js`, and a fresh direct-backend live loop with 1 round / 2 workers completed successfully. Committing and pushing the current branch state now.
2026-04-22 Codex: Git add completed, but commit hit a stale `.git/index.lock`. Verifying there is no active git process, clearing the stale lock, then retrying commit/push sequentially.
2026-04-22 Codex: Commit and push succeeded on `codex/vendor-neutral-advisor-skills` at `523439f`. Final local check is just a clean worktree confirmation before handoff.
