# AgentSystem / App OS Requirements

## 1. Purpose

AgentSystem aims to become an **App OS**: a system that can define, install, run, supervise, evolve, and persist AI-native applications as first-class long-lived objects.

The system should not be treated as a single assistant workflow runner. Instead, it should behave more like an operating system for apps:
- apps are registered and installed
- apps have runtime policy and lifecycle
- apps own isolated data namespaces
- apps maintain app-local shared context for internal execution
- apps can be long-running services or one-shot pipelines
- runtime behavior can be reviewed into experience
- experience can evolve into reusable skills
- a user-facing control plane can observe and intervene without being required for every app-internal step

---

## 2. Product Goals

### 2.1 Core goals
The system must support:
- defining apps as structured blueprints
- registering and installing blueprints as app instances
- managing app lifecycle and runtime state
- separating app data, runtime state, system metadata, and skill assets
- accepting user commands through a unified interaction interface
- supporting both service apps and pipeline apps
- supervising runtime behavior through schedule, health, restart, and event mechanisms
- reviewing runtime practice into reusable experience
- suggesting reusable skills from runtime experience

### 2.2 Architectural goals
The system should:
- treat **App** as the main user-facing product unit
- treat **Skill** as a reusable capability unit, not the default product unit
- prefer deterministic modules over LLM use
- use intelligent skills only for semantic, analytic, or generative steps
- distinguish network availability from intelligence availability
- treat intelligence invocation as a governed runtime policy decision rather than a default behavior whenever a model is reachable
- infer app runtime class and startup behavior from skill metadata instead of requiring users to manually choose low-level capability profiles
- maintain explicit boundaries between:
  - blueprint definition
  - app installation
  - runtime execution
  - app data
  - runtime state
  - experience / skill assets

---

## 3. Key Definitions

### 3.1 Module
A deterministic foundation capability such as file, state, event, auth, or config operations.

### 3.2 Skill
A reusable capability asset that may rely on rule logic or LLM reasoning. Skills can be versioned, replaced, disabled, and suggested from experience.

Each skill should also support internal capability metadata so the system can classify:
- intelligence level
- network requirement
- runtime criticality (`build_only | optional_runtime | required_runtime`)
- execution locality (`local | hybrid | remote`)
- invocation default (`automatic | ask_user | explicit_only`)
- risk level

### 3.3 App Blueprint
A structured app definition template describing:
- goal
- roles
- tasks
- workflows
- views
- required modules
- required skills
- storage plan
- runtime policy

### 3.4 App Instance
The installed lifecycle object derived from a blueprint. It owns:
- lifecycle status
- runtime policy
- execution mode
- owner
- namespaces
- runtime state

### 3.5 Runtime Policy
A structured policy describing:
- execution mode (`service | pipeline`)
- activation mode
- restart policy
- persistence level
- idle strategy
- network behavior
- intelligence behavior
- invocation governance for optional intelligent steps

### 3.6 Experience
A structured record of useful operational knowledge extracted from documents, demonstrations, runtime, or human notes.

---

## 4. Scope

### 4.1 In scope
Current project scope includes:
- requirement routing
- immutable skill control interface
- experience store and skill blueprint store
- demonstration extraction
- app lifecycle management
- runtime host
- scheduler and supervisor
- runtime persistence
- app registry and installer
- app data namespaces and data records
- event bus and event subscriptions
- practice review from runtime behavior
- experience-to-skill suggestion flow

### 4.2 Out of scope for current phase
Not required for current milestone:
- full GUI designer
- rich multi-tenant admin panel
- production-grade marketplace
- full deployment / scaling architecture
- advanced policy engine
- complete workflow compiler

---

## 5. Functional Requirements

### 5.1 Requirement intake
The system must support routing user requirements into:
- `app`
- `skill`
- `hybrid`
- `unclear`

It must also decide whether user demonstration is:
- `required`
- `optional`
- `not_needed`
- `clarify`

### 5.2 Skill control
The system must provide a stable human-controlled interface for:
- listing skills
- viewing a skill
- replacing a skill version
- rolling back a skill
- enabling / disabling a skill
- protecting immutable control interfaces

### 5.3 Experience and skill assets
The system must support:
- storing `ExperienceRecord`
- storing `SkillBlueprint`
- linking experiences to skills
- suggesting skills from experience

