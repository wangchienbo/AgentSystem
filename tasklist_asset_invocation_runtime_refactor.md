# Tasklist: Phase P Asset Invocation Runtime Refactor

## Goal
Implement the Phase P governed invocation architecture defined in:
- `docs/phase-p-asset-invocation-runtime-and-session-binding.md`

This tasklist is the implementation driver for the full refactor. It is structured by phase and uses completion-oriented items.

---

## Phase 1. Protocol and Truth Layer

### 1.1 Invocation envelope and response contract
- [ ] Add invocation request envelope model
- [ ] Add invocation response envelope model
- [ ] Add compatibility adapter from legacy `asset_id + method + params`
- [ ] Add structured error taxonomy model
- [ ] Add unit tests for request envelope validation
- [ ] Add unit tests for response envelope validation
- [ ] Add unit tests for legacy normalization path

### 1.2 Session binding data model
- [ ] Add asset session binding record model
- [ ] Define required fields:
  - [ ] `asset_id`
  - [ ] `upstream_session_id`
  - [ ] `local_session_id`
  - [ ] `root_session_id`
  - [ ] `parent_session_id`
  - [ ] `status`
  - [ ] `created_at`
  - [ ] `last_active_at`
  - [ ] `metadata`
- [ ] Add uniqueness rule documentation for `(asset_id, upstream_session_id)`
- [ ] Add model serialization tests

### 1.3 Asset center persistence extensions
- [ ] Add session binding persistence API to asset center service
- [ ] Add read-by-asset-and-upstream-session API
- [ ] Add upsert binding API
- [ ] Add list/recent binding API for warmup/recovery support
- [ ] Add persistence-level uniqueness enforcement
- [ ] Add unit tests for uniqueness behavior
- [ ] Add unit tests for read / upsert behavior

### 1.4 Documentation sync for Phase 1
- [ ] Update `docs/design.md` to reference Phase P invocation contract
- [ ] Update `docs/system-relationship-map.md` for envelope + binding truth layer

---

## Phase 2. Inbound Runtime Layer Integration

### 2.1 Runtime wrapper core
- [ ] Add `AssetInvocationRuntimeLayer`
- [ ] Add `before_invoke(...)`
- [ ] Add `resolve_local_session(...)`
- [ ] Add `persist_binding(...)`
- [ ] Add `after_invoke(...)`
- [ ] Add structured binding-hit metadata (`memory`, `persisted`, `new`, `recovered_by_history`)

### 2.2 Binding resolver and cache
- [ ] Add in-memory binding cache
- [ ] Add binding cache lookup path
- [ ] Add persisted binding lookup path
- [ ] Add fallback historical-session judgment hook interface
- [ ] Add binding write-through behavior to cache and persistence
- [ ] Add unit tests for cache hit
- [ ] Add unit tests for persisted hit
- [ ] Add unit tests for fallback path

### 2.3 Runtime center integration
- [ ] Integrate `AssetInvocationRuntimeLayer` into runtime center asset call path
- [ ] Ensure all inbound asset calls pass through runtime layer before business logic
- [ ] Preserve compatibility for existing runtime-center callers
- [ ] Add integration tests for runtime-center wrapped invocation

### 2.4 Invocation dispatcher upgrade
- [ ] Upgrade dispatcher to accept unified invocation envelope
- [ ] Preserve current explicit dispatch API as compatibility shim
- [ ] Normalize old dispatches into new envelope internally
- [ ] Add tests for envelope-based dispatch
- [ ] Add tests for old-path normalization compatibility

### 2.5 Registration protocol wrapper injection
- [ ] Extend `AssetRegistrationProtocol` to register wrapped invocation behavior
- [ ] Ensure bare method mappings are not exposed without runtime wrapper participation
- [ ] Add tests proving registered assets are auto-wrapped

---

## Phase 3. Tool / vLLM and Context Assembly Convergence

### 3.1 Tool / vLLM request contract
- [ ] Define tool/vllm invocation request shape using `asset_id + local_session_id`
- [ ] Define tool/vllm response shape with traceable metadata
- [ ] Add contract tests

### 3.2 Context center query extensions
- [ ] Add query by `asset_id + local_session_id`
- [ ] Add recent window query
- [ ] Add summary query
- [ ] Add snapshot query
- [ ] Add evidence refs query
- [ ] Add tests for each query surface

### 3.3 Context bundle assembly
- [ ] Add budget-aware context assembly service or extend existing one
- [ ] Add summary-first assembly strategy
- [ ] Add snapshot inclusion rules
- [ ] Add evidence-ref inclusion rules
- [ ] Add token-budget tests

