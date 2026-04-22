# AgentSystem Phase H 正式执行设计

> 本文档是 AgentSystem 在“复杂系统适配与迭代执行”主框架下，对 **Phase H 资产化运行态** 的正式设计说明。  
> 它不是普通 backlog，也不是松散的技术备忘，而是用于约束后续实现方向、任务拆解顺序与验证节奏的正式执行设计。  
> 对应顶层目标文件：`control-plane/tasks/complex-system-adaptation-task-list.md`

---

## 1. 文档定位

Phase H 的作用，不是单独长出一套新的平行路线，而是为顶层“真实场景驱动的复杂系统适配框架”提供一层稳定的运行态底座。

它要解决的问题很明确：
- 系统当前有哪些可操作对象
- 这些对象如何被统一描述
- 它们当前是否活着、状态是什么、能力是什么
- 用户交互链路如何基于统一资产语义完成发现、调用、状态变更与解释性返回
- 后续治理、审计、降级如何挂在稳定资产契约上，而不是继续堆 patch

因此，Phase H 的正式交付物不应只是代码，更包括：
1. 正式设计约束
2. 稳定边界说明
3. 最小公共契约
4. 状态机与主链路编排
5. 可执行 task list
6. 配套验证记录机制

---

## 2. 总体控制原则

这次不能再按“模块想到哪做哪”推进，而必须固定成三层结构。

### 2.1 顶层目标层
文件：`control-plane/tasks/complex-system-adaptation-task-list.md`

职责：
- 定义什么叫“比较好用”
- 定义每轮真实场景
- 定义失配分类
- 决定本轮到底验证哪条主链路

约束：
- 不承接具体实现细节
- 不直接变成技术 backlog
- 不替代阶段级设计说明

### 2.2 技术实现层
文件：`tasklist_phase_h.md`

职责：
- 只承接当前阶段为支撑主链路必须落地的技术任务
- 不能脱离顶层场景自己长出一套平行 roadmap
- 每个技术任务都必须能回答“它支撑哪个真实场景”

约束：
- 只做当前阶段必要内容
- 不把验证记录、运行结论、临时排障笔记混写进去

### 2.3 运行验证层
文件：`docs/e2e-test-results.md`

职责：
- 记录真实链路验证
- 记录失配点
- 记录修复结果
- 记录是否进入下一轮

约束：
- 不替代设计文档
- 不替代技术 task list
- 不在这里发散新架构路线

### 2.4 三层不能混
这是 Phase H 的总控约束：
- 顶层目标层定义方向
- 技术实现层承接阶段任务
- 运行验证层沉淀真实结果

三层一旦混写，后果通常就是：
- 目标和实现纠缠
- backlog 变成口号堆积
- 验证记录失去结构
- 后续迭代无法判断到底是设计问题、实现问题还是验证问题

---

## 3. Phase H 的正式目标

Phase H 的正式目标不是做一个抽象资产系统，而是让 AgentSystem 建立一条稳定、可验证、可解释的运行态主链路：

`HTTP/UI -> Login/Auth -> LightBrainGateway -> ToolCallingEngine / Orchestrator -> RuntimeCenter -> Asset`

这条链路必须满足：
- 用户只在交互层交互
- Gateway 负责组织，不自己持有完整运行态真相
- RuntimeCenter 是运行态发现真相源
- ToolCallingEngine 通过资产发现工具认识系统当前能力
- 资产调用必须挂在稳定 capability 和状态语义上

### 3.1 不允许出现的偏航形式
不能出现：
- 用户直接访问 RuntimeCenter
- 用户直接访问 ConfigCenter
- 前端绕过 Gateway 直接调用资产
- ToolCallingEngine 自己拼资产目录
- Gateway 持有一套与 RuntimeCenter 并行的资产真相
- 治理逻辑先于资产契约落地

---

## 4. 边界定义

### 4.1 ConfigCenter 的边界
定位：**固定配置入口，不是运行态真相源**。

