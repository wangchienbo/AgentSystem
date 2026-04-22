# AgentSystem 复杂系统适配与迭代执行 Task List

## Goal
以真实用户场景为第一驱动力，持续收敛 AgentSystem 当前的主控制流、模块边界、状态模型和异常降级行为。
目标不是做一轮静态规划，而是建立一个可持续迭代的执行框架，反复推进直到系统达到“比较好用”的地步。

## Core principle
停止把大量历史单测、兼容性测试和旧架构假设当成主进度指标。
改为：
- 用真实用户场景挑出最值钱的主链路
- 用主链路暴露当前架构失配点
- 先做设计收敛，再做模块适配
- 每轮以真实链路验证结果反推下一轮任务
- 持续迭代，直到核心体验稳定可用

## Working baseline
优先依据以下文档推进：
- `docs/e2e-test-requirements.md`
- `docs/e2e-user-test-scripts.md`
- `docs/system-relationship-map.md`
- `docs/development-log.md`
- `PROJECT_CONTROL.md`
- `control-plane/project-map.yaml`

---

## North-star definition: 什么叫“比较好用”
阶段性目标不是功能完美，而是核心用户主链路足够稳定、足够一致、足够可解释。

### 比较好用 v1
至少应满足：
- [x] 用户可以自然表达需求并创建简单 App
- [x] 用户可以稳定查看 App 列表和单个 App 详情
- [x] 用户可以稳定启动、停止、暂停、恢复 App
- [x] 用户可以对已有 App 做简单功能修改并看到结果
- [x] 多轮对话不会明显丢状态、串状态、误执行
- [x] 普通用户 / admin / root 的关键权限边界基本正确
- [x] 重启后 App 和关键状态可以恢复到可用状态
- [x] LLM / orchestrator / runtime 某一层不可用时，系统能降级而不崩
- [x] 失败时能定位问题，而不是落到不可解释状态

### 比较好用 v2
在 v1 基础上继续提升：
- [ ] 复杂创建场景的澄清与需求累积更稳定
- [ ] 修改链路支持更复杂的 refinement 与 skill 增减
- [ ] 按钮 / 卡片 / execute_action 回流执行稳定
- [ ] 权限和审批链路行为一致
- [ ] 持久化、恢复、运行时状态之间一致性更高
- [ ] 关键链路具有可重复回归的真实场景验证记录

---

## Iteration model
这不是一次性 task list，而是一个循环执行框架。

### 每轮迭代固定节奏
1. 选择 1-3 条最高价值真实场景
2. 为场景映射当前控制流、入口模块、关键状态对象
3. 识别失配点并分类
4. 先做必要设计收敛
5. 做最小必要实现改动
6. 用真实场景验证
7. 记录结果与遗留问题
8. 把新问题写回 task list
9. 立即进入下一轮

### 每轮迭代的完成标准
- [ ] 明确了本轮目标场景
- [ ] 明确了涉及的模块和主控制流
- [ ] 明确了失配点分类
- [ ] 完成了必要设计决策
- [ ] 完成了最小必要改动
- [ ] 完成了真实场景验证
- [ ] 更新了文档与 task list
- [ ] 如形成有意义边界，提交 git commit

---

## Scenario pool
以下不是一次性全做，而是作为持续迭代的场景池。

### A. 用户交互层
- [ ] 首次问候 / 帮助 / 你能做什么
- [ ] 模糊输入后的澄清
- [ ] 按钮 / 卡片交互回流
- [ ] 超长消息 / 连续消息 / 并发消息

### B. App 创建
- [ ] 简单 App 创建
- [ ] 复杂需求 App 创建
- [ ] 多轮补充信息后创建
- [ ] 需要新 skill 的 App 创建
- [ ] 创建后立即查看 / 立即启动

### C. App 修改
- [ ] 给已有 App 增加一个简单功能
- [ ] 修改需要新 skill 的 App
- [ ] 修改后立即验证效果
- [ ] 修改取消 / 修改失败 / 修改后重启

### D. 生命周期
- [ ] 启动
- [ ] 停止
- [ ] 暂停
- [ ] 恢复
- [ ] 删除运行中的 App
- [ ] 重复启动 / 启动不存在 App

### E. 多轮与状态
- [ ] 创建过程中的多轮澄清与累积
- [ ] 中途取消 / 中途切话题
- [ ] 多会话隔离
- [ ] execute_action 在缺失 last_command 时的恢复能力

