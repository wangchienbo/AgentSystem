# Development Log - 2026-03-16 - Demonstration Extractor

## What was written
- Added `DemonstrationRecord` model.
- Added `DemonstrationExtractor` to convert user demonstrations into `ExperienceRecord` + `SkillBlueprint`.
- Added API entrypoint to extract a demonstration and store the results.

## Files changed
- `app/models/demonstration.py`
- `app/services/demonstration_extractor.py`
- `app/api/main.py`
- `tests/unit/test_demonstration_extractor.py`
- `docs/requirements.md`
- `docs/design.md`
- `docs/testing.md`
- `docs/devlogs/2026-03-16-demonstration-extractor.md`

## Tests
- full unit suite
