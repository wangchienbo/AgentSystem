# AgentSystem Task List - Phase H 资产化运行态详细执行设计

> 本文件不是普通 backlog，而是 **Phase H 的执行设计与收口约束**。
> 它服务于顶层规划：`control-plane/tasks/complex-system-adaptation-task-list.md`，用于把“资产化运行态”收敛成一条不会跑偏的主路径。
>
> 本阶段目标不是堆功能点，而是先建立稳定的运行态资产契约，再让注册、发现、生命周期、治理和验证逐层挂上去。

---

## 1. 设计约束

### 1.0 总体控制原则
Phase H 必须固定在三个层次上推进，不能再按模块自然生长：

#### A. 顶层目标层
文件：`control-plane/tasks/complex-system-adaptation-task-list.md`

职责：
- 定义什么叫“比较好用”
- 定义每轮真实场景
- 定义失配分类
- 决定本轮验证哪条主链路

#### B. 技术实现层
文件：`tasklist_phase_h.md`

职责：
- 只承接当前阶段为支撑主链路必须落地的技术任务
- 不能脱离顶层场景长出一套平行 roadmap
- 每个技术任务都必须能回答“它支撑哪个真实场景”

#### C. 运行验证层
文件：`docs/e2e-test-results.md`

职责：
- 记录真实链路验证
- 记录失配点
- 记录修复结果
- 记录是否进入下一轮

约束：
- 三层不能混
- 顶层目标层不承接具体实现细节
- 技术实现层不脱离顶层目标自行扩张
- 运行验证层不替代设计，也不替代实现

### 1.1 北极星
Phase H 的目标不是做一个抽象的“资产系统”，而是让 AgentSystem 具备下面这条真实可验证主链路：

`用户请求 → HTTP / Chat 交互层 → Gateway → Runtime → Asset Registry / RuntimeCenter → Tool / LLM / App 生命周期动作 → 可解释结果`

### 1.2 主路径原则
- 先收敛公共契约，再接入具体能力
- 先保证资产“可定义、可注册、可发现、可解释”，再扩展治理和复杂编排
- 优先做会被多处复用的稳定结构，不接受为了赶进度堆临时 patch
- Phase H 期间以真实场景链路闭环为准，不以孤立测试数量作为主进度指标

### 1.3 收敛顺序约束
必须按以下顺序推进：
1. 最小公共资产契约
2. 资产注册与发现
3. 安装/启动/生命周期接入
4. 真实链路验证
5. 治理与权限补位

其中，治理必须挂在稳定资产契约上，不能先行做一层临时权限 patch。

### 1.4 设计判断原则
遇到实现分歧时，优先采用以下判断标准：
- 是否降低后续返工成本
- 是否让 HTTP、Gateway、Runtime、Tool Call 共用同一语义
- 是否让真实场景更容易验证与记录
- 是否能作为后续 v1 主路径的稳定底座

---

## 2. 边界定义

### 2.1 Phase H 要解决的问题
Phase H 只解决“运行态资产化”的核心问题：
- 运行中的核心服务和应用实例，如何被统一表示
- 系统如何发现当前可操作对象
- 生命周期动作如何通过稳定资产语义暴露
- 用户交互链路如何基于资产发现和资产调用完成真实闭环
- 后续治理如何有稳定挂载点

### 2.2 Phase H 不直接解决的问题
以下内容不作为本阶段主目标，只能在不破坏主路径的前提下顺带兼容：
- 完整多租户治理体系
- 富 UI 控制台
- 全量复杂审批流
- 高级调度优化
- 完整的跨资产编排 DSL
- 过早细化所有资产类型的高级子契约

### 2.3 资产化边界
本阶段至少覆盖两类资产：

#### A. 核心系统资产
例如：
- `master_control`
- `config_center`
- `model_router`
- `tool_calling_engine`
- `light_brain_gateway`
- `runtime_center`

#### B. 运行态应用资产
例如：
- app instance
- session runtime（后续接入）
- materialized skill runtime（后续接入）

### 2.4 固定配置与运行态的边界
必须明确区分：
- **固定配置资产**：定义入口、静态依赖、系统内建能力来源
- **运行态资产**：当前活着、可查询、可调用、可变更状态的对象

原则：
- 固定配置负责“第一次知道它存在”
- 运行态资产中心负责“现在它是否可用、具备什么能力、如何操作它”

### 2.5 ConfigCenter 的边界
定位：固定配置入口，不是运行态真相源。

只负责：
- 系统第一次知道配置从哪来
- 默认模型、默认路由、默认资产入口
- 固定资产或静态配置的声明

不负责：
- 运行中有哪些资产活着
- 某个 App 当前状态
- 某个 Skill 当前是否已安装
- 某个用户当前会话是否存在

结论：
- ConfigCenter 是 bootstrap source，不是 runtime source of truth