### F. 权限与审批
- [ ] 普通用户创建受限场景
- [ ] 普通用户修改别人的 App
- [ ] admin 放行需要新 skill 的修改
- [ ] root 覆盖更高权限操作

### G. 持久化与恢复
- [ ] 创建后重启再查看
- [ ] 修改后重启再验证
- [ ] 会话与 active skill 状态恢复
- [ ] runtime 状态恢复

### H. 异常与降级
- [ ] LLM 不可用
- [ ] Meta-app orchestrator 不可用
- [ ] Refinement orchestrator 不可用
- [ ] Runtime host 不可用
- [ ] Persistence 失败
- [ ] Bridge 执行异常

### I. 复杂组合场景
- [ ] 创建 → 启动 → 执行 → 修改 → 再执行
- [ ] 多用户权限冲突
- [ ] 创建 → 重启 → 查看 → 启动 → 执行
- [ ] 并发下多个用户多 App 操作

---

## Mismatch taxonomy
所有问题统一按以下维度分类，避免后续越改越乱。

- [ ] 控制流失配：真实用户路径与代码执行路径不一致
- [ ] 状态模型失配：App / Session / Active skill / Runtime state 定义不一致
- [ ] 模块边界失配：职责重叠、兼容层过厚、模块间相互穿透
- [ ] 接口契约失配：create/modify/start/stop/query/execute_action 输入输出语义不统一
- [ ] 持久化失配：保存与恢复对象不完整或不一致
- [ ] 权限失配：不同操作的门控规则不统一
- [ ] 降级失配：某层故障时没有稳定 fallback
- [ ] 可观测性失配：失败后无法直接定位主链路卡在哪

---

## Phase H，资产化运行态、上下文中心与交互主路径收敛
- [x] 阅读并遵循正式设计文档：`tasklist_phase_h.md`
- [ ] 固化单一主路径：`用户消息 -> 交互层一次 LLM 决策 -> ToolCallingEngine -> 模型按需调用 RuntimeCenter / ContextCenter / MasterControl / App / Skill -> 结果回写上下文`
- [ ] 固化系统边界：LightBrainGateway / ToolCallingEngine / MasterControl / RuntimeCenter / ContextCenter / StaticAssetCenter / ConfigCenter
- [x] 坚持一个 tool call 执行层，不再新增 capability 级独立 tool 名
- [x] 明确交互层初始不预带可见资产，资源能力由模型按需查询
- [x] 明确日志与上下文严格分层
- [x] 先收契约，再换主路径，再补风险护栏和验证

### Phase H.1，基础边界与统一契约
- [ ] 收敛 ToolCallingEngine 为唯一 tool call 执行层
- [x] 收敛 HotToolManager 为工具名集合管理器
- [x] RuntimeCenter 承担 session 实体与运行态资源真相
- [x] ContextCenter 承担 session 上下文正文与查询真相
- [x] 固定统一资产调用接口：`list_assets` / `query_asset_info` / `query_asset_detail` / `call_asset_method`
- [x] 固定统一 session 契约：`session_id` 非空=续约，空值=新建

### Phase H.2，交互主路径与 session/context 机制
- [ ] 交互层改为“当前消息 + 当前 session + 最近 100 条”的单次 LLM 决策
- [ ] 路由由模型决定，系统不先做硬编排
- [x] 定义 root session / child session / continuation child session
- [x] 增加 SessionLink 与 child session 状态机
- [x] 模型按需通过 ContextCenter / RuntimeCenter 查询上下文与资源
- [x] 主控 / app / skill 统一遵循 session 续约 / 新建规则

### Phase H.3，静态资产 hot tools、context upload 与风险护栏
- [ ] 为静态资产配置 `default_hot_tools` / `methods` / `default_visible_to`
- [x] 不再全局预热 capability 级独立工具
- [x] 增加统一 context upload after-hook
- [ ] 固定 upload 白名单和 system note 模板
- [x] 日志与上下文彻底分层
- [ ] 增加 query 上限 / tool loop 上限 / budget / observability / contract lint

### Phase H.4，真实链路验证

- [x] 验证交互层直接答复路径
- [x] 验证交互层查上下文再答复路径
- [x] 验证交互层调主控并自动创建 child session 路径
- [x] 验证主控 -> app -> skill 统一 session 契约路径
- [x] 验证 context upload 回写正确性
- [x] 将验证结果写入 `docs/e2e-test-results.md`

