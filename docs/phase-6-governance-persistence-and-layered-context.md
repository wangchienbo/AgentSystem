# Phase 6 / Governance, Production Persistence, and Layered Context

## 1. Purpose

Phase 6 turns the system from a strong prototype into a more durable and governable runtime substrate.

By this point, the platform should already have:
- richer workflow execution
- refinement/materialization/app-assembly closure
- risk governance foundations
- rollout/release operator surfaces

The next limiting factors are then:
- policy/permission depth
- persistence durability and restart/recovery correctness
- context growth and retrieval discipline

Phase 6 addresses those limits directly.

---

## 2. Main goals

Phase 6 should provide:
- stronger permission/policy boundaries for apps, skills, prompts, and risky operations
- more production-oriented persistence/recovery posture
- a real layered context architecture that keeps runtime intelligence bounded and inspectable

---

## 3. Deliverables

### 3.1 Permission and policy model expansion

The system already has risk governance and selected policy hooks.
Phase 6 should evolve this into a clearer multi-scope permission/policy system.

At minimum, policy should be able to govern:
- app install / activate / rollback
- skill materialization / activation / override
- risky generated app assembly
- prompt invocation
- network use
- filesystem write / shell behavior
- automatic vs reviewer-required rollout
- telemetry/upgrade-evidence collection posture

Desired policy scopes:
- global
- app
- skill
- workflow/module-step type
- refinement/materialization scope
- reviewer override scope

### 3.2 Reviewer and authority boundaries

The system should make reviewer authority explicit.

Required capabilities:
- who can approve risky materialization
- who can activate staged revisions/releases
- what actions require explicit reviewer identity and reason
- what actions remain read-only/operator-only vs mutation-authorized

The immediate goal is not enterprise IAM complexity, but explicit inspectable authority boundaries.

### 3.3 Production-grade persistence strategy

Current file-based persistence is good for the prototype, but Phase 6 should define and implement a stronger durability path.

Required areas:
- persistence adapter abstraction or backend layering
- stronger snapshot/log consistency rules
- restart/rebuild correctness for app/runtime/refinement/governance state
- clearer quarantine/corruption handling
- migration-friendly contracts for future DB-backed persistence

Suggested persistence boundary split:
- online runtime state
- operator/governance state
- append-only evidence/log state
- large/generated skill assets

### 3.4 Recovery correctness and replay boundaries

The system should distinguish:
- recover current runtime state
- reload persisted managed assets
- replay or inspect historical evidence
- recover blocked/manual/event-wait executions

Recovery should be explainable and bounded:
- what was restored
- what remained unresolved
- what requires revalidation/restart

### 3.5 Layered context implementation

The current docs already define layered context direction.
Phase 6 should make it operational.

Required layers:
- **L0 working set**
- **L1 compact summary**
- **L2 execution detail**
- **L3 promoted long-term experience/evidence**

Required capabilities:
- derive/update working set automatically
- compact on workflow completion/failure/stage change under policy
- preserve decisions / constraints / artifacts / open loops
- retrieve deeper context selectively by reference
- expose prompt-ready context from L0 + selected L1/L3 instead of raw history

### 3.6 Context-policy and retrieval contracts

Layered context should not be “just summaries”; it needs policy and retrieval rules.

Required behavior:
- configurable compaction triggers
- configurable budget/selection hints
- retrieval by app/workflow/failure/artifact reference
- operator inspection of what context was compacted vs retained
- compatibility with prompt-selection and evidence-promotion services

### 3.7 Governance observability

As governance and context become more complex, operator surfaces must stay coherent.

Expected dashboard/read-model growth:
- policy summary by scope
- override queue / approvals / revocations
- persistence health / corruption / quarantine summary
- context summary counts and latest compaction state
- unresolved blocked/manual/event-wait recovery summary

---

## 4. Service/module plan

Expected code areas:
- `app/services/collection_policy_service.py`
- `app/services/skill_risk_policy.py`
- `app/services/runtime_state_store.py`
- `app/services/prompt_selection_service.py`
- `app/services/app_context.py`
- `app/services/...context compaction services...`
- `app/models/...policy models...`
- `app/models/...context summary models...`
- `app/api/main.py`

Possible new services:
- `app/services/policy_authority_service.py`
- `app/services/persistence_backend.py`
- `app/services/context_compaction_service.py`
- `app/services/context_retrieval_service.py`
- `app/services/persistence_health_service.py`

---

## 5. Test plan

### 5.1 Policy/permission tests
- scoped policy resolution
- reviewer-required actions reject missing reviewer identity
- risky operations remain blocked without override
- prompt/network/filesystem/shell permissions remain inspectable

### 5.2 Persistence/recovery tests
- rebuild runtime from persisted state across app/runtime/refinement/governance assets
- corruption/quarantine handling does not break bootstrap
- backend abstraction preserves existing service contracts
- unresolved executions remain recoverable/inspectable after restart

### 5.3 Layered context tests
- working set derivation from app context + recent execution
- auto compaction on completion/failure/stage change
- retrieval of detail by reference
- prompt/context selection prefers compact layers over raw execution history
- evidence promotion links remain preserved through compaction

### 5.4 Operator/API tests
- policy summary and override surfaces
- persistence health summary
- context layer inspection and compaction history
- blocked/manual/event-wait recovery visibility after restart

---

## 6. Acceptance criteria

Phase 6 is complete when:
- policy/permission boundaries are more explicit and test-covered
- persistence/recovery behavior is durable enough for longer-lived operation
- layered context is an implemented runtime feature rather than a design note only
- operator surfaces can explain policy, persistence health, and context state coherently

---

## 7. Recommended implementation order

1. policy/authority expansion
2. persistence backend and health/recovery hardening
3. layered context compaction implementation
4. layered retrieval + prompt/evidence integration
5. operator/dashboard alignment
6. docs + tests + development log update