### 5.4 Demonstration extraction
The system must support transforming demonstration input into:
- an experience record
- a candidate skill blueprint

### 5.5 App registration and installation
The system must support:
- registering a blueprint
- listing registry entries
- installing a blueprint into an app instance
- carrying runtime policy from blueprint into instance

### 5.6 App lifecycle
Each app instance must support lifecycle states including:
- `draft`
- `validating`
- `compiled`
- `installed`
- `running`
- `paused`
- `stopped`
- `failed`
- `upgrading`
- `archived`

Required lifecycle actions include:
- validate
- compile
- install
- start
- pause
- resume
- stop
- fail
- upgrade
- archive

### 5.7 Runtime management
The runtime layer must support:
- runtime lease tracking
- checkpoint generation
- pending task queue
- healthcheck
- runtime overview

### 5.8 Scheduling and supervision
The system must support:
- interval-trigger schedules
- event-trigger schedules
- supervision policies
- failure observation
- restart attempts
- circuit-open protection

### 5.9 Interaction gateway
The system must expose a main command interface that:
- matches user commands to app catalog entries
- installs app instances through the installer flow
- opens long-running service apps
- executes one-shot pipeline apps
- falls back to clarification when no app matches

### 5.10 Data namespaces
The system must create and manage explicit namespaces for:
- `app_data`
- `runtime_state`
- `system_metadata`
- `skill_assets`

It must support listing namespaces and writing/reading data records.

### 5.11 System default skills and app configuration
Each installed app must receive a minimal built-in system skill set that does not depend on external intelligence or network availability.

The current expected baseline includes:
- `system.app_config`
- `system.context`
- `system.state`
- `system.audit`

The system must support a per-app configuration surface controlled through `system.app_config` for:
- config read
- config write
- config patch
- config delete
- default initialization
- schema validation
- config change history

The platform should inject these system skills during installation rather than requiring end users to declare them manually.

### 5.12 Skill classification and app profile resolution
The system must classify skills internally from their declared or inferred capability metadata.

It must support deriving an app-level runtime profile from the installed skill set, including at least:
- highest runtime intelligence level among active runtime skills
- runtime network requirement (`none | optional | required`)
- offline capability
- default startup class
- default intelligent invocation posture

The app-level runtime profile should be inferred by the platform and should not require end users to manually assign technical runtime classes.

### 5.13 Offline capability and direct start
The system must distinguish:
- network availability
- intelligence availability
- intelligent invocation policy

An app that does not require intelligence for runtime execution should be able to start directly without AI mediation.

The system must support at least these runtime outcomes:
- fully direct start for deterministic/offline-capable apps
- direct start with optional intelligent enhancement
- intelligent start only when runtime-critical skills require it

### 5.14 Intelligent invocation governance
The system must avoid calling intelligent skills by default merely because model access is configured.

It must prefer deterministic execution first and only invoke intelligence when:
- the step requires it
- the runtime policy allows it
- the cost / token policy allows it
- user confirmation is obtained when required by policy

The system should support a default ask-before-intelligence posture for optional or token-spending intelligent steps.

### 5.15 App shared context
The system must support app-local shared context that is independent from the user-facing control AI context.

Each app shared context must support at least:
- app description
- current goal
- current stage
- structured entries grouped by sections such as:
  - `facts`
  - `artifacts`
  - `decisions`
  - `questions`
  - `constraints`
  - `open_loops`

The system must support:
- creating app context automatically or on first use
- updating app context stage and goal
- appending structured context entries
- listing and retrieving app contexts

### 5.16 Event bus
The system must support:
- publishing internal events
- recording event logs
- registering subscriptions
- triggering event schedules from published events

### 5.17 Skill packaging, contracts, and runtime adapters
The system must treat a skill as a runnable capability package rather than only a symbolic dependency name.

Each skill should support a machine-readable package/manifest describing at least:
- identity and version
- capability metadata
- runtime adapter type
- input/output/error contracts
- dependency declarations
- validation assets/examples

The runtime adapter model should support at least these execution styles:
- in-process callable
- local script with structured input/output
- RPC service
- binary executable
- frontend or human-interaction adapter where applicable

### 5.18 Skill orchestration and dispatch
The system must support orchestrated skill execution through a unified runtime surface.

