# AgentSystem Telemetry / Upgrade-Evidence Implementation Plan

## 1. Purpose

This document turns the telemetry / feedback / upgrade-evidence design into a practical implementation plan.

It exists to answer four questions clearly:
- what should be built first
- what data structures are actually needed
- what should be deferred or reduced for now
- how to keep the design aligned with the project principle of a thin core and skill-centric higher-order behavior

This plan intentionally prefers a buildable first version over a maximal design.

---

## 1A. Terminology used in this plan

This plan uses the following terms with narrow meanings:
- `telemetry`: lightweight online runtime records
- `upgrade-evidence log`: append-only historical evidence for replay/acceptance/optimization
- `evaluation summary`: derived candidate-comparison or acceptance result

These terms should stay aligned with `docs/telemetry-and-upgrade-logging.md`.

---

## 2. Delivery Strategy

The implementation should proceed in phases.

### Phase 1: core substrate only
Build the minimum platform substrate needed to support later skill-driven iteration:
- telemetry models
- lightweight collection service
- version binding
- append-only upgrade-log writer
- collection policy levels (`off | light | medium` initially)
- basic query surfaces

### Phase 2: evaluation substrate
Build the minimum comparison / acceptance substrate:
- candidate evaluation summary model
- basic compare primitives
- cost / latency / success summary aggregation
- release / rollback evidence records

### Phase 2A: core-skill toolchain bootstrap
Before broad autonomous skill growth, establish a small governed core-skill toolchain, such as:
- replay sample selection skill
- cost analysis skill
- acceptance report skill
- candidate comparison skill
- archive summary skill

### Phase 3: skill consumption layer
Use the substrate and core-skill toolchain to support additional ordinary skill generation and governance.

### Phase 4: higher-order automation
Only after the substrate is stable:
- next-version generation skill
- test orchestration skill
- gated publish skill
- rollback orchestration skill

This keeps the system buildable and avoids forcing a large autonomous loop into the core too early.

---

## 3. Phase 1 Scope

## 3.1 Must-build components

### A. Telemetry domain models
Add models for:
- `InteractionTelemetryRecord`
- `StepTelemetryRecord`
- `FeedbackRecord`
- `VersionBindingRecord`
- `CollectionPolicyRecord`

### B. Upgrade-evidence event model
Add a minimal append-only log event envelope, for example:
- `UpgradeLogEvent`
  - `event_id`
  - `ts`
  - `event_type`
  - `scope`
  - `app_id`
  - `skill_id`
  - `agent_id`
  - `interaction_id`
  - `payload`
  - `extension_payload`

### C. Lightweight telemetry services
Expected service families:
- telemetry collection service
- collection policy resolver service
- version binding helper/service
- upgrade-log append writer
- upgrade-log read helper

### D. Basic persistence layout
The first version should be file-backed if that is consistent with current project persistence patterns.

Suggested directories:
- `runtime/telemetry/interactions/`
- `runtime/telemetry/feedback/`
- `runtime/upgrade_logs/interactions/`
- `runtime/upgrade_logs/evaluations/`
- `runtime/upgrade_logs/releases/`

### E. Query surfaces
The first query surfaces should focus on practical value:
- fetch telemetry by interaction id
- list recent interactions for an app
- list recent feedback for an app or skill
- list upgrade-log events in a time window
- list candidate evaluation summaries once Phase 2 begins

---

## 4. Proposed Data Models

## 4.1 InteractionTelemetryRecord
Recommended fields:
- `interaction_id`
- `session_id`
- `user_id`
- `app_id`
- `app_version`
- `agent_id`
- `agent_version`
- `request_type`
- `started_at`
- `ended_at`
- `success`
- `failure_reason`
- `total_input_tokens`
- `total_output_tokens`
- `total_tokens`
- `total_latency_ms`
- `total_tool_calls`
- `strategy_name`
- `collection_level`
- `aborted`
- `retried`
- `escalated`

## 4.2 StepTelemetryRecord
Recommended fields:
- `interaction_id`
- `step_id`
- `parent_step_id`
- `step_type`
- `name`
- `version`
- `started_at`
- `ended_at`
- `input_tokens`
- `output_tokens`
- `latency_ms`
- `success`
- `error_code`
- `retry_count`
- `cache_hit`
- `estimated_cost`