只负责：
- 系统第一次知道配置从哪来
- 默认模型 / 默认路由 / 默认资产入口
- 固定资产或静态配置的声明

不负责：
- 运行中有哪些资产活着
- 某个 App 当前状态
- 某个 Skill 当前是否已安装
- 某个用户当前会话是否存在

正式结论：
**ConfigCenter 是 bootstrap source，不是 runtime source of truth。**

### 4.2 RuntimeCenter 的边界
定位：**运行态资产中心，是运行态发现的真相源**。

负责：
- 资产注册
- 资产状态
- 资产心跳
- 资产能力发现
- 运行态可调用入口

不负责：
- 固定配置规则
- 长篇业务逻辑编排
- LLM 模型选择策略本身
- 用户交互解释性回复

正式结论：
**所有“现在系统里有什么、能不能调用、状态是什么”都应该从 RuntimeCenter 看。**

### 4.3 LightBrainGateway 的边界
定位：**唯一用户交互入口**。

负责：
- 接收用户消息
- 绑定用户身份 / session
- 组织 LLM、Tool Call、资产调用
- 返回解释性回复

不负责：
- 自己保存完整运行态真相
- 自己维护资产目录
- 绕过 RuntimeCenter 直接硬编码调用所有服务

正式结论：
**用户只跟 Gateway 交互，Gateway 再去发现和调用资产。**

### 4.4 ToolCallingEngine 的边界
定位：**LLM 的动作执行层，不是资产目录本身**。

负责：
- 暴露 tool schema 给 LLM
- 执行被选中的 tool
- 把 tool 结果回流给 LLM

不负责：
- 自己持有资产清单
- 自己决定系统里有哪些资产
- 绕开 RuntimeCenter 直接拼凑资产信息

正式结论：
**ToolCallingEngine 看见资产，必须通过 RuntimeCenter / Asset tools。**

---

## 5. 核心执行原则固化

### 5.1 用户只在交互层交互
因此主链路必须是：

`HTTP/UI -> Login/Auth -> LightBrainGateway -> ToolCallingEngine / Orchestrator -> RuntimeCenter -> Asset`

不能出现：
- 用户直接打 RuntimeCenter
- 用户直接打 ConfigCenter
- 前端绕过 Gateway 直调资产

### 5.2 安装以后启动注册
因此 App / Skill / Session 这类运行态对象，必须经历：

`create/install -> start/materialize -> register -> heartbeat -> discoverable`

不能出现：
- 只创建不注册
- 已启动但 RuntimeCenter 不知道
- Tool Call 能调用但资产中心查不到
- ConfigCenter 里有配置但运行态根本没起来

### 5.3 固定配置只负责第一次找到入口
因此 ConfigCenter 只能回答：
- 默认模型是什么
- 固定入口是什么
- 初始静态声明是什么

不能回答：
- 这个 App 现在在不在
- 这个 Skill 是否已 materialize
- 这个 session 当前是否有效

### 5.4 LLM 先发现资产，再调用资产
因此 Tool Call 层必须拆两步：

第一步：
- `list_assets`
- `query_asset_info`

第二步：
- `call_asset_method`

不能让 LLM 直接盲调某个动作，而不知道资产能力边界与状态前提。

---

## 6. 最小公共契约

这是 Phase H 的第一落点，也是后续所有能力的挂载底座。

### 6.1 AssetDescriptor
用于描述资产是谁。

建议最小字段：
- `asset_id`
- `asset_type`
- `version`
- `owner_type`
- `owner_id`
- `source_of_truth`
- `status`
- `capabilities`
- `invoke_contract`
- `health_contract`
- `created_at`
- `updated_at`
- `tags`

正式要求：
- `asset_id` 必须稳定且全局唯一
- `asset_type` 必须可区分核心服务、App、Skill、Session 等类别
- `source_of_truth` 必须明确来自配置、注册表或运行时生成

### 6.2 AssetCapability
用于描述资产能做什么。

