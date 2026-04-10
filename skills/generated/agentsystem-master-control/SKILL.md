---
name: agentsystem-master-control
description: Master control skill for AgentSystem. Use for project-scoped governance, architecture routing, context assembly, app/domain boundary decisions, control-plane maintenance, and deciding when subordinate skills should be created or revised.
---

# AgentSystem Master Control

Project-internal control layer for AgentSystem.

This skill is the required middle layer for non-trivial project-scoped governance work.
It does not replace the outer assistant persona.
It governs routing, scoping, decomposition, control-plane maintenance, and subordinate-skill creation policy for the AgentSystem repository.

## Core boundary

This skill governs project structure and routing.
It must not become a competing user-facing assistant persona.
It must not default to whole-repo context loading.
It must not create persistent subordinate skills casually or without clear scope evidence.

## What this control skill governs

- project-level routing and scope selection
- app/domain/module decomposition decisions
- project-scoped context assembly discipline
- subordinate skill creation, revision, merge, or retirement decisions
- maintenance of project control artifacts
- cross-scope dependency and impact tracking

## What it must not do

- redefine system or workspace identity
- act as the sole executor for every implementation task
- bypass durable file-backed project governance
- assume every request is project-level
- create low-value child skills for one-off work

## Anchor relationship and entry model

The routing anchor for this skill is `/root/project/AgentSystem/PROJECT_CONTROL.md`.
That anchor's first job is to register and locate this master control skill for outer agents and fresh sessions.

Normal model:
1. outer agent reads the anchor
2. outer agent routes into this master control skill when trigger conditions match
3. this skill determines whether to stay at project scope or delegate downward

This skill may read the anchor for consistency and recovery checks, but does not depend on the anchor to find itself during normal operation.

## Trigger conditions

Use this skill when the request involves:
- project architecture or restructuring
- deciding ownership or scope boundaries
- deciding whether work belongs to project, app, domain, or module scope
- creating or revising subordinate skills
- cross-module or cross-app impact analysis
- updating project control artifacts
- deciding what context should be loaded for a non-trivial change

Usually do not use this skill for tiny obvious edits with narrow local scope.

## Standard workflow

1. determine whether the request is project-scoped or safely local
2. if project-scoped, read only the minimum relevant control artifacts
3. identify target scope and impacted neighboring scopes
4. decide whether to keep work in project control or delegate
5. if delegation is needed, decide whether an existing subordinate scope is sufficient or a new one should be created
6. after meaningful structural changes, update control artifacts immediately

## Context assembly policy

Prefer this order:
1. project anchor for routing confirmation when needed
2. `control-plane/project-map.yaml` for current structural state
3. target scope records under `control-plane/modules/` and relevant task files
4. impacted contracts/interfaces when they exist
5. local implementation files only as needed

Avoid whole-repo loading by default.
Use the smallest sufficient working set.

## Foundational subordinate capabilities

This skill must operate with the following built-in subordinate capabilities from day one, even if they are represented as internal roles rather than separate installable skills.

### 1. project-manager
Responsibilities:
- maintain project-level planning and routing
- keep project-domain scope ownership coherent
- decide when work is truly project-level

### 2. app-manager
Responsibilities:
- interpret app-level boundaries inside AgentSystem
- identify when a request should move from project scope into app or domain scope
- escalate back to project scope when cross-app or cross-domain effects appear

### 3. context-assembler
Responsibilities:
- gather the minimum sufficient context for the request
- avoid unnecessary repository-wide loading
- prioritize anchor, project-map, scope records, and then local implementation files

### 4. skill-governor
Responsibilities:
- decide when a persistent subordinate skill should be created, revised, merged, or avoided
- require stable scope, ownership, and escalation rules before persistent child-skill creation

### 5. control-plane-maintainer
Responsibilities:
- update the anchor and project control artifacts after structural change
- keep project-map, scope records, and task records synchronized enough for resumability

## Subordinate-skill creation policy

Create a persistent subordinate skill only when several of the following are true:
- there is a stable responsibility boundary
- there is a recognizable owned file set, interface surface, or runtime boundary
- the scope will recur across multiple tasks
- re-orientation cost is high enough to justify specialization
- durable ownership and escalation rules are needed

For every persistent subordinate skill, record:
- scope id
- purpose
- owned files or contract surfaces
- dependencies
- constraints
- allowed operations
- escalation conditions back to this master control skill

## Control-plane artifacts

Maintain at least:
- `/root/project/AgentSystem/PROJECT_CONTROL.md`
- `/root/project/AgentSystem/control-plane/project-map.yaml`
- `/root/project/AgentSystem/control-plane/modules/`
- `/root/project/AgentSystem/control-plane/interfaces/`
- `/root/project/AgentSystem/control-plane/tasks/`

Keep these artifacts concise, durable, and structural.
Do not turn them into chat transcripts.

## Initial AgentSystem project domains

Use these as the initial project-domain guide unless later evidence justifies reshaping:
- `platform-core`
- `runtime-and-control-plane`
- `skill-evolution-toolchain`
- `telemetry-evidence-governance`

These are initial governance domains, not frozen forever.

## Consistency and recovery

On meaningful project-governance entry:
- ensure the anchor still points to this skill
- ensure `project-map.yaml` exists
- ensure `modules/` and `tasks/` exist
- repair or recreate the minimum skeleton if missing

If the control layer becomes stale, repair the minimum viable routing and scope state before proceeding with major structural changes.

## Update obligations

After meaningful structural or governance changes:
- update `project-map.yaml`
- update affected scope/module files
- update task records
- update anchor registration if the master control skill path changes
- reflect major cross-cutting structure changes in `docs/system-relationship-map.md` when applicable
