# Phase R Proposal Seed

## Purpose

This document captures the immediate next-step proposal after Phase Q closure.
It is not a full implementation plan yet. Its role is to define the most natural next phase boundary so development can continue without reopening Phase Q.

Detailed rollout task list:
- `docs/phase-r-detailed-task-list.md`

## Why a new phase is needed

Phase Q already closed the workflow/context convergence baseline:
- workflow stages exist beyond draft-only bootstrap
- Context Center runtime storage/recovery exists
- summary-first working memory exists
- workflow hooks and continuation recovery exist
- HTTP and service-up closure are green

The next work should therefore move from **foundation convergence** to **runtime execution closure**.

## Proposed Phase R focus

### 1. Action execution closure beyond draft bootstrap
Broaden the real executable action path for the actions that Phase Q formalized but mostly represented as workflow contract/state progression:
- `approve_solution_draft`
- `revise_solution_draft`
- `materialize_task_list`
- `locate_repo_context`
- `implement_app_change`
- `upgrade_app_runtime`
- `run_acceptance`

Goal:
- these actions should not only exist as workflow-state hints
- they should become first-class executable runtime operations with bounded deterministic behavior where possible

### 2. Repo / implementation / acceptance runtime binding
Strengthen the bridge between pending-task workflow state and the real project/runtime world:
- repo context should be materialized from actual repository inspection
- implementation targets should resolve to concrete files/modules
- acceptance plans should produce concrete commands / probes / results

### 3. Evidence-backed execution and closure
The next phase should keep the Phase Q governance posture:
- summary-first by default
- bounded detail retrieval
- explicit acceptance evidence
- no silent upgrade from hints to verified implementation claims

But extend it into execution closure so a workflow can move from:
- proposed work
- to concrete file changes / runtime actions
- to explicit acceptance output
- to persisted acceptance evidence

## Progress update after initial execution waves

The first bounded execution waves are now partially landed:
- `approve_solution_draft`
- `revise_solution_draft`
- `materialize_task_list`
- `locate_repo_context`
- `implement_app_change`
- `run_acceptance`

Current posture:
- these actions now have executable skeleton behavior and structured payload returns
- the chain is deterministic and bounded, but still represents workflow-oriented closure rather than fully general autonomous implementation
- the real `/api/action` HTTP surface now has bounded live-chain coverage from task-list preparation through acceptance completion
- next expansion should deepen execution truth and evidence quality, not reopen Phase Q foundations

## Suggested first wave for Phase R

### Wave 1: executable repo-context and acceptance planning
Start with the lowest-risk, highest-leverage runtime closures:
- make `locate_repo_context` executable against the actual repository
- materialize acceptance plans into explicit commands / probes / criteria
- persist those acceptance results back into workflow state + Context Center

Why this first:
- it builds on Phase Q structures directly
- it avoids premature broad mutation execution
- it improves real closure quality for later implementation / upgrade waves

## Entry criteria

Phase R should start only if the team agrees to treat Phase Q as closed and avoid reopening its foundation scope except for bug fixes.
