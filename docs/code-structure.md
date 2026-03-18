# Code Structure

This document is a lightweight map of the current AgentSystem code layout for ongoing development.

## API entry

- `app/api/main.py`
  - FastAPI app creation
  - bootstrap invocation
  - route declarations

## Bootstrap layer

- `app/bootstrap/runtime.py`
  - builds the core service graph
- `app/bootstrap/skills.py`
  - wires built-in skill handlers into the runtime
- `app/bootstrap/catalog.py`
  - registers demo blueprints and demo catalog entries

## System skill implementations

- `app/services/system_skills/app_config.py`
  - `system.app_config`
- `app/services/system_skills/state_audit.py`
  - `system.state`
  - `system.audit`
- `app/services/system_skills/context.py`
  - `system.context`
- `app/services/system_skill_registry.py`
  - built-in skill metadata / manifest registration

Compatibility wrappers currently remain at:
- `app/services/app_config_service.py`
- `app/services/system_skill_service.py`
- `app/services/context_skill_service.py`

These should be treated as migration shims, not the long-term home of the implementations.

## Skill formalization layer

- `app/models/skill_control.py`
  - skill registry entries and capability profile
- `app/models/skill_manifest.py`
  - minimal manifest + contract refs
- `app/models/skill_adapter.py`
  - adapter spec
- `app/services/skill_manifest_validator.py`
  - minimal manifest validation
- `app/services/skill_runtime.py`
  - callable/script adapter execution

## App runtime posture

- `app/models/app_profile.py`
- `app/services/app_profile_resolver.py`

These compute the minimal runtime posture inferred from registered skill metadata.

## What to read first for future changes

### When changing runtime bootstrap
Read:
1. `app/bootstrap/runtime.py`
2. `app/bootstrap/skills.py`
3. `app/bootstrap/catalog.py`
4. `app/api/main.py`

### When changing system skills
Read:
1. `docs/skill-design-principles.md`
2. `app/services/system_skills/README.md`
3. `app/services/system_skill_registry.py`
4. the relevant file under `app/services/system_skills/`

### When changing skill package/runtime structure
Read:
1. `app/models/skill_control.py`
2. `app/models/skill_manifest.py`
3. `app/models/skill_adapter.py`
4. `app/services/skill_manifest_validator.py`
5. `app/services/skill_runtime.py`