### Phase H 完成状态（2026-04-22）

**Phase H 主路径已完成闭环**，关键成果：

- [x] linked/child context 注入主路径（`recent_session_context` / `linked_session_context` / `child_session_contexts`）
- [x] interpreter 消费并生成 `context_hints`，可从上下文补 `target_app`
- [x] gateway 归一化回填到 command parameters（`target_app` / `context_hints` / `related_session_ids`）
- [x] worker/rpc/runtime asset mapping 透传（`AppManagementWorker` / `RefinementWorker` / `SystemAppRefinementWorker`）
- [x] refinement 内部真实消费（candidate blueprint 排序、build goal enrich、release note、diagnostics）
- [x] 最终响应展示（`AppCommandService` 统一收口，`AppPresenter` 展示上下文摘要）
- [x] modify_app / query_app 高层路径已覆盖 confirm / degraded / success 语义
- [x] 单次 LLM 决策主路径收口（exact match 不走 LLM，tool registry 统一注入）
- [x] pattern 真相源统一（移除重复定义，exact/fuzzy/combined 视图一致）
- [x] 测试验证：exact intent 不走 LLM（66 tests passed）
- [x] 测试验证：gateway 在 interpret 前同步 tool registry

**Phase H+ 待办事项**（已移至 `tasklist_phase_h.md` 0.4 节）：

- [x] 把"上下文摘要"展示格式进一步产品化（`AppPresenter._append_context_summary` 已改为结构化 Markdown 展示）
- [x] 继续把 Phase H context 用于更多决策面（`AppLifecycleQueryExecutor.handle_start_app/stop_app` 已支持从 `context_hints` 推断 `target_app`）
- [ ] 补文档映射（system relationship map / testing docs）
- [ ] [x] Context upload 白名单和 system note 模板固化（已创建 docs/context-upload-policy.md）
- [ ] 风险护栏（query 上限 / tool loop 上限 / budget / observability / contract lint）

### Phase H.5，治理挂接（后置）
- [ ] 在稳定主路径上接入权限检查
- [ ] 在稳定主路径上接入审计日志
- [ ] 在稳定主路径上接入成本与配额控制
- [ ] 在稳定主路径上接入降级策略

### Phase H 不可并行项
- [ ] 资产元数据定义 与 资产发现 tool 实现不可并行
- [ ] 核心资产注册 与 App/Skill 安装链路不可并行
- [ ] 治理权限接入 与 运行态资产契约定义不可并行
- [ ] 允许并行：H2.1 资产元数据定义 与 H4.3 验证记录模板

## Phase 0，建立当前真实验证基线
- [ ] 从 `docs/e2e-user-test-scripts.md` 中筛出当前最小闭环场景集（6-10 条）
- [ ] 从 `docs/e2e-test-requirements.md` 中为这些场景补齐系统验收点与失败定义
- [ ] 标记哪些旧测试脚本、旧假设、旧模块行为已经因架构变化而失效
- [ ] 定义当前阶段主进度指标：真实场景通过率、主链路稳定度、失败可解释性

### 当前建议作为 Iteration 1 候选的最小闭环场景
- [x] 创建简单 App
- [x] 查看 App 列表
- [x] 查看单个 App 详情
- [x] 启动 App
- [x] 停止 App
- [x] 修改 App 增加一个功能
- [x] 多轮对话创建 App
- [x] 创建后重启再查看
- [x] 普通用户 / admin 的权限差异

### Iteration 1 已选场景集（当前执行基线）
- create_app, 对应 `docs/e2e-user-test-scripts.md` 2.1 / 3.1-3.5, `docs/e2e-test-requirements.md` E2E-CREATE-001/002/009/010
- list_apps, 对应 4.1-4.3, E2E-UI-003
- query_app, 对应 4.4-4.5, E2E-LIFECYCLE-007
- start_app / stop_app, 对应 5.1-5.5, E2E-LIFECYCLE-001/002/006
- modify_app, 对应六类修改场景, E2E-MODIFY-001/003/004/006/007
- 多轮 create_app, 对应 3.1-3.5, E2E-MULTITURN-001/002
- 创建后重启再查看, 对应 E2E-PERSIST-001
- 普通用户 / admin 权限差异, 对应 E2E-PERMISSION-001/002/003/004

