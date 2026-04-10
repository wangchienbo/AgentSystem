# PROJECT_CONTROL.md

This repository uses a project control layer.

## Mandatory entry rule

Before doing project-scoped development or project-management work:
1. read `control-plane/project-map.yaml`
2. identify the active module
3. read `control-plane/modules/<module-id>.md`
4. read directly relevant `control-plane/interfaces/*.md`
5. avoid whole-repo loading unless necessary

## Mandatory middle-layer rule

The project control skill is the required middle layer for:
- module discovery
- module understanding
- module graph updates
- project-structure changes
- adding, deleting, splitting, or merging modules
- creating or revising module skills
- interface contract updates
- project-scoped retrieval/search intended to reason about module ownership or impact
- introducing new meta-skills or app-design control layers into the system

## First-entry self-check

On first entry, the control skill should verify:
- `PROJECT_CONTROL.md` exists
- `control-plane/project-map.yaml` exists
- `control-plane/modules/` exists
- `control-plane/interfaces/` exists
- `control-plane/tasks/` exists
- the active module in `control-plane/project-map.yaml` is resolvable

If any control-plane artifact is missing or stale, repair the control plane before continuing normal project-management work.
