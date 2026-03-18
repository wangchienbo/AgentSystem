# TOOLS.md - AgentSystem Local Ops Notes

This file is a project-local operator cheat sheet for common paths, commands, and gotchas.
It is intentionally practical and non-authoritative: README and docs remain the formal project documentation.

## Project root

- Repository root: `/root/project/AgentSystem`

## Primary docs

- `README.md` — project overview and quick start
- `docs/requirements.md` — current milestone requirements and boundaries
- `docs/design.md` — architecture and object model
- `docs/testing.md` — test strategy and coverage map
- `docs/testing-detail.md` — detailed test notes and environment-specific validation
- `docs/development-log.md` — chronological implementation log

## Common commands

Run from the repo root unless noted otherwise.

### Environment setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

### Start API server

```bash
. .venv/bin/activate
uvicorn app.api.main:app --reload
```

### Run tests

```bash
. .venv/bin/activate
pytest -q
```

### Probe model connectivity

```bash
. .venv/bin/activate
python scripts/model_probe.py
```

## Local configuration

Default private config path:

- `/root/.config/agentsystem/config.yaml`

Supported env-style fallbacks include:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

Repository examples:

- `config/config.local.example.yaml`
- `config/model.local.example.json`
- `.env.local.example`

## Runtime data

Runtime persistence is written under:

- `data/runtime/`

These files often change after running the API or tests. Treat them as runtime snapshots, not core source files.

## Repo navigation hints

If `/root/project/README.md` does not exist, use this repo-local README instead:

- `/root/project/AgentSystem/README.md`

For AgentSystem work, do not stop at `/root/project`; enter the actual repo root.

## Workflow reminders

For each completed feature/module:

1. implement in `/root/project/AgentSystem`
2. run/update tests
3. update docs when behavior changes
4. add a development-log entry
5. commit the related change set

Recommended git flow:

- work on a feature branch
- keep related changes grouped
- avoid excessive commit fragmentation

## Current practical gotchas

- Top-level `/root/project/README.md` may be absent; the active README is the repo-local one in this project.
- `pytest` may not exist in the host shell unless `.venv` is activated first.
- `data/runtime/*.json` modifications may just reflect execution/test activity rather than unfinished source work.