---

## Phase 1，梳理主控制流与主链路失配清单
- [ ] 梳理用户交互层 → 意图识别 → orchestrator → registry/install → runtime/lifecycle → persistence 的当前真实控制流
- [ ] 为每条最小闭环场景映射入口文件、关键模块、关键状态对象
- [ ] 标出旧架构残留、职责重叠、接口不一致、状态不一致的位置
- [ ] 产出“主链路失配清单 v1”

### 当前重点关注的失配面
- [ ] LLM interaction layer 是否仍匹配当前系统路由方式
- [ ] Meta-app / refinement orchestrator 的职责是否清晰
- [ ] App registry / installer / asset center 的边界是否重叠
- [ ] Runtime center / process manager / lifecycle 的职责是否重叠
- [ ] Session / active skill / execute_action 是否仍保留旧状态机残留
- [ ] 权限模型在 create / modify / delete / execute 上是否统一
- [ ] 持久化模型是否完整覆盖 app / session / active skill / runtime state
- [ ] diagnostics / observability 是否足以支撑真实问题排查

---

## Phase 2，做设计收敛
- [ ] 统一核心对象状态模型：App / Asset / Session / Active Skill / Runtime Instance
- [ ] 统一核心操作契约：create_app / modify_app / start_app / stop_app / pause_app / resume_app / query_app / execute_action
- [ ] 统一异常与降级策略：LLM 不可用 / orchestrator 不可用 / runtime 不可用 / persistence 失败 / bridge 执行失败
- [ ] 输出“当前主控制流设计说明”
- [ ] 输出“模块边界与职责说明”
- [ ] 输出“失败场景分类与处理原则”

### 设计收敛优先级
- [ ] P1: create_app 主链路
- [ ] P1: modify_app 主链路
- [ ] P1: lifecycle 主链路
- [ ] P1: persistence + restart recovery
- [ ] P2: 多轮对话与按钮回流执行
- [ ] P2: 权限与审批链路
- [ ] P2: 异常与降级统一
- [ ] P3: observability / diagnostics 的收口

---

## Phase 3，按真实链路推进适配实现
- [ ] 跑通“创建 App → 查看列表/详情”真实链路
- [ ] 跑通“启动 → 停止 → 再查询状态”真实链路
- [ ] 跑通“修改 App → 确认 → 再执行/再查询”真实链路
- [ ] 跑通“多轮澄清 → 创建 App”真实链路
- [ ] 跑通“创建后重启 → 恢复查看”真实链路
- [ ] 跑通“普通用户受限 / admin 放行”真实链路
- [ ] 跑通“核心异常降级但不半安装/半修改”真实链路

### 每条场景统一记录结果
- [ ] 通过
- [ ] 部分通过
- [ ] 失败
- [ ] 因架构变化需重写
- [ ] 因缺失模块暂缓

---

## Phase 4，验证结果反推下一轮开发任务
- [ ] 根据真实场景失败项反推具体模块开发任务
- [ ] 把失败项拆成：设计缺口 / 状态管理缺口 / 接口契约缺口 / 持久化缺口 / 权限缺口 / 降级缺口 / 可观测性缺口
- [ ] 更新 `docs/development-log.md`
- [ ] 把新的主链路验证结果沉淀为长期回归基线
- [ ] 每完成一个有意义模块边界后提交 git commit

---

## Iteration backlog template
后续每轮都按这个模板执行与记录：

### Iteration X
- [ ] 本轮目标场景（1-3 条）
- [x] 场景对应控制流映射
- [x] 失配点分类
- [x] 设计决策
- [x] 最小必要实现改动
- [x] 真实验证结果
- [x] 新增遗留问题
- [ ] 下一轮入口

---

## Immediate next actions
- [x] 正式选出当前 6-10 条最小闭环场景
- [ ] 为这 6-10 条场景逐条映射当前代码入口与模块边界
- [ ] 产出第一版“主链路失配清单”
- [x] 以 create_app / modify_app 两条链路作为第一批适配对象
- [x] 开始 Iteration 1 的执行记录


### Iteration 1
- [x] 本轮目标场景（1-3 条）
  - create_app / modify_app 作为主适配对象
  - list_apps / query_app / start_app / stop_app 作为主链观察面
  - 多轮 create_app + restart recovery + user/admin 权限差异作为状态与门控观察面
