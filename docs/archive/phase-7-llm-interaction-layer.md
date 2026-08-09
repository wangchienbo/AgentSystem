# Phase 7: LLM-Powered Interaction Layer (用户交互层)

## 1. 目标

让 AgentSystem 从一个"强大的 API 集合"变成"一个能用的产品"：
- 用户用自然语言与系统对话
- LLM 理解意图并路由到正确的子系统
- 执行与对话严格分离
- 支持按钮、卡片、列表等富交互界面
- 所有交互通过主控（master control）进行

### 与核心架构的关系

LLM 交互层是**有状态持久化 App OS** 的用户入口：
- 用户命令通过对话层转化为工作流，工作流负责启动、停止、修改和管理 App
- App 是功能模块的隔离边界（光脑模型），每个 App 有独立的数据、上下文和生命周期
- 对话层不负责直接操作 App 内部状态，而是通过工作流编排 App 级别的运维操作
- 系统的全量持久化能力保证：对话会话状态、App 配置、执行上下文在重启后不丢失

---

## 2. 现状差距分析

### 2.1 AgentSystem 已有能力（内核 80% 完成）

| 能力域 | 状态 | 说明 |
|--------|------|------|
| App 生命周期 | ✅ | draft → installed → running → stopped → paused |
| Skill 治理 | ✅ | 创建/注册/验证/风险管控/版本管理/回滚 |
| Meta-app 全链路 | ✅ | LLM 设计 → skill 创建 → blueprint 组装 → 安装 |
| Workflow 执行 | ✅ | deterministic steps + skill dispatch |
| 自我迭代闭环 | ✅ | practice review → experience → skill suggestion → refinement |
| 控制面治理 | ✅ | risk policy, rollout governance, operator surfaces |
| API 端点 | ✅ | ~80 个端点，覆盖所有子系统 |

### 2.2 核心缺口（用户可用层 40% 完成）

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| 没有自然语言入口 | 用户只能通过 API 操作 | P0 |
| 现有 InteractionGateway 只是关键词匹配 | 不是真正的对话 | P0 |
| 没有对话会话管理 | 无上下文连续性 | P0 |
| 没有 LLM 意图识别 | 无法理解用户自然语言 | P0 |
| 没有结构化回复（卡片/按钮） | 纯文本，不友好 | P1 |
| 没有流式输出 | 等待时间长 | P1 |
| Skill 不对用户可见 | 用户不知道能做什么 | P1 |
| 没有多通道适配 | 只支持 REST API | P2 |

### 2.3 与 OpenClaw 的对比

| 维度 | OpenClaw | AgentSystem 当前 | AgentSystem 需要 |
|------|----------|-----------------|-----------------|
| 入口 | 统一 Gateway | 分散的 API 端点 | 统一 LLM Gateway |
| 路由 | LLM 理解 + slash commands | 关键词匹配 | LLM 意图识别 |
| 会话 | 长驻、按 peer 隔离 | 无 | 会话管理器 |
| 流式 | 实时 delta 流 | 无 | SSE 流式输出 |
| 技能发现 | user-invocable + native commands | 只有 API | skill 即命令 |
| 可视化 | Canvas/A2UI | 纯文本 | 卡片/按钮/列表 |
| 消息控制 | 去重/防抖/队列 | 无 | 消息流控制 |
| 执行分离 | LLM 决策 + tool 执行 | 直接调用 | LLM 路由 + 确定性执行 |

---

## 3. OpenClaw 交互层架构借鉴

### 3.1 Gateway 模式 — 统一入口

OpenClaw 的核心是**单一长驻 Gateway**，拥有所有消息面（WhatsApp / Telegram / Discord / Signal / WebChat）。

```
WhatsApp / Telegram / Discord / WebChat
            ↓
    [ Gateway (daemon) ]
            ↓
    [ Agent Loop ]
            ↓
    [ Tool Execution + Streaming ]
```

**借鉴要点**：
- 所有用户请求经过一个统一的网关
- 网关负责 channel 适配、session 路由、agent 调度
- Gateway 是所有 session 的所有者，不是客户端

