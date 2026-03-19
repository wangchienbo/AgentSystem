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

### Module: practice review and runtime experience distillation

Implemented a first practice-to-experience loop so the system can summarize runtime behavior into reusable experience records.

#### Added
- `app/models/practice_review.py`
  - `PracticeReviewRequest`
  - `PracticeReviewResult`
- `app/services/practice_review.py`
  - runtime event + data record review
  - experience summary generation
  - experience store integration
- `tests/unit/test_practice_review.py`
  - runtime practice review tests

#### Updated
- `app/api/main.py`
  - added practice review endpoint
- `app/core/errors.py`
  - added practice review error mapping

#### API endpoints added
- `POST /practice/review`

#### Behavior added
- system can now inspect an app instance's recent event log and data records
- runtime behavior is summarized into an `ExperienceRecord`
- generated runtime experiences are added to the experience store

#### Tests
- validated:
  - runtime practice review generates an experience record
  - review works from runtime events + app data records
  - practice review API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `47 passed`

### Module: experience-to-skill suggestion layer

Implemented a first semi-automatic bridge from runtime experience to reusable skill blueprint suggestions.

#### Added
- `app/models/skill_suggestion.py`
  - `SkillSuggestionRequest`
  - `SkillSuggestionResult`
- `app/services/skill_suggestion.py`
  - experience lookup
  - candidate skill blueprint generation
  - optional persistence into skill blueprint store
- `tests/unit/test_skill_suggestion.py`
  - skill suggestion tests

#### Updated
- `app/api/main.py`
  - added skill suggestion endpoint
- `app/core/errors.py`
  - added skill suggestion error mapping

#### API endpoints added
- `POST /skills/suggest-from-experience`

#### Behavior added
- system can now generate a candidate `SkillBlueprint` from an `ExperienceRecord`
- suggestion can remain advisory or be persisted into the skill blueprint store
- practice review output can now feed the next evolution step: experience -> skill suggestion

#### Tests
- validated:
  - blueprint suggestion generation from runtime experience
  - optional suggestion persistence
  - practice review -> skill suggestion API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `50 passed`

### Module: self-refinement patch proposal layer

Implemented the first constrained self-iteration layer. The system can now generate patch proposals for itself without directly auto-modifying core runtime behavior.

#### Added
- `app/models/patch_proposal.py`
  - `PatchProposal`
  - `SelfRefinementRequest`
  - `SelfRefinementResult`
- `app/services/self_refinement.py`
  - experience-driven patch proposal generation
  - runtime policy patch suggestions
  - workflow patch suggestions
- `tests/unit/test_self_refinement.py`
  - self-refinement tests

#### Updated
- `app/api/main.py`
  - added self-refinement proposal endpoint
- `app/core/errors.py`
  - added self-refinement error mapping

#### API endpoints added
- `POST /self-refinement/propose`

#### Behavior added
- system can now generate constrained self-refinement proposals from runtime experience
- proposals include:
  - target type
  - evidence
  - expected benefit
  - risk level
  - auto-apply allowance
  - validation checklist
  - rollback target
- current proposal targets:
  - runtime policy
  - workflow

#### Safety boundary
- this layer only produces proposals
- it does not auto-apply structural system changes
- medium/high-risk refinement remains explicitly reviewable

#### Tests
- validated:
  - self-refinement proposal generation from reviewed runtime experience
  - runtime policy and workflow proposals both appear when relevant
  - self-refinement API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `52 passed`

### Module: proposal review and approval flow

Implemented the first review loop for self-refinement proposals so the system can move from proposal generation to controlled approval and limited application.

#### Added
- `app/models/proposal_review.py`
  - `ProposalReviewRecord`
  - `ProposalReviewRequest`
- `app/services/proposal_review.py`
  - proposal registration
  - proposal listing
  - proposal review state transitions
  - limited low-risk runtime policy patch application
- `tests/unit/test_proposal_review.py`
  - proposal review and apply tests

