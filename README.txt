AI Loop Prototype for XAMPP / Windows
=====================================

What this is
------------
A local prototype scaffold for:
- Commander input
- Worker A (utility / benefit pressure)
- Worker B (risk / adversarial pressure)
- Summarizer / canonical memory
- JSON persistence and event logging
- Autonomous multi-round execution
- Cross-process locking between PHP and PowerShell

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
2. Choose `Mock` or `Live API`, model, and reasoning effort.
3. Click Start Task.
4. Either click `Run Round` for one cycle or `Run Auto Loop` for repeated cycles.
5. Use `Cancel Loop` to stop after the current round.
6. Watch worker panels, summary, event log, and step log update.

Main files
----------
- index.html               UI
- assets/app.js            frontend logic
- api/*.php                broker endpoints
- ps/*.ps1                 worker/summarizer scripts
- data/state.json          canonical state
- data/events.jsonl        append-only event log

Current behavior
----------------
Workers support two modes:
- `mock`: local scaffolded reasoning output
- `live`: real model calls through the OpenAI Responses API

The loop preserves contradictions, step logs, and per-round checkpoint files.
The backend also uses a shared lock so PHP and PowerShell do not trample the same state file.

Next sensible step
------------------
Move autonomous looping off the request thread and into a queue / background runner so longer sessions survive page refreshes and can scale past a single blocking HTTP request.
