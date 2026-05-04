# Phase Q: Workflow / Context Center / Summary-Detail Convergence Final Design

## 1. Purpose

This document is the final design baseline for the next compatible evolution stage of AgentSystem.

It extends the current App OS prototype into a fuller self-iteration and app-delivery closure without replacing the existing architecture. The goal is to converge workflow progression, repo/upgrade/acceptance self-awareness, layered context and asset access, and a system-level Context Center into one governed design.

This phase is additive to the current system and must remain compatible with:
- `LightBrainGateway`
- `PendingTaskRecord` / `PendingTaskOrchestrator`
- `/api/chat` and `/api/action`
- current asset registry/runtime/session-binding foundations
- the existing HTTP service-up acceptance path
- file-based runtime persistence and current session mapping

---

## 2. Design Goals

The target is to upgrade the current narrow continuation chain:
- `draft_create -> continue -> apply_draft_app -> running`

into a complete long-running closure that can cover:
1. solution drafting
2. solution review
3. task list generation and revision
4. repo locating and project self-awareness
5. code modification
6. upgrade / install / activation
7. acceptance and regression validation
8. reusable execution memory and recent working context
9. controlled summary/detail retrieval for both context and assets
10. continuation recovery that survives restart and supports real HTTP paths

This design must preserve the identity of AgentSystem as a **stateful persistent App OS**, not degrade it into a single-turn chat bot or a temporary workflow runner.

---

## 3. Core Design Principles

### 3.1 Compatibility-first incremental evolution
The system must evolve on top of the current structure, not by replacing it with a new planner or a separate workflow engine.

### 3.2 Workflow is the formal closure surface
User requests that lead to app changes, runtime changes, or self-iteration must converge into a staged workflow container instead of remaining loose conversational state.

### 3.3 Default summary, explicit detail
Both context and assets follow the same pattern:
- default to summaries
- fetch detail only when explicitly needed
- keep detail retrieval under system control

### 3.4 Full persistence below, minimal working memory above
The lower layer should persist enough detail for recovery and audit, while the model-facing layer should receive only the current working memory view.

### 3.5 Acceptance is part of the product path
The system is not done when it drafts or edits code. It is done when it can also:
- locate the repo
- apply the change
- install or activate when needed
- verify the result through real runtime acceptance

### 3.6 Context Center is system-level infrastructure
Context Center is not just a chat helper. It is a shared working-memory and recovery substrate for gateway, apps, workflow execution, governance, self-iteration, and acceptance.

---

## 4. Current Compatible Foundations

This phase intentionally builds on existing system foundations that are already present in the repository:
- `LightBrainGateway`
- `InteractionOrchestrator`
- `DecisionProtocol`
- `PendingTaskRecord`
- `PendingTaskStore`
- `PendingTaskOrchestrator`
- `DraftAppApplicationService`
- `AppApplicationService`
- current asset summary/detail direction
- session mapping and parent/child session relationships
- `/api/chat` and `/api/action`
- file-based runtime persistence
- service-up and focused HTTP continuation acceptance coverage

The design assumes these remain the main substrate.

---

## 5. Unified Workflow Stage Layer

### 5.1 Objective
The current continuation chain is too narrow. It should be expanded into a formal workflow stage model that can drive real implementation closure.

### 5.2 Workflow stages
Recommended canonical stages:
1. `intent_received`
2. `solution_drafting`
3. `solution_reviewing`
4. `tasklist_preparing`
5. `repo_locating`
6. `implementation_pending`
7. `implementation_running`
8. `upgrade_pending`
9. `upgrade_running`
10. `acceptance_pending`
11. `acceptance_running`
12. `done`
13. `blocked`

### 5.3 PendingTaskRecord evolution
`PendingTaskRecord` remains the main workflow container and is extended instead of replaced.

It should be able to carry at least:
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

It continues to preserve the current fields such as:
- `intent`
- `status`
- `known_facts`
- `missing_fields`
- `next_recommended_action`

### 5.4 PendingTaskOrchestrator role
`PendingTaskOrchestrator` evolves from draft-bootstrap advancement into a formal stage transition engine.