### 3.2 Agent Loop — 思考-行动循环

```
消息入 → 上下文组装 → 模型推理 → 工具执行 → 流式回复 → 持久化
```

**借鉴要点**：
- 单次 agent run 是完整的"理解→决策→执行→回复"循环
- 工具调用事件广播给客户端
- lifecycle 事件 (start/end/error)
- 自动 compaction 防止上下文爆炸

### 3.3 Session Management — 会话隔离

```
DM → per-channel-peer 隔离
Group → per-group 隔离
Cron → 每次新会话
```

**借鉴要点**：
- Session 由 Gateway 所有
- 按 channel + peer 隔离
- 支持 daily reset、idle reset、manual reset
- 会话历史持久化为 JSONL transcript

### 3.4 Skill as User Commands — 技能即命令

```
user-invocable: true → 自动注册为 slash command
command-dispatch: tool → 确定性直达（不经过模型）
```

**借鉴要点**：
- Skill 不仅内部可用，也对用户可见、可发现
- `user-invocable` 控制是否暴露为用户命令
- `command-dispatch: tool` 支持确定性直达

### 3.5 Message Flow Control — 消息流控制

```
去重 → 防抖 → 队列模式 → 流式分块
```

**借鉴要点**：
- 同一用户快速消息可合并（debounce）
- 运行中的新消息可队列化（steer/interrupt/followup/collect）
- 分块输出尊重平台限制
- 支持流式 partial replies

### 3.6 可视化层 — Canvas / A2UI

```
Canvas (HTML/CSS/JS) + A2UI (Agent-to-UI)
```

**借鉴要点**：
- 不只是纯文本回复
- 支持卡片、按钮、进度条等结构化回复
- Agent 可以 push HTML 到 canvas host

### 3.7 Plugin Hooks — 生命周期拦截

```
before_model_resolve → before_prompt_build → before_agent_start
→ before_agent_reply → agent_end → before_tool_call → after_tool_call
```

**借鉴要点**：
- 在关键生命周期节点设置 hook
- 允许插件/自定义逻辑拦截和修改行为
- block/cancel 机制控制流程

---

## 4. 技术设计方案

### 4.1 整体架构

借鉴 OpenClaw 的 Gateway + Agent Loop 模式，但适配 AgentSystem 的 API/Service 拓扑：

```
用户 (QQBot / WebChat / CLI / Telegram)
    ↓
[ LLM Interaction Gateway ]  ← 新增：统一入口
    ├── 消息去重/防抖
    ├── 会话路由
    └── Agent Loop 调度
    ↓
[ Conversation Session Manager ]  ← 新增：会话管理
    ├── 会话生命周期
    ├── 上下文维护
    └── 压缩/重置
    ↓
[ Conversation Router (LLM) ]  ← 新增：意图识别 + 参数提取
    ├── 意图分类
    ├── 参数提取
    ├── 澄清判断
    └── 动作建议
    ↓
    ├──→ MetaAppCreationOrchestrator (已有) → 创建 app
    ├──→ AppRegistryService (已有) → app 管理
    ├──→ AppLifecycleService (已有) → lifecycle 操作
    ├──→ SkillFactoryService (已有) → skill 创建
    ├──→ SkillControlService (已有) → skill 管理
    ├──→ WorkflowExecutorService (已有) → workflow 执行
    ├──→ SystemSkillRegistry (已有) → system skill 调用
    └──→ Clarification Engine (新增) → 澄清/帮助
    ↓
[ Response Serializer ]  ← 新增：结构化回复
    ├── 文本回复
    ├── 卡片回复
    ├── 列表回复
    ├── 确认对话框
    └── 动作建议（按钮）
```

### 4.2 核心组件

#### 4.2.1 ConversationSessionManager（会话管理）

借鉴 OpenClaw 的 session management：
- Session 由系统所有，不是客户端
- 按 user_id + channel 隔离（per-channel-peer）
- 支持 idle reset、manual reset
- 上下文压缩防止爆炸

