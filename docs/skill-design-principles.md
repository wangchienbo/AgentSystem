# Skill Design Principles

This document is the canonical reference for designing platform skills, system-default skills, runtime-governance skills, and builder/intelligent skills in AgentSystem.

It exists so future skill design does not drift across ad-hoc conversations or implicit assumptions.

> **Context**: Skills exist to serve **Apps** — the fundamental unit of this stateful, persistent App OS. Apps are isolated functional modules (光脑 model), and user commands are workflows that orchestrate app lifecycle operations. Skills are reusable capabilities that apps depend on, not standalone products.

## 1. Purpose

This document defines the stable design principles that future skills should follow.

It is especially intended for:
- system-default skills
- platform runtime/governance skills
- builder-time intelligent skills
- future skill-package and runtime-adapter implementations

When introducing a new core skill, this document should be consulted before implementation.

## 2. Core Skill Design Principles

The following principles are the baseline for future skill design.

### 2.1 Deterministic first
If a capability can be executed deterministically, the platform should prefer deterministic execution over intelligent execution.

### 2.2 Local-first for platform foundations
System-default and runtime-governance skills should be local-first whenever possible.

### 2.3 Offline-capable foundations
Core platform skills should not require network or model access unless their role explicitly demands it.

### 2.4 Separate network from intelligence
A skill must not conflate:
- network availability
- intelligence availability
- intelligence invocation policy

### 2.5 Explicit invocation posture
A skill should explicitly indicate whether intelligent execution is:
- automatic
- ask-user
- explicit-only

### 2.6 Machine-readable contracts
Core skills should have strict machine-readable contracts for:
- input
- output
- error
- side effects / execution notes where relevant

### 2.7 Orchestrator-visible execution
Skill execution should remain visible to the runtime/orchestrator so policy, tracing, timeout, retry, and audit can be applied consistently.

### 2.8 Skill-centric evolution by default
If a higher-order behavior such as generation, testing, acceptance, archive, publish, or rollback can be expressed as a reusable skill workflow rather than a hard-coded core behavior, the platform should prefer the skill path unless the function must remain a core standard or safety boundary.

### 2.9 Build-time vs runtime clarity
A skill should explicitly indicate whether it is:
- build-only
- optional at runtime
- required at runtime

### 2.10 Core-skill toolchain over core bloat
When the platform needs higher-order self-improvement behavior, the default preference should be:
- keep the platform core minimal
- express the improvement workflow as a governed core skill when possible
- allow ordinary skills to be produced and managed by that toolchain later

This means the main growth path should be governed skill growth, not repeated core expansion.

## 3. Canonical Core Skill Principle Table

| Skill / capability | Primary role | Runtime criticality | Must be local-first | Must avoid default intelligence | Needs strict contract | Notes |
|---|---|---|---|---|---|---|
| `system.app_config` | per-app deterministic config surface | required_runtime | yes | yes | yes | config must remain separate from context and runtime state |
| `system.context` | app-local shared execution context | required_runtime | yes | yes | yes | should not silently invoke intelligence |
| `system.state` | runtime state access and mutation | required_runtime | yes | yes | yes | optimized for workflow/runtime use |
| `system.audit` | structured audit trail and execution records | required_runtime | yes | yes | yes | should record policy, failure, and invocation decisions |
| `system.skill_runtime` | unified skill execution entry | required_runtime | yes | yes | yes | adapter-based dispatch, timeout/retry/trace enforcement |
| `system.skill_registry` | skill metadata and version lookup | required_runtime | yes | yes | yes | source of truth for capability tags and manifests |
| `system.skill_validator` | skill package validation | build_and_runtime_governance | yes | yes | yes | should reject invalid manifests/contracts/adapters |
| `system.app_profile_resolver` | derive app runtime posture from skill set | build_and_runtime_governance | yes | yes | yes | build-only skills should not inflate runtime class |
| `requirement.clarify` | builder assistance | build_only | not necessarily | no | yes | typically intelligent; should not become runtime-required by accident |
| `blueprint.generate` | builder assistance | build_only | not necessarily | no | yes | typically intelligent and explicit-use |
| `workflow.suggest` | builder/runtime optional assistance | build_only_or_optional_runtime | not necessarily | no | yes | should be carefully tagged if runtime-visible |
| `self_refinement` | proposal generation | build_only_or_optional_runtime | not necessarily | no | yes | token spend and autonomy should remain governed |
| `system.interaction_router` | LLM-powered user interaction routing and dispatch | required_runtime | yes | no (LLM is the core purpose) | yes | routes natural language to subsystems; must degrade gracefully to rule-based matching when model unavailable |
| `system.conversation_session` | conversation session lifecycle and context management | required_runtime | yes | yes | yes | session isolation, history compaction, and context tracking; no intelligence needed |
| `system.response_serializer` | interaction response serialization for multi-channel output | required_runtime | yes | yes | yes | deterministic serialization of text/card/list/confirm/error response types |