It should remain compatible with the current draft continuation path while gradually supporting:
- solution progression
- review
- task list materialization
- repo locating
- implementation triggering
- upgrade execution
- acceptance triggering

### 5.5 Workflow write hooks
Workflow stages must define fixed context write hooks at key points:
- stage entered
- stage completed
- stage blocked
- action before execution
- action after execution
- acceptance started
- acceptance completed

These hooks are mandatory and should feed Context Center automatically.

---

## 6. Formal Action Contract Expansion

The current `apply_draft_app` action remains valid and is preserved.

The system should grow a broader action contract surface compatible with workflow progression, including:
- `approve_solution_draft`
- `revise_solution_draft`
- `materialize_task_list`
- `locate_repo_context`
- `implement_app_change`
- `upgrade_app_runtime`
- `run_acceptance`
- `apply_draft_app`

This keeps the current draft path alive while allowing the system to converge toward full implementation closure.

---

## 7. Asset Summary / Detail Layer

### 7.1 Default asset summaries
The model should not receive raw full asset internals by default.

Default asset summary should include compact model-facing information such as:
- identity
- name
- description
- type
- version
- tags

### 7.2 Asset detail retrieval
When more information is needed, the model may request:
- `needed_asset_detail_ids`

The system then injects only the requested detail.

### 7.3 Wider asset discovery
If the currently visible asset summary set is insufficient, the model may request:
- `needed_more_asset_summary_query`

This allows broader asset summary expansion without exposing the entire asset space by default.

---

## 8. Context Summary / Detail Layer

### 8.1 Default summary-first model
The model should see a summary-based working memory by default, not the full raw context history.

### 8.2 Context detail retrieval
When needed, the model may request:
- `needed_context_detail_ids`

The system then supplies the requested detail records.

### 8.3 Broader context expansion
When the current working memory is not enough, the model may request:
- `needed_more_context_summary_query`

This allows retrieval of older or broader context summaries.

### 8.4 Retrieval boundary
Context detail retrieval is a system-internal controlled operation. It is not exposed as a normal end-user tool call and should not be treated as ordinary runtime tool usage.

---

## 9. Repo / Upgrade / Acceptance Self-Awareness

A complete app-delivery system must know how to finish its own work.

The system therefore needs reusable structured self-awareness in four areas.

### 9.1 Repo awareness
The system must know:
- active repo path
- primary README or project docs
- relevant module or file paths
- where the current change belongs

### 9.2 Upgrade awareness
The system must know:
- how to build or install changes
- how to activate or reload them
- how to restart when required
- how to roll back when activation fails

### 9.3 Runtime identity awareness
The system must know:
- whether it is acting as app, asset, workflow, or system component
- current version / source / installed status when relevant
- runtime/lifecycle posture of the current target

### 9.4 Acceptance awareness
The system must know:
- which tests or probes to run
- which HTTP surfaces or runtime states to verify
- which outcomes are sufficient to count as closure

These facts should be persisted back into workflow state and context events rather than being left as one-off conversational reasoning.

---

## 10. Context Center Final Positioning

Context Center is the **system-level working-memory and recovery substrate** for AgentSystem.

It is shared by:
- chat / gateway flow
- app internal execution
- workflow execution
- governance / self-iteration
- acceptance and regression validation
- continuation recovery

Context Center is **not** the source of truth for:
- lifecycle state
- runtime state
- asset binding truth
- large debug traces

Those remain the responsibility of runtime, lifecycle, asset, and log-specific modules.

---

## 11. Context Center Minimal Event Model

The Context Center detail layer uses an intentionally minimal event schema.

Each detail event contains only:
- `timestamp`
- `role`
- `message`

`session_id` is carried by storage location and query surface rather than embedded as a payload field in the minimal design.

### 11.1 Role rules
`role` directly encodes the event source identity. Canonical role forms are:
- `user`
- `system`
- `<tool_name>`
- `<asset_name>`

This phase does not add separate `kind`, `source_type`, `source_id`, or rich meta envelopes into the detail event schema.

### 11.2 Message rules
`message` is a plain string.

