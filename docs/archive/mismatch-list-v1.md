# Main Path Mismatch List v1

> **Source**: Phase H ~ Iteration 14 synthesis
> **Version**: v1
> **Date**: 2026-04-22
> **Status**: Reviewed & Formatted

This document consolidates architecture mismatches identified through Phase H ~ Iteration 14, classified using the Mismatch Taxonomy.

---

## Summary by Category

| Category | Count | Status Distribution |
|----------|-------|---------------------|
| Control Flow Mismatch | 2 | 1 Fixed, 1 Documented |
| State Model Mismatch | 1 | Fixed |
| Module Boundary Mismatch | 2 | 1 Fixed, 1 Partial |
| Interface Contract Mismatch | 3 | 2 Fixed, 1 Documented |
| Persistence Mismatch | 0 | N/A |
| Permission Mismatch | 0 | N/A |
| Degradation Mismatch | 1 | Documented |
| Observability Mismatch | 1 | Partial |

**Total Mismatches**: 10 documented, 5 resolved, 5 require future work

---

## 1. Control Flow Mismatch (控制流失配)

### CF-001: Bridge Bypassing for Builtin Intents
- **Status**: Fixed & Verified (Phase H)
- **Impact**: Low (runtime behavior corrected, E2E verified)
- **Description**: `greet` / `query_help` / `query_status` were going through bridge path even when bridge was available, instead of using local direct-reply handler.
- **Resolution**: Local builtin handlers now bypass bridge. E2E test `test_direct_reply_path_bypasses_bridge_for_builtin_intents` locks the behavior.
- **Evidence**: `tests/unit/test_light_brain.py` test passes.

### CF-002: Old Bridge / Local Compatible Path Residual Forks
- **Status**: Documented, Partial Cleanup
- **Impact**: Medium
- **Description**: Child session creation still maintains some bridge-related compatibility branches. While Phase H unified the path, residual fork logic exists for backward compatibility.
- **Resolution Direction**: Continue compressing old bridge / local compatibility branches in favor of unified child session wrapper.
- **Evidence**: `e2e-test-results.md` H4-02 "仍需继续压缩旧 bridge / 本地兼容路径的残留分叉"
- **Priority**: P2 (cleanup, not blocking)

### CF-003: Multi-Intent Decomposition Not Supported
- **Status**: Documented Gap, Not Implemented
- **Impact**: Medium
- **Description**: `LightBrainInterpreter` currently only supports single-intent recognition. Multi-intent decomposition (IntentDecomposer + TaskScheduler) identified in Iteration 9 as missing modules.
- **Resolution Direction**: Optional enhancement - not blocking Phase II main path. May be implemented later if user scenarios demand it.
- **Evidence**: Iteration 9 "失配点 1~5" documentation
- **Priority**: P3 (optional, marked for future Phase)

---

## 2. State Model Mismatch (状态模型失配)

### SM-001: Session Key Misalignment in Clarification
- **Status**: Fixed (Phase H)
- **Impact**: High (was breaking clarification flow)
- **Description**: Session keys for pending runtime asset clarifications were misaligned between storage and retrieval.
- **Resolution**: Aligned `_pending_runtime_asset_clarifications` read/write paths.
- **Evidence**: Iteration 1 "失配点分类" - marked as resolved.

### SM-002: Runtime Asset Clarification / Follow-up Connection
- **Status**: Fixed (Iteration 2)
- **Impact**: High
- **Description**: Clarification flow for runtime assets was not properly connecting through to follow-up handling.
- **Resolution**: `_finalize_command` 5-step post-processing implemented. `peek_only` mode added to prevent premature pending consumption.
- **Evidence**: `74 passed in 25.67s`, all 5 original failures resolved.

---

## 3. Module Boundary Mismatch (模块边界失配)

### MB-001: Snapshot Persistence Mixed Runtime Objects
- **Status**: Fixed (Phase H)
- **Impact**: High
- **Description**: Session persistence was including runtime objects in snapshots, causing serialization issues.
- **Resolution**: `LightBrainMemory` now cleans snapshots to JSON-safe format. Only serializable command snapshots persisted.
- **Evidence**: `light_brain_memory.py` snapshot cleaning for parameters/context/suggested_actions.

### MB-002: Runtime Asset Intent Precedence
- **Status**: Fixed (Phase H)
- **Impact**: Medium
- **Description**: Runtime asset call intents could be swallowed by detail-like paths.
- **Resolution**: Fixed precedence so runtime asset calls have priority. Detail reads use `get_asset_detail -> get -> query_asset_info` compatible chain.
- **Evidence**: `asset_tools.py` tolerant read chain implemented.

### MB-003: Bridge Responsibility Overlap
- **Status**: Partial (Documented)
- **Impact**: Low
- **Description**: Some orchestration responsibilities still overlap between bridge and local child session wrapper.
- **Resolution Direction**: Continue migration to unified local wrapper. Bridge becomes transport-only.
- **Evidence**: H4-02 notes on "child session 状态机已开始被真实主链消费" but "仍需继续压缩旧 bridge / 本地兼容路径的残留分叉"
- **Priority**: P2

---

## 4. Interface Contract Mismatch (接口契约失配)

### IC-001: Clarification Question Generation Inconsistency
- **Status**: Fixed (Phase H)
- **Impact**: Medium
- **Description**: Clarification questions were generated inconsistently across different handlers.
- **Resolution**: Unified post-processing via `_finalize_command`. All paths now converge to consistent question generation.
- **Evidence**: Iteration 1 "clarification question 生成不一致 → 已统一后处理收口"

### IC-002: Command Parameter Schema Assumptions
- **Status**: Fixed (Phase H)
- **Impact**: Medium
- **Description**: Asset detail presentation layer assumed fixed schema, breaking with methods/interfaces variants.
- **Resolution**: Detail presentation now compatible with methods/interfaces variants.
- **Evidence**: `light_brain_gateway.py` detail display layer alignment.

