# AgentSystem / App OS Design

## 1. Design Intent

AgentSystem is designed as an **App OS** rather than a single assistant runtime.
Its core job is to manage apps as long-lived system objects while allowing the system to learn from runtime practice and gradually improve its reusable capability layer.

The current design direction is:
- user interacts with the system through a control plane and unified gateway
- apps are defined as blueprints, installed as instances, and governed by runtime policy
- apps own separated namespaces for business and runtime data
- apps also own app-local shared context for internal execution and coordination
- apps can react to events and schedules
- runtime behavior can be reviewed into experience
- experience can be turned into candidate skills

---

## 2. Core Design Principles

### 2.1 App is the main product object
Users primarily interact with apps, not with low-level skills.

### 2.2 Skill is a reusable capability asset
Skills are versioned, replaceable, suggestible capability units. They are dependencies of apps and builders, not usually the top-level product unit.

### 2.3 Definition and instance are separate
- blueprint = definition template
- instance = installed lifecycle object

### 2.4 Data and runtime are separate
- app data persists with the app instance
- runtime state persists only as needed for recovery and supervision

### 2.5 Intelligence is selective
The system should use deterministic services first, and use intelligence mainly for abstraction, suggestion, diagnosis, and generation.

### 2.6 System should evolve from practice
The intended evolutionary chain is:
- practice
- experience
- skill suggestion
- future workflow/app refinement

---

## 3. High-level Architecture

```text
[ User / API / Chat Input ]
            |
            v
[ Control Plane / Interaction Gateway ]
            |
            +------------------------------+
            |                              |
            v                              v
[ App Catalog ] ----> [ App Registry ] ----> [ App Installer ]
            |                                 |
            |                                 v
            |                          [ App Instance ]
            |                                 |
            v                                 v
[ Lifecycle Manager ] <----> [ Runtime Host ] <----> [ Scheduler ]
                                      |                  |
                                      |                  v
                                      |            [ Event Bus ]
                                      |
                                      +------> [ App Shared Context Store ]
                                      |
                                      v
                              [ App Data Store ]
                                      |
                                      v
                              [ Runtime Persistence ]

[ Experience Store ] <---- [ Practice Review ] <---- [ Event Log + Data Records ]
        |
        v
[ Skill Suggestion Service ]
```

---

## 4. Object Model

## 4.1 Capability Layer

### Module
Deterministic building block such as file, state, event, auth, config, or network operations.

### Skill
Reusable capability asset, versioned and controlled. Skills may be manually replaced, rolled back, enabled, disabled, or suggested from experience.

## 4.2 Definition Layer

### RequirementIntent
Structured routing output from user requirement intake.

### DemonstrationRecord
Observed user demonstration used for extraction.

### AppBlueprint
Defines:
- goal
- roles
- tasks
- workflows
- views
- required modules
- required skills
- storage plan
- runtime policy

### RuntimePolicy
Defines:
- execution mode (`service | pipeline`)
- activation mode
- restart policy
- persistence level
- idle strategy
- restart limit

## 4.3 Runtime Layer

### AppInstance
Installed lifecycle object containing:
- blueprint id
- owner user id
- status
- installed version
- execution mode
- runtime policy
- data namespace root

### LifecycleEvent
Represents state transitions.

### RuntimeLease
Tracks current runtime health and heartbeat.

### RuntimeCheckpoint
Captures resumable runtime snapshots.

### ScheduleRecord
Defines interval or event-based task triggering.

### SupervisionPolicy / SupervisionStatus
Define restart behavior and current supervision state.

### EventRecord / EventSubscription
Represent internal system events and their subscriptions.

## 4.4 Data / Evolution Layer

### DataNamespace
Represents an isolated namespace for:
- app_data
- runtime_state
- system_metadata
- skill_assets

### DataRecord
Structured record within a namespace.

### AppSharedContext / AppContextEntry
Structured app-local shared execution context containing:
- app identity and description
- current goal and current stage
- grouped entries for facts, artifacts, decisions, questions, constraints, and open loops

