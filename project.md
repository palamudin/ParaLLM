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

- Local-first on Python, HTML, CSS, and JavaScript, with the shell and control plane now served directly by Python
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
- `runtime/*.py`: reasoning engine and eval runner
- `backend/app/*.py`: active Python control plane and Python-served shell
- `deploy/`: Docker Compose stack and container images for the Python-only self-host path
- `scripts/qa_check.py`: reusable QA harness for linting and reversible endpoint smoke checks
- `scripts/qa_live_check.py`: reusable live QA harness for budget-capped, source-restricted endpoint smoke checks
- `scripts/qa_eval_check.py`: reusable isolated-eval smoke harness for suites, arms, and run artifacts
- `scripts/qa_local_tools_check.py`: reusable read-only local-tool smoke harness for root policy, tool execution, and mocked Responses continuation
- `scripts/qa_python_crossover_check.py`: reusable crossover smoke that boots the Python control plane, serves the shell from ASGI, and exercises the migrated write/job/eval paths end to end
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
- `data/locks/loop.lock`: cross-process lock directory used by the Python control plane and its worker subprocesses

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
- Optional commander-review-guided dynamic adversarial lane spin-up for the next round when a missing viewpoint survives review
- Summarizer evidence-vetting mode that scores worker claims without doing its own web research
- Session budget guardrails for total tokens, estimated spend, per-call output tokens, and web-search tool calls
- API keys can be managed locally through the UI as a local key pool, with per-slot inputs, masked previews, and deterministic per-position assignment
- Form draft state is persisted locally so edits, roster changes, and loop settings do not get stomped by polling refreshes
- The transitional local fallback can still store secrets in `Auth.txt` as a one-key-per-line pool, but the preferred paths are now `env`, `docker_secret`, or `external`

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
- Detached background loop launching through `backend/workers/loop_job.py`
- Shared-state locking between the Python control plane and worker subprocesses
- Python dispatch now runs directly through the backend control plane and worker subprocesses
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
- The separate commander review pass can now request one additional adversarial lane for the next round, and when dynamic spin-up is enabled the runtime appends that worker with a visible audit step instead of silently mutating the roster
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
- The repo now carries a first self-hostable Python deployment path under `deploy/`, with:
  - the Python-served shell and control plane in one service
  - named volumes for runtime data and the transitional auth file
- Runtime/storage/auth paths now accept environment overrides so the stack no longer assumes one legacy Windows-local filesystem shape
- The Python control plane can now serve the shell itself at `/` and `/index.html`, so the app no longer depends on an external web server for normal local use
- The frontend now calls `/v1/*` routes directly, so the active shell no longer depends on legacy route naming
- Session usage accounting with token, web-search-call, and estimated-spend tracking in state, jobs, and the top-bar counters
- Usage spend now follows a conservative chargeable-search assumption: web-search-related model tokens are treated as billable and tool calls remain separately priced
- Budget stop behavior that marks work as `budget_exhausted` instead of running past configured limits
- Masked API-key-pool status in the top bar for local test-key swapping without exposing secrets
- Reset Session archives the current state to `data/sessions`, clears the active task, and reloads a fresh draft with short carry-forward context
- Per-round checkpoint snapshots such as `*_A_step002.json` and `*_summary_round002.json`
- UI history panels for recent jobs and checkpoint artifacts
- Optional live model execution with mock fallback still available
- Reusable `python scripts/qa_check.py` harness for Python/JS checks plus reversible mock endpoint smoke, with optional resident-runtime refresh to avoid stale-code false negatives
- The mock QA harness now also covers lane-template spawning, export/replay, bounded queueing, retry, and resume through the active Python endpoints
- Reusable `python scripts/qa_live_check.py` harness for reversible live endpoint smoke with OpenAI-domain allow-lists, runtime refresh, and spend/token caps
- Verified live smoke run with grounded worker search and summarizer vetting against OpenAI-owned sources on April 18, 2026
- Verified widened live `A/B/C` run with grounded worker research, live summarizer vetting, and saved output artifacts on April 19, 2026
- Verified resident Python runtime dispatch on April 19, 2026 with mock `A/B/summarizer` execution through the control-plane endpoints
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
  - manual target dispatch now uses the active control-plane route instead of the old PowerShell shim
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
  - `python scripts/qa_check.py` passed after exercising lane templates, export/replay, bounded queueing, retry, and resume through the active control-plane endpoints
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

