# Phase R Detailed Task List

## 1. Purpose

This document converts the current Phase R proposal seed into an implementation-oriented rollout list.

Phase R starts after Phase Q closure and after the first bounded executable workflow chain has already landed in skeleton form.

Companion references:
- `docs/phase-r-proposal-seed.md`
- `docs/phase-q-completion-summary.md`
- `docs/phase-q-workflow-context-center-final-design.md`

## 2. Current Starting State

Already landed before this task list:
- `approve_solution_draft`
- `revise_solution_draft`
- `materialize_task_list`
- `locate_repo_context`
- `implement_app_change`
- `run_acceptance`
- bounded live `/api/action` workflow-chain coverage through acceptance completion

Phase R therefore should not re-implement the chain skeleton. It should deepen execution truth, evidence quality, and runtime usefulness.

## 3. Delivery Strategy

Recommended bounded rollout order:
1. strengthen repo-context truth
2. strengthen implementation-plan truth
3. strengthen acceptance evidence truth
4. connect workflow outcomes back into durable operator-facing surfaces

## 4. Wave 1: Repo-Context Truth Upgrade

### 4.1 Repo inspection enrichment
Status: [x] completed
- `locate_repo_context` now validates repo-root existence, captures README presence, filters key docs to existing files, normalizes bounded module targets, and records cheap repo facts (`git_branch`, `git_dirty`, `repo_valid`)

### 4.2 Validation
Status: [x] completed
- focused tests cover:
  - missing README fallback handling
  - bounded existing-doc filtering
  - target module normalization
  - cheap git-fact extraction

## 5. Wave 2: Implementation-Plan Truth Upgrade

### 5.1 Structured implementation bundle
Status: [x] completed
- `implement_app_change` now emits structured work items with bounded rationale/source links and a `validation_map` that seeds acceptance probes from the implementation bundle

### 5.2 Validation
Status: [x] completed
- focused tests cover:
  - plan derivation from repo context + task list
  - acceptance probe seeding from implementation bundle

## 6. Wave 3: Acceptance Evidence Upgrade

### 6.1 Evidence normalization
Status: [x] completed
- `run_acceptance` now stores normalized per-command evidence with exit code, bounded stdout/stderr excerpts, timestamp, pass/fail status, and matched success-criteria references, plus aggregate pass/fail counts

### 6.2 Validation
Status: [x] completed
- focused tests cover:
  - multi-command style result normalization shape
  - failure retry posture
  - evidence summary aggregation

## 7. Wave 4: Operator / HTTP Surfaces

### 7.1 Runtime surfacing
Status: [x] completed
- richer repo / implementation / acceptance payloads remain exposed on gateway action replies and `/api/action`, including repo truth, implementation validation mapping, and normalized acceptance evidence summary fields

### 7.2 Validation
Status: [x] completed
- real HTTP action slices now assert the richer payload fields once they stabilize

## 8. Documentation Tasks

### 8.1 Update proposal seed snapshots
- refresh `docs/phase-r-proposal-seed.md` when each wave materially lands

### 8.2 Update testing docs
- keep `docs/testing.md` and `docs/testing-detail.md` aligned with richer execution truth and evidence coverage

### 8.3 Update development log
- append each completed wave with implementation and validation evidence

## 9. Suggested Commit Boundaries

1. `feat: enrich workflow repo context truth`
2. `feat: enrich workflow implementation plan truth`
3. `feat: normalize workflow acceptance evidence`
4. `test: expand workflow action http and evidence coverage`
5. `docs: update phase r execution evidence`

## 10. Initial Acceptance Checklist for Phase R

Phase R should be considered meaningfully underway when:
- repo-context payload is grounded in actual existing repo/doc truth
- implementation plan carries more than placeholder target-file lists
- acceptance evidence is normalized and reusable
- HTTP and gateway surfaces expose the richer payloads without contract drift
- focused tests remain green after each wave

## 11. Next Bounded Extension Layer

### 11.1 Wave 5: Mutation/evidence binding
Status: [x] first slice landed
- `implement_app_change` now carries `changed_files_intent` linked to `mapped_work_item_id`
- `validation_map` now also records `mapped_work_item_id`
- `run_acceptance` now maps command evidence back to `matched_work_item_ids`
- gateway acceptance execution now also promotes aggregate `evidence_summary` back onto the top-level `acceptance_plan`
- canonical pending-task defaults and orchestrator acceptance flows now preserve the richer binding/evidence summary shape

### 11.2 Validation
Status: [x] first slice landed
- focused tests cover changed-file intent exposure and acceptance-evidence to work-item binding on both gateway and real `/api/action` paths
- orchestrator tests cover persisted `evidence_summary` behavior and keep Context Center verification scoped to the lighter event/message contract

### 11.3 Next open slice
Status: [ ] pending
- derive bounded changed-file intent from actual repo inspection plus task-list hints instead of only direct module carry-forward
- allow acceptance evidence to map multiple commands back to distinct work-item ids without relying on the single-work-item fallback
- decide whether a lightweight changed-file/result summary should also surface into a compact operator-facing read model