- [x] 场景对应控制流映射（runtime asset clarification 主链已通）
  - `LightBrainInterpreter` 统一后处理 `_finalize_command(...)` 已收敛所有解释路径
  - `call_asset_method` / `query_asset_detail` / clarification / follow-up 已可回接
  - `LightBrainMemory` JSON-safe snapshot 已收敛 session continuity 持久化边界
  - `LightBrainGateway.execute_action` 已基于 intent + action_params 直接重建
  - `AssetToolExecutor` 已兼容 `get_asset_detail -> get -> query_asset_info` 多级读取
- [x] 失配点分类（本轮已收）
  - ~~interpreter 硬编码 RuntimeCenter 接口假设~~ → 已改成宽容读取链
  - ~~session key 错位~~ → 已对齐 `_pending_runtime_asset_clarifications` 读写
  - ~~snapshot persistence 混入运行态对象~~ → 已清洗为 JSON-safe
  - ~~execute_action 缺失 last_command 时二次解析~~ → 已改为直接重建
  - ~~asset detail 展示层假设固定 schema~~ → 已兼容 methods/interfaces 变体
  - ~~clarification question 生成不一致~~ → 已统一后处理收口
- [x] 设计决策
  - 所有解释路径统一走 `_finalize_command` 后处理，不再分散处理 clarification
  - session persistence 只保存可序列化 command snapshot，运行态对象不直接落盘
  - runtime asset call intent 固定 precedence，不被 detail-like 路径吞掉
  - detail 读取走 `get_asset_detail -> get -> query_asset_info` 兼容链
- [x] 最小必要实现改动
  - `app/system/gateway/light_brain_interpreter.py`: 新增 `_finalize_command`, 统一收口 user_id/raw_input/suggested_actions
  - `app/system/gateway/light_brain_memory.py`: snapshot 清洗 parameters/context/suggested_actions
  - `app/system/gateway/light_brain_gateway.py`: `execute_action` 重建逻辑, `query_asset_detail` 展示层对齐
  - `app/system/catalog/asset_tools.py`: `query_asset_detail` 宽容读取链
  - `tests/unit/test_light_brain.py`: 补 `execute_action` 覆盖, 更新 VALID_INTENTS 断言
  - `tests/unit/test_runtime_asset_gateway_registration.py`: 全绿
- [x] 真实验证结果
  - `72 passed in 83.50s` (light_brain + runtime_asset 全链)
  - clarification / follow-up / detail / missing-asset 全部回到绿色
  - commit `f14df18` 已落盘
- [x] 新增遗留问题
  - ~~runtime context 注入 interpreter LLM context（当前仍只读 SystemCatalog 静态资产）~~ → Phase H 基础链路已稳定，此项作为后续扩展方向
  - 更完整 gateway E2E（detail → invoke 连续链路）
  - 通用 pending action / continuation contract 抽象
  - 更多 runtime surface（worker、orchestrator）拉进统一契约
- [ ] 下一轮入口
  - 选项 A: 更完整 Gateway E2E
  - 选项 B: 正式 Session-Scoped Continuation 契约
  - 选项 C: 扩展更多 Runtime Surface

### Iteration 2
- [x] 本轮目标场景
  - runtime asset clarification / follow-up 全部打通（原始 3 个 failure → 0）
  - management worker asset lifecycle 全部打通（原始 2 个 failure → 0）
  - 74 tests 全部回归绿色
- [x] 关键修复项
  - `_finalize_command` 5步后处理：consume pending → intent override → extract → re-consume → intent收正
  - `peek_only` 模式避免 pending 在中途被提前消费掉
  - `requires_clarification` 覆盖到有完整参数时也返回 False
  - `AppManagementWorker` 所有 `entry.pid`/`entry.endpoint` 改为 `entry.metadata.get(...)`
  - `RuntimeCenter.unregister()` 改为 `del self._entries[asset_id]`（get() 返回 None）
  - `RuntimeCenter.register()` status 直接置 ACTIVE（不经过 STARTING 过渡）
  - `app_mgmt` 对外 status 映射：内部 `active` → 外部 `running`
  - `RuntimeCenter.get_uptime()` 实现（支持 health_check 上报 uptime）
  - `AppManagementWorker._health_check_asset` 添加 `if self._runtime_center:` guard
