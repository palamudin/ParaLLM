# Hourly Specialization Checkpoint

Every hour, check:

1. Is Para running?
2. Is the latest specialization output newer than the previous checkpoint?
3. Did the Blender proof create or update `.blend`, `.json`, or render artifacts?
4. What is the current blocker?
5. What is the next useful test?

This reminder intentionally does not launch an LLM run automatically. It records state and gives the operator/Codex/Para a clean checkpoint prompt without unattended token burn.

