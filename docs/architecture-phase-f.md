# Phase F: 原生 Tool Calling + 统一模型路由 + App 创作者重构

## 1. 现状问题清单

### 1.1 无原生 Tool Calling
- 所有 LLM 调用都是**单次 prompt → response**
- `parse_intent_with_tools` 只是把工具列表拼成文本塞进 prompt，**不是真正的 tool calling**
- skill 无法进行**多次迭代分析**（查数据 → 分析 → 再查 → 综合）
- 无法利用 OpenAI Responses API 原生的 `tools` + `tool_calls` + `tool_result` 循环

### 1.2 无统一模型路由
- 7+ 个 LLM 调用点各自加载全局模型配置
- 所有调用都走同一个模型，简单任务浪费强模型
- skill 无法声明自己的模型偏好

### 1.3 创作者是硬编码服务，无 skill 组装
- `MetaAppBootstrapService` 是 Python 服务，不是 skill
- LLM 盲设计，不知道已有 skill 列表
- 无用户确认环节

### 1.4 无多轮状态管理
- 网关不维护 `active_skill` 状态
- 用户第二次输入重新走意图解析，不知道"这个 skill 还在等待我回复"

---

## 2. 整体架构

```
┌───────────────────────────────────────────────────────────────────┐
│                        用户交互层                                   │
│  light_brain_gateway.py                                           │
│  - 意图解析（正则优先 → LLM fallback）                               │
│  - 多轮状态管理: active_skill 维护                                 │
│  - 【用户确认】设计方案展示 / 调整 / 验收                            │
│  - 【指导环节】创建失败反馈引导                                      │
└──────────────────────────────┬────────────────────────────────────┘
                               │
          ┌────────────────────┴────────────────────┐
          │                                         │
          ▼                                         ▼
┌─────────────────────┐              ┌──────────────────────────────┐
│   Skill Router      │              │   ModelRouter (统一路由层)      │
│   (intent → skill)  │              │                              │
│                     │              │  路由优先级:                   │
│  1. 查 active_skill │              │  1. skill 声明的 model_pref   │
│  2. 查 skill 注册表  │              │  2. 调用者类型 + 复杂度         │
│  3. 回退到 handler  │              │  3. 全局默认模型                │
└────────┬────────────┘              └──────────────┬───────────────┘
         │                                          │
         ▼                                          ▼
┌───────────────────────────────────────────────────────────────────┐
│                    App 创作者层（Path B）                            │
│  app/services/app_designer/                                       │
│                                                                   │
│  ┌──────────────────┐    ┌───────────────────┐                   │
│  │ intent_analyzer  │    │  architect         │                   │
│  │                  │    │                    │                   │
│  │ 专用意图分析      │    │  架构设计师         │                   │
│  │ ModelRouter:     │    │  ModelRouter:      │                   │
│  │ cheap 模型       │    │  strong 模型       │                   │
│  │                  │    │  注入 skill registry│                   │
│  └──────────────────┘    └───────────────────┘                   │
│                                                                   │
│  ┌─────────────────────────────────────────────────┐             │
│  │  orchestrator.py                                │             │
│  │  - 意图 → 设计 → 用户确认 → 创建 → 安装          │             │
│  └─────────────────────────────────────────────────┘             │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                    原生 Tool Calling 引擎                           │
│  app/services/tool_calling_engine.py                               │
│                                                                   │
│  支持 OpenAI Responses API 原生 tool calling:                      │
│  1. 发送 system + user + tools                                     │
│  2. LLM 返回 tool_calls                                            │
│  3. 执行工具 → 返回 tool_result                                    │
│  4. 循环直到 LLM 给出最终答案                                       │
│                                                                   │
│  多轮迭代: 查数据 → 分析 → 再查 → 综合 → 最终回复                   │
│                                                                   │
│  每次调用都通过 ModelRouter 解析模型:                               │
│  client = model_router.get_client(caller="skill:<id>")             │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                    创建层                                           │
│  skill_factory → skill_installer → skill_registry                  │
│  - 生成 skill 代码                                                  │
│  - 注册到系统                                                       │
│  - 安装上线                                                         │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心设计

### 3.1 原生 Tool Calling 引擎

**文件**: `app/services/tool_calling_engine.py`（新增）

```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.model_router import ModelRouter
from app.services.model_client import OpenAIResponsesClient


@dataclass
class ToolDefinition:
    """OpenAI 格式的 tool 定义"""
    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass
class ToolCallResult:
    """工具执行结果"""
    tool_call_id: str
    tool_name: str
    result: Any
    error: str = ""


