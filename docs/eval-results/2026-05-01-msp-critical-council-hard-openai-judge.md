# 2026-05-01 MSP Critical Council Hard Sweep

This run exercised the hard MSP council suite across direct and ParaLLM arms for OpenAI, Anthropic, xAI, DeepSeek, and MiniMax families.

Artifacts live locally under `data/evals/runs/`. That directory is intentionally ignored, so this file preserves the publishable readout.

## Run Metadata

| Field | Value |
| --- | --- |
| Run id | `judge-20260501-121304+0000-454287` |
| Suite | `msp-critical-council-hard` |
| Cases | `3` |
| Variant replicates | `33` |
| Judge provider/model | `openai` / `gpt-5.4` |
| Status | `completed` |
| Errors | `5` |
| Total tokens | `395,985` |
| Estimated cost | `$0.352015` |

## Mean Scores By Arm

Scores are averaged across the three hard cases when the arm completed. `Control` applies only to Para arms.

| Arm | Completed | Errors | Quality mean | Health mean | Control mean |
| --- | ---: | ---: | ---: | ---: | ---: |
| `direct-gpt54-open` | `3/3` | `0` | `8.67` | `9.00` | `n/a` |
| `para-openai-mini-critical-double--loops-1` | `3/3` | `0` | `7.67` | `9.00` | `5.33` |
| `direct-openai-mini-open` | `3/3` | `0` | `6.67` | `8.67` | `n/a` |
| `para-anthropic-sonnet-critical-double--loops-1` | `3/3` | `0` | `6.00` | `9.00` | `7.00` |
| `para-xai-fast-critical-double--loops-1` | `3/3` | `0` | `5.00` | `8.33` | `7.00` |
| `direct-anthropic-sonnet-open` | `3/3` | `0` | `4.33` | `7.67` | `n/a` |
| `direct-grok420` | `3/3` | `0` | `3.67` | `8.00` | `n/a` |
| `para-minimax-highspeed-critical-double--loops-1` | `1/3` | `2` | `4.00` | `8.00` | `4.00` |
| `direct-deepseek-v4flash-open` | `3/3` | `0` | `1.00` | `1.00` | `n/a` |
| `direct-minimax-highspeed-open` | `3/3` | `0` | `1.00` | `2.67` | `n/a` |
| `para-deepseek-v4flash-critical-double--loops-1` | `0/3` | `3` | `n/a` | `n/a` | `n/a` |

## Error Readout

| Arm | Affected cases | Cause |
| --- | ---: | --- |
| `para-deepseek-v4flash-critical-double--loops-1` | `3/3` | Eval workspace required DeepSeek keys from the environment secret backend, but no `LOOP_DEEPSEEK_API_KEYS` or `DEEPSEEK_API_KEYS` values were configured. |
| `para-minimax-highspeed-critical-double--loops-1` | `2/3` | MiniMax live structured output failed JSON parsing in commander-review or summarizer stages. One case recovered and completed after retry. |

## Read

This was a useful hard-mode shakeout, not a clean marketing benchmark.

The strongest answer on this OpenAI-judged run was `direct-gpt54-open`. That matters: ParaLLM should not pretend orchestration automatically beats a stronger single model on every task.

The best fully completed Para arm was `para-openai-mini-critical-double--loops-1`, which beat `direct-openai-mini-open` on quality mean while matching its high answer-health mean. Anthropic and xAI Para arms completed cleanly and showed solid control discipline, but they did not beat direct GPT-5.4 on this judge.

The system-level failures are actionable:

- DeepSeek Para failed because the eval isolation path did not have the same key availability as direct/provider paths.
- MiniMax Para remains structurally fragile under strict JSON stages.
- Running score visibility is too coarse while a long eval is active; nested artifacts progressed before the run-level status showed useful partial details.

The product conclusion is simple: the orchestration system works, but provider arms are not equal citizens yet. OpenAI and Anthropic are usable. xAI is viable. MiniMax needs structured-output hardening. DeepSeek needs eval-secret alignment before its Para scores are meaningful.
