# AgentSystem / App OS Testing Strategy

## 1. Purpose

This document defines how AgentSystem should be validated against its current implemented architecture and its near-term roadmap.

The testing goal is not only to validate isolated functions, but to verify that the system behaves coherently as an App OS with:
- blueprint registration and installation
- lifecycle and runtime management
- scheduling and supervision
- data namespace isolation
- app-local shared context
- app configuration and default system skills
- skill classification and app-profile resolution
- event-driven runtime behavior
- practice-to-experience distillation
- experience-to-skill suggestion

---

## 2. Testing Layers

### 2.1 Unit tests
Used for deterministic services and models such as:
- lifecycle transition logic
- scheduler validation
- supervisor policy behavior
- data namespace creation
- event publishing
- experience and skill suggestion logic

### 2.2 Integration tests
Used for API and service combinations such as:
- registry -> install -> runtime
- event publish -> event schedule trigger
- practice review -> experience store
- experience -> skill suggestion

### 2.3 End-to-end milestone tests
Used to validate full user/system flows:
- install a blueprint
- open a service app
- publish events
- store data
- review runtime practice
- generate a candidate skill blueprint

---

## 3. Current Implemented Test Matrix

The current codebase already covers the following implemented domains.

## 3.1 Requirement routing
Covered behavior:
- route app / skill / hybrid / unclear
- determine demonstration requirement

## 3.2 Skill control interface
Covered behavior:
- list skills
- replace skill version
- rollback
- enable / disable
- immutable protection
- API error mapping
- authoring helpers can generate consistent callable/script skill registry entries
- API-driven skill creation can register a generated skill, smoke-test it, and assemble it into an app blueprint
- generated skill flows can also install and execute a blueprint-built app, including a non-trivial script skill that performs real text normalization instead of a pure echo fixture
- generated script skill assets can persist and reload into a rebuilt runtime and still execute correctly
- generated skill API failures return structured diagnostics for invalid request, callable generation failure, install/execute failure classes, and malformed generated-app mapping requests
- generated skill diagnostics can be converted into suggested retry payloads through the retry-advice API
- generated app assembly can chain multiple skills through explicit step mappings, including mapping prior step outputs and workflow inputs into nested downstream payload fields
- generated app assembly also covers lightweight transform/default mapping behavior for common composition cleanup paths
- generated app assembly returns schema-based mapping suggestions and unresolved required downstream inputs for safe adjacent-step matches
- install-run coverage verifies high-confidence suggestions are auto-applied without breaking explicit mapping flows
- compile-time validation now distinguishes legitimate nested mapping targets from true output/input schema mismatches

## 3.3 Experience store and demonstration extraction
Covered behavior:
- store experiences
- store skill blueprints
- suggest skills for an experience
- extract demonstration into experience and skill blueprint

## 3.4 Lifecycle and runtime host
Covered behavior:
- legal state transitions
- invalid transition rejection
- start / pause / resume / stop
- healthcheck
- task queue
- runtime overview
- API error mapping

## 3.5 Scheduler and supervisor
Covered behavior:
- interval trigger
- event trigger validation
- failure observation
- restart logic
- circuit-open protection
- scheduler/supervisor API flow
- proposal review / priority analysis context-aware scoring and review notes

## 3.6 Registry and installer
Covered behavior:
- blueprint registration
- install flow
- runtime policy propagation to app instance
- registry API flow
- minimal workflow execution against deterministic primitives
- workflow-id selection and placeholder handling for human_task / skill steps
- step output passing between deterministic workflow steps
- conditional step execution and workflow output aggregation
- event-triggered workflow subscription execution
- minimal registered skill dispatch inside workflow execution
- skill input mapping and failure capture during workflow execution
- blueprint allowlist enforcement for workflow skill steps
- workflow and skill observability APIs for history/failure/latest inspection, including failure filtering by workflow id and failed step id
- workflow execution results include explicit `failed_step_ids` for failure targeting and regression assertions
- retry API for rerunning the latest failed workflow execution with structured before/after comparison metadata
- workflow diagnostics API for summarizing latest execution/failure/retry state per app/workflow, including failed-step filtering, latest-recovery summaries, combined overview responses, and health-summary fields
- workflow health status rules for healthy / failing / unknown transitions
- dedicated observability service tests covering overview aggregation and health classification independent of the executor API tests, including recovering-state behavior
- observability history queries covering recent-N and unresolved-only filtering behavior
- timeline event summaries covering failure/retry flow normalization
- timeline pagination/windowing behavior covering `since` and cursor-based fetches
- shared observability filter model coverage to keep query semantics aligned across service/API surfaces
- API contract tests verifying diagnostics/history/timeline respect the same observability filter semantics
- page-shape coverage for observability-history so it stays aligned with timeline pagination semantics
- page metadata coverage for history/timeline responses (counts, cursors, window info)

## 3.7 Interaction gateway
Covered behavior:
- open service app from command
- run pipeline app from command
- clarify unknown command

## 3.8 App data store
Covered behavior:
- namespace provisioning
- installer-driven namespace creation
- record write/read behavior
- namespace API flow

## 3.9 App shared context
Covered behavior:
- context creation on first use
- installer-seeded goal and owner identity
- context stage/goal update
- structured context entry append
- joined context + runtime inspection API flow
- interaction-driven context updates for service and pipeline apps

