# 光脑架构设计 (Light Brain Architecture)

> 灵感来源：《吞噬星空》中的光脑——每个人的个人智能终端。
> 一个统一的、有状态的、以 App 为功能模块的智能操作系统。
> 用户用自然语言下达指令，光脑自动理解、调度 App、返回结果。

---

## 1. 光脑的核心隐喻

### 1.1 什么是光脑？

在《吞噬星空》中，光脑是每个人的**个人智能终端**：
- 一个统一的交互界面（全息投影/虚拟屏幕）
- 功能以 App 形式组织（通讯、导航、战斗辅助、资料查询...）
- 每个 App 独立运行、数据隔离、状态持久
- 用户用自然语言下达指令，光脑自动调度
- 关机后再开机，所有 App 和数据都在原来的状态

### 1.2 光脑 → AgentSystem 的映射

| 光脑概念 | AgentSystem 对应 | 说明 |
|---------|------------------|------|
| 光脑本体 | AgentSystem 运行时 | 统一的、有状态的系统 |
| 全息界面 | LLM 交互层 (/chat/*) | 自然语言对话入口 |
| 光脑 App | App Instance | 功能模块，持久化运行 |
| App 数据 | App Data Namespace | 每个 App 独立的存储空间 |
| App 状态 | App Shared Context | 运行上下文，跨重启保留 |
| 语音指令 | 用户自然语言消息 | "帮我建个监控 App" |
| 光脑理解 | Conversation Router | LLM 意图识别 |
| 光脑调度 | Workflow Engine | 将指令转为工作流执行 |
| 功能模块库 | Skill Registry | 可复用的能力单元 |
| 光脑记忆 | Runtime Persistence | 一切状态持久化 |

---

## 2. 光脑交互范式

### 2.1 用户看到的"光脑"

用户打开光脑（进入对话界面），看到的是：

```
┌─────────────────────────────────────┐
│  💠 AgentSystem 光脑                 │
│  运行中 · 3 个 App 在线              │
├─────────────────────────────────────┤
│                                     │
│  📱 已安装的 App                     │
│  ┌──────────┐ ┌──────────┐          │
│  │ 📊 数据   │ │ 🔍 监控   │          │
│  │ 运行中    │ │ 已暂停    │          │
│  └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐          │
│  │ 📝 日报   │ │ ➕ 新建   │          │
│  │ 已停止    │ │ App      │          │
│  └──────────┘ └──────────┘          │
│                                     │
│  💬 对我说点什么...                  │
│  "启动监控" "帮我建个翻译 App"       │
│  "看看日报今天完成了什么"            │
│                                     │
└─────────────────────────────────────┘
```

### 2.2 典型对话流

#### 场景 A：创建新 App

```
用户: 帮我建一个数据监控 App，每小时检查一次服务器状态，
     如果发现 CPU 超过 80% 就通知我

光脑: 好的，我来帮你设计这个监控 App：

     📋 App 概要
     名称: 服务器监控
     类型: 服务型 App（持续运行）
     执行频率: 每小时
     触发条件: CPU > 80%
     通知方式: 系统消息
     
     需要以下能力模块：
     ✓ 系统状态查询 (system.health_check)
     ✓ 阈值判断 (condition.threshold)
     ✓ 消息通知 (notification.alert)
     
     要我现在创建并启动吗？
     [✅ 创建并启动] [✏️ 修改配置] [❌ 取消]
```

#### 场景 B：管理已有 App

```
用户: 看看我有哪些 App 在跑

光脑: 你目前有 3 个 App：

     🟢 服务器监控 — 运行中
        下次检查: 14:00 | 已运行 6 小时
        最近告警: 无

     🟡 日报生成器 — 已暂停
        上次运行: 昨天 18:00
        [▶️ 恢复] [📊 查看报告] [⚙️ 设置]

     🔴 数据转换器 — 已停止
        最后状态: 完成 | 处理 1200 条记录
        [▶️ 重新运行] [📋 查看结果] [🗑️ 删除]

     需要我做什么？
```

#### 场景 C：对话式操作

```
用户: 把日报生成器改成每天早上 9 点发给我

光脑: 已更新 日报生成器 的配置：
     
     📅 新调度: 每天 09:00
     📤 推送方式: 系统消息
     📊 内容范围: 全天数据
     
     要我现在测试运行一次吗？
     [▶️ 测试运行] [✅ 就这样] [↩️ 改回去]
```

#### 场景 D：查询 App 内部状态

```
用户: 服务器监控今天有发现什么异常吗？

光脑: 📊 服务器监控 — 今日报告

     检查次数: 12 次
     异常次数: 2 次
     
     ⚠️ 09:00 — CPU 峰值 85.3%
         服务器: prod-web-01
         持续: 3 分钟
         状态: 已自动恢复
     
     ⚠️ 14:00 — 内存使用率 91%
         服务器: prod-db-01
         持续: 12 分钟
         状态: 已通知管理员
     
     需要我查看详细信息或调整告警阈值吗？
     [📋 详细日志] [⚙️ 调整阈值] [📧 导出报告]
```

---

## 3. 光脑核心架构

### 3.1 系统分层

```
┌─────────────────────────────────────────────────────┐
│                   光脑交互层                          │
│              (用户看到的"全息界面")                    │
│                                                      │
│  LLMInteractionGateway    ResponseSerializer         │
│  ConversationRouter       ConversationSession        │
│  CommandInterpreter       ActionDispatcher            │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│                   工作流编排层                         │
│            (光脑的"自动调度"能力)                      │
│                                                      │
│  WorkflowEngine          WorkflowCompiler            │
│  StepExecutor            StateMachine                │
│  ErrorRecovery           RetryPolicy                 │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│                   App 管理层                           │
│          (光脑的"功能模块"管理)                        │
│                                                      │
│  AppRegistry             AppInstaller                │
│  AppLifecycleManager     AppRuntimeHost              │
│  AppScheduler            AppSupervisor               │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│                   能力层                               │
│            (光脑的"技能库")                            │
│                                                      │
│  SkillRegistry           SkillValidator              │
│  SkillRuntime            SkillFactory                │
│  SystemSkills            GeneratedSkills             │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│                   持久化层                             │
│            (光脑的"记忆")                              │
│                                                      │
│  RuntimeStateStore       AppDataStore                │
│  AppContextStore         ExperienceStore             │
│  EventLog                UpgradeEvidence             │
└─────────────────────────────────────────────────────┘
```

### 3.2 光脑的核心组件设计

#### 3.2.1 光脑网关 (LightBrainGateway)

```python
class LightBrainGateway:
    """
    光脑的统一入口——用户的"全息界面"。
    
    职责:
    - 接收用户的自然语言消息
    - 管理对话会话（上下文连续性）
    - 调用光脑理解器解析意图
    - 分发到对应的工作流或 App 操作
    - 序列化为富交互回复（卡片/按钮/列表）
    """
    
    async def process_message(
        self,
        user_id: str,
        channel: str,
        message: str,
        attachments: list[str] | None = None,
    ) -> LightBrainResponse:
        ...
    
    async def stream_message(
        self,
        user_id: str,
        channel: str,
        message: str,
    ) -> AsyncIterator[StreamChunk]:
        ...
    
    async def execute_action(
        self,
        user_id: str,
        session_id: str,
        action_id: str,
        action_params: dict | None = None,
    ) -> LightBrainResponse:
        """执行用户点击的按钮/选项"""
        ...
    
    async def get_session_state(
        self,
        user_id: str,
        session_id: str,
    ) -> SessionState:
        """获取当前会话状态（App 列表、上下文等）"""
        ...
```

#### 3.2.2 光脑理解器 (LightBrainInterpreter)

```python
class LightBrainInterpreter:
    """
    光脑的"理解力"——把自然语言转为结构化指令。
    
    用户说: "帮我建个监控 App"
    输出:   Command(intent="create_app", params={...})
    
    用户说: "启动日报"
    输出:   Command(intent="start_app", params={"app_name": "日报"})
    """
    
    async def interpret(
        self,
        user_message: str,
        session_context: SessionContext,
        available_apps: list[AppSummary],
        system_state: SystemState,
    ) -> InterpretedCommand:
        ...


class InterpretedCommand(BaseModel):
    """解析后的结构化指令"""
    intent: str  # create_app | start_app | stop_app | query_app | query_status | modify_app | ...
    confidence: float
    target_app: str | None  # 目标 App 名称或 ID
    parameters: dict  # 提取的结构化参数
    requires_clarification: bool
    clarification_question: str | None
    suggested_actions: list[ActionSuggestion]
    raw_interpretation: str  # LLM 的原始推理过程（用于调试）


class ActionSuggestion(BaseModel):
    """用户可执行的下一步操作"""
    id: str
    label: str  # 按钮文字
    icon: str | None
    action_type: str  # "confirm" | "modify" | "cancel" | "navigate" | "execute"
    payload: dict  # 传递给 execute_action 的参数
    style: str = "primary"  # primary | secondary | danger | ghost
```

#### 3.2.3 工作流执行器 (WorkflowEngine)

```python
class WorkflowEngine:
    """
    光脑的"自动调度"能力。
    
    用户命令 → 工作流 → 具体操作
    
    例如 "创建并启动监控 App" 会生成一个工作流:
    1. create_app(blueprint)
    2. install_app(app_id)
    3. start_app(app_id)
    4. verify_app_health(app_id)
    5. return result
    """
    
    async def execute_command(
        self,
        command: InterpretedCommand,
        user_id: str,
        session_id: str,
    ) -> WorkflowResult:
        """将用户指令转为工作流执行"""
        ...
    
    async def build_workflow(
        self,
        intent: str,
        parameters: dict,
        context: WorkflowContext,
    ) -> WorkflowPlan:
        """根据意图构建工作流计划"""
        ...


class WorkflowPlan(BaseModel):
    """工作流执行计划"""
    steps: list[WorkflowStep]
    rollback_plan: list[RollbackStep]
    estimated_duration: str
    risk_level: str  # low | medium | high


class WorkflowStep(BaseModel):
    step_id: str
    action: str  # 操作名称
    target: str  # 目标对象
    inputs: dict
    depends_on: list[str]  # 依赖的步骤 ID
    on_failure: str  # abort | retry | skip | ask_user
```

#### 3.2.4 光脑记忆 (LightBrainMemory)

```python
class LightBrainMemory:
    """
    光脑的"记忆"——所有状态持久化。
    
    光脑关机再开机，一切如初（但数据还在）。
    """
    
    # 持久化的内容:
    # - 所有 App 的定义和状态
    # - 所有 App 的数据和配置
    # - 所有 App 的执行上下文
    # - 对话会话历史（压缩后）
    # - 用户偏好和习惯
    # - 经验记录（从运行实践中学习）
    # - 技能库和版本
    
    # 不需要持久化的:
    # - 临时运行时状态（心跳、租约等）
    # - 未保存的用户输入草稿
    # - 流式输出的中间状态
    
    async def restore_state(self) -> LightBrainState:
        """恢复光脑的完整状态"""
        ...
    
    async def persist_state(self, state: LightBrainState):
        """持久化当前状态"""
        ...


class LightBrainState(BaseModel):
    """光脑完整状态快照"""
    apps: list[AppState]  # 所有 App 的完整状态
    skills: list[SkillState]  # 所有技能的状态
    sessions: list[SessionSummary]  # 活跃的对话会话
    user_preferences: dict  # 用户偏好
    system_config: dict  # 系统配置
    last_updated: datetime
```

---

## 4. App 的生命周期（光脑视角）

### 4.1 App 状态机

```
                    创建
     [新建] ──────────────────> [草稿]
                                  │
                     验证通过       │
                        ↓          │
     [运行中] <─── 启动 ─── [已安装]
        │                          │
        │ 暂停                      │ 停止
        ↓                          ↓
     [已暂停]                   [已停止]
        │                          │
        │ 恢复                      │ 重新启动
        ↓                          ↓
     [运行中]                   [运行中]
        │
        │ 出错
        ↓
     [故障] ──── 自动恢复 ───> [运行中]
        │
        │ 修复
        ↓
     [运行中]

删除: 任何状态 → [已删除]
```

### 4.2 App 的持久化模型

```python
class AppPersistentState(BaseModel):
    """
    App 的持久化状态——关机不丢。
    """
    app_id: str
    app_name: str
    blueprint_id: str
    status: str  # draft | installed | running | paused | stopped | error
    
    # 配置（用户可修改）
    config: dict
    schedule: ScheduleConfig | None
    runtime_policy: RuntimePolicy
    
    # 数据（App 自己管理的）
    data_namespace: str
    data_summary: dict | None  # 数据摘要，不加载具体内容
    
    # 执行上下文（App 内部的工作记忆）
    shared_context: AppContext | None
    
    # 运行时信息（持久化但可重建的）
    installed_at: datetime
    started_at: datetime | None
    last_run_at: datetime | None
    last_result: dict | None
    
    # 统计信息
    total_runs: int
    total_errors: int
    avg_duration: str | None


class ScheduleConfig(BaseModel):
    """调度配置"""
    type: str  # "interval" | "cron" | "event"
    interval_seconds: int | None
    cron_expression: str | None
    event_type: str | None
    enabled: bool = True
    next_run_at: datetime | None
```

---

## 5. 工作流设计

### 5.1 内置工作流模板

光脑内置一批常用工作流，覆盖用户最常见的操作：

| 工作流 | 触发意图 | 步骤 |
|-------|---------|------|
| `create_app` | create_app | 理解需求 → 生成蓝图 → 创建技能 → 组装蓝图 → 安装 → 验证 |
| `start_app` | start_app | 查找 App → 检查依赖 → 启动 → 验证健康 → 返回状态 |
| `stop_app` | stop_app | 查找 App → 优雅停止 → 保存状态 → 确认 |
| `pause_app` | pause_app | 查找 App → 暂停调度 → 保存检查点 → 确认 |
| `resume_app` | resume_app | 查找 App → 恢复调度 → 从检查点继续 → 确认 |
| `modify_app` | modify_app | 查找 App → 解析修改 → 更新配置 → 重新验证 → 确认 |
| `query_app` | query_app | 查找 App → 收集状态 → 收集数据摘要 → 格式化回复 |
| `query_status` | query_status | 收集系统状态 → 收集 App 列表 → 收集技能状态 → 格式化 |
| `delete_app` | delete_app | 查找 App → 停止运行 → 删除数据 → 删除定义 → 确认 |
| `list_apps` | list_apps | 查询所有 App → 按状态分组 → 格式化卡片回复 |

### 5.2 工作流示例：创建 App

```
用户: "帮我建个监控 App，每小时检查服务器状态"

Workflow: create_app
  Step 1: interpret_requirements
    输入: 用户消息 + 会话上下文
    输出: {
      "app_type": "monitor",
      "name": "服务器监控",
      "schedule": {"type": "interval", "seconds": 3600},
      "actions": ["check_server_health"],
      "conditions": {"cpu_threshold": 80},
      "notifications": ["system_message"]
    }
  
  Step 2: generate_blueprint (meta-app orchestrator)
    输入: 结构化需求
    输出: AppBlueprint {
      "goal": "监控服务器状态并在异常时告警",
      "skills": ["system.health_check", "condition.threshold", "notification.alert"],
      "workflow": [...],
      "runtime_policy": {...}
    }
  
  Step 3: create_skills (如果需要新技能)
    输入: Blueprint 中的技能列表
    输出: 已注册的技能 ID 列表
  
  Step 4: assemble_blueprint
    输入: Blueprint + 技能 ID
    输出: 组装后的完整 Blueprint
  
  Step 5: install_app
    输入: Blueprint
    输出: AppInstance { app_id: "app-server-monitor-001", ... }
  
  Step 6: verify_health
    输入: AppInstance
    输出: { "status": "healthy", "message": "App 安装成功，等待调度触发" }
  
  Step 7: format_response
    输入: 工作流结果
    输出: LightBrainResponse (富交互卡片)
```

---

## 6. 回复格式设计

### 6.1 回复类型

```python
class LightBrainResponse(BaseModel):
    """光脑的标准回复"""
    type: str  # text | card | list | form | confirm | progress | error
    content: str  # 主文本内容
    data: dict | None  # 结构化数据
    
    # 交互元素
    actions: list[ActionSuggestion]  # 可点击的按钮/选项
    inline_items: list[InlineItem] | None  # 内嵌列表项
    
    # 上下文
    session_id: str
    related_app: str | None
    requires_input: bool  # 是否需要用户进一步输入


class InlineItem(BaseModel):
    """内嵌列表项（用于 App 卡片列表等）"""
    id: str
    title: str
    subtitle: str | None
    status: str  # running | paused | stopped | error | draft
    status_icon: str  # 🟢 | 🟡 | 🔴 | ⚪
    metadata: dict | None
    actions: list[ActionSuggestion]
```

### 6.2 回复模板

```python
# App 列表回复
LIGHTBRAIN_RESPONSE_TEMPLATES = {
    "app_list": {
        "type": "list",
        "content": "你目前有 {total} 个 App：",
        "items": "{app_cards}",  # 每个 App 一张卡片
        "actions": [
            {"id": "create_new", "label": "➕ 新建 App", "action_type": "navigate"},
            {"id": "help", "label": "❓ 帮助", "action_type": "help"},
        ]
    },
    
    "app_status": {
        "type": "card",
        "content": "{app_name} — {status_text}",
        "data": "{app_details}",
        "actions": "{contextual_actions}"  # 根据 App 状态动态生成
    },
    
    "create_confirm": {
        "type": "confirm",
        "content": "好的，我来帮你创建这个 App：\n\n{app_summary}",
        "actions": [
            {"id": "confirm_create", "label": "✅ 创建并启动", "style": "primary"},
            {"id": "modify", "label": "✏️ 修改配置", "style": "secondary"},
            {"id": "cancel", "label": "❌ 取消", "style": "ghost"},
        ]
    },
    
    "progress": {
        "type": "progress",
        "content": "{progress_text}",
        "data": {"current_step": N, "total_steps": M, "step_name": "..."},
    },
}
```

---

## 7. 接下来做什么（开发路线图）

### Phase 8.1：光脑网关骨架（~3 天）

**目标**: 能跑通"对话 → 回复"的基本循环

```
需要创建的文件:
├── app/services/light_brain_gateway.py       # 光脑网关主入口
├── app/services/light_brain_interpreter.py    # 意图解析器
├── app/services/light_brain_memory.py         # 持久化记忆
├── app/models/light_brain.py                  # 数据模型
├── app/api/chat.py                            # /chat/* 路由
└── app/models/chat.py                         # 请求/响应模型
```

**具体任务**:
1. 定义 `LightBrainResponse`、`ActionSuggestion`、`InlineItem` 模型
2. 实现 `LightBrainGateway.process_message()` 骨架
3. 实现基于规则的意图识别（先用 rule-based，LLM 后续接入）
4. 实现 `ConversationSession` 会话管理
5. 注册 `/chat/message` 端点
6. 写 3 个集成测试：文本回复、App 列表查询、简单操作

**验收标准**:
- `POST /chat/message` 返回结构化回复
- 对话上下文能在同一 session 中保持
- 返回包含可操作按钮的回复

### Phase 8.2：工作流引擎集成（~3 天）

**目标**: 对话能真正操作 App（创建/启动/停止/查询）

```
需要创建/修改的文件:
├── app/services/workflow_engine.py            # 工作流执行器
├── app/services/workflow_planner.py           # 工作流规划
├── app/services/light_brain_interpreter.py    # 增强：参数提取
└── tests/unit/test_workflow_engine.py
```

**具体任务**:
1. 实现 `WorkflowEngine.execute_command()`
2. 内置 5 个核心工作流模板（create/start/stop/query/list）
3. `LightBrainInterpreter` 接入现有 `MetaAppCreationOrchestrator`
4. 工作流执行结果转为 `LightBrainResponse`
5. 写 5 个集成测试：创建 App、启动、停止、查询状态、列出所有

**验收标准**:
- 用户说"创建 XX App"→ 实际创建并安装
- 用户说"启动 XX"→ 实际启动
- 用户说"看看我的 App"→ 返回列表卡片

### Phase 8.3：LLM 意图理解（~2 天）

**目标**: 从 rule-based 升级为 LLM 驱动

```
需要创建/修改的文件:
├── app/services/llm_intent_parser.py          # LLM 意图解析
├── app/services/light_brain_interpreter.py    # 增强：LLM 模式
└── tests/unit/test_llm_intent_parser.py
```

**具体任务**:
1. 实现 LLM 意图解析（接入现有 `model_client.py`）
2. 设计 prompt 模板（意图分类 + 参数提取）
3. 降级策略：LLM 不可用时退回 rule-based
4. 会话上下文注入到 LLM prompt
5. 写 3 个测试：LLM 解析、降级、上下文注入

### Phase 8.4：富交互体验（~2 天）

**目标**: 卡片/按钮/列表/进度条

```
需要创建/修改的文件:
├── app/services/response_serializer.py        # 增强：富交互格式
├── app/services/light_brain_gateway.py        # 增强：action 执行
└── tests/unit/test_response_serializer.py
```

**具体任务**:
1. 实现完整的 `ResponseSerializer`
2. App 列表回复（多卡片布局）
3. App 详情回复（卡片 + 操作按钮）
4. 创建确认回复（确认卡片）
5. 进度回复（流式进度更新）
6. 用户点击按钮 → 执行对应 action

### Phase 8.5：持久化与恢复（~2 天）

**目标**: 重启后状态不丢失

```
需要创建/修改的文件:
├── app/services/light_brain_memory.py         # 完整实现
├── app/bootstrap/runtime.py                   # 注入光脑服务
└── tests/unit/test_light_brain_memory.py
```

**具体任务**:
1. 实现 `LightBrainMemory` 完整持久化
2. App 状态自动保存
3. 对话会话持久化
4. 系统重启后恢复所有状态
5. 写 3 个测试：保存/恢复/重启

### Phase 8.6：多通道接入（~2 天）

**目标**: 支持 QQBot/WebChat 多通道

```
需要创建/修改的文件:
├── app/services/channel_adapters/qqbot.py     # QQBot 适配器
├── app/services/channel_adapters/webchat.py   # WebChat 适配器
└── tests/unit/test_channel_adapters.py
```

**具体任务**:
1. QQBot 通道适配（消息格式转换）
2. WebChat 通道适配
3. 按钮/卡片在不同通道的渲染适配
4. 写 2 个集成测试

---

## 8. 总览：光脑开发路线图

```
Phase 8.1  光脑骨架       ████████░░  ~3天  对话→回复基本循环
Phase 8.2  工作流集成     ░░░░░░░░░░  ~3天  真正操作 App
Phase 8.3  LLM 理解       ░░░░░░░░░░  ~2天  自然语言深度理解
Phase 8.4  富交互体验     ░░░░░░░░░░  ~2天  卡片/按钮/进度
Phase 8.5  持久化恢复     ░░░░░░░░░░  ~2天  重启状态不丢
Phase 8.6  多通道接入     ░░░░░░░░░░  ~2天  QQBot/WebChat

总工期: ~14 天
```

### 里程碑

| 里程碑 | 时间 | 用户能看到什么 |
|-------|------|---------------|
| M1: 能对话 | Day 3 | "你好" → 回复；"看看 App" → 列表 |
| M2: 能操作 | Day 6 | "创建 XX" → 真的创建；"启动" → 真的启动 |
| M3: 能理解 | Day 8 | "帮我搞个监控的" → 自动推断需求 |
| M4: 好看 | Day 10 | 卡片、按钮、进度条、确认对话框 |
| M5: 不忘 | Day 12 | 重启后所有 App 状态恢复 |
| M6: 多渠道 | Day 14 | QQBot 也能用光脑 |

---

## 9. 光脑 vs 传统操作系统的差异

| 维度 | 传统 OS | 光脑 (AgentSystem) |
|------|---------|-------------------|
| 交互方式 | 鼠标/键盘/触屏 | 自然语言对话 |
| App 启动 | 点击图标 | 说"启动 XX" |
| App 配置 | 设置面板 | 说"改成 XX 样子" |
| 文件管理 | 文件夹浏览 | 说"看看 XX 的数据" |
| 权限管理 | 权限弹窗 | 光脑自动判断是否安全 |
| 多任务 | 任务管理器 | 说"看看哪些在跑" |
| 故障处理 | 错误码/日志 | 光脑自动诊断+建议 |
| 学习成本 | 需要了解 UI | 会说话就会用 |

---

## 10. 设计原则

1. **用户只说人话** —— 不需要记命令、API、参数
2. **光脑主动思考** —— 自动推断、建议、确认
3. **App 自己管理** —— 每个 App 隔离运行、状态持久
4. **一切可恢复** —— 关机重启，状态如初
5. **安全可控** —— 重要操作需确认，危险操作需授权
6. **渐进式智能** —— rule-based → LLM-assisted → 自动化