The platform should prefer orchestrator-mediated skill dispatch over uncontrolled skill-to-skill direct calls so it can enforce:
- input/output validation
- timeout policy
- retry policy
- observability and audit
- network / intelligence invocation governance
- dependency and permission checks

### 5.19 Skill and app validation
The system must validate both skills and apps before runtime activation.

Skill-level validation should check at least:
- manifest completeness
- contract/schema validity
- runtime adapter resolvability
- compatibility between declared capability tags and actual execution form

App-level validation should check at least:
- required skill existence
- workflow step / skill contract compatibility
- input/output mapping compatibility between steps
- consistency between app runtime posture and runtime-capable skill set
- build-only skill leakage into runtime execution paths

### 5.20 Core skill principle reference
The system documentation must maintain a canonical core-skill principle reference table for future platform-skill design.

That table must identify, for each core skill or core skill category:
- primary role
- runtime criticality
- whether local-first behavior is required
- whether default intelligence use is prohibited
- whether strict machine-readable contracts are required
- special design constraints or boundary notes

This reference should be consulted whenever new system-default or platform-governance skills are introduced.

### 5.21 Practice review
The system must support reviewing a runtime practice episode by combining:
- recent event log
- data records

and distilling them into an `ExperienceRecord`.

### 5.22 Experience-to-skill suggestion
The system must support generating a candidate `SkillBlueprint` from a stored `ExperienceRecord`, optionally persisting it.

---

## 6. Data Requirements

### 6.1 Data separation
The system must explicitly separate:
- app business data
- runtime execution state
- system metadata
- skill asset data

### 6.2 Persistence
The system must persist at least:
- app instances
- lifecycle events
- runtime leases
- checkpoints
- pending tasks
- schedules
- supervision policies and statuses
- registry entries and blueprints
- namespaces and data records
- event logs and subscriptions

### 6.3 Namespace provisioning
Installing an app must provision its namespaces automatically.

---

## 7. Execution Model Requirements

### 7.1 Service apps
A service app is a long-lived app that can:
- be opened by user command
- stay active across interactions
- subscribe to events
- run background schedules
- be supervised and restarted

### 7.2 Pipeline apps
A pipeline app is a one-shot app that:
- accepts a command or input
- runs once
- stops after finishing
- may still retain its business data and result records

---

## 8. Intelligence Boundaries

The system must prefer deterministic logic wherever possible.
LLM-like intelligence should be used only for:
- requirement clarification
- blueprint generation
- conflict diagnosis
- workflow suggestions
- role inference
- semantic analysis of data or experience

The system should not rely on LLMs for:
- basic state transitions
- registry storage
- namespace management
- event delivery
- lifecycle enforcement

---

## 9. Non-functional Requirements

### 9.1 Maintainability
- schemas should remain explicit
- service boundaries should be clear
- features should be added as composable services

### 9.2 Observability
The system should make runtime behavior inspectable through:
- event logs
- lifecycle events
- checkpoint and lease state
- reviewable practice summaries

### 9.3 Testability
Core services should be covered by unit/integration tests.

### 9.4 Evolvability
The system should support the evolution chain:
- practice
- experience
- skill suggestion
- future workflow/app refinement

---

## 10. Acceptance Criteria for Current Milestone

Current milestone is considered complete if the system can:
- route requirements
- manage skill control safely
- store experiences and skill blueprints
- extract from demonstrations
- register and install app blueprints
- run lifecycle transitions
- host runtime state
- schedule and supervise apps
- separate app data namespaces
- publish and react to events
- review runtime practice into experience
- suggest skill blueprints from experience
- pass automated tests for the above

---

## 11. Current Gap After This Milestone

The next major gaps are:
- workflow execution modules tied to app data and event operations
- contradiction / priority analysis for better decision focus
- app refinement from suggested skills
- stronger policy and permission model
- production-grade persistence and recovery
- layered context compaction and retrieval

## 12. Layered Context Management

To prevent context explosion, the system should manage execution context as layered memory instead of a single continuously growing prompt payload.

Required capabilities:
- maintain a minimal **working set** for the current execution scope
- maintain a compact **task/app summary** separate from execution detail
- preserve **execution detail** outside the prompt path for on-demand retrieval
- support explicit or threshold-based context compaction
- preserve decisions, constraints, open loops, artifacts, and current goal/stage during compaction
- provide selective retrieval of deeper context only when required by the current execution node
- support promotion of repeated patterns into long-term reusable experience
