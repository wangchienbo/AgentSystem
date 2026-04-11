# 2026-04-11 Meta-app bootstrap module

## Summary
Added a project-internal `meta-app` module so AgentSystem can bootstrap app-scoped control structures using AgentSystem-native models and services instead of relying on external workspace skills directly.

## What was added
- control-plane module/task records for `meta-app`
- generated structural subordinate skill `meta-app-control`
- `app/models/meta_app.py`
- `app/services/meta_app/` service skeleton for structure/governance/bootstrap

## Design note
The module references workspace control-skill patterns as inspiration, but adapts them to the repository's current app generation and modification flows.