@dataclass
class ToolCallingSession:
    """多轮 tool calling 会话"""
    session_id: str
    skill_id: str
    messages: list[dict] = field(default_factory=list)
    max_turns: int = 10
    current_turn: int = 0
    is_complete: bool = False
    final_answer: str = ""


class ToolCallingEngine:
    """原生 Tool Calling 引擎 — 支持多轮迭代分析"""
    
    def __init__(self, model_router: ModelRouter, tool_registry: dict[str, Callable] = None):
        self._router = model_router
        self._tools: dict[str, Callable] = tool_registry or {}
        self._sessions: dict[str, ToolCallingSession] = {}
    
    def register_tool(self, name: str, handler: Callable):
        """注册可被 LLM 调用的工具"""
        self._tools[name] = handler
    
    def execute(self, skill_id: str, system_prompt: str, user_message: str,
                tools: list[ToolDefinition], max_turns: int = 10) -> str:
        """执行多轮 tool calling
        
        流程:
        1. 通过 ModelRouter 获取 skill 对应的模型 client
        2. 发送 messages + tools → LLM
        3. 如果 LLM 返回 tool_calls → 执行工具 → 循环
        4. 直到 LLM 给出最终答案
        """
        # 通过 ModelRouter 获取 client（自动按 skill 选模型）
        client = self._router.get_client(caller=f"skill:{skill_id}")
        
        # 初始化会话
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        session = ToolCallingSession(
            session_id=f"tc-{skill_id}-{id(self)}",
            skill_id=skill_id,
            messages=messages,
            max_turns=max_turns,
        )
        self._sessions[session.session_id] = session
        
        # 多轮循环
        for turn in range(max_turns):
            session.current_turn = turn + 1
            
            # 调用 LLM（带 tools）
            response = self._call_llm_with_tools(client, messages, tools)
            
            # 检查是否有 tool_calls
            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                # LLM 给出最终答案
                session.final_answer = self._extract_text(response)
                session.is_complete = True
                break
            
            # 执行工具调用
            messages.append(response["message"])  # 添加 assistant 的 tool_calls 消息
            
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                tool_call_id = tc["id"]
                
                result = self._execute_tool(tool_name, tool_args, tool_call_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        
        return session.final_answer
    
    def _call_llm_with_tools(self, client, messages: list[dict], 
                              tools: list[ToolDefinition]) -> dict:
        """调用 LLM，支持 tool calling"""
        tools_payload = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            }
            for t in tools
        ]
        
        # 通过 chat completion 调用（支持 tools 参数）
        result_text, usage = client.chat_with_tools(
            messages=messages,
            tools=tools_payload,
        )
        
        # 解析 tool_calls（如果有）
        return self._parse_tool_calling_response(result_text)
    
    def _execute_tool(self, name: str, args: dict, tool_call_id: str) -> dict:
        """执行单个工具调用"""
        handler = self._tools.get(name)
        if not handler:
            return {"error": f"Tool not found: {name}"}
        try:
            result = handler(**args)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

**关键**：`ModelRouter.get_client()` 自动根据 `skill_id` 解析模型，**每轮调用都用同一个模型**（保持上下文一致）。

### 3.2 统一模型路由器

**文件**: `app/services/model_router.py`（新增）

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.services.model_config_loader import ModelConfigLoader, ModelConfigError
from app.services.model_client import OpenAIResponsesClient


@dataclass
class ModelRoute:
    """模型路由结果"""
    profile_name: str      # "cheap" / "balanced" / "strong"
    model_name: str        # 实际模型名，如 "gpt-4o-mini"
    config: Any            # ModelConfig 对象
    temperature: float = 0.7
    max_tokens: int = 4096


# 内置调用者路由策略
BUILTIN_CALLER_ROUTES: dict[tuple[str, str], str] = {
    # App 创作者层
    ("intent_analyzer", "simple"):    "cheap",
    ("intent_analyzer", "moderate"):  "cheap",
    ("architect", "moderate"):        "strong",
    ("architect", "complex"):         "strong",
    ("self_refiner", "complex"):      "strong",
    ("skill_suggester", "moderate"):  "balanced",
    # 用户交互层
    ("llm_responder", "simple"):      "cheap",
    ("llm_responder", "moderate"):    "balanced",
    ("llm_responder", "complex"):     "strong",
}


