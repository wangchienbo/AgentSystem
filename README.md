# AgentSystem

App OS prototype for building, managing, and running AI-native applications.

## Current status

This repository contains the first project skeleton for:
- App Blueprint models
- App Instance models
- Minimal FastAPI service
- Initial validation endpoint
- Initial unit tests

## Documentation

See `docs/`:
- `docs/requirements.md`
- `docs/design.md`
- `docs/testing.md`
- `docs/testing-detail.md`

## Run

```bash
pip install -e .
uvicorn app.api.main:app --reload
pytest
```
