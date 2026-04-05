# Code Structure

## Related Maps

- See `docs/system-relationship-map.md` for the cross-cutting module / feature / test relationship graph used for change-impact analysis.
- See `docs/telemetry-and-upgrade-logging.md` for the telemetry / feedback / upgrade-evidence architecture that future implementation should follow.

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
4. `app/models/skill_asset.py`
5. `app/services/skill_manifest_validator.py`
6. `app/services/skill_runtime.py`
7. `app/services/skill_asset_service.py`
8. `docs/skill-asset-governance.md`

## Planned telemetry / upgrade evidence layer

This layer is now a documented design target and should be treated as a first-class future structure area.

Expected module families include:
- telemetry models for interaction / step / feedback / version binding
- collection-policy models for per-scope and per-level control
- lightweight online telemetry services
- append-only upgrade-log writers/readers
- evaluation summary / candidate comparison primitives

Design rule:
- the core should define the standard substrate
- higher-order generation / testing / acceptance / publish / rollback flows should remain skill-oriented whenever practical