class ModelRouter:
    """统一模型路由器 — 所有 LLM 调用都经过这里"""
    
    def __init__(self, config_path=None, skill_control=None):
        self._loader = ModelConfigLoader(config_path)
        self._skill_control = skill_control
        self._route_table = dict(BUILTIN_CALLER_ROUTES)
        
        # 模型 profiles
        self._profiles = {
            "cheap":    {"model": "gpt-4o-mini", "temperature": 0.3, "max_tokens": 2048},
            "balanced": {"model": "gpt-4.1",     "temperature": 0.5, "max_tokens": 4096},
            "strong":   {"model": "gpt-5.4",     "temperature": 0.7, "max_tokens": 8192},
        }
        self._default_profile = "strong"
    
    def resolve(self, caller: str, complexity: str = "moderate") -> ModelRoute:
        """解析调用者应该用哪个模型
        
        路由优先级:
        1. skill 声明的 model_preference
        2. 调用者类型 + 复杂度 → 查路由表
        3. 全局默认模型
        """
        # 1. skill 声明优先
        if caller.startswith("skill:"):
            skill_id = caller.split(":", 1)[1]
            pref = self._get_skill_model_preference(skill_id)
            if pref:
                return self._resolve_by_name(pref)
        
        # 2. 调用者路由表
        profile = self._route_table.get((caller, complexity))
        if profile:
            return self._resolve_by_name(profile)
        
        # 3. 全局默认
        return self._resolve_by_name(self._default_profile)
    
    def get_client(self, caller: str, complexity: str = "moderate") -> OpenAIResponsesClient:
        """一步到位：解析 + 创建 client"""
        route = self.resolve(caller, complexity)
        api_key = self._loader.resolve_api_key(route.config)
        return OpenAIResponsesClient(config=route.config, api_key=api_key)
    
    def _resolve_by_name(self, profile_name: str) -> ModelRoute:
        profile = self._profiles.get(profile_name, self._profiles[self._default_profile])
        try:
            config = self._loader.load()  # 加载基础配置
            # 覆盖 model 字段
            from app.models.model_config import ModelConfig
            config = ModelConfig(
                base_url=config.base_url,
                model=profile["model"],
                api_key_env=config.api_key_env,
                api_key=config.api_key,
                timeout_seconds=config.timeout_seconds,
            )
        except ModelConfigError:
            # 降级处理
            raise
        
        return ModelRoute(
            profile_name=profile_name,
            model_name=profile["model"],
            config=config,
            temperature=profile["temperature"],
            max_tokens=profile["max_tokens"],
        )
    
    def _get_skill_model_preference(self, skill_id: str) -> str | None:
        """从 skill 注册表读取 model_preference"""
        if not self._skill_control:
            return None
        try:
            entry = self._skill_control.get_skill(skill_id)
            return getattr(entry.capability_profile, 'model_preference', None)
        except Exception:
            return None
```

### 3.3 Skill 模型偏好声明

**修改**: `app/models/skill_control.py`

在 `SkillCapabilityProfile` 中新增字段：

```python
class SkillCapabilityProfile(BaseModel):
    intelligence_level: SkillIntelligenceLevel = "L0_deterministic"
    network_requirement: SkillNetworkRequirement = "N0_none"
    runtime_criticality: SkillRuntimeCriticality = "C2_required_runtime"
    execution_locality: SkillExecutionLocality = "local"
    invocation_default: SkillInvocationDefault = "automatic"
    risk_level: str = Field(default="R0_safe_read", min_length=1)
    
    # ===== 新增 =====
    model_preference: str | None = None  # "cheap" / "balanced" / "strong" / 直接模型名
    supports_tool_calling: bool = False  # 是否支持原生 tool calling 多轮迭代
```

### 3.4 Model Client 升级

**修改**: `app/services/model_client.py`

新增 `chat_with_tools` 方法支持原生 tool calling：

```python
def chat_with_tools(
    self,
    messages: list[dict[str, str]],
    tools: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> tuple[dict, dict]:
    """支持 tool calling 的 chat 完成请求
    
    Returns:
        (response_dict, usage_info)
        response_dict 包含:
        - message: {"role": "assistant", "content": ..., "tool_calls": [...]}
        - text: 提取的文本内容（如果有）
        - tool_calls: 工具调用列表（如果有）
    """
    model_name = model or self._config.model
    url = self._config.base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": messages,
        "tools": tools,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,  # tool calling 不需要 stream
    }
    # ... 发送请求并解析 response