## Archived Milestones

- The previous product-surface milestone set is no longer the main blocker. The next work is split into an alignment blocker plus a new roadmap track.
- Pricing policy still uses a conservative `assume_chargeable` stance for web-search-related model tokens, while acknowledging the OpenAI-owned pricing-page conflict from April 19, 2026.

### Alignment Blocker: True Separate Pass Closure

- The true separate path is now wired as `commander -> workers -> commander_review -> summarizer`, and a live run on April 20, 2026 proved that commander review can:
  - preserve its own course decision
  - emit a polished `dynamicLaneDecision`
  - spin a concrete next-round persona such as `Abuse Cases`
  - attach a purpose-built pressure instruction instead of a generic template
- The remaining blocker is round scoping:
  - when commander review appends a new worker for the next round, the autonomous loop currently treats that worker as if it were required for the current round before summarization
  - that causes the loop to fail with `All configured worker checkpoints are required before summarizing.` even though the new lane was intentionally meant for the following round
- The next patch needs to make roster requirements round-aware:
  - freeze the worker roster at round start
  - let commander review append `activeFromRound = currentRound + 1`
  - require summarizer alignment only against the round-start roster, not the newly expanded roster
  - reflect the same rule in control-plane preflight, runtime checks, Review, and QA
- Do not call the true separate milestone closed until a real 2-round live loop completes with:
  - commander review present
  - a spun worker active in round 2
  - a successful final summary after round 1 and round 2

### Roadmap Track

1. Deployment portability and packaging
   - Highest-priority product milestone after the alignment blocker
   - Break the hard legacy Windows web-server lock-in
   - Add a supported local dev/runtime path for Linux and macOS
   - Add a containerized path so setup is not tied to a manually tended local web-server stack
   - Keep the current Windows path working during the transition instead of forcing a rewrite-first migration

2. Secret storage and secure retrieval
   - Move beyond plaintext local `Auth.txt` as the only secret store
   - Add secure local key storage plus controlled retrieval into the runtime
   - Preserve the key-pool UX, but back it with safer storage, masking, rotation metadata, and clearer secret-handling policy
   - Treat this as a real security milestone, not just frontend cleanup

3. Prototype hardening
   - The repo is still prototype-grade despite the feature surface
   - Add better error handling, stronger typing discipline, unit tests, and security hardening
   - Expand QA from reversible smoke into repeatable component coverage for dispatch, round alignment, tool loops, and recovery semantics
   - Use the new true-separate path as a forcing function for this cleanup

4. Multi-provider model abstraction
   - Remove the OpenAI-only runtime assumption
   - Add a provider layer that can support Grok, Claude, Gemini, and local runtimes through Ollama or LiteLLM
   - Make mixed-model experiments first-class so we can test same-model lanes against mixed-model lanes honestly
   - Local inference support matters here because there is already waiting local GPU capacity and that changes the economics of adversarial fan-out

5. Review-surface and frontend architecture
   - The frontend is still too monolithic and the review surface deserves better visualization
   - Break the current app surface into more maintainable frontend modules
   - Improve review visualization for:
     - round-by-round lead direction changes
     - commander-review vs final-summary comparison
     - dynamic lane spawn reason and activation round
     - tool usage, evidence, and cost overlays
   - Treat this as both UX work and code-organization work

6. Cost governance without betraying the thesis
   - Token burn remains inherent to the architecture and should stay treated as a known product tradeoff, not a bug
   - The milestone is not “make it cheap at any cost”
   - The milestone is:
     - keep burn visible
     - keep budgets enforceable
     - keep evals honest about whether the extra pressure earns its spend
     - add fast-lane or guardrail options only around the primary reasoning path, not by starving workers of shared user context

## Next Milestones

- The true separate path is now considered functionally closed for the local prototype.
- On April 21, 2026, the system completed 5 clean live 2-round runs without hanging, with:
  - `commander -> workers -> commander_review -> summarizer`
  - a next-round spawned worker activating correctly in round 2
  - a successful final summary after both rounds
  - a passing async dispatch smoke after the same round-alignment fixes
- That means the next phase is no longer "make the local POC basically work."
- The next phase is "turn the local POC into something that can grow into an online, enterprise-capable offering."

### Milestone 1: Dynamic Lane Polish

- Goal:
  - Make dynamic adversarial spin-up deliberate, legible, and reliably useful instead of merely possible
