# Partial-Scenario Problem Grouping and Solution Plan (2026-05-03)

## Purpose
This document groups the 29 partial-closure scenarios from the 50-scenario interaction review, then proposes a concrete solution plan.

## Source basis
- `docs/50-scenario-interaction-review-2026-05-03.md`
- `docs/interaction-record-problem-analysis-2026-05-03.md`
- `docs/user-123-full-interaction-2026-05-03.md`
- `docs/e2e-user-interaction-records-2026-05-03.md`

## High-level split
From the 50-scenario interaction review:
- matched: **19**
- partial: **29**
- failed: **2**

This document focuses on the **29 partial** scenarios.

## Grouping result

## Group A. Over-clarification / no draft-first execution
### Count
**23 scenarios**

### Typical symptom
The system understands the request but keeps asking for more context, more identifiers, or more confirmation instead of taking a minimal executable action.

### Representative scenarios
- S03 首次体验-需求模糊
- S11 多App协同
- S12 App批量操作
- S13 App配置管理
- S14 App权限管理
- S18 多轮-纠错与修正
- S21 多轮-指令冲突处理
- S22 多轮-模糊需求澄清
- S23 多轮-长对话记忆
- S24 多轮-指令链执行
- S25 多轮-异常恢复
- S26 权限-用户隔离
- S29 权限-Token与限流
- S30 权限-数据加密
- S31 错误-无效输入
- S36 Skill-安装与使用
- S40 Skill-推荐与发现
- S41 系统-状态监控
- S42 系统-配置管理
- S44 系统-用户管理
- S45 系统-日志分析
- S48 交叉-混合指令类型
- S50 交叉-全流程端到端

### Common response pattern
- “无法确认，因为缺少……”
- “请提供具体名称 / 路径 / 标识……”
- “当前上下文中未执行过……”
- “我可以指导你如何做……”

### Root cause hypothesis
1. The assistant does not have a strong **draft-first execution policy**.
2. Missing fields are treated as hard blockers instead of soft defaults.
3. The system prefers safe explanation over bounded forward action.

### What should happen instead
- infer a default object when confidence is high enough
- create a draft asset / task / app / action plan
- execute the smallest non-destructive next step
- then ask for refinement

## Group B. Lifecycle state not truthful / state machine drift
### Count
**4 scenarios**

### Representative scenarios
- S06 App创建-完整流程
- S07 App修改-功能扩展
- S08 App删除与重建
- S27 权限-角色管理

### Typical symptom
The conversation appears to have progressed through create / rename / start / stop / delete semantics, but the final response reveals the target app was never truly created, started, or made uniquely addressable.

### Common response pattern
- “从未成功启动过该应用”
- “当前未找到正在运行的实例”
- “系统中不存在名为 … 的已安装应用”
- “目标不唯一，无法直接操作”

### Root cause hypothesis
1. The conversational workflow claims lifecycle progress before persistence/runtime truth is established.
2. Naming and addressing are too weak, so later lifecycle operations lose their target.
3. The user-visible state machine is not aligned with the underlying registry/runtime truth.

### What should happen instead
- create operations must return a stable handle
- rename operations must update the canonical target reference
- start/stop/delete must operate on stable IDs, not only fragile natural-language names
- status confirmations should read from the actual runtime/persistence truth layer

## Group C. Action not executed despite explicit terminal command
### Count
**2 scenarios**

### Representative scenarios
- S33 错误-资源不足
- S39 Skill-性能调优

### Typical symptom
The final user command is an explicit operational command (“停止图片处理App”, “停止图像处理App”), but the assistant still replies with inability to identify the target rather than using the conversation-established object.

### Root cause hypothesis
1. Target grounding across turns is weak.
2. The assistant does not bind “the app we have been discussing” strongly enough to a stable runtime object.
3. Terminal operational commands are still routed through generic clarification behavior.

### What should happen instead
- use last-active target inference
- bind ongoing subject references to canonical IDs
- favor execution over re-asking when the active target is obvious from context

## Cross-cutting issue beneath all groups
### Over-scaffolded response policy
Even when the correct action is simple, replies often begin with heavy framing like:
- “当前结论建议做轻量验证……”
- extended conclusion scaffolding
- multiple layers of explanatory caution

This increases user-visible friction and hides the difference between:
- action completed
- action not completed
- action impossible
- action needs refinement

## Solution plan

## P0. Fix execution policy before response style
### P0.1 Add draft-first execution policy
For partially specified requests, if intent confidence is high:
- create a draft object
- assign a default name/template/type
- persist a pending task state
- reply with what was already done plus what still needs confirmation

### P0.2 Add pending-task recovery
Persist by `user_id` / session family:
- intent class
- target entity draft
- collected parameters
- missing parameters
- next executable step

When the user says:
- 继续
- 开始执行
- 按刚才那个继续

The system should resume, not restart clarification.

### P0.3 Separate response success from goal closure success
Extend E2E evaluation to record:
- transport success
- response success
- execution success
- goal closure success

Without this, green runs will keep overstating product readiness.

## P1. Fix lifecycle truthfulness
### P1.1 Use stable target IDs through the whole lifecycle
For create/rename/start/stop/delete:
- generate canonical target IDs
- persist alias mapping
- update references after rename
- execute by ID, not only by free text

### P1.2 Truthful confirmation rules
Never claim stop/delete/status success from conversational assumption. Only confirm from:
- persistence state
- runtime registry
- structured operation result

### P1.3 Add lifecycle regression assertions
For lifecycle-heavy scenarios, assert that final reply matches actual registry/runtime truth.

## P1.4 Add active-target inference
For explicit follow-up commands like:
- 停止它
- 删除这个
- 就按刚才那个继续

Use the most recent active target when ambiguity is low.

## P2. Fix query fast-paths and response style
### P2.1 Fast-path deterministic queries
Questions like:
- 有多少次请求记录？
- 当前有哪些 App？
- 系统健康吗？

should hit a lightweight read model first, not a heavy orchestration chain.

### P2.2 Reduce scaffold-heavy wording
For operational scenarios, prefer:
- action result
- current state
- next required input

over large explanatory wrappers.

## Suggested implementation modules
Likely touch points:
- gateway / interaction orchestrator
- session router / context resume path
- app management / runtime center / asset center
- pending task store or app context store
- response policy layer
- E2E scoring / evaluation logic

## Proposed delivery sequence
### Phase 1
- pending-task persistence
- continue/execute resume behavior
- draft-first creation

### Phase 2
- stable target IDs and alias grounding
- truthful lifecycle confirmations
- active-target inference

### Phase 3
- read fast-path for operational queries
- response-style simplification
- stronger E2E goal-closure scoring

## Expected outcome after fixes
If the above plan lands correctly:
- most of the 23 Group-A scenarios should move from partial to matched
- the 4 Group-B lifecycle scenarios should become truthfully closable
- the 2 Group-C command-finalization scenarios should execute without re-asking
- the system’s user-visible behavior will shift from “smart but hesitant” to “bounded and closing”

## Final recommendation
The next artifact after this document should be a direct engineering tasklist tied to concrete modules and tests. The analysis is already sufficient. The bottleneck is no longer diagnosis; it is implementation discipline.
