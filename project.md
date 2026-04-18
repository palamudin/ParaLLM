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

- Local-first on Windows with XAMPP, PHP, PowerShell, HTML, CSS, and JavaScript
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
- `ps/*.ps1`: worker and summarizer processes
- `data/state.json`: canonical state
- `data/events.jsonl`: low-level event log
- `data/steps.jsonl`: structured step log for human-readable process trace
- `data/tasks/*.json`: task snapshots
- `data/checkpoints/*.json`: worker and summary checkpoints

## Runtime Options

- Execution mode: `live` or `mock`
- Default low-cost recommendation: `gpt-5-mini`
- Reasoning effort can be tuned per task
- Secrets stay in `Auth.txt` locally and should never be logged

## Sync Model

- Independence by default
- Sharing only at checkpoints, blocker conditions, or scheduled round boundaries
- Shared content should be summarized, structured, and tagged by source
- Workers can leave peer steer requests for the other lane
- Summaries must preserve stable findings, conflicts, conditional truths, and recommended next actions

## Immediate Milestones

1. Create persistent project memory and logging
2. Add round execution with visible worker-to-worker steer packets
3. Add model-backed workers using the local API key without leaking it into logs
4. Add file locking / queue discipline for safer concurrency
5. Add packaging and repeatable test flow

## Notes

- `Auth.txt` currently contains the API key for local testing. It must not be copied into logs, responses, or version control.
- Before committing, the repo should ignore secrets and volatile runtime data.
