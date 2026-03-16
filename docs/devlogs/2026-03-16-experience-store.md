# Development Log - 2026-03-16 - Experience Store

## What was written
- Added `ExperienceRecord` model for explicit experience assets.
- Added `SkillBlueprint` model for reusable procedural skill assets.
- Added `ExperienceStore` service to persist experience and skill blueprints in-memory.
- Added API endpoints to create/list experiences and skill blueprints, plus suggestion lookup by experience.

## Files changed
- `app/models/experience.py`
- `app/models/skill_blueprint.py`
- `app/services/experience_store.py`
- `app/api/main.py`
- `tests/unit/test_experience_store.py`
- `docs/requirements.md`
- `docs/design.md`
- `docs/testing.md`
- `docs/devlogs/2026-03-16-experience-store.md`

## Tests
- full unit suite
