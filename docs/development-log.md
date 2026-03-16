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

### Module: app registry, installer, and runtime policy alignment

Aligned the architecture around OS-style boundaries: skill as reusable capability, blueprint as definition, instance as lifecycle object.

#### Added
- `app/models/runtime_policy.py`
  - execution mode
  - activation mode
  - restart policy
  - persistence level
  - idle strategy
- `app/models/registry.py`
  - registry entry model
  - install result model
- `app/services/app_registry.py`
  - blueprint registration
  - registry listing
  - blueprint lookup
  - persistence to runtime store
- `app/services/app_installer.py`
  - blueprint -> instance installation flow
  - instance creation with execution mode and runtime policy
  - lifecycle transitions through validate / compile / install

#### Updated
- `app/models/app_blueprint.py`
  - added `runtime_policy`
- `app/models/app_instance.py`
  - added `execution_mode`
  - added `runtime_policy`
- `app/services/interaction_gateway.py`
  - now routes through installer instead of directly constructing instances
- `app/api/main.py`
  - added registry endpoints
  - preloaded example blueprints into registry
  - interaction path now depends on registry + installer flow
- `app/core/errors.py`
  - added registry / installer error mapping
- `README.md`
  - updated current prototype status
- `docs/design.md`
  - added boundary clarification for skill / blueprint / app instance / data layers

#### API endpoints added
- `GET /registry/apps`
- `POST /registry/apps`
- `POST /registry/apps/{blueprint_id}/install`

#### Behavior added
- service/pipeline mode now belongs to runtime policy instead of being only a catalog convention
- app interaction now installs from registered blueprints before runtime activation
- registry data and blueprints are persisted into runtime store snapshots

#### Tests
- added `tests/unit/test_registry_installer.py`
- updated `tests/unit/test_interaction_gateway.py`
- validated:
  - blueprint registration
  - install flow
  - runtime policy propagation into app instance
  - registry API flow
  - interaction gateway installer-backed execution

#### Validation
- Reused local virtual environment: `.venv`
- Ran test suite successfully
- Result: `37 passed`

### Module: app data store and namespace separation

Implemented a first explicit data layer split for long-lived apps.

#### Added
- `app/models/data_record.py`
  - `DataNamespace`
  - `DataRecord`
- `app/services/app_data_store.py`
  - app namespace provisioning
  - skill asset namespace provisioning
  - record write/read APIs
  - persistence of namespaces and records via runtime store
- `.gitignore`
  - ignore local virtualenv, caches, and test data directories

#### Updated
- `app/services/app_installer.py`
  - app installation now provisions app-specific namespaces
- `app/api/main.py`
  - added namespace and record endpoints
  - runtime persistence snapshot now includes data namespaces and records
  - initialized global skill asset namespace
- `app/core/errors.py`
  - added app data store error mapping
- `tests/unit/test_registry_installer.py`
  - installer tests now include app data store wiring
- `tests/unit/test_interaction_gateway.py`
  - gateway tests now include installer + data store wiring

#### API endpoints added
- `GET /data/namespaces`
- `GET /data/namespaces/{namespace_id}`
- `GET /data/namespaces/{namespace_id}/records`
- `POST /data/namespaces/{namespace_id}/records`

#### Behavior added
- every installed app now gets dedicated namespaces for:
  - `app_data`
  - `runtime_state`
  - `system_metadata`
- system also maintains a global `skill_assets` namespace
- app business data is now explicitly separated from runtime state in the model

#### Tests
- added `tests/unit/test_app_data_store.py`
- validated:
  - namespace provisioning
  - installer-driven namespace creation
  - record write/read behavior
  - namespace API flow
  - persistence snapshot exposure

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories
- Ran test suite successfully
- Result: `41 passed`

### Module: event bus and event-driven scheduling

Implemented a first internal event bus so long-running apps can react to system and app events.

#### Added
- `app/models/event_bus.py`
  - `EventRecord`
  - `EventSubscription`
  - `EventPublishResult`
- `app/services/event_bus.py`
  - event publishing
  - event log persistence
  - subscription registration
  - scheduler integration on publish
- `tests/unit/test_event_bus.py`
  - event-driven scheduling tests

#### Updated
- `app/services/scheduler.py`
  - event schedules now auto-create subscriptions
  - subscription listing support
  - event subscriptions persist alongside schedules
- `app/api/main.py`
  - added event publish/list/subscription endpoints
  - runtime persistence snapshot now includes event log and subscriptions
- `app/core/errors.py`
  - added event bus error mapping
- `.gitignore`
  - now ignores `*.egg-info/`

#### API endpoints added
- `GET /events`
- `POST /events/publish`
- `GET /events/subscriptions`
- `POST /events/subscriptions`

#### Behavior added
- event schedules can now be triggered through internal event publication instead of only manual scheduler calls
- published events are recorded in a persistent event log
- event subscriptions are visible and persisted as first-class runtime objects

#### Tests
- validated:
  - event publish triggers event schedules
  - scheduler auto-registers event subscriptions
  - event API flow
  - manual subscription creation

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `45 passed`
