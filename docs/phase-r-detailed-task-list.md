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
- strengthen `run_acceptance` result storage so each result captures:
  - command
  - exit code
  - bounded stdout/stderr excerpts
  - pass/fail status
  - timestamp
  - optional mapped success criteria ids when available

### 6.2 Validation
- add focused tests for:
  - multi-command result aggregation
  - failure retry posture
  - evidence normalization shape

## 7. Wave 4: Operator / HTTP Surfaces

### 7.1 Runtime surfacing
- ensure the richer repo / implementation / acceptance payloads remain stable on:
  - gateway action replies
  - `/api/action`
  - service-up and regression-friendly probes where practical

### 7.2 Validation
- expand real HTTP action slices when new payload fields become stable

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
