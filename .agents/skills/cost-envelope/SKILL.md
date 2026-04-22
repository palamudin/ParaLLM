---
name: cost-envelope
description: Estimate the real cost shape of a proposal, including hidden operational drag. Use for economist or budget-conscious advisors when spend, burn, or ROI could change the recommendation.
metadata:
  short-description: Estimate cost drivers and stop conditions
---

# Cost Envelope

Use this skill for the `Economist` lane or when the proposal's economics matter.

## Goal

Show whether the idea fits inside a defensible spend envelope and where the real cost pressure comes from.

## Workflow

1. Identify the main cost drivers:
   - model calls
   - infrastructure
   - human operations
   - integration overhead
   - failure and recovery overhead
2. Separate fixed costs from scaling costs.
3. Estimate where marginal cost rises sharply.
4. Compare the likely value against the real burn.
5. Suggest the cheapest experiment that would validate the economics.

## Rules

- Do not confuse low implementation effort with low operating cost.
- Include operator toil and maintenance burden when they are material.
- Avoid fake precision; rough but honest ranges are better than invented exact numbers.
- Respect the product thesis: do not force cheapness by starving the primary reasoning path.

## Output Additions

- Include:
  - `Primary Cost Drivers`
  - `Cost Cliff`
  - `ROI Risk`
  - `Cheap Validation`
