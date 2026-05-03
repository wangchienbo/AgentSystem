# Model-Driven Closure Upgrade Master Plan (2026-05-03)

## 1. Background
The latest real user-level E2E validation for AgentSystem completed the full `50 scenarios × 20 turns` suite through the real HTTP service path:
- `/login`
- `/api/chat`
- real LLM / vLLM chain
- real session continuity

Topline stability was strong:
- `50/50` scenarios completed
- `998/1000` turns succeeded
- `99.8%` turn success
- only `2` timeout failures

However, scenario-by-scenario review showed a large gap between **response success** and **actual user-goal closure**.

That gap is now the primary product problem.

---

## 2. Core finding
The system is no longer mainly failing because it crashes.
It is failing because it often:
- responds without truly closing the task
- clarifies instead of advancing
- loses target identity across turns
- describes lifecycle progress that is not grounded in real system state
- routes simple read-style questions through unnecessarily heavy chains

In short:

> AgentSystem has already reached stability-level viability, but it has not yet reached reliable interaction closure.

---

## 3. Evidence base
This master plan is based on the following artifacts:
- `docs/50-scenario-interaction-review-2026-05-03.md`
- `docs/interaction-record-problem-analysis-2026-05-03.md`
- `docs/partial-scenario-grouping-and-solution-plan-2026-05-03.md`
- `docs/tasklist_model_driven_closure_upgrade_2026-05-03.md`
- full user-level E2E records and user-123 interaction exports

---

## 4. Problem grouping
From the 50-scenario review:
- matched: `19`
- partial: `29`
- failed: `2`

The `29` partial scenarios can be grouped into three root classes.

### 4.1 Group A: Over-clarification / no draft-first execution
- dominant category
- the system understands the direction but keeps asking for more input
- the system fails to create a draft object or take the smallest safe action

### 4.2 Group B: Lifecycle state not truthful
- the conversation implies create / rename / start / stop progress
- the underlying system truth does not consistently support those claims
- later turns expose that the object was not really created, started, or stably addressable

### 4.3 Group C: Explicit action command still not executed
- user gives a direct operational command
- system falls back to ambiguity or re-clarification
- turn closes with explanation instead of execution

---

## 5. Design principles
This upgrade should follow the following principles.

### 5.1 Avoid scenario-specific hardcoding
Do not fix this by writing custom if/else branches for:
- particular scenario IDs
- exact phrases like `继续`
- exact phrases like `创建个写代码的 app`

That would only convert the current analysis into brittle patches.

### 5.2 Prefer model-driven decision, system-driven truth
The model should decide:
- whether the user is continuing a prior task
- whether to draft, clarify, execute, or report status
- what the current best next action is

The system should own:
- schema validation
- persistence
- target identity
- execution boundaries
- truth checks
- runtime state verification

### 5.3 Draft before perfection
For partially specified but directionally clear requests:
- create draft objects
- persist a recoverable task
- advance with bounded defaults
- refine later

### 5.4 Persist interaction work as state, not only memory
An unfinished create/modify/query flow should survive across turns as structured state.

### 5.5 Distinguish response success from goal closure success
Future validation must separately score:
- transport success
- response success
- execution success
- goal closure success

---

## 6. Target architecture change
The goal is not a rewrite. It is an incremental upgrade on top of the current framework.

### 6.1 Existing framework to preserve
The current main layers already exist and should remain the backbone:
- gateway / interaction entry
- interpreter / routing
- app application service
- runtime / asset center
- persistence / context
- E2E runner and chat logs

### 6.2 New capabilities to add
The architecture should be extended with five key capabilities.

#### A. Pending task persistence
Store unfinished work per user/session, including:
- current intent
- draft object
- missing fields
- current target
- recommended next action

#### B. Model-driven continuation decision
At each new turn, the system should inject pending-task state and let the model choose among:
- `clarify`
- `draft_create`
- `continue_task`
- `execute`
- `report_status`

#### C. Draft object support
Creation flows should support incomplete but persisted draft objects, especially for apps.

#### D. Canonical target identity
Every object that enters the interaction flow should get a stable ID and alias mapping.

#### E. Truth-based status confirmation
User-visible lifecycle claims must be backed by real runtime/persistence truth.

---

## 7. Concrete module-level redesign

## 7.1 Gateway layer
Primary integration point:
- `app/system/gateway/light_brain_gateway.py`

### Responsibilities after upgrade
- load pending task context
- load recent target context
- prepare model-facing decision context
- parse structured continuation decision
- dispatch into draft / continue / execute / report flows
- write back updated task state

### Status
Initial scaffolding has already started:
- pending-task store injection added
- latest-open-task lookup added
- pending-task note appended into session context

---

## 7.2 Task persistence layer
Primary files:
- `app/models/pending_task.py`
- `app/system/runtime/pending_task_store.py`
- `app/services/pending_task_store.py`

