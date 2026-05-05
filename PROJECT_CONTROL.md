# PROJECT_CONTROL.md

## Purpose

This file is the routing anchor for AgentSystem's project master control skill.
Its first responsibility is to register and locate the master control skill for project-scoped governance work.

## Registered master control skill

- Skill id: `agentsystem-master-control`
- Skill path: `./skills/generated/agentsystem-master-control/SKILL.md`
- Governed scope: the full AgentSystem repository at `<repo-root>`

## Entry conditions

Enter the master control skill first when the request involves project-level routing, architecture, cross-scope impact, subordinate-skill governance, app/domain/module decomposition, or non-trivial context selection.

## Scope note

This anchor exists to locate the master control skill. It is not the full control-plane logic.

## Control artifacts

- `./control-plane/project-map.yaml`
- `./control-plane/modules/`
- `./control-plane/interfaces/`
- `./control-plane/tasks/`
- `./control-plane/subordinate-skills/registry.yaml`
- `./control-plane/subordinate-skills/structural-candidates.yaml`