#### Updated
- `app/api/main.py`
  - self-refinement proposal generation now registers proposals for later review
  - added proposal listing endpoint
  - added review record listing endpoint
  - added approve/reject/apply endpoint
  - persistence snapshot now includes patch proposals and proposal reviews
- `app/core/errors.py`
  - added proposal review error mapping

#### API endpoints added
- `GET /self-refinement/proposals`
- `GET /self-refinement/reviews`
- `POST /self-refinement/review`

#### Behavior added
- self-refinement proposals are now persisted as first-class review objects
- review states now include:
  - proposed
  - approved
  - rejected
  - applied
- low-risk runtime policy proposals can be applied in a constrained way
- workflow proposals currently support review/approval but not direct application

#### Safety boundary
- review and approval are now explicit steps
- structural workflow changes are not auto-applied
- apply remains restricted to low-risk runtime-policy patches only

#### Tests
- validated:
  - proposal registration
  - low-risk runtime patch application
  - proposal review API flow
  - approval flow for workflow proposals

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `54 passed`

### Module: priority and contradiction analysis for self-refinement

Implemented a first priority-analysis layer so the system can rank its own refinement proposals and identify the current main contradiction.

#### Added
- `app/models/priority_analysis.py`
  - `PriorityAnalysisRequest`
  - `PrioritizedProposal`
  - `PriorityAnalysisResult`
- `app/services/priority_analysis.py`
  - proposal scoring
  - main contradiction description
  - recommended next action generation
- `tests/unit/test_priority_analysis.py`
  - priority analysis tests

#### Updated
- `app/api/main.py`
  - added self-refinement priority analysis endpoint
- `app/core/errors.py`
  - added priority analysis error mapping

#### API endpoints added
- `POST /self-refinement/analyze-priority`

#### Behavior added
- system can now rank multiple refinement proposals by priority
- ranking considers:
  - target type impact
  - risk level
  - auto-apply eligibility
  - amount of evidence
- analysis also outputs:
  - primary contradiction
  - recommended next action

#### Design value
- the system no longer only produces proposals
- it can now distinguish primary vs secondary refinement actions
- this is the first step toward a structured “抓主要矛盾” capability in the runtime evolution loop

#### Tests
- validated:
  - low-risk runtime policy proposal ranks ahead of workflow proposal when appropriate
  - priority analysis API flow

#### Validation
- Reused local virtual environment: `.venv`
- Cleaned transient `data/test-*` directories and `*.egg-info`
- Ran test suite successfully
- Result: `56 passed`

### Module: local model configuration and connectivity probe

Implemented the first project-level model access scaffolding so AgentSystem can connect to an OpenAI-compatible responses API independently of the host assistant runtime.

#### Added
- `app/models/model_config.py`
  - local model configuration schema
- `app/services/model_config_loader.py`
  - local file / environment configuration loader
  - API key resolution
- `app/services/model_client.py`
  - OpenAI-compatible `/v1/responses` probe client
- `config/model.local.example.json`
  - example local model configuration template
- `.env.local.example`
  - example environment variable template
- `scripts/model_probe.py`
  - minimal connectivity probe script
- `tests/unit/test_model_config.py`
  - model configuration loader tests

#### Updated
- `.gitignore`
  - ignore `.env.local`
  - ignore `config/model.local.json`
- `README.md`
  - added local model configuration section
- `docs/testing-detail.md`
  - recorded actual project-level model probe status

#### Behavior added
- project can now load model settings from a local gitignored config file or environment variables
- project can now resolve API key by env var name
- project can probe an OpenAI-compatible responses endpoint directly

#### Validation
- Ran unit tests successfully
- Result: `59 passed`
- Ran actual model probe against configured endpoint
- Result: `/v1/responses` returned `MODEL_PROBE_OK`

#### Security note
- real API secret was written only to local gitignored files
- no secret was added to tracked repository files or commits