```

### 3.5 App 创作者层（Path B）

**目录**: `app/services/app_designer/`（新增）

#### 3.5.1 意图分析器 `intent_analyzer.py`

```python
class AppIntentAnalyzer:
    """App 创建专用意图分析器 — 用便宜模型"""
    
    def __init__(self, model_router: ModelRouter):
        self._router = model_router
    
    def analyze(self, user_input: str) -> AppIntentResult:
        route = self._router.resolve("intent_analyzer", "simple")
        client = OpenAIResponsesClient(config=route.config, 
                                        api_key=self._loader.resolve_api_key(route.config))
        
        response, _ = client.generate_response(
            system_prompt="你是 App 创建意图分析器。分析用户需求，输出结构化 JSON。",
            user_message=user_input,
            max_tokens=500,
            temperature=0.1,
        )
        return self._parse_result(response)
```

#### 3.5.2 架构设计师 `architect.py`

```python
class AppArchitect:
    """App 架构设计师 — 注入 skill registry，用强模型"""
    
    def __init__(self, model_router: ModelRouter, skill_registry):
        self._router = model_router
        self._skill_registry = skill_registry
    
    def design(self, intent: AppIntentResult) -> AppDesignResult:
        route = self._router.resolve("architect", intent.complexity)
        client = OpenAIResponsesClient(config=route.config,
                                        api_key=self._loader.resolve_api_key(route.config))
        
        # 查询已有 skill 列表
        existing_skills = self._list_existing_skills()
        
        # 构建 prompt — 注入已有 skill
        prompt = self._build_design_prompt(intent, existing_skills)
        
        # 调用 LLM
        response, _ = client.generate_response(
            system_prompt="你是 App 架构设计师。基于已有 skill 库设计 App 架构，优先复用。",
            user_message=prompt,
            max_tokens=4096,
            temperature=0.5,
        )
        return self._parse_design(response)
```

#### 3.5.3 编排器 `orchestrator.py`

```python
class AppDesignOrchestrator:
    """App 创作者编排器 — 替代现有 MetaAppCreationOrchestrator"""
    
    def __init__(self, intent_analyzer, architect, skill_factory, ui_gateway):
        self._intent_analyzer = intent_analyzer
        self._architect = architect
        self._skill_factory = skill_factory
        self._ui_gateway = ui_gateway  # 用户确认层
    
    async def create_app(self, user_input: str, session_id: str) -> Result:
        # Step 1: 意图分析
        intent = self._intent_analyzer.analyze(user_input)
        
        # Step 2: 需要澄清？
        if intent.needs_clarification:
            return await self._ui_gateway.ask_clarification(
                intent.clarification_questions, session_id)
        
        # Step 3: 架构设计（注入 skill registry）
        design = self._architect.design(intent)
        
        # Step 4: 【用户确认环节】
        confirmation = await self._ui_gateway.present_design(design, session_id)
        if not confirmation.approved:
            return Result.rejected(confirmation.feedback)
        
        # Step 5: 创建 skill（复用已有 + 新建）
        created_ids = self._create_skills(design)
        
        # Step 6: 组装 → 安装 → 上线
        blueprint = self._skill_factory.build_blueprint_from_skills(created_ids)
        installed = self._skill_factory.install(blueprint)
        
        return Result.success(installed)
```

### 3.6 多轮状态管理

**修改**: `app/services/light_brain_gateway.py`

```python
class LightBrainGateway:
    def __init__(self, ...):
        # ... 现有代码 ...
        self._active_skills: dict[str, dict] = {}  # session_id → {skill_id, state}
    
    async def process_message(self, request: ChatMessageRequest) -> ChatMessageResponse:
        # ... 现有代码 ...
        
        # 1. 检查是否有活跃 skill（多轮状态）
        active = self._active_skills.get(request.session_id)
        if active:
            # 直接路由到活跃 skill，跳过意图解析
            return await self._continue_active_skill(request, active)
        
        # 2. 正常意图解析
        command = self._interpreter.interpret(request.message, available_apps)
        # ... 执行 ...
    
    async def _execute_skill_command(self, skill_id: str, request: ChatMessageRequest) -> ChatMessageResponse:
        """执行 skill 命令，支持多轮"""
        # ... 调用 skill ...
        
        # 如果 skill 返回 waiting 状态
        if result.status == "waiting_user_input":
            self._active_skills[request.session_id] = {
                "skill_id": skill_id,
                "state": result.state,
            }
            return ChatMessageResponse(
                type="text",
                content=result.message,
                requires_input=True,
            )
        
        # skill 完成，清除状态
        self._active_skills.pop(request.session_id, None)
        return ChatMessageResponse(type="text", content=result.message)
