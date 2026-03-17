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

### 5.11 App shared context
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

### 5.12 Event bus
The system must support:
- publishing internal events
- recording event logs
- registering subscriptions
- triggering event schedules from published events

### 5.12 Practice review
The system must support reviewing a runtime practice episode by combining:
- recent event log
- data records

and distilling them into an `ExperienceRecord`.

### 5.13 Experience-to-skill suggestion
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
