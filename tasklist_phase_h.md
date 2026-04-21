# AgentSystem Task List - Phase H 资产化运行态与上下文主路径重构执行设计

> 本文件不是普通 backlog，而是 **Phase H 的执行设计、顺序约束与风险护栏**。
> 它服务于顶层规划：`control-plane/tasks/complex-system-adaptation-task-list.md`。
>
> 本阶段目标不是继续给旧链路打补丁，而是把 AgentSystem 的运行态资产、单一 tool call 层、上下文中心、会话树和交互主路径收敛成一条稳定主路径。

---

## 1. 目标与总原则（Chapter 1）

> 本章只回答三个问题：
> 1. Phase H 这一轮到底在收什么主路径
> 2. 哪些原则是硬约束，后续实现不能回退
> 3. 哪些东西明确不是当前阶段目标，避免范围继续膨胀

### 1.1 本阶段真实目标
建立这样一条统一主路径：

`用户消息 -> 交互层一次 LLM 决策 -> ToolCallingEngine -> 模型按需调用 RuntimeCenter / ContextCenter / MasterControl / App / Skill -> 结果回写上下文`

本阶段要解决的不是抽象的“能力更多”，而是：
- tool call 只有一层
- 资产调用只有一套统一契约
- session 生命周期与 session 上下文分开管理
- 交互层、主控层、app 层、skill 层遵循同一 session 续约/新建规则
- 通过 session tree 控制多轮对话上下文膨胀
- 日志和上下文彻底分层

### 1.2 北极星验收标准
完成这一阶段后，系统至少应该满足：
- 用户消息进入后，交互层只做一次统一 LLM 决策，不再走多套并列路由逻辑
- 模型可以通过统一 tool call 能力，自主查询上下文、资源并决定是否调主控
- session_id 契约在交互层、主控、app、skill 之间一致
- context upload 成为统一默认后处理，而不是各层手工补写
- 工具层、运行态层、上下文层、静态资产层、配置层的真相源边界清晰

### 1.3 主路径原则
- 不做复杂上下文剪裁层
- 不依赖摘要压缩传递用户意图
- 不再把 asset capability 动态映射成独立 tool 名
- 不先做硬路由编排，优先把能力暴露给模型，由模型做路由选择
- 所有正式结果统一通过 context upload 回写
- 交互层初始不预带可见资产，资源能力由模型按需查询
- 任何实现都不能重新把日志和上下文混成一套东西

### 1.4 当前阶段的硬约束
以下约束一旦确认，后续实现不得回退：
- ToolCallingEngine 是唯一 tool call 执行层
- RuntimeCenter 负责 session 实体与运行态资源
- ContextCenter 负责 session 对应上下文正文
- StaticAssetCenter 负责静态资产契约
- ConfigCenter 只负责 bootstrap 配置来源
- session_id 非空=续约，空值=新建
- 模型不能直接生成真实 session id，只能传空值或已有 id

### 1.5 非目标
本阶段不追求：
- 富 UI 控制台
- 全量多租户治理
- 完整 DSL 编排
- 高级调度优化
- 复杂审批系统
- 过早做全自动智能摘要/压缩体系
- 过早引入第二套上下文裁剪/预编排层

### 1.6 执行判断原则
后续遇到实现分歧时，优先按以下顺序判断：
1. 是否会破坏单一 tool call 层
2. 是否会模糊 RuntimeCenter / ContextCenter / StaticAssetCenter 的真相源边界
3. 是否会让 session 续约 / 新建规则不一致
4. 是否会把本该由模型决策的路由重新塞回系统硬编排
5. 是否会让上下文重新膨胀或让日志污染交互上下文

---

## 2. 基础边界与真相源（Chapter 2）

> 本章目标是把“谁是真相源，谁只是执行器，谁只是编排器”一次讲清楚。
> 后续所有实现都必须以本章边界为准，不能再让职责回流、回穿或重新耦合。

### 2.0 核心中心 / 引擎职责总表

#### 真相源类中心
1. `RuntimeCenter`
   - 运行态资源真相
   - session 实体真相
2. `ContextCenter`
   - session 上下文正文真相
3. `StaticAssetCenter`
   - 静态资产契约真相
4. `ConfigCenter`
   - bootstrap 配置真相

#### 执行 / 编排类核心
5. `MasterControl`
   - 复杂任务协调与业务编排中心
6. `ToolCallingEngine`
   - 唯一 tool call 执行中心

