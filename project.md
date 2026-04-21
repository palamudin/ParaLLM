# AI Loop POC

## Purpose

Build a local prototype for a two-process reasoning loop that keeps independent viewpoints, shares only structured checkpoints, preserves contradictions, and maintains an audit trail of every meaningful step.

## Core Idea

This is not "two minds." It is two separate process lanes with distinct roles:

- Worker A: utility / benefits / progress pressure
- Worker B: risk / adversarial / failure pressure
- Summarizer: canonical shared memory that merges checkpoints without erasing disagreement
- Summarizer output now needs a dual surface:
  - a seamless front-channel answer that reads like one normal LLM reply
  - a review-channel adjudication trace that shows what evidence and adversarial arguments shaped that answer

The design goal is sparse, structured sharing. The workers should not stream every token to each other. They should expose a steer packet at controlled intervals so each lane can react to the other without collapsing into a single blended process.

## Prototype Constraints

- Local-first on Windows with XAMPP, PHP, HTML, CSS, JavaScript, and now a resident Python runtime
- No Node requirement for the first prototype
- Frontend dependencies that become part of the shell baseline should be vendored locally instead of pulled from runtime CDNs
- Persistence kept in local JSON / JSONL files
- Every important step should be logged
- Contradictions should remain visible
- Assumptions must not be silently upgraded into facts

## Current Architecture

- `index.html`: local control panel and live state display
- `assets/app.js`: frontend polling and command dispatch
- `assets/app.css`: local styling
- `assets/vendor/bootstrap/`: locally vendored Bootstrap 5 shell baseline and utility/component layer
- `api/*.php`: PHP broker endpoints
- `runtime/*.py`: resident worker / summarizer runtime service
- `scripts/qa_check.py`: reusable QA harness for linting and reversible endpoint smoke checks
- `scripts/qa_live_check.py`: reusable live QA harness for budget-capped, source-restricted endpoint smoke checks
- `scripts/qa_eval_check.py`: reusable isolated-eval smoke harness for suites, arms, and run artifacts
- `scripts/qa_local_tools_check.py`: reusable read-only local-tool smoke harness for root policy, tool execution, and mocked Responses continuation
- `scripts/quality_benchmark.py`: blind quality benchmark for comparing direct output vs steered output on the same case
- `runtime/eval_runner.py`: isolated eval runner for suite/arm/replicate benchmarking outside the live singleton workspace
- `data/state.json`: canonical state
- `data/events.jsonl`: low-level event log
- `data/steps.jsonl`: structured step log for human-readable process trace
- `data/tasks/*.json`: task snapshots
- `data/checkpoints/*.json`: worker and summary checkpoints
- `data/outputs/*.json`: dedicated worker and summarizer output artifacts with response metadata for quality review
- `data/sessions/*.json`: archived session snapshots captured by Reset Session with carry-forward context
- `data/jobs/*.json`: background loop job metadata and result summaries
- `data/evals/`: isolated eval suites, arm manifests, run manifests, score files, and per-replicate workspaces
- `data/locks/loop.lock`: cross-process lock directory used by PHP and the resident Python runtime

## Runtime Options

- Execution mode: `live` or `mock`
- Default low-cost recommendation: `gpt-5-mini`
- Opinionated runtime profiles: `Low`, `Mid`, `High`, and `Ultra` for template-driven cost/depth tradeoffs
- Per-position model selection for each worker lane and the summarizer
- Per-worker directive selection with named lane personas such as `Proponent`, `Sceptic`, `Security`, and other focused adversaries
- Per-worker temperature qualifiers so each lane can stay cool, balanced, or hot while preserving its own point of view
- Reasoning effort can be tuned per task
- Optional grounded worker research with `web_search`, live-web toggle, and domain allow-lists
- Optional read-only local file tools for commander and worker lanes with repo-relative allow-roots
- Optional read-only GitHub repo tools for commander and worker lanes with owner/repo allow-lists
- Optional summarizer-guided dynamic adversarial lane spin-up for the next round when a missing viewpoint survives review
- Summarizer evidence-vetting mode that scores worker claims without doing its own web research
- Session budget guardrails for total tokens, estimated spend, per-call output tokens, and web-search tool calls
- API keys can be managed locally through the UI as a local key pool, with per-slot inputs, masked previews, and deterministic per-position assignment
- Form draft state is persisted locally so edits, roster changes, and loop settings do not get stomped by polling refreshes
- Secrets stay in `Auth.txt` locally as a one-key-per-line pool and should never be logged

## Sync Model

- Independence by default
- Sharing only at checkpoints, blocker conditions, or scheduled round boundaries
- Shared content should be summarized, structured, and tagged by source
- Workers can leave peer steer requests for the other lane
- Summaries must preserve stable findings, conflicts, conditional truths, and recommended next actions
- The summarizer should speak as its own evidence-based opinion, not as a narrator of what the workers did
- Review artifacts should keep expandable source lines so the summarizer's position can be audited later