## 4.3 FeedbackRecord
Recommended fields:
- `feedback_id`
- `interaction_id`
- `scope_type` (`app | skill | session | interaction`)
- `scope_id`
- `feedback_kind` (`explicit | implicit`)
- `score`
- `labels`
- `note`
- `created_at`

## 4.4 VersionBindingRecord
Recommended fields:
- `interaction_id`
- `app_version`
- `skill_versions`
- `agent_version`
- `policy_version`
- `evaluation_suite_version`

## 4.5 CollectionPolicyRecord
Recommended fields:
- `scope_type` (`global | app | skill | agent | task_type`)

Note: Phase 1 should actively use only `global | app | skill`, while `agent | task_type` may remain future-facing placeholders if included at all.
- `scope_id`
- `enabled`
- `level` (`off | light | medium | heavy | custom`)
- `capture_feedback`
- `capture_payload_summary`
- `capture_truncated_payload`
- `allow_skill_extension`
- `updated_at`

---

## 5. Upgrade-Log Format

## 5.1 Format choice
Use JSONL for the first implementation.

Reasons:
- append-friendly
- simple to inspect
- easy to stream
- easy to consume from future skills/scripts
- resilient compared with mutating a large JSON array

## 5.2 Rotation policy
First implementation:
- daily file rotation only

Do not implement hourly rotation in Phase 1 unless volume immediately proves it necessary.

## 5.3 File naming
Suggested examples:
- `runtime/upgrade_logs/interactions/2026-03-28.jsonl`
- `runtime/upgrade_logs/evaluations/2026-03-28.jsonl`
- `runtime/upgrade_logs/releases/2026-03-28.jsonl`

## 5.4 Append-only rule
The first implementation should treat historical upgrade logs as append-only files.

Normal runtime paths should not rewrite prior log files in place.

---

## 6. Collection Levels

The implementation should intentionally start smaller than the full conceptual design.

## 6.1 Phase 1 supported levels
Implement first:
- `off`
- `light`
- `medium`

### `off`
- do not record upgrade-evidence logs
- keep only minimal runtime state needed by the existing system

### `light` (default)
- record interaction summaries
- record step summaries
- record token/latency/success/failure totals
- record version binding
- record explicit feedback
- optionally record a small set of implicit signals
- do not store raw full payloads

### `medium`
- everything from light
- add bounded summaries for key steps
- allow truncated payload capture where explicitly supported

## 6.2 Deferred levels
Do not implement in Phase 1 unless clearly needed:
- `heavy`
- `custom`

These should remain as design targets, not mandatory first-delivery scope.

---

## 7. User-Control and Policy Boundaries

The first build should support these policy scopes:
- global
- app
- skill

Agent-level and task-type-level policy may remain as schema placeholders or Phase 2 items if needed.

### 7.1 Default posture
The first implementation should default to:
- enabled = true
- level = `light`
- allow skill extension = true
- truncated payload capture = false

### 7.2 Safe reduction rule
If policy resolution becomes too complex in Phase 1, use a simple precedence order:
- skill override
- app override
- global default

Do not overbuild policy composition before practical usage exists.

---

## 8. Skill Extensibility Rule

The first implementation should allow skills to attach additional structured evidence, but only through a bounded extension field.

Recommended rule:
- core defines the envelope
- skills may write `extension_payload`
- skills may not replace the base event schema

This avoids fragmentation while preserving flexibility.

## 8.1 Trust boundary for skill extensions
Phase 1 platform decisions should not directly trust arbitrary extension fields for hard gates or release actions.

Unless an extension contract is explicitly registered later, extension payloads should be treated as supplemental analysis material rather than authoritative governance input.

---

## 9. Evaluation Substrate (Phase 2)

When Phase 2 begins, add:
- `CandidateEvaluationRecord`
- `ReleaseDecisionRecord`
- `RollbackDecisionRecord`

Recommended candidate evaluation fields:
- `candidate_id`
- `target_type`
- `target_id`
- `baseline_version`
- `candidate_version`
- `success_delta`
- `token_delta`
- `latency_delta`
- `feedback_delta`
- `stability_delta`
- `accepted`
- `rejection_reason`
- `evaluated_at`