- Scope:
  - improve how commander review chooses a missing lane type
  - tighten how a spawned worker is named, focused, temperature-set, and instructed
  - prevent near-duplicate personas from being spawned under different labels
  - show the spawn reason, required pressure, and activation round clearly in Review
- Acceptance criteria:
  - a spawned lane carries a specific unresolved pressure, not a generic template instruction
  - duplicate or low-value lane suggestions are rejected cleanly
  - eval coverage exists for fixed lanes vs dynamic spin-up on the same prompts
  - Review makes the spawn reason and effect on the final answer obvious

### Milestone 2: Deployment Portability and Online Packaging

- Goal:
  - Break the hard legacy Windows web-server lock-in and define the first deployment shape that could credibly become an online offering
- Scope:
  - add a supported Linux/macOS local path
  - add a containerized path for single-node deployment
  - separate "dev convenience" from "runtime requirement" so the old local web-server stack is no longer the product boundary
  - define the first online topology for control plane, runtime service, queueing, state, and artifacts
- Acceptance criteria:
  - a fresh environment can boot the app without legacy local-server handholding
  - Docker-based local bring-up works for the main app path
  - runtime state, jobs, and artifacts have a documented service boundary
  - the repo contains a documented path from local single-node deployment to hosted deployment

#### Current progress

- The repo now includes a first Python-only Docker bring-up under `deploy/compose.yml`
- The active container image is:
  - `backend` (Python ASGI shell + control plane)
- The packaging QA path now includes `scripts/qa_container_check.py`
- The Python crossover QA path now includes `scripts/qa_python_crossover_check.py`
- The shell now runs directly from the Python backend at `http://127.0.0.1:8787/`
- The portable local launcher now lives at `scripts/run_local_stack.py`
- The deploy env contract now lives in `.env.example`
- The portability validation path now includes `scripts/qa_portability_check.py`
- The Python control plane now exposes `GET /v1/system/topology`
- The Python control plane now exposes `GET /v1/system/infrastructure`
- The deployment boundary is now explicit in code for:
  - queue backend
  - metadata backend
  - artifact backend
  - secret backend
  - runtime execution backend
- The repo now includes a real hosted-dev proof harness in `scripts/qa_hosted_dev_stack.py`:
  - it is supposed to fail hard when Docker is missing
  - once Docker exists, it boots the hosted-dev compose stack and proves Redis, Postgres, object storage, mounted secrets, and background loops through live checks
- The runtime execution backend is now selectable between:
  - `embedded_engine_subprocess`
  - `runtime_service`
- The queue backend is no longer just declarative:
  - `redis` now owns background loop ordering and ready target-dispatch launch handoff through a Python queue adapter
  - the local profile still keeps queue metadata on JSON files, while hosted-style metadata can now move to Postgres
- The metadata backend is no longer just a probe target:
  - `postgres` now owns shared control-plane state, job metadata, task snapshots, and eval run state across both the backend and runtime engine
  - filesystem-backed JSON remains for events, steps, and eval suite/arm manifests during this phase
- The artifact backend is no longer just a probe target:
  - `object_storage` now owns runtime checkpoints, saved output artifacts, session archives, and export bundles, and Review/history reads the runtime artifacts back through the same adapter
  - eval suite/arm manifests remain filesystem-backed in this phase
- The secret backend is no longer only transitional local-file handling:
  - `LOOP_SECRET_BACKEND=env` now works through the runtime as well as the control plane via `LOOP_OPENAI_API_KEYS`, and the local profile now defaults to it
  - `LOOP_SECRET_BACKEND=docker_secret` now supports mounted newline-delimited key files such as `/run/secrets/openai_api_keys`
  - `LOOP_SECRET_BACKEND=external` now works as a real read-only HTTP provider path through both the backend and runtime when `LOOP_SECRET_PROVIDER_URL` is configured
  - local `Auth.txt` remains only the transitional writable path for local-first testing
- A hosted-dev dependency shape now exists in `deploy/compose.hosted-dev.yml` with:
  - `postgres`
  - `redis`
  - `minio`
- A dedicated runtime-service deployment override now exists in `deploy/compose.hosted-dev.runtime-service.yml`:
  - backend delegates target execution over HTTP to a separate `runtime` container
  - the runtime image now installs the full Python dependency set instead of assuming a pre-warmed environment
- A portable handoff bundle can now be produced with `python scripts/package_hosted_bundle.py`:
  - it stages the Docker files, env contract, shell assets, runtime/backend code, and QA scripts under `build/hosted-bundle/`