Rules:
- each event should express one main fact or one main output when practical
- no complex structured payload is required in the detail layer
- no extra meta is required in the detail layer

This keeps Context Center lightweight and aligned with the current file-based system style.

---

## 12. Context Center Storage Layout

Context Center storage is partitioned first by session, then by day.

### 12.1 Detail store
- `context/detail/<session_id>/YYYY-MM-DD.jsonl`

### 12.2 Summary store
- `context/summary/<session_id>/YYYY-MM-DD.jsonl`

### 12.3 Parent/child sessions
Parent-child session relationships are not duplicated into every event. Existing session mapping logic remains the authoritative place for those relationships.

---

## 13. Sliding Window Write and Recovery Mechanism

### 13.1 Write path
When an event arrives:
1. persist it into a temporary durable buffer file first
2. enqueue it into the in-memory priority queue
3. place it into the session-local sliding reorder window
4. sort within the window
5. flush stable events into the formal detail file
6. generate a provisional summary immediately
7. asynchronously replace that provisional summary with an LLM-produced finalized summary

### 13.2 Durable buffer
The temporary buffer exists for:
- crash recovery
- restart recovery
- not-yet-stable waiting events

Implementation may use a ring-buffer file.

### 13.3 Session-local sorting window
The window spans 5 minutes total:
- first 2 minutes are treated as the stable zone
- last 3 minutes remain waiting for possible late-arriving inserts

### 13.4 Recovery on startup
Before the service is considered available, it must:
1. load the durable temporary buffer
2. reconstruct the in-memory queue
3. reorder the buffered events
4. flush stable events into formal detail storage
5. preserve the remaining waiting zone
6. enter ready state only after recovery completes

### 13.5 Availability rule
Context Center is not considered ready until startup recovery completes.

---

## 14. Recent Working Memory View

The default model-facing working-memory view is built from recent context.

### 14.1 Default amount
The default read is:
- the most recent 300 events

### 14.2 Stable + pending composition
Recent working memory includes both:
- `stable` events already flushed to formal files
- `pending` events still inside the reorder window

Therefore:
- recent view = stable + pending

### 14.3 Structured response
Recent context APIs must distinguish stable and pending in the returned structure. They must not silently flatten the two classes into one undifferentiated list.

### 14.4 Cross-day reading
Recent event queries must read across date files when necessary and must operate in session-global reverse chronological order. They must not assume that reading only the current day file is sufficient.

---

## 15. Summary Layer and Working Memory View

The summary layer is not merely a convenience compression file. It is the default **working memory view** for the model.

### 15.1 Two-layer structure
- detail layer stores raw context events
- summary layer stores compact working-memory summaries derived from those events

### 15.2 Provisional summary on write
When a detail event is formally flushed, the system should immediately write a provisional summary so summary view remains available without waiting for LLM latency.

### 15.3 Async finalized summary replacement
A single background summary worker then calls the LLM and directly replaces the provisional summary with the finalized summary.

Rules:
- only the current effective summary is kept
- old provisional summaries are not retained as historical versions
- the summary worker is single-threaded and rate-limited to 1

---

## 16. Summary Prompt Rules

Summary quality is system-critical because summary is the default working memory.

### 16.1 Short records
For short records:
- summary should prefer the original text
- only light cleanup is allowed

### 16.2 Long records
For long records, the summary must answer only:
1. what was done
2. what the result was

### 16.3 Hard prompt constraints
Summary prompts must explicitly forbid:
- inventing new facts
- turning attempts into confirmed outcomes
- turning partial success into full completion
- adding conclusions not supported by the source event

---

## 17. Context Center as a System-Level Substrate

The final design goes beyond simple chat support.

### 17.1 Workflow hooks
Workflow transitions must write context through fixed hooks.

### 17.2 Acceptance writes
Acceptance results must be written into Context Center automatically, not only into test logs or stdout.

### 17.3 App consumption
Apps, workflows, and runtime components should be able to query their own recent working memory and details when needed. Context Center is not reserved for only the top-level controller.

### 17.4 Governance and self-iteration convergence
Governance, regression observation, live observation, and self-iteration should share the same context memory line where appropriate rather than developing a completely separate context history mechanism.