### Module: external private default path for model config

Moved the default model configuration lookup path out of the repository so secrets no longer need to live under the project directory.

#### Updated
- `app/services/model_config_loader.py`
  - default config path changed to `/root/.config/agentsystem/model.local.json`
  - default env path changed to `/root/.config/agentsystem/model.local.env`
  - loader now imports environment values from the private env file automatically
- `README.md`
  - updated local model configuration instructions
- `docs/testing-detail.md`
  - updated project-level model probe notes
- `tests/unit/test_model_config.py`
  - added validation for private env-file loading

#### Behavior added
- the project now prefers private configuration outside the repository by default
- local model secrets can live in `/root/.config/agentsystem/` instead of the workspace
- model probe works using the new default private path without requiring project-local secret files

#### Validation
- Ran full test suite successfully
- Result: `60 passed`
- Ran actual model probe via default external config path
- Result: `/v1/responses` returned `MODEL_PROBE_OK`

### Module: unified private YAML configuration

Unified the local private model configuration into a single YAML file outside the repository.

#### Updated
- `pyproject.toml`
  - added `PyYAML`
- `app/models/model_config.py`
  - added optional inline `api_key`
- `app/services/model_config_loader.py`
  - default private config path changed to `/root/.config/agentsystem/config.yaml`
  - YAML `model:` section is now the primary config source
  - legacy JSON/env private paths remain temporarily compatible for migration
- `app/services/model_client.py`
  - now tolerates event-stream probe responses
- `README.md`
  - updated local config docs for the YAML path
- `docs/testing-detail.md`
  - updated private config and probe notes
- `tests/unit/test_model_config.py`
  - rewritten for YAML-based config loading

#### Added
- `config/config.local.example.yaml`
  - repository template for the private YAML structure

#### Behavior added
- project now prefers one private YAML file at `/root/.config/agentsystem/config.yaml`
- the YAML file can carry the real API key locally without needing extra env files
- loader still keeps env fallback and temporary legacy compatibility
- probe now handles both JSON and SSE-style response bodies

#### Validation
- Installed `PyYAML` in the repo-local virtualenv
- Ran full test suite successfully
- Result: `59 passed`
- Ran actual model probe using `/root/.config/agentsystem/config.yaml`
- Result: endpoint reachable and returned SSE response events from `/v1/responses`

### Module: model-enhanced skill suggestion with deterministic fallback

Added an optional model-backed skill suggestion layer while preserving the original deterministic synthesis path as a safe fallback.

#### Added
- `app/services/model_skill_suggester.py`
  - generates constrained skill blueprint JSON from runtime experience via the configured responses API
  - exposes availability checks so model enhancement stays optional

#### Updated
- `app/services/skill_suggestion.py`
  - now supports injected model suggester
  - still builds a deterministic rule-based suggestion first
  - falls back to deterministic synthesis whenever model config or model output is invalid
- `app/api/main.py`
  - wires `ModelSkillSuggester` into the global `SkillSuggestionService`
- `tests/unit/test_skill_suggestion.py`
  - added model-success and model-fallback tests

#### Behavior added
- skill suggestion can now be model-enhanced when local private model config is available
- model output is constrained to a narrow JSON blueprint shape
- deterministic fallback still guarantees the feature works without model access or under model failure

#### Validation
- Ran full test suite successfully
- Result: `61 passed`

### Module: model-enhanced self refinement with constrained fallback

Added an optional model-backed self-refinement proposal synthesizer while keeping the existing deterministic proposal path as the hard safety floor.

#### Added
- `app/services/model_self_refiner.py`
  - generates constrained self-refinement proposal JSON via the configured responses API
  - only targets proposal synthesis, not direct mutation
  - exposes availability checks so model enhancement remains optional

#### Updated
- `app/services/self_refinement.py`
  - now supports injected model self-refiner
  - still builds deterministic runtime_policy/workflow proposals first
  - falls back to deterministic proposals whenever model config or model output is invalid
