# Generated Skill & App Self-Iteration Roadmap

## 1. Purpose

This document turns the current generated-skill experiments into a staged delivery roadmap.

The target capability is not merely "register a demo skill", but a durable product path where AgentSystem can:
- create ordinary skills through an interface
- execute them for real
- assemble them into apps
- install and run those apps
- diagnose failures
- iteratively improve the authoring/runtime path

This roadmap is ordered by implementation priority rather than by architectural abstraction.

---

## 2. Current Baseline

Already working today:
- low-friction skill authoring helpers for callable/script packaging
- API-first generated skill creation (`/skills/create`)
- generated blueprint assembly from registered skills (`/apps/from-skills`)
- generated blueprint install + workflow execution (`/apps/from-skills/install-run`)
- real script-skill verification with a non-trivial slugify skill
- focused regression slice covering authoring + runtime adapters + generated skill flow

Current proven baseline:
- generated **script** skills can be created through the API
- generated script skills can be smoke-tested through the runtime
- generated script skills can be assembled into an app blueprint
- generated app blueprints can be installed and run
- runtime/schema mismatches can be surfaced and fixed through framework changes

Current known limits:
- callable skills are not yet auto-materialized into real handler implementations
- generated skill assets are not yet treated as durable package artifacts
- failure diagnosis is still too stringly and not yet a true self-repair loop
- multi-step skill composition remains minimal

---

## 3. Delivery Principles

> **Self-iteration maintenance rule**
>
> Any future self-iteration work that changes system structure, adds/removes skills, changes generated-app flow, introduces new contracts/helpers, or changes important validation paths must also update `docs/system-relationship-map.md` in the same change set.
>
> The relationship map is part of the self-iteration substrate: if the system evolves but the map does not, future iterations will lose impact awareness.

1. **Prove with real skills, not synthetic placeholders only**
   Every stage should be validated with at least one realistic skill or app path.

2. **Patch framework gaps exposed by validation**
   When a real generated-skill test fails, improve the platform instead of only relaxing the test.

3. **Prefer durable assets over runtime-only registration**
   A generated skill should become something the system owns, reloads, and manages.

4. **Keep the path API-first**
   The final product path should not require editing source files by hand for ordinary skill creation.

5. **Preserve deterministic-first posture**
   Deterministic and script-backed skills should become reliable before more autonomous model-generated code paths expand.

---

## 4. Roadmap Overview

| Phase | Goal | Priority | Main outcome |
| --- | --- | --- | --- |
| Phase 1 | Durable generated skill assets | P0 | created skills survive beyond the current runtime session |
| Phase 2 | Real callable skill generation path | P0 | non-script skills can be auto-created and truly executed |
| Phase 3 | Structured diagnostics and retry loop | P0 | generated-skill failures become actionable machine-readable events |
| Phase 4 | Stronger skill composition and mapping | P1 | multi-step generated apps become practical |
| Phase 5 | Better generated app skeletons | P1 | generated apps become less toy-like and more reusable |
| Phase 6 | Broader real-skill validation matrix | P1 | framework confidence increases across multiple ordinary skill types |
| Phase 7 | Security and permission boundaries | P2 | generated skill execution becomes safer to expand |
| Phase 8 | Skill revision / rollback / self-improvement loop | P2 | generated skills start to evolve, not only appear |

---

## 5. Phase-by-Phase Plan

## Phase 1 — Durable generated skill assets (P0)

### Objective
Make generated skills durable system assets instead of mostly runtime-registered objects.

### Why first
Without persistence/reload, generated skills are closer to session artifacts than platform capabilities.

### Scope
- define generated skill asset storage layout
- persist generated manifests/contracts/adapter specs
- persist script/callable asset metadata in `skill_assets`
- add startup reload for generated skills
- distinguish built-in skills vs generated skills in registry metadata

### Candidate modules
- `app/services/skill_factory.py`
- `app/services/app_data_store.py`
- `app/services/skill_control.py`
- new generated skill asset persistence helper/service
- bootstrap reload path in `app/bootstrap/runtime.py`

### Acceptance criteria
- [x] a generated script skill survives process restart
- [ ] registry can distinguish generated assets from built-ins
- [x] reload restores manifest/contract/runtime registration correctly
- [x] focused persistence/reload tests pass

### Suggested validation skill
- reuse `skill.text.slugify`
- create skill -> persist -> rebuild runtime -> smoke execute again

---

## Phase 2 — Real callable skill generation path (P0)

### Objective
Support real generated callable skills, not only script-backed ones.

### Why second
This is the clearest missing capability for ordinary deterministic skills.

### Scope
- define callable skill code artifact layout
- materialize handler modules/files for generated callable skills
- validate handler import path + function signature
- register generated callable handlers into runtime
- smoke execute generated callable skills via API path

### Candidate modules
- `app/services/skill_factory.py`
- `app/services/skill_authoring.py`
- new callable skill materializer service
- runtime registration/reload helpers

### Acceptance criteria
- [x] interface can create a callable skill with a real handler implementation artifact
- [x] callable skill smoke test executes without manual source editing
- [x] generated callable skill can be used in generated app install-run flow
- [x] focused callable generation regression passes

### Suggested validation skill
- deterministic metadata formatter
- JSON object key normalizer
- frontmatter parser

---

## Phase 3 — Structured diagnostics and retry loop (P0)

### Objective
Turn generation/runtime/install failures into structured machine-actionable diagnostics.

### Why third
This is the minimum needed for self-iteration rather than manual debugging.

### Scope
- normalize generated-skill failure categories
- add structured diagnostic model/API response
- capture failure stage (`create | register | smoke_test | assemble | install | execute`)
- attach remediation hints where deterministic
- define retry payload shape for corrected regeneration

