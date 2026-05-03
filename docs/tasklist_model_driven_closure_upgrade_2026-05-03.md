# Engineering Tasklist: Model-driven Closure Upgrade (2026-05-03)

## Goal
Implement the interaction-closure upgrade on top of the current AgentSystem framework, without falling back to scenario-specific hardcoding.

This tasklist is derived from:
- `docs/partial-scenario-grouping-and-solution-plan-2026-05-03.md`
- `docs/interaction-record-problem-analysis-2026-05-03.md`
- `docs/50-scenario-interaction-review-2026-05-03.md`
- full 50-scenario user-level E2E results

---

## Phase 1. Pending Task + Draft-First Core

### 1.1 Pending task domain model
- [ ] Add `PendingTaskRecord` model
- [ ] Define fields:
  - [ ] `task_id`
  - [ ] `user_id`
  - [ ] `session_id`
  - [ ] `intent`
  - [ ] `status`
  - [ ] `draft_payload`
  - [ ] `target_ref`
  - [ ] `known_facts`
  - [ ] `missing_fields`
  - [ ] `next_recommended_action`
  - [ ] `last_user_message`
  - [ ] `created_at`
  - [ ] `updated_at`
- [ ] Add serialization tests for the task model

### 1.2 Pending task persistence service
- [ ] Add `PendingTaskStore` or extend the existing context/persistence layer with pending-task namespace support
- [ ] Add create / update / read-latest-open-task APIs
- [ ] Add list-open-tasks-by-user API
- [ ] Add mark-completed / mark-abandoned APIs
- [ ] Add persistence tests

### 1.3 Gateway task-context injection
- [ ] Update `LightBrainGateway.receive_message(...)` path to load pending-task context by `user_id`
- [ ] Inject recent pending-task snapshot into the model-facing decision context
- [ ] Inject recent target/entity snapshot into the same decision context
- [ ] Add tests for no-task / one-open-task / multiple-task selection paths

### 1.4 Model-driven task continuation decision
- [ ] Add structured output model, e.g. `TaskContinuationDecision`
- [ ] Support conversation modes:
  - [ ] `clarify`
  - [ ] `draft_create`
  - [ ] `continue_task`
  - [ ] `execute`
  - [ ] `report_status`
- [ ] Add decision parser / validator
- [ ] Update interaction path so the model selects next action from structured world state, rather than hardcoded “继续/开始执行” branches
- [ ] Add tests for continuation decision parsing and fallback

### 1.5 Draft-first proposal generation
- [ ] Extend intent/requirement routing to emit `draft_proposal` instead of only `missing_fields`
- [ ] Add model prompt context for default-name / default-type / default-goal proposal generation
- [ ] Add schema validation for generated draft proposals
- [ ] Add tests for partially specified creation requests

### 1.6 Draft app object creation
- [ ] Extend app/application service to support `draft` status objects
- [ ] Allow create flow to persist a draft object before full configuration is known
- [ ] Return stable handle (`app_id` / `target_id`) for draft objects
- [ ] Add tests proving draft objects survive follow-up interactions

---

## Phase 2. Stable Target Identity + Lifecycle Truth

### 2.1 Canonical target reference model
- [ ] Add canonical `target_id` / `app_id` reference model for user-visible objects
- [ ] Add alias support (`display_name`, historical names, generated aliases)
- [ ] Add lookup tests for alias → canonical target resolution

### 2.2 Rename and alias persistence
- [ ] Ensure rename operations update canonical display name while preserving aliases
- [ ] Ensure subsequent natural-language references resolve to the same target
- [ ] Add rename-followed-by-stop/delete/query regression tests

### 2.3 Lifecycle execution by canonical ID
- [ ] Update create/start/stop/delete/query flows to execute against canonical IDs once the target is grounded
- [ ] Prevent lifecycle follow-ups from degrading back to free-text ambiguity when confidence is high
- [ ] Add tests for explicit target continuation (`停止它`, `删除这个`, `继续刚才那个`)

### 2.4 Truth-based status confirmation
- [ ] Add a status confirmation adapter that reads from actual runtime/persistence truth before replying success/failure
- [ ] Prevent the assistant from confirming lifecycle completion from conversational assumption alone
- [ ] Add tests for:
  - [ ] created but not started
  - [ ] started and later stopped
  - [ ] rename reflected in status queries
  - [ ] delete reflected in truth layer

---

## Phase 3. Query Fast-Path + Read Models

