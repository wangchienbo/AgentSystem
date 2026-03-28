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
- `/root/.config/agentsystem/config.yaml` (default private YAML config path)
- environment variables such as `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`

Repository examples:
- `config/config.local.example.yaml`
- `config/model.local.example.json`
- `.env.local.example`

Connectivity probe:
- `python scripts/model_probe.py`

## Documentation

Design direction summary:
- keep the platform core thin
- establish a governed core-skill toolchain
- let future capability expansion happen mainly through skill growth rather than repeated core expansion

See:
- `TOOLS.md` — project-local operator notes, common commands, paths, and gotchas
- `docs/requirements.md`
- `docs/design.md`
- `docs/skill-design-principles.md` — canonical reference for future core-skill design
- `docs/code-structure.md` — lightweight map of bootstrap/runtime/system-skill layout
- `docs/system-relationship-map.md` — required co-maintained system map; update it whenever structural code, feature boundaries, shared contracts, or important tests change
- `docs/telemetry-and-upgrade-logging.md` — telemetry, feedback, collection levels, and append-only upgrade-evidence design
- `docs/implementation-plan-telemetry.md` — phased implementation plan and requirement-reduction boundary for the telemetry/evolution layer
- `docs/testing.md`
- `docs/testing-detail.md`
- `docs/development-log.md`

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
uvicorn app.api.main:app --reload
pytest -q
```
