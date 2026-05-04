# Phase Q Detailed Task List

## 1. Purpose

This document converts the final Phase Q design baseline into an implementation-oriented task list.

It is intentionally detailed and module-scoped so the next development stage can proceed as a controlled incremental rollout rather than an unbounded redesign.

Companion design reference:
- `docs/phase-q-workflow-context-center-final-design.md`

This task list assumes development continues inside the tracked repository and remains compatible with the current App OS architecture.

---

## 2. Delivery Strategy

Phase Q should be delivered in bounded waves, not as a single giant merge.

Recommended rollout order:
1. workflow state and action contract foundation
2. context center storage and recovery foundation
3. summary/detail retrieval integration
4. repo / upgrade / acceptance self-awareness integration
5. workflow hooks and system-wide context integration
6. full HTTP and service-up acceptance closure

Each wave should:
- keep the system runnable
- add or update focused tests
- update docs
- add development-log evidence
- end with a commit

---

## 3. Global Constraints

All tasks below must respect these constraints:
- preserve compatibility with current `LightBrainGateway`, `PendingTaskRecord`, `/api/chat`, `/api/action`
- do not remove the current draft continuation path before the broader workflow path is ready
- do not expose context-detail retrieval as a normal model-facing tool
- keep Context Center detail events minimal: `timestamp + role + message`
- default recent working memory must continue to mean: `stable + pending`
- keep the summary worker single-threaded with rate limit 1
- keep startup recovery mandatory before Context Center becomes ready
- keep testing focused on changed surfaces first, not broad unrelated regression churn

---

## 4. Wave 1: Workflow State Foundation

### 4.1 Extend pending task model into workflow container

#### Tasks
- extend `app/models/pending_task.py`
- add new workflow-compatible fields:
  - `workflow_type`
  - `current_stage`
  - `stage_status`
  - `solution_draft`
  - `review_result`
  - `task_list`
  - `repo_context`
  - `implementation_plan`
  - `upgrade_plan`
  - `acceptance_plan`
  - `artifacts`
- preserve backward compatibility with existing stored pending-task files
- ensure missing new fields have stable defaults during load

#### Target modules
- `app/models/pending_task.py`
- any pending-task persistence adapters / serializers

#### Acceptance
- existing draft continuation tests still pass
- new tests verify old records can still load without migration failure
- new tests verify the new fields serialize and deserialize correctly

---

### 4.2 Introduce canonical workflow stage constants

Status: [x] completed

#### Tasks
- define canonical stage values for:
  - `intent_received`
  - `solution_drafting`
  - `solution_reviewing`
  - `tasklist_preparing`
  - `repo_locating`
  - `implementation_pending`
  - `implementation_running`
  - `upgrade_pending`
  - `upgrade_running`
  - `acceptance_pending`
  - `acceptance_running`
  - `done`
  - `blocked`
- centralize them in one model/helper location rather than duplicating string literals
- ensure current draft bootstrap path maps cleanly into the new stage model

#### Target modules
- `app/models/pending_task.py`
- `app/services/pending_task_orchestrator.py`

#### Acceptance
- tests verify stage values are stable and reused consistently
- draft path still works with mapped stage progression

---

### 4.3 Upgrade PendingTaskOrchestrator into stage transition engine

Status: [x] completed

#### Tasks
- refactor `app/services/pending_task_orchestrator.py`
- preserve current draft-specific stage logic
- add stage transition helpers for broader workflow progression
- separate:
  - stage transition logic
  - next action generation
  - fact updates
  - artifact updates
- ensure `next_recommended_action` continues to work for current draft path

#### Target modules
- `app/services/pending_task_orchestrator.py`

#### Acceptance
- current draft continuation tests remain green
- new tests verify stage transition helpers for non-draft workflow stages
- orchestrator can represent blocked state and done state cleanly

---

### 4.4 Expand gateway action contract for future workflow operations

Status: [x] completed

#### Tasks
- extend gateway action payload builders to support future actions:
  - `approve_solution_draft`
  - `revise_solution_draft`
  - `materialize_task_list`
  - `locate_repo_context`
  - `implement_app_change`
  - `upgrade_app_runtime`
  - `run_acceptance`
- keep `apply_draft_app` fully compatible
- do not require all new actions to be executable in wave 1; contract support can precede full handlers

#### Target modules
- `app/system/gateway/light_brain_gateway.py`
- `app/models/chat.py`
- any action envelope helpers

#### Acceptance
- tests verify action payload shape remains backward compatible
- tests verify new action types can be emitted without breaking old clients

---

## 5. Wave 2: Context Center Storage and Recovery Foundation

### 5.1 Introduce Context Center storage module layout

Status: [x] completed

