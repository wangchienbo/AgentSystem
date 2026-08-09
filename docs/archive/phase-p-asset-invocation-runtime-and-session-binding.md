# AgentSystem Phase P: Asset Invocation Runtime, Session Binding, and Governed RPC Architecture

## 1. Background and Problem Statement

AgentSystem has already completed the main asset-centered runtime convergence on the model-facing surface. The preferred runtime invocation surface is now `call_asset_method`, and the current codebase already contains reusable substrate pieces including:

- asset registration via `AssetRegistrationProtocol`
- asset descriptors and method declarations in the asset center
- invocation validation and dispatch via `InvocationDispatcher`
- runtime execution routing via `RuntimeCenter.call_asset_method(...)`
- interaction-side orchestration and context refresh scaffolding

This is enough to support capability invocation, but it is not yet enough to support governed, recoverable, recursive, session-aware operation across the full system.

The current system still has several structural gaps:

1. invocation requests are still centered on `asset_id + method + params` and do not yet carry a unified session-aware invocation envelope
2. assets do not yet have a mandatory shared inbound runtime layer that executes before business logic
3. session continuity across user -> control -> app -> skill -> child skill chains is not yet a first-class runtime contract
4. the asset center does not yet persist the unique upstream-to-local session binding truth required for restart recovery and stable multi-hop continuity
5. context content and session binding truth are not yet fully separated into distinct system authorities
6. tool / vllm context assembly is not yet fully narrowed to the role of consuming an already-resolved local asset session
7. registration, installation, packaging, and generation flows do not yet forcibly guarantee that every new asset participates in the governed invocation contract
8. runtime-wide observability, audit replay, and topology views are not yet shaped around the new recursive invocation and session-binding model

This phase defines the architecture required to close those gaps without discarding the current asset-centered runtime backbone.

---

## 2. Design Goals

### 2.1 Primary goals

This phase must deliver a system in which:

- every cross-layer invocation uses a unified RPC-style invocation contract
- every asset inbound call passes through a mandatory runtime governance layer before business logic executes
- every asset can maintain multiple internal local sessions
- for any given asset, one upstream session id maps to exactly one local session id
- the upstream-to-local session binding truth persists in the asset center and survives restarts
- context content remains stored and queried through the context center
- tool / vllm invocation uses `asset_id + local_session_id` to assemble model context, rather than acting as the source of session-binding truth
- new assets cannot bypass the governed invocation contract through custom registration, packaging, or installation shortcuts
- the whole runtime becomes traceable, replayable, and inspectable as a governed system rather than a loose function-call graph

### 2.2 Secondary goals

This phase should also improve:

- runtime routing and endpoint discovery
- future process isolation compatibility
- port and endpoint governance
- generated asset compliance
- error classification and replayability
- multi-hop trace clarity
- long-running continuity across restarts and upgrades

### 2.3 Non-goals

This phase does not require:

- a full distributed transport rollout on day one
- immediate removal of all current compatibility helpers
- rewriting every asset implementation at once
- collapsing the distinction between App, Skill, and Asset product semantics

---

## 3. Design Constraints and Compatibility Principles

### 3.1 Preserve the current asset-centered backbone

The current substrate is not to be discarded. The following existing structures are authoritative starting points and must be reused:

- `AssetRegistrationProtocol`
- `InvocationDispatcher`
- `RuntimeCenter.call_asset_method(...)`
- asset descriptor and method declaration models
- runtime-side service reference and method mapping registration

### 3.2 Add governance on top of invocation, not alongside it

The system must not grow a second unrelated invocation path. The new phase must strengthen the existing invocation path with:

- a unified invocation envelope
- a mandatory inbound runtime layer
- session binding persistence
- stronger runtime routing metadata

### 3.3 Preserve model-facing simplicity while strengthening internal truth

The model-facing capability surface may remain simple, but internal runtime truth must become stricter. Lower-level runtime authority must no longer depend on prompt-only interpretation.

### 3.4 Enforce compatibility by mechanism, not by convention

No future asset should rely on developers remembering to do the right thing. Registration, installation, packaging, and generation must all enforce participation in the governed invocation architecture.

---

## 4. Core Concept Definitions

### 4.1 Asset

Asset is the unified runtime invocation abstraction. An Asset is the object that can:

- declare methods
- be registered
- be discovered
- receive inbound invocation
- participate in governed runtime execution

Both Apps and Skills participate in runtime invocation as Assets.

### 4.2 App

App is the product-level delivery and orchestration unit. An App may:

- own product-facing behavior
- own app-level lifecycle
- orchestrate child assets or skills
- expose one or more runtime capabilities through its asset form

### 4.3 Skill

Skill is the reusable capability unit. A Skill may:

- be deterministic or LLM-assisted
- be invoked directly by an App or other governing layer
- expose reusable methods as an asset-capable runtime unit

### 4.4 AssetInvocationRuntimeLayer

A mandatory inbound runtime layer executed before any asset business logic. This layer is not the tool layer and not the vllm layer. It is the shared runtime governance layer for all asset invocations.

Its responsibilities are:

1. upload inbound context events
2. parse the upstream session reference
3. resolve the local asset session id
4. hit memory binding cache when possible
5. hit persisted asset-center binding truth when possible
6. trigger historical-session judgment only when binding does not yet exist
7. persist any new binding truth
8. hand the resolved local session id into actual business execution

### 4.5 Tool / vLLM Layer

The tool layer in this phase refers to the vllm/model invocation context assembly layer. It is not the inbound asset runtime governance layer.

Its responsibilities are:

- consume `asset_id + local_session_id`
- query the context center for context content
- assemble prompt/context bundles
- invoke the model
- record model invocation summaries and traces

It must not be treated as the source of session-binding truth.

### 4.6 Upstream Session ID

The session id passed into an asset from its caller. This is the caller-layer session reference, not necessarily the callee's local session id.

### 4.7 Local Session ID

The session id resolved and owned inside the current asset.

### 4.8 Root Session ID

The root session reference for a multi-hop tree of invocations.

### 4.9 Session Binding Truth

The authoritative persisted mapping:

```text
(asset_id, upstream_session_id) -> local_session_id
```

This truth belongs to the asset center, not to the context center.

### 4.10 Context Content Truth

The event history, snapshots, summaries, evidence refs, and context material used for prompt assembly. This truth belongs to the context center.

---

## 5. Overall Architecture

### 5.1 Invocation chain

The governed invocation chain is:

- user layer -> control layer
- control layer -> app asset
- app asset -> skill / child asset
- asset internal logic -> tool / vllm when model assistance is needed

Every cross-layer invocation uses the same session-aware envelope shape.

### 5.2 Responsibility split

#### Control layer
- interprets user intent
- selects target app or asset
- assembles invocation request
- directly performs RPC-style invocation to the target
- uploads control-side context events

#### Asset inbound runtime layer
- uploads inbound asset event
- resolves local asset session id from upstream session
- persists and recovers binding truth
- forwards execution to business logic

#### Asset business logic
- executes deterministic or orchestrated behavior
- may invoke child assets
- may call tool / vllm when LLM assistance is needed

#### Tool / vllm layer
- assembles model context using local asset session
- calls the model
- records model invocation evidence

#### Asset center
- stores asset descriptors and asset session binding truth
- supports target identity lookup and runtime metadata

#### Context center
- stores event streams, summaries, snapshots, and context content for prompt assembly

#### Runtime registry / endpoint registry
- stores runtime endpoint and instance routing truth

---

## 6. Unified RPC Contract

### 6.1 Request envelope

All cross-layer invocations must use a unified request envelope.

Required structure:

```json
{
  "request_id": "...",
  "target_id": "...",
  "target_type": "app|skill|system_asset|vllm",
  "method": "...",
  "args": {},
  "session": {
    "upstream_session_id": "...",
    "root_session_id": "...",
    "parent_session_id": "..."
  },
  "caller": {
    "caller_id": "...",
    "caller_type": "user|control|app|skill"
  },
  "trace_context": {},
  "metadata": {}
}
```

### 6.2 Response envelope