```python
# app/services/conversation_session.py

@dataclass
class MessageRecord:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)

@dataclass
class ConversationSession:
    session_id: str
    user_id: str
    channel: str
    message_history: list[MessageRecord] = field(default_factory=list)
    current_task: dict | None = None  # 当前正在进行的任务
    pending_confirmations: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    token_usage: int = 0

class ConversationSessionManager:
    """管理用户对话会话。"""

    MAX_HISTORY = 50  # 最大历史条数
    COMPACT_KEEP = 20  # 压缩后保留条数

    def __init__(self, state_store: RuntimeStateStore | None = None):
        self._sessions: dict[str, ConversationSession] = {}
        self._state_store = state_store  # 可选持久化

    def get_or_create(self, user_id: str, channel: str) -> ConversationSession:
        key = f"{user_id}:{channel}"
        if key not in self._sessions:
            self._sessions[key] = ConversationSession(
                session_id=key, user_id=user_id, channel=channel,
            )
        return self._sessions[key]

    def add_message(self, session_id: str, role: str, content: str, **metadata):
        session = self._sessions[session_id]
        session.message_history.append(MessageRecord(
            role=role, content=content, timestamp=datetime.now(), metadata=metadata,
        ))
        session.last_active = datetime.now()
        if len(session.message_history) > self.MAX_HISTORY:
            self._compact(session)

    def _compact(self, session: ConversationSession):
        """压缩历史：保留最近 N 条 + 摘要。"""
        old = session.message_history[:-self.COMPACT_KEEP]
        summary = f"[{len(old)} 条历史消息已压缩]"
        session.message_history = [
            MessageRecord("system", summary, datetime.now())
        ] + session.message_history[-self.COMPACT_KEEP:]

    def reset(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
```

#### 4.2.2 ConversationRouter（LLM 意图识别）

借鉴 OpenClaw 的 requirement routing + slash command dispatch：
- LLM 理解意图（类似 requirement router 但更通用）
- 提取结构化参数
- 判断是否需要澄清
- 返回建议动作（类似 slash command 发现）

```python
# app/services/conversation_router.py

@dataclass
class RoutingResult:
    intent: str  # 意图类别
    confidence: float
    extracted_params: dict[str, Any]
    needs_clarification: bool
    clarification_questions: list[str] = field(default_factory=list)
    suggested_actions: list[ActionSuggestion] = field(default_factory=list)
    target_service: str = ""

@dataclass
class ActionSuggestion:
    label: str  # 按钮/选项文本
    action_id: str
    params: dict[str, Any]
    is_primary: bool = False

class ConversationRouter:
    """LLM 驱动的对话路由器。

    意图体系：
    - create_app: 创建新 app → 走 meta-app 流程
    - manage_app: 管理已有 app (start/stop/pause/list)
    - create_skill: 创建新 skill
    - manage_skill: 管理已有 skill (enable/disable/list)
    - run_workflow: 执行 workflow
    - query_status: 查询状态 (apps/skills/system)
    - query_help: 帮助/说明
    - clarify: 需要进一步澄清
    """

    INTENT_DEFINITIONS = {
        "create_app": {
            "description": "用户想创建一个新的 app",
            "required_params": ["app_name", "goal"],
            "optional_params": ["app_kind", "complexity", "scope"],
            "service": "meta_app_orchestrator",
        },
        "manage_app": {
            "description": "用户想管理已有 app",
            "required_params": ["action"],
            "optional_params": ["app_name"],
            "service": "app_services",
        },
        "manage_skill": {
            "description": "用户想管理 skill",
            "required_params": ["action"],
            "optional_params": ["skill_name"],
            "service": "skill_services",
        },
        "query_status": {
            "description": "用户想查询系统状态",
            "required_params": [],
            "optional_params": ["scope"],
            "service": "app_registry",
        },
        "query_help": {
            "description": "用户需要帮助",
            "required_params": [],
            "optional_params": [],
            "service": "none",
        },
    }

    SYSTEM_PROMPT = """你是 AgentSystem 的智能交互路由器。

## 角色
你是 App OS 的交互前端。用户通过自然语言与你对话，你需要理解意图、提取参数、决定下一步。

## 意图体系
{intent_definitions}

## 规则
- 信息不足时主动澄清，不要猜测
- 创建 app 前确认关键参数
- 破坏性操作前要求确认
- 用简洁中文回复

## 输出
输出 JSON 格式的路由结果。"""

    def __init__(self, model_client: OpenAICompatibleClient):
        self._model_client = model_client

    async def route(self, session: ConversationSession, message: str) -> RoutingResult:
        prompt = self._build_prompt(session, message)
        response = await self._model_client.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # 低温度保证稳定性
            max_tokens=1000,
        )
        return self._parse_result(response.text)
```