#### Tasks
- add a formal Context Center service area, for example under:
  - `app/services/context_center.py`
  - `app/services/context_writer.py`
  - `app/services/context_query_service.py`
  - `app/services/context_recovery_manager.py`
  - `app/services/context_summary_worker.py`
- wire them as first-class runtime services rather than helper functions

#### Acceptance
- runtime can construct these services cleanly
- service bootstrap does not yet need full feature parity, but service wiring must be real

---

### 5.2 Implement minimal detail event schema

Status: [x] completed

#### Tasks
- define detail event write/read contract using only:
  - `timestamp`
  - `role`
  - `message`
- ensure session binding is carried by storage path
- define role rules for:
  - `user`
  - `system`
  - `<tool_name>`
  - `<asset_name>`
- do not add detail-layer meta payloads in this wave

#### Acceptance
- tests verify detail event append and readback format
- tests verify role values pass through unchanged

---

### 5.3 Implement session-bucketed day-file storage

Status: [x] completed

#### Tasks
- create storage layout:
  - `context/detail/<session_id>/YYYY-MM-DD.jsonl`
  - `context/summary/<session_id>/YYYY-MM-DD.jsonl`
- add path helpers
- ensure directory creation is automatic
- ensure cross-day writing behavior works correctly at date boundaries

#### Acceptance
- tests verify file creation and append behavior
- tests verify multi-day read support across day files

---

### 5.4 Implement durable temporary buffer

Status: [x] completed

#### Tasks
- add a persistent temporary event buffer for not-yet-stable events
- implement it as a bounded ring-buffer style file or equivalent bounded durable structure
- store enough information to recover pending window events after restart
- make the buffer session-aware

#### Acceptance
- tests verify pending events survive process restart simulation
- tests verify buffer can reconstruct ordering candidates

---

### 5.5 Implement session-local sliding reorder window

Status: [x] completed

#### Tasks
- implement 5 minute reorder window:
  - first 2 minutes stable zone
  - last 3 minutes waiting zone
- add per-session priority queue / ordering structure
- write stable-zone events to formal detail store
- keep waiting-zone events in temporary durable storage + memory queue

#### Acceptance
- tests verify in-order writes
- tests verify modest out-of-order arrival gets corrected
- tests verify stable events flush while waiting events remain pending

---

### 5.6 Implement startup recovery before ready

#### Tasks
- on service startup:
  - read temporary durable buffer
  - rebuild pending queues
  - reorder buffered events
  - flush stable zone to formal detail files
  - retain waiting zone
- Context Center must not become ready until recovery is done
- expose ready / recovering state internally

#### Acceptance
- tests simulate restart and verify recovery
- tests verify service not-ready state before recovery completion
- tests verify recovered state can continue normal writes after startup

---

### 5.7 Enforce session-local write serialization

Status: [x] completed

#### Tasks
- ensure same-session writes cannot race
- add per-session lock/serializer strategy
- verify detail file append, temp buffer write, and queue updates are serialized for one session

#### Acceptance
- tests simulate concurrent same-session writes
- no corruption / duplication / unstable append order in same-session path

---

## 6. Wave 3: Summary Layer and Recent Working Memory View

### 6.1 Implement recent working memory query surface

Status: [x] completed

#### Tasks
- implement query service that returns default recent 300 events
- read across multiple day files when necessary
- merge:
  - stable events from formal detail files
  - pending events from reorder window
- return them in a structured form distinguishing `stable` and `pending`

#### Acceptance
- tests verify default recent count behavior
- tests verify stable + pending both appear
- tests verify cross-day recent reads

---

### 6.2 Implement provisional summary write path

Status: [x] completed

#### Tasks
- when detail event is formally flushed, generate immediate provisional summary
- write provisional summary into session/day summary file
- ensure summary remains available even before LLM finalization

#### Acceptance
- tests verify summary is available immediately after detail flush
- tests verify provisional summary file path and append behavior

---

### 6.3 Implement finalized summary replacement worker

Status: [x] completed

#### Tasks
- implement async summary replacement worker
- worker must be single-threaded and rate-limited to 1
- worker reads provisional summaries and replaces them with finalized LLM summaries
- do not preserve old provisional summary history

#### Acceptance
- tests verify replacement occurs cleanly
- tests verify only one worker path runs at a time
- tests verify failed LLM summary generation does not block detail persistence

---

### 6.4 Implement summary prompt policy

Status: [x] completed

#### Tasks
- codify summary prompt rules:
  - short record: near-verbatim, light cleanup only
  - long record: summarize only “what was done” and “what the result was”
  - forbid invented facts, attempt→confirmation inflation, partial→complete inflation
- centralize summary prompt construction

#### Acceptance
- prompt tests or contract tests verify assembled prompt text contains the required constraints
- if lightweight model stub tests are available, verify short vs long branching works

---

