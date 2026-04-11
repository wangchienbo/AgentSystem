---
name: agentsystem-master-control
description: Master control skill for AgentSystem. Use for project-scoped governance, architecture routing, context assembly, subordinate-skill governance, app/domain boundary decisions, control-plane maintenance, and deciding when subordinate skills should be created, reused, updated, downloaded, or retired.
---

# AgentSystem Master Control

Project-internal control layer for AgentSystem.

This skill is the required middle layer for non-trivial project-scoped governance work.
It does not replace the outer assistant persona.
It governs routing, scoping, decomposition, control-plane maintenance, subordinate-skill governance, and structural evolution for the AgentSystem repository.

## Core boundary

This skill governs project structure and routing.
It must not become a competing user-facing assistant persona.
It must not default to whole-repo context loading.
It must not create persistent subordinate skills casually or without clear scope evidence.

## What this control skill governs

- project-level routing and scope selection
- app/domain/module decomposition decisions
- project-scoped context assembly discipline
- subordinate-skill category and lifecycle governance
- subordinate-skill discovery, reuse, install, update, merge, retirement, and registry maintenance
- maintenance of project control artifacts
- cross-scope dependency and impact tracking

## What it must not do

- redefine system or workspace identity
- act as the sole executor for every implementation task
- bypass durable file-backed project governance
- assume every request is project-level
- create low-value child skills for one-off work
- treat module skill as the only kind of subordinate skill

## Anchor relationship and entry model

The routing anchor for this skill is `/root/project/AgentSystem/PROJECT_CONTROL.md`.
That anchor's first job is to register and locate this master control skill for outer agents and fresh sessions.

## Trigger conditions

Use this skill when the request involves:
- project architecture or restructuring
- deciding ownership or scope boundaries
- deciding whether work belongs to project, app, domain, or module scope
- subordinate-skill governance or subordinate-skill lifecycle decisions
- cross-module or cross-app impact analysis
- updating project control artifacts
- deciding what context should be loaded for a non-trivial change

## Explicit initialization rules

On first activation, this master control skill should automatically:
1. read `PROJECT_CONTROL.md`, `control-plane/project-map.yaml`, subordinate registry, and structural-candidate artifact
2. scan the repository structure and key project documents, including README and major design/requirements/testing references
3. reconcile generated control state with repository reality
4. confirm or revise the initial stable governed scopes
5. decide whether any first structural subordinate skills should be created immediately
6. create the necessary first subordinate skills in this master control skill's own role
7. update registry, candidates, project map, module records, task records, and related control artifacts to reflect the initialized structure

## Standard workflow

1. determine whether the request is project-scoped or safely local
2. if project-scoped, read only the minimum relevant control artifacts
3. identify target scope and impacted neighboring scopes
4. decide whether to keep work in project control or delegate downward
5. decide whether an existing subordinate skill should be reused or updated before creating a new one
6. after meaningful structural changes, update control artifacts and subordinate-skill registry immediately

## Context assembly policy

Prefer this order:
1. project anchor for routing confirmation when needed
2. `control-plane/project-map.yaml`
3. `control-plane/subordinate-skills/registry.yaml` when subordinate-skill governance matters
4. `control-plane/subordinate-skills/structural-candidates.yaml` when structural promotion decisions matter
5. target scope records and task files
6. interfaces/contracts when relevant
7. local implementation files only as needed

Avoid whole-repo loading by default.
Use the smallest sufficient working set.

## Subordinate-skill model and categories

Subordinate skill is the general class of child capabilities governed by this master control layer.
Subordinate skills are divided into:
- functional subordinate skills
- structural subordinate skills

A module skill is a structural subordinate skill, not the entire meaning of subordinate skill.

### Functional subordinate skills
These support the master control layer's own operation and governance logic.
They may initially exist as internal roles or procedures, but remain durable governed capabilities.

### Structural subordinate skills
These correspond to stable app, domain, or module boundaries inside AgentSystem.
They should only become persistent when boundary evidence is strong enough.

## Foundational subordinate capabilities

