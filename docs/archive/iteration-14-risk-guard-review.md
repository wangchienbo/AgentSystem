# Iteration 14 - Risk Guards Inventory and Gap Review

## Goal
盘点当前 AgentSystem 已经存在的风险护栏实现、设计文档、真实接入点与缺口，形成一个统一的评审基线，避免“文档说有，主链没接”或“代码已有，但没有纳入 Phase H / v2 主路径口径”的情况。

---

## 1. Inventory Summary

### 1.1 Query / Rate Limits
**已发现实现：**
- `app/services/rate_limiter.py`
- `app/api/middleware.py`

**当前能力：**
- session 并发查询上限
- session 每分钟查询上限
- tool call per-command / per-session 上限
- API middleware 级别的 RPM 限制

**当前状态判断：**
- **部分落地**
- 具备基础实现，但未见已明确挂接到 Phase H 主消息主链的统一入口证明

**缺口：**
- 缺少“交互主路径已接入 rate limiter”的统一文档映射
- 缺少与 task list / E2E 的对应验证记录
- user-level rate limit 配置存在于 dataclass 设计，但主链落点不清晰

---

### 1.2 Tool Loop Guards
**已发现实现：**
- `app/services/tool_loop_guard.py`
- `app/services/rate_limiter.py` 中 tool call 限制

**当前能力：**
- per-command tool call limit
- rapid call window limit
- repeating pattern loop detection

**当前状态判断：**
- **能力已实现，但主链挂接证据不足**

**缺口：**
- 未看到与 `ToolCallingEngine` / gateway 主执行链的明确接线文档
- 未看到 focused test 或 E2E 回归记录
- “tool loop 上限”在 docs 已提出，但还未形成“已启用 / 未启用”结论

---

### 1.3 Budget / Quota
**已发现实现：**
- `app/services/budget_tracker.py`
- `app/system/workers/app_mgmt.py` 中 `CostQuotaManager`
- `docs/risk-guards-design.md`

**当前能力：**
- token budget per session / per user per day / per command
- governance worker 中 app create/uninstall 配额检查

**当前状态判断：**
- **双轨存在，尚未完全收敛**

**缺口：**
- `budget_tracker.py` 与治理里的 `CostQuotaManager` 口径未完全统一
- token/cost budget 与 app operation quota 是两套护栏，尚未做统一分类
- 缺少“哪些预算对 LLM 主路径生效，哪些只对治理操作生效”的正式结论

---

### 1.4 Observability
**已发现实现：**
- `app/utils/observability.py`
- `app/services/workflow_observability.py`
- `app/services/workflow_observability_helpers.py`

**当前能力：**
- command metrics 收集
- duration/tokens/tool_calls/error/blocked 统计
- workflow observability API 支持

**当前状态判断：**
- **实现存在，接入范围分层不均**

**缺口：**
- command-level observability 是否接入 gateway 主链，需要补映射
- workflow observability 与交互层 observability 仍是分层存在，缺少统一说明
- 长任务被外部 SIGTERM 打断的测试策略目前靠执行经验，没有形成制度化文档

---

### 1.5 Contract Lint
**已发现实现：**
- `app/services/contract_linter.py`
- docs 中提到 `app/utils/contract_lint.py`，与现有路径不一致

**当前能力：**
- JSON 结构校验
- tool args required/type 基础校验

**当前状态判断：**
- **已实现，但文档与代码路径存在漂移**

**缺口：**
- docs 与实际代码文件路径不一致
- 未明确接入点，无法证明已在主链阻断非法 contract
- 缺少测试矩阵映射

---

### 1.6 Clarification / Pending Context Guards
**已发现实现：**
- `app/services/continuation_service.py`
- `app/models/continuation.py`
- `app/models/chat.py` clarification 字段
- `app/services/app_create_modify_executor.py`
- `app/services/app_lifecycle_query_executor.py`

**当前能力：**
- clarification response 统一建模
- continuation state 抽象化
- create/modify/lifecycle 类路径在缺参时走 clarification

**当前状态判断：**
- **主路径已落地**

**缺口：**
- 仍处于新旧接口兼容期，文档明确写明“旧 runtime asset clarification 接口是过渡态”
- 缺少统一归类，当前被分散记录在 Phase H / Iteration 10 / Iteration 12 中

---

## 2. Gap Review

### G1. 文档与代码路径漂移
- `risk-guards-design.md` 中部分路径仍是“计划态”，与现有落地文件不一致
- 典型例子：`app/utils/contract_lint.py` vs `app/services/contract_linter.py`

### G2. 已实现不等于已接入
- rate limiter / tool loop guard / observability / contract linter 都已存在实现
- 但是否已经稳定挂接到 Phase H 主消息主链，目前证据不完整

### G3. 护栏分类口径未统一
- token budget、tool loop、query limit、quota、audit、observability 目前分散在不同模块
- 缺少统一分类：
  - 资源护栏
  - 执行护栏
  - 合同护栏
  - 审计护栏
  - 解释连续性护栏

### G4. 缺少系统级验证记录
- 除 governance 审计/配额外，多数护栏尚未形成独立 E2E 或 focused integration 记录
- 这会导致“理论存在，但运行中是否生效”难以判断

---

## 3. Proposed Closure Actions

### Action A - Iteration 14.1 文档收敛
- 更新 `docs/risk-guards-design.md`
- 把“计划态文件路径”改为当前真实实现路径
- 标注每类护栏为：已实现 / 部分实现 / 未接入 / 待验证

### Action B - Iteration 14.2 主链挂接证据补齐
- 为 rate limiter / tool loop guard / contract linter / command observability 补接入点映射
- 至少在 `system-relationship-map.md` 或独立风险护栏文档中说明入口

### Action C - Iteration 14.3 验证补齐
- 为高优先级护栏补 focused tests：
  - query limit
  - tool loop block
  - contract lint reject
  - command observability record

---

## 4. Current Conclusion
当前风险护栏状态不是“完全缺失”，而是：
- **治理护栏（审计、配额）接入度最高**
- **clarification / continuation 护栏在主链上最完整**
- **rate limit / tool loop / contract lint / observability 多数停留在“实现已有，但接入与验证证据不足”阶段**

因此，Iteration 14 的核心不应再写新一轮抽象设计，而应优先做：
1. 文档收敛
2. 主链接入证据补齐
3. focused validation