### 17.5 Continuation recovery dual-source rule
Continuation recovery should use both:
- `PendingTask`
- recent Context Center working memory

This makes continuation more robust than relying on one state holder alone.

### 17.6 Runtime bootstrap as first-class bundle
Context Center should be wired in `build_runtime` as explicit first-class components, for example:
- `context_center`
- `context_writer`
- `context_summary_worker`
- `context_recovery_manager`
- `context_query_service`

It must not remain a scattered helper pattern.

---

## 18. Logging and VLLM I/O Positioning

### 18.1 Log Center responsibility
Log Center remains the home for:
- debugging
- auditing
- trace-level diagnosis
- full prompt / full result investigation

### 18.2 VLLM input/output
Full VLLM input and output should be uploaded asynchronously to the log center for observability and postmortem analysis.

### 18.3 What does not belong in Context Center
The following should not be dumped into Context Center detail by default:
- full prompt payloads
- large raw traces
- bulky low-level debug logs

Context Center stores reusable working context, not every low-level diagnostic artifact.

---

## 19. Default Turn and Context Budget Direction

The next-stage workflow and continuation model should no longer assume tiny loop limits.

### 19.1 Turn budget
For complex self-iteration and implementation workflows, the design target is:
- default `max_turns >= 24`

### 19.2 Default context read budget
Default recent working memory:
- 300 recent events

### 19.3 Expansion behavior
Only when the model explicitly asks for more should the system fetch:
- more context summaries
- more context details
- more asset summaries
- more asset details

---

## 20. Explicitly Deferred Scope

This phase intentionally does not require:
- rich detail-event schemas
- detail-layer structured meta
- default global deduplication
- summary version history
- parent-child session duplication inside each event
- exposing detail retrieval as a normal tool call
- default advanced ranking or complex relevance selection

These can be added later if operational evidence justifies them.

---

## 21. Accepted Tradeoffs

This final design intentionally accepts the following tradeoffs for the current phase:
1. recent 300 events are not guaranteed to be the globally best 300 events
2. detail-layer string events are weaker for direct programmatic filtering
3. the current phase does not perform default deduplication
4. pending events are visible in recent working memory and therefore require explicit stability signaling
5. role names directly encode tool/asset identities and therefore need naming stability
6. summary quality meaningfully shapes overall reasoning quality

These tradeoffs are acceptable for this phase because they preserve simplicity and implementation momentum while keeping the architecture coherent.

---

## 22. Implementation Hard Requirements

The following are mandatory implementation rules for this phase:
1. session-local writes must be serialized
2. recent view must expose both stable and pending content
3. Context Center cannot become ready before recovery completes
4. recent queries must support cross-day global reverse-order reads
5. formal detail flush must immediately produce a provisional summary
6. summary replacement must run on a single worker with limit 1
7. the durable ring buffer must be sized to cover worst-case window pressure
8. short-record summaries must stay near-verbatim and long-record summaries must only answer what was done and what result was obtained
9. workflow stage transitions must write context via fixed hooks
10. acceptance results must automatically enter Context Center

---

## 23. Compatibility with the Current AgentSystem

This design is fully compatible with the current direction of AgentSystem as a stateful persistent App OS.

It does not replace:
- App OS fundamentals
- draft continuation
- asset/session-binding foundations
- existing HTTP entry surfaces
- file-based persistence style
- session mapping logic

Instead, it unifies and extends them into a coherent next stage that supports:
- complete workflow closure
- system-level working memory
- controlled summary/detail retrieval
- stronger continuation recovery
- real repo / upgrade / acceptance self-awareness

---

## 24. Final Design Summary

AgentSystem next-stage design should be understood as follows:

It remains a stateful persistent App OS built on the current runtime, gateway, pending-task, and HTTP surfaces, but it grows a formal workflow stage model, controlled context and asset summary/detail retrieval, repo/upgrade/acceptance self-awareness, and a system-level Context Center that stores minimal session-scoped events with durable buffering, sliding-window ordering, provisional-to-final summary replacement, and stable-plus-pending working memory views.

That combination forms the final compatible baseline for full self-iteration closure.
