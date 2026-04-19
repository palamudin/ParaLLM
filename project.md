# AI Loop POC

## Purpose

Build a local prototype for a two-process reasoning loop that keeps independent viewpoints, shares only structured checkpoints, preserves contradictions, and maintains an audit trail of every meaningful step.

## Core Idea

This is not "two minds." It is two separate process lanes with distinct roles:

- Worker A: utility / benefits / progress pressure
- Worker B: risk / adversarial / failure pressure
- Summarizer: canonical shared memory that merges checkpoints without erasing disagreement

The design goal is sparse, structured sharing. The workers should not stream every token to each other. They should expose a steer packet at controlled intervals so each lane can react to the other without collapsing into a single blended process.

## Prototype Constraints

- Local-first on Windows with XAMPP, PHP, HTML, CSS, JavaScript, and now a resident Python runtime
- No Node requirement for the first prototype
- Persistence kept in local JSON / JSONL files
- Every important step should be logged
- Contradictions should remain visible
- Assumptions must not be silently upgraded into facts

## Current Architecture

- `index.html`: local control panel and live state display
- `assets/app.js`: frontend polling and command dispatch
- `assets/app.css`: local styling
- `api/*.php`: PHP broker endpoints
- `runtime/*.py`: resident worker / summarizer runtime service
- `ps/*.ps1`: fallback worker and summarizer scripts retained as a safety net during migration
- `data/state.json`: canonical state
- `data/events.jsonl`: low-level event log
- `data/steps.jsonl`: structured step log for human-readable process trace
- `data/tasks/*.json`: task snapshots
- `data/checkpoints/*.json`: worker and summary checkpoints
- `data/outputs/*.json`: dedicated worker and summarizer output artifacts with response metadata for quality review
- `data/sessions/*.json`: archived session snapshots captured by Reset Session with carry-forward context
- `data/jobs/*.json`: background loop job metadata and result summaries
- `data/locks/loop.lock`: cross-process lock directory used by PHP, Python, and PowerShell fallback paths

## Runtime Options

- Execution mode: `live` or `mock`
- Default low-cost recommendation: `gpt-5-mini`
- Per-position model selection for each worker lane and the summarizer
- Reasoning effort can be tuned per task
- Optional grounded worker research with `web_search`, live-web toggle, and domain allow-lists
- Summarizer evidence-vetting mode that scores worker claims without doing its own web research
- Session budget guardrails for total tokens, estimated spend, per-call output tokens, and web-search tool calls
- API key can be managed locally through the UI and is only displayed as a masked last-4 preview
- Form draft state is persisted locally so edits do not get stomped by polling refreshes
- Secrets stay in `Auth.txt` locally and should never be logged

## Sync Model

- Independence by default
- Sharing only at checkpoints, blocker conditions, or scheduled round boundaries
- Shared content should be summarized, structured, and tagged by source
- Workers can leave peer steer requests for the other lane
- Summaries must preserve stable findings, conflicts, conditional truths, and recommended next actions

## Current POC Features

- Dynamic worker roster starting with `A` and `B`, with bounded adversarial expansion through additional lettered lanes
- Commander form now includes a `Session Context` field for short carry-forward memory between sessions
- Manual single-target execution for any configured worker lane and the summarizer
- Manual single-round execution
- Autonomous multi-round execution with configurable round count and delay
- Cancellation that stops after the current round completes
- Detached background loop launching through `scripts/loop_runner.php`
- Shared-state locking between PHP and the resident Python runtime, with PowerShell fallback still available
- Resident Python runtime service on `127.0.0.1:8765` keeps worker/summarizer logic warm between calls instead of spawning a new shell process every step
- PHP dispatch now prefers the Python runtime and only falls back to PowerShell if the service is unavailable
- Stale queued/running job recovery based on queue age and heartbeat age
- Per-position model selection in the UI for workers and summarizer
- Grounded worker research mode using the OpenAI Responses API `web_search` tool with optional OpenAI-domain allow-lists
- Worker checkpoints now carry evidence ledgers, research queries, consulted source URLs, and evidence gaps
- Summarizer now acts as a vetter, preserving conflicts while scoring supported, mixed, weak, or disputed claims
- Each worker and summarizer run now saves a dedicated output artifact so quality can be inspected separately from canonical state
- Artifact Review UI supports side-by-side inspection of saved checkpoints and output artifacts
- URL/source normalization now drops malformed non-URL entries and canonicalizes saved source links in fresh artifacts
- Sidebar workspace shell now splits `Home`, `Settings`, `Debug`, and `Review`, with a chat-first center pane and the API key moved into Settings / Integrations
- Fine tuning controls now live in Settings instead of crowding the main conversation surface
- Session usage accounting with token, web-search-call, and estimated-spend tracking in state, jobs, and the top-bar counters
- Budget stop behavior that marks work as `budget_exhausted` instead of running past configured limits
- Masked API key management in the top bar for local test-key swapping
- Reset Session archives the current state to `data/sessions`, clears the active task, and reloads a fresh draft with short carry-forward context
- Per-round checkpoint snapshots such as `*_A_step002.json` and `*_summary_round002.json`
- UI history panels for recent jobs and checkpoint artifacts
- Optional live model execution with mock fallback still available
- Verified live smoke run with grounded worker search and summarizer vetting against OpenAI-owned sources on April 18, 2026
- Verified widened live `A/B/C` run with grounded worker research, live summarizer vetting, and saved output artifacts on April 19, 2026
- Verified resident Python runtime dispatch on April 19, 2026 with mock `A/B/summarizer` execution through the existing PHP endpoints
- Verified resident Python runtime live path on April 19, 2026; model calls reached the Python runtime correctly and preserved the existing fallback-to-mock behavior when Responses API output was truncated by `max_output_tokens`

## Immediate Milestones

1. Add resume/retry tooling for interrupted background runs instead of only recovery-to-error
2. Add explicit exception policy for when raw artifacts are allowed vs. structured checkpoints only
3. Add side-by-side round history review in the UI with richer drill-down than filename lists
4. Add export and replay tooling for audited sessions
5. Add bounded multi-job queueing instead of a single active background job slot
6. Add richer lane templates so new adversarial workers can be spawned from selectable viewpoints instead of only the next default letter slot
7. Reconcile conflicting OpenAI-owned pricing statements for web-search content tokens before treating cost estimates as billing-accurate
8. Tighten live prompt/output handling so the resident Python runtime hits structured-output success more often before needing mock fallback on `max_output_tokens`

## Notes

- `Auth.txt` currently contains the API key for local testing. It must not be copied into logs, responses, or version control.
- Before committing, the repo should ignore secrets and volatile runtime data.