### 3.1 Read-fast-path intent classification
- [ ] Add query-fast-path classifier for count/status/list/read-only requests
- [ ] Support examples like:
  - [ ] `有多少次请求记录？`
  - [ ] `当前有哪些App？`
  - [ ] `它现在运行了吗？`
  - [ ] `有多少个用户？`
- [ ] Add tests for routing into fast-path instead of heavy orchestration

### 3.2 Operational read model facade
- [ ] Add a read facade, e.g. `OperationReadModel`
- [ ] Implement helper surfaces:
  - [ ] `get_app_runtime_state(...)`
  - [ ] `get_draft_state(...)`
  - [ ] `get_recent_request_count(...)`
  - [ ] `get_latest_operation_result(...)`
  - [ ] `get_user_open_tasks(...)`
- [ ] Add tests for deterministic query answers

### 3.3 Audit/log count optimization
- [ ] Add cheap path for audit/log count queries
- [ ] Ensure S15-style “有多少次请求记录？” avoids heavy reasoning/tool fanout
- [ ] Add timeout regression test for this exact query family

---

## Phase 4. Response Policy + Closure Semantics

### 4.1 Closure-aware response shaping
- [ ] Add final response shaping layer that binds user-visible reply to actual execution result
- [ ] Prefer short operational closure form:
  - [ ] what was done
  - [ ] current real state
  - [ ] what is still missing
  - [ ] next default step
- [ ] Reduce overuse of scaffold-heavy “当前结论建议做轻量验证” wrappers on execution paths

### 4.2 Separate response success from goal closure success
- [ ] Extend user-level E2E result schema with:
  - [ ] `transport_success`
  - [ ] `response_success`
  - [ ] `execution_success`
  - [ ] `goal_closure_success`
  - [ ] `closure_reason`
- [ ] Add report generation tests for the expanded schema

### 4.3 Closure-aware scenario assertions
- [ ] Add closure assertions for lifecycle-heavy scenarios
- [ ] Add closure assertions for continuation-heavy scenarios
- [ ] Add closure assertions for draft-create flows

---

## Phase 5. Logging and Run Isolation

### 5.1 Add run identifier to chat logs
- [ ] Add `run_id` field to test-generated session logs
- [ ] Ensure repeated E2E runs can be segmented cleanly
- [ ] Add tests for run isolation in chat-log persistence

### 5.2 Improve scenario-to-log correlation
- [ ] Add scenario_id metadata in test-user records when generated by E2E runner
- [ ] Make post-run forensic analysis able to isolate a single scenario without reused-session ambiguity

---

## Phase 6. Regression Validation

### 6.1 Targeted regression for known weak points
- [ ] Re-run and harden:
  - [ ] S05 creation timeout path
  - [ ] S06 lifecycle truth path
  - [ ] S07 modify/stop path
  - [ ] S08 delete/rebuild path
  - [ ] S15 audit count path
  - [ ] real-user-style “继续 / 开始执行 / 结合之前记录继续” path

### 6.2 Full-suite validation
- [ ] Re-run full 50-scenario × 20-turn user-level E2E suite
- [ ] Compare against baseline:
  - [ ] scenario pass count
  - [ ] turn pass count
  - [ ] timeout count
  - [ ] partial-closure count
  - [ ] goal-closure count

---

## Suggested module touch points
Likely files / areas to modify:
- `app/system/gateway/light_brain_gateway.py`
- `app/services/intent_router.py`
- `app/services/requirement_router.py`
- `app/services/app_context_store.py` or adjacent persistence service
- `app/services/...` pending-task store module (new)
- `app/services/app_application_service.py`
- `app/system/catalog/runtime_center.py`
- `app/system/asset_center/...`
- response shaping / final answer adapter path
- `tests/e2e/test_50_scenarios_20_turns_user_level.py`

---

## Delivery order recommendation
### First implementation slice
- Phase 1.1 ~ 1.6
- Phase 2.1 ~ 2.4 (minimal viable canonical target and truth confirmation)

### Second implementation slice
- Phase 3.1 ~ 3.3
- Phase 4.1 ~ 4.3

### Third implementation slice
- Phase 5.1 ~ 5.2
- Phase 6 full regression rerun

---

## Definition of done
This upgrade should be considered complete only when:
- partially specified create requests produce draft objects instead of endless clarification
- `继续 / 开始执行 / 结合之前记录继续` can resume pending work
- lifecycle confirmations reflect truth layer state instead of conversational guesswork
- query-style read operations avoid pathological latency
- future 50-scenario runs show a much smaller gap between pass rate and goal-closure rate
