# AgentSystem / App OS Design

## 1. Design Intent

Detailed companion reference: `docs/telemetry-and-upgrade-logging.md`.


AgentSystem is designed as an **App OS** rather than a single assistant runtime.
Its core job is to manage apps as long-lived system objects while allowing the system to learn from runtime practice and gradually improve its reusable capability layer.

The current design direction is:
- user interacts with the system through a control plane and unified gateway
- the core platform stays thin and standard-oriented while higher-order behaviors should remain skill-centric wherever practical
- runtime operational telemetry and upgrade/evolution evidence are separated by design
- self-iteration must remain evidence-bound, user-governed, and cost-aware
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

A lightweight requirement-understanding loop should exist before blueprint generation:
- first route the request (`app | skill | hybrid | unclear`)
- then build a minimal structured requirement spec
- then decide whether the request is ready, needs clarification, or needs demonstration
- only after that should later generation flows consume the request as a candidate blueprint/app/skill definition input

Network reachability and intelligence availability are separate concerns:
- an app may have network but should still avoid intelligent calls by default
- an app may be offline-capable while still carrying optional intelligent enhancements
- intelligent invocation should be governed by policy, not by mere model availability

### 2.6 System should evolve from practice
The intended evolutionary chain is:
- practice
- experience
- skill suggestion
- future workflow/app refinement

This should be treated as a disciplined world-model loop rather than a purely verbal planning loop.

### 2.7 Thin core, skill-centric higher-order behavior
The platform core should own:
- standard contracts
- telemetry/event envelopes
- collection policy and safety boundaries
- primitive compare / evaluate / publish / rollback / archive operations

Higher-order workflows such as:
- next-version generation
- replay/test orchestration
- acceptance review
- archive/report generation
- publish/rollback orchestration

should remain skill-oriented wherever practical. This preserves extensibility while keeping the core implementable and governable.

### 2.8 Runtime telemetry and upgrade evidence are separate
The system should maintain two distinct observation planes:
- lightweight online telemetry for runtime/control-plane usage
- append-only upgrade/evolution evidence for replay, acceptance, and self-iteration

This separation reduces online cost while preserving the historical evidence needed for improvement.

### 2.9 Cost-aware optimization, not intelligence-first optimization
Candidate improvements should be judged by:
- user experience
- task success
- token efficiency
- latency efficiency
- stability and rollback posture

The design should prefer reducing unnecessary work before adding heavier intelligence.

### 2.10 Core-skill toolchain before broad self-expansion
The preferred long-term expansion path is:
- keep the platform core small
- establish a governed core-skill toolchain for generation, testing, acceptance, archive, publish, and rollback
- let that toolchain produce and govern additional ordinary skills
- reserve direct core changes for standards, safety boundaries, and primitive runtime/governance capabilities

In other words, the system should mainly grow by adding and governing skills, not by continuously enlarging the core platform.