约束：
- 真相源类中心不能偷偷承担别的中心的真相职责
- 执行 / 编排类核心不能回退成新的数据真相源
- 命名必须稳定，后续文档与代码不再混用“资源中心/运行中心/资产中心”等模糊表述

### 2.1 边界总规则
所有中心 / 引擎一律遵守：
- 真相源只负责自己那一类状态和契约，不承担别的中心的数据真相
- 执行器只执行，不演化成新的配置中心或上下文真相源
- 编排器只决定怎么协调，不拥有运行态资源真相或上下文正文真相
- 任何跨中心读取都通过显式接口完成，不允许靠隐式共享内存语义偷穿边界

### 2.2 ToolCallingEngine
定位：唯一 tool call 执行层。

负责：
- 暴露 tool schema 给 LLM
- 执行被选中的 tool
- 将 tool 结果回流给 LLM

不负责：
- 维护资产目录真相
- 推导可见资产
- 维护 session tree
- 生成热工具定义
- 记录 session 正文

硬约束：
- `ToolDef.name == register_tool(name, handler) == hot tool name`
- 不允许出现第二套并列 tool executor

### 2.3 RuntimeCenter
定位：运行态资源与 session 实体的真相源。

负责：
- 资源注册 / 注销 / 查询 / 调用分发
- session 实体增删查改
- session 生命周期状态
- 运行态资产 / 动态资源真相

不负责：
- 存 session 对话正文
- 直接拼 prompt
- 维护 tool call schema
- 代替 ContextCenter 保存上下文正文

最重要边界：
- “会话对象是谁、当前状态是什么” 归 RuntimeCenter
- “这个会话里说过什么、沉淀了什么” 不归 RuntimeCenter

### 2.4 ContextCenter
定位：上下文正文与上下文查询真相源。

状态：当前仓库尚未正式落地独立 `ContextCenter` 类型。现阶段由 `LightBrainMemory`
作为过渡性适配体承接 session 上下文正文的持久化与读取。后续迁移时，必须把
session 实体真相与 context 正文真相拆回 `RuntimeCenter` / `ContextCenter`。

负责：
- session 对应的上下文记录
- 最近窗口读取
- 指定区间读取
- child session / linked session 的上下文检索
- context upload / append / read
- 用于模型的上下文查询能力

不负责：
- session 实体生命周期本体
- 资源注册真相
- tool handler 执行
- 业务调度本体

最重要边界：
- ContextCenter 保存和返回的是“交互所需正式上下文”
- 它不是日志中心，不承担完整运行流水回放

### 2.5 StaticAssetCenter
定位：静态资产契约真相源。

负责：
- 静态资产定义
- `default_hot_tools`
- `methods` / interface contract
- `default_visible_to`
- 静态资产元数据一致性校验

不负责：
- 运行态资源真相
- session 对话正文
- tool handler 执行
- 业务调度

最重要边界：
- 它定义“一个静态资产应该长什么样、默认暴露什么能力”
- 它不负责“当前运行时到底有哪些动态资源活着”

### 2.6 ConfigCenter
定位：bootstrap 配置真相源。

负责：
- 默认配置来源
- 默认模型 / 默认路由
- 系统第一次知道入口从哪里来

不负责：
- 运行态资源真相
- session 上下文正文
- 动态工具执行
- 任务编排

最重要边界：
- ConfigCenter 管的是启动与默认配置，不是运行中实时状态

### 2.7 MasterControl
定位：复杂任务协调与业务编排中心。

负责：
- 复杂任务分解与协调
- 跨 app / skill 的业务编排
- 需要下沉执行时继续调用统一 tool call 层和统一资产契约

不负责：
- session 实体真相
- session 正文真相
- 静态资产契约真相
- 第二套独立工具执行体系

最重要边界：
- MasterControl 是编排者，不是新的数据中心

### 2.8 HotToolManager
定位：工具名集合管理器。

状态：已按本章边界落地到当前实现。

负责：
- 维护 fixed tools / system tools / session-local hot tools 的工具名集合
- 返回当前调用应暴露哪些工具名

不负责：
- 生成新的 ToolDef
- 注册 handler
- 从 capability 推导新 tool name
- 维护资产目录真相

最重要边界：
- 它只是“本轮该暴露哪些工具名”的组装器，不是工具工厂

### 2.9 日志 vs 上下文
两者必须分层：

#### 日志
- 详细
- 分级
- 面向调试 / 审计 / 排障
- 可以记录 route、tool trace、错误细节