This context is separate from the user-facing control AI context and is intended to support autonomous app-local execution.

### ExperienceRecord
Structured runtime, demonstration, or human knowledge asset.

### SkillBlueprint
Structured candidate reusable skill artifact.

### PracticeReviewResult
Structured output of reviewing recent runtime practice.

### SkillSuggestionResult
Structured output of turning experience into a candidate skill blueprint.

---

## 5. Layered Services

## 5.1 Requirement Routing
Current implementation uses a rule-driven `RequirementRouter` to classify user intent and decide whether demonstration is needed.

## 5.2 Skill Control Interface
`SkillControlService` acts as a protected human override layer for skill lifecycle control.

## 5.3 Experience Store
`ExperienceStore` is currently an in-memory asset store for:
- experiences
- skill blueprints

It supports linking skill blueprints to related experiences.

## 5.4 Demonstration Extraction
`DemonstrationExtractor` converts demonstrations into:
- an experience record
- a skill blueprint

## 5.5 App Registry and Installer
`AppRegistryService` stores blueprint definitions.
`AppInstallerService` converts blueprints into installable instances and provisions namespaces.

## 5.6 Lifecycle and Runtime
`AppLifecycleService` manages valid state transitions.
`AppRuntimeHostService` manages runtime lease, checkpoint, pending tasks, and health updates.

## 5.7 Scheduler and Supervisor
`SchedulerService` manages interval and event schedules.
`SupervisorService` manages failure observation, restart attempts, and circuit-open protection.

Proposal review and priority analysis now also support context-aware operation:
- review records can retain context-derived notes
- proposal prioritization can consider open loops, decisions, constraints, and paused stage
- contradiction and recommendation output can reflect app-local execution context

## 5.8 Event Bus
`EventBusService` records internal events, supports subscriptions, and triggers event schedules.

## 5.9 App Data Store
`AppDataStore` provisions and manages namespaces and records for apps and global skill assets.

## 5.10 Interaction Gateway / Control Plane Boundary
`InteractionGateway` is the main command entry point for the user-facing control plane.
It routes user commands to app catalog entries and triggers install/open/run flows.

The control plane is responsible for:
- user-facing interaction
- app routing and orchestration
- high-level intervention
- inspection and explanation

The control plane is not required for every app-internal execution step.

## 5.11 App Shared Context
`AppContextStore` maintains app-local shared execution context so an app can continue internal work without routing every step through the control plane.

The current implementation now binds shared context into install and interaction flows:
- installer ensures a context exists when an app instance is provisioned
- blueprint goal can seed the initial current goal
- service-app open updates current stage/goal and records the latest user command as an open loop
- pipeline execution records the latest run artifact and marks the context archived after completion
- context inspection can optionally include runtime overview for joined operational debugging

## 5.12 Practice Review
`PracticeReviewService` reviews recent runtime events and data records, then distills them into an experience.

The current implementation also folds app shared context into review output:
- current goal and stage can enrich the practice summary
- recent context entries can become review evidence and tags
- the resulting experience can retain more app-local execution state instead of only event/data traces

## 5.12 Skill Suggestion
`SkillSuggestionService` generates candidate reusable skill blueprints from stored experiences.

---

## 6. Main Runtime Flows

## 6.1 User command -> service app
1. user command enters interaction gateway
2. catalog matches the app
3. installer ensures the instance exists
4. lifecycle ensures app reaches `installed`
5. runtime host starts the service app
6. app remains available for ongoing work

## 6.2 User command -> pipeline app
1. user command enters interaction gateway
2. catalog matches a pipeline app
3. installer ensures the instance exists
4. runtime host starts the app
5. task is enqueued
6. runtime host stops the app after execution

## 6.3 Runtime event -> event schedule
1. event bus publishes an event
2. scheduler locates matching event schedules
3. pending task is enqueued into runtime host
4. event is recorded in persistent log