- That means the legacy local web-server stack is no longer required for local use or controlled end-to-end testing
- Remaining work for this milestone is no longer "invent Docker support"; it is:
  - prove the stack on a real Docker host
  - keep reducing compatibility-only legacy surfaces like the standalone runtime service
  - replace the current explicit boundary metadata with real hosted backends behind it

#### Architecture Breakout

- Transitional local path
  - Python-only local launcher via `scripts/run_local_stack.py`
  - Goal: one cross-platform bring-up path for Windows, Linux, and macOS without the legacy local stack
- Portable single-node path
  - Static frontend served by the Python app itself
  - Python ASGI control plane for task creation, polling, history, auth status, eval launch, and job control
  - Python runtime library invoked by backend-managed background jobs
  - Optional compatibility runtime service only where older smoke/test paths still need it
  - Redis-backed queue for loop jobs / target jobs
  - Postgres for canonical task/job metadata
  - Object storage or local disk abstraction for artifacts, checkpoints, and eval outputs
- Hosted enterprise path
  - CDN/static shell for frontend
  - Python control-plane API behind a gateway
  - background worker pool for commander, worker, commander-review, summarizer, and eval jobs
  - durable relational state store plus object storage for artifacts
  - managed secret store for provider keys and customer credentials
  - audit/telemetry pipeline for usage, job events, tool calls, and review actions

#### Python-First Architecture Snapshot

- Current filesystem responsibilities
  - `index.html` plus `assets/`
    - the current static shell, frontend state management, and review UI
  - `backend/`
    - the active HTTP control plane, shell serving, job orchestration, settings/auth mutation, eval launch, replay/export, and state mutation
  - `runtime/`
    - the reasoning engine, runtime service, and eval runner
  - `scripts/`
    - QA harnesses, portability helpers, bundle packaging, and local bring-up tools
  - `data/`
    - canonical state, artifacts, jobs, eval runs, and volatile local runtime outputs
- Structural observation
  - the repo is now cleanly split into `frontend`, `control plane`, and `runtime`
  - the main remaining architecture work is replacing transitional local-file seams with hosted-grade queue, metadata, artifact, and secret backends

#### Target Layout

- `frontend/`
  - static app shell
  - built assets
  - review/operator UI
- `backend/api/`
  - Python ASGI app
  - routers for tasks, loops, jobs, auth/integrations, history, eval, and admin/review operations
- `backend/core/`
  - shared domain logic
  - task normalization
  - worker roster logic
  - budget/profile logic
  - auth-slot assignment
  - job-state transitions
- `backend/runtime/`
  - reasoning engine and provider adapters
  - commander / worker / commander-review / summarizer execution
- `backend/workers/`
  - background worker entrypoints for loop jobs, dispatch jobs, eval jobs
- `backend/storage/`
  - relational models and object-store abstraction
- `backend/tests/`
  - component, integration, and fault-injection coverage
- `deploy/`
  - Dockerfiles
  - compose for single-node self-host
  - hosted deployment manifests

#### Current Cutover Status

- The Python-first scaffold now lives under `backend/`
  - `backend/app/main.py`
    - FastAPI app exposing the active read, write, job, and settings surfaces
  - `backend/app/storage.py`
    - storage layer for local JSON, hosted seams, and eval artifacts
  - `backend/app/control.py`
    - draft normalization, task creation, auth-pool status, and state/task/event writes using the same lock discipline as the resident runtime
  - `backend/app/jobs.py`
    - background loop creation, cancellation, retry/resume, queue bookkeeping, and the Python-native loop runner launch path
  - `backend/app/dispatch.py`
    - commander/worker/commander-review/summarizer background dispatch, round batching, and sync target execution
  - `backend/workers/loop_job.py`
    - background worker entrypoint for autonomous loop jobs
  - `backend/workers/dispatch_job.py`
    - background worker entrypoint for target dispatch jobs
  - `backend/tests/test_storage.py`
    - regression guard for the read-model behavior
  - `backend/tests/test_control.py`
    - regression guard for the write-path behavior
  - `backend/tests/test_app.py`
    - route-registration smoke for the ASGI surface
  - `backend/tests/test_dispatch.py`
    - regression coverage for round batching, partial answer queueing, and sync target execution
  - `backend/tests/test_settings.py`
    - regression coverage for auth key mutation, runtime apply, worker draft edits, roster growth, and per-position model changes
  - `backend/tests/test_sessions.py`
    - regression coverage for session reset, state reset, session replay, and export bundle generation
  - `backend/tests/test_evals.py`
    - regression coverage for eval-run queueing and manifest validation