- `app/api/main.py`
  - wires `ModelSelfRefiner` into the global `SelfRefinementService`
- `tests/unit/test_self_refinement.py`
  - added model-success and model-fallback tests

#### Behavior added
- self refinement can now be model-enhanced when local private model config is available
- model output is constrained to a narrow proposal JSON shape
- refinement remains proposal-before-apply; no direct model-driven mutation was added
- deterministic fallback still guarantees the feature works without model access or under model failure

#### Validation
- Ran full test suite successfully
- Result: `63 passed`

### Module: app shared context model and control-plane boundary docs

Added the first explicit app-local shared context model so apps can maintain internal execution context independently from the user-facing control plane.

#### Added
- `app/models/app_context.py`
  - `AppSharedContext`
  - `AppContextEntry`
- `app/services/app_context_store.py`
  - shared context creation
  - context stage/goal update
  - structured entry append
  - persistence via runtime state store
- `tests/unit/test_app_context_store.py`
  - app context service and API tests

#### Updated
- `app/api/main.py`
  - added app context APIs
  - runtime persistence snapshot now includes `app_contexts`
- `app/core/errors.py`
  - added app context error mapping
- `docs/requirements.md`
  - documented app-local shared context and user-facing control plane boundary
- `docs/design.md`
  - documented control plane vs app runtime boundary and app shared context store
- `docs/testing.md`
  - added app shared context coverage to testing strategy

#### API endpoints added
- `GET /app-contexts`
- `GET /app-contexts/{app_instance_id}`
- `POST /app-contexts/{app_instance_id}`
- `POST /app-contexts/{app_instance_id}/entries`

#### Behavior added
- apps can now maintain app-local shared context independently from the control-plane AI
- app contexts can store structured facts, artifacts, decisions, questions, constraints, and open loops
- the system can now expose app-level goal/stage state without forcing all internal execution back through the user-facing control plane

#### Validation
- Ran full test suite successfully
- Result: `65 passed`

### Module: documentation consolidation for requirements, design, and testing

Reorganized the project documents into a coherent set aligned with the current implemented architecture.

#### Updated
- `docs/requirements.md`
  - rewritten around current scope and implemented milestones
  - clarified app / skill / blueprint / instance boundaries
  - aligned requirements with actual runtime, data, event, and evolution capabilities
- `docs/design.md`
  - rewritten into a single coherent architecture document
  - aligned service map, object model, runtime flows, data model, and evolution chain with the current codebase
- `docs/testing.md`
  - rewritten into a testing strategy document aligned with the implemented test matrix and development discipline

#### Documentation goals achieved
- removed duplicated / conflicting structure from older drafts
- aligned docs with the current implemented milestone instead of a purely hypothetical future system
- made the logic consistent across requirements, design, and testing
- clarified near-term gaps after the current milestone

#### Validation
- Ran full test suite after documentation update
- Result: `50 passed`

## 2026-03-18

### Module: documentation update for system skills, app config, and runtime capability inference

Documented the next-step platform direction for deterministic system defaults, app configuration, skill capability tags, and automatic runtime-profile inference.

#### Updated
- `docs/requirements.md`
  - added requirements for built-in system skills
  - added per-app deterministic config surface expectations
  - added skill classification and app-profile resolution requirements
  - added direct-start/offline-capable behavior requirements
  - added intelligence invocation governance requirements
- `docs/design.md`
  - separated network availability from intelligence availability
  - described capability-tagged skills and runtime profile aggregation
  - documented app-config as a built-in system capability
  - documented policy-driven ask-before-intelligence behavior
- `docs/testing.md`
  - updated suite status to `81 passed`
  - added future test coverage targets for capability classification, direct start, and invocation governance

#### Design intent clarified
- users should not manually choose low-level runtime classes for apps
- the platform should infer app runtime posture from skill metadata
- runtime build-time skills and runtime skills should remain distinct
- optional intelligence should not automatically consume user tokens
- no-network and no-intelligence are separate runtime conditions

