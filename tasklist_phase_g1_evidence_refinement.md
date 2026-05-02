# Tasklist: Phase G1 Evidence Refinement and Replay-Grade Observation

## Goal
Implement the next-stage governance observation substrate described in `docs/design.md` Phase G1 so regression governance can reason over layered evidence instead of only coarse run summaries.

---

## Phase 1. Observation and evidence contracts

### 1.1 Observation record model
- [x] Add `ObservationRecord` model
- [x] Include observation identity, source, scope, timestamps, and trace linkage
- [x] Include contradiction-family-ready `domain / subdomain / signal` fields
- [x] Add serialization and validation tests

### 1.2 Evidence envelope model
- [x] Add `EvidenceEnvelope` model
- [x] Support evidence layers:
  - [x] input evidence
  - [x] routing evidence
  - [x] tool-selection evidence
  - [x] execution evidence
  - [x] output evidence
  - [x] user-feedback evidence
- [x] Add evidence grade / confidence / refs fields
- [x] Add validation tests

### 1.3 Governance digest contract
- [x] Add `GovernanceEvidenceDigest` model
- [x] Add summary reducers for evidence-layer counts and dominant failure layer
- [x] Add unit tests

---

## Phase 2. Replay-grade sample ingestion

### 2.1 Replay regression sample model
- [x] Add `ReplayRegressionSample` model
- [x] Support fixed prompt seed linkage and historical replay provenance
- [x] Add bounded payload / excerpt rules
- [x] Add validation tests

### 2.2 Curated replay ingestion path
- [x] Add ingestion service for curated replay-backed samples
- [x] Ensure ingestion is bounded and not a raw mirror of production traffic
- [x] Add tests for acceptance / rejection rules

### 2.3 Persistence and retrieval
- [x] Add persistence path for replay samples
- [x] Add list / recent retrieval APIs
- [x] Add tests for persistence roundtrip

---

## Phase 3. Regression evidence layering

### 3.1 Fixed regression enrichment
- [x] Extend fixed regression run artifacts with evidence envelopes
- [x] Record layer-specific evidence for routing, execution, and output shaping
- [x] Add tests for enriched artifact structure

### 3.2 Live observation compatibility path
- [x] Extend live chat observation persistence to emit layer-aware evidence envelopes
- [x] Keep existing read-side digests compatibility-safe
- [x] Add tests for additive compatibility behavior

### 3.3 Failure attribution
- [x] Add attribution rules for:
  - [x] requirement misunderstanding
  - [x] routing error
  - [x] missing evidence
  - [x] bad tool execution
  - [x] weak final answer shaping
- [x] Add unit tests for attribution classification

---

## Phase 4. Governance operator surfaces

### 4.1 Evidence-layer digests
- [x] Update governance summary builders to include dominant evidence layer and counts
- [x] Add tests for operator summary payloads

### 4.2 Nightly/manual regression compatibility
- [ ] Include bounded replay-backed slice in nightly/manual governance cycle inputs
- [ ] Keep current canonical prompt matrix intact
- [ ] Add regression tests

### 4.3 Self-iteration visibility
- [ ] Expose additive self-iteration summaries for replay-grade observation state
- [ ] Add tests for asset-facing read models

---

## Cross-cutting documentation and delivery
- [ ] Update `docs/design.md` after each completed phase boundary
- [ ] Update `docs/system-relationship-map.md` after structural changes
- [ ] Update `docs/testing.md` and `docs/testing-detail.md` for new evidence/replay validation slices
- [ ] Add development log entry for each completed phase slice
- [ ] Commit at stable phase boundaries
- [ ] Push at stable phase boundaries