This world-model loop should be treated as a disciplined runtime-governed process rather than a purely verbal planning loop:
- investigate reality through runtime signals, user corrections, and concrete outcomes
- transform observations into explicit contradictions, hypotheses, and proposed changes
- test those changes in bounded workflows before wider rollout
- keep revision tied to evidence, not only narrative plausibility
- record the loop as first-class system objects (hypothesis, experiment, verification result, rollout decision) so refinement is inspectable rather than hidden inside one-shot proposal text
- persist those refinement-loop objects through the runtime store and expose query surfaces so system learning remains visible across process rebuilds
- keep verification execution pluggable: runtime paths may invoke real grouped regression, while tests should be able to inject a bounded executor so learning-loop regression coverage stays fast and deterministic
- treat rollout as a governable queue, not only an immediate promote/hold judgment; queue items and overview read models should make the learning loop operationally visible
- rollout queue items should support explicit lifecycle transitions (approve/apply/reject/rollback) so refinement promotion is operationally governed rather than hidden in one-off side effects
- the system should preserve negative learning signals through failed-hypothesis records and expose recent refinement history through dashboard read models, so self-improvement can incorporate both success and disproof
- refinement loop decisions should become failure-aware: previously disproven hypotheses should raise repeat-risk scores, annotate verification with gating reasons, and block naive promotion of repeated strategies
- refinement governance should expose lightweight operator read models parallel to workflow observability, including filtered rollout-queue pages, failed-hypothesis archive pages, and aggregate stats summaries keyed by app/hypothesis/proposal filters
- refinement governance should also expose a dashboard-style aggregate surface that composes overview + stats + recent queue/failure slices so operators can review learning-governance state through one higher-level read model
- refinement operator endpoints should share a small API-side filter builder, mirroring workflow observability, so future query knobs stay aligned across queue/stats/dashboard surfaces
- refinement operator workflows should also expose a one-call summary read model that merges proposal inventory, review state, latest priority decision, and governance dashboard slices so operators do not need to stitch multiple endpoints together for routine triage
- refinement governance API-path coverage may be maintained as a dedicated slower integration slice rather than being forced into the main workflow golden path, preserving faster regression loops for the common operator path
- runtime wiring should support test-only opt-outs for model-backed self-refinement and grouped-regression verification so deterministic API-path tests can exercise refinement flows without accidentally invoking remote model calls or recursive full-suite regressions
- model-backed self-refinement should be explicit opt-in at runtime wiring time (`AGENTSYSTEM_ENABLE_MODEL_REFINER=1`), with fallback proposal synthesis remaining the default path when the feature is not deliberately enabled
- refinement governance page-style responses should mirror workflow observability structure by nesting counts/has-more state under `meta`, which reduces contract drift between the two operator surfaces
- shared operator-facing pagination semantics should live in a common contract model (`OperatorPageMeta`), with domain-specific extensions such as workflow unresolved counts layering on top instead of redefining the whole shape
- shared operator-facing query semantics should likewise live in a common base filter model (`OperatorFilterParams`), with workflow/refinement filters layering on domain-specific selectors without redefining common pagination/time-window fields
- shared operator dashboard semantics should live in a common overview/stats core (`OperatorDashboardCore`), while domain-specific dashboards add their own recent timeline/queue/archive sections on top
- API-side operator filter construction should be centralized in a shared helper module (`app/api/operator_filters.py`), while thin compatibility wrappers may remain temporarily to avoid churn during migration
- generated/runtime skill manifests should begin carrying explicit risk metadata (`risk_level`, network/filesystem/shell allowances), and script adapters should be validated against an allowlisted command-prefix policy before registration/runtime use
- generated app assembly should enforce a default deny gate for risky skills (e.g. networked, shell, filesystem-write, or explicitly high-risk manifests), so self-iteration cannot silently turn high-risk assets into auto-install/auto-run apps
- generated-app policy gates should emit structured skill diagnostics (stage=`assemble`, kind=`policy_blocked`) with machine-readable policy reasons, so future approval or override layers can consume them cleanly
- reviewer-managed skill risk decisions should live in a dedicated persisted policy store, and generated app assembly should consult active overrides before enforcing default deny behavior for risky skills
- risk governance should emit and persist a lightweight event trail (`policy_blocked`, `override_approved`, `override_revoked`) so audit and observability layers can expose more than the latest policy decision snapshot
- the risk policy layer should also provide stats and dashboard-shaped read models (overview + stats + recent events) consistent with the broader operator-surface direction in the system
- app rollout governance should extend beyond activate/rollback controls to include explicit release-to-release comparison, so operators can inspect note / required-skill / runtime-policy / runtime-profile / app-shape drift before promoting or reverting a release
- app rollout governance should also expose a release-history summary contract, so control-plane readers do not need to reconstruct active/draft/rollback posture or timeline ordering from raw release lists alone
- app registry/control-plane reads should also provide a single summary contract for common operator views, aggregating active release posture, release counts, rollback availability, app shape, and runtime profile without requiring client-side joins across multiple registry endpoints
- app governance should also expose a registry-wide overview contract so operators can triage draft-bearing or rollback-relevant apps before drilling into per-app compare/history surfaces
- app governance should further expose an explicit attention/triage contract that explains *why* an app needs review (draft present, rollback target available, recently rolled back) instead of forcing operators to infer urgency from overview fields alone
- app operator surfaces should also support lightweight action records (for example acknowledging or dismissing an attention case) so review state can affect what the triage queue shows without requiring full release-state mutation
- skill suggestion / self-iteration entry paths should be able to consume risk governance summaries so generated recommendations can adapt toward lower-risk execution forms when the governance layer shows recent blocking pressure
- that governance context should include blueprint-materialization policy pressure specifically, allowing suggestions to bias not only toward lower-risk execution but also toward callable materialization when shell/script forms are being blocked
- blueprint materialization should consume `prefer_callable_materialization` as an active default-selection hint when the caller does not explicitly choose an adapter, so governance-aware defaults influence real artifact shape selection
- governance-aware suggestions should project that bias into blueprint-level `safety_profile` metadata (preferred risk level, local-only preference, shell/network/write allowances) so later generation/materialization stages can inherit safer defaults
- `SkillFactoryService` should expose a creation-defaults bridge from `SkillBlueprint.safety_profile` into concrete capability/risk defaults, even before the full generated-skill authoring pipeline consumes it end-to-end
- `SkillFactoryService` should also expose a blueprint-to-`SkillCreationRequest` bridge so governance-aware defaults can enter the concrete request object used by later materialization/registration flows
- the API layer should expose blueprint materialization as a first-class path, allowing stored `SkillBlueprint` records to become real skills while preserving the request defaults derived from governance-aware safety metadata
- blueprint materialization responses should expose both the intermediate creation request and the final registered skill state so governance-aware propagation can be validated end-to-end
- blueprint materialization should interpret safety metadata as active policy, not passive annotation: for example, low-risk blueprints should be able to block shell/script materialization unless a future explicit override layer authorizes it
- blueprint materialization should consult skill risk overrides under a dedicated `blueprint_materialization` scope before enforcing shell/script blocks, keeping approval logic aligned with the existing risk-governance subsystem
- blueprint-derived risk defaults should not stop at request construction: they must remain part of the concrete `SkillCreationRequest` contract and flow through skill authoring into the final `SkillManifest`, so validators and downstream governance inspect the same risk state the blueprint materialization logic intended
- when a scoped blueprint-materialization override intentionally authorizes shell/script materialization, the resulting authored manifest should carry explicit elevated shell-risk metadata rather than relying on an invisible side channel, preserving consistency across API diagnostics, manifest validation, registry state, and future audit surfaces
- generated app assembly should reuse `AppProfileResolverService` so blueprint skeleton defaults (execution mode, idle behavior, operator-facing overview/run/activity views, and the default generated-agent task) reflect the runtime properties of the selected skills instead of always emitting the same bare service shell
- the inferred `AppRuntimeProfile` should be promoted into both generated blueprints and registry-entry summaries, not kept only inside installer/runtime state, so pre-install control-plane reads and generated-app UIs can consume the same normalized runtime capability view that installation later persists into `AppInstance`
- generated app assembly should also perform a lightweight app-shape classification using available skill metadata (ids, descriptions, tags, and basic schema field signals) so the emitted role/task/view wording differs across text-oriented apps, structured-data transforms, and multi-step pipelines without requiring manual blueprint editing
- the same inferred app runtime profile exposed pre-install in blueprints/registry summaries should also be returned from install results, keeping pre-install and post-install control-plane reads aligned around one normalized runtime capability contract
- lightweight generated-app shape classification should also persist into explicit `app_shape` fields on `AppBlueprint`, `AppRegistryEntry`, and `AppInstallResult`, leaving human-facing wording as a presentation layer rather than the only place where app-type semantics exist