### Module: documentation update for skill package contracts and runtime adapters

Extended the documentation direction so skills are treated as runnable capability packages with explicit contracts, adapters, and validation rules.

#### Updated
- `docs/requirements.md`
  - added requirements for skill packaging, skill contracts, runtime adapters, and app/skill validation
- `docs/design.md`
  - documented skill package shape, unified execution envelope, runtime adapter model, orchestrator-mediated dispatch, and compile-time validation expectations
- `docs/testing.md`
  - added future validation targets for manifest/schema/adapter checking and runtime/build-time skill separation

#### Design intent clarified
- skills should be packaged as structured runtime units rather than symbolic names only
- skill execution should flow through a unified runtime/orchestrator surface
- skill contracts should be machine-readable for compile-time validation and safe composition
- adapter diversity (callable/script/rpc/binary/frontend) should not break runtime governance or observability

### Module: documentation update for dedicated skill design principles reference

Moved the core-skill principle table into its own dedicated document so future skill design has a stable, explicit reference point.

#### Added
- `docs/skill-design-principles.md`
  - canonical reference for core skill design principles
  - core-skill principle table
  - design checklist for future core skills

#### Updated
- `docs/requirements.md`
  - records the dedicated canonical reference path
- `docs/design.md`
  - now points to the standalone skill design principles document
- `docs/testing.md`
  - references the standalone document in future validation targets
- `README.md`
  - documents the dedicated skill design principles doc path
- `TOOLS.md`
  - records the dedicated doc path for future implementation work

#### Design intent clarified
- future core skills should be reviewed against one dedicated canonical reference document
- the skill design principles should remain stable and discoverable outside the broader architecture doc
- core skill roles, locality, intelligence posture, and contract strictness should stay explicit

## 2026-03-18

### Module: minimal skill metadata and capability profile registration

Started moving skills from symbolic names toward structured runtime metadata.

#### Implemented
- extended `SkillRegistryEntry` with:
  - `capability_profile`
  - `runtime_adapter`
- introduced `SkillCapabilityProfile` with:
  - intelligence level
  - network requirement
  - runtime criticality
  - execution locality
  - invocation default
  - risk level
- registered built-in system skills and `skill.echo` with explicit capability metadata in the API bootstrap layer
- added test coverage verifying skill metadata is exposed through the skill listing API

#### Design intent clarified
- skills should no longer be treated as names only once they become runtime-visible
- capability metadata should be present before full manifest/contract work begins
- built-in system skills should model the same metadata shape expected of future skills

### Module: minimal skill manifest and contract references

Added a minimal manifest layer so registered skills begin to expose package-style structure in addition to capability tags.

#### Implemented
- introduced `SkillManifest`
- introduced `SkillContractRef`
- extended `SkillRegistryEntry` with optional `manifest`
- registered built-in system skills and demo skill with minimal manifests
- added tests verifying manifests are exposed via the skill listing API

#### Design intent clarified
- manifest/contract evolution should be gradual and backward compatible
- capability tags and manifest structure should coexist during migration
- runtime-visible system skills should expose both operational metadata and package-style identity

### Module: minimal manifest validation on skill registration

Added the first validator layer so manifest structure begins to participate in registration-time checks.

#### Implemented
- introduced `SkillManifestValidatorService`
- registration now validates manifest consistency when a manifest is present
- validator currently checks:
  - manifest skill id matches registry entry skill id
  - manifest name matches registry name
  - manifest version matches active version
  - manifest runtime adapter matches registry runtime adapter
- added validator-focused unit tests and a negative registration test

#### Design intent clarified
- manifest data should not be passive metadata only
- validation should be incremental and preserve backward compatibility for entries without manifests
- registration-time checks are the first step toward fuller skill package validation

### Module: minimal runtime adapter model

