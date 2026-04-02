# Phase 5 / Suggested Skill -> App Refinement Closure

## 1. Purpose

Phase 5 closes the gap between:
- observed runtime practice
- suggested reusable capabilities
- materialized skills
- assembled apps
- install/run/rollout behavior

The system already has many of the individual pieces:
- practice review
- experience store
- skill suggestion
- blueprint materialization
- generated skill creation
- generated app assembly
- risk governance
- rollout/operator surfaces

The remaining gap is orchestration.

Phase 5 is therefore about building a coherent refinement-and-assembly closure, not inventing a wholly new subsystem.

---

## 2. Core design intent

The platform should support a governed path that can:
1. inspect runtime experience
2. derive candidate skill blueprints
3. materialize missing skills when appropriate
4. assemble those skills into an app blueprint or app revision
5. validate the result
6. install/run it in a bounded way
7. expose rollout/governance state for review

This should remain evidence-bound and policy-aware.

Suggestion is still not silent mutation.

---

## 3. Main gaps to close

Current partial capabilities already exist, but are fragmented:
- suggestion and materialization are separated
- app assembly is available but not naturally tied to suggested skills
- proposal/refinement objects exist but do not yet provide a one-call refinement-to-app path
- operator surfaces can inspect pieces, but not one coherent refinement closure

Phase 5 should close that fragmentation.

---

## 4. Deliverables

### 4.1 Suggested-skill materialization orchestration

Add a higher-level orchestration path that can:
- take one or more suggested `SkillBlueprint` records
- determine which are already materialized vs missing
- materialize missing ones through the existing governed blueprint-materialization path
- preserve governance-aware defaults and policy diagnostics

This should not bypass:
- risk policy
- materialization overrides
- manifest validation
- runtime smoke tests

### 4.2 App refinement from suggested skills

Add a first-class app refinement flow that can:
- take an existing app or a refinement proposal
- incorporate suggested/materialized skills
- produce either:
  - a refined app blueprint draft
  - a staged app release candidate
  - a generated app blueprint for install/run validation

The result should preserve:
- changed required skills
- changed runtime profile
- changed app shape
- refinement evidence links

### 4.3 One-call refinement closure API

The platform should expose a one-call orchestration path that can perform, in a governed sequence:
- select suggestions
- materialize missing skills
- assemble/refine app blueprint
- validate
- optionally install
- optionally execute smoke path
- return structured diagnostics and rollout-ready metadata

The API must return:
- what was reused vs newly materialized
- what policy blocks happened
- what app shape/runtime profile changed
- what rollout/reviewer action is still needed

### 4.4 Refinement governance linkage

Refinement/operator surfaces should evolve so that app refinement is not separate from refinement memory/governance.

Required linkage:
- refinement proposal links to suggested skill ids / blueprint ids
- refinement verification links to materialized skill versions when applicable
- rollout queue items can point to refined app release candidates
- dashboards can summarize refinement -> materialization -> app-assembly progression

### 4.5 Release candidate and comparison support

When app refinement produces a new app candidate, the control plane should treat it as an operator-visible candidate rather than a hidden intermediate.

Required behavior:
- refined app candidate can be staged as a draft release or explicit candidate object
- compare surfaces show changed skills/runtime policy/runtime profile/app shape
- install/run validation can happen before activation

### 4.6 Diagnostics and retryability

The refinement closure path must return structured diagnostics rather than coarse failure strings.

Examples:
- suggestion insufficient
- materialization blocked by policy
- materialization failed smoke test
- assembly wiring unresolved
- install failed
- smoke execution partial/failed

Each should ideally include:
- stage
- kind
- structured details
- suggested correction or retry payload when possible

---

## 5. Service/module plan

Expected code areas:
- `app/services/skill_suggestion.py`
- `app/services/skill_factory.py`
- `app/services/refinement_loop.py`
- `app/services/proposal_review.py`
- `app/services/app_registry.py`
- `app/services/app_installer.py`
- `app/models/refinement_loop.py`
- `app/models/skill_creation.py`
- `app/models/registry.py`
- `app/api/main.py`

Possible new services:
- `app/services/app_refinement_orchestrator.py`
- `app/services/suggested_skill_materializer.py`
- `app/services/refinement_release_builder.py`

---

## 6. API plan

Potential new/extended endpoints:
- refine app from selected suggestions
- materialize-and-assemble from suggestion ids
- optionally install/run refined candidate
- list refinement-linked app candidates or release candidates
- compare current app vs refined candidate

These should compose with existing registry/release surfaces rather than replace them.

---

## 7. Test plan

### 7.1 Service tests
- suggestion ids -> missing skills materialized -> app blueprint assembled
- existing materialized skills are reused instead of duplicated
- policy-blocked suggestions return structured diagnostics
- refined app candidate records changed runtime profile/app shape

### 7.2 API tests
- one-call refinement closure returns materialization + assembly + validation outputs
- optional install/run path returns execution diagnostics without losing candidate metadata
- compare surfaces reflect refined candidate drift

### 7.3 Golden path tests
- runtime experience -> suggestion -> materialize -> assemble -> install -> execute
- existing app -> refinement proposal -> refined release candidate -> compare -> activate/rollback

---

## 8. Acceptance criteria

Phase 5 is complete when:
- suggested skills can flow into materialized skills through one governed orchestration path
- refined app candidates can be assembled from those skills without manual stitching
- operator surfaces can inspect refined candidate differences clearly
- optional install/run validation exists for refined candidates
- diagnostics remain structured and retry-friendly

### 8.1 First implemented closure slice

This round implements the first executable Phase-5 closure slice:
- one-call refinement closure API at `/apps/refine-from-suggested-skills/closure`
- orchestration from selected suggested skill blueprints -> materialize missing skills -> assemble app blueprint -> register candidate -> create draft release -> optional install/run
- closure result now returns:
  - selected blueprints
  - created/materialized skill ids
  - reused skill ids
  - generated blueprint + app assembly result
  - draft release metadata
  - compare summary for the refined candidate
  - optional install result
  - optional workflow execution result
  - structured diagnostics for non-completed execution validation

Still pending for deeper Phase-5 follow-up:
- tighter integration with proposal/refinement-memory objects
- richer release comparison against prior active versions instead of current lightweight compare summary
- stronger policy-block/materialization-diagnostics coverage across more risk variants
- rollout queue/dashboard linkage for refined candidates

---

## 9. Recommended implementation order

1. suggested-skill materialization orchestration
2. app refinement candidate builder
3. one-call refinement closure API
4. refinement governance linkage and dashboard updates
5. release compare/install-run alignment
6. docs + tests + development log update