建议最小字段：
- `name`
- `description`
- `method`
- `input_schema_ref`
- `output_schema_ref`
- `side_effect_level`
- `requires_runtime_alive`
- `permission_hint`

正式要求：
- capability 不能只是自由文本
- 至少要有稳定方法标识
- 必须能成为后续权限、审计、验证的挂点

### 6.3 AssetState
用于描述资产当前处于什么状态。

建议最小状态集：
- `declared`
- `installing`
- `starting`
- `active`
- `degraded`
- `stopped`
- `removed`

异常扩展：
- `crashed`
- `paused`
- `unknown`

正式要求：
- 状态集足够小
- 状态要能支持安装、启动、发现、停止、恢复与异常定位
- 状态语义必须能直接被生命周期、治理和验证复用

### 6.4 资产分类模型
至少分四类：
- `fixed_asset`
- `core_runtime_asset`
- `materialized_asset`
- `session_asset`

正式要求：
- 固定配置资产与运行时实例资产不能混掉
- session 语义不能提前污染核心契约

### 6.5 生命周期状态机
统一最小状态迁移：

`declared -> installing -> starting -> active -> degraded -> stopped -> removed`

异常分支允许：
- `starting -> crashed`
- `active -> crashed`
- `degraded -> crashed`

恢复分支允许：
- `stopped -> starting`
- `degraded -> active`

正式约束：
- 不允许跳过安装/启动阶段直接进入 active
- 已启动但 RuntimeCenter 不知道，视为链路不完整
- `crashed` 不等于 `stopped`
- ConfigCenter 有配置但运行态没起来，不构成可发现资产

---

## 7. 分阶段执行编排

### Phase 0，先建不会偏的骨架
目标：
先把资产模型、注册模型、发现模型钉死，不先急着做复杂功能。

#### 0.1 资产元数据契约
产物：
- `AssetDescriptor`
- `AssetCapability`
- `AssetState`

#### 0.2 资产分类模型
产物：
- fixed asset
- core runtime asset
- materialized asset
- session asset

#### 0.3 注册状态机
产物：
- `declared -> installing -> starting -> active -> degraded -> stopped -> removed`

### Phase 1，核心服务先资产化
目标：
先让系统能“看见自己”。

先注册：
- `master_control`
- `config_center`
- `runtime_center`
- `model_router`
- `tool_calling_engine`
- `light_brain_gateway`

顺序约束：
1. 先定义元数据
2. 再注册核心资产
3. 再做发现工具

### Phase 2，发现工具落地
目标：
让 LLM 和 Gateway 不再失明。

先做三个 tool：
- `list_assets`
- `query_asset_info`
- `call_asset_method`

其中 `call_asset_method` 不是任意 Python method 直调，必须经过安全映射层。

### Phase 3，App / Skill / Session 运行态闭环
目标：
让“安装后启动注册”真正成立。

#### 3.1 App 链路
- create app spec
- install app
- materialize runtime instance
- register runtime asset
- start
- heartbeat
- discoverable

#### 3.2 Skill 链路
- install skill package
- validate manifest
- register to skill control
- materialize callable/runtime form
- register skill asset
- expose capabilities

#### 3.3 Session 链路
- user login
- create session
- session asset register
- session memory attach
- session close / expire

### Phase 4，用户主链路验证
优先只选三个场景：

#### 场景 A1
“我有哪些资产 / 你现在能操作什么”

验证：
- Gateway 是否先查资产
- LLM 是否先 list/query 再回答

#### 场景 B1
“帮我创建一个简单 App”

验证：
- create/install/register/start 是否闭环

#### 场景 D1
“启动我的监控应用”

验证：
- `list_assets -> query_asset_info -> call_asset_method` 是否闭环

### Phase 5，治理接入
最后再接：
- MasterControl 权限检查
- 审计日志
- 成本与配额
- 降级策略

原因：
如果前面运行态资产模型没定，治理会接到假对象上，后面必然返工。

---

## 8. 不可并行项

### 8.1 资产元数据定义 vs 资产发现 tool 实现
不能并行。

