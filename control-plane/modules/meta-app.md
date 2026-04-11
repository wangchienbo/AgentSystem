# meta-app

## Purpose
Provide an in-project meta-app capability for AgentSystem that can define, bootstrap, and govern app-scoped control structures using AgentSystem-native models and services.

## Responsibilities
- define app-scoped control bootstrap inputs and outputs
- assemble initial app control skeletons compatible with current blueprint/install/runtime flows
- maintain app-level subordinate registries and structure records
- support future recursive app-level decomposition without requiring user step-by-step decomposition instructions

## Reference sources
This module is inspired by the structure ideas in:
- `/root/.openclaw/workspace/skills/control-skill-factory/`
- `/root/.openclaw/workspace/skills/project-skill-factory/`
- `/root/.openclaw/workspace/skills/project-module-control-plane/`

It must adapt those ideas to AgentSystem's current application-generation and application-modification paths rather than copying external workspace skills verbatim.
