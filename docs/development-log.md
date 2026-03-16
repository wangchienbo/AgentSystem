# Development Log

## 2026-03-16

### Module: lifecycle manager and runtime host

Implemented a first minimal runtime lifecycle layer for persistent app management.

#### Added
- `app/services/lifecycle.py`
  - `AppLifecycleService`
  - deterministic app lifecycle transition rules
  - lifecycle event recording
- `app/services/runtime_host.py`
  - `AppRuntimeHostService`
  - runtime lease tracking
  - task queue tracking
  - checkpoint generation
  - healthcheck and restart-count bookkeeping
- `app/models/runtime.py`
  - `LifecycleEvent`
  - `RuntimeCheckpoint`
  - `RuntimeLease`
  - `LifecycleTransitionResult`
  - `RuntimeOverview`

#### API endpoints added
- `GET /apps`
- `POST /apps`
- `GET /apps/{app_instance_id}`
- `GET /apps/{app_instance_id}/events`
- `POST /apps/{app_instance_id}/actions/{action}`
- `POST /apps/{app_instance_id}/tasks`
- `POST /apps/{app_instance_id}/healthcheck`
- `GET /apps/{app_instance_id}/runtime`

#### Updated
- `app/core/errors.py`
  - added lifecycle/runtime error mapping
- `app/api/main.py`
  - wired lifecycle and runtime host services into FastAPI

#### Tests
- added `tests/unit/test_lifecycle_runtime.py`
- validated:
  - legal lifecycle transitions
  - invalid transition rejection
  - runtime start/pause/resume/stop
  - healthcheck + pending task queue
  - runtime API flow
  - 404/400 error mapping

#### Validation
- Created local virtual environment: `.venv`
- Installed package in editable mode with dev dependencies
- Ran test suite successfully
- Result: `24 passed`

### Module: scheduler and supervisor services

Implemented a first minimal scheduling and supervision layer for long-running app hosting.

#### Added
- `app/models/scheduling.py`
  - `ScheduleRecord`
  - `ScheduleTriggerResult`
  - `SupervisionPolicy`
  - `SupervisionStatus`
  - `SupervisionActionResult`
- `app/services/scheduler.py`
  - interval schedule registration
  - event-triggered schedule registration
  - pause / resume / disable controls
  - task enqueue on trigger
- `app/services/supervisor.py`
  - supervision policy registration
  - failure observation
  - restart attempt logic
  - open-circuit protection
  - supervision status reset

#### API endpoints added
- `GET /schedules`
- `POST /schedules`
- `POST /schedules/trigger/interval`
- `POST /schedules/trigger/event`
- `POST /schedules/{schedule_id}/pause`
- `POST /schedules/{schedule_id}/resume`
- `POST /schedules/{schedule_id}/disable`
- `POST /supervision/policies`
- `GET /supervision/{app_instance_id}`
- `POST /supervision/{app_instance_id}/observe-failure`
- `POST /supervision/{app_instance_id}/attempt-restart`
- `POST /supervision/{app_instance_id}/reset`

#### Updated
- `app/api/main.py`
  - wired scheduler and supervisor services into FastAPI
- `app/core/errors.py`
  - added scheduler/supervisor error mapping

#### Tests
- added `tests/unit/test_scheduler_supervisor.py`
- validated:
  - interval schedule trigger
  - event schedule validation
  - supervision failure observation
  - restart flow
  - circuit-open protection
  - scheduler/supervisor API flow

#### Validation
- Reused local virtual environment: `.venv`
- Ran test suite successfully
- Result: `29 passed`

### Module: interaction gateway and runtime persistence

Implemented a first user-facing command gateway plus minimal file-based runtime persistence.

#### Added
- `app/models/interaction.py`
  - `AppCatalogEntry`
  - `UserCommand`
  - `InteractionDecision`
- `app/services/app_catalog.py`
  - app catalog registry
  - trigger phrase matching
- `app/services/interaction_gateway.py`
  - main user command entry
  - service app open flow
  - pipeline app one-shot run flow
  - fallback clarify decision when no app matches
- `app/services/runtime_state_store.py`
  - JSON file persistence for runtime state collections and mappings

#### Updated
- `app/services/lifecycle.py`
  - persist app instances and lifecycle events
- `app/services/runtime_host.py`
  - persist leases, checkpoints, and pending tasks
- `app/services/scheduler.py`
  - persist schedules
- `app/services/supervisor.py`
  - persist supervision policies and statuses
- `app/api/main.py`
  - added catalog listing endpoint
  - added interaction command endpoint
  - added runtime persistence snapshot endpoint
  - wired a default service app and pipeline app into the catalog
- `app/core/errors.py`
  - added app catalog domain error mapping

#### API endpoints added
- `GET /catalog/apps`
- `POST /interaction/command`
- `GET /runtime/persistence`

#### Behavior added
- user commands can now be routed to:
  - open a long-running service app
  - execute a one-shot pipeline app
  - return a clarify response when no app is matched
- runtime state now persists to `data/runtime/*.json`

#### Tests
- added `tests/unit/test_interaction_gateway.py`
- validated:
  - service app command routing
  - pipeline app command routing
  - clarify fallback
  - runtime persistence file creation
  - interaction API and persistence snapshot

#### Validation
- Reused local virtual environment: `.venv`
- Ran test suite successfully
- Result: `34 passed`