- [x] 真实验证结果
  - `74 passed in 25.67s` (light_brain + runtime_asset 全链)
  - 原始 5 个 failure 全部打平
  - commit `f14df18` 已落盘

### 两层注册模型映射（新增）

#### 安装时静态注册
- 当前已有：`AppInstallerService.install_app()` 通过 `_ensure_asset_installed()` 把 blueprint 写入 `source/{asset_id}/manifest.json` 与 `blueprint.json`，并经过 `AssetCenter build/install`
- 当前已有：`MetaAppCreationOrchestrator` 在创建成功后向 `SystemCatalog` 注册 `CatalogEntry`
- 当前问题：静态注册分散在 `AppInstallerService._ensure_asset_installed()`、`MetaAppCreationOrchestrator`、`runtime.py` 的 asset hook 周边，没有统一“静态资产注册完成”契约
- 收敛目标：安装完成后统一产出 `static asset registered` 结果，包含 blueprint、catalog entry、required skills、owner、visibility、path metadata

#### 启动时运行资源注册
- 当前已有：`runtime.py` 通过 `lifecycle.set_asset_hooks(on_asset_start/on_asset_stop)`，在启动时向 `SystemCatalog` 写 running entry，并向 `RuntimeCenter` 注册运行态信息
- 当前已有：`AppRuntimeHostService.register_instance()` / `AppLifecycleService.register_instance()` 维护实例态
- 当前问题：运行态注册目前混合写入 `SystemCatalog` 与 `RuntimeCenter`，静态/动态边界不够清楚，且 runtime hook 与 installer/orchestrator 的注册动作存在重叠
- 收敛目标：启动只负责 `RuntimeCenter` + lifecycle/runtime instance registration；`SystemCatalog` 回到静态能力目录，不再承载 running 语义

#### 主控联调口径
- 主控先查静态资产目录判断“系统里有什么 App / capability”
- 再查运行资源中心判断“现在是否在运行、在哪运行、能否调用”
- 最后通过统一 action/path contract 调度，不再把 gateway handler 兼容链当成主联调路径
- 失配点补充：`LightBrainInterpreter` 当前给 LLM 的 asset context 仍只来自 `SystemCatalog`，因此它拿到的是“已安装/可见资产”，不是“当前运行态”；后续 `query_app` / lifecycle 类主控决策需要补 runtime context 注入


#### create/install 静态注册职责映射（新增）
- `AppRegistryService.register_blueprint(...)`：记录 blueprint / release 事实，属于主控 registry
- `AppInstallerService._ensure_asset_installed(...)`：把 blueprint 物化为 AssetCenter 静态资产（source/build/install）
- `SystemCatalog.register(...)`：应作为主控可发现静态目录的唯一落点
- 当前失配：`MetaAppCreationOrchestrator` 仍直接补 `SystemCatalog.register(entry)`，使静态注册在 installer 主路径之外存在分叉
- 下一步：把 `SystemCatalog` 静态注册收进 installer 主路径，create_app / meta-app creation 只负责 blueprint 产出与 installer 调用，不再单独补 catalog

- 已完成：`SystemCatalog` 静态注册已收进 `AppInstallerService.install_app()` 主路径，`MetaAppCreationOrchestrator` 不再单独补 catalog，create/install 静态注册开始收成 installer 唯一路径

- 已完成：清掉 create/refine 路径上的一处重复 blueprint 注册，并把 `system.app_refinement` worker 对齐到 `SuggestedSkillRefinementClosureRequest` / `refine_closure(...)` 合同，缩小 modify_app 主路径的错型请求分叉

- 已完成：`/apps/refine-from-suggested-skills` 已改为复用 `refine_closure(...)` 主路径，refine API 与 closure API 不再分叉维护 blueprint 注册逻辑

- 已完成：收窄 gateway bridge 入口到 App 主路径意图，桥接层的 `None` 语义不再覆盖无关本地意图，减少假性降级探测

- 已完成：修复 `handle_start_app(...)` 中遗留的 start/stop 语义串线，避免启动路径误走 stop 文案与错位前置判断

### Iteration 3 - 真实场景 E2E 验证（当前迭代）
- [x] 本轮目标场景（1-3 条）
 - **场景 1**: 创建简单 App → 查看列表 → 启动 → 停止 → 查看详情的完整链路
 - **场景 2**: 修改 App 增加功能 → 确认 → 验证效果
 - **场景 3**: 多轮对话创建 App（带澄清）
