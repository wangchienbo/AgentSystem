# AgentSystem

App OS prototype for building, managing, and running AI-native applications.

## Current status

This repository now contains a working prototype skeleton for:
- App Blueprint models with runtime policy
- App Instance models with execution mode
- App registry and installer flow
- Interaction gateway for opening service apps and running pipeline apps
- Runtime host, scheduler, and supervisor services
- File-based runtime persistence
- FastAPI endpoints for validation, registry, install, runtime, and interaction flows
- Unit tests covering the core lifecycle and orchestration path

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