## 3.10 Event bus
Covered behavior:
- publish event
- trigger event schedule
- auto-create event subscription from event schedule
- list event subscriptions
- event API flow

## 3.10 Practice review
Covered behavior:
- review runtime events and data records
- fold app shared context into summary and tags
- generate runtime experience record
- review API flow

## 3.11 Skill suggestion
Covered behavior:
- generate candidate skill blueprint from experience
- self-refinement can incorporate app shared context into proposal evidence
- optional persistence into store
- review -> experience -> skill suggestion API flow

---

## 4. Test Suite Status

At the time of this document update:
- automated local test suite passes
- current result: `31 passed` for the latest focused validation/runtime regression slice, with additional focused green runs covering context compaction and file-backed test isolation work

This indicates the implemented milestone is internally consistent at the current level of scope.

---

## 5. Core Functional Test Groups

## 5.1 Lifecycle tests
Required checks:
- draft -> validating -> compiled -> installed
- installed -> running
- running -> paused -> running
- running -> stopped
- running -> failed
- invalid transitions rejected

## 5.2 Runtime tests
Required checks:
- lease creation
- checkpoint generation
- pending task queue changes
- healthcheck updates

## 5.3 Scheduling tests
Required checks:
- interval schedules trigger tasks
- event schedules require `event_name`
- paused/disabled schedules do not trigger active work

## 5.4 Supervision tests
Required checks:
- failure counts increase correctly
- restart attempts follow policy
- circuit opens after configured threshold

## 5.5 Data tests
Required checks:
- namespaces created on install
- app data, runtime state, and system metadata remain distinct
- records can be written and listed

## 5.6 Event tests
Required checks:
- event log is persisted
- subscriptions are visible
- event publish triggers matching schedules

## 5.7 Evolution tests
Required checks:
- runtime practice becomes experience
- experience becomes skill suggestion
- persistence option works as expected

## 5.8 Capability-classification and invocation-governance tests
Required checks:
- deterministic system skills are injected for every app install
- app config surface is initialized and isolated per app
- runtime profile is resolved from runtime-capable skills rather than build-only skills
- offline-capable apps can direct-start without intelligence availability
- optional intelligent steps respect ask-before-intelligence policy
- network availability and intelligence availability are evaluated independently

## 5.9 Skill package / contract / adapter validation tests
Required checks:
- skill manifests are rejected when required metadata or contract references are missing
- contract/schema refs resolve through one authoritative registry/source
- input/output examples satisfy declared schemas
- callable/script/rpc/binary adapter declarations resolve correctly
- adapter resolvability is tested separately from contract/schema validity
- declared capability tags remain consistent with runtime form
- workflow skill steps fail validation when upstream/downstream contracts do not align
- workflow skill steps referencing undeclared skills are rejected
- required skills missing from the registry are rejected before install
- build-only skills are rejected from runtime execution paths
- dispatched skill inputs are rejected before execution when they violate the declared request contract
- returned outputs/errors are rejected or flagged when they violate the declared response contract

## 5.10 Core skill principle reference tests
Required checks:
- every system-default skill is represented in `docs/skill-design-principles.md`
- system-default skills declared as local-first do not depend on remote-only adapters
- skills marked as no-default-intelligence do not declare implicit intelligent execution paths
- future governance skills remain classified with explicit runtime criticality and contract strictness

---

## 6. API-level Validation Targets

The following API groups should remain covered by tests:
- `/blueprints/validate`
- `/skills/*`
- `/experiences`
- `/demonstrations/extract`
- `/apps/*`
- `/registry/apps*`
- `/interaction/command`
- `/data/namespaces*`
- `/events*`
- `/schedules*`
- `/supervision*`
- `/practice/review`
- `/skills/suggest-from-experience`

---

## 7. Testing Discipline

### 7.1 For each feature node
For each functional feature node, the expected workflow is:
1. implement the feature
2. add or update tests
3. run the full suite
4. commit the node
5. push the node

This is the current active development rule.

### 7.2 Deterministic first
Core runtime, lifecycle, scheduling, data, and event behavior should be validated through deterministic tests rather than LLM-based tests.

### 7.3 Documentation-aligned validation
Tests should map back to the implemented requirements and current design, not to speculative future architecture only.

---

## 8. Known Current Testing Limits

The current suite is strong for core service logic, but still limited in these areas:
- no real workflow execution engine yet
- no module execution runtime yet
- no real permission/policy enforcement tests yet
- no load/performance tests yet
- no multi-user concurrency tests yet
- no production persistence backend migration tests yet

---

## 9. Next Testing Priorities

As the system evolves, the next test groups to add should be:
1. workflow execution against data and event primitives
2. contradiction / priority analysis behavior
3. refinement flows from suggested skills into workflows/apps
4. policy and permission enforcement
5. persistent backend compatibility tests
6. longer-running service app recovery tests
7. layered context compaction and working-set derivation tests
   - summary/policy persistence and reload
   - auto compaction on stage change
   - working-set/detail views include workflow and skill execution references

---

## 10. Conclusion

The current testing strategy should continue to protect the system’s core identity:
- apps as managed long-lived objects
- deterministic runtime and data boundaries
- event-driven execution
- evolution from runtime practice into reusable capability suggestions

The test suite should grow with the architecture, but remain grounded in deterministic validation wherever possible.
