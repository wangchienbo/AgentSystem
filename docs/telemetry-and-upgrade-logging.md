# AgentSystem Telemetry and Upgrade Logging Design

## 1. Purpose

This document defines the telemetry, feedback, and upgrade-log design for AgentSystem.

Its purpose is to support a system that:
- stays pleasant to use over time
- can improve app and skill behavior through evidence rather than guesswork
- keeps token and runtime cost visible and governable
- remains skill-centric and self-iterable without turning the core into a heavy monolith

The central design stance is:
- the core platform should provide standard observation, collection, policy, and primitive interfaces
- higher-level behaviors such as upgrade generation, testing, acceptance, archiving, publish, and rollback should remain as skill-driven workflows whenever possible

---

## 2A. Terminology boundary

To avoid drift across documents, the following terms should be used consistently:
- **telemetry**: lightweight, structured runtime records used for ordinary operational reads and controls
- **upgrade-evidence logs**: append-only historical evidence used for replay, acceptance, optimization, publish, and rollback analysis
- **observability**: a broader operator-facing read layer that may consume telemetry and other domain summaries, but is not identical to telemetry itself
- **audit**: policy/action trace surfaces associated with system governance; audit may consume upgrade-evidence, but should not be treated as a synonym for all upgrade logs
- **evaluation summary**: a derived comparison or acceptance record, not a raw telemetry event

---

## 2. Core Design Position

### 2.1 Core thin, skill heavy
The core system should remain responsible for:
- standardized telemetry and feedback collection
- version binding and identity correlation
- low-cost structured runtime observation
- upgrade-log generation interfaces
- collection policy and safety boundaries
- primitive publish / rollback / evaluate interfaces

Skills should remain responsible for:
- next-version generation
- test orchestration
- acceptance orchestration
- archive/report generation
- publish / rollback orchestration
- complex user-intent handling
- upgrade-log enrichment and downstream storage workflows

This keeps the architecture aligned with the broader AgentSystem direction:
- apps are the product surface
- skills are the reusable behavior layer
- the platform provides standards and boundaries rather than embedding every workflow as core code

### 2.2 Self-iteration must be evidence-bound
App and skill self-iteration should be supported, but must not be driven only by verbal proposals or subjective optimism.

Any self-iteration loop should be grounded in:
- user feedback
- runtime outcome quality
- token/cost behavior
- latency behavior
- stability / regression checks
- explicit publish / rollback control

### 2.3 Cost is a first-class optimization dimension
Optimization must not mean only “smarter” or “more autonomous”.

The system must treat the following as first-class and jointly evaluated:
- user experience / comfort
- task success rate
- token efficiency
- latency efficiency
- stability and controllability

This means token usage is not an afterthought; it is part of the optimization target itself.

---

## 3. Data Separation Principle

The platform must separate two different kinds of information:

### 3.1 Runtime operational telemetry
This is the lightweight, structured information needed for normal system operation.

It exists to support:
- online control-plane reads
- current-state inspection
- budget enforcement
- real-time status and usage tracking
- lightweight analytics

Properties:
- structured
- queryable
- low-latency
- low-cost
- safe for frequent access

### 3.2 Upgrade/evolution evidence logs
This is the append-only historical evidence used for:
- optimization analysis
- replay and acceptance
- candidate generation
- regression auditing
- publish/rollback evidence
- skill-driven offline analysis

Properties:
- append-only
- time-sliced
- primarily event-oriented
- optimized for later replay/analysis rather than online serving
- should not be required for the online serving path to function

### 3.3 Why the split matters
This separation prevents three common failure modes:
- online storage becoming bloated with heavy historical detail
- optimization evidence being lost due to overwrite-style state updates
- the upgrade loop increasing runtime cost for ordinary use

---

## 4. Telemetry and Logging Architecture

The recommended architecture is dual-track:

### 4.1 Online structured telemetry track
Used by running apps, control-plane reads, and lightweight analytics.

Representative record families:
- `interactions`
- `interaction_steps`
- `feedback_records`
- `budget_usage`
- `version_bindings`
- `evaluation_summaries`

### 4.2 Upgrade-log track
Used by optimization, replay, acceptance, and evidence-preserving evolution flows.

