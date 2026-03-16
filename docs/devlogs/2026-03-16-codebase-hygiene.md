# Development Log - 2026-03-16 - Codebase Hygiene

## What was written
- Added shared API error mapping for skill control failures.
- Improved HTTP behavior for not found vs immutable interface violations.
- Moved `pytest` out of runtime dependencies into optional dev dependencies.
- Added API-level tests for skill control error handling.
- Removed tracked bytecode/cache noise from the repository.

## Files changed
- `app/core/errors.py`
- `app/api/main.py`
- `pyproject.toml`
- `tests/unit/test_skill_control.py`
- `docs/design.md`
- `docs/testing.md`
- `docs/devlogs/2026-03-16-codebase-hygiene.md`

## Tests
- full unit suite