#### 上下文
- 面向交互使用
- 是正式文档
- 只保留后续交互理解需要的正式记录
- 不承担完整执行流水回放

硬约束：
- 日志不能直接冒充上下文
- 上下文不能被调试流水污染

### 2.10 Chapter 2 验收标准
本章真正落地后，应满足：
- 任意一个字段 / 状态都能明确回答“归哪个中心负责”
- 任意一个新需求都能判断“应该落在哪个中心，而不是新造第七个真相源”
- 后续代码改造不会再把 session 正文写回 RuntimeCenter
- 后续代码改造不会再把工具生成职责塞回 HotToolManager
- 后续代码改造不会再让 MasterControl 长成第二套执行平面

---

## 3. 统一调用契约（Chapter 3）

> 本章回答的是：模型到底通过什么统一入口调用能力，session_id 到底怎么解释，系统最终把结果写回哪里。
> 这一章是后续代码实现的接口宪法，不能模糊。

### 3.1 统一资产调用接口
资产操作统一走通用工具：
- `list_assets(filter)`
- `query_asset_info(asset_id)`
- `query_asset_detail(asset_id)`
- `call_asset_method(asset_id, method, params)`

状态：以上四个统一接口已在当前运行时注册，并作为固定系统工具暴露。

约束：
- 不允许为每个 asset capability 动态生成独立 tool name
- 不允许绕开统一入口直调资产方法
- 不允许在运行时再长出第二套路由专用调用协议

### 3.2 四个统一接口的职责分工
#### `list_assets`
用于：
- 查当前运行态可见的资产或资源
- 让模型知道“现在有哪些东西能用”

不用于：
- 读取资产的完整方法细节
- 直接执行资产方法

#### `query_asset_info`
用于：
- 获取资产的基础说明
- 帮助模型判断这个资产是不是它要的对象

不用于：
- 替代方法级 schema 查询
- 直接执行资产方法

#### `query_asset_detail`
用于：
- 获取更完整的方法细节、schema、调用约束
- 帮助模型构造 `call_asset_method` 的参数

不用于：
- 直接执行资产方法

#### `call_asset_method`
用于：
- 对指定资产执行指定方法
- 真正触发运行态动作

不用于：
- 发现资产列表
- 猜测资产能力

### 3.3 模型调用路径原则
模型的标准路径应是：
1. 若需要知道当前能用什么，先 `list_assets`
2. 若需要判断某个资产是否合适，再 `query_asset_info`
3. 若需要拿到方法级细节，再 `query_asset_detail`
4. 确认后统一走 `call_asset_method`

允许跳步：
- 如果模型已经明确知道目标资产和方法，可直接 `call_asset_method`
- 不强制每次都先 `list_assets -> query -> call`

### 3.4 session_id 统一契约
统一规则：
- `session_id` 非空 = 续约 / 复用
- `session_id` 为空 = 新建 child session

这条规则必须在以下层保持完全一致：
- 交互层 -> 主控
- 主控 -> app
- app -> skill

禁止：
- 某一层把空 `session_id` 当异常
- 某一层自行发明第三种语义
- 某一层要求自己的私有 session 参数协议

### 3.5 模型与系统的 session 权责边界
模型可以做的事：
- 传已有 `session_id`
- 传空 `session_id`
- 基于上下文和任务决定复用还是新建

系统必须做的事：
- 解析并 resolve 真实 session
- 必要时创建 child session
- 返回最终 `resolved_session_id`

模型不能做的事：
- 自己生成真实 session id
- 伪造未分配 session id
- 跳过系统 resolve 流程直接认定 session 已存在

### 3.6 resolved session 回写规则
模型传入的是“请求值”，系统产出的是“真实值”。

统一规则：
- 后续 upload 一律回写 **resolved session id**
- 绝不回写模型原始空值
- 绝不回写候选值或临时值
- 绝不因为上游传了已有 id 就跳过最终 resolve 校验

### 3.7 统一返回契约
所有关键调用至少应返回：
- `ok`
- `resolved_session_id`（如适用）
- `asset_id`
- `method`
- `result`
- `error`（失败时）

目的：
- 让上层模型和 after-hook 知道真正写回哪里
- 让 observability 能统一记录调用闭环