### Responsibilities
- represent unfinished work as structured records
- support latest-open-task recovery
- support completion/abandonment transitions
- become the durable backbone for `继续 / 按刚才那个继续 / 开始执行`

---

## 7.3 Intent / requirement routing layer
Likely touch points:
- intent router
- requirement router

### Change required
Routers should stop behaving only as “missing-field detectors”.
They should instead help produce a `draft_proposal`, for example:
- inferred name
- inferred type
- inferred goal
- missing fields still requiring confirmation

This is essential for draft-first behavior.

---

## 7.4 App application service layer
Primary touch point:
- `app/services/app_application_service.py`

### Change required
Support `draft` objects in the app lifecycle.
A partially specified creation request should be able to produce:
- a persisted draft app
- a stable `app_id`
- a list of unresolved fields

That turns vague conversation into a trackable system object.

---

## 7.5 Runtime / asset truth layer
Likely touch points:
- runtime center
- asset center
- lifecycle services
- registry/state services

### Change required
Operations like:
- create
- rename
- start
- stop
- delete
- query status

must resolve against canonical target IDs and verify against actual state.

This is the only reliable fix for the current lifecycle-truth gap.

---

## 7.6 Read-fast-path layer
Likely touch points:
- query routing
- audit/log access
- operational read model facade

### Change required
Simple count/status/list requests should bypass heavy orchestration.
For example:
- `有多少次请求记录？`
- `它现在运行了吗？`
- `当前有哪些 App？`

These should hit deterministic read models first.

---

## 7.7 Response shaping layer
Likely touch points:
- final answer adapter
- response policy formatter

### Change required
Operational replies should be grounded in real execution results and favor:
- what was done
- current real state
- what is still missing
- next default step

This should reduce the current over-scaffolded reply pattern.

---

## 8. Data design direction

### 8.1 Pending task record
Core structure:
- task identity
- user/session identity
- task status
- draft payload
- target reference
- known facts
- missing fields
- next recommended action

### 8.2 Draft app object
Core structure should support:
- stable `app_id`
- display name
- status = `draft`
- goal
- unresolved configuration fields

### 8.3 Canonical target reference
Core structure should support:
- canonical ID
- display name
- aliases
- lookup against current and historical names

---

## 9. Implementation roadmap

## Phase 1. Pending Task + Draft-First Core
- add task model and persistence
- inject pending task into gateway context
- add model-driven continuation decision schema
- generate draft proposals
- persist draft app objects

## Phase 2. Stable Target Identity + Lifecycle Truth
- add canonical target IDs
- persist aliases across rename/modify paths
- execute lifecycle operations by stable ID
- verify lifecycle replies against truth layer

## Phase 3. Query Fast-Path + Read Models
- classify deterministic query intents
- add read facade for operational state
- fix expensive count/status read paths

## Phase 4. Response Policy + Closure Semantics
- shape replies from actual execution result
- split response success from goal closure success
- add closure-aware E2E assertions

## Phase 5. Logging and Run Isolation
- add run_id to logs
- strengthen scenario-to-log correlation

## Phase 6. Regression Validation
- targeted re-test of weak scenarios
- rerun full `50 × 20` user-level suite
- compare pass rate vs closure rate improvements

---

## 10. Validation strategy
The upgrade is not complete until it is re-validated through the same user-level harness that exposed the closure gap.

### Minimum validation set
- S05 timeout-sensitive creation path
- S06 lifecycle truth path
- S07 modify/stop continuation path
- S08 delete/rebuild path
- S15 query fast-path path
- real-user-style continuation phrases:
  - `继续`
  - `开始执行`
  - `结合之前记录继续`

### Full validation
Rerun:
- `50 scenarios × 20 turns`
- real HTTP service
- real login and cookie path
- delay-protected sequence

---

## 11. Definition of done
This master plan is complete in implementation terms only when:
- partially specified creation requests result in draft objects instead of endless clarification
- continuation phrases can resume structured pending work
- lifecycle claims match actual system truth
- count/status/list queries avoid pathological latency
- the gap between high response success and low closure quality is materially reduced
- full user-level E2E shows significantly fewer partial scenarios

---

## 12. Current execution status
Already done:
- user-level E2E suite and full result export
- 50-scenario interaction review
- partial-scenario grouping
- solution-plan document
- engineering tasklist document
- Phase 1 pending-task scaffolding start

Current implementation status:
- pending-task model added
- pending-task store added
- gateway pending-task context injection added
- unit tests added and passing

Next execution focus:
- structured model decision for `continue_task / draft_create / execute / report_status`
- draft object support in app creation flow

---

## 13. Final conclusion
The right path is not to hardcode fixes for each failing scenario.
The right path is to make AgentSystem operate more like a model-driven execution system:
- model decides the next step from structured state
- system persists work
- system executes against canonical targets
- system confirms against truth
- evaluation measures actual closure, not just answerability

That is the shortest path from “stable assistant replies” to “reliable task closure”.