---

## 3A. Telemetry and upgrade-evidence architecture

The observation layer should be split into two coordinated but distinct planes.

### 3A.1 Online telemetry plane
This plane serves ordinary runtime and control-plane needs.

It should hold lightweight, queryable records such as:
- interaction summaries
- step/invocation summaries
- token and latency totals
- success/failure outcomes
- explicit and implicit feedback
- version bindings across app / skill / agent / policy

This plane should stay cheap enough to keep enabled by default in light mode.

### 3A.2 Upgrade/evolution evidence plane
This plane serves replay, acceptance, version comparison, optimization, publish, and rollback analysis.

It should use:
- append-only writing
- time-sliced files
- JSONL-oriented event storage
- event-first records with optional aggregate snapshots

It should not become a hard dependency for the online serving path.

### 3A.3 Collection policy model
Observation policy should support:
- global scope
- app scope
- skill scope
- agent scope
- task-type scope

Collection levels should support at least:
- off
- light
- medium
- heavy
- custom

Default posture should be light collection enabled, with expensive raw capture disabled unless explicitly enabled.

### 3A.4 Skill-extensible upgrade evidence
The core platform should define the baseline telemetry/event envelope.

Skills may append structured upgrade-oriented evidence on top of that envelope, for example:
- replay-sample reasons
- optimization hints
- domain-specific acceptance notes
- archive/report metadata