#### 4.2.3 LLMInteractionGateway（主入口）

借鉴 OpenClaw 的 Gateway + Agent Loop 模式：
- 统一入口，所有请求经过这里
- 理解→决策→执行→回复 完整循环
- 支持流式输出
- 工具调用事件可追踪
- 会话上下文自动维护

```python
# app/services/llm_interaction_gateway.py

@dataclass
class InteractionResponse:
    text: str
    response_type: str  # text/card/list/form/confirm/progress/error
    actions: list[ActionSuggestion]
    data: dict[str, Any] | None = None
    session_id: str = ""

class LLMInteractionGateway:
    """LLM 驱动的统一交互入口。

    这是用户与 AgentSystem 的主要界面。
    所有用户请求都经过这里，由 LLM 理解意图后分发到对应子系统。
    """

    def __init__(
        self,
        router: ConversationRouter,
        session_manager: ConversationSessionManager,
        meta_app_orchestrator: MetaAppCreationOrchestrator,
        app_registry: AppRegistryService,
        app_installer: AppInstallerService,
        lifecycle: AppLifecycleService,
        runtime_host: AppRuntimeHostService,
        skill_control: SkillControlService,
        skill_factory: SkillFactoryService,
        system_skill_registry: SystemSkillRegistry,
        context_store: AppContextStore,
        workflow_executor: WorkflowExecutorService | None = None,
    ):
        self._router = router
        self._sessions = session_manager
        self._meta_app = meta_app_orchestrator
        self._app_registry = app_registry
        self._app_installer = app_installer
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._skill_control = skill_control
        self._skill_factory = skill_factory
        self._system_skills = system_skill_registry
        self._context_store = context_store
        self._workflow_executor = workflow_executor

    async def process_message(
        self,
        user_id: str,
        message: str,
        channel: str = "webchat",
    ) -> InteractionResponse:
        """主入口：用户发一句话，系统理解并执行。

        流程：
        1. 获取/创建会话
        2. LLM 路由（理解意图）
        3. 分发到对应子系统
        4. 构建回复
        5. 记录到会话历史
        """
        session = self._sessions.get_or_create(user_id, channel)
        self._sessions.add_message(session.session_id, "user", message)

        # Step 1: LLM 路由
        routing = await self._router.route(session, message)

        # Step 2: 根据意图分发
        if routing.needs_clarification:
            response = self._handle_clarification(routing)
        elif routing.intent == "create_app":
            response = await self._handle_create_app(session, routing)
        elif routing.intent == "manage_app":
            response = await self._handle_manage_app(session, routing)
        elif routing.intent == "manage_skill":
            response = await self._handle_manage_skill(session, routing)
        elif routing.intent == "query_status":
            response = await self._handle_query_status(session, routing)
        elif routing.intent == "query_help":
            response = self._handle_help()
        else:
            response = self._handle_unknown(routing)

        self._sessions.add_message(session.session_id, "assistant", response.text)
        response.session_id = session.session_id
        return response

    async def _handle_create_app(self, session, routing) -> InteractionResponse:
        """创建 app：调用 meta-app 全链路。"""
        params = routing.extracted_params
        request = AppCreationFromMetaAppRequest(
            app_name=params.get("app_name", "unnamed-app"),
            goal=params.get("goal", ""),
            app_kind=params.get("app_kind", "pipeline"),
            complexity=params.get("complexity", "moderate"),
            scope=params.get("scope", "app"),
            context=params.get("description", ""),
            auto_install=True,
        )
        result = self._meta_app.create_app_through_meta_app(request)
        return InteractionResponse(
            text=f"✅ App '{result.app_name}' 已创建！\n"
                 f"生成了 {len(result.created_skill_ids)} 个 skill(s)。\n"
                 f"{'已自动安装并运行。' if result.blueprint else '蓝图已生成。'}",
            response_type="card",
            actions=[
                ActionSuggestion("查看详情", "view_app", {"app_name": result.app_name}),
                ActionSuggestion("创建另一个", "create_app", {}),
            ],
            data={"app_name": result.app_name, "skill_ids": result.created_skill_ids},
        )

    async def _handle_manage_app(self, session, routing) -> InteractionResponse:
        """管理 app。"""
        action = routing.extracted_params.get("action", "list")
        app_name = routing.extracted_params.get("app_name")

        if action == "list":
            entries = self._app_registry.list_registry()
            lines = [
                f"{i+1}. {e.blueprint_id} ({getattr(e, 'status', 'unknown')})"
                for i, e in enumerate(entries)
            ]
            return InteractionResponse(
                text=f"你目前有 {len(entries)} 个 app：\n" + "\n".join(lines),
                response_type="list",
                actions=[ActionSuggestion("创建新 app", "create_app", {})],
            )
        elif action == "start" and app_name:
            # 调用 lifecycle + runtime_host
            self._lifecycle.transition_to(app_name, "running")
            self._runtime_host.start_app(app_name)
            return InteractionResponse(
                text=f"✅ App '{app_name}' 已启动。",
                response_type="text",
                actions=[
                    ActionSuggestion("查看状态", "query_status", {"scope": "apps"}),
                    ActionSuggestion("停止", "manage_app", {"action": "stop", "app_name": app_name}),
                ],
            )
        # ... 其他 action

    async def _handle_query_status(self, session, routing) -> InteractionResponse:
        """查询系统状态。"""
        scope = routing.extracted_params.get("scope", "all")
        parts = []

        if scope in ("apps", "all"):
            entries = self._app_registry.list_registry()
            parts.append(f"📱 Apps: {len(entries)} 个")
            for e in entries:
                parts.append(f"  - {e.blueprint_id} ({getattr(e, 'status', 'unknown')})")

        if scope in ("skills", "all"):
            skills = self._skill_control.list_skills()
            parts.append(f"\n🔧 Skills: {len(skills)} 个")
            for s in skills:
                parts.append(f"  - {s}")

        return InteractionResponse(
            text="\n".join(parts),
            response_type="list" if scope == "all" else "text",
            actions=[
                ActionSuggestion("创建新 app", "create_app", {}),
                ActionSuggestion("帮助", "query_help", {}),
            ],
        )

    def _handle_help(self) -> InteractionResponse:
        """帮助。"""
        return InteractionResponse(
            text="我是 AgentSystem 助手。我可以帮你：\n"
                 "1. 创建 app — 告诉我你想要什么\n"
                 "2. 管理 app — 查看/启动/停止\n"
                 "3. 管理 skill — 查看/启用/禁用\n"
                 "4. 查询状态 — 系统/app/skill 状态\n\n"
                 "试试说：'帮我创建一个日报总结的 app'",
            response_type="text",
            actions=[
                ActionSuggestion("创建 app", "create_app", {}),
                ActionSuggestion("查看 app", "query_status", {"scope": "apps"}),
                ActionSuggestion("查看 skill", "query_status", {"scope": "skills"}),
            ],
        )
```

