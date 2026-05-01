# Response Shapes

This folder preserves one real raw response shape per provider so output extraction can target stable vendor-specific envelopes without debugging live plumbing every time.

These files are intentionally raw:
- no normalization
- no flattening
- no field pruning
- no post-processing

Current samples:
- `openai_response.json`
  - source: `data/evals/runs/judge-20260428-022847+0000-7ef940/cases/rmm-midnight-malware-push-critical-structured/direct-openai-mini-open/replicate-001/direct_answer_output.json`
- `xai_response.json`
  - source: `data/evals/runs/judge-20260428-033021+0000-257883/cases/rmm-midnight-malware-push-critical-structured/direct-xai-fast-open/replicate-001/direct_answer_output.json`
- `anthropic_response.md`
  - source: `data/evals/runs/judge-20260428-023652+0000-1537d8/cases/rmm-midnight-malware-push-critical-structured/direct-anthropic-sonnet-open/replicate-001/direct_answer_output.json`
  - kept as markdown because the raw provider output arrived as fenced JSON text
- `minimax_response.json`
  - source: `data/evals/runs/judge-20260428-024543+0000-67b398/cases/rmm-midnight-malware-push-critical-structured/direct-minimax-highspeed-open/replicate-001/direct_answer_output.json`
- `ollama_response.json`
  - source: `data/old_logs/20260427-191831Z/outputs/t-20260421-220814-bdc52f_commander_output.json`

Use these as the local truth set when shaping provider-specific field extraction for Para output.
