# PERCSI and ParaLLM: Cognitive Architecture Lineage

Status: architectural source and development reference

Canonical publication: [PERCSI: A Construct-Based Cognitive Architecture for Simulated Perception, Memory Integration, and Emergent Reasoning](https://medium.com/@jakovposao/percsi-a-construct-based-cognitive-architecture-for-simulated-perception-memory-integration-and-a5060f73fd93)

Author: Jakov Jerkovic

Publication date shown in the article body: July 19, 2025

Repository record created: August 28, 2026

## Why This Document Exists

PERCSI is part of ParaLLM's conceptual lineage. It describes a construct-based way to give stateless inference systems functional continuity through perception, memory processing, hypothesis generation, primary reasoning, and feedback.

ParaLLM has independently turned several of those constructs into working software. This document preserves the original architecture as a source reference, distinguishes it from ParaLLM's current implementation, and records what the relationship implies for the next development phase.

This is not a claim that either system is sentient. It is an engineering account of how durable external constructs can provide continuity, memory, pressure, and inspectable adaptation around otherwise episodic model calls.

## Part I: Author-Supplied Original Text

The text below was supplied directly by Jakov Jerkovic for repository preservation on August 28, 2026. Formatting was normalized to Markdown and Medium interface debris was removed. The article's substantive wording is preserved.

### PERCSI: A Construct-Based Cognitive Architecture for Simulated Perception, Memory Integration, and Emergent Reasoning

**Jakov Jerkovic**

**July 19, 2025**

#### Abstract

Current large language models (LLMs) excel in pattern recognition and symbolic reasoning but lack key cognitive attributes such as persistent perception, contextual continuity, and adaptive self-referential reasoning. This paper introduces PERCSI (Perceived Embodiment through Reasoning, Constructs, and Sensory Integration), a layered cognitive framework that simulates continuous perception using sensor integration, prioritized memory orchestration, and recursive hypothesis generation. PERCSI bridges the gap between stateless inference systems and the perception-action loops inherent to biological cognition by combining real-time sensory input streams with hierarchical memory and secondary reasoning subsystems. While PERCSI does not endow intrinsic sentience, it achieves functional continuity and proto-emergent behaviors through orchestrated constructs, providing a pathway for scalable artificial agency under bounded compute conditions.

#### 1. Introduction

Biological cognition is characterized by persistent, unavoidable perception, what we term gate lock on flood: a continuous influx of sensory data shaping adaptive responses and internal states. Humans cannot selectively “disable” perception, and their memory systems dynamically integrate experience into decision-making. In contrast, contemporary LLMs are reactive and stateless, responding to isolated prompts without inherent continuity.

The absence of continuous perceptual context restricts emergent properties such as long-horizon reasoning and goal persistence. We propose PERCSI, a modular architecture designed to fake continuity by layering constructs for perception, memory integration, and hypothesis-driven reasoning over stateless inference models.

#### 2. Related Work

##### 2.1 Cognitive Architectures

Classical frameworks such as SOAR [Newell, 1990] and ACT-R [Anderson, 1996] formalized symbolic cognitive control but lacked adaptability to unstructured sensory streams. LIDA extended these ideas into embodied agents, yet computational cost and brittleness remain barriers.

##### 2.2 Embodied AI and Sensor Fusion

Robotics and embodied AI leverage perception-action loops to achieve contextually grounded behavior [Brooks, 1986; Levine et al., 2016]. While these approaches hardwire sensor responses into procedural routines, PERCSI introduces dynamic prioritization and hypothesis evaluation.

##### 2.3 Emergent Behavior and Meta-Reasoning

Recent work such as Reflexion [Shinn et al., 2023] and Self-Ask [Press et al., 2022] demonstrates recursive reasoning and self-critique as mechanisms for improved task performance. PERCSI generalizes this by introducing asynchronous sub-models for meta-level hypothesis generation informed by multimodal inputs.

#### 3. The PERCSI Framework

##### 3.1 Architectural Overview

PERCSI consists of five interacting layers designed to emulate perception, contextual memory, and recursive evaluation (Figure 1):

1. Sensory Integration Layer (SIL)
2. Contextual Memory Orchestrator (CMO)
3. Independent Memory Processor (IMP)
4. Hypothesis Generation Engine (HGE)
5. Primary Cognitive Core (PCC)

Feedback Loop: Monitors outcomes, adjusts hypothesis weighting for next iteration.

##### 3.2 Control Flow (Algorithmic Outline)

```text
While system_active:
    sensory_input = capture(SIL)
    memory_update(CMO, sensory_input)
    context_summary = IMP.summarize(memory_state)
    hypotheses = HGE.generate(context_summary)
    output = PCC.reason(hypotheses, context_summary)
    log_feedback(output)
```

#### 4. Expected Properties and Emergence

By simulating perception continuity and layering reflective sub-processes, PERCSI exhibits:

- Persistent Awareness Illusion: Sensors provide constant state updates.
- Self-Referential Loops: HGE injects meta-context into reasoning, mimicking introspection.
- Goal Continuity: Memory replay creates pseudo-intentional behavior (e.g., resuming prior tasks autonomously).

#### 5. Experimental Testbed: Mobile Implementation

Smartphones provide an ideal environment for PERCSI:

- Sensor-rich platform: Accelerometer, gyroscope, GPS, camera, mic.
- Local inference capability: Neural processing units for HGE and IMP.
- Cloud offload for PCC: LLM reasoning hosted remotely with asynchronous caching.

Hypothesis: Mobile-based PERCSI can demonstrate adaptive behaviors such as energy optimization, personalized context switching, and proactive alerting — without explicit programming of these features.

#### 6. Ethical and Safety Considerations

PERCSI creates behavioral anthropomorphism without sentience, raising transparency concerns. Safeguards:

- Mandatory introspection logs.
- Hard limits on autonomous execution.
- Explainable hypothesis reporting.

#### 7. Conclusion

PERCSI demonstrates that continuous perception and emergent-like reasoning can be simulated through orchestrated constructs layered over stateless inference models. By introducing modular subsystems for sensory integration, memory management, and hypothesis-driven evaluation, PERCSI provides a blueprint for future context-aware, adaptive agents without requiring full AGI infrastructure.

#### References

- Newell, A. (1990). *Unified Theories of Cognition*. Harvard University Press.
- Anderson, J.R. (1996). *ACT-R: A Cognitive Architecture for Modeling Human Cognition*.
- Brooks, R. (1986). *A Robust Layered Control System for a Mobile Robot*. IEEE Journal of Robotics.
- Levine, S., et al. (2016). *End-to-End Training of Deep Visuomotor Policies*. JMLR.
- Shinn, N., et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. arXiv:2303.11366.
- Press, O., et al. (2022). *Measuring and Narrowing the Compositionality Gap in Language Models*.

## Part II: My Perception of PERCSI

PERCSI's important move is not "give an LLM more context." Its important move is to separate cognitive functions into persistent constructs around the model.

The model is not expected to become continuous by itself. Continuity is produced by architecture:

- perception keeps arriving,
- memory survives individual calls,
- memory is processed outside the main response,
- multiple hypotheses exist before selection,
- one core emits the public decision,
- observed outcomes alter later cycles.

That distinction is fundamental. Prompt engineering changes a call. PERCSI changes the environment in which calls occur.

The phrase "gate lock on flood" is particularly important to the design. A biological system cannot simply opt out of all perception. A PERCSI-style system therefore needs an input stream that remains available even when the primary core is idle. This does not mean every event should reach the expensive reasoning path. It means every event should enter an accountable attention and memory system that decides whether it is noise, state, evidence, conflict, or a reason to think.

PERCSI also provides a useful boundary against anthropomorphic overclaiming. Functional continuity, self-reference, and resumed goals can emerge from external state and feedback without proving subjective experience. That makes the architecture useful precisely because its behavior can be engineered, inspected, and tested without requiring a metaphysical conclusion.

## Part III: PERCSI Compared with ParaLLM

### Architectural Mapping

| PERCSI construct | ParaLLM implementation or analogue | Current maturity | Important gap |
| --- | --- | --- | --- |
| Sensory Integration Layer | User prompts, runtime events, steps, provider callbacks, tools, files, repo graph, job state, and logs | Partial | Inputs are mostly task-triggered. There is no unified continuous perception bus with attention and novelty control. |
| Contextual Memory Orchestrator | Fractal Memory banks, scoped recall, ranked retrieval, runtime fallback, provenance, Timerbiter metadata, and conflict locks | Working but domain-shaped | Recall is stronger than deposit. Education, routing, authority, retention, supersession, and promotion are not yet one lifecycle. |
| Independent Memory Processor | Memory projection, query-focused excerpts, Timerbiter ordering, obligation extraction, judge learning, candidate ledger, and librarian artifacts | Partial | Processing is not yet a durable independent service that continually consolidates and re-evaluates memory. |
| Hypothesis Generation Engine | Commander plus adversarial workers, dynamic specialist lanes, skills, contradiction capture, and provider diversity | Strong | Lanes are normally spawned by a run contract, not by a generalized perception or unresolved-state trigger. |
| Primary Cognitive Core | Commander Review plus Summarizer and final-answer release gates | Strong | The final core still depends on model compliance backed by deterministic checks; action authority remains mostly answer-oriented. |
| Feedback Loop | Evals, judges, provider-call ledgers, evidence artifacts, replay, deterministic checks, and memory candidates | Strong evidence capture, incomplete learning | Candidate promotion is deliberately held. Generic outcome-to-memory-to-hypothesis reweighting is not closed yet. |

### Where ParaLLM Already Extends the PERCSI Sketch

ParaLLM adds several engineering controls that PERCSI identifies in principle but does not specify operationally:

- provider-normalized execution across multiple model families,
- adversarial disagreement that remains visible instead of being averaged away,
- explicit source and artifact retention,
- unresolved-memory conflict locks that freeze affected actions,
- deterministic final-answer obligation checks,
- isolated Direct, Direct plus memory, and multi-lane evaluation paths,
- cost, usage, timeout, authentication, and scheduler contracts,
- operator-facing review surfaces for claims, traces, failures, and evidence.

PERCSI explains the cognitive topology. ParaLLM is becoming an operational implementation with audit, provider, evaluation, and deployment boundaries.

### Where ParaLLM Does Not Yet Satisfy PERCSI

ParaLLM is not yet continuously perceptive. Its scheduler can continue work and its runtime records state, but most cognition still begins with an operator task or an explicit job.

The memory system is asymmetrical:

- retrieval is implemented and increasingly authoritative,
- temporal projection and contradiction handling are implemented,
- answer release can enforce retrieved obligations,
- candidate capture exists,
- generic context-driven destination selection is not implemented,
- promotion remains intentionally disabled pending contextual review,
- deployment education is not yet a first-class product workflow.

The feedback loop therefore records more than it safely learns. That is the correct safety posture for the current stage, but it is also the main architectural gap.

## Part IV: Consequences for the Next Development Phase

### 1. Treat Education as CMO and IMP Construction

The proposed Fractal Memory educational module should not be a bulk document uploader. It should build a deployment-specific cognitive context through a governed pipeline:

1. Register the deployment, domain, owners, and allowed sources.
2. Ingest source material without promoting it directly to trusted memory.
3. Preserve the original artifact and content hash.
4. Extract candidate facts, procedures, entities, relationships, temporal claims, exceptions, and conflicts.
5. Route candidates to session, user, domain, SOP, benchmark, artifact, quarantine, or rejection destinations.
6. Verify claims against their source and, where required, independent corroborating evidence.
7. Assign scope, authority, freshness, temporal bounds, retention, and supersession rules.
8. Promote only reviewed or policy-qualified candidates into active banks.
9. Generate curriculum checks and deployment exams from promoted material.
10. Re-run retrieval, conflict, and action tests before declaring the deployment educated.

This is the practical merger of PERCSI's Contextual Memory Orchestrator and Independent Memory Processor.

### 2. Checkpoint Before Reset

The current MSP, synthetic needle, conflict, and LongMemEval banks are experimental evidence. They should be checkpointed with:

- bank contents and hashes,
- source registry,
- eval manifests and scores,
- retrieval configuration,
- Timerbiter projections,
- known limitations,
- application version and commit,
- restoration instructions.

Only after that checkpoint should active memory be cleared for a clean educational-module proof. Resetting active memory must not erase the evidence that established the architecture's current behavior.

### 3. Introduce a Perception Event Contract

A future SIL should normalize inputs into an event envelope rather than wiring each source directly into reasoning. A minimal event should carry:

- event id and observed time,
- source and source authority,
- deployment and subject scope,
- raw artifact reference,
- normalized observation,
- confidence and novelty,
- urgency and expiry,
- relationship to existing state,
- privacy and execution constraints.

The first consumer should be an attention/router layer, not the most expensive reasoning model. Continuous perception without attention control becomes cost amplification and context poisoning.

### 4. Keep Memory Authoritative but Falsifiable

ParaLLM's rule that relevant memory outranks fresh model priors should remain. The education module must make that trust deserved.

Memory should be overmatched only by explicit evidence with stronger authority, narrower scope, greater freshness, or a valid signed exception. An unresolved material conflict should freeze the affected action and identify what evidence or authority can resolve it.

This keeps memory from becoming either optional flavor text or an uncorrectable dogma.

### 5. Separate Hypothesis from Action

PERCSI's HGE should be free to generate uncomfortable or unlikely hypotheses. That freedom should not imply permission to act.

ParaLLM should preserve separate contracts for:

- hypothesis generation,
- evidence gathering,
- adjudication,
- public recommendation,
- reversible execution,
- irreversible or privileged execution.

The richer the perception and memory loop becomes, the more important this separation becomes.

### 6. Make Feedback Earn the Right to Become Memory

A high judge score is evidence about an answer, not automatic evidence that every sentence in the answer is true. Feedback promotion should distinguish:

- observed outcome,
- judge interpretation,
- operator correction,
- source-backed fact,
- reusable procedure,
- model-generated hypothesis,
- benchmark-specific artifact.

The candidate ledger already creates the correct holding area. The next step is a context router and memory arbiter that can explain every promote, merge, supersede, quarantine, and reject decision.

## Part V: Working Architectural Position

PERCSI should remain the conceptual parent architecture and ParaLLM should remain the engineered vehicle. They are related but not interchangeable.

PERCSI asks how continuity, perception, memory, hypotheses, and feedback can be constructed around stateless inference.

ParaLLM asks how those constructs can be made operational across providers, domains, evidence stores, operator controls, evaluations, and deployment boundaries without hiding disagreement or surrendering auditability.

The immediate development direction is therefore:

> Turn ParaLLM's proven answer-time memory machinery into a governed deployment education system, then connect that system to an accountable perception loop.

That direction advances the original PERCSI thesis while staying faithful to the evidence, safety boundaries, and operational lessons already produced by ParaLLM.

## Evidence Pointers in This Repository

- [README architecture and benchmark record](../README.md)
- [Running architecture and milestone log](../project.md)
- [Memory deposit pipeline](memory-deposit-pipeline.md)
- [Memory evidence journey](journal/2026-05-19-memory-evidence-journey.md)
- [Synthetic memory test](eval-results/2026-05-13-synthetic-needle-ledger-transit.md)
- [LongMemEval oracle pilot](eval-results/2026-05-13-longmemeval-oracle-pilot.md)
- [Memory conflict owner audit](eval-results/2026-05-12-memory-conflict-owner-audit-rerun.md)
- `backend/app/knowledgebase.py`
- `backend/app/memory_deposit.py`
- `backend/app/judge_learning.py`
- `runtime/engine.py`
- `runtime/eval_runner.py`
