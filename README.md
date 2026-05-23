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
- `~/.config/agentsystem/config.yaml` (default private YAML config path, or `$AGENTSYSTEM_HOME/config.yaml`)
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
- `docs/skill-asset-governance.md` — file-based governance model for candidate/core/archived skill assets and their consistency rules
- `docs/telemetry-and-upgrade-logging.md` — telemetry, feedback, collection levels, and append-only upgrade-evidence design
- `docs/implementation-plan-telemetry.md` — phased implementation plan and requirement-reduction boundary for the telemetry/evolution layer
- `docs/testing.md`
- `docs/testing-detail.md`
- `docs/development-constraints.md` — **AI 开发新代码时必须遵守的约束合集**（Skill 分层、App 设计、上下文读取、代码结构、禁止事项）
- `docs/development-log.md`

## Operator CLI (Phase 1 skeleton)

The repository is transitioning toward a standard install model with a Python control-plane entrypoint:

```bash
agentsystem status
agentsystem doctor
agentsystem runtime-layout
agentsystem assets list
agentsystem assets install <asset_id>
```

Current posture:
- these commands exist as an initial CLI skeleton
- `status` / `doctor` expose lightweight runtime-layout checks
- `status` / `doctor` now also surface config-file presence and local `http://localhost:80/api/status` reachability for service-readiness checks
- `runtime-layout` exposes the current repo-based layout contract
- legacy `start_server.sh`, `stop_server.sh`, and `start_web_server.sh` now act as compatibility wrappers that delegate into the Python CLI

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
uvicorn app.api.main:app --reload
pytest -q
```