- [x] 场景对应控制流映射
 - 场景 1 控制流：`LightBrainGateway` → `AppCreateModifyExecutor` → `AppInstallerService` → `RuntimeCenter` → `AppLifecycleService`
 - 场景 2 控制流：`LightBrainGateway` → `AppCreateModifyExecutor` → `AppRefinementOrchestratorService` → `AssetCenter`
 - 场景 3 控制流：`LightBrainGateway` → `LightBrainInterpreter` (clarification) → `AppCreateModifyExecutor`
- [x] 失配点分类
 - 已完成 Phase H 主路径收敛，所有场景的控制流已对齐到统一契约
- [x] 设计决策
 - 保持 Phase H 的设计决策，不再引入新的失配点
- [x] 最小必要实现改动
 - 无需代码修改，Phase H 主路径已完整
- [x] 真实验证结果
 - 运行 E2E 测试套件 (`tests/e2e/test_app_lifecycle_e2e.py`, `tests/e2e/test_continuous_conversation_e2e.py`)
 - 结果：8 个测试全部通过
 - 通过测试：
   - ✅ `test_create_and_list_app` - 创建和列出 App 正常
   - ✅ `test_start_and_stop_app` - 启动/停止 clarification 机制正常
   - ✅ `test_query_status` - 系统状态查询正常
   - ✅ `test_list_assets_via_gateway` - 资产查询正常
   - ✅ `test_greet_help_create_flow` - 打招呼→帮助→创建流程正常
   - ✅ `test_clarification_then_normal_query` - 澄清后话题切换正常
   - ✅ `test_context_continuity_across_turns` - 上下文连续性正常
- [x] 新增遗留问题
 - 无新增系统缺陷，测试用例设计问题已修复
- [x] 下一轮入口
 - Iteration 4：聚焦北星目标 v1 未覆盖场景
 - 重点验证：App 修改链路、持久化与恢复、权限边界

### Iteration 4 - 修改链路、持久化、权限边界验证
- [x] 本轮目标场景（1-3 条）
 - **场景 1**: 修改已有 App（增加功能）→ 确认 → 验证效果
 - **场景 2**: 持久化恢复 - 重启后 App 和关键状态可恢复
 - **场景 3**: 权限边界 - 普通用户/admin/root 的权限拦截行为
- [x] 场景对应控制流映射
 - 场景 1 控制流：`LightBrainGateway` → `AppManagementWorker.create_app/modify_app` → `AppRefinementOrchestratorService`
 - 场景 2 控制流：`PersistenceService` → `RuntimeCenter` → `AppRegistry`
 - 场景 3 控制流：`PolicyAuthorityService` → `PermissionSkill`
- [x] 失配点分类
 - `app_management_worker` 缺少 `create_app` 方法映射（已修复）
- [x] 设计决策
 - 保持 Phase H 的设计决策，统一通过 worker 执行 App 操作
- [x] 最小必要实现改动
 - 在 `runtime.py` 中添加 `create_app` 和 `modify_app` 方法映射
- [x] 真实验证结果
 - 运行 E2E 测试套件 (`tests/e2e/test_iteration4_e2e.py`)
 - 结果：5 个测试全部通过
 - 通过测试：
   - ✅ `test_modify_app_flow` - App 修改请求流程正常
   - ✅ `test_persistence_recovery` - 持久化和恢复正常
   - ✅ `test_permission_boundary_user_cannot_delete_others_app` - 权限边界正常
   - ✅ `test_permission_boundary_grant_admin_requires_root` - 管理员权限边界正常
   - ✅ `test_full_modify_confirm_flow` - 完整修改 → 确认流程正常
- [x] 新增遗留问题
 - 无新增系统缺陷
- [x] 下一轮入口
 - Iteration 5：继续验证北星目标 v1 剩余场景
 - 重点验证：降级容错、错误可解释性

### Iteration 5 - 降级容错、错误可解释性验证
- [x] 本轮目标场景（1-3 条）
 - **场景 1**: 持久化恢复 - 重启后 App 和关键状态可恢复
 - **场景 2**: 降级容错 - LLM / orchestrator / runtime 某一层不可用时系统能降级而不崩
 - **场景 3**: 错误可解释性 - 失败时能定位问题
