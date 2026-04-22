# Phase IV Planning - Risk Guards Validation & Architecture Decisions

> **Status**: Planning
> **Previous Phase**: Phase III (Iteration 13-15) - Documentation Mapping, Risk Guards Inventory, Mismatch List v1
> **Entry Document**: `docs/mismatch-list-v1.md`
> **Goal**: Complete risk guards validation, make architectural decisions for long-term optimization

---

## 1. Entry Context

Phase III successfully consolidated the baseline:
- Documentation mapping aligned across 5 key documents
- Risk guards inventory identified 6 categories with clear gaps
- Mismatch list v1 captured 10 mismatches (5 resolved, 5 active)

The most urgent gaps from mismatch list v1 requiring Phase IV attention:

| ID | Mismatch | Priority | Current Status |
|----|----------|----------|----------------|
| DG-002 | Rate limiter/budget tracker main path wiring evidence | P2 | Implementation exists, integration evidence missing |
| OB-002 | Risk guard observability gaps - focused validation | P2 | No focused tests for block/reject scenarios |
| IC-003 | Budget/quota dual track unification decision | P2 | Two parallel implementations need architectural decision |
| CF-003 | Multi-intent decomposition (optional) | P3 | Identified gap, not blocking |
| OB-001 | Context summary productization | P3 | Debug-style → UX polish |
| IC-004 | Contract linter doc path alignment | P3 | Documentation drift |

---

## 2. Phase IV Scope

### Track A: Risk Guards Focused Validation (P2)
**Goal**: Prove that risk guards are actually wired and working in the main path.

#### A1. Rate Limiter Integration Evidence
- **Target**: `app/services/rate_limiter.py`
- **Question**: Is rate limiter actually invoked in gateway/interpreter main path?
- **Deliverable**: 
  - Integration point mapping document
  - Focused test verifying rate limiting triggers correctly
  - Documentation of degradation behavior when limits hit

#### A2. Tool Loop Guard Validation
- **Target**: `app/services/tool_loop_guard.py`
- **Question**: Does tool loop guard actually block infinite loops in production?
- **Deliverable**:
  - E2E test with forced loop scenario
  - Verification of block/reject observability

#### A3. Contract Linter Wiring
- **Target**: `app/services/contract_linter.py`
- **Question**: Is contract validation actually invoked before tool execution?
- **Deliverable**:
  - Main path integration point identified
  - Test showing contract rejection path

#### A4. Budget/Quota Observability
- **Target**: `app/services/budget_tracker.py`, `AppManagementWorker.CostQuotaManager`
- **Question**: Are budget overruns actually observable and blocking?
- **Deliverable**:
  - Focused test for budget limit enforcement
  - Metrics/audit logging verification

### Track B: Architecture Decisions (P2/P3)
**Goal**: Make explicit architectural decisions for long-term consistency.

#### B1. Budget/Quota Unification Decision
**Context**:
- `budget_tracker.py` - token-level resource tracking
- `CostQuotaManager` - governance-level operation quotas

**Decision Needed**:
- Option 1: Merge into unified quota system
- Option 2: Keep separated (resource vs governance concerns)
- Option 3: Layer them (budget tracker as foundation, quota as policy layer)

**Deliverable**: Architecture decision record (ADR) documenting choice and migration path

#### B2. Observability Architecture Review
**Questions**:
- Should command-level and workflow observability merge?
- What's the single source of truth for execution metrics?
- How do risk guard blocks surface in observability?

**Deliverable**: Observability architecture doc update

### Track C: Optional Improvements (P3)

#### C1. Multi-Intent Decomposition (Deferred from Iteration 9)
- **Status**: Not blocking, identified gap
- **Decision**: Implement only if user scenarios demand
- **Action**: Move to backlog, monitor for demand

#### C2. Context Summary Productization
- **Target**: `AppPresenter._append_context_summary`
- **Current**: Debug-style structured output
- **Target**: Natural, user-friendly interaction copy
- **Action**: UX copy polish (low priority)

#### C3. Documentation Path Alignment
- **Target**: `risk-guards-design.md` vs actual file paths
- **Action**: Align documented paths with implementation

---

## 3. Proposed Iteration Breakdown

### Iteration 16 - Rate Limiter & Tool Loop Guard Focused Validation
- **Goal**: Prove rate limiter and tool loop guard are wired and functional
- **Deliverables**:
  - Integration point mapping for rate limiter in gateway/interpreter
  - Focused test: `test_rate_limiter_blocks_excessive_queries`
  - Focused test: `test_tool_loop_guard_detects_infinite_loop`
  - Update `docs/risk-guards-design.md` with actual integration points
- **Entry**: `docs/mismatch-list-v1.md` DG-002, OB-002

### Iteration 17 - Contract Linter & Budget Validation
- **Goal**: Validate contract linter and budget tracker integration
- **Deliverables**:
  - Integration point mapping for contract linter
  - Focused test: `test_contract_linter_rejects_invalid_args`
  - Focused test: `test_budget_tracker_enforces_limits`
  - Observability verification for block events
- **Entry**: `docs/mismatch-list-v1.md` OB-002, IC-003

### Iteration 18 - Architecture Decision: Budget/Quota Unification
- **Goal**: Make explicit architectural decision and document migration path
- **Deliverables**:
  - ADR: Budget/Quota system unification decision
  - If decision is "unify": Implementation plan for merging tracks
  - If decision is "layer": Document clear separation of concerns
  - Update relevant design docs with decision
- **Entry**: `docs/mismatch-list-v1.md` IC-003

### Iteration 19 - Observability & Documentation Cleanup
- **Goal**: Complete observability architecture, align documentation paths
- **Deliverables**:
  - Observability architecture update (command vs workflow unification)
  - `risk-guards-design.md` path alignment
  - Context summary productization (if time permits)
- **Entry**: `docs/mismatch-list-v1.md` OB-001, IC-004

---

## 4. Exit Criteria

Phase IV completes when:
- [ ] Rate limiter integration evidence documented and tested
- [ ] Tool loop guard block behavior verified with focused test
- [ ] Contract linter main path wiring identified and validated
- [ ] Budget/quota observability gaps closed
- [ ] Budget/Quota unification ADR complete
- [ ] Documentation paths aligned with implementation
- [ ] Updated mismatch list v2 (if any P2 gaps remain)
- [ ] Clear Phase V entry defined (likely: governance expansion or performance optimization)

---

## 5. Risk & Dependencies

| Risk | Mitigation |
|------|-----------|
| Rate limiter not actually wired to main path | Accept finding, create wiring task as Phase IV extension |
| Budget/Quota decision requires stakeholder input | Prepare decision memo with options, await input |
| Focused tests reveal deeper architectural issues | Document as new mismatches, assess if blocking |

---

## 6. Notes

- Phase IV maintains "convergence over expansion" principle
- No new major features unless strictly required for validation
- Focus is on **proving existing capabilities work** and **making architectural decisions explicit**
- Multi-intent decomposition explicitly deferred to backlog (user-demand triggered)