Representative log families:
- `logs/interactions/YYYY-MM-DD.jsonl`
- `logs/optimization/YYYY-MM-DD.jsonl`
- `logs/evaluations/YYYY-MM-DD.jsonl`
- `logs/releases/YYYY-MM-DD.jsonl`

### 4.3 Log format
Upgrade logs should prefer JSON Lines (`.jsonl`):
- one event per line
- append-friendly
- stream-friendly
- resilient to partial write failure
- easy for skills and scripts to consume later

### 4.4 Rotation policy
Default recommendation:
- rotate by day

High-volume deployments may later support:
- rotate by hour

The initial design should prefer simplicity over premature operational complexity.

---

## 5. Collection Policy and User Control

### 5.1 User-governed collection
Users must be able to control telemetry and upgrade collection policy.

Policy should be expressible at multiple scopes:
- global
- app
- skill
- agent
- task type

Users should be able to define different strategies for app and skill behavior, such as:
- whether upgrade information is collected
- whether a skill may append custom upgrade evidence
- whether a specific app is cost-first or quality-first
- whether automatic publication is allowed
- whether acceptance requires human confirmation

### 5.2 Upgrade information must be freely switchable
Upgrade information collection should support:
- enable/disable globally
- enable/disable by app
- enable/disable by skill
- content-level control
- retention-level control

### 5.3 Collection levels
Collection should be tiered.

#### Level 0: off
- no upgrade/evolution evidence collection
- only minimal operational state remains

#### Level 1: light (default)
- structured event collection
- token / latency / success / failure summaries
- version binding
- lightweight explicit + implicit feedback signals
- no large raw payload capture

#### Level 2: medium
- includes light-level collection
- adds key-step summaries
- allows bounded truncated payload capture
- suitable for normal optimization cycles

#### Level 3: heavy
- detailed step evidence
- richer payload retention
- intended for debugging, acceptance audits, or focused tuning
- must not be the default

#### Level 4: custom
- user- or skill-defined collection behavior
- allows app/skill/task-specific specialization

### 5.4 Default posture
The default system posture should be:
- collection available
- light mode enabled
- upgrade logs allowed
- expensive raw capture disabled
- user able to narrow or disable collection at any time

### 5.5 Delivery-phase boundary
The conceptual design supports off/light/medium/heavy/custom and broader scope layering, but the first delivery should prioritize a smaller subset.

The buildable first implementation should start with:
- `off | light | medium` collection levels
- `global | app | skill` policy scopes

Heavier collection levels and more complex scope composition should remain later-phase targets unless practical demand proves them necessary earlier.

---

## 6. Standardized Event Model and Skill Extensibility

### 6.1 Core provides minimum standard events
The platform should define a minimum standardized event vocabulary, for example:
- `interaction_started`
- `interaction_completed`
- `step_completed`
- `tool_failed`
- `feedback_received`
- `candidate_evaluated`
- `release_published`
- `release_rolled_back`

These events provide the shared evidence substrate required by the platform.

### 6.2 Skills may extend upgrade evidence
Skills should be allowed to append their own upgrade-oriented details on top of the standardized event model.

Examples of skill-specific enrichment:
- why a sample was selected for replay
- a skill-specific optimization hint
- a test-selection explanation
- a domain-specific acceptance signal
- a compact aggregate generated by a specialized skill

The rule should be:
- the platform owns the baseline schema and event envelope
- skills may add structured extension payloads

This preserves consistency without giving up flexibility.

### 6.3 Platform-decision boundary for extension payloads
Skill extension payloads should be treated as supplemental evidence unless the platform explicitly registers a contract that promotes a given extension field into a trusted decision input.

This means:
- baseline platform decisions should rely first on platform-defined fields
- extension payloads must not break or replace the base event envelope
- publish / rollback / acceptance gates should not silently depend on arbitrary unregistered extension fields

This prevents evidence fragmentation from turning into governance fragmentation.

---

## 7. Recommended Runtime Telemetry Entities

### 7.1 Interaction record
Captures one user request or one top-level app request.

Suggested fields:
- interaction_id
- session_id
- user_id
- app_id
- app_version
- agent_id
- agent_version
- request_type
- start_time
- end_time
- success
- failure_reason
- total_input_tokens
- total_output_tokens
- total_tokens
- total_latency_ms
- total_tool_calls
- strategy_name
- collection_level
- user_feedback_score
- user_feedback_text
- aborted
- retried
- escalated

