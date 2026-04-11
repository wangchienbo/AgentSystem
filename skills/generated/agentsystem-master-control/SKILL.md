---
name: agentsystem-master-control
description: Master control skill for AgentSystem. Use for project-scoped governance, architecture routing, context assembly, subordinate-skill governance, app/domain/module decomposition, recursive initialization, and deciding when subordinate skills should be created, reused, updated, downloaded, or retired.
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
- recursive initialization to practical working granularity
- project-scoped context assembly discipline
- subordinate-skill category and lifecycle governance
- subordinate-skill discovery, reuse, install, update, merge, retirement, and registry maintenance
- maintenance of project control artifacts
- cross-scope dependency and impact tracking

## Explicit initialization rules
On first activation, this master control skill should automatically:
1. read `PROJECT_CONTROL.md`, `control-plane/project-map.yaml`, subordinate registry, and structural-candidate artifact
2. scan the repository structure and key project documents, including README and major design/requirements/testing/code-structure references
3. reconcile generated control state with repository reality
4. identify or revise practical governed scopes
5. recursively decompose scopes that remain too large or too mixed for practical governance
6. create the necessary subordinate skills in this master control skill's own role until the project reaches a reasonable working granularity
7. update registry, candidates, project map, module records, task records, and related control artifacts to reflect the initialized structure

## Context assembly policy
Prefer this order:
1. project anchor
2. `control-plane/project-map.yaml`
3. subordinate registry and structural candidates
4. target module/scope records and task files
5. relevant interfaces/contracts
6. local implementation files only as needed

Avoid whole-repo loading by default after initialization; prefer the smallest sufficient working set.

## Subordinate-skill model and categories
Subordinate skill is the general class of child capabilities governed by this master control layer.
Subordinate skills are divided into:
- functional subordinate skills
- structural subordinate skills

## Foundational functional subordinate capabilities
- `project-manager`
- `app-manager`
- `context-assembler`
- `skill-governor`
- `control-plane-maintainer`
- `subordinate-skill-manager`

## Structural subordinate creation rule
During initialization and later restructuring, continue decomposing until the repository reaches practical working granularity. Users should not need to manually request second-layer decomposition during ordinary bootstrap.

## Control-plane artifacts
Maintain at least:
- `PROJECT_CONTROL.md`
- `control-plane/project-map.yaml`
- `control-plane/modules/`
- `control-plane/interfaces/`
- `control-plane/tasks/`
- `control-plane/subordinate-skills/registry.yaml`
- `control-plane/subordinate-skills/structural-candidates.yaml`

## Escalation rule
Escalate back to this master control skill when a requested change crosses structural subordinate boundaries, revises project decomposition, or requires new subordinate creation/merge/retirement.