This master control skill must operate with the following built-in functional subordinate capabilities from day one:
- `project-manager`
- `app-manager`
- `context-assembler`
- `skill-governor`
- `control-plane-maintainer`
- `subordinate-skill-manager`

### project-manager
Maintains project-level planning, scope routing, and project-scoped task governance.

### app-manager
Handles app-level scope interpretation and escalation between app scope and project scope.

### context-assembler
Builds the minimal sufficient context set for project-governed work.

### skill-governor
Decides whether subordinate skills should be created, updated, merged, or avoided.

### control-plane-maintainer
Keeps anchor and control-plane artifacts synchronized with structural changes.

### subordinate-skill-manager
Discovers, installs, updates, aligns, and retires subordinate skills under governance rules.
It must prefer existing trusted local skills first, then trusted external sources when justified.
Any external subordinate-skill download or update must be recorded in the subordinate-skill registry.
It also participates in first-run initialization by helping evaluate structural subordinate candidates and determining whether any immediate subordinate-skill creation is justified.

## Subordinate-skill lifecycle policy

Before creating a new persistent subordinate skill, check whether:
- an existing local subordinate skill already covers the scope
- an existing subordinate skill should be updated instead of duplicated
- the requested capability is functional or structural
- the scope is stable enough to justify persistence

For each durable subordinate skill, record:
- subordinate skill id
- category
- scope id
- purpose
- source
- version
- lifecycle status
- dependencies
- compatibility notes
- update policy
- escalation conditions

## Structural subordinate candidate policy

Maintain a durable structural-candidate artifact at:
- `/root/project/AgentSystem/control-plane/subordinate-skills/structural-candidates.yaml`

Use it to track stable app/domain/module scopes that might later become structural subordinate skills.
Not every structural candidate should be promoted immediately.

For each structural candidate, record:
- candidate id
- candidate type
- scope id
- current recommendation
- rationale
- promotion conditions

Promotion from candidate to structural subordinate skill should happen only when:
- repeated work confirms a durable stable boundary
- owned files or interface surfaces are clear enough
- re-orientation cost is high enough to justify persistent specialization
- the skill-governor and subordinate-skill-manager agree that reuse/update is worse than promotion

## External download and update policy

Automatic download or update of subordinate skills is allowed only under governance.
This requires:
- a scope-justified need
- trusted source preference
- durable registry recording
- version/source tracking
- compatibility note recording when material
- refusal of uncontrolled skill sprawl

Prefer this order:
1. reuse existing local governed subordinate skill
2. update existing local governed subordinate skill
3. generate a new local subordinate skill
4. download or update from a trusted external source only when justified

## Control-plane artifacts

Maintain at least:
- `/root/project/AgentSystem/PROJECT_CONTROL.md`
- `/root/project/AgentSystem/control-plane/project-map.yaml`
- `/root/project/AgentSystem/control-plane/modules/`
- `/root/project/AgentSystem/control-plane/interfaces/`
- `/root/project/AgentSystem/control-plane/tasks/`
- `/root/project/AgentSystem/control-plane/subordinate-skills/registry.yaml`
- `/root/project/AgentSystem/control-plane/subordinate-skills/structural-candidates.yaml`

## First-run initialization

On first bootstrap handoff from the meta-skill, this master control skill should execute its explicit initialization rules automatically.
This includes:
- validating anchor and control-plane consistency
- validating subordinate-skill registry existence
- validating structural-candidate artifact existence
- scanning repository structure and key project documents
- reconciling control artifacts with current repository reality
- evaluating whether any immediate subordinate-skill creation is necessary
- creating the minimal necessary first subordinate skills in its own role

## Consistency and recovery

On meaningful governance entry:
- ensure the anchor still points to this skill
- ensure `project-map.yaml` exists
- ensure subordinate-skill registry exists
- ensure structural-candidate artifact exists
- repair or recreate the minimum skeleton if missing

## Update obligations

After meaningful structural or subordinate-skill lifecycle changes:
- update `project-map.yaml` when scope structure shifts
- update affected scope/task/interface files
- update subordinate-skill registry
- update anchor registration if the master control skill path changes
- reflect major cross-cutting structure changes in `docs/system-relationship-map.md` when applicable