### 7.2 Step / invocation record
Captures one meaningful execution step.

Suggested fields:
- interaction_id
- step_id
- parent_step_id
- step_type (`reason | tool | skill | subagent | system`)
- name
- version
- input_size
- output_size
- input_tokens
- output_tokens
- latency_ms
- success
- error_code
- retry_count
- cache_hit
- estimated_cost

### 7.3 Feedback record
Should support both explicit and implicit signals.

Explicit examples:
- satisfaction score
- like / dislike
- “too long”
- “too slow”
- “not accurate”

Implicit examples:
- immediate re-ask
- repeated command attempt
- user correction after output
- interruption
- escalation to stronger mode or human check

### 7.4 Version binding record
Must correlate execution with:
- app version
- skill versions
- agent version
- policy version
- evaluation suite version

Without this, upgrade comparison and rollback evidence become unreliable.

---

## 8. Upgrade Log Design

### 8.1 Append-only rule
Upgrade logs should be append-only.

The system should not rewrite prior upgrade evidence files in place during ordinary operation.

### 8.2 Time-sliced files
Logs should be split by time window.

Default:
- per day

Possible later extension:
- per hour for high-volume systems

### 8.3 What should be logged
Upgrade logs should normally include:
- interaction summaries
- step summaries
- token / latency / cost summaries
- feedback signals
- error / anomaly events
- version identifiers
- evaluation outcomes
- publish / rollback decisions
- bounded summaries or references to key evidence

### 8.4 What should not be logged by default
The default light path should avoid:
- full raw prompts for every call
- full model context dumps
- chain-of-thought capture
- large unbounded tool outputs
- high-sensitivity payloads in cleartext

Those should require stronger collection modes or explicit policy.

### 8.5 Event logs and aggregate logs
The upgrade evidence plane may contain two complementary layers:

#### Event log
Fine-grained machine-oriented events.

#### Aggregate / snapshot log
Periodic or evaluation-triggered summaries, for example:
- 24h skill success rate summary
- 7-day token trend for an app
- highest-cost execution path summary
- candidate-vs-baseline evaluation summary

This allows skills to consume either raw events or pre-aggregated evidence.

---

## 9. Evaluation and Optimization Criteria

The optimization loop should be governed by both weighted scoring and hard gates.

### 9.1 Weighted comparison dimensions
Candidate changes should be compared using dimensions such as:
- user experience / comfort
- task success rate
- token efficiency
- latency efficiency
- stability

### 9.2 Hard gates
No candidate should be promoted if it violates hard boundaries such as:
- significant success-rate regression
- excessive token growth
- excessive latency growth
- failed regression tests
- unacceptable negative-feedback increase

Weighted improvement is useful, but must not override basic safety and quality gates.

---

## 10. Publish / Rollback and Skill-Oriented Orchestration

The core platform should expose primitive operations for:
- compare
- evaluate
- publish
- rollback
- archive

Higher-level user-facing workflows should be implemented primarily as skills that compose those primitives.

This enables natural-language requests such as:
- generate a lower-cost next version
- run replay and cost tests
- only publish if token growth stays under budget
- archive failure reasons if acceptance fails

The platform should support both:
- direct low-level control
- high-level skill-driven orchestration

---

## 11. Design Consequences for AgentSystem

To align with this document, AgentSystem should evolve toward:
- a lightweight telemetry core
- a separated upgrade-log pipeline
- policy-aware collection control per app and per skill
- machine-readable version binding across app/skill/agent/evaluation artifacts
- skill-driven generation/testing/acceptance/publish/rollback workflows
- explicit cost-aware optimization rather than intelligence-first optimization

The expected design outcome is:
- normal use stays lightweight
- optimization remains evidence-bound
- users can control the amount and shape of recorded upgrade information
- skills can extend the upgrade loop without replacing the platform’s standard evidence substrate

---

## 12. Recommended Near-Term Delivery Order

1. define the online telemetry schema
2. define the upgrade-log event schema and file layout
3. add collection policy and level controls
4. add version-binding support to execution records
5. expose query surfaces for skill consumption
6. add evaluation summary contracts
7. later add skill-driven generation / test / acceptance / archive / publish workflows

This keeps the platform aligned with the long-term skill-centric design while starting from the most foundational observation layer.