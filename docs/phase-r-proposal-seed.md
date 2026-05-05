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

The first bounded execution waves are now landed for the initial rollout arc:
- `approve_solution_draft`
- `revise_solution_draft`
- `materialize_task_list`
- `locate_repo_context`
- `implement_app_change`
- `run_acceptance`

Current posture:
- these actions now have executable skeleton behavior and structured payload returns
- repo-context truth, implementation-plan truth, acceptance-evidence truth, and HTTP/runtime surfacing all have bounded landed coverage
- a second bounded extension layer has started, linking changed-file intent, validation mapping, and acceptance evidence back to work-item identifiers
- the richer binding shape is now also reflected in canonical pending-task defaults, top-level `acceptance_plan.evidence_summary`, and orchestrator acceptance-summary persistence
- the chain remains deterministic and bounded, and still represents workflow-oriented closure rather than fully general autonomous implementation
- the real `/api/action` HTTP surface now has bounded live-chain coverage from task-list preparation through acceptance completion, with richer payload assertions on repo, implementation, changed-file intent, and acceptance evidence fields
- next expansion should continue deepening mutation/evidence binding on top of this baseline instead of reopening Phase Q foundations

## Initial rollout arc completion

The first bounded rollout arc of Phase R should now be treated as complete:
- Wave 1: repo-context truth upgrade, completed
- Wave 2: implementation-plan truth upgrade, completed
- Wave 3: acceptance-evidence truth upgrade, completed
- Wave 4: operator and HTTP surface hardening, completed

Implication:
- future Phase R work should extend the execution closure baseline rather than re-proving the same first-wave chain

## Suggested next wave for Phase R

### Wave 5: real mutation and evidence-to-change binding
Start with the next bounded closure layer above the current baseline:
- connect implementation work items more explicitly to concrete changed-file intent
- bind acceptance evidence to those implementation work items more directly
- keep execution bounded and inspectable, without broad autonomous mutation

Why this next:
- the first arc already proved workflow action closure and HTTP surfacing
- the next missing truth is the bridge between implementation intent and actual change evidence
- it advances runtime usefulness without reopening Phase Q or over-expanding autonomy

Immediate open slice within this wave:
- derive changed-file intent from repo inspection plus task-list hints more explicitly
- improve multi-command evidence-to-work-item mapping beyond the current single-work-item fallback
- evaluate whether a compact operator-facing changed-file/result summary read model is warranted

## Entry criteria

Phase R should start only if the team agrees to treat Phase Q as closed and avoid reopening its foundation scope except for bug fixes.
