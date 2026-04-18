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
- Cross-process locking between PHP and PowerShell
- Detached background loop execution through PHP + PowerShell
- Stale-job recovery for interrupted background runs
- Recent job and artifact history in the UI
- Per-position model selection
- Session token / spend tracking with budget limits
- Masked API key management through the UI

Folder target
-------------
Copy the whole ai-loop-xampp folder into:
C:\xampp\htdocs\

Then browse to:
http://localhost/ai-loop-xampp/

Requirements
------------
- XAMPP / Apache / PHP enabled
- Windows PowerShell available
- PHP shell_exec enabled
- PowerShell execution allowed for local scripts

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
2. Set or swap the API key in the top bar if you want to use `Live API`.
3. Choose `Mock` or `Live API`, the default worker model, summarizer model, and reasoning effort.
4. Adjust the session budget if you want tighter spend control.
5. Click Start Task.
6. Either click `Run Round` for one cycle or `Run Auto Loop` to queue a detached background run.
7. Use `Add Adversarial` to grow the worker roster with another viewpoint lane.
8. Use `Cancel Loop` to stop after the current round.
9. Watch worker panels, summary, event log, step log, spend counters, and loop status update while the background job progresses.
10. Use the Recent Jobs and Recent Artifacts panels to review prior runs and per-round checkpoints.

Main files
----------
- index.html               UI
- assets/app.js            frontend logic
- api/*.php                broker endpoints
- scripts/loop_runner.php  background loop runner
- ps/*.ps1                 worker/summarizer scripts
- data/state.json          canonical state
- data/events.jsonl        append-only event log
- data/jobs/*.json         background job metadata

Current behavior
----------------
Workers support two modes:
- `mock`: local scaffolded reasoning output
- `live`: real model calls through the OpenAI Responses API

The loop preserves contradictions, step logs, and per-round checkpoint files.
The backend also uses a shared lock so PHP and PowerShell do not trample the same state file.
`Run Auto Loop` now returns quickly and a detached background runner continues the work while the UI polls state.
If a queued or running background job goes stale, polling endpoints will mark it as recovered, move it to `error`, and append a recovery entry to the step log.
History polling is read-mostly and stays available even if a recovery check has to be deferred briefly because the loop lock is busy.
The top bar shows the current masked API key, session tokens, and estimated spend so you can control live testing costs without exposing the full secret in the browser.

Next sensible step
------------------
Add resume/retry tooling for interrupted jobs, richer side-by-side round inspection, and eventually a bounded multi-job queue instead of a single active background slot.
