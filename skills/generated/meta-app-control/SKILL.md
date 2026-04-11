---
name: meta-app-control
description: Generic app control skill generator (meta skill). Use to generate app-level control skills for any AgentSystem app. Input: app name, goal, complexity. Output: app control manifest, subordinate skill suggestions, decomposition plan, and governance notes. Build-time and evolve-time only — not a runtime dependency.
---

# Meta App Control

Generic meta skill for generating app-level control skills in AgentSystem.

## What It Does

Given an app description (name, goal, complexity, kind), this skill produces:

1. **App control skill manifest** — skill_id, handler entry, capability profile
2. **App anchor file** — e.g. `APP_CONTROL.md`
3. **Subordinate skill suggestions** — domain-models, services, api, tests (based on complexity)
4. **Decomposition plan** — step-by-step guide for setting up the app control structure
5. **Governance notes** — build-time/evolve-time boundaries, escalation rules

## What It Does NOT Do

- It does NOT handle runtime operations
- It does NOT build blueprints or install apps
- It does NOT participate in mature app execution
- It does NOT generate business logic code

## Scope

Primary focus:
- `app/models/meta_app.py` — output models
- `app/models/meta_app_skill.py` — request models
- `app/services/meta_app/bootstrap.py` — core generation logic

## Complexity-Based Decomposition

| Complexity | Subordinates Generated |
|---|---|
| simple | domain-models only |
| moderate | domain-models + services |
| complex | domain-models + services + api + tests |

## Governance Rules

1. This is a **build-time / evolve-time** capability only
2. Generated app control skills should be reviewed before first use
3. Escalate to top-level project control when changes affect broad runtime contracts
4. Do NOT invoke during mature runtime operations

## Input Contract

```
app_name: str          # Required, min_length=1
goal: str              # Required, min_length=1
app_kind: str          # Default: "service"
complexity: str        # "simple" | "moderate" | "complex" (default: "moderate")
scope: dict            # Optional scope hints
context: dict          # Optional additional context
```

## Output Contract

```
AppControlSkillResult:
  app_name: str
  app_slug: str
  anchor_file: str
  control_skill: AppControlSkillManifest
  subordinate_suggestions: list[SubordinateSkillSuggestion]
  decomposition_plan: list[str]
  governance_notes: list[str]
```
