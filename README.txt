AI Loop Prototype for XAMPP / Windows
=====================================

What this is
------------
A local prototype scaffold for:
- Chat-first commander input where `Send` creates a task and kicks off the configured loop automatically
- Dynamic worker lanes that start with Proponent / Sceptic and can expand with more adversarial viewpoints
- Summarizer / canonical memory
- JSON persistence and event logging
- Autonomous multi-round execution
- Cross-process locking between PHP, Python, and PowerShell fallback paths
- Detached background loop execution through PHP
- Stale-job recovery for interrupted background runs
- Recent job and artifact history in the UI
- Per-position model selection
- Per-worker directive and temperature controls
- Session token / spend tracking with budget limits
- Optional grounded worker research with web-search controls
- Summarizer evidence vetting over worker research
- Masked API key management through the UI
- Persistent commander draft state plus session reset / carry-forward archive support
- Resident Python runtime service so worker/summarizer logic stays warm between dispatches

Folder target
-------------
Copy the whole ai-loop-xampp folder into:
C:\xampp\htdocs\

Then browse to:
http://localhost/ai-loop-xampp/

Requirements
------------
- XAMPP / Apache / PHP enabled
- Python 3 available locally
- Windows PowerShell available for fallback and service launching on Windows
- PHP shell_exec enabled
- PowerShell execution allowed for local scripts on Windows

If shell_exec is disabled in php.ini
------------------------------------
Check php.ini for disable_functions.
If shell_exec is listed there, remove it and restart Apache.

Execution policy note
---------------------
PHP runs PowerShell using:
-ExecutionPolicy Bypass

This is prototype scaffolding, not hardened production design.

Main flow
---------
1. Open Home and type the prompt you want the lanes to investigate.
2. Optionally tweak Settings first:
   API key lives in `Settings / Integrations`.
   Fine tuning, budgets, loop rounds, and research policy live in `Settings / Fine Tuning`.
3. Review the worker rail on Home:
   it starts with `Proponent` and `Sceptic`
   use `+ Add` to grow the adversarial roster
   use the per-worker controls to choose directive, temperature, and model
4. Press `Send`.
5. The app creates a task from the staged roster and automatically queues the configured loop.
6. Read the final Agent reply in Home. Lane inspection is collapsed by default and can be expanded above the answer if you want to review the worker internals.
7. Use `Debug` for manual controls such as `Run Round`, `Run Auto Loop`, `Summarize`, `Refresh`, `Reset Session`, `Cancel Loop`, or `Reset State`, and for reviewing/editing carry-forward `Session Context`.
8. Use `Review` for memory, jobs, artifacts, and side-by-side output inspection.

Main files
----------
- index.html               UI
- assets/app.js            frontend logic
- api/*.php                broker endpoints
- scripts/loop_runner.php  background loop runner
- runtime/*.py             resident Python runtime service and engine
- ps/*.ps1                 worker/summarizer fallback scripts
- data/state.json          canonical state
- data/sessions/*.json    archived session resets with carry-forward summaries
- data/events.jsonl        append-only event log
- data/outputs/*.json      dedicated saved worker/summarizer outputs for inspection
- data/jobs/*.json         background job metadata

Current behavior
----------------
Workers support two modes:
- `mock`: local scaffolded reasoning output
- `live`: real model calls through the OpenAI Responses API

PHP now dispatches worker and summarizer targets through a resident Python service on `127.0.0.1:8765`.
That service keeps the runtime warm between calls and writes the same state, checkpoint, output, and step-log artifacts as before.
If the Python service is unavailable, PHP still falls back to the older PowerShell path so the app stays usable during migration.
For live structured outputs, the Python runtime now treats very low `maxOutputTokens` values as a requested cap, not a trap:
- workers start with a safe floor of `900`
- summarizer starts with a safe floor of `1400`
- one retry is allowed at a higher cap if the Responses API returns `incomplete: max_output_tokens`
- requested and effective caps are both logged in `steps.jsonl` and saved output artifacts

When worker research is enabled, worker lanes can use the Responses API `web_search` tool, keep their own research queries and consulted source URLs, and leave evidence ledgers for the summarizer to vet.
When summarizer vetting is enabled, the summarizer scores the worker claims by support strength instead of only merging prose.
The loop preserves contradictions, step logs, and per-round checkpoint files.
Each worker and summarizer run also writes a dedicated output artifact so you can inspect returned content and response metadata without diffing canonical state.
The Artifact Review section can load those saved artifacts side by side and show both raw response text and normalized output.
Fresh artifacts now normalize and dedupe source URLs more aggressively so malformed non-URL strings do not pollute research-source lists.
The commander form is now draft-backed, so refresh polling no longer overwrites in-progress edits.
The stored draft now also carries the worker roster plus loop rounds and delay, so a page refresh does not wipe the staged lanes.
Home chat polling now preserves scroll position and lane-inspector expansion state instead of snapping back to the bottom on every refresh.
The Home thread is intentionally simplified: it shows the prompt and the summarizer's response in a more standard agent-chat style, while lane inspection stays collapsed unless explicitly opened.
`Reset Session` writes an archive file under `data/sessions`, clears the active task, and preloads a short carry-forward summary into the `Session Context` field for the next task.
The backend also uses a shared lock so PHP and PowerShell do not trample the same state file.
`Run Auto Loop` now returns quickly and a detached background runner continues the work while the UI polls state.
If a queued or running background job goes stale, polling endpoints will mark it as recovered, move it to `error`, and append a recovery entry to the step log.
History polling is read-mostly and stays available even if a recovery check has to be deferred briefly because the loop lock is busy.
The top bar shows the current masked API key, session tokens, web-search-call count, and estimated spend so you can control live testing costs without exposing the full secret in the browser.

Live verification note
----------------------
On April 18, 2026, the prototype was smoke-tested live with:
- grounded worker search restricted to OpenAI-owned domains
- summarizer evidence vetting enabled
- `gpt-5-mini` for workers and summarizer

On April 19, 2026, a widened live `A/B/C` run also completed successfully with:
- three live worker lanes plus a live summarizer
- grounded worker research and saved output artifacts in `data/outputs`
- a total estimated spend that stayed below the configured session cap

On April 19, 2026, the resident Python runtime was also verified with:
- a mock `A/B/summarizer` pass through the existing `api/run_ps.php` endpoint, returning `backend: python`
- a live `A/B/summarizer` pass through the Python runtime, which matched the prior behavior by falling back to mock when the Responses API returned `incomplete: max_output_tokens`
- a later live `A/B/summarizer` pass with `maxOutputTokens=500`, which still completed live because the runtime lifted the effective caps and retried where needed
- a final release-validation pass through the send-style task + background-loop flow, where both a mock smoke and a live smoke completed end to end with a saved summary artifact

That run confirmed:
- worker `web_search` usage is captured in usage totals and per-target buckets
- worker checkpoints persist research queries, source URLs, and evidence ledgers
- summarizer checkpoints persist evidence verdicts and preserved conflicts
- output-token recovery metadata is preserved in step logs and output artifacts
- the default chat path of `start_task` plus `start_loop` still works after the Home/Debug split and thread-renderer cleanup

One real residual caveat remains: OpenAI-owned pricing pages currently show conflicting statements about whether web-search content tokens are billed at model rates or free, so the prototype should still treat web-search spend as an estimate rather than invoice-accurate truth until that conflict is reconciled.

Next sensible step
------------------
Add resume/retry tooling for interrupted jobs, richer side-by-side round inspection, and tighten live prompt/output handling so the Python runtime lands more structured responses before fallback is needed.