## 4. Skill Design Checklist

Whenever a new core skill is introduced, its design should be reviewed against this checklist:

1. Is it a system-default skill, runtime-governance skill, builder skill, or app/runtime skill?
2. Is it build-only, optional-runtime, or required-runtime?
3. Must it be local-first?
4. Must it remain offline-capable?
5. Does it require network?
6. Does it require intelligence?
7. What is its default invocation posture?
8. Does it have strict machine-readable input/output/error contracts?
9. Should it be visible to the orchestrator/runtime for tracing, retry, and policy control?
10. Could it incorrectly inflate app runtime intelligence level if misclassified?
11. Does it blur config/state/context/audit boundaries?
12. Could this behavior live as a skill instead of a core hard-coded flow?
13. If it participates in self-iteration, does it produce or consume standardized telemetry/upgrade evidence cleanly?
14. If this is a self-improvement toolchain capability, should it exist as a governed core skill rather than as new platform-core code?

## 5. How to Use This Document

### 5.1 Before designing a new core skill
Read this document first and classify the candidate skill against the canonical table.

### 5.2 Before implementing adapters or manifests
Check whether the skill's runtime form matches the principles and whether its contract strictness is sufficient.

### 5.3 Before introducing a new system-default skill
Confirm that:
- it belongs in the system-default set
- it is local-first unless there is a strong reason otherwise
- it does not silently require intelligence
- its contract and runtime boundaries are explicit

## 6. Relationship to Other Docs

- `docs/requirements.md` defines that a maintained core-skill principle reference must exist.
- `docs/design.md` should reference this document when describing skill/runtime architecture.
- `docs/testing.md` should define validation targets that keep core skills aligned with this document.
- `docs/system-relationship-map.md` must be updated whenever core-skill/runtime/self-iteration changes alter system coupling, feature boundaries, or validation impact.
- `README.md` and `TOOLS.md` should point here so future implementation work can find it quickly.

## 7. Phase 7: LLM Interaction Layer Skill Design Principles

The LLM interaction layer introduces three new core system skills:

### 7.1 `system.interaction_router`
- **Role**: LLM-powered intent classification and parameter extraction from natural language
- **Runtime criticality**: required_runtime (for the LLM-powered path)
- **Local-first**: yes (degrades to rule-based matching when model unavailable)
- **Default intelligence**: yes (LLM is the core purpose of this skill)
- **Strict contract**: yes (JSON routing result with intent, confidence, params, clarification flags)
- **Design notes**:
  - Must support graceful degradation to the existing `RequirementRouter` when model is unavailable
  - Intent classification should be stable and deterministic given the same input
  - Confidence scores should be meaningful (high = route directly, low = ask for clarification)
  - Extracted parameters must match the structured request schemas of target subsystems
  - Action suggestions should be actionable and match available API endpoints

### 7.2 `system.conversation_session`
- **Role**: Session lifecycle, message history, context tracking, and compaction
- **Runtime criticality**: required_runtime
- **Local-first**: yes (fully deterministic, no intelligence needed)
- **Default intelligence**: no
- **Strict contract**: yes (session state, message records, compaction summaries)
- **Design notes**:
  - Session isolation by user_id + channel is mandatory
  - Message history must be bounded (compact when exceeds threshold)
  - Compaction must preserve key context (decisions, constraints, open loops)
  - Session state must survive runtime restarts (persist to state store)

### 7.3 `system.response_serializer`
- **Role**: Serialize interaction responses into channel-friendly formats
- **Runtime criticality**: required_runtime
- **Local-first**: yes (fully deterministic)
- **Default intelligence**: no
- **Strict contract**: yes (response type, action list, data payload)
- **Design notes**:
  - Must support multiple response types: text, card, list, form, confirm, progress, error
  - Action suggestions must be serializable for channel-specific rendering (buttons, menus, etc.)
  - Must remain channel-abstracted at the service layer, with channel adapters handling format specifics
