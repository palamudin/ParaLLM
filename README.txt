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
2. Click Start Task.
3. Click Run A.
4. Click Run B.
5. Click Summarize.
6. Watch panels and event log update.

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
Workers are mocked logic with structured outputs.
They do not call real model APIs yet.
That is intentional so the loop and state handling work first.

Next sensible step
------------------
Replace workerA.ps1 / workerB.ps1 internals with real API-driven reasoning calls while keeping the same checkpoint schema.
