# Phase 4 / Workflow Execution Enhancement

## 1. Purpose

Phase 4 turns the current workflow path from a usable prototype into a more complete execution substrate.

The current system already supports:
- basic workflow execution
- deterministic module primitives
- skill-step dispatch
- prompt invocation as a workflow step
- retry, diagnostics, timeline, and health summaries

The next gap is not whether workflows can run at all, but whether workflows can serve as the stable execution backbone for real apps, app refinement, and later long-lived runtime behavior.

Phase 4 therefore focuses on:
- richer workflow step coverage
- stronger app-data and event integration
- better recovery and retry semantics
- more explicit execution-state and failure-state contracts
- keeping the execution layer deterministic-first and inspectable

---

## 2. Goals

Phase 4 should deliver a workflow runtime that is:
- expressive enough for realistic app logic
- bounded and deterministic by default
- observable enough for later refinement/governance loops
- compatible with app-local shared context and app data namespaces
- safe to extend toward Phase 5 refinement/app-assembly flows

---

## 3. Current baseline

Already implemented:
- workflow step execution
- `state.set` / `state.get`
- event emission
- skill-step dispatch
- prompt invocation step
- step-output references (`$from_step`, `$from_inputs`)
- conditional execution (`when`)
- execution history
- failure inspection
- retry
- diagnostics / overview / timeline / dashboard summaries

Current major gaps:
- richer deterministic workflow primitives for app data and event operations
- explicit workflow compensation / recovery posture
- better partial-failure semantics for multi-step apps
- operator-facing execution contracts for unresolved/manual work
- stronger consistency between execution, context, and stored artifacts

---

## 4. Deliverables

### 4.1 Workflow primitive expansion

Add first-class workflow primitives for:
- `data.read`
- `data.write`
- `data.list`
- `event.publish`
- `context.append`
- `context.set_goal`
- `context.set_stage`
- `workflow.fail`
- `workflow.complete`
- `workflow.pause_for_human`

Design rules:
- these remain module-style deterministic runtime primitives
- they should not bypass existing service/store boundaries
- each primitive should emit structured step outputs
- failure should distinguish contract error vs runtime/store error

### 4.2 Workflow execution state contract

Introduce clearer execution-state distinctions such as:
- `completed`
- `partial`
- `failed`
- `paused_for_human`
- `blocked_by_policy`
- `waiting_for_event`

The executor should preserve:
- latest blocking step
- unresolved step ids
- unresolved reason kinds
- recovery hints

### 4.3 Recovery and retry model

Strengthen retry from “rerun the latest failed/partial execution” into a clearer recovery model:
- retry from latest partial or failed execution
- preserve retry lineage
- summarize what changed since the parent execution
- distinguish resolved / unchanged / newly failed steps
- expose machine-readable recovery metadata

Future-facing but still Phase-4 scoped:
- bounded step-level retry policy
- retry-safe deterministic primitives
- explicit non-retryable contract violations

### 4.4 App data and context coupling

Workflow execution should become the main safe path for app data mutation.

Required behavior:
- app data writes flow through deterministic primitives
- context writes are explicit and inspectable
- workflow-produced artifacts can be persisted into app namespaces and context together without ambiguity
- operator-facing diagnostics can explain which data/context writes happened before failure

### 4.5 Human/manual work contract

The current `human_task` placeholder should evolve into an explicit blocked/manual-work contract.

At minimum:
- a step can intentionally pause into `paused_for_human`
- the execution record preserves what input/action is needed
- unresolved manual steps remain visible in diagnostics/overview/dashboard reads
- retry/recovery can resume after manual satisfaction instead of appearing as a generic failure only

### 4.6 Event-driven continuation

Event handling should evolve from “publish an event and maybe trigger a schedule” into a clearer workflow continuation contract:
- workflows may publish events
- workflows may block waiting for named events
- diagnostics should surface event-wait state distinctly from ordinary failure
- later events can resume or trigger follow-up runs through explicit stored linkage

---

## 5. API and contract changes

Phase 4 should introduce or extend APIs for:
- workflow execution detail with unresolved/manual/event-wait state
- latest recovery summary
- optional resume-after-manual action
- optional resume-after-event linkage visibility
- app-data/context mutation traces inside workflow diagnostics

Public contracts should stay stable and page-shaped where appropriate.

---

## 6. Service/module plan

Expected code areas:
- `app/services/workflow_executor.py`
- `app/services/workflow_observability.py`
- `app/services/app_data_store.py`
- `app/services/app_context.py`
- `app/services/event_bus.py`
- `app/models/workflow_observability.py`
- `app/models/...workflow execution state models...`
- `app/api/main.py`

Possible new helpers:
- `app/services/workflow_step_runtime.py`
- `app/services/workflow_recovery.py`
- `app/services/workflow_context_projection.py`

---

## 7. Test plan

### 7.1 Unit/service tests
- `data.read/write/list` primitives
- explicit blocked/manual/event-wait state modeling
- retry lineage and comparison
- context/data mutation trace summaries

### 7.2 API tests
- diagnostics include unresolved/manual/event-wait state
- retry/resume responses include recovery metadata
- overview/dashboard reflects paused/manual states distinctly

### 7.3 Golden path tests
- multi-step workflow writes app data, appends context, publishes event, then completes
- workflow pauses for human, resumes, and completes
- workflow blocks on policy or event and surfaces inspectable status

---

## 8. Acceptance criteria

Phase 4 is complete when:
- workflows can mutate app data and context through first-class primitives
- blocked/manual/event-wait states are distinguishable from generic failure
- retry/recovery metadata is explicit and queryable
- observability surfaces explain unresolved work clearly
- tests cover service + API + golden-path execution behavior

---

## 9. Recommended implementation order

1. workflow execution state contract
2. app-data/context primitives
3. manual-work / event-wait contract
4. recovery metadata and retry lineage
5. observability/API alignment
6. docs + tests + development log update