This preserves consistency while keeping higher-order evolution workflows skill-centric.

### 3A.5 Buildability boundary
The full conceptual model should not be interpreted as mandatory Day-1 scope.

The first implementation should prefer:
- light telemetry over heavy capture
- simple scope precedence over policy combinatorics
- append-only evidence substrate over full autonomous optimization loops

If a requirement cannot be delivered without making the core too heavy, it should be deferred, reduced, or shifted into a skill-level workflow.

### 3A.6 Core vs core-skill vs ordinary-skill boundary
The architecture should preserve three distinct layers:

- **core platform**: standards, runtime, registry, telemetry, policy, primitive governance operations
- **core skills**: the governed toolchain for generation, replay selection, testing, acceptance, archive, publish, and rollback workflows
- **ordinary skills**: business or domain skills that can be generated, revised, tested, accepted, published, and rolled back through the governed toolchain

Ordinary skills should not directly mutate platform-core standards or safety boundaries. Those changes must remain under explicit platform or core-skill governance.

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

Each skill should also carry capability tags used by the platform for automatic classification and runtime governance:
- intelligence level (`L0_deterministic | L1_assisted | L2_semantic | L3_autonomous`)
- network requirement (`N0_none | N1_optional | N2_required`)
- runtime criticality (`C0_build_only | C1_optional_runtime | C2_required_runtime`)
- execution locality (`local | hybrid | remote`)
- invocation default (`automatic | ask_user | explicit_only`)
- risk level

A skill should evolve toward a package model that includes:
- metadata / manifest
- machine-readable input/output/error contracts
- one or more runtime adapters
- dependency declarations
- examples and validation assets

To make normal skill authoring viable for self-iteration, the platform now also treats skill packaging as a first-class builder concern:
- `SkillAuthoringService` can generate consistent registry entries for callable and script skills
- built-in skills should use the same authoring path as normal skills where possible
- tests should verify authoring output separately from runtime execution so skill authors can localize failures faster

The next packaging layer now starts to exist as an API-facing factory path:
- `SkillFactoryService` can create a skill from an API request
- skill contracts are registered into the schema registry during creation
- the newly created skill is immediately smoke-tested through the runtime
- registered skills can be assembled into a minimal app blueprint through an interface instead of hand-written blueprint editing
- the generated app path can also be installed and executed immediately, which makes contract mismatches in the authoring path visible early
- generated app assembly now supports step-level inputs plus explicit step mapping declarations so multi-step generated apps can be composed without hand-editing blueprints
- generated mappings are compiled into the same declarative workflow reference shape already understood by runtime execution (`$from_step` / `$from_inputs`) instead of introducing a separate execution path
- generated mapping targets may point into nested downstream object fields, which keeps the API-facing assembly surface compact while preserving schema-first workflow validation
- generated mappings may also carry lightweight assembly-time transforms/defaults (for example lowercase/uppercase/stringify/wrap-object and literal/default injection) so common app-composition cleanup can happen without inventing a separate workflow DSL
- generated app assembly now computes conservative schema-based mapping suggestions between adjacent steps and returns unresolved required downstream fields
- high-confidence adjacent-step suggestions are auto-applied into generated workflow inputs only when they do not conflict with explicit user mappings or hand-authored step inputs
- generated skills should persist as assets and be reloaded into registry/runtime on bootstrap so the path becomes durable rather than session-only
- generated skill failures should surface as structured diagnostics with stage/kind/hint metadata instead of only raw error strings
- structured diagnostics should be able to carry a suggested retry request so failure handling can flow into the next generation attempt
- blueprint validation now has two semantics: strict validation for explicit operator/API checks, and a relaxed install-time path that still validates declared dependencies/contracts while allowing intentionally partial runtime workflows and demo catalog blueprints to install without every step skill being predeclared or prebootstrapped
- retry semantics now treat the latest `partial` execution as the canonical retry target so workflow recovery and observability remain aligned even when a partial run has no explicit failed step ids
- paginated workflow timeline responses should preserve backward-compatible list-like access (`len`, iteration, indexing) at the service model layer even though the public contract is page-shaped

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
- network behavior
- intelligence behavior
- invocation governance for optional intelligent steps

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