## Current POC Features

- Dynamic worker roster starting with `Proponent` and `Sceptic`, with bounded adversarial expansion through additional lettered lanes
- Session context remains available for short carry-forward memory between sessions, but it now lives under `Debug` instead of the main Home flow
- Home is now chat-first: the main workflow is prompt plus `Send`, and that single action creates a task and kicks off the configured loop automatically
- The Home composer is now draft-first instead of active-task-first, so a stale task no longer overwrites the next-send `live` / `mock` setting after refresh
- Home chat polling now preserves scroll position and lane-inspector expansion state instead of snapping back to the bottom on every refresh
- Manual operations such as `Run Round`, `Run Auto Loop`, `Summarize`, `Refresh`, `Reset Session`, and `Reset State` now live under `Debug` instead of cluttering the main conversation flow
- Worker side controls now expose directive, temperature, and per-worker model selectors directly in the home rail, plus a `+ Add` lane button for on-demand adversarial expansion
- Home-side worker roster edits now stage the next send without mutating the currently displayed active task
- Manual single-target execution for any configured worker lane and the summarizer
- Manual single-round execution
- Autonomous multi-round execution with configurable round count and delay
- Cancellation that stops after the current round completes
- Detached background loop launching through `scripts/loop_runner.php`
- Shared-state locking between PHP and the resident Python runtime
- Resident Python runtime service on `127.0.0.1:8765` keeps worker/summarizer logic warm between calls instead of spawning a new shell process every step
- PHP dispatch now runs exclusively through the resident Python runtime
- Windows background launches now use a detached `cmd /c start` path instead of a PowerShell shim
- Live Python dispatch now applies target-aware structured-output token floors and a single retry on `incomplete: max_output_tokens`, while still recording the user-requested cap for auditability
- Stale queued/running job recovery based on queue age and heartbeat age
- Per-position model selection in the UI for workers and summarizer
- Settings now expose `Low` / `Mid` / `High` / `Ultra` runtime profiles that template worker model, summarizer model, reasoning effort, and budget ceilings for the next send
- Settings can now apply the current runtime template to all current worker lanes plus the summarizer, without requiring a new task
- Home now mirrors those runtime profiles with a compact quick-profile dashboard, staged-vs-active runtime summary, and `Sync Active` action so users do not have to dive into Settings for basic cost control
- The Home rail now lets users spawn the next adversarial lane from a selectable template such as `Security`, `Economist`, `User Advocate`, or other focused viewpoints instead of only taking the next default slot
- Grounded worker research mode using the OpenAI Responses API `web_search` tool with optional OpenAI-domain allow-lists
- Worker checkpoints now carry evidence ledgers, research queries, consulted source URLs, and evidence gaps
- Commander and worker lanes can now call audited local tools (`local_list_dir`, `local_read_file`, `local_search_text`) against explicit repo-relative roots, and those reads are logged into steps, checkpoints, and artifact metadata
- Commander and worker lanes can now call audited GitHub tools (`github_list_paths`, `github_read_file`, `github_get_issue`, `github_get_pull_request`, `github_get_commit`) against explicit owner/repo allow-lists, and those reads are logged into steps, checkpoints, and artifact metadata
- The summarizer can now request one additional adversarial lane for the next round, and when dynamic spin-up is enabled the runtime appends that worker with a visible audit step instead of silently mutating the roster
- Summarizer now acts as a vetter, preserving conflicts while scoring supported, mixed, weak, or disputed claims
- Each worker and summarizer run now saves a dedicated output artifact so quality can be inspected separately from canonical state
- Artifact Review UI supports side-by-side inspection of saved checkpoints and output artifacts
- Review now exposes recent-job operations for queued/interrupted/completed jobs, including bounded queue visibility plus `Resume`, `Retry`, and `Cancel` actions where allowed
- Review now exposes side-by-side round history cards, session archive replay/export controls, and a visible artifact exception policy for raw review-only outputs
- Review and artifact meta now surface requested vs effective output-token caps, retry attempts, and incomplete-output recovery notes directly in the UI
- URL/source normalization now drops malformed non-URL entries and canonicalizes saved source links in fresh artifacts
- Sidebar workspace shell now splits `Home`, `Settings`, `Debug`, and `Review`, with a chat-first center pane and the API key pool moved into Settings / Integrations
- The frontend shell now rides a local Bootstrap 5 baseline instead of a purely bespoke spacing/layout stack, which gives the app a tighter admin-style canvas and a saner light/dark foundation
- The sidebar is now a true collapsible admin rail with a header-anchored collapse control on desktop and slide-in behavior on smaller screens
- The Home composer footer is now intentionally compressed: quick tools and `Send` share one row, redundant composer help is removed, and empty attachment filler text no longer consumes vertical space
- The main thread now renders the Agent answer in a simpler chat format while worker lanes stay collapsed behind an `Inspect worker lanes` disclosure by default
- The main thread should now converge toward a truly seamless assistant reply, with internal lane reasoning removed from the public thread and moved into Review
- The summarizer now treats the visible answer as a lead direction that privately absorbs adversarial pressure, instead of outputting a recap or an averaged consensus blend
- The lead thread now performs a review-only control audit before answering: it records its first-pass draft, the question it applies to adversarial pressure, which objections it accepted or rejected, what concerns it held out, and the self-check it ran before finalizing the public answer
- Summaries now need a front-answer layer plus a review-only adjudication layer with cited worker line refs
- Review should expose the summarizer's current position, why it landed there, and the exact worker lines that shaped that judgment
- Reusable QA should exist as a first-class path so syntax checks and reversible endpoint smoke tests can be rerun quickly after runtime/UI changes
- Read-only tool paths should have their own explicit QA so tool-loop regressions get caught without spending live tokens
- GitHub/repo read tooling should share that same QA discipline so connector-like access can be verified without spending model tokens
- Dynamic lane spin-up should also have its own QA because a bad roster mutation is a state-management bug, not just a prompting bug
- Live QA should stay separate from mock QA so spend-bearing checks remain explicit, budget-capped, and domain-restricted
- Quality benchmarking should also be first-class so we can test whether steered output is actually better than a direct answer, not just more elaborate
- Isolated evals should live beside the app, not inside the interactive singleton state, so hidden gold answers and benchmark artifacts cannot contaminate normal tasks
- Session context is now treated as review/debug data rather than primary user input and has been moved out of the Home surface
- Fine tuning controls now live in Settings instead of crowding the main conversation surface, and the stored draft now includes worker roster, loop rounds, and loop delay
- Session usage accounting with token, web-search-call, and estimated-spend tracking in state, jobs, and the top-bar counters
- Usage spend now follows a conservative chargeable-search assumption: web-search-related model tokens are treated as billable and tool calls remain separately priced
- Budget stop behavior that marks work as `budget_exhausted` instead of running past configured limits
- Masked API-key-pool status in the top bar for local test-key swapping without exposing secrets
- Reset Session archives the current state to `data/sessions`, clears the active task, and reloads a fresh draft with short carry-forward context
- Per-round checkpoint snapshots such as `*_A_step002.json` and `*_summary_round002.json`
- UI history panels for recent jobs and checkpoint artifacts
- Optional live model execution with mock fallback still available
- Reusable `python scripts/qa_check.py` harness for Python/PHP/JS checks plus reversible mock endpoint smoke, with optional resident-runtime refresh to avoid stale-code false negatives
- The mock QA harness now also covers lane-template spawning, export/replay, bounded queueing, retry, and resume through the real PHP endpoints
- Reusable `python scripts/qa_live_check.py` harness for reversible live endpoint smoke with OpenAI-domain allow-lists, runtime refresh, and spend/token caps
- Verified live smoke run with grounded worker search and summarizer vetting against OpenAI-owned sources on April 18, 2026
- Verified widened live `A/B/C` run with grounded worker research, live summarizer vetting, and saved output artifacts on April 19, 2026
- Verified resident Python runtime dispatch on April 19, 2026 with mock `A/B/summarizer` execution through the existing PHP endpoints
- Verified resident Python runtime live path on April 19, 2026; model calls reached the Python runtime correctly and preserved the existing fallback-to-mock behavior when Responses API output was truncated by `max_output_tokens`
- Verified low-cap resident Python live run on April 19, 2026 with task budget `maxOutputTokens=500`; workers and summarizer still completed live because the runtime elevated to safe structured-output floors (`900` worker, `1400` summarizer) and retried to `1800` where needed
- Verified dynamic multi-adversarial roster on April 19, 2026:
  - mock `A/B/C` manual round completed with all 3 workers represented in summary/output artifacts
  - mock `A/B/C/D` manual round completed with all 4 workers represented in summary/output artifacts
  - mock `A/B/C/D/E` 2-round background loop completed with all 5 workers represented in summary/output artifacts
  - live `A/B/C` manual round completed through the resident Python runtime with usage tracked for `A`, `B`, `C`, and `summarizer`
