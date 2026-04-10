# Module: skills-generated

## Purpose
Own skill registry/control, manifest and adapter contracts, generated skill authoring/runtime, and generated app assembly paths.

## Responsibilities
- maintain skill registry and runtime contracts
- maintain generated skill authoring/materialization/runtime paths
- preserve risk-aware generated app assembly behavior
- host or coordinate future meta-skill and generated-skill governance capabilities when they belong to the skill generation layer

## Depends On
- app-runtime-core
- registry-blueprints-control-plane

## Provides
- skill-registry-api
- generated-skill-api
- skill-runtime-api

## File Scope

### Primary Paths
- app/services/skill_control.py
- app/services/skill_runtime.py
- app/services/skill_factory.py
- app/services/skill_authoring.py
- app/services/skill_manifest_validator.py
- app/services/generated_callable_materializer.py
- app/services/generated_skill_assets.py
- app/services/system_skill_registry.py
- app/bootstrap/skills.py

### Related Paths
- app/models/skill_control.py
- app/models/skill_manifest.py
- app/models/skill_adapter.py
- docs/skill-asset-governance.md
- docs/skill-design-principles.md

### Interface Paths
- app/services/app_registry.py
- app/services/workflow_executor.py
- app/api/main.py

### Excluded Paths
- app/services/refinement_rollout.py
- app/services/priority_analysis.py

## Constraints
- generated skill and generated app behavior must remain aligned with manifest/runtime/risk contracts
- meta-skill introduction should go through the project control layer before becoming a direct system capability

## Current Tasks
- define where app-skill-factory-related capabilities belong
- decide whether app design control-plane generation lives inside this module or as a split child module later
- preserve isolated testability for generated skill and app assembly api surfaces

## Open Risks
- generation responsibilities can sprawl across skill/runtime/registry/learning boundaries if not explicitly governed by the project control layer