### Candidate modules
- `app/models/skill_creation.py`
- `app/services/skill_factory.py`
- `app/core/errors.py`
- workflow/install validation surfaces

### Acceptance criteria
- [x] failing generated skill requests produce structured diagnostics
- [x] contract errors, adapter errors, install errors, and runtime errors are distinguishable
- [x] retry payload examples can be derived from failure responses
- [x] tests verify diagnostic shapes for at least 3 failure classes

### Suggested validation cases
- missing script command
- callable import failure
- contract mismatch during workflow execution

---

## Phase 4 — Stronger skill composition and mapping (P1)

### Objective
Make multi-step generated apps practical instead of only single-step generated apps.

### Scope
- explicit step-output to step-input mapping helpers
- field-level mapping and transform rules
- defaults / optional field support
- generated multi-step app composition helpers
- better handling for working-set injection + schema compatibility

### Acceptance criteria
- generated app can chain at least 2 skills without manual blueprint editing
- step output field mapping is explicit and tested
- schema compatibility issues are visible before runtime where possible

### Suggested validation app
- normalize title -> generate slug -> persist metadata summary

---

## Phase 5 — Better generated app skeletons (P1)

### Objective
Improve generated apps from “minimal runnable” to “reasonable starting app”.

### Scope
- richer default roles/tasks/views
- service vs pipeline skeleton variants
- runtime policy defaults inferred from installed skills
- generated app descriptions and metadata
- optional app profile hints based on skill capabilities

### Acceptance criteria
- generated app skeletons differ meaningfully by app type
- blueprint validation no longer needs ad-hoc patching for common generated paths
- generated app metadata is useful for control-plane display

---

## Phase 6 — Broader real-skill validation matrix (P1)

### Objective
Increase confidence by validating different ordinary skill shapes.

### Validation targets
At least one real example for each of:
- text normalization
- JSON reshape / extract
- metadata parsing
- deterministic validation skill
- multi-step generated app using more than one skill

### Acceptance criteria
- at least 4 realistic generated skill cases exist
- at least 2 generated app cases exist
- focused regression suite covers them without manual setup

---

## Phase 7 — Security and permission boundaries (P2)

### Objective
Keep generated skill expansion safe.

### Scope
- adapter allowlists / command restrictions
- file/network boundary metadata
- generated skill risk classification enforcement
- install/run gating for risky generated skills
- manifest-level risk metadata (`risk_level`, shell/filesystem/network allowances) as the baseline machine-readable substrate

### Acceptance criteria
- high-risk generated skill requests are blocked or gated intentionally
- script command restrictions are test-covered
- risk metadata affects whether auto-install/auto-run is allowed
- generated app assembly rejects risky skills by default unless a future explicit policy layer authorizes them
- blocked assembly/install-run paths surface structured policy diagnostics that a future approval or override layer can consume
- reviewer-managed overrides can intentionally unblock risky generated app assembly with an auditable persisted decision
- governance actions and policy blocks leave a queryable event trail suitable for future risk dashboards and audit/reporting surfaces
- operator-facing risk stats/dashboard reads are available so future self-iteration loops can inspect governance state without hand-scanning raw records
- skill suggestion / self-iteration entry points should consume governance summaries so newly suggested skills naturally trend safer under active policy pressure
- those safer defaults should be preserved in blueprint-level metadata so downstream generation stages can honor them automatically
- the generation layer should expose an explicit bridge from blueprint safety metadata into concrete creation defaults before full end-to-end generated-skill materialization is completed
- the next handoff should also project those defaults into concrete `SkillCreationRequest` objects so the generated-skill create path can consume them directly
- stored blueprints should be materializable through a concrete API path so the governance-aware handoff becomes part of the real generated-skill creation flow, not just an internal helper
- that API path should expose the final registered skill state so future self-iteration loops can verify whether governance-aware defaults actually propagated into the resulting artifact
- blueprint safety metadata should also become active materialization policy, preventing low-risk blueprints from silently crossing into shell/network-heavy forms without a later explicit override layer
- that materialization policy should participate in the same audited override system, using a dedicated `blueprint_materialization` scope when intentional exceptions are granted

---

## Phase 8 — Skill revision / rollback / self-improvement loop (P2)

### Objective
Move from generated-skill creation to generated-skill evolution.

### Scope
- generated skill version lineage
- structured replace/rollback for generated assets
- failure-driven regeneration requests
- compare old vs new skill contract/runtime behavior

### Acceptance criteria
- generated skill can be replaced with a new version through the API path
- previous version remains recoverable
- regression comparison between versions is visible

---

## 6. Immediate Next 3 Tasks

### Task A — generated skill persistence and reload
Reason:
This is the most important gap between “worked once” and “is part of the system”.

### Task B — real callable skill generation path
Reason:
This removes the biggest current asymmetry between script skills and ordinary deterministic skills.

### Task C — structured diagnostics for generation/install/run failures
Reason:
This is the minimum viable self-iteration loop.

---

## 7. Progress Tracking Template

Use this checklist when executing the roadmap:

- [ ] Phase 1: generated asset persistence/reload
- [ ] Phase 2: callable generation path
- [ ] Phase 3: structured diagnostics + retry loop
- [ ] Phase 4: multi-step composition/mapping
- [ ] Phase 5: richer generated app skeletons
- [ ] Phase 6: broader real-skill validation matrix
- [ ] Phase 7: security/permission boundaries
- [ ] Phase 8: revision/rollback/self-improvement

Per phase, record:
- implementation files
- validation cases
- focused regression result
- open follow-up gaps
- whether `docs/system-relationship-map.md` was updated to reflect the new structure / coupling / test impact