- Verified chat-first send flow on April 19, 2026:
  - draft settings and worker roster can be saved before a task exists
  - `+ Add` works without an active task and grows the stored roster
  - worker directive / temperature / model changes persist through the new roster endpoints
  - `Send` creates a task from the staged roster and immediately starts the configured loop
- Verified live-mode refresh fix on April 19, 2026:
  - with an older mock task still active, the rendered Settings form now keeps the persisted draft's `executionMode=live`
  - a fresh manual live smoke task (`t-20260419-082140-1a296c`) completed through the resident Python runtime instead of falling back to mock
  - a second manual live task (`t-20260419-082140-4e6764`) confirmed the current project/key also has live access to `gpt-5.4-mini` and `gpt-5.4`
- Verified thread-behavior cleanup on April 19, 2026:
  - Home no longer forces the chat viewport to the bottom on every polling refresh
  - the lane inspector stays expanded while the displayed thread content is unchanged
  - lane inspection is now presented above the final Agent answer for users who want to review the internal lanes
- Verified release-validation send flow on April 19, 2026:
  - mock `start_task` plus `start_loop` smoke completed end to end with summary output saved
  - live `start_task` plus `start_loop` smoke completed end to end through the resident Python runtime
  - the live release-validation smoke used `6,422` total tokens for an estimated `$0.006562`