### 3.8 Chapter 3 验收标准
本章真正落地后，应满足：
- 代码里不再出现 capability -> 独立 tool name 的新增路径
- 任意资产调用都能落回这四个统一接口之一
- session_id 空值 / 非空规则在交互层、主控、app、skill 完全一致
- upload 回写目标永远来自 resolved session，而不是模型原始输入
- 不会再出现“发现协议一套、调用协议一套、回写协议再一套”的分裂

---

## 4. 交互层固定主路径（Chapter 4）

> 本章只解决一件事：用户消息进入系统后，交互层到底怎么走，模型拿到什么，模型自己决定什么，系统又负责兜哪些底。

### 4.1 交互层定位
交互层是统一入口判定层，不是新的业务主控。

它只负责：
- 接收用户消息
- 在一次 LLM 调用中做统一决策
- 必要时直答 / 本地起流水线 / 掉主控
- 将最终结果纳入统一上下文回写流程

它不负责：
- 预先替模型硬路由
- 预先把全量资产和全量上下文塞给模型
- 演化成第二套主控编排器

### 4.2 交互层初始输入
默认提供：
- 当前用户消息
- 当前 interaction session 最近 100 条记录
- 当前 `session_id`
- 通用资产调用工具：
  - `call_asset_method`
  - `query_asset_info`
  - `query_asset_detail`

约束：
- 默认不直接注入可见资产列表
- 默认不直接注入长历史
- 默认不直接把 root session 的全部内容下发给交互层
- `ContextCenter` / `RuntimeCenter` / `MasterControl` 等能力由模型在 tool call 过程中按需查询和调用

### 4.3 为什么只带最近 100 条
默认带最近 100 条的目的不是为了替代 ContextCenter，而是：
- 给模型一个足够小但足够有判断力的当前窗口
- 避免每次都先查询上下文
- 降低首轮决策延迟

如果最近 100 条不够，模型再通过 ContextCenter 自主扩查。

### 4.4 交互层一次决策输出协议
交互层一次 LLM 调用必须产出固定 schema：
- `mode`: `direct_reply` | `local_pipeline` | `dispatch_master_control`
- `reply_text`
- `target_session_id`（可为空）
- `session_decision`: `reuse_existing` | `fork_new`
- `reason_code`

硬约束：
- 模型不能自己生成真实 session id
- 模型只能选择“复用已有 id”或“空值表示新建”
- 如果要调主控或其他资产，请求组装由模型自己完成
- 系统不在 LLM 决策前额外插入第二套路由器

### 4.5 模型在交互层可做的事
模型可以在统一 tool call 层中自行决定：
- 直接回答
- 调 `ContextCenter` 查询上下文
- 调 `RuntimeCenter` 查询运行态资源或 session 信息
- 调 `MasterControl`
- 调下游 app / skill

这意味着：
- 路由由模型决定
- 系统负责能力暴露、执行和回写
- 不是系统先 if/else 再允许模型执行

### 4.6 交互层决策的推荐顺序
推荐顺序：
1. 先基于当前消息 + 最近 100 条判断能否直接答
2. 若上下文不足，再查当前 session 更早区间
3. 若仍不足，再查 linked session / child session
4. 若需要复杂编排，再调 `MasterControl`

说明：
- 这是推荐顺序，不是硬编码死流程
- 模型在非常明确的情况下可以跳步

### 4.7 系统兜底职责
虽然路由由模型决定，但系统仍必须兜住：
- tool call 执行
- session resolve
- resolved session 回写
- context upload after-hook
- 日志记录与观测
- query 上限 / tool loop 上限 / budget 保护

### 4.8 禁止回退的旧路径
以下旧路径在本章确认后不应继续存在：
- 交互层预带全量可见资产
- 交互层先硬路由，模型只做填空式调用
- 交互层默认继承整棵 root session 历史
- 再长出一个“轻主控 / 隐式主控”层

### 4.9 Chapter 4 验收标准
本章真正落地后，应满足：
- 用户消息进入后，交互层只有一次统一 LLM 决策入口
- 模型可以在首轮不查资产、不查长历史的情况下完成大部分简单决策
- 需要时再通过 ContextCenter / RuntimeCenter 扩查，而不是系统预塞
- 主控调用是模型主动选择，不是系统先验硬分流
- 交互层不会再次膨胀成新的编排中心

---

## 5. Session 与 Context 机制（Chapter 5）

> 本章回答：会话树怎么长，上下文正文放哪，哪些状态归 RuntimeCenter，哪些内容归 ContextCenter，以及如何防止上下文沿调用链无限膨胀。