- The Python control plane now owns the active route surface
  - `POST /v1/auth/keys`
  - `POST /v1/session/reset`
  - `POST /v1/state/reset`
  - `POST /v1/session/replay`
  - `GET /v1/session/export`
  - `POST /v1/runtime/apply`
  - `POST /v1/workers/update`
  - `POST /v1/workers/add`
  - `POST /v1/positions/model`
  - `POST /v1/evals/runs`
  - `POST /v1/loops`
  - `POST /v1/loops/cancel`
  - `POST /v1/jobs/manage`
  - `POST /v1/targets/background`
  - `POST /v1/rounds`
  - `POST /v1/targets/run`
- The frontend now calls `/v1/*` routes directly in `assets/app.js`
- The Python backend serves the shell directly at `GET /` and `GET /index.html`
- `scripts/qa_python_crossover_check.py` proves that path with reversible state preservation
- CI/dependency baseline is explicit instead of machine-local
  - `.python-version` pins the Python family
  - `.nvmrc` pins the Node family used for syntax checks
  - `requirements-ci.txt` pins the deployment Python graph
  - `requirements-dev.txt` adds CI/developer audit tooling on top of the pinned runtime graph
  - `.github/workflows/ci.yml` runs the repo QA on Linux with Python and Node installed deliberately
  - `.github/dependabot.yml` keeps GitHub Actions and pip dependencies under automated update review
  - `scripts/qa_supply_chain_check.py` enforces local browser assets, SHA-pinned workflows, pinned Python manifests, and a clean `pip-audit` result
  - `SECURITY.md` records the current reporting and dependency-hardening posture for the repo

#### Improvements Unlocked By The Cutover

- Unify orchestration rules in one language
  - worker activation rounds
  - job recovery
  - target dependency handling
  - budget enforcement
  - key-slot rotation
- Replace file-polling request patterns with better primitives
  - SSE or WebSockets for live run status
  - direct queue/job introspection
  - cleaner partial-answer progress reporting
- Replace local JSON as the primary source of truth over time
  - Postgres for tasks, drafts, jobs, and metadata
  - object storage for artifacts and eval outputs
  - Redis for queueing / ephemeral coordination
- Reduce frontend duplication
  - move shared config catalogs out of `assets/app.js` into backend-served config endpoints
- Improve testability
  - one control-plane test harness instead of split legacy endpoint smoke plus runtime smoke

#### Ongoing Migration Plan

- Phase 1
  - keep the existing frontend
  - keep strengthening the Python API and hosted seams
- Phase 2
  - move more shared normalization and business logic into `backend/core`
  - keep shrinking transitional local-file dependencies
- Phase 3
  - replace remaining local metadata/artifact/secrets seams with hosted-grade backends
- Phase 4
  - move from single-node self-host to repeatable hosted deployment profiles

### Milestone 3: Secrets, Security, and Controlled Retrieval

- Goal:
  - Replace prototype-local secret handling with a real secret-storage and retrieval story suitable for a hosted system
- Scope:
  - move beyond plaintext local `Auth.txt` as the long-term secret store
  - support safer local storage for development
  - define managed-secret retrieval for hosted/runtime use
  - harden tool boundaries, audit logs, and secret-handling policy
- Acceptance criteria:
  - local development no longer depends on plaintext-only secret handling as the preferred path
  - hosted/runtime secret retrieval is documented and implemented behind a clean interface
  - secrets never appear in artifacts, steps, or browser-visible debug surfaces
  - secret rotation, masking, and retrieval failure behavior are explicit and test-covered

#### Current progress

- Secret-shaped local and GitHub files are now filtered out of retrieval listings and blocked from direct reads/searches by default.
- Hosted/runtime secret backends already exist for `env`, `docker_secret`, and `external`, and the default backend selection is now profile-aware:
  - local profile defaults to `env`
  - hosted profiles default to `docker_secret`
  - `local_file` remains explicit fallback only
- Live model calls now rotate to the next non-empty key on auth-style failures instead of binding one lane to one dead key for the rest of the run.
- Managed secret backends now fail loudly when empty or unreachable, so live execution no longer drifts into file/env fallthrough or quiet mock fallback when the selected backend is degraded.

