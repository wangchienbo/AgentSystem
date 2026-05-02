# Tasklist: Phase P Asset Invocation Runtime Refactor

## Goal
Implement the Phase P governed invocation architecture defined in:
- `docs/phase-p-asset-invocation-runtime-and-session-binding.md`

This tasklist is the implementation driver for the full refactor. It is structured by phase and uses completion-oriented items.

---

## Phase 1. Protocol and Truth Layer

### 1.1 Invocation envelope and response contract
- [x] Add invocation request envelope model
- [x] Add invocation response envelope model
- [x] Add compatibility adapter from legacy `asset_id + method + params`
- [x] Add structured error taxonomy model
- [x] Add unit tests for request envelope validation
- [x] Add unit tests for response envelope validation
- [x] Add unit tests for legacy normalization path

### 1.2 Session binding data model
- [x] Add asset session binding record model
- [x] Define required fields:
  - [x] `asset_id`
  - [x] `upstream_session_id`
  - [x] `local_session_id`
  - [x] `root_session_id`
  - [x] `parent_session_id`
  - [x] `status`
  - [x] `created_at`
  - [x] `last_active_at`
  - [x] `metadata`
- [x] Add uniqueness rule documentation for `(asset_id, upstream_session_id)`
- [x] Add model serialization tests

### 1.3 Asset center persistence extensions
- [x] Add session binding persistence API to asset center service
- [x] Add read-by-asset-and-upstream-session API
- [x] Add upsert binding API
- [x] Add list/recent binding API for warmup/recovery support
- [x] Add persistence-level uniqueness enforcement
- [x] Add unit tests for uniqueness behavior
- [x] Add unit tests for read / upsert behavior

### 1.4 Documentation sync for Phase 1
- [x] Update `docs/design.md` to reference Phase P invocation contract
- [x] Update `docs/system-relationship-map.md` for envelope + binding truth layer

---

## Phase 2. Inbound Runtime Layer Integration

### 2.1 Runtime wrapper core
- [x] Add `AssetInvocationRuntimeLayer`
- [x] Add `before_invoke(...)`
- [x] Add `resolve_local_session(...)`
- [x] Add `persist_binding(...)`
- [x] Add `after_invoke(...)`
- [x] Add structured binding-hit metadata (`memory`, `persisted`, `new`, `recovered_by_history`)

### 2.2 Binding resolver and cache
- [x] Add in-memory binding cache
- [x] Add binding cache lookup path
- [x] Add persisted binding lookup path
- [x] Add fallback historical-session judgment hook interface
- [x] Add binding write-through behavior to cache and persistence
- [x] Add unit tests for cache hit
- [x] Add unit tests for persisted hit
- [x] Add unit tests for fallback path

### 2.3 Runtime center integration
- [x] Integrate `AssetInvocationRuntimeLayer` into runtime center asset call path
- [x] Ensure all inbound asset calls pass through runtime layer before business logic
- [x] Preserve compatibility for existing runtime-center callers
- [x] Add integration tests for runtime-center wrapped invocation

### 2.4 Invocation dispatcher upgrade
- [x] Upgrade dispatcher to accept unified invocation envelope
- [x] Preserve current explicit dispatch API as compatibility shim
- [x] Normalize old dispatches into new envelope internally
- [x] Add tests for envelope-based dispatch
- [x] Add tests for old-path normalization compatibility

### 2.5 Registration protocol wrapper injection
- [x] Extend `AssetRegistrationProtocol` to register wrapped invocation behavior
- [x] Ensure bare method mappings are not exposed without runtime wrapper participation
- [x] Add tests proving registered assets are auto-wrapped

---

## Phase 3. Tool / vLLM and Context Assembly Convergence

### 3.1 Tool / vLLM request contract
- [x] Define tool/vllm invocation request shape using `asset_id + local_session_id`
- [x] Define tool/vllm response shape with traceable metadata
- [x] Add contract tests

### 3.2 Context center query extensions
- [x] Add query by `asset_id + local_session_id`
- [x] Add recent window query
- [x] Add summary query
- [x] Add snapshot query
- [x] Add evidence refs query
- [x] Add tests for each query surface

### 3.3 Context bundle assembly
- [x] Add budget-aware context assembly service or extend existing one
- [x] Add summary-first assembly strategy
- [x] Add snapshot inclusion rules
- [x] Add evidence-ref inclusion rules
- [x] Add token-budget tests