## 6.4 Runtime practice -> experience
1. runtime generates event log and data records
2. practice review inspects recent facts
3. app shared context is joined as local execution evidence
4. review generates an experience summary
5. experience is stored for later reuse

## 6.5 Experience -> suggested skill
1. a stored experience is selected
2. self-refinement can combine experience with app shared context to generate patch proposals
3. skill suggestion service generates a candidate skill blueprint
4. suggestion may remain advisory or be persisted into the skill store

---

## 7. State and Lifecycle Design

## 7.1 App lifecycle states
Supported states:
- draft
- validating
- compiled
- installed
- running
- paused
- stopped
- failed
- upgrading
- archived

## 7.2 App execution modes
### Service app
Used for long-running, event-aware, reopenable app instances.

### Pipeline app
Used for one-shot execution, after which runtime stops but data may remain.

## 7.3 Runtime supervision model
The supervision model supports:
- failure observation
- restart attempts
- restart caps
- circuit-open protection

---

## 8. Data Design

## 8.1 Namespace split
Each installed app gets:
- `app_data`
- `runtime_state`
- `system_metadata`

The system also maintains:
- `global:skill_assets`

## 8.2 Persistence split
Current file-based persistence stores:
- app instances
- lifecycle events
- runtime leases
- runtime checkpoints
- runtime tasks
- schedules
- supervision state
- registry entries
- registry blueprints
- namespaces
- data records
- event log
- event subscriptions

## 8.3 Why this split matters
This prevents app business data from being confused with ephemeral runtime state, and keeps skill assets from turning into hidden app data.

---

## 9. Intelligence / Evolution Design

## 9.1 Demonstration to experience and skill
Demonstration extraction is the first path from observed user behavior to reusable system assets.

## 9.2 Practice review as runtime learning
Practice review creates a feedback loop from actual runtime behavior to explicit experience records.

## 9.3 Experience to skill suggestion
Skill suggestion turns explicit experience into reusable capability proposals without automatically mutating the system.

This keeps a safe evolution boundary:
- observe
- summarize
- suggest
- optionally persist
- future human or system approval can decide actual adoption

---

## 10. Safety and Control Boundaries

### 10.1 Immutable human override
The skill control surface should remain protected and deterministic.

### 10.2 Suggestion is not direct mutation
Practice review and skill suggestion should not silently rewrite core skills or app structure.

### 10.3 Runtime services remain deterministic
Lifecycle, installer, data provisioning, scheduling, and event dispatch should remain deterministic.

---

## 11. Current Implemented Boundary Summary

At the current stage the codebase already implements a meaningful subset of the target design:
- requirement routing
- skill control
- experience store
- demonstration extraction
- lifecycle manager
- runtime host
- scheduler
- supervisor
- interaction gateway
- runtime persistence
- app registry
- installer
- app data namespaces
- event bus
- practice review
- experience-to-skill suggestion

This means the project is no longer just schema scaffolding; it already contains an initial operating skeleton plus an early practice-driven evolution loop.

---

## 12. Near-term Design Gaps

The next most important missing pieces are:
- richer workflow execution beyond the current minimal deterministic executor
- app data operations as workflow primitives
- contradiction / priority analysis for better focus
- app/workflow refinement based on suggested skills
- stronger permission and policy enforcement
- durable production-grade persistence backends

Current implementation note:
- a minimal workflow executor now exists for workflow execution
- it supports deterministic step skeletons for `state.set`, `state.get`, and event emission
- it also includes placeholders for `human_task` and `skill` steps so workflows can preserve unresolved work in context
- step outputs can now be passed into later steps through lightweight `$from_step` / `$from_inputs` references
- step-level conditional execution is supported through simple `when` checks
- workflow execution returns an aggregated outputs summary for completed/skipped steps and step outputs
- event-driven workflow subscriptions can now auto-trigger workflow execution from published internal events
- `skill` steps now support a minimal dispatch contract through `SkillRuntimeService`, with registered handlers, structured request/result payloads, and execution persistence
- execution can write app data, append shared-context artifacts, persist runtime execution records, and publish internal events