The intended next-step installer behavior is:
- inject a mandatory deterministic system skill baseline for every app
- initialize app configuration records and defaults
- classify runtime skills from capability tags
- resolve an app runtime profile from the installed skill set
- determine whether direct start, optional-intelligence start, or intelligence-required start is appropriate
- reject blueprints that deterministically violate runtime-skill validation rules before provisioning instances

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

The user-facing layer should not require users to manually pick low-level technical runtime classes such as offline-capable, intelligence-optional, or direct-start mode.
Instead, the control plane should expose the resolved app behavior after platform inference.

The control plane is responsible for:
- user-facing interaction
- app routing and orchestration
- high-level intervention
- inspection and explanation

The control plane is not required for every app-internal execution step.

## 5.11 App Shared Context
`AppContextStore` maintains app-local shared execution context so an app can continue internal work without routing every step through the control plane.

Alongside context, each app should also have a deterministic app-configuration surface exposed through a built-in `system.app_config` skill. This config surface should be separate from runtime state and separate from app-local reasoning context.

The current implementation now binds shared context into install and interaction flows:
- installer ensures a context exists when an app instance is provisioned
- blueprint goal can seed the initial current goal
- service-app open updates current stage/goal and records the latest user command as an open loop
- pipeline execution records the latest run artifact and marks the context archived after completion
- context inspection can optionally include runtime overview for joined operational debugging

## 5.12 Skill classification, runtime profile resolution, and invocation governance
The intended platform direction is to classify skills internally and aggregate them into an app runtime profile.

### Skill classification
A future `SkillClassificationService` should infer or validate capability tags from skill declarations, dependencies, and execution traits.

### App profile resolution
A future `AppProfileResolver` should aggregate runtime-capable skills and determine:
- highest runtime intelligence level
- runtime network requirement
- offline capability
- direct-start support
- default ask-before-intelligence behavior

Build-only skills should influence builder flows but should not inflate runtime classification for apps that no longer depend on intelligence once installed.

### Invocation governance
At runtime, the system should evaluate in order:
1. whether a step can be completed deterministically
2. whether network is required and available
3. whether intelligence is required and available
4. whether policy requires user confirmation before spending intelligence resources

This allows the platform to distinguish:
- no network
- no intelligence
- intelligence available but not worth invoking automatically

## 5.13 Skill package, contract, and adapter model
A skill should be treated as a runnable capability package rather than only a named dependency.

### Skill package shape
A future skill package should include at least:
- manifest metadata (`id`, `name`, `version`, purpose, category)
- capability tags
- runtime adapter declaration
- input/output/error schema references
- dependency declarations (modules, skills, binaries, services)
- validation examples and optional healthcheck metadata

The intended direction is schema-first:
- machine-readable contract/schema definitions should be the authoritative source for runtime envelopes
- adapter declarations should describe how execution happens, not redefine payload shapes independently
- future inspection/debugging surfaces should reuse the same contract source instead of inventing parallel representations

### Runtime adapters
The runtime layer should support multiple adapter types behind one execution contract:
- `callable` for in-process deterministic handlers
- `script` for local script execution with structured JSON input/output
- `rpc` for local or remote services
- `binary` for compiled executables or tools
- `frontend` / human-interaction adapters where user interaction is the execution surface

### Unified execution envelope
Regardless of adapter, skill execution should converge on a common request/response envelope so workflow orchestration, policy enforcement, observability, and retry remain uniform.