Added the first explicit adapter-spec layer so runtime adapter intent begins to exist separately from plain string labels.

#### Implemented
- introduced `SkillAdapterSpec`
- extended `SkillManifest` with `adapter`
- validator now checks adapter-kind alignment with runtime adapter
- `SkillRuntimeService` now distinguishes callable vs script adapters
- script adapters are recognized but intentionally fail with a clear not-implemented error
- added unit coverage for callable execution and script-adapter rejection

#### Design intent clarified
- runtime adapters should become first-class execution specs rather than opaque strings
- adapter evolution can proceed incrementally without pretending unsupported adapters already work
- explicit not-implemented behavior is better than silently treating every adapter like callable

### Module: minimal script adapter execution

Promoted the script adapter from placeholder status to a minimal runnable execution path.

#### Implemented
- `SkillRuntimeService` can now execute `script` adapters via local subprocess
- request payload is serialized as JSON to stdin
- script result is read as JSON from stdout and parsed into `SkillExecutionResult`
- added a fixture script and adapter runtime unit coverage

#### Current constraints
- script execution is local-only
- JSON stdin/stdout only
- no streaming or interactive session support yet
- fixed timeout for the initial implementation

#### Design intent clarified
- script adapter support should be real, not nominal
- the first supported non-callable adapter should stay narrow and deterministic
- JSON request/response envelopes are the foundation for future adapter expansion

### Module: context runtime view serialization hardening

Identified a hang during pytest shutdown around context/runtime-view serialization and made the context skill return path more defensive.

#### Implemented
- hardened `list_runtime_view` to return plain JSON-friendly dict payloads
- added a targeted regression test for JSON serialization of context runtime views

#### Design intent clarified
- system skill outputs should be aggressively normalized to JSON-friendly payloads
- runtime/view helper paths should avoid leaking nested model objects into higher-level serialization

### Module: bootstrap cleanup for built-in skill registration

Reduced duplication in the API bootstrap layer by extracting built-in skill registration and handler wiring into a dedicated helper module.

#### Implemented
- added `app/services/system_skill_registry.py`
- moved built-in skill registry entry construction into shared helper functions
- moved built-in handler registration into a shared helper
- reduced repeated manifest/capability boilerplate in `app/api/main.py`

#### Design intent clarified
- bootstrap wiring should stay readable as the number of built-in skills grows
- system skill definitions should be centralized to reduce drift between metadata and handler registration

### Module: bootstrap extraction for runtime construction and built-in handlers

Further reduced `app/api/main.py` complexity by extracting service construction and built-in handler assembly into dedicated bootstrap modules.

#### Added
- `app/bootstrap/runtime.py`
- `app/bootstrap/skills.py`

#### Implemented
- moved service graph construction into `build_runtime()`
- moved built-in handler creation/wiring into `bootstrap_builtin_skills()`
- reduced `main.py` to mostly composition and route declarations

#### Design intent clarified
- runtime bootstrap and API route declaration should evolve independently
- service graph construction should be centralized for easier future refactors and testing

### Module: demo catalog/bootstrap extraction

Moved demo blueprint registration and catalog seeding out of `app/api/main.py` so the entry file keeps shrinking toward route-only composition.

#### Added
- `app/bootstrap/catalog.py`

#### Implemented
- extracted built-in demo app blueprint registration
- extracted built-in catalog entry registration
- reduced direct bootstrap noise in `main.py`

#### Design intent clarified
- sample/demo bootstrapping should remain easy to find without cluttering API route definitions
- bootstrap data and runtime wiring should stay separated from route implementation details

### Module: organize system skill services under a dedicated directory

Grouped the platform default skill implementations into a clearer service subtree while keeping old import paths as compatibility wrappers.

#### Added
- `app/services/system_skills/app_config.py`
- `app/services/system_skills/state_audit.py`
- `app/services/system_skills/context.py`
- `app/services/system_skills/README.md`