### 3.4 Tool / vLLM responsibility narrowing
- [ ] Remove or isolate any binding-truth assumptions from tool/vllm path
- [ ] Ensure tool/vllm only consumes resolved local session id
- [ ] Add tests proving local-session-based assembly behavior

### 3.5 Model invocation recording
- [ ] Record context refs used by model invocation
- [ ] Record token usage
- [ ] Record output summary
- [ ] Record trace linkage back to invocation request
- [ ] Add tests for model invocation logging structure

---

## Phase 4. Identity Resolution, Runtime Routing, and Endpoint Governance

### 4.1 Asset identity resolution
- [ ] Add asset alias model
- [ ] Add capability tag model
- [ ] Add name/alias/capability resolution API in asset center
- [ ] Add tests for identity resolution priority and ambiguity handling

### 4.2 Runtime registry and endpoint registry
- [ ] Add runtime registry model
- [ ] Add endpoint registry model
- [ ] Add lookup by `target_id`
- [ ] Add health/status fields
- [ ] Add tests for runtime lookup

### 4.3 Port allocator and endpoint conflict handling
- [ ] Add port allocation model and service
- [ ] Add endpoint uniqueness checks
- [ ] Add conflict detection behavior
- [ ] Add install-time allocation path
- [ ] Add tests for port conflict cases

### 4.4 Invocation routing integration
- [ ] Update invocation path to separate asset identity resolution from endpoint resolution
- [ ] Add integration tests for name -> target id -> endpoint -> invoke flow

---

## Phase 5. Registration, Installation, Packaging, and Generation Enforcement

### 5.1 Installer enforcement
- [ ] Extend installer to validate invocation-envelope compatibility
- [ ] Extend installer to validate runtime-wrapper compatibility
- [ ] Extend installer to validate session-binding participation declaration
- [ ] Add structured install failure reasons
- [ ] Add installer tests for compliant/non-compliant assets

### 5.2 Manifest expansion
- [ ] Add invocation contract version field
- [ ] Add runtime wrapper compatibility field
- [ ] Add session binding support field
- [ ] Add endpoint requirement field
- [ ] Add tool/vllm usage mode field
- [ ] Add manifest validation tests

### 5.3 Registration hardening
- [ ] Prevent registration of assets that bypass wrapper participation
- [ ] Add tests for rejection of non-compliant registration

### 5.4 New asset scaffolding
- [ ] Update asset scaffolding/templates to include runtime layer hooks
- [ ] Update generated asset defaults to include invocation envelope support
- [ ] Add tests or sample generation verification

### 5.5 Generated asset compliance
- [ ] Ensure generated assets default to compliant manifest + runtime wrapper structure
- [ ] Add validation coverage for generated assets

---

## Phase 6. Governance Views, Audit Replay, and End-to-End Validation

### 6.1 Runtime topology read model
- [ ] Add runtime topology read model
- [ ] Include assets, instances, sessions, bindings, and downstream invocation edges
- [ ] Add topology query tests

### 6.2 Audit and replay chain
- [ ] Add invocation audit record model
- [ ] Record request envelope
- [ ] Record binding resolution mode
- [ ] Record downstream call links
- [ ] Record tool/vllm usage links
- [ ] Add replay-oriented retrieval path
- [ ] Add replay tests for representative invocation chains

### 6.3 Error taxonomy propagation
- [ ] Propagate structured error taxonomy across dispatcher, runtime layer, tool/vllm, and persistence
- [ ] Add tests for error surface consistency

### 6.4 Multi-hop session propagation tests
- [ ] Add control -> app propagation test
- [ ] Add app -> skill propagation test
- [ ] Add skill -> child-skill propagation test
- [ ] Add root/upstream/local session relationship assertions

### 6.5 Restart recovery tests
- [ ] Add asset restart binding recovery test
- [ ] Add cold-start fallback session judgment test
- [ ] Add cache reload behavior test

### 6.6 End-to-end regression validation
- [ ] Add representative deterministic chain test
- [ ] Add representative LLM-assisted chain test
- [ ] Add mixed multi-hop chain test
- [ ] Add compatibility regression for legacy caller path

---

## Cross-cutting documentation and delivery
- [ ] Update `docs/design.md` after each completed phase boundary
- [ ] Update `docs/system-relationship-map.md` after structural code changes
- [ ] Add development log entry for each completed phase slice
- [ ] Commit at stable phase boundaries
- [ ] Push at stable phase boundaries