### 5.1 Session Tree 模型
采用：
- `root session`
- `child session`
- `continuation child session`

目标：
- 控制多轮会话膨胀
- 已完成任务默认停止增长
- 新任务默认不继续拼进旧 child session
- 让主控 / app / skill 的上下文沿树状结构自然分层

### 5.2 Root Session
Root session 是用户层根会话。

职责：
- 挂住用户长期交互主线
- 提供最上层会话归属
- 不要求每次把 root 下所有历史直接灌给交互层

约束：
- root session 不是默认 prompt 垃圾桶
- root 存在不代表所有 child 都要继承它的全部正文

### 5.3 Child Session
Child session 用于承接特定阶段、特定 actor、特定 topic 的局部上下文。

适用：
- interaction 层的局部连续话题
- master_control 的协调子任务
- app / skill 的局部执行轨道

约束：
- child session 默认只带自己的局部正文窗口
- child 完成后默认进入不可继续自然增长状态

### 5.4 Continuation Child Session
当一个 child session 主题仍连续，但正文已过长时，允许 fork continuation child session。

目的：
- 保持主题连续
- 避免单个 child 无限增长
- 保持 relatedness 可续接而不是重开全新无关 session

### 5.5 Session 最小结构
- `root_session_id`
- `session_id`
- `parent_session_id`
- `kind` (`interaction` / `orchestration` / `app` / `skill`)
- `topic_key`
- `status`
- `created_at`
- `updated_at`

### 5.6 Session 状态机
至少支持：
- `active`
- `idle`
- `resolved`
- `archived`

建议语义：
- `active`: 正在参与当前工作流
- `idle`: 暂时未继续，但可恢复
- `resolved`: 当前任务已完成，默认不再自然续写
- `archived`: 归档，仅用于检索和审计参考

约束：
- `resolved` 默认不可续写
- 如需继续旧任务，应显式 reopen 或 fork continuation child session

### 5.7 SessionLink
必须记录上下游 session 映射。

最小字段：
- `parent_session_id`
- `child_session_id`
- `parent_actor`
- `child_actor`
- `topic_key`
- `status`
- `created_at`
- `updated_at`

目的：
- 支撑后续 relatedness 判断
- 支撑模型按 session id 续约正确下游 session
- 支撑 ContextCenter 查询 linked session 上下文

### 5.8 RuntimeCenter 与 ContextCenter 的分工
#### RuntimeCenter 管
- session 实体
- session 生命周期状态
- session 增删查改
- session 与运行态资源的关联

#### ContextCenter 管
- session 正文记录
- 最近窗口读取
- 指定区间读取
- linked session / child session 的上下文读取
- context upload / append / read

硬约束：
- RuntimeCenter 不保存对话正文真相
- ContextCenter 不接管 session 生命周期真相
- 两者通过显式 session id / link 关联，不共享隐式“混合 session 对象”

### 5.9 ContextCenter 查询能力
至少提供：
- `get_recent_context(session_id, limit)`
- `get_context_range(session_id, start, end)`
- `get_child_sessions(parent_session_id)`
- `get_linked_sessions(session_id)`
- `append_context_record(session_id, record)`

原则：
- 不压缩、不改写原文语义
- 模型如果需要更多上下文，应自行通过 ContextCenter 查询
- 查询能力是补充入口，不是默认把所有历史预灌给交互层

### 5.10 防膨胀规则
- 默认只给交互层最近 100 条
- 下游 actor 默认只继承当前 child session，而不是整棵 root history
- child session 过长时优先 continuation fork，而不是继续无限追加
- 已 resolved 的 session 默认不再自然增长
- 日志流水不进入正式上下文正文

### 5.11 Chapter 5 验收标准
本章真正落地后，应满足：
- 能清楚回答任意一条记录是“session 实体状态”还是“session 正文内容”
- 主控 / app / skill 不会再把上下文无限串在一个 session 里
- 上游能够记录下游 child session，并在下一轮正确续约
- ContextCenter 能按 session / 区间 / link 查询，而不是只会全量读
- 不再依赖摘要压缩来掩盖上下文膨胀问题

---

## 6. 静态资产 hot tools 与可见性（Chapter 6）

> 本章解决：静态资产需要声明什么，HotToolManager 到底还剩什么职责，可见资产如何暴露给模型，以及为什么不能重新回到 capability 级独立工具那条旧路。

### 6.1 静态资产配置最小要求
静态资产至少应声明：
- `default_hot_tools`
- `methods` / interface contract
- `default_visible_to`

