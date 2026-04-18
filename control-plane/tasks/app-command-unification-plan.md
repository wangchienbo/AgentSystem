# AgentSystem 主链路统一重构方案（草案 v1）

## Why switch strategy now
系统尚未上线，因此当前不需要为了兼容历史路径而持续背负过重的过渡层。
在这个阶段，更合理的方向不是继续围绕 gateway / worker / orchestrator / legacy fallback 做小修小补，
而是直接推进主链路统一，把 create_app / modify_app / lifecycle / query 这批核心操作收敛到更清晰的结构上。

## Strategic shift
从“在现有多路径上做保守修补”切换为“在未上线窗口完成结构性收敛”。

目标：
- 不再默认保留历史不可达路径
- 不再为旧兼容入口持续加补丁
- 用一次较大的结构性改造，建立清晰主路径
- 之后再在新主路径上做真实场景验证和持续迭代

---

## Current structural problem
当前 create_app / modify_app 暴露出的根问题不是单点 bug，而是：

- gateway 层承担过多交互、确认、权限、降级和部分控制流分发职责
- worker/orchestrator/service 多层链路叠加，但缺少统一 contract
- legacy path、RPC path、fallback path 曾长期并存
- active skill / session / runtime / persistence 目标不统一
- create 与 modify 在权限和确认协议上曾经逐步漂移

这说明应该从“统一主控制流”入手，而不是继续在边缘点逐个补丁。

---

## Target architecture direction

### 1. 建立统一的 AppCommand 主路径
把 create / modify / start / stop / pause / resume / query / list / delete 统一纳入一套更清晰的应用命令主路径。

建议收敛成：
- gateway：只负责用户交互、会话状态、多轮澄清、确认卡片、回复包装
- command application layer：负责命令级 contract、权限门控、降级策略、调用具体 domain service
- domain orchestrators/services：负责 create/modify/lifecycle/query 的真实业务执行
- runtime/persistence/catalog：负责状态落盘、运行态与展示态一致性

也就是让 gateway 不再直接知道过多细节，让“命令应用层”成为真正的中间主控面。

### 2. create_app / modify_app contract 统一
应统一：
- request model
- confirm payload model
- success / error / requires_clarification / requires_confirmation response model
- permission check contract
- fallback / degrade contract

### 3. 权限策略独立成统一 policy
不再复用 `_check_app_modify_permission()` 去控制 create 等其他动作。
应抽出统一的 AppOperationPolicy，例如：
- can_create_app
- can_modify_app
- can_delete_app
- can_create_skill_for_app
- can_modify_foreign_app

### 4. 降级策略显式化
create / modify / lifecycle 都需要统一定义：
- bus unavailable
- worker unavailable
- orchestrator unavailable
- service unavailable
- persistence unavailable
各自怎么退，返回什么用户语义。

### 5. active skill / 多轮状态与 persistence 对齐
active skill 不能永远停在进程内 dict。
需要明确：
- 哪些状态必须持久化
- 哪些状态可丢失
- 重启后多轮交互要不要恢复、恢复到什么粒度

---

## Refactor phases

### Phase R1 — command layer unification
- [ ] 引入统一 AppCommand / AppCommandResult contract
- [ ] 引入统一 AppCommandRouter / AppCommandService
- [ ] 让 gateway 不再直接分散处理 create/modify/start/stop/query 的业务分支
- [ ] 把 confirmed payload 和 command rebuild 统一交给 command layer

### Phase R2 — create/modify consolidation
- [ ] 抽出 CreateAppService / ModifyAppService 的统一调用入口
- [ ] 统一 create_app / modify_app 的 permission gate
- [ ] 统一 create_app / modify_app 的 degrade path
- [ ] 删除已被主路径替代的 legacy create/modify 分支

### Phase R3 — lifecycle/query consolidation
- [ ] 统一 list/query/start/stop/pause/resume 的调用入口
- [ ] 对齐 AppCatalog / RuntimeCenter / lifecycle 的状态语义
- [ ] 统一 query/list 的返回模型

### Phase R4 — session and persistence alignment
- [ ] 设计 active skill 持久化模型
- [ ] 对齐 session / command / action replay
- [ ] 明确重启恢复边界

### Phase R5 — real scenario validation
- [ ] 回到最小闭环真实场景集验证新主路径
- [ ] 用真实失败结果继续下一轮开发任务

---

## Immediate implementation direction
既然当前允许大改，下一步不应该继续零散补丁，而应该直接开始：

1. 抽一层统一的 AppCommand contract
2. 先把 create_app / modify_app 放进统一 command layer
3. 再从 gateway 中挪走零散的 confirmed / permission / degrade 分支

## Important note
这意味着后续会有更多结构性改动，但这是在“未上线窗口”里最值得做的事情。
现在承受一次较大的结构性调整，成本远低于上线后再带着历史漂移继续修。