- Verified PowerShell removal on April 19, 2026:
  - manual target dispatch now uses `api/run_target.php` instead of the old `api/run_ps.php`
  - background loop launch and Python service startup still work without any `.ps1` worker scripts in the repo
  - after killing the resident Python service, both manual dispatch and a 1-round background live loop successfully relaunched it
- Verified reusable QA harness on April 19, 2026:
  - `python scripts/qa_check.py` passed after restarting the resident Python runtime to pick up the current backend code
  - the reversible mock smoke confirmed `frontAnswer`, `summarizerOpinion`, `reviewTrace`, and `lineCatalog` in both state and saved summary output artifacts
- Verified reusable live QA harness on April 19, 2026:
  - `python scripts/qa_live_check.py` passed after restarting the resident Python runtime to pick up the current backend code
  - the reversible live smoke stayed within the configured cap at approximately `$0.031216`, using `29,471` tokens and `2` web-search calls
  - worker research and citation URLs stayed within the OpenAI-owned allow-list
- Verified runtime-profile apply path on April 19, 2026:
  - the Settings UI now renders the new reasoning-profile cards and the `Apply Runtime To Current Task` action
  - a reversible endpoint smoke confirmed active-task runtime, summarizer model, worker models, and draft budget fields all moved together when applying a stronger template
- Verified front-dash runtime controls on April 19, 2026:
  - Home now renders the new `Quick profile` card, the header profile pill, and the `Sync Active` action
  - `python scripts/qa_check.py` still passed after the Home runtime dashboard changes
- Verified review-operations milestone closeout on April 19, 2026:
  - Review now renders recent-job cards with `Resume`, `Retry`, and `Cancel` actions where allowed
  - Review now renders round-history drill-down with direct side-by-side compare actions into the artifact panes
  - Review now renders session-archive replay/export controls plus the raw-artifact exception policy
  - requested vs effective output-token caps now render in review history and artifact meta, not only in saved JSON
  - `python scripts/qa_check.py` passed after exercising lane templates, export/replay, bounded queueing, retry, and resume through the real PHP endpoints
- Verified lead-answer architecture and profile-depth pass on April 19, 2026:
  - summary schema now records `leadDirection`, absorbed adversarial pressure, and integration mode alongside the public answer
  - live summarizer instructions now force one directional answer voice that privately pressure-tests itself against the strongest objections
  - quality profiles now retune auto-loop depth in addition to model, reasoning effort, and budget ceilings
  - `Apply Runtime To Current Task` now carries loop depth and delay into the active task as well as the draft
- Verified steer-vs-direct benchmark harness on April 19, 2026:
  - a new blind judge path compares a direct baseline answer against the public steered answer on the same prompt
  - the judge only sees anonymous `Answer A` / `Answer B` slots so it cannot bias toward the known architecture
  - the benchmark now rejects silent mock-fallback steer runs by default so a broken live path does not masquerade as a bad quality result
  - the benchmark now also scores lead-thread control over adversarial pressure and can sweep multiple loop depths in one run
  - repeat trials now aggregate score deltas for decisiveness, tradeoff handling, objection absorption, actionability, single-voice quality, and overall quality
  - benchmark reports now save locally under `data/benchmarks/`

## Immediate Milestones

- All eight milestone items from the previous pass are now closed in the product surface or resolved as explicit policy.
- Pricing policy now uses a conservative `assume_chargeable` stance for web-search-related model tokens, while still acknowledging that OpenAI-owned pages conflicted on April 19, 2026.
- The next exploration is no longer milestone debt but tuning: calibrate how strongly adversarial objections can narrow, redirect, or reverse the lead answer on difficult prompts without making the public voice collapse into hesitation, then validate those changes against the blind steer-vs-direct benchmark.

## Notes

- `Auth.txt` now acts as a local API key pool for testing, with one key per line. It must not be copied into logs, responses, or version control.
- Before committing, the repo should ignore secrets and volatile runtime data.