### 6.5 Add summary/detail retrieval integration points

Status: [x] completed

#### Tasks
- implement query methods for:
  - recent working memory summaries
  - detail lookup by id / reference once ids are introduced on the retrieval side
- preserve system-internal retrieval boundary
- do not expose context detail retrieval as general tool invocation

#### Acceptance
- tests verify summary and detail query services are callable from gateway/runtime layers

---

## 7. Wave 4: Gateway and Model-Facing Retrieval Protocol Integration

### 7.1 Expand DecisionProtocol for context/asset retrieval requests

Status: [x] completed

#### Tasks
- extend decision protocol models to support:
  - `needed_context_detail_ids`
  - `needed_more_context_summary_query`
  - `needed_asset_detail_ids`
  - `needed_more_asset_summary_query`
- preserve compatibility with current response and invoke shapes

#### Target modules
- `app/system/interaction_runtime/decision_protocol.py`
- any related response models in `app/models/chat.py`

#### Acceptance
- tests verify parsing/validation of the new retrieval request fields
- existing protocol consumers do not break

---

### 7.2 Integrate recent working memory into gateway assembly

Status: [x] completed

#### Tasks
- update gateway / interaction assembly so the model gets summary-first working memory instead of only loose session history
- include stable + pending working memory view
- keep current draft continuation path compatible

#### Target modules
- `app/system/gateway/light_brain_gateway.py`
- `app/system/interaction_runtime/interaction_orchestrator.py`
- `app/system/http_test_server.py` if response surfaces need compatible additions

#### Acceptance
- tests verify gateway can consume Context Center recent view
- tests verify current conversation reply contract still works

---

### 7.3 Add controlled context detail injection path

Status: [x] completed

#### Tasks
- when the model requests `needed_context_detail_ids`, load the requested detail through Context Center query service
- append detail into the next model turn through system-controlled assembly
- ensure this is recorded as context assembly behavior, not ordinary tool behavior

#### Acceptance
- tests verify detail requests cause detail injection
- tests verify ordinary tool traces are not polluted by internal detail retrieval semantics

---

### 7.4 Add controlled asset detail and broader summary expansion path

Status: [x] completed

#### Tasks
- integrate `needed_asset_detail_ids`
- integrate `needed_more_asset_summary_query`
- integrate `needed_more_context_summary_query`
- ensure expansion requests are bounded and compatible with current asset/query services

#### Acceptance
- tests verify broader summary expansion can be requested without exposing full raw stores by default

---

## 8. Wave 5: Repo / Upgrade / Acceptance Self-Awareness Integration

### 8.1 Implement repo context capture

Status: [x] completed

#### Tasks
- define a reusable repo-context structure carried in pending task state
- capture:
  - active repo path
  - primary README path
  - key docs consulted
  - target files / modules
- seed repo awareness from current project conventions

#### Acceptance
- tests verify repo context can be persisted in workflow state
- gateway/orchestrator can surface repo-related known facts

---

### 8.2 Implement upgrade plan capture

Status: [x] completed

#### Tasks
- define upgrade-plan structure in workflow state
- capture:
  - build/install command plan
  - activation / reload path
  - rollback hint
- keep it initially descriptive if full automated execution is not yet ready

#### Acceptance
- tests verify upgrade plan persistence and rendering into workflow state

---

### 8.3 Implement acceptance plan and acceptance result capture

#### Tasks
- define acceptance-plan structure in workflow state
- capture:
  - test/probe commands
  - HTTP/runtime verification points
  - success criteria
- capture acceptance results back into workflow state and Context Center

#### Acceptance
- tests verify acceptance plans and results serialize correctly
- tests verify acceptance completion emits context write events

---

### 8.4 Standardize high-value fact message templates

#### Tasks
- define consistent message templates for high-value reusable facts such as:
  - repo located
  - target file identified
  - upgrade path determined
  - acceptance passed / failed
- keep detail event schema minimal while making messages more stable and reusable

#### Acceptance
- tests verify template helpers emit stable strings
- gateway/orchestrator integration uses those helpers for new writes where appropriate

---

## 9. Wave 6: Workflow Hooks and System-Wide Context Convergence

### 9.1 Add workflow context write hooks

#### Tasks
- add mandatory write hooks for:
  - stage entered
  - stage completed
  - stage blocked
  - action before execution
  - action after execution
  - acceptance started
  - acceptance completed
- ensure these write through Context Center writer service

#### Acceptance
- tests verify hook invocation on stage changes
- tests verify generated events appear in Context Center storage

---

### 9.2 Integrate app-side context writing

#### Tasks
- allow app/runtime components to write context events through the same writer service
- ensure app-originated events respect session partitioning and role rules

#### Acceptance
- tests verify app-side writes are stored and retrievable

---