### 3.4 Tool / vLLM responsibility narrowing
- [x] Remove or isolate any binding-truth assumptions from tool/vllm path
- [x] Ensure tool/vllm only consumes resolved local session id
- [x] Add tests proving local-session-based assembly behavior

### 3.5 Model invocation recording
- [x] Record context refs used by model invocation
- [x] Record token usage
- [x] Record output summary
- [x] Record trace linkage back to invocation request
- [x] Add tests for model invocation logging structure

---

## Phase 4. Identity Resolution, Runtime Routing, and Endpoint Governance

### 4.1 Asset identity resolution
- [x] Add asset alias model
- [x] Add capability tag model
- [x] Add name/alias/capability resolution API in asset center
- [x] Add tests for identity resolution priority and ambiguity handling

### 4.2 Runtime registry and endpoint registry
- [x] Add runtime registry model
- [x] Add endpoint registry model
- [x] Add lookup by `target_id`
- [x] Add health/status fields
- [x] Add tests for runtime lookup

### 4.3 Port allocator and endpoint conflict handling
- [x] Add port allocation model and service
- [x] Add endpoint uniqueness checks
- [x] Add conflict detection behavior
- [x] Add install-time allocation path
- [x] Add tests for port conflict cases

### 4.4 Invocation routing integration
- [x] Update invocation path to separate asset identity resolution from endpoint resolution
- [x] Add integration tests for name -> target id -> endpoint -> invoke flow

---

## Phase 5. Registration, Installation, Packaging, and Generation Enforcement

### 5.1 Installer enforcement
- [x] Extend installer to validate invocation-envelope compatibility
- [x] Extend installer to validate runtime-wrapper compatibility
- [x] Extend installer to validate session-binding participation declaration
- [x] Add structured install failure reasons
- [x] Add installer tests for compliant/non-compliant assets

### 5.2 Manifest expansion
- [x] Add invocation contract version field
- [x] Add runtime wrapper compatibility field
- [x] Add session binding support field
- [x] Add endpoint requirement field
- [x] Add tool/vllm usage mode field
- [x] Add manifest validation tests

### 5.3 Registration hardening
- [x] Prevent registration of assets that bypass wrapper participation
- [x] Add tests for rejection of non-compliant registration

### 5.4 New asset scaffolding
- [x] Update asset scaffolding/templates to include runtime layer hooks
- [x] Update generated asset defaults to include invocation envelope support
- [x] Add tests or sample generation verification

### 5.5 Generated asset compliance
- [x] Ensure generated assets default to compliant manifest + runtime wrapper structure
- [x] Add validation coverage for generated assets

---

## Phase 6. Governance Views, Audit Replay, and End-to-End Validation

### 6.1 Runtime topology read model
- [x] Add runtime topology read model
- [x] Include assets, instances, sessions, bindings, and downstream invocation edges
- [x] Add topology query tests

### 6.2 Audit and replay chain
- [x] Add invocation audit record model
- [x] Record request envelope
- [x] Record binding resolution mode
- [x] Record downstream call links
- [x] Record tool/vllm usage links
- [x] Add replay-oriented retrieval path
- [x] Add replay tests for representative invocation chains

### 6.3 Error taxonomy propagation
- [x] Propagate structured error taxonomy across dispatcher, runtime layer, tool/vllm, and persistence
- [x] Add tests for error surface consistency

### 6.4 Multi-hop session propagation tests
- [x] Add control -> app propagation test
- [x] Add app -> skill propagation test
- [x] Add skill -> child-skill propagation test
- [x] Add root/upstream/local session relationship assertions

### 6.5 Restart recovery tests
- [x] Add asset restart binding recovery test
- [x] Add cold-start fallback session judgment test
- [ ] Add cache reload behavior test

### 6.6 End-to-end regression validation
- [x] Add representative deterministic chain test
- [ ] Add representative LLM-assisted chain test
- [ ] Add mixed multi-hop chain test
- [x] Add compatibility regression for legacy caller path

---

## Cross-cutting documentation and delivery
- [ ] Update `docs/design.md` after each completed phase boundary
- [ ] Update `docs/system-relationship-map.md` after structural code changes
- [ ] Add development log entry for each completed phase slice
- [ ] Commit at stable phase boundaries
- [ ] Push at stable phase boundaries
