# Phase V Planning - Implementation or Expansion

> **Status**: Planning  
> **Previous Phase**: Phase IV (Iteration 13-19) - Risk Guards Validation & Architecture Decisions  
> **Entry Document**: `docs/mismatch-list-v1.md`, `docs/adr-001-budget-quota-unification.md`  
> **Decision Point**: P1/P2 Implementation vs. New Expansion

---

## 1. Entry Context

Phase IV successfully completed risk guards inventory, validation, and architecture decisions:
- **26 focused tests** validating all risk guard components
- **ADR-001** documenting Budget/Quota unification decision (Layered Architecture)
- **Mismatch List v1** with 5 resolved, 5 active gaps
- **Documentation alignment** across 8 risk guard categories

### Active Gaps from Phase IV

| ID | Gap | Priority | Current State |
|----|-----|----------|---------------|
| DG-002 | Rate Limiter / Tool Loop Guard not invoked in main path | P1 | Implemented, not wired |
| IC-003 | Budget/Quota dual tracks | P2 | ADR-001 decision made, not implemented |
| IC-004 | Contract Linter not wired | P1 | Implemented, not wired |
| OB-002 | Risk guard block events not observable | P1 | Collector exists, events not fired |
| OB-001 | Context summary productization | P3 | Debug-style, needs UX polish |

---

## 2. Phase V Options

### Option A: Complete P1/P2 Implementation (Risk Guards Closure)

**Goal**: Finish what Phase IV validated and documented - actually wire the risk guards into the main message path.

#### A1. Rate Limiter Main Path Integration
- **Work**: Add `is_session_allowed()` check at `receive_message()` entry
- **Work**: Add `record_query()` tracking after processing
- **Work**: Add concurrent query tracking around async operations
- **Files**: `app/system/gateway/light_brain_gateway.py`
- **Tests**: Update `test_iteration16_risk_guard_integration.py` to verify blocking

#### A2. Tool Loop Guard Main Path Integration  
- **Work**: Add `check_allowed()` / `record_call()` to `ToolCallingEngine`
- **Work**: Add `reset_command()` at command start
- **Files**: `app/services/tool_calling_engine.py` or `app/services/tool_call_executor.py`
- **Tests**: Verify loop detection triggers and blocks

#### A3. Contract Linter Tool Path Integration
- **Work**: Add `validate_tool_args()` before tool execution
- **Work**: Add `validate_json_structure()` for LLM outputs
- **Files**: `app/services/tool_calling_engine.py`

#### A4. Risk Guard Observability Events
- **Work**: Connect `_rate_limiter`, `_tool_loop_guard` to `_observability` collector
- **Work**: Fire events: `rate_limiter.blocked`, `tool_loop.limit_exceeded`
- **Files**: All risk guard services + `app/utils/observability.py`

#### A5. Budget/Quota Architecture Implementation (ADR-001 Phase 1-2)
- **Phase 1**: Define `ResourceBudgetManager` interface
- **Phase 2**: Rename `BudgetTracker` → `ResourceBudgetManager`, update governance dependency
- **Files**: `app/services/budget_tracker.py`, `app/system/workers/app_mgmt.py`

**Estimated Effort**: 4-6 iterations  
**Outcome**: Risk guards fully operational, not just documented  
**Risk**: May delay other feature work

---

### Option B: Governance Expansion

**Goal**: Extend governance capabilities beyond basic audit/quota.

#### B1. Advanced Permission System
- Role-based access control (RBAC) beyond admin/root
- Resource-level permissions (app ownership, skill execution)
- Permission inheritance and delegation

#### B2. Compliance & Audit Enhancement
- Structured audit log export (JSONL, CSV)
- Audit log querying and filtering API
- Compliance report generation

#### B3. Multi-tenant Isolation
- Namespace/app registry isolation per tenant
- Cross-tenant permission boundaries
- Resource quotas per tenant

**Estimated Effort**: 6-8 iterations  
**Outcome**: Enterprise-ready governance  
**Risk**: P1 gaps remain unfixed

---

### Option C: Performance & Scalability

**Goal**: Optimize for higher throughput, lower latency.

#### C1. Async Architecture Optimization
- Reduce blocking operations in gateway
- Connection pooling for LLM clients
- Parallel tool execution where safe

#### C2. Caching Layer
- LLM response caching for identical queries
- Tool result caching for deterministic tools
- Session state caching to reduce persistence load