#### Updated
- `app/services/app_config_service.py`
- `app/services/system_skill_service.py`
- `app/services/context_skill_service.py`
  - now act as thin compatibility exports
- `TOOLS.md`
  - notes the new system-skill directory layout

#### Design intent clarified
- default system skills should be easy to find as one family of services
- migration should preserve existing imports while improving layout

### Module: internal import cleanup and code-structure note

Started switching internal wiring toward the new `app/services/system_skills/` package and added a lightweight structure guide for future development.

#### Added
- `docs/code-structure.md`

#### Updated
- `app/bootstrap/runtime.py`
  - now imports system-skill implementations from the new package directly
- `README.md`
  - points to `docs/code-structure.md`
- `TOOLS.md`
  - points to `docs/code-structure.md`

#### Design intent clarified
- the new system-skill package should become the primary import target over time
- a small structure map is useful while the codebase is still actively being reorganized

### Module: stabilize system.context runtime-view tests

Hardened the system-context test path so runtime-view validation no longer depends on reused on-disk test directories.

#### Updated
- `app/services/app_context_store.py`
  - added the missing `LifecycleError` import used by runtime-view fallback handling
- `tests/unit/test_context_runtime_view_serialization.py`
  - expanded coverage for both runtime-present and runtime-unavailable serialization paths
- `tests/unit/test_system_context_skill.py`
  - switched test storage paths to pytest-managed `tmp_path` directories to avoid cross-run state pollution

#### Validation
- Ran targeted regression tests successfully
- Result: `3 passed`

#### Design intent clarified
- file-backed runtime tests should isolate their storage roots per test run
- system skill serialization tests should cover both happy-path and fallback-path payload shapes

### Module: isolate workflow and system-skill tests from on-disk state reuse

Continued converting file-backed unit tests away from fixed `data/test-*` directories so repeated local runs do not inherit stale runtime JSON state.

#### Updated
- `tests/unit/test_workflow_executor.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_skill_runtime.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_interaction_gateway.py`
  - switched file-backed stores and persistence checks to pytest `tmp_path`
- `tests/unit/test_system_app_config_skill.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_system_state_and_audit_skills.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`

#### Validation
- Ran focused regression suite successfully
- Result: `19 passed`

#### Design intent clarified
- unit tests that exercise the JSON file runtime store should use unique temporary roots by default
- repeated local/CI runs should not depend on manual cleanup of prior `data/test-*` artifacts

### Module: isolate refinement and registry/event tests from persistent test state

Extended the `tmp_path` migration to additional file-backed tests in the refinement, registry, and event areas.

#### Updated
- `tests/unit/test_self_refinement.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_priority_analysis.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_registry_installer.py`
  - switched file-backed stores and installer namespaces to pytest `tmp_path`
- `tests/unit/test_event_bus.py`
  - switched file-backed runtime store to pytest `tmp_path`

#### Validation
- Ran focused regression suite successfully
- Result: `13 passed`

#### Design intent clarified
- refinement and registry tests should be isolated from previously persisted runtime JSON just like workflow/runtime tests
- test stability improvements should be applied consistently across subsystems rather than only around the originally failing area

### Module: finish tmp_path migration for remaining file-backed unit tests

Completed another pass over the remaining fixed `data/test-*` unit tests to reduce state leakage across repeated runs.

#### Updated
- `tests/unit/test_proposal_review.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_workflow_subscription.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_app_config_service.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_app_data_store.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_practice_review.py`
  - switched file-backed stores and namespaces to pytest `tmp_path`
- `tests/unit/test_context_runtime_view_serialization.py`
  - aligned the new serialization regression tests with pytest `tmp_path`

#### Validation
- Ran focused regression suite successfully
- Result: `13 passed`

#### Design intent clarified
- all new and recently touched file-backed unit tests should default to isolated temporary roots
- regression tests added during bug fixing should follow the same isolation rules as the rest of the suite