### 9.3 Integrate governance / self-iteration observation writes

#### Tasks
- identify which governance/self-iteration observations should enter Context Center as reusable working context
- add bounded integration points so governance observations can contribute to the shared working-memory line without dumping raw logs

#### Acceptance
- tests verify at least one governance/self-iteration path can write compact context events

---

### 9.4 Use Context Center in continuation recovery

#### Tasks
- update continuation logic so “continue” recovery can combine:
  - pending task state
  - recent working memory from Context Center
- retain current draft continuation behavior while broadening the recovery basis

#### Acceptance
- tests verify continuation remains backward compatible
- new tests verify continuation can recover using stored recent context when pending task facts are partial

---

## 10. Wave 7: HTTP, Service-Up, and End-to-End Closure

### 10.1 Extend HTTP surfaces compatibly where needed

#### Tasks
- ensure `/api/chat` and `/api/action` can work with the new workflow/context contracts without breaking existing consumers
- if needed, add compatible context-view metadata fields in responses without removing current fields

#### Acceptance
- HTTP unit tests remain green
- new HTTP tests cover any new fields or changed assembly behavior

---

### 10.2 Add focused Context Center unit tests

#### Tasks
- add unit tests for:
  - storage path helpers
  - ring buffer behavior
  - session-local serialization
  - startup recovery
  - recent stable+pending merge
  - summary worker replacement

#### Acceptance
- dedicated test module suite passes reliably

---

### 10.3 Add gateway/workflow integration tests

#### Tasks
- add focused tests for:
  - workflow stage progression beyond draft-only path
  - context write hooks
  - summary-first model assembly
  - context detail retrieval requests
  - asset detail request compatibility

#### Acceptance
- focused integration suite passes

---

### 10.4 Add HTTP acceptance coverage for recent working memory and continuation recovery

#### Tasks
- extend HTTP/server tests to cover:
  - recent view assembly
  - stable + pending exposure
  - continuation after restart/recovery where practical in bounded tests

#### Acceptance
- HTTP tests verify new behavior without regressing old action path behavior

---

### 10.5 Update service-up E2E path

#### Tasks
- evolve `tests/scripts/e2e_self_iteration_service_up.py` as the broader workflow/context path becomes real
- continue validating:
  - draft create
  - multi-step continue
  - apply_draft_app
  - running state
- then extend toward newer workflow/context behaviors only after the underlying stages are real

#### Acceptance
- focused probe remains green throughout
- full service-up script reaches stable runnable closure again after the new infrastructure lands

---

## 11. Documentation Tasks

### 11.1 Update requirements
- add any accepted new requirement language for workflow stage closure, context center working memory, and summary/detail retrieval if not already reflected

### 11.2 Update design references
- update `docs/design.md` with a short pointer to the new phase document once implementation begins landing materially

### 11.3 Update testing docs
- update `docs/testing.md` and `docs/testing-detail.md` to include:
  - Context Center storage/recovery coverage
  - summary replacement coverage
  - workflow hook coverage
  - restart recovery expectations

### 11.4 Update development log
- every completed wave should append concrete implementation notes and validation evidence

---

## 12. Suggested Commit Boundaries

To avoid excessive fragmentation, recommended commit grouping is:

1. `feat: extend pending task workflow stage model`
2. `feat: add context center storage and recovery foundation`
3. `feat: add working memory summary pipeline`
4. `feat: integrate context and asset summary detail retrieval`
5. `feat: add repo upgrade acceptance workflow awareness`
6. `feat: wire workflow hooks into context center`
7. `test: expand http and service-up closure coverage`
8. `docs: update phase q implementation evidence`

Actual grouping can merge adjacent items when changes are tightly coupled, but each group should still represent a meaningful stable node.

---

## 13. Minimal Acceptance Checklist for Phase Q Completion

Phase Q should only be considered substantially complete when all of the following are true:

- workflow stage model exists beyond narrow draft bootstrap only
- pending task state can carry repo / implementation / upgrade / acceptance planning facts
- Context Center services are real runtime components
- detail events are stored with the minimal event model
- durable buffer + reorder window + recovery work end-to-end
- recent working memory returns structured stable + pending content
- provisional summary + async finalized summary replacement work
- summary/detail retrieval requests are supported in the protocol layer
- gateway can assemble summary-first working memory
- acceptance results are persisted into Context Center
- continuation recovery can use both pending task state and Context Center
- focused tests pass
- HTTP tests pass
- service-up path remains operational
- docs and development log are updated

---

## 14. Final Note

This task list is intentionally detailed so implementation can proceed in bounded modules while keeping the current system live.

The main rule is:
- preserve the current working closure
- extend it in thin compatible layers
- validate each layer before stacking the next one

That is the intended delivery posture for Phase Q.
