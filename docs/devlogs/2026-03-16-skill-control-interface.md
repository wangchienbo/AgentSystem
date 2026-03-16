# Development Log - 2026-03-16 - Skill Control Interface

## What was written
- Added immutable-oriented skill control models.
- Added `SkillControlService` for list/get/replace/rollback/disable/enable flows.
- Protected the human control surface with `immutable_interface=True`.
- Exposed initial API routes for manual skill operations.

## Files changed
- `app/models/skill_control.py`
- `app/services/skill_control.py`
- `app/api/main.py`
- `tests/unit/test_skill_control.py`
- `docs/requirements.md`
- `docs/design.md`
- `docs/testing.md`
- `docs/devlogs/2026-03-16-skill-control-interface.md`

## Tests
- `python -m pytest tests/unit/test_skill_control.py`
- full unit suite