### 2.6 RuntimeCenter 的职责边界
定位：运行态资产中心，是运行态发现的真相源。

RuntimeCenter 在 Phase H 中应承担：
- 资产注册
- 资产注销
- 资产状态查询
- 资产心跳
- 资产能力查询
- 资产基础调用分发入口

RuntimeCenter 不应在这一阶段承担：
- 固定配置规则
- 复杂权限决策本体
- 业务语义解释
- LLM prompt 编排
- 跨领域流程编排总控

结论：
- 所有“现在系统里有什么、能不能调用、状态是什么”都应该从 RuntimeCenter 看

### 2.7 LightBrainGateway 的边界
定位：唯一用户交互入口。

负责：
- 接收用户消息
- 绑定用户身份与 session
- 组织 LLM、Tool Call、资产调用
- 返回解释性回复

不负责：
- 自己保存完整运行态真相
- 自己维护资产目录
- 绕过 RuntimeCenter 直接硬编码调用所有服务

结论：
- 用户只跟 Gateway 交互，Gateway 再去发现和调用资产

### 2.8 ToolCallingEngine 的边界
定位：LLM 的动作执行层，不是资产目录本身。

负责：
- 暴露 tool schema 给 LLM
- 执行被选中的 tool
- 把 tool 结果回流给 LLM

不负责：
- 自己持有资产清单
- 自己决定系统里有哪些资产
- 绕开 RuntimeCenter 直接拼凑资产信息

结论：
- ToolCallingEngine 看见资产，必须通过 RuntimeCenter 或其暴露的 Asset tools

---

## 3. 最小公共契约

> 这是 Phase H 的第一落点，也是后续所有任务的挂载底座。

### 3.1 AssetDescriptor
用于描述资产是谁。

建议最小字段：
- `asset_id`
- `asset_type`
- `version`
- `owner_type`
- `owner_id`
- `source_of_truth`
- `is_static`
- `status`
- `capabilities`
- `invoke_contract`
- `health_contract`
- `created_at`
- `updated_at`
- `tags`

语义要求：
- `asset_id` 全局唯一且稳定
- `asset_type` 必须能区分系统核心服务 / app / session / skill-runtime 等类别
- `source_of_truth` 明确该资产定义来自配置、注册表还是运行时生成

### 3.2 AssetCapability
用于描述资产能做什么。

建议最小字段：
- `name`
- `description`
- `method`
- `input_schema_ref` 或等价输入约束
- `output_schema_ref` 或等价输出约束
- `side_effect_level`
- `requires_runtime_alive`

语义要求：
- capability 要可被 LLM / Tool 层解释
- capability 不能只是一段自由文本，至少要有稳定方法标识
- capability 是权限、审计、验证的未来挂点

### 3.3 AssetState
用于描述资产当前处于什么状态。

建议最小演进状态集：
- `declared`
- `installing`
- `starting`
- `active`
- `degraded`
- `stopped`
- `removed`

可选异常扩展：
- `crashed`
- `paused`
- `unknown`

语义要求：
- 状态集必须足够小，避免一开始过度设计
- 状态必须支持 lifecycle 管理与验证记录
- 后续权限与降级逻辑必须能直接依赖该状态枚举

### 3.4 资产分类模型
至少分四类：
- `fixed_asset`，固定资产，例如 `config_center`
- `core_runtime_asset`，核心运行资产，例如 `master_control`
- `materialized_asset`，安装或生成后进入运行态的 App/Skill
- `session_asset`，用户会话资产

约束：
- 不能把固定配置资产和运行时实例资产混为一类
- 不能让 session 语义提前污染核心资产契约

### 3.5 生命周期状态机
最小状态迁移建议：
- `declared -> installing`
- `installing -> starting`
- `starting -> active`
- `starting -> crashed`
- `active -> degraded`
- `active -> stopped`
- `active -> crashed`
- `degraded -> active`
- `degraded -> stopped`
- `stopped -> starting`
- `stopped -> removed`

约束：
- 不允许跳过安装/启动阶段直接进入 active
- 已启动但 RuntimeCenter 不知道，视为链路不完整
- `crashed` 不等于 `stopped`，它代表异常终止
- ConfigCenter 有配置但运行态没起来，不构成可发现资产

---

## 4. 状态机与执行流

### 4.0 交互主链路总约束
用户只在交互层交互，因此主链路必须是：

`HTTP/UI -> Login/Auth -> LightBrainGateway -> ToolCallingEngine / Orchestrator -> RuntimeCenter -> Asset`

不能出现：
- 用户直接打 RuntimeCenter
- 用户直接打 ConfigCenter
- 前端绕过 Gateway 直调资产

固定配置只负责第一次找到入口，因此 ConfigCenter 只能回答：
- 默认模型是什么
- 固定入口是什么
- 初始静态声明是什么