### 9.1 Hard gates
The first evaluation substrate should support hard-gate logic before complex weighted scoring.

Prefer implementing first:
- max token growth threshold
- max latency growth threshold
- no unacceptable success regression
- no failed required regression slice

Weighted scoring can be layered on after the hard-gate model exists.

---

## 10. What Should Be Deferred or Reduced

To keep the project implementable, the following should be deferred or reduced initially.

## 10.1 Do not build a fully automatic self-iteration loop yet
Do not start with:
- auto generation
- auto acceptance
- auto publish
- auto rollback

in one fully autonomous chain.

Build the evidence substrate first.

## 10.2 Do not permit unconstrained custom logging formats
Skills should not be allowed to invent arbitrary top-level log shapes in Phase 1.

Use a core envelope plus extension payload.

## 10.3 Do not overbuild implicit-feedback inference
Use only a small number of reliable implicit signals at first.

Examples that are reasonable later but should not dominate Phase 1 complexity:
- repeat request detection
- immediate correction after output
- manual retry after failure

## 10.4 Do not build full policy combinatorics too early
Support only the most useful scopes first.

## 10.5 Do not require complete payload retention
Raw full input/output capture should remain off by default and can be omitted entirely in the first implementation if sensitivity/cost tradeoffs remain unclear.

---

## 11. Suggested Module Placement

A reasonable first code layout could be:
- `app/models/telemetry.py`
- `app/models/upgrade_log.py`
- `app/models/collection_policy.py`
- `app/services/telemetry_service.py`
- `app/services/collection_policy_service.py`
- `app/services/upgrade_log_service.py`
- `app/services/evaluation_summary_service.py` (Phase 2)

If the codebase later prefers a package layout, these can move under:
- `app/services/telemetry/`

The important point is to keep:\n- telemetry substrate\n- upgrade-log substrate\n- evaluation substrate\n\nclearly separated even if they remain adjacent.

---

## 12. API / Query Surface Suggestions

The first delivery should keep API surface modest.

Recommended initial surfaces:
- telemetry lookup by interaction id
- recent telemetry list by app id
- recent feedback list by app id / skill id
- recent upgrade-log events by type and time window
- collection policy get/set for global/app/skill

Do not ship a large operator dashboard API for this layer in Phase 1 unless the underlying records are already stable.

---

## 13. Testing Plan

## 13.1 Phase 1 tests
Must include:
- telemetry record creation tests
- collection policy precedence tests
- append-only JSONL writing tests
- rotation-by-day tests
- version-binding tests
- light vs medium collection behavior tests
- failure-tolerant logging tests so runtime does not break when log writing fails

## 13.2 Phase 2 tests
Add:
- hard-gate evaluation tests
- candidate-vs-baseline comparison tests
- release/rollback evidence tests
- skill extension payload parsing tests

---

## 14. Practical Acceptance Criteria

The first implementation should be considered successful if:
- the system can collect lightweight interaction/step/feedback telemetry
- the system can bind telemetry to version information
- the system can append upgrade-evidence events to daily JSONL files
- global/app/skill policy can enable/disable and switch between off/light/medium
- future skills can read standardized evidence without needing the core to know every higher-order workflow

That is enough to support later evolution without overcommitting to an unbuildable first release.

---

## 15A. Long-term growth rule

After the telemetry/evaluation/governance substrate exists and the core-skill toolchain is stable, the preferred system growth path should be:
- ordinary skills generate or revise other ordinary skills
- core skills supervise that generation/testing/acceptance flow
- the platform core changes only when standards, safety boundaries, or primitive runtime/governance capabilities must change

## 15. Final Implementation Guideline

When deciding whether something belongs in the core or in a skill, prefer this rule:

### Put it in the core if it is:
- a shared standard
- a safety boundary
- a stable event/model envelope
- a primitive record/query capability
- a publish/rollback/evaluate primitive

### Put it in a skill if it is:
- a higher-order workflow
- a strategy choice
- a report/archive format
- a next-version generation flow
- a test orchestration flow
- a domain-specific optimization behavior

This keeps the system aligned with the intended product philosophy while still keeping the roadmap implementable.