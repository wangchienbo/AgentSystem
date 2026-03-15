# Development Log - 2026-03-15 - Requirement Router

## What was written
- Added `RequirementIntent` model for structured requirement routing output.
- Added `RequirementRouter` service to classify requests into app / skill / hybrid / unclear.
- Added demonstration-first decision logic for required / optional / not_needed / clarify.
- Exposed `/route-requirement` API endpoint for quick validation.

## Files changed
- `app/models/requirement_intent.py`
- `app/services/requirement_router.py`
- `app/api/main.py`
- `tests/unit/test_requirement_router.py`
- `docs/requirements.md`
- `docs/design.md`
- `docs/testing.md`
- `docs/devlogs/2026-03-15-requirement-router.md`

## Tests
- `pytest`
