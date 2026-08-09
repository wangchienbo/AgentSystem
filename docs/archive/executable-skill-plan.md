# Executable Skill Adapter + Script Skill Generator v1 Plan

## 1. Goal

Build the next-stage capability that lets AgentSystem generate, register, install, and execute script-based skills in a way that is compatible with app management, workflow execution, policy governance, and review tooling.

This plan intentionally separates:
- **App layer**: blueprint / install / instance / workflow / runtime policy
- **Skill layer**: reusable executable capability asset
- **Adapter layer**: how a skill is actually invoked at runtime

The primary near-term target is **script-based executable skills**. Binary skills should be treated as a later extension of the same adapter model.

---

## 2. Why this is the next step

The current platform already has:
- requirement clarify / extraction / readiness / blueprint draft handoff
- app blueprint / install / workflow runtime
- system capability skill surfaces
- prompt-driven app execution (`prompt.invoke`)
- telemetry / evaluation / governance / evidence loops
- generated-skill and skill-registry concepts in the codebase

What is still missing is a governed runtime path for:
- generating a new concrete executable skill
- registering it as a first-class skill asset
- letting an app depend on it and invoke it through normal workflow/runtime paths

So the next implementation phase should not begin from "write some generated files", but from the runtime contract that allows generated executable skills to become real platform objects.

---

## 3. Non-goals for v1

Not in v1:
- binary compilation pipeline
- cross-language packaging/build orchestration
- remote/containerized sandbox fleet
- marketplace/distribution UX
- full autonomous skill authoring from arbitrary natural language
- broad code synthesis quality optimization

The v1 target is deliberately narrower:
- local executable adapter
- script skill scaffold generation
- registry/runtime/app integration
- governance and testability

---

## 4. Architecture Overview

```text
Requirement / Skill Draft
        |
        v
Skill Scaffold Generator
        |
        v
Generated Skill Asset Directory
(manifest + schema + executable entrypoint + smoke test)
        |
        v
Skill Registry / Skill Control
        |
        v
Skill Runtime Service
        |
        +---- callable adapter
        |
        +---- executable adapter (new)
                     |
                     v
           local process execution
           (json stdin/stdout contract)
        |
        v
Workflow Executor / App Runtime
        |
        v
Telemetry / Evaluation / Governance / Review
```

---

## 5. Core Design Decision

### 5.1 App should not care whether a skill is callable or executable

App/workflow references should continue to use only:
- `kind = "skill"`
- `ref = <skill_id>`

The app layer should not need to know whether the skill is:
- builtin callable
- generated script
- future binary executable

That decision belongs to the skill runtime adapter layer.

### 5.2 Executable skill support should be implemented as a runtime adapter, not as a special workflow step

Do **not** create a new app-specific workflow primitive such as `script.execute` as the main path.

Instead:
- keep app workflow semantics stable
- extend `SkillRuntimeService` with an executable adapter
- let apps keep using skills through the normal skill abstraction

This preserves app-management compatibility.

---

## 6. Executable Skill Contract (v1)

### 6.1 Registry/manifest fields

Each executable skill should declare at least:

- `runtime_adapter = "executable"`
- `entrypoint`
- `invocation_protocol = "json_stdio"`
- `language` (`python` / `node` / `shell` / `binary`)
- `timeout_seconds`
- `capability_profile`
- executable-risk metadata

Suggested example:

```json
{
  "skill_id": "skill.slugify",
  "name": "Slugify Skill",
  "runtime_adapter": "executable",
  "entrypoint": "main.py",
  "invocation_protocol": "json_stdio",
  "language": "python",
  "timeout_seconds": 20,
  "capability_profile": {
    "intelligence_level": "L0_deterministic",
    "network_requirement": "N0_none",
    "runtime_criticality": "C2_required_runtime",
    "execution_locality": "local",
    "invocation_default": "automatic",
    "risk_level": "R1_local_write"
  },
  "runtime_permissions": {
    "allow_network": false,
    "allow_filesystem_write": true,
    "allow_shell": false
  }
}
```

### 6.2 Input contract

The executable skill receives JSON on stdin.

Example:

```json
{
  "skill_id": "skill.slugify",
  "version": "0.1.0",
  "inputs": {
    "text": "Hello World"
  },
  "context": {
    "app_instance_id": "app.slugify.1",
    "workflow_id": "wf.main",
    "step_id": "step.slugify"
  }
}
```

### 6.3 Output contract

The executable skill writes one JSON object to stdout.

Success example:

```json
{
  "status": "completed",
  "output": {
    "slug": "hello-world"
  },
  "artifacts": [],
  "metrics": {
    "duration_ms": 5
  }
}
```

Failure example:

```json
{
  "status": "failed",
  "error": {
    "code": "INVALID_INPUT",
    "message": "text is required"
  }
}
```

### 6.4 Adapter behavior requirements

The adapter must:
- serialize input JSON
- launch process with bounded timeout
- write stdin
- collect stdout/stderr
- parse stdout JSON
- normalize errors
- map failure into standard skill execution result
- preserve stderr preview for diagnostics

---

## 7. Runtime Integration Plan

## 7.1 Skill models

Extend the skill manifest / registry entry to carry executable runtime fields.