### Milestone 4: Prototype Hardening

- Goal:
  - Make the system boringly reliable instead of merely clever and feature-rich
- Scope:
  - add better error handling, typing discipline, and component tests
  - expand QA from reversible smoke into repeatable coverage for dispatch, round alignment, tool loops, and recovery semantics
  - harden state transitions and failure messaging across backend and runtime services
- Acceptance criteria:
  - core runtime paths have repeatable automated tests beyond smoke level
  - failure modes become explicit, logged, and user-legible
  - cross-process recovery semantics are verified under fault injection
  - the main runtime no longer depends on "read the logs and guess" during common failure cases

#### Current progress

- Dispatch and loop execution now expose explicit failpoints for repeatable hardening tests.
- Recovery coverage now verifies stale dispatch recovery, stale loop recovery, and dependency-failure interruption instead of relying only on smoke tests.
- State, artifact, session, and history reads now coerce malformed payloads into explicit `contractWarnings` instead of leaking broken shapes into the shell.
- Review and history surfaces now show execution-health state, degraded/recovered/fallback badges, and telemetry/data-contract warnings directly in the operator view.
- Session reset, replay, and export paths now have explicit fault injection and warning-preserving bundle assembly.
- Dispatch/runtime failures now land in explicit operator-facing classes such as `Provider`, `Output cap`, `Dependency`, and `Partial-risk` instead of one generic error bucket.
- Step/event telemetry parsing now drops malformed JSONL safely, preserves degradation across later clean lines, and surfaces telemetry quality problems visibly instead of silently skewing execution health.

#### Milestone status

- Milestone 4 is now considered complete for the current roadmap bar.
- The next active engineering milestone is `Milestone 5: Multi-Provider Model Abstraction`.

### Milestone 5: Multi-Provider Model Abstraction

- Goal:
  - Remove the OpenAI-only runtime assumption and make provider choice a real product capability
- Current status:
  - initial slice landed
  - runtime/provider dispatch now supports `openai` plus a first native `ollama` path
  - workers inherit the task runtime provider while the summarizer/lead-thread provider can be set separately
  - Ollama is intentionally limited to structured local generation for now and does not yet support the runtime's research/tool loop
- Scope:
  - add a provider layer that can support OpenAI, Grok, Claude, Gemini, and local runtimes through Ollama or LiteLLM
  - make mixed-model experiments first-class
  - support local inference because available GPU capacity changes the economics of adversarial fan-out
- Acceptance criteria:
  - at least one non-OpenAI provider path runs through the same orchestration model
  - local/Ollama or LiteLLM support exists for controlled experiments
  - provider-specific failures surface cleanly without corrupting task state
  - evals can compare same-model vs mixed-model lane stacks honestly

### Milestone 6: Review Surface and Frontend Architecture

- Goal:
  - Make the review surface worthy of the runtime and make the frontend maintainable enough for a real product
- Scope:
  - break the monolithic frontend into saner modules
  - improve review visualization for:
    - round-by-round lead-direction changes
    - commander-review vs final-summary comparison
    - dynamic lane spawn reason and activation round
    - tool usage, evidence, and cost overlays
  - start shaping the UI for a hosted/operator audience, not only a local tinkering surface
- Acceptance criteria:
  - the review surface explains why the final answer changed across rounds
  - dynamic spin-up, tool use, and control audit are visually inspectable without reading raw JSON
  - the frontend codebase is split enough that new product work does not require editing one giant file
  - the shell can support both end-user and operator/review workflows cleanly

### Milestone 7: Cost Governance Without Betraying the Thesis

- Goal:
  - Keep burn visible and governable without weakening the full-context adversarial architecture
- Scope:
  - keep all lanes fully informed on the primary path
  - improve spend observability, guardrails, and benchmark honesty
  - add fast-lane options only around the primary reasoning path, not by starving workers of shared user context
- Acceptance criteria:
  - per-lane and per-role burn is visible in the product surface and saved artifacts
  - guardrails can stop runaway jobs without silently degrading answer quality
  - evals make it obvious when extra disagreement earns its spend and when it does not
  - the product can explain high-burn modes honestly instead of pretending they are cheap

## Notes

- `Auth.txt` now acts only as a local fallback API key pool for testing, with one key per line. It must not be copied into logs, responses, or version control.
- Before committing, the repo should ignore secrets and volatile runtime data.