All invoked assets must return a unified response envelope.

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "resolved_local_session_id": "...",
  "request_id": "...",
  "trace_context": {},
  "state_updates": {},
  "metadata": {}
}
```

### 6.3 Error taxonomy

At minimum the runtime must distinguish:

- `routing_error`
- `binding_error`
- `context_error`
- `invocation_error`
- `runtime_error`
- `model_error`
- `persistence_error`

This taxonomy must be available in structured responses, logs, and replay artifacts.

### 6.4 Compatibility rule

The existing `asset_id + method + params` invocation shape must remain temporarily available as a compatibility adapter, but all new runtime logic must normalize into the unified envelope internally.

---

## 7. Tree-Structured Session Binding Model

### 7.1 Session tree model

Invocation continuity is tree-structured rather than globally flat. Example:

- `user_session`
  - `control_session`
    - `app_session`
      - `skill_session`

Each layer owns its own local session ids.

### 7.2 Uniqueness rule

Within a single asset:

- many local session ids may exist
- but one upstream session id may bind to exactly one local session id

Formal rule:

```text
(asset_id, upstream_session_id) -> unique local_session_id
```

The reverse direction is not the primary truth contract for this phase.

### 7.3 Binding lookup order

When an asset receives an invocation:

1. lookup `(asset_id, upstream_session_id)` in memory binding cache
2. if absent, lookup persisted binding truth in the asset center
3. if absent, perform historical-session judgment and produce a new or recovered local session id
4. persist the resolved binding in both memory and asset-center storage

### 7.4 Historical-session judgment

Historical judgment is a fallback, not the default path.

It is only allowed when binding truth does not already exist.

The judgment process may inspect:

- historical session candidates
- recent summaries
- snapshots
- structured context signals
- model-assisted ranking or disambiguation

The judgment result must always become a persisted binding truth after resolution.

### 7.5 Restart recovery

On asset restart:

- hot bindings may be preloaded into memory cache
- cold bindings remain recoverable from the asset center
- if neither exists, fallback session judgment may run

---

## 8. Asset Invocation Runtime Layer

### 8.1 Position in the call stack

For every inbound asset call, execution order must be:

1. invocation envelope accepted
2. `AssetInvocationRuntimeLayer.before_invoke(...)`
3. session binding resolution
4. asset business logic invocation
5. `AssetInvocationRuntimeLayer.after_invoke(...)`
6. response envelope emitted

### 8.2 Responsibilities

The runtime layer must:

- upload inbound invocation event
- validate presence and shape of session reference
- resolve local session id
- record binding hit mode (`memory`, `persisted`, `new`, `recovered_by_history`)
- maintain binding cache freshness
- persist new or updated binding truth
- decorate outbound execution context with the resolved local session id
- ensure errors are emitted with structured error type and trace linkage

### 8.3 Non-responsibilities

The runtime layer must not:

- assemble vllm prompt context itself
- act as the global content storage authority
- act as the long-term governance evidence store
- directly replace asset business logic

### 8.4 Hook model

A preferred interface shape is:

- `before_invoke(envelope)`
- `resolve_local_session(envelope)`
- `persist_binding(binding)`
- `invoke_actual_logic(...)`
- `after_invoke(result)`

All asset invocations must pass through this wrapper.

---

## 9. Asset Center Responsibilities in This Phase

### 9.1 Existing preserved roles

The asset center remains responsible for:

- asset descriptors
- method schemas
- asset identity lookup
- asset metadata
- model records and requirements where already applicable

### 9.2 New required role: session binding truth authority

The asset center must add an authoritative persisted session binding store.

Required persisted fields include:

- `asset_id`
- `upstream_session_id`
- `local_session_id`
- `root_session_id`
- `parent_session_id`
- `status`
- `created_at`
- `last_active_at`
- `metadata`

### 9.3 Required uniqueness constraint

The store must enforce:

```text
UNIQUE(asset_id, upstream_session_id)
```

### 9.4 Required APIs

At minimum the asset center must support:

- resolve target by name / alias / capability tag
- get descriptor by target id
- read session binding by `(asset_id, upstream_session_id)`
- upsert binding truth
- preload or stream active bindings for runtime warmup

---

## 10. Context Center Responsibilities in This Phase

### 10.1 Content authority only

The context center is the content source for:

- inbound and outbound events
- user-visible messages
- control-side events
- asset execution events
- tool / model invocation summaries
- snapshots
- summaries
- evidence refs
- context chunks

### 10.2 Required query surfaces

The context center must support at least:

- query by `asset_id + local_session_id`
- recent event window queries
- session summary queries
- snapshot retrieval
- evidence reference retrieval
- budget-aware context bundle assembly support

### 10.3 Explicit non-goal

The context center must not become the authoritative source of session binding truth.

---

## 11. Tool / vLLM Layer Responsibilities

### 11.1 Invocation contract

When an asset needs LLM assistance, the tool / vllm layer receives:

- `asset_id`
- `local_session_id`
- current task input
- optional model or invocation metadata

### 11.2 Responsibilities

The tool / vllm layer must:

- query the context center using `asset_id + local_session_id`
- assemble prompt/context under explicit budget controls
- invoke the model
- record input refs, context refs, output summary, and token usage
- return structured model results to the asset business logic

### 11.3 Non-responsibilities

The tool / vllm layer must not:

- invent the authoritative asset session binding
- decide which upstream session maps to which local asset session unless explicitly called only as fallback ranking assistance by the runtime layer
- replace the asset center as session-binding truth authority

---

## 12. Asset Identity, Discovery, and Runtime Routing

### 12.1 Static identity resolution

The caller may begin with:

- app name
- skill name
- alias
- capability tag

This must first resolve through the asset center into:

- `target_id`
- `target_type`
- descriptor and method declarations

### 12.2 Dynamic runtime routing

Once `target_id` is resolved, the runtime must then resolve:

- `instance_id`
- `host`
- `port`
- `protocol`
- `health`
- startup / readiness status

This routing truth belongs to the runtime registry / endpoint registry.

### 12.3 Port and endpoint governance

This phase should also incorporate:

- endpoint uniqueness rules
- install-time port allocation
- endpoint conflict detection
- transport metadata for future process isolation

These should be integrated into the total redesign rather than deferred into a separate project.

---

## 13. Registration, Installation, Packaging, and Generation Enforcement

### 13.1 Registration-time enforcement

`AssetRegistrationProtocol` must be upgraded so that asset registration does not expose bare business handlers directly. Instead, registration must automatically wrap assets in the shared inbound runtime governance layer.

### 13.2 Installation-time enforcement

The installer must reject assets that do not declare compatibility with:

- the unified invocation envelope
- the runtime wrapper contract
- session binding participation
- method / schema / runtime entry requirements

### 13.3 Manifest additions

Asset manifests must declare at least:

- invocation contract version
- runtime wrapper compatibility
- session binding support
- endpoint requirements
- tool / vllm usage mode (`none | optional | required`)

### 13.4 Generated asset compliance

Any future asset generation path must emit assets already compatible with:

- the standard invocation envelope
- the runtime wrapper
- session binding hooks
- context upload hooks

Generated assets must never bypass the governed invocation contract.

---

## 14. Runtime Topology, Audit Replay, and Governance Views

### 14.1 Runtime topology view

The system should expose a runtime topology or governance read model capable of answering:

- what assets exist
- which instances are active
- which sessions are active
- which bindings are hot
- which assets are invoking which downstream assets
- which model invocations are currently happening
- which assets are missing required compatibility features
- which endpoints conflict or are unhealthy

### 14.2 Audit replay chain

Every invocation should be replayable through structured artifacts that capture:

- caller identity
- target identity
- request envelope
- binding resolution mode
- resolved local session id
- downstream invocations
- tool/vllm usage
- context refs used
- final output and error metadata

### 14.3 Governance implication

This phase turns the invocation substrate into a governed runtime rather than just a working call graph.

---

## 15. Phased Implementation Requirements

## Phase 1. Protocol and Truth Layer

### Objective
Establish the canonical invocation and binding contracts.

### Scope
- define invocation request envelope
- define invocation response envelope
- define structured error taxonomy
- define session binding model
- define asset-center binding persistence schema and uniqueness constraints

### Required outputs
- formal envelope schemas
- binding record schema
- asset center persistence implementation or migration plan
- compatibility adapter definition for legacy call sites

### Hard constraints
- binding truth must not be placed in the context center
- no downstream implementation may invent a second incompatible envelope
- uniqueness constraint for `(asset_id, upstream_session_id)` must be explicitly enforced in persistence design

### Acceptance criteria
- schema definitions committed
- binding schema committed
- persistence API committed
- uniqueness constraint tests passing
- compatibility notes documented

## Phase 2. Inbound Runtime Layer Integration

### Objective
Make every asset invocation pass through the governed inbound runtime layer.

### Scope
- implement `AssetInvocationRuntimeLayer`
- integrate runtime layer into `RuntimeCenter`
- upgrade `InvocationDispatcher` to normalize invocation envelopes
- implement binding cache and binding resolver

### Required outputs
- runtime wrapper implementation
- dispatcher envelope support
- cache + resolver implementation
- integration tests for runtime layer entry behavior

### Hard constraints
- asset business logic must no longer be directly invoked from the runtime center without passing through the shared runtime layer
- legacy callers may remain supported, but internal execution must normalize into the new path

### Acceptance criteria
- memory-hit binding flow passes
- persisted-hit binding flow passes
- fallback historical-judgment flow passes
- response envelope includes resolved local session id

## Phase 3. Tool / vLLM and Context Assembly Convergence

### Objective
Constrain the tool/vllm layer to context-content assembly based on resolved local asset sessions.

### Scope
- define tool/vllm invocation contract around `asset_id + local_session_id`
- add context-center query interfaces for content assembly
- add summaries / snapshots / budget-aware bundle assembly support
- record model invocation traces and summaries

### Required outputs
- tool/vllm request contract
- context-center query APIs
- prompt context assembly policy
- model invocation recording schema

### Hard constraints
- tool / vllm must not become the source of binding truth
- local session id must already be resolved before normal vllm context assembly begins

### Acceptance criteria
- prompt assembly tests pass using local session ids
- snapshot/summarization path passes
- token-budget-aware assembly tests pass
- model invocation records are written with trace linkage

## Phase 4. Identity Resolution, Runtime Routing, and Endpoint Governance

### Objective
Separate static asset identity resolution from dynamic endpoint routing.

### Scope
- alias and capability resolution in the asset center
- runtime registry and endpoint registry
- port allocation and endpoint conflict handling
- future-compatible transport metadata

### Required outputs
- alias/capability lookup model
- runtime registry design and implementation
- endpoint registry design and implementation
- port allocator plan or implementation

### Hard constraints
- caller identity resolution and runtime endpoint resolution must not be conflated into one opaque function
- endpoint uniqueness policy must be explicit

### Acceptance criteria
- asset-name/alias resolution tests pass
- runtime endpoint lookup tests pass
- endpoint conflict tests pass
- install-time allocation tests pass where applicable

## Phase 5. Enforcement Across Registration, Installation, Packaging, and Generation

### Objective
Guarantee that every future asset participates in the governed runtime contract.

### Scope
- registration-time auto-wrapper injection
- installer validation of envelope/runtime compatibility
- manifest expansion
- asset generation and scaffolding updates

### Required outputs
- registration wrapper injection logic
- installer validation logic
- manifest contract updates
- new-asset scaffolding updates

### Hard constraints
- no newly installed asset may bypass the runtime wrapper
- generated assets must default to compliance

### Acceptance criteria
- non-compliant asset install fails with structured error
- compliant asset install succeeds and is auto-wrapped
- generated asset template includes runtime-layer participation hooks

## Phase 6. Governance Read Models, Audit Replay, and End-to-End Validation

### Objective
Make the governed runtime observable, replayable, and operationally trustworthy.

### Scope
- runtime topology read model
- audit replay chain
- unified error reporting integration
- end-to-end scenario validation
- restart recovery validation

### Required outputs
- runtime topology query surface
- replay-ready invocation audit records
- error taxonomy integration across layers
- end-to-end regression suite

### Hard constraints
- critical invocation chains must become replayable
- restart continuity of binding truth must be demonstrable

### Acceptance criteria
- multi-hop tree session propagation tests pass
- restart recovery tests pass
- replay chain for representative scenarios passes
- runtime topology queries produce coherent results
- end-to-end complex scenario suite passes

---

## 16. Migration Strategy

### 16.1 Preserve existing invocation entry points temporarily

The current `asset_id + method + params` entry path remains temporarily available as a compatibility shape, but the runtime must internally normalize it to the new envelope.

### 16.2 Gradual asset migration

Existing assets should be migrated by:

1. registering under the auto-injected runtime wrapper
2. adopting standard response envelopes
3. integrating local session usage where needed
4. gradually narrowing legacy shortcuts

### 16.3 Binding store initialization

If prior stable session continuity information exists in any form, a migration path should be considered. Otherwise the system may begin fresh binding capture on first governed runtime execution.

### 16.4 Rollout discipline

Rollout should prefer additive compatibility first, then tightening enforcement once the wrapper path is stable and tested.

---

## 17. Validation and Acceptance Standard

The redesign is not complete until the following are true:

1. all representative inbound asset calls pass through the shared runtime layer
2. session binding persistence exists in the asset center
3. `(asset_id, upstream_session_id)` uniqueness is enforced
4. tool/vllm context assembly operates on resolved local asset sessions
5. old and new invocation entry paths remain compatibility-safe during migration
6. newly installed/generated assets cannot bypass the governed runtime contract
7. runtime topology and replay artifacts are sufficient to inspect representative invocation chains
8. restart recovery succeeds for representative asset binding scenarios
9. complex end-to-end flows involving control -> app -> skill -> vllm remain green

---

## 18. Recommended Immediate Next Steps

1. commit this design as the phase baseline
2. add a dedicated tasklist derived directly from the six implementation phases
3. implement Phase 1 schemas and persistence first
4. wire `AssetInvocationRuntimeLayer` into runtime entry as the first major code change
5. only then proceed to tool/vllm context convergence and runtime routing expansion