## 5.14 Skill orchestration and dispatch
Skill execution should be orchestrator-mediated by default.

The platform should prefer workflow/runtime dispatch over uncontrolled skill-to-skill direct calling so it can uniformly apply:
- schema validation
- timeout and retry handling
- audit and tracing
- permission checks
- network and intelligence policies
- cost/token governance

Direct skill-to-skill dependencies may still be declared, but dependency resolution should remain visible to the orchestrator/runtime layer.

## 5.15 Skill validation and compile-time checking
A future `SkillValidationService` should validate skill packages before they become active runtime capabilities.

Validation should be treated as three connected layers rather than one undifferentiated check:

### Package validation
Runs before a skill becomes active or installable.
It should cover at least:
- manifest completeness
- schema correctness
- adapter resolvability
- consistency between capability tags and actual runtime form
- compatibility between declared dependencies and the execution environment

### Compile-time app/workflow validation
Runs before app install or runtime activation.
It should cover at least:
- required skill existence
- workflow step / skill contract compatibility
- input/output mapping compatibility between steps
- misuse of build-only skills inside runtime execution paths
- mismatch between app runtime profile and runtime-critical skill requirements

### Runtime envelope validation
Runs at dispatch boundaries even after compile-time checks pass.
It should cover at least:
- request/input payload validation before adapter execution
- response/output/error validation after adapter execution
- adapter/runtime failures being distinguished from contract violations

This separation follows a stricter schema-first model:
- contract validity and adapter executability are different dimensions
- invalid packages should be blocked before activation
- invalid workflow wiring should be blocked before install/start
- invalid runtime payloads should fail as envelope violations rather than silently poisoning downstream steps

## 5.16 Core skill design principles reference
The canonical core-skill design principles are maintained in:

- `docs/skill-design-principles.md`

That document should be consulted before introducing new system-default skills, runtime-governance skills, or builder/intelligent platform skills.

## 5.17 Practice Review
`PracticeReviewService` reviews recent runtime events and data records, then distills them into an experience.

The current implementation also folds app shared context into review output:
- current goal and stage can enrich the practice summary
- recent context entries can become review evidence and tags
- the resulting experience can retain more app-local execution state instead of only event/data traces

## 5.18 Skill Suggestion
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
- suggested-skill refinement should not require callers to manually materialize each suggested blueprint first; the platform should provide a one-call orchestration path that materializes missing suggested skills and assembles an app blueprint from them
- stronger permission and policy enforcement
- durable production-grade persistence backends
- layered context compaction and retrieval

## 13. Layered Context Architecture

To avoid context explosion, runtime context should be split into layers instead of accumulated into one prompt-sized blob.

### 13.1 Layers
- **L0 Working Set**: current goal, stage, active constraints, current open loops, most recent critical outputs
- **L1 Task/App Summary**: compact summary of progress, major decisions, unresolved issues, key artifacts
- **L2 Execution Detail**: step/node-level details, logs, intermediate inputs/outputs, failure traces
- **L3 Long-term Experience**: reusable lessons, patterns, and promoted operational knowledge

### 13.2 Design Rules
- prompts should prefer L0 + selected L1, not raw L2
- L2 detail should remain queryable by reference rather than always loaded
- compaction should preserve decisions, constraints, open loops, artifacts, and references
- app/workflow execution history should serve as a primary detail source for compaction
- app shared context should remain the active mutable layer, while summaries become derived state

### 13.3 Minimal Implementation Plan
- add `ContextCompactionService`
- persist `context_summaries`
- build a `working_set` view derived from app context + recent execution history
- expose APIs for compaction, listing layers, and retrieving working set
- keep detail in `app_contexts`, `workflow_execution_history`, and `skill_executions`