```

---

## 4. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| **新增** | `app/services/model_router.py` | 统一模型路由器 |
| **新增** | `app/services/tool_calling_engine.py` | 原生 Tool Calling 引擎 |
| **新增** | `app/services/app_designer/__init__.py` | 包初始化 |
| **新增** | `app/services/app_designer/intent_analyzer.py` | App 专用意图分析 |
| **新增** | `app/services/app_designer/architect.py` | App 架构设计师 |
| **新增** | `app/services/app_designer/orchestrator.py` | 创作者编排器 |
| **新增** | `app/models/app_design.py` | 意图/设计/确认数据模型 |
| **修改** | `app/services/model_client.py` | 新增 `chat_with_tools` |
| **修改** | `app/models/skill_control.py` | 新增 `model_preference`, `supports_tool_calling` |
| **修改** | `app/services/light_brain_gateway.py` | 多轮状态 + 用户确认 + ModelRouter 注入 |
| **修改** | `app/services/meta_app/bootstrap.py` | 改为通过 ModelRouter 获取 client |
| **修改** | `app/services/llm_responder.py` | 改为通过 ModelRouter 获取 client |
| **修改** | `app/services/model_self_refiner.py` | 改为通过 ModelRouter 获取 client |
| **修改** | `app/services/model_skill_suggester.py` | 改为通过 ModelRouter 获取 client |
| **修改** | `app/services/system_skills/maoxuan.py` | 改为通过 ModelRouter 获取 client |
| **修改** | `app/services/prompt_invocation_service.py` | 改为通过 ModelRouter 获取 client |
| **修改** | `app/bootstrap/runtime.py` | 注册 ModelRouter + App Designer 服务 |
| **修改** | `~/.config/agentsystem/config.yaml` | 多模型配置 |

---

## 5. 配置示例

```yaml
# ~/.config/agentsystem/config.yaml
model:
  default: strong

models:
  cheap:
    base_url: "https://crs.ruinique.com/v1"
    model: "gpt-4o-mini"
    api_key_env: "OPENAI_API_KEY"
  balanced:
    base_url: "https://crs.ruinique.com/v1"
    model: "gpt-4.1"
    api_key_env: "OPENAI_API_KEY"
  strong:
    base_url: "https://crs.ruinique.com/v1"
    model: "gpt-5.4"
    api_key_env: "OPENAI_API_KEY"

# 路由策略覆盖（可选）
routing:
  overrides:
    intent_analyzer: cheap
    architect: strong
    llm_responder: balanced
```

---

## 6. 实施步骤

### Phase F.1: 模型路由基础设施（2-3 个文件）
1. `model_router.py` — ModelRouter
2. `skill_control.py` — 新增 model_preference 字段
3. `model_client.py` — 新增 `chat_with_tools`
4. 改造 7 个调用点（全部改为 `ModelRouter.get_client()`）
5. config.yaml 扩展
6. runtime.py 注册

### Phase F.2: Tool Calling 引擎（1-2 个文件）
1. `tool_calling_engine.py` — 多轮 tool calling 循环
2. 为需要多轮的 skill 注册 tools
3. 测试端到端多轮迭代

### Phase F.3: App 创作者（Path B）（3-4 个文件）
1. `intent_analyzer.py` — App 专用意图分析
2. `architect.py` — 架构设计师（注入 skill registry）
3. `orchestrator.py` — 编排器
4. `app_design.py` — 数据模型
5. 网关层接入用户确认环节

### Phase F.4: 多轮状态管理（1 个文件）
1. `light_brain_gateway.py` — active_skill 状态维护
2. 测试多轮对话流程

---

## 7. 向后兼容

- 现有 `meta_app/` 保留不删
- 所有改造通过注入 `ModelRouter` 实现，不破坏现有 API
- `ModelConfigLoader` 保留为降级路径
- 新旧流程通过 feature flag 切换

---

## 8. 预期效果

**改造前**:
```
用户: "帮我建个监控App"
  → 正则匹配 → 硬编码 handler → 全局模型 LLM 盲设计 → 创建 → 上线
  ❌ 不知道已有 skill
  ❌ 所有调用走同一模型
  ❌ 无用户确认
  ❌ 无法多轮迭代
```

**改造后**:
```
用户: "帮我建个监控App"
  → 意图分析（cheap 模型）→ 架构设计（strong 模型，注入 skill registry）
  → 🛑 用户确认设计方案 → 创建 skill（各 skill 按自己的 model_preference 调模型）
  → 组装 → 安装 → 上线

skill 内部多轮迭代:
  → 查系统指标 → 分析数据 → 再查历史 → 综合判断 → 给出建议
  ✅ 原生 tool calling，多轮自动循环
```
