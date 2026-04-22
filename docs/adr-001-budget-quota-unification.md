# Architecture Decision Record (ADR-001): Budget/Quota System Unification

> **Status**: ✅ **IMPLEMENTED**  
> **Date**: 2026-04-22  
> **Implementation Date**: 2026-04-22 (Phase V, Iterations 24-26)  
> **Context**: Iteration 18 - Phase IV  
> **Related Mismatch**: IC-003 (✅ Resolved)

---

## Implementation Status

**Phase 1** (Interface definition): ✅ Complete  
**Phase 2** (Governance layer update): ✅ Complete  
**Phase 3** (LLM/Tool path integration): ✅ Complete  

**Files**:
- `app/services/resource_budget_manager.py` - Resource layer interface
- `app/services/budget_tracker.py` - Token budget tracking
- `app/system/workers/app_mgmt.py` - Governance layer integration

**Integration Points**:
- ToolCallExecutor: Budget check before tool execution
- LightBrainGateway: Budget check before LLM calls
- CostQuotaManager: Governance policy enforcement

---

## 1. Context & Problem Statement

### Current State (Dual Tracks)
AgentSystem currently has two parallel budget/quota tracking systems:

**Track 1: Resource Budget (app/services/budget_tracker.py)**
- Tracks token consumption per session/user/command
- Enforces limits on LLM API costs
- Data structures: `BudgetConfig`, `BudgetTracker`, `BudgetState`
- Methods: `consume_tokens()`, `get_session_usage()`, `get_user_daily_usage()`

**Track 2: Governance Quota (app/system/workers/app_mgmt.py via CostQuotaManager)**
- Tracks operation-level quotas (app creation, deletion)
- Enforces business-level governance rules
- Integrated with `AuditLogger`, `PolicyAuthorityService`
- Used for resource-intensive operations (create_app, uninstall_app)

### Problem
- Two systems with overlapping concerns but no unified interface
- Risk of inconsistent enforcement
- Observability fragmented across two implementations
- Developer confusion about which system to use for new features

---

## 2. Decision Options

### Option A: Merge into Unified Quota System
**Approach**: Consolidate into single `QuotaManager` service

**Pros**:
- Single source of truth for all quota/budget concerns
- Simpler mental model for developers
- Unified observability and reporting
- Easier to add new quota types

**Cons**:
- Breaking change to existing governance integration
- Risk of mixing concerns (resource vs business logic)
- May require significant refactoring

**Implementation**:
```python
class UnifiedQuotaManager:
    def check_and_consume(
        self,
        user_id: str,
        session_id: str,
        quota_type: QuotaType,  # TOKEN, OPERATION, COMPUTE
        amount: int,
        context: dict | None = None,
    ) -> tuple[bool, str | None]:
        ...
```

---

### Option B: Keep Separated by Concern
**Approach**: Maintain two systems with clear boundaries

**Pros**:
- Clear separation: resource budget vs governance quota
- No breaking changes to existing code
- Each system optimized for its specific use case
- Governance track already proven with audit integration

**Cons**:
- Two systems to maintain
- Potential inconsistency in enforcement patterns
- Developer must choose correctly

**Refinement**: Add naming clarity
- `TokenBudgetTracker` (resource focus)
- `GovernanceQuotaManager` (business rules focus)

---

### Option C: Layered Architecture (Recommended)
**Approach**: Budget tracker as foundation, quota as policy layer

**Design**:
```
┌─────────────────────────────────────────┐
│  Governance Layer                      │
│  - Policy rules                          │
│  - Operation quotas (CostQuotaManager)   │
│  - Business-level enforcement            │
├─────────────────────────────────────────┤
│  Resource Layer                        │
│  - Token budgets (BudgetTracker)         │
│  - Compute budgets (future)             │
│  - Low-level resource tracking          │
├─────────────────────────────────────────┤
│  Observability Layer                   │
│  - Unified event logging                │
│  - Cross-layer metrics                  │
└─────────────────────────────────────────┘
```

**Pros**:
- Clean separation of concerns
- Resource layer can be shared across multiple policy domains
- Governance can compose multiple resource types
- Observability unified at bottom layer

**Cons**:
- Slightly more complex architecture
- Requires clear interface definition between layers

**Implementation Plan**:
1. Rename for clarity: `BudgetTracker` → `ResourceBudgetManager`
2. Define `ResourceBudgetManager` interface for governance layer
3. Update `CostQuotaManager` to consume resource metrics from `ResourceBudgetManager`
4. Add unified observability hooks
5. Document usage patterns in dev guide

---

## 3. Decision

**Selected**: Option C - Layered Architecture

**Rationale**:
1. **Separation of concerns**: Resource tracking (token costs) is fundamentally different from business policy (operation permissions)
2. **Proven patterns**: Track 2 (governance) already demonstrates that policy layers work well
3. **Flexibility**: Future resource types (storage, compute) can be added without changing governance logic
4. **Observability**: Single observability layer can collect from both
5. **Migration path**: Can be implemented incrementally without breaking existing functionality

---

## 4. Implementation Roadmap

### Phase 1: Interface Definition (Iteration 18.x)
- [ ] Define `ResourceBudgetManager` interface
- [ ] Document `CostQuotaManager` → `ResourceBudgetManager` dependency
- [ ] Create unified observability events

### Phase 2: Refactoring (Iteration 19+)
- [ ] Rename `BudgetTracker` → `ResourceBudgetManager`
- [ ] Update `BudgetConfig` → `ResourceBudgetConfig`
- [ ] Add `ResourceBudgetManager` injection to governance layer
- [ ] Remove duplicate token tracking in governance

### Phase 3: Integration (Future Iteration)
- [ ] Wire resource budget to LLM calls
- [ ] Wire resource budget to tool execution
- [ ] Unified quota dashboard

---

## 5. Migration Compatibility

### Backward Compatibility
- Keep `BudgetTracker` as alias/deprecated during transition
- Governance quota API remains unchanged
- Existing tests continue to work

### Breaking Changes
None planned for Phase 1-2. Phase 3 may introduce:
- New required dependencies in constructors
- Additional observability events (additive only)

---

## 6. Consequences

### Positive
- Clear architectural boundaries
- Unified observability for both tracks
- Extensible for future resource types
- Governance policy can leverage resource data

### Negative
- More components to understand (but well-documented)
- Slightly more wiring required

### Neutral
- Two files remain (but with clear roles)

---

## 7. Related Documents

- `docs/mismatch-list-v1.md` - IC-003 entry
- `app/services/budget_tracker.py` - Track 1 implementation
- `app/system/workers/app_mgmt.py` - Track 2 (CostQuotaManager)
- `tests/focused/test_iteration17_contract_budget_validation.py` - Validation tests

---

## 8. Decision Status

- [x] Options documented
- [x] Recommendation provided
- [ ] Stakeholder review (if required)
- [ ] Implementation scheduled
