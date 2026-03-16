# AgentSystem

App OS prototype for building, managing, and running AI-native applications.

## Current status

This repository now contains a working prototype skeleton for:
- App Blueprint models with runtime policy
- App Instance models with execution mode
- App registry and installer flow
- Interaction gateway for opening service apps and running pipeline apps
- Runtime host, scheduler, supervisor, and event bus services
- App data namespace separation
- Practice review, skill suggestion, self-refinement, proposal review, and priority analysis
- File-based runtime persistence
- OpenAI-compatible model configuration scaffolding and connectivity probe
- FastAPI endpoints for validation, registry, install, runtime, and interaction flows
- Unit tests covering the core lifecycle and orchestration path

## Local model configuration

The project now supports local model configuration via either:
- `config/model.local.json` (gitignored)
- environment variables such as `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`

Examples:
- `config/model.local.example.json`
- `.env.local.example`

Connectivity probe:
- `python scripts/model_probe.py`

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