原因：
descriptor 没定，tool 返回结构必然反复改。

### 8.2 核心资产注册 vs App / Skill 安装链路
不能并行。

原因：
核心资产注册都没定，App / Skill 资产模型更容易跑偏。

### 8.3 治理权限接入 vs 运行态资产契约定义
不能并行。

原因：
权限点要挂在稳定资产契约上，不然全是临时 patch。

### 8.4 可以并行的低冲突项
可以并行：
- H2.1 资产元数据定义
- H4.3 验证记录模板

原因：
一个定义运行态公共语义，一个定义验证沉淀格式，低耦合。

---

## 9. 每阶段完成标准

### Phase 0 完成标准
- 资产契约稳定
- 资产分类稳定
- 生命周期状态机稳定

### Phase 1 完成标准
- 核心系统服务可注册为资产
- 系统能看到自身关键运行资产

### Phase 2 完成标准
- 系统能列出资产
- 能查看资产详情
- 能通过安全映射调用资产方法

### Phase 3 完成标准
- App / Skill / Session 真正进入运行态资产中心
- 安装、启动、注册、发现形成闭环

### Phase 4 完成标准
- 至少三条真实用户场景通过结构化验证
- 失配点可定位、可回写

### Phase 5 完成标准
- 权限、审计、成本、降级统一挂在资产语义上
- 失败时能解释“谁操作了什么，为何失败”

---

## 10. 与顶层场景的映射

- 资产发现能力，支撑 A 类“你能做什么 / 我有哪些资产”
- App 运行态闭环，支撑 B 类创建场景
- 生命周期动作统一，支撑 D 类启动/停止/恢复
- Session 资产化，支撑 E 类多轮与状态
- 权限与审计挂接，支撑 F 类权限与审批
- 状态与恢复统一，支撑 G 类持久化与恢复
- 降级挂接，支撑 H 类异常与降级
- 组合资产调用，支撑 I 类复杂组合场景

---

## 11. 正式 Task List

### H2.1 最小公共资产契约
- [x] 定义 `AssetDescriptor` - 已实现在 `app/models/asset_contract.py`
- [x] 定义 `AssetCapability` - 已实现在 `app/models/asset_contract.py`
- [x] 定义 `AssetState` - 已实现在 `app/models/asset_contract.py`
- [x] 定义资产分类模型 - 已实现 `AssetKind`/`AssetType`/`Visibility`
- [x] 定义生命周期状态机 - 已实现 `ALLOWED_ASSET_STATE_TRANSITIONS`
- [x] 明确字段命名、枚举、契约位置 - 已固化在 Pydantic 模型

### H2.2 核心服务资产化注册
- [ ] `master_control` 注册
- [ ] `config_center` 注册
- [ ] `runtime_center` 注册
- [ ] `model_router` 注册
- [ ] `tool_calling_engine` 注册
- [ ] `light_brain_gateway` 注册

### H2.3 资产发现工具
- [ ] `list_assets`
- [ ] `query_asset_info`
- [ ] `call_asset_method`
- [ ] 安全映射层

### H3 运行态闭环
- [ ] App 链路接入
- [ ] Skill 链路接入
- [ ] Session 链路接入

### H4 验证与记录
- [ ] 建立 `docs/e2e-test-results.md`
- [ ] 固定记录模板
- [ ] 完成 A1/B1/D1 三个场景验证

### H5 治理挂接
- [x] 权限检查 - Iteration 20-21 完成 (PolicyAuthorityService)
- [x] 审计日志 - Iteration 8 完成 (AuditLogger)
- [x] 成本与配额 - Iteration 24-26 完成 (CostQuotaManager + ResourceBudgetManager)
- [x] 降级策略 - Iteration 23 完成 (Observability + block/reject 处理)

---

## 12. 当前最稳推进顺序

1. 正式化 Phase H 设计文档
2. 构建可执行 task list
3. 落地 H2.1 最小公共资产契约
4. 同步建立验证记录模板
5. 再进入核心资产注册与发现工具实现