Potential additions:
- `runtime_adapter`
- `entrypoint`
- `invocation_protocol`
- `language`
- `timeout_seconds`
- `runtime_permissions`
- `origin` remains preserved (`builtin | generated`)

## 7.2 Skill runtime service

Add `ExecutableSkillAdapter` and teach `SkillRuntimeService` to dispatch:

- `callable` -> existing builtin path
- `executable` -> new process-based execution path

The adapter should return a normal `SkillExecutionResult` so upstream code does not fork on adapter type.

## 7.3 Validation and smoke tests

Executable skills should have a registration-time smoke check:
- entrypoint exists
- manifest is valid
- test input can be executed (or dry-run validated)
- output contract parses correctly

---

## 8. App Management Integration Plan

## 8.1 App blueprint dependencies

Apps should continue declaring skill dependencies by `skill_id`.

No app-level change should be required to indicate script-vs-callable unless a future optimization layer wants to surface it for diagnostics.

## 8.2 App installer checks

Install-time validation should additionally verify:
- referenced executable skills are present
- entrypoint exists
- runtime_adapter is supported
- capability/risk profile is compatible with app runtime policy
- executable permissions are allowed by policy

## 8.3 Workflow executor

No special new step type is needed for v1 skill execution.

The normal skill step path should be enough:
- workflow step references `skill_id`
- skill runtime resolves adapter
- executable skill runs through the new adapter

That is the key compatibility goal with app management.

---

## 9. Governance Model

Executable skills must not be treated as equivalent to harmless builtin callables.

### 9.1 Risk controls

Manifest should explicitly declare:
- local execution
- network requirement
- filesystem write permission
- shell allowance
- risk level

### 9.2 Registration gates

Default-deny behavior should apply to risky generated executable skills unless:
- policy allows them
- or explicit override is present

### 9.3 App install gates

Apps depending on executable skills should inherit governance checks during install and assembly.

### 9.4 Runtime telemetry and evidence

Executable skill execution should emit:
- skill execution telemetry
- stderr/timeout diagnostics
- governance blocked events when denied
- evidence pressure if repeated failures/blocks occur

---

## 10. Script Skill Generator v1 Plan

## 10.1 Output directory layout

Suggested layout:

```text
generated_skills/
  skill_slugify/
    manifest.json
    schema.json
    main.py
    README.md
    tests/
      test_smoke.py
```

## 10.2 Generator inputs

The generator should accept a structured request such as:
- skill_id
- name
- description
- input schema
- output schema
- language
- adapter type (fixed to executable in v1)
- risk/capability defaults
- minimal behavior template type

## 10.3 V1 generation modes

Keep v1 narrow and deterministic. Good initial templates:
- text transform
- required-field validator
- key/value extractor
- slugify / normalization helper
- echo/debug adapter example

Avoid open-ended codegen for arbitrary logic in v1.

## 10.4 Generated entrypoint behavior

The generated script should:
- read JSON from stdin
- validate required fields
- run deterministic transformation logic
- write JSON to stdout
- exit non-zero on fatal failure

---

## 11. Recommended Implementation Phases

## Phase 1 — Executable Adapter Foundation

Deliverables:
- manifest fields for executable runtime
- `ExecutableSkillAdapter`
- skill runtime dispatch support
- registration/smoke validation
- tests for successful execution, timeout, malformed stdout, missing entrypoint

## Phase 2 — Script Skill Scaffold Generator

Deliverables:
- generation request model
- generated skill directory layout
- deterministic templates
- asset persistence
- registry registration for generated executable skills
- tests for scaffold correctness and reload behavior

## Phase 3 — App Integration

Deliverables:
- app installer validation for executable skills
- workflow execution of generated executable skills
- app install/run E2E using generated script skill
- telemetry/governance coverage

## Phase 4 — Governance and Review Hardening

Deliverables:
- runtime permission gates
- executable-specific governance diagnostics
- evidence integration for repeated blocks/failures
- review summaries for generated executable skill runs

---

## 12. Test Plan Additions

Need new coverage for:
- executable adapter happy path
- timeout / stderr / invalid-json handling
- generated executable skill scaffold correctness
- generated executable skill registry durability
- app install with executable skill dependency
- workflow execution through executable skill path
- policy block / allowlist checks
- telemetry / evaluation / evidence integration for executable skills

---

## 13. Suggested Initial File Additions

Potential new files/modules:
- `app/services/executable_skill_adapter.py`
- `app/models/generated_skill_asset.py` (if current models are insufficient)
- `app/services/script_skill_generator.py`
- `tests/unit/test_executable_skill_adapter.py`
- `tests/unit/test_script_skill_generator.py`
- `tests/unit/test_generated_executable_skill_app_flow.py`

Potential touched files:
- skill manifest / registry models
- skill control / runtime service
- app installer
- workflow executor tests
- runtime bootstrap wiring

---

## 14. Final Recommendation

The next development phase should be executed in this order:
1. executable runtime contract
2. executable adapter
3. script scaffold generator
4. registry/runtime integration
5. app install/workflow integration
6. governance + telemetry + evidence hardening

That order minimizes churn and keeps app management stable while introducing executable skills as first-class governed runtime assets.
