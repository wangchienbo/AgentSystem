# 2026-04-11: Meta-App Refactored into Generic App Control Skill Generator

## Motivation
User direction: `meta-app` should be a generic meta skill (similar to `control-skill-factory`), responsible only for generating app-level control skills. It should NOT be a runtime dependency — only participate in build-time and evolve-time phases.

## Changes

### 1. Rewrote `MetaAppBootstrapService` (app/services/meta_app/bootstrap.py)
- Now acts as a true meta-skill: input app metadata, output app control skill
- Generates `AppControlSkillManifest`, subordinate suggestions, decomposition plan, governance notes
- Complexity-based decomposition:
  - simple → domain-models only
  - moderate → domain-models + services
  - complex → domain-models + services + api + tests

### 2. New Output Model (app/models/meta_app.py)
- `AppControlSkillManifest` — skill_id, name, description, capability profile
- `SubordinateSkillSuggestion` — suggested subordinate per scope
- `AppControlSkillResult` — full generator output

### 3. Updated Request Model (app/models/meta_app_skill.py)
- Added `complexity`, `scope` fields
- Changed operation to `generate_control_skill`

### 4. Registered in Runtime Builder (app/bootstrap/runtime.py)
- `meta_app_bootstrap = MetaAppBootstrapService()` in `build_runtime()`
- `system.meta_app` handler uses this service

### 5. Removed Old Files
- `governance.py` and `structure.py` consolidated into `bootstrap.py`

### 6. Updated SKILL.md
- `skills/generated/meta-app-control/SKILL.md` fully rewritten
- Clear input/output contracts
- Explicit governance rules (build-time only)

## Commits
- `b6336a6` — Refactor meta-app into generic app control skill generator
- `0779f22` — Update meta-app-control SKILL.md for new contract