不能回答：
- 这个 App 现在在不在
- 这个 Skill 是否已 materialize
- 这个 session 当前是否有效

LLM 必须先发现资产，再调用资产，因此 Tool Call 层必须拆成两步：
1. `list_assets` / `query_asset_info`
2. `call_asset_method`

不能让 LLM 在不知道资产能力边界的情况下直接盲调动作。

### 4.1 资产注册主流
`create/install -> start/materialize -> register -> heartbeat -> discoverable`

对系统核心服务则是：
`系统启动 -> 生成 AssetDescriptor -> 附带 capabilities -> 写入 RuntimeCenter -> 进入 starting -> 成功后 active`

### 4.2 资产发现主流
`交互层/Tool/LLM 请求 -> RuntimeCenter 查询资产列表/详情 -> 返回 descriptor + state + capabilities`

### 4.3 资产调用主流
`调用方发起操作 -> 通过 asset_id 定位 -> 校验当前 state 与 capability -> 分发到真实实现 -> 返回结构化结果 -> 更新 state/审计记录`

### 4.4 生命周期动作主流
对 app 类资产至少支持：
- start
- stop
- pause（可后置）
- resume（可后置）
- status

### 4.5 异常与降级主流
Phase H 只要求实现最小可解释闭环：
- 调用失败时能知道失败发生在哪一层
- 资产不可用时能明确反映到 state
- 失败不会把资产留在不可理解的中间态

---

## 5. 分阶段任务

## Phase H.1 基础设施（已完成）
- [x] HTTP API 服务框架
- [x] 用户认证流程骨架
- [x] Gateway 接入
- [x] ToolCallingEngine 资产感知路由
- [x] ModelRouter config-first API key 读取
- [x] ConfigCenter 固定配置加载
- [x] RuntimeCenter 基础实现

### H1 完成价值
- 提供了交互入口
- 提供了 runtime 容器和基础编排位置
- 为 Phase H 后续资产化接入留出了骨架

---

## Phase H.2 资产契约与注册发现（当前主阶段）

### H2.1 最小公共资产契约
- [ ] 定义 `AssetDescriptor`
- [ ] 定义 `AssetCapability`
- [ ] 定义 `AssetState`
- [ ] 定义资产生命周期最小状态机
- [ ] 统一命名与字段约束

交付标准：
- Runtime、Gateway、Tool Call、API 可以共用同一套语义
- 不再通过隐式字符串约定表达资产能力与状态

### H2.2 核心服务资产化注册
- [ ] 在 `build_runtime()` 中完成核心服务实例注册
- [ ] 系统启动后可看到核心服务资产清单
- [ ] 系统关闭时注销或切换到合理终态
- [ ] 心跳或等价机制能维护运行态状态

建议首批资产：
- `asset:master_control:v1`
- `asset:config_center:v1`
- `asset:model_router:v1`
- `asset:tool_calling_engine:v1`
- `asset:light_brain_gateway:v1`
- `asset:runtime_center:v1`

### H2.3 资产发现接口
- [ ] `list_assets(filter)`
- [ ] `query_asset_info(asset_id)`
- [ ] `call_asset_method(asset_id, method, params)`

交付标准：
- LLM 或交互层可以先发现资产，再决定调用
- 发现结果包含 descriptor/state/capabilities
- 资产调用返回结构化结果，而不是散乱响应

---

## Phase H.3 安装、启动、生命周期接入

### H3.1 App 安装工作流接入
- [ ] `validate_blueprint`
- [ ] `create_app_instance`
- [ ] `install`
- [ ] `register_to_runtime`
- [ ] 生成稳定 app asset_id

### H3.2 Skill 安装与 materialization 接入
- [ ] skill 安装后注册为可发现资产
- [ ] 动态 skill 生成后同步进入 RuntimeCenter
- [ ] 修改链路逐步挂到资产语义上

### H3.3 生命周期动作接入
- [ ] start_app
- [ ] stop_app
- [ ] pause_app（可次级）
- [ ] resume_app（可次级）
- [ ] status 查询统一走资产状态

交付标准：
- app 从“定义/安装对象”进入“运行态资产对象”
- 生命周期动作不再依赖散落的特判入口

---

## Phase H.4 真实链路验证与记录

### H4.1 端到端主链路验证
目标场景示例：
- 用户说：“启动我的监控应用”
- 系统发现相关资产
- 系统读取资产能力
- 系统执行 start 动作
- 系统返回结构化结果与当前状态

验证要求：
- 明确经过了哪些控制流节点
- 记录失配点
- 记录修复结果

### H4.2 多轮与 session 资产化
- [ ] `asset:session:{user_id}:{session_id}` 语义接入
- [ ] session 状态与 memory 绑定
- [ ] 解决多轮丢状态 / 串状态问题