#### 4.2.4 ResponseSerializer（结构化回复）

借鉴 OpenClaw 的 Canvas/A2UI 概念，但简化为 AgentSystem 当前需要的回复类型：

```python
# app/services/response_serializer.py

class ResponseSerializer:
    """将 InteractionResponse 序列化为不同通道友好的格式。"""

    def to_text(self, response: InteractionResponse) -> str:
        """纯文本格式（所有通道通用）。"""
        parts = [response.text]
        if response.actions:
            parts.append("\n---\n可用操作：")
            for i, a in enumerate(response.actions, 1):
                marker = " [主要]" if a.is_primary else ""
                parts.append(f"  {i}. {a.label}{marker}")
        return "\n".join(parts)

    def to_card(self, response: InteractionResponse) -> dict:
        """卡片格式（支持按钮的通道）。"""
        return {
            "type": "card",
            "title": response.data.get("app_name", "AgentSystem") if response.data else "AgentSystem",
            "body": response.text,
            "buttons": [
                {"label": a.label, "action_id": a.action_id, "params": a.params}
                for a in response.actions
            ],
        }

    def to_webchat(self, response: InteractionResponse) -> dict:
        """WebChat 前端格式。"""
        return {
            "session_id": response.session_id,
            "text": response.text,
            "response_type": response.response_type,
            "actions": [
                {"label": a.label, "action_id": a.action_id, "params": a.params, "is_primary": a.is_primary}
                for a in response.actions
            ],
            "data": response.data,
        }
```