Current implementation note:
- context compaction summaries and policies are now persisted and reloaded through the runtime state store
- working-set and summary metadata now include recent workflow/skill references for selective deep retrieval
- policy-driven auto compaction can now trigger on workflow completion, workflow failure, and stage change
- runtime persistence inspection now exposes `context_summaries` and `context_policies`
- a minimal workflow executor now exists for workflow execution
- it supports deterministic step skeletons for `state.set`, `state.get`, and event emission
- it also includes placeholders for `human_task` and `skill` steps so workflows can preserve unresolved work in context
- step outputs can now be passed into later steps through lightweight `$from_step` / `$from_inputs` references
- step-level conditional execution is supported through simple `when` checks
- workflow execution returns an aggregated outputs summary for completed/skipped steps and step outputs
- event-driven workflow subscriptions can now auto-trigger workflow execution from published internal events
- `skill` steps now support a minimal dispatch contract through `SkillRuntimeService`, with registered handlers, structured request/result payloads, input mapping, failure capture, execution persistence, and blueprint-declared allowlist enforcement
- workflow and skill execution now expose basic observability surfaces: execution history, filtered failure inspection, latest execution lookup, and skill failure listings
- workflow failure inspection can now be narrowed by app instance, workflow id, and failed step id for faster operator triage
- workflow execution results now carry explicit `failed_step_ids` so failure review and future policy/retry tooling can identify the exact blocked steps without re-scanning every step payload
- retrying the latest failed workflow now returns structured before/after comparison metadata so operators can see whether status changed and which failed steps were resolved, unchanged, or newly introduced
- workflow diagnostics can now aggregate latest execution, latest true failure, latest retry, and a lightweight recovery-state summary for operator-facing failure panels
- diagnostics can also be narrowed to one failed step path, and a dedicated latest-recovery view exposes the newest retry outcome in a UI-friendly shape
- diagnostics/recovery aggregation logic is now separated into a dedicated workflow observability service instead of being duplicated in the API layer or mixed into execution code, and `/workflows/overview` exposes a combined response for operator dashboards
- workflow overview now includes a first-class health summary (`health_status`, `severity`, unresolved failure count, latest failed steps, retry presence) so dashboards can render status without inferring it client-side
- health rules now explicitly distinguish `healthy`, `failing`, and `unknown` (partial-without-failed-steps) states, avoiding ambiguous dashboard status inference
- health/severity classification is now centralized inside the observability service, making future additions like `recovering` rule changes or dashboard severities easier to evolve safely
- observability health classification now follows a small explicit rule table, which makes state additions and severity tuning less error-prone than growing nested conditionals
- observability queries now support recent-N and unresolved-only history retrieval, which is a better fit for dashboards/timelines than forcing clients to slice the full execution history themselves
- timeline-style observability summaries are now exposed as compact event cards (failure / retry / recovery / completed / partial) so UI surfaces do not need to transform full execution payloads just to render an incident feed
- timeline queries now support `since` windows and cursor-style pagination so the observability layer can back activity feeds without forcing clients to pull and sort the entire history each time
- observability queries now share an explicit filter model so API handlers and service logic stop drifting in which query knobs they support
- API contract coverage now checks that diagnostics/history/timeline honor the same filter semantics, and observability-history formally supports time-window filtering alongside unresolved/recent slicing
- history and timeline now share the same page-style response shape, and API-side filter construction is centralized through a small helper instead of repeated inline parameter assembly
- paged observability responses now carry lightweight metadata (`returned_count`, `unresolved_count`, `has_more`, `window_since`, `next_cursor`) so dashboard clients can render state without re-deriving feed stats client-side
- an aggregate stats summary is now available for workflow observability, giving operator-facing surfaces totals for executions, failures, retries, recoveries, unresolved states, and latest activity time
- a dashboard-style read model now combines overview, stats, and recent timeline into one higher-level payload for operator surfaces that want one coherent summary call
- observability internals are now starting to split into helper/query modules so API parsing and low-level classification/filter logic stop accumulating inside one large service/file
- registry/operator surfaces now include release comparison, overview, attention, and control-plane summary read models so release review can happen through one coherent operator-facing contract
- operator-facing workflow/refinement surfaces now share small common filter/page/dashboard contracts, reducing drift between related read models while keeping domain-specific payloads explicit
- workflow execution telemetry now binds app versions through the installed app-instance version surface, avoiding contract drift between installer/runtime models and executor telemetry
- recent failed workflow executions can now be retried directly from stored execution history and inputs
- execution can write app data, append shared-context artifacts, persist runtime execution records, and publish internal events
