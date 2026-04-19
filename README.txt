AI Loop Prototype for XAMPP / Windows
=====================================

What this is
------------
A local prototype scaffold for:
- Commander input
- Dynamic worker lanes that start with A/B and can expand with more adversarial viewpoints
- Summarizer / canonical memory
- JSON persistence and event logging
- Autonomous multi-round execution
- Cross-process locking between PHP, Python, and PowerShell fallback paths
- Detached background loop execution through PHP
- Stale-job recovery for interrupted background runs
- Recent job and artifact history in the UI
- Per-position model selection
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
1. Enter objective + constraints.
2. Optionally keep or edit the `Session Context` field if you are carrying forward a prior session.
3. Set or swap the API key in the top bar if you want to use `Live API`.
4. Choose `Mock` or `Live API`, the default worker model, summarizer model, and reasoning effort.
5. Choose whether workers may use grounded web search, whether the summarizer should vet evidence, and optionally set a domain allow-list.
6. Adjust the session budget if you want tighter spend control.
7. Click Start Task.
8. Either click `Run Round` for one cycle or `Run Auto Loop` to queue a detached background run.
9. Use `Add Adversarial` to grow the worker roster with another viewpoint lane.
10. Use `Reset Session` to archive the current run, clear the active task, and load a fresh draft with a short carry-forward context summary.
11. Use `Cancel Loop` to stop after the current round.
12. Watch worker panels, summary, event log, step log, spend counters, web-search-call count, and loop status update while the background job progresses.
13. Use the Recent Jobs and Recent Artifacts panels to review prior runs and per-round checkpoints.
14. Use Artifact Review to load any saved checkpoint or output artifact into side-by-side panes for quality comparison.

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

That run confirmed:
- worker `web_search` usage is captured in usage totals and per-target buckets
- worker checkpoints persist research queries, source URLs, and evidence ledgers
- summarizer checkpoints persist evidence verdicts and preserved conflicts
- output-token recovery metadata is preserved in step logs and output artifacts

One real residual caveat remains: OpenAI-owned pricing pages currently show conflicting statements about whether web-search content tokens are billed at model rates or free, so the prototype should still treat web-search spend as an estimate rather than invoice-accurate truth until that conflict is reconciled.

Next sensible step
------------------
Add resume/retry tooling for interrupted jobs, richer side-by-side round inspection, and tighten live prompt/output handling so the Python runtime lands more structured responses before fallback is needed.