### 4.3 对话流示例

#### 场景 1：创建 App（完整流程）

```
用户: "帮我做一个日报总结的 app"

→ LLM Router 识别: intent=create_app, confidence=0.85
→ 参数不足: 缺 goal 细节
→ 需要澄清

系统: "好的！我来帮你设计一个日报总结 app。请告诉我：
  1. 日报的输入来源是什么？（手动输入 / 邮件 / 其他系统）
  2. 输出格式偏好？（文本 / 表格 / 邮件）"

用户: "手动输入，输出文本就行"

→ LLM Router 识别: intent=create_app, confidence=0.95
→ 参数就绪: {app_name: "daily-report-summary", goal: "总结每日工作", ...}
→ 调用 meta_app_orchestrator.create_app_through_meta_app()
→ LLM 设计 → skill 创建 → blueprint 组装 → 安装

系统: [卡片回复]
  "✅ App 'daily-report-summary' 已创建！
   生成了 2 个 skill(s)。已自动安装并运行。
   [查看详情] [创建另一个]"
```

#### 场景 2：管理 App

```
用户: "看看我的 app"

→ LLM Router: intent=query_status, scope=apps

系统: [列表回复]
  "你目前有 3 个 app：
   1. daily-report-summary (running)
   2. weekly-review (stopped)
   3. bug-triage (installed)
   [启动 weekly-review] [创建新 app]"

用户: "启动 weekly-review"

→ LLM Router: intent=manage_app, action=start, app_name=weekly-review
→ 调用 lifecycle + runtime_host

系统: "✅ weekly-review 已启动。
  [查看状态] [停止]"
```

#### 场景 3：Skill 发现

```
用户: "有哪些可用的 skill"

→ LLM Router: intent=query_status, scope=skills

系统: [列表回复]
  "系统共有 16 个 skill：
   内建: system.app_config, system.context, system.state, system.audit
   生成: input-collector, text-summarizer
   能力: system.maoxuan (毛选思维分析)
   [查看某个 skill 详情] [创建新 skill]"
```

### 4.4 API 端点设计

```python
# 新增到 app/api/main.py

# 主对话入口
@app.post("/chat/message")
async def send_chat_message(request: ChatMessageRequest) -> dict:
    """用户发送一条消息，系统理解并执行。"""
    response = await llm_interaction_gateway.process_message(
        user_id=request.user_id,
        message=request.message,
        channel=request.channel,
    )
    return {
        "session_id": response.session_id,
        "text": response.text,
        "response_type": response.response_type,
        "actions": [a.__dict__ for a in response.actions],
        "data": response.data,
    }

# 流式对话（SSE）
@app.post("/chat/message/stream")
async def send_chat_message_stream(request: ChatMessageRequest) -> StreamingResponse:
    """流式对话，实时返回 LLM 输出。"""
    async def event_stream():
        async for chunk in llm_interaction_gateway.process_message_stream(...):
            yield f"data: {json.dumps(chunk)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# 会话管理
@app.get("/chat/sessions")
async def list_chat_sessions(user_id: str) -> list[dict]: ...

@app.delete("/chat/sessions/{session_id}")
async def reset_chat_session(session_id: str) -> dict: ...

# 动作执行（用户点了按钮/选项）
@app.post("/chat/actions/{action_id}")
async def execute_chat_action(action_id: str, body: dict) -> dict: ...
```