### IC-003: Budget/Quota Dual Tracks
- **Status**: Documented, Not Unified
- **Impact**: Low-Medium
- **Description**: `budget_tracker.py` and governance `CostQuotaManager` exist as parallel implementations. Token/cost budget vs app operation quota are two separate guard systems without unified classification.
- **Resolution Direction**: Needs architectural decision on whether to merge or keep separated by concern (resource vs governance).
- **Evidence**: Iteration 14 "budget/quota 双轨存在，尚未完全收敛"
- **Priority**: P2 (cleanup, documented for Phase III/IV)

### IC-004: Contract Linter Path Drift
- **Status**: Documented
- **Impact**: Low
- **Description**: Design doc references `app/utils/contract_lint.py` but implementation is at `app/services/contract_linter.py`.
- **Resolution Direction**: Update design doc to match implementation path.
- **Evidence**: Iteration 14 "G1. 文档与代码路径漂移"
- **Priority**: P3 (documentation fix)

---

## 5. Persistence Mismatch (持久化失配)

### Current Status: No Active Mismatches
All previously identified persistence issues resolved:
- JSON-safe snapshot serialization implemented
- Command-only persistence (no runtime objects)
- Context upload after-hook implemented
- Child session context linking persists correctly

---

## 6. Permission Mismatch (权限失配)

### Current Status: No Active Mismatches
Governance guards (Iteration 8) fully implemented:
- `PolicyAuthorityService` integrated
- `AuditLogger` integrated for all state-changing operations
- `CostQuotaManager` integrated for resource-intensive operations
- E2E tests passing (10/10)

---

## 7. Degradation Mismatch (降级失配)

### DG-001: Legacy Execute_Action Without Last_Command
- **Status**: Fixed (Phase H)
- **Impact**: High
- **Description**: `execute_action` previously failed when `last_command` was missing from context.
- **Resolution**: `execute_action` now rebuilds directly from intent + action_params instead of requiring last_command.
- **Evidence**: `light_brain_gateway.py` reconstruction logic.

### DG-002: Missing Gateway-Level Degradation for Resource Exhaustion
- **Status**: Documented Gap
- **Impact**: Medium
- **Description**: While rate limiter and budget tracker exist, there's no documented evidence they're wired to the Phase H main message path for graceful degradation.
- **Resolution Direction**: Need to map rate limiter/budget tracker integration points to gateway and document the degradation behavior.
- **Evidence**: Iteration 14 "rate limiter / budget tracker 多数停留在'实现已有，但接入与验证证据不足'"
- **Priority**: P2 (needs focused validation)

---

## 8. Observability Mismatch (可观测性失配)

### OB-001: Context Summary Debug vs Product Format
- **Status**: Partial (Fixed but noted for improvement)
- **Impact**: Low
- **Description**: `AppPresenter._append_context_summary` shows debug-style summary. Phase H made it structured Markdown, but further productization possible.
- **Resolution Direction**: Continue productization in later Phase.
- **Evidence**: Phase H notes "目前是调试型摘要展示，后续可继续产品化为更自然的最终交互文案"
- **Priority**: P3

### OB-002: Risk Guard Observability Gaps
- **Status**: Documented Gap
- **Impact**: Medium
- **Description**: Rate limiter, tool loop guard, contract linter have implementations but lack focused validation tests and documented observability hooks.
- **Resolution Direction**: Add focused tests for block events, rejection reasons, and metric collection points.
- **Evidence**: Iteration 14 "缺少 focused validation 记录"
- **Priority**: P2

---

## Legacy Issues from Earlier Phases (Now Resolved)

### ~Interpreter Hardcoded RuntimeCenter Interface~ ✓ Fixed
- Original: Interpreter assumed specific RuntimeCenter interface
- Resolution: Changed to tolerant read chain

### ~Session Key Misalignment~ ✓ Fixed
- Original: `_pending_runtime_asset_clarifications` misaligned
- Resolution: Aligned read/write paths

### ~Snapshot Persistence with Runtime Objects~ ✓ Fixed
- Original: Runtime objects in snapshots
- Resolution: JSON-safe cleaning implemented

### ~Execute_Action Secondary Parsing~ ✓ Fixed
- Original: Required last_command for reconstruction
- Resolution: Direct reconstruction from intent + params

### ~Asset Detail Fixed Schema~ ✓ Fixed
- Original: Presentation assumed fixed schema
- Resolution: Compatible with methods/interfaces variants

---

## Active Gaps Requiring Future Work

1. **Multi-Intent Decomposition** (CF-003): Optional enhancement, not blocking
2. **Bridge Path Compression** (CF-002, MB-003): Cleanup of residual fork logic
3. **Budget/Quota Unification** (IC-003): Architectural decision needed on dual-track guards
4. **Rate Limiter Main Path Wiring** (DG-002): Evidence of gateway integration needed
5. **Risk Guard Focused Validation** (OB-002): Tests for block/reject scenarios
6. **Contract Linter Doc Path** (IC-004): Documentation alignment
7. **Context Summary Productization** (OB-001): UX polish

---

## Next Phase Entry Points

Based on this mismatch list, recommended Phase III/IV entry points:

### Immediate (P2)
- Add focused validation tests for rate limiter, tool loop guard, contract linter
- Document rate limiter/budget tracker gateway integration points
- Update `risk-guards-design.md` with actual file paths

### Short-term (Future Phase)
- Architectural decision: unify budget/quota or maintain separation
- Productize context summary presentation
- Compress remaining bridge compatibility branches

### Optional (Future Phase)
- Multi-intent decomposition implementation (if user scenarios demand)