### H4.3 验证记录模板
- [ ] 建立 `docs/e2e-test-results.md` 或等价文档
- [ ] 固定记录模板：
  - 场景
  - 输入
  - 控制流
  - 预期
  - 实际结果
  - 失配分类
  - 修复动作
  - 当前结论
  - 遗留问题

交付标准：
- 每轮真实验证都能沉淀为结构化记录
- 顶层任务迭代能直接消费这些记录

---

## Phase H.5 治理与权限接入

### H5.1 MasterControl 权限接入
- [ ] 用户操作资产前做权限检查
- [ ] 普通用户 / admin / root 边界真实落地
- [ ] 权限判断挂在 capability 与 asset 语义上

### H5.2 审计日志与失败定位
- [ ] 记录谁操作了哪个资产
- [ ] 记录调用方法、时间、结果、失败原因
- [ ] 失败时可定位到交互层 / Gateway / Runtime / Asset 调用层

### H5.3 成本、配额、降级
- [ ] ModelRouter 成本追踪按 user / asset 维度挂接
- [ ] LLM 或 orchestrator 不可用时触发清晰降级策略

交付标准：
- 治理不再是补丁式逻辑
- 权限、审计、降级都挂在统一资产语义上

---

## 6. 不可并行项

### 6.1 治理权限接入 vs 运行态资产契约定义
**不可并行。**

原因：
- 权限检查必须挂在稳定 capability/asset 语义上
- 若资产契约未先稳定，权限逻辑只能变成临时 patch
- 后续会导致审计、降级、接口返回全部返工

结论：
- 必须先完成 H2.1，再进入 H5.1

### 6.2 生命周期动作扩展 vs 资产发现接口缺失
**不建议并行。**

原因：
- 若先铺 start/stop 入口但资产发现未统一，交互层仍需走特判
- 会让“发现-调用-状态查询”链路断裂

### 6.3 session 资产化 vs 主 app 资产主链路未闭合
**不建议提前展开。**

原因：
- session 属于第二层运行态对象
- 主 app 资产契约和调用语义未稳定前，session 接入容易带来双倍返工

---

## 7. 可以并行的低冲突项

以下两项可以并行推进：
- **H2.1 资产元数据定义**
- **H4.3 验证记录模板**

原因：
- 一个定义运行态公共语义
- 一个定义验证沉淀格式
- 二者低耦合，且都能直接为主路径服务

---

## 8. 每阶段完成标准

### H2 完成标准
- 资产公共契约稳定
- 核心系统服务完成注册
- 系统能列出资产、查询资产详情、调用最小资产方法
- 交互层不再依赖“知道内部对象名”的隐式耦合

### H3 完成标准
- app 安装后进入运行态资产中心
- 生命周期动作可通过统一资产语义执行
- app 具备最小可运维性

### H4 完成标准
- 至少有一条真实用户场景主链路完整跑通
- 每次验证都有结构化记录
- 失配点可以稳定复现与回写

### H5 完成标准
- 权限、审计、降级都挂载在统一资产语义上
- 失败时可以解释“谁操作了什么，为何失败”
- 资产层具备进入 v1 主链路的治理基础

---

## 9. 与顶层场景的映射

### 对顶层 v1 目标的支撑关系
- **统一交互表达需求** → H1 + H4
- **稳定查看 App 列表和详情** → H2.3
- **稳定启动/停止/暂停/恢复** → H3.3 + H4.1
- **简单修改并看到结果** → H3.2 + H4.1
- **多轮对话不明显丢状态** → H4.2
- **权限边界基本正确** → H5.1
- **重启后关键状态可恢复** → H3 + 后续恢复机制
- **某层不可用时可降级** → H5.3
- **失败时能定位问题** → H4.3 + H5.2

### 对顶层复杂系统适配框架的意义
Phase H 不是孤立实现，而是在顶层“真实场景 → 控制流 → 失配 → 修复 → 记录 → 回写”的迭代框架中，提供运行态资产这一层稳定底座。

没有这个底座，后续很多问题都会退化成：
- 到处塞 patch
- 状态散落
- 权限无挂点
- 验证不可复用

---

## 10. 当前最稳推进顺序

1. H2.1 最小公共资产契约
2. H4.3 验证记录模板（可并行）
3. H2.2 核心服务资产化注册
4. H2.3 资产发现接口
5. H3.1 App 安装工作流接入
6. H3.3 生命周期动作接入
7. H4.1 端到端主链路验证
8. H5.1 治理权限接入
9. H5.2 / H5.3 审计与降级补强
10. H4.2 session 资产化

---

## 11. 当前结论

Phase H 现在最稳的动作不是继续散点写代码，而是先把：
- **执行设计文档稳定下来**
- **最小公共资产契约落地出来**

只有这样，后续注册、发现、生命周期、治理、验证才会挂在同一条主路径上，不会继续演化成局部修补。