说明：
- `default_hot_tools` 用于表达“这个资产默认最值得暴露哪些通用工具名”
- `methods` 用于表达“这个资产有哪些方法、参数 schema、调用说明”
- `default_visible_to` 用于表达“哪些 actor / session 默认能看到这个资产”

### 6.2 StaticAssetCenter 的职责边界
StaticAssetCenter 负责：
- 保存静态资产定义
- 保存 `default_hot_tools`
- 保存 `methods` / interface contract
- 保存 `default_visible_to`
- 对静态资产元数据做一致性校验

不负责：
- 维护运行时动态资源清单
- 直接组装 prompt
- 执行 tool handler
- 生成 capability 级独立工具

### 6.3 HotToolManager 的最终收口
HotToolManager 最终只负责：
- 维护 fixed tools / system tools / session-local hot tools 的工具名集合
- 返回当前调用应暴露哪些工具名

HotToolManager 不再负责：
- 生成新的 ToolDef
- 注册 handler
- 根据 capability 动态派生工具名
- 维护资产目录真相
- 替模型做资产发现

一句话：
- HotToolManager 是“工具名集合组装器”，不是“工具工厂”

### 6.4 可见资产原则
交互层初始不带可见资产列表。

模型如需知道当前可用资产，应通过：
- `RuntimeCenter`
- `StaticAssetCenter`
- `ContextCenter`

在 tool call 过程中查询得到，再决定下一步。

这意味着：
- 可见性是运行时查询结果
- 不是系统预塞给模型的静态大 prompt
- 资产发现是模型按需行为，不是系统默认铺满输入

### 6.5 工具暴露原则
工具暴露时：
- 不再把 asset capability 全部物化为独立工具
- 不再全局预热所有能力到 prompt
- 只暴露统一通用工具 + 当前调用真正需要的工具名集合

统一通用工具仍然是：
- `list_assets`
- `query_asset_info`
- `query_asset_detail`
- `call_asset_method`

### 6.6 为什么不能回到 capability 级独立工具
因为那条路会重新带来：
- 工具名爆炸
- handler 注册漂移
- ToolDef / register_tool / hot tool name 不一致
- 资产契约和运行态实现再次耦合
- HotToolManager 职责重新膨胀

因此，本章确认后：
- capability 可以存在于资产 contract 中
- 但不能再直接映射成新的独立 LLM tool 名

### 6.7 default_visible_to 的语义
`default_visible_to` 用于表达默认可见性，不表达最终唯一可见性。

也就是说：
- 它是静态默认策略
- 最终是否可见，仍要结合当前 session / actor / runtime state 判断

这样可以避免：
- 静态配置过死
- runtime 无法表达局部可见性

### 6.8 Chapter 6 验收标准
本章真正落地后，应满足：
- 静态资产 contract 能清楚表达默认热工具、方法 schema、默认可见性
- HotToolManager 不再回退成工具定义生成器
- 模型需要资产时，通过查询得到，而不是系统预塞满屏资产说明
- 不再出现 capability -> 独立 tool name 的新实现
- ToolCallingEngine / StaticAssetCenter / HotToolManager 三者职责不再交叉

---

## 7. Context upload、日志分层与风险护栏（Chapter 7）

> 本章解决三个横切问题：正式结果如何回写上下文，日志和上下文如何彻底分层，以及系统如何加最小护栏避免模型与工具环路失控。

### 7.1 Context upload 默认 after-hook
任何 actor 完成一次正式 turn 后，系统自动执行 context upload。

适用范围：
- interaction
- master_control
- app
- skill

目的：
- 避免各层忘记回写
- 统一上下文沉淀行为
- 保证上层和下层的记录格式一致

### 7.2 默认上传内容白名单
允许上传：
- 用户原始消息
- assistant 最终回复
- 最终 dispatch decision
- 最终结构化结果
- 极短的 system note

禁止默认上传：
- scratchpad
- chain-of-thought
- 全量 tool trace
- 中间失败尝试
- 长篇自由文本总结

原则：
- 上下文是给后续交互用的正式记录
- 不是把完整执行流水倒进去的容器

### 7.3 system note 规范
system note 只能作为结构化附加索引，不替代原始消息。

建议最小字段：
- `type`
- `actor`
- `resolved_session_id`
- `decision`
- `outcome`
- `pending`

约束：
- system note 要短
- system note 不能替代原文
- system note 不能扩写成长篇总结型上下文污染

### 7.4 日志与上下文分层
#### 日志
- 详细
- 分级
- 面向调试 / 审计 / 排障
- 可以记录 route、tool trace、错误细节

#### 上下文
- 面向交互使用
- 是正式文档
- 只保留后续交互理解需要的正式记录
- 不承担完整执行流水回放

硬约束：
- 日志不能直接冒充上下文
- 上下文不能被调试流水污染
- 想看完整执行链就查日志，不是查 ContextCenter 正文

### 7.5 最小护栏一：上下文查询限制
必须有：
- 每轮 ContextCenter 查询次数上限
- 默认查询顺序：当前窗口 -> 当前 session 更早区间 -> linked session
- 禁止无界全量读取

目的：
- 防止模型因可查上下文而无限扩查
- 防止本地成本被上下文检索环路拖爆

### 7.6 最小护栏二：tool loop 与预算限制
必须有：
- 每轮 tool loop 上限
- 每轮 context query 次数上限
- per-turn budget
- timeout / bailout 策略

目的：
- 防止模型在“查上下文 -> 调资产 -> 再查上下文”中局部失控
- 防止复杂任务把一次 turn 拖成无界执行

### 7.7 最小护栏三：observability
至少记录：
- incoming message id
- selected actor
- requested session_id
- resolved session_id
- reused or forked
- upload target
- selected asset / method

作用：
- 解释为什么这次走了这个路由
- 解释为什么写回到了这个 session
- 解释为什么模型决定继续查上下文或调主控

### 7.8 最小护栏四：contract lint
必须有：
- 统一资产调用接口校验
- tool / asset / hot tool 配置一致性校验
- 禁止 capability -> 独立 tool name 回退
- 禁止 RuntimeCenter / ContextCenter 职责回流

作用：
- 把“文档规则”变成可检查约束
- 防止后续代码在局部 patch 里悄悄回退

### 7.9 Chapter 7 验收标准
本章真正落地后，应满足：
- 任何正式 turn 结束后，都能自动生成一致的上下文沉淀
- 查询完整执行链需要看日志，而不是污染上下文正文
- 上下文查询、tool loop、预算都有最小护栏
- 出问题时能从 observability 里看出 route / session / upload 决策
- 新代码不能轻易把已收敛的契约和边界再打散

---

## 8. 实施顺序与验收闭环（Chapter 8）

> 前 7 章解决的是“应该怎么设计”，本章解决的是“接下来到底先做什么、后做什么、每一步怎么验收、做到哪里算真正完成”。

### 8.1 实施总顺序
必须按以下顺序推进，避免边改边打散：

1. 先收契约
2. 再收中心边界
3. 再改交互主路径
4. 再打通 session / context 机制
5. 再收静态资产与 hot tools
6. 再补 upload / 日志 / 风险护栏
7. 最后做真实链路验证

原因：
- 契约不稳时先改运行态，只会让代码更乱
- 中心边界未收清时先加能力，只会重新耦合
- 主路径不稳时先跑验证，结果不具参考价值

### 8.2 对应章节到实施阶段的映射
#### Phase A，契约与边界
对应：
- Chapter 1
- Chapter 2
- Chapter 3

目标：
- 统一总原则
- 统一真相源边界
- 统一调用契约

#### Phase B，交互与会话主路径
对应：
- Chapter 4
- Chapter 5

目标：
- 固定交互层一次 LLM 决策主路径
- 固定 Session Tree / ContextCenter 机制

#### Phase C，资产暴露与运行期收口
对应：
- Chapter 6
- Chapter 7

目标：
- 收掉 capability 级独立工具旧路
- 收掉日志/上下文混流
- 补齐护栏和观测

#### Phase D，验收闭环
对应：
- 本章

目标：
- 按统一标准验证主路径是否真实跑通

### 8.3 逐文件改造优先级
#### 第一批，先改最容易继续长歪的文件
- `app/bootstrap/runtime.py`
- `app/services/hot_tool_manager.py`
- `app/ai/tool_calling_engine.py`

状态：已部分完成。
- `app/services/hot_tool_manager.py` 已收口为工具名集合管理器
- 统一资产工具注册已固定到 `list_assets / query_asset_info / query_asset_detail / call_asset_method`
- `session_id` 空值=新建、非空=续约 已落到交互入口与请求模型

目标：
- 收掉旧 capability -> tool name 逻辑
- 固定统一资产工具注册
- 固定 ToolCallingEngine 单层执行事实

#### 第二批，再改会话与上下文骨架
- `runtime_center.py`（或实际 RuntimeCenter 落点）
- `app/services/context_center.py`（新增，最小骨架已落地）
- `app/models/context.py`（新增，最小骨架已落地）

目标：
- 明确 session 实体与上下文正文分层
- 增加 SessionLink / 状态机 / 查询骨架

#### 第三批，改交互主路径
- `app/system/gateway/light_brain_gateway.py`
- `app/system/gateway/tool_calling_interpreter.py`

状态：已开始落地。
- `LightBrainGateway` 已支持可选 `ContextCenter` 注入
- 当前 active path 已镜像写入 user / assistant 最近窗口到 `ContextCenter`
- `command.context` 已可携带最近 session context 窗口，后续继续替换旧读取路径

目标：
- 固定当前消息 + 当前 session + 最近 100 条窗口
- 固定模型按需查询上下文 / 资源 / 主控
- 不再预带可见资产列表

#### 第四批，打通主控 / app / skill 统一 session 契约
- master_control 入口
- app 调用入口
- skill 调用入口

目标：
- 空 session_id = 新建
- 非空 session_id = 续约
- resolved session id 统一回传

#### 第五批，补 after-hook 与护栏
- context upload 落点
- observability 落点
- contract lint 落点

目标：
- 自动回写
- 观测可查
- 回退可拦

### 8.4 每一批的验收点
#### 第一批验收
- 代码里不再新增 capability -> 独立 tool name
- ToolCallingEngine / HotToolManager 职责不再交叉

#### 第二批验收
- session 实体状态和 session 正文内容可以清晰分开
- ContextCenter 能按 session / range / link 查询

#### 第三批验收
- 交互层首轮不预带可见资产
- 交互层只走一次统一 LLM 决策

#### 第四批验收
- 主控 / app / skill 的 session 契约完全一致
- resolved session id 能贯穿回写

#### 第五批验收
- 正式结果自动回写
- 日志与上下文不混流
- query / loop / budget 护栏生效

### 8.5 真实链路验证清单
至少验证：
1. 交互层直接答复路径
2. 交互层查上下文再答复路径
3. 交互层调主控并自动创建 child session 路径
4. 主控 -> app -> skill 统一 session 契约路径
5. context upload 回写正确性
6. observability 能还原 route / session / upload 决策

### 8.6 完成定义
只有同时满足以下条件，才算 Phase H 这一轮真正完成：
- 文档规则已经落到代码，不只是文字说明
- 单一 ToolCallingEngine 执行层已经在代码中成立
- RuntimeCenter / ContextCenter / StaticAssetCenter / ConfigCenter 边界在代码中成立
- 交互层主路径已切换到新模型
- Session Tree / ContextCenter / SessionLink 已能支撑真实链路
- upload / 日志 / 护栏已生效
- 真实链路验证通过并有记录

### 8.7 Chapter 8 验收标准
本章真正落地后，应满足：
- 团队无需再猜“下一步先改什么”
- 任一章节都能映射到具体改造批次和文件落点
- 验收点与章节定义一致，不会出现“文档一套，实施顺序另一套”
- Phase H 可以从讨论稿进入真正的落地执行状态

---

## 9. 严格评审结论

Verdict: sound-with-gaps

Good:
- 单一 ToolCallingEngine + 统一资产调用接口，明显降低工具层耦合与命名漂移
- RuntimeCenter / ContextCenter 分层后，session 实体与上下文正文边界清晰
- 交互层不预带可见资产，改为模型按需查询，更符合统一能力暴露原则
- 空 `session_id` 表示新建、非空表示续约，这条契约足够统一，能从交互层贯穿到 skill
- 日志与上下文分层后，可同时兼顾调试能力与交互保真

Gaps / Risks:
- 交互层 decision schema、upload 白名单、session 生命周期如果不尽快落成硬约束，后续实现仍会漂移
- ContextCenter 容易继续被塞入额外职责，必须严格守边界
- 模型驱动路由虽然统一，但必须配合 prompt policy、query 限额和 observability 一起落，不然局部成本会失控

Recommendation:
- 先完成契约收敛和中心分层，再动交互层主路径
- 不再继续保留旧 capability 预热逻辑
- 不再新增系统先验硬路由逻辑
- observability 与 contract lint 必须同步上，不要后补

Execution decision:
- continue