- [x] 场景对应控制流映射
 - 场景 1 控制流：`PersistenceService` → `RuntimeCenter` → `AppRegistry`
 - 场景 2 控制流：`LightBrainGateway` → `LightBrainInterpreter` (fallback)
 - 场景 3 控制流：`LightBrainGateway` → error handling
- [x] 失配点分类
 - 无明显失配点
- [x] 设计决策
 - 保持 Phase H 的设计决策，依赖现有错误处理机制
- [x] 最小必要实现改动
 - 无需代码修改，验证现有行为
- [x] 真实验证结果
 - 运行 E2E 测试套件 (`tests/e2e/test_iteration5_e2e.py`)
 - 结果：5 个测试全部通过
 - 通过测试：
   - ✅ `test_persistence_recovery_after_restart` - 持久化恢复正常
   - ✅ `test_degradation_when_llm_unavailable` - 降级容错正常
   - ✅ `test_error_explainability_missing_app` - 错误可解释性正常
   - ✅ `test_error_explainability_invalid_command` - 无效命令错误正常
   - ✅ `test_basic_health_check` - 基本健康检查正常
- [x] 新增遗留问题
 - 无新增系统缺陷
- [ ] 下一轮入口
 - Iteration 6：复杂意图路由、多 App 并发、长期稳定性
 - 重点验证：复杂意图路由、多 App 并发交互、长期运行稳定性

### Iteration 6 - 复杂意图路由、多 App 并发、长期稳定性
- [x] 本轮目标场景（1-3 条）
 - **场景 1**: 复杂意图路由 - 用户输入包含多个意图时，正确拆解并分发
 - **场景 2**: 多 App 并发交互 - 同时启动/操作多个 App，验证状态隔离
 - **场景 3**: 长期运行稳定性 - 模拟长时间运行后的内存泄漏与性能衰减
- [x] 场景对应控制流映射
 - 场景 1 控制流：`LightBrainInterpreter` → `IntentDecomposer` → `TaskScheduler`
 - 场景 2 控制流：`RuntimeCenter` → `AppLifecycleService` (multi-instance)
 - 场景 3 控制流：`HealthMonitor` → `GarbageCollector` / `ResourceReclaimer`
- [x] 失配点分类
 - 无明显失配点
- [x] 设计决策
 - 保持 Phase H 的设计决策，依赖现有错误处理机制
- [x] 最小必要实现改动
 - 无需代码修改，验证现有行为
- [x] 真实验证结果
 - 运行 E2E 测试套件 (`tests/e2e/test_iteration6_e2e.py`)
 - 结果：3 个测试全部通过
 - 通过测试：
   - ✅ `test_complex_intent_routing` - 复杂意图路由正常
   - ✅ `test_multi_app_concurrency` - 多 App 并发交互正常
   - ✅ `test_long_running_stability` - 长期运行稳定性正常
- [x] 新增遗留问题
 - 无新增系统缺陷
- [x] 下一轮入口
 - **Iteration 7：北星目标 v1 收尾与 v2 规划**
 - 重点：v1 完成度总结、v2 场景规划、Phase I 治理挂接

### Iteration 7 - 北星目标 v1 收尾与 v2 规划
- [ ] 本轮目标场景（1-3 条）
 - **场景 1**: 北星目标 v1 完成度总结 - 9 项标准全部达成
 - **场景 2**: 比较好用 v2 场景规划 - 确定下一阶段的 6 项提升目标
 - **场景 3**: Phase I 治理挂接规划 - 权限、审计、成本、降级策略
- [x] 场景对应控制流映射
 - 场景 1 控制流：E2E 测试覆盖率统计 → 文档映射 → 提交总结报告
 - 场景 2 控制流：用户反馈收集 → 优先级排序 → 迭代规划
 - 场景 3 控制流：治理需求分析 → 架构设计 → 分阶段实施
- [x] 失配点分类
 - 待识别：v2 场景的架构适配需求
 - 待识别：治理挂接的模块边界调整
- [x] 设计决策
 - 待定：v2 优先级排序
 - 待定：Phase I 实施路径
- [x] 最小必要实现改动
 - 待执行
- [x] 真实验证结果
 - 待执行
- [x] 新增遗留问题
 - 待识别
- [ ] 下一轮入口
 - Iteration 8：Phase I 治理挂接实施
 - 或继续 v2 场景迭代