### 4.5 请求/响应模型

```python
# app/models/chat.py

class ChatMessageRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    channel: str = Field(default="webchat")
    session_id: str | None = None

class ChatMessageResponse(BaseModel):
    session_id: str
    text: str
    response_type: str  # text/card/list/form/confirm/progress/error
    actions: list[dict] = Field(default_factory=list)
    data: dict | None = None
```

### 4.6 系统 Prompt 模板

```
你是 AgentSystem 的智能交互助手。你是 App OS 的前端，帮助用户管理 apps、skills 和 workflows。

## 你的能力
1. 创建 app：用户描述需求 → 你设计结构 → 自动生成 skills → 组装 blueprint → 安装运行
2. 管理 app：查看/启动/暂停/停止/删除已安装的 app
3. 管理 skill：查看/启用/禁用/创建 skill
4. 查询状态：系统概览、app 列表、skill 列表
5. 帮助：解释系统能力和用法

## 交互规则
- 用户输入模糊时，主动澄清而非猜测
- 创建 app 前，确认关键参数（输入来源、输出格式、执行频率）
- 执行破坏性操作前，要求用户确认
- 用简洁中文回复，避免技术术语
- 返回结构化回复时，附带可执行的后续动作建议
```

---

## 5. 执行计划

### Phase 7.1: 基础对话网关（~2 天）
- [ ] `ConversationSessionManager` — 会话管理
- [ ] `ConversationRouter` — LLM 意图识别
- [ ] `LLMInteractionGateway` — 主入口
- [ ] `ChatMessageRequest/Response` 模型
- [ ] `POST /chat/message` — API 端点
- [ ] 系统 prompt 设计

### Phase 7.2: 全链路打通（~2 天）
- [ ] Router → meta-app 创建 app 流程
- [ ] Router → app 管理流程 (list/start/stop/pause)
- [ ] Router → skill 查询/管理
- [ ] Router → 系统状态查询
- [ ] Runtime wiring (bootstrap/runtime.py)
- [ ] 端到端测试

### Phase 7.3: 用户体验增强（~1 天）
- [ ] 流式输出（SSE）
- [ ] 卡片/列表/确认等回复类型完善
- [ ] 对话历史查看 API
- [ ] 会话压缩策略优化

### Phase 7.4: 多通道接入（~1 天）
- [ ] QQBot 通道适配
- [ ] 通道特定的消息格式适配
- [ ] Skill 作为用户可发现命令（借鉴 OpenClaw user-invocable）

---

## 6. 需要更新的项目文档

| 文档 | 更新内容 |
|---|---|
| `docs/requirements.md` | 在 §5.1 新增 LLM 交互网关需求；§10 新增验收标准 |
| `docs/design.md` | 新增 LLM Interaction Gateway 设计章节；更新架构图 |
| `docs/testing.md` | 新增交互层测试计划；新增对话路由测试用例；新增 E2E 测试 |
| `docs/code-structure.md` | 新增交互层模块映射 |
| `docs/system-relationship-map.md` | 新增 LLM 交互网关的关系节点 |
| `docs/skill-design-principles.md` | 新增交互层 skill 的设计原则；Core Skill 表新增 `system.interaction_router` |

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 意图识别不准 | 用户操作失败 | 置信度低时主动澄清；支持手动纠正 |
| 上下文爆炸 | token 成本失控 | 会话压缩（保留最近 20 条 + 摘要） |
| 模型不可用 | 交互层瘫痪 | 降级到规则匹配模式（fallback to keyword matching） |
| 多通道消息格式差异 | 解析错误 | 通道适配器层隔离 |

---

## 8. 与现有系统的兼容性

- ✅ 所有现有 API 端点保持不变
- ✅ 交互层是对现有 API 的**封装**，不是替代
- ✅ `InteractionGateway`（旧版）保留为 fallback
- ✅ 新的 `LLMInteractionGateway` 作为主入口
- ✅ bootstrap/runtime wiring 新增交互层服务实例化