#### C3. Memory Management
- Session lifecycle optimization (early cleanup)
- Large payload streaming (avoid loading full context)
- Memory leak detection and prevention

**Estimated Effort**: 4-6 iterations  
**Outcome**: Better performance under load  
**Risk**: P1 gaps remain unfixed

---

### Option D: New Capability Development

**Goal**: Add major new functionality.

#### D1. Multi-Intent Decomposition (from Iteration 9 backlog)
- Implement `IntentDecomposer` and `TaskScheduler`
- Enable "create app and start it" in single message
- Parallel execution of independent sub-tasks

#### D2. Advanced App Features
- App-to-app communication/interop
- Event-driven app triggers (webhooks, schedules)
- App marketplace / discovery

#### D3. Enhanced Developer Experience
- App debugging tools (step-through, inspection)
- App performance profiling
- Hot-reload for app development

**Estimated Effort**: 8+ iterations  
**Outcome**: Major feature expansion  
**Risk**: Technical debt accumulates (P1 gaps)

---

## 3. Recommendation

**Primary Recommendation: Option A + selective B1**

**Rationale**:
1. **Close the loop**: Phase IV documented gaps, Phase V should close them
2. **Foundation first**: Risk guards are foundational safety - better to finish before expanding
3. **Efficient**: P1 gaps are 60-80% done (implemented, just not wired)
4. **Reduced risk**: Wiring existing code is lower risk than new features

**Hybrid Approach**:
- Iterations 20-23: P1 implementation (A1-A4)
- Iteration 24: P2 Phase 1 (ADR-001 interface definition)
- Iteration 25-26: Governance B1 (RBAC) - foundation for future expansion

---

## 4. Exit Criteria

### If Option A selected:
- [ ] Rate Limiter actively blocks excessive queries in production
- [ ] Tool Loop Guard detects and blocks infinite loops
- [ ] Contract Linter validates tool args before execution
- [ ] All block events observable in metrics/logs
- [ ] ADR-001 Phase 1-2 complete (interface + rename)
- [ ] Mismatch List v2 with P1 gaps resolved

### If Option B/C/D selected:
- [ ] Explicit decision document accepting P1 gaps remain
- [ ] P1 gaps added to technical debt backlog with priority
- [ ] Phase V scope and iterations defined
- [ ] Success criteria for chosen option documented

---

## 5. Decision Required

**Choose one**:

1. **Implement P1/P2** (Option A) - Finish risk guards wiring
2. **Governance Expansion** (Option B) - Extend governance capabilities
3. **Performance** (Option C) - Optimize for scale
4. **New Capabilities** (Option D) - Add major features
5. **Hybrid** (A + B1) - Close critical gaps, then extend governance

**Default**: Option A (Hybrid) if no explicit choice provided - prioritizes completing foundational work before expansion.

---

## 6. Proposed Task List Update

If Option A (Hybrid) selected:

```markdown
### Iteration 20 - Rate Limiter Main Path Integration
- Wire `is_session_allowed()` to `receive_message()` entry
- Wire `record_query()` to post-processing
- Wire concurrent tracking around async operations
- Update tests to verify actual blocking behavior

### Iteration 21 - Tool Loop Guard Main Path Integration  
- Wire `check_allowed()` / `record_call()` to tool execution
- Wire `reset_command()` to command start
- Update tests to verify loop detection

### Iteration 22 - Contract Linter Integration
- Wire `validate_tool_args()` before tool calls
- Wire validation for LLM structured outputs
- Document integration points

### Iteration 23 - Risk Guard Observability Events
- Connect all guards to observability collector
- Implement block event firing
- Verify events in metrics export

### Iteration 24 - ADR-001 Phase 1 (Interface Definition)
- Define `ResourceBudgetManager` interface
- Document integration between layers
- Update governance dependency design

### Iteration 25-26 - RBAC Governance Extension
- Extend permission system beyond admin/root
- Resource-level permissions
- Permission inheritance
```

---

## 7. Related Documents

- `docs/mismatch-list-v1.md` - Active gaps (DG-002, IC-003, IC-004, OB-002)
- `docs/adr-001-budget-quota-unification.md` - Architecture decision
- `tests/focused/test_iteration16_risk_guard_integration.py` - Validation tests
- `tests/focused/test_iteration17_contract_budget_validation.py` - Validation tests
