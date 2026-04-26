"""Tool Calling Interpreter - unified LLM-driven intent + tool selection.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │  User Message                                           │
  └────────────────┬────────────────────────────────────────┘
                   │
          ┌────────▼────────┐
          │  Exact Matches  │  ← greetings / help / status
          │  (zero LLM cost) │    bypass LLM immediately
          └────────┬────────┘
                   │ no match
          ┌────────▼────────┐
          │  Check Memory   │  ← pending continuation?
          │  for session    │    resume if yes
          └────────┬────────┘
                   │ no pending
          ┌────────▼──────────────────────────┐
          │  ToolCallingEngine               │
          │  + ToolRegistry + History Context│
          │  LLM selects tool               │
          └────────┬──────────────────────────┘
                   │
          ┌────────▼────────┐
          │ Tool executed  │  ← handler returns raw result
          │ → LLM generates│    LLM generates friendly reply
          │   friendly msg │
          └────────────────┘

Key principles:
  - Pending state stored in LightBrainMemory (session-scoped)
  - ContinuationService as optional layer (if registered)
  - Bridge/Master handlers remain unchanged
  - Gateway gets: user message → friendly reply (tool execution invisible)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.models.chat import InterpretedCommand
from app.services.tool_registry import ToolRegistry
from app.services.tool_calling_engine import ToolCallingEngine, ToolDef

logger = logging.getLogger(__name__)


# ─── Prompt Templates ────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """你是 AgentSystem 的智能交互引擎。

你的职责是根据用户输入选择合适工具,并基于工具结果生成友好回复。

## 当前会话状态
{session_context}

## 可用工具
{tools_description}

## 执行策略
1. **找到答案就停**:一旦发现能回答用户问题的核心信息,立即停止调用工具,直接回复
2. **边做边评估**:每调用一个工具后,问自己:"这些信息够回答用户了吗?"
   - 够了 → 立即回复,不要继续探索
   - 不够 → 再调 1-2 个工具,然后必须给结论
3. **分阶段交付**:
   - 先给"有没有/是什么"的结论
   - 如果用户需要,再深入"怎么做/为什么"
4. **不要过度探索**:用户问"有没有持久化",找到"有,用 JSON"就够了,不要继续查表结构/字段
5. **处理"继续"指令**（重要）：
   - **模糊继续**（用户只说"继续"）：
     - 再深入 1 个关键点（读 1 个文件或搜索 1 个关键词）
     - 给结论，停，问"还要继续吗？"
   - **具体继续**（用户说"继续看 XX"）：
     - 完成用户指定的目标（读完 XX 文件/查完 XX 逻辑）
     - 给结论，停，问"还需要什么？"
   - **复杂任务**（用户说"全部看完/深入分析"）：
     - 先评估工作量："需要读 N 个文件，大约 M 分钟"
     - 等待用户确认
     - 用户确认后，执行
6. 用户请求明确时,选择对应工具并提取参数
7. 缺少必要参数时,使用 `ask_clarification` 追问
8. 用户在回答上一个追问时,从 pending intent 续接上下文
9. 无法理解时,使用 `unclear` 给出引导

## 参数提取规则
- `app_name`: 从用户输入提取 App 名称
- `app_type`: 提取 App 类型
- `description`: 保留原始需求描述
- `status`: 过滤条件,枚举值 running/stopped/paused/all

## 代码自省规则
当用户要求看代码、查仓库、查持久化、查记忆、查源码位置时:
- **必须先 read_file 读取真实文件内容后才能给出具体实现细节**
- 优先检查:`app/system/gateway/light_brain_memory.py`、`app/system/gateway/light_brain_gateway.py`、`app/bootstrap/runtime.py`、`app/services/persistence_service.py`、`app/system/http_test_server.py`
- 没看关键文件前,不要直接说"未实现"或"仅内存"
- 涉及 Web Chat 时,要区分 HTTP 测试入口状态和底层持久化链路
- **代码自省约束 (硬性)**:
  - 只陈述真实 read_file 命中的文件内容
  - **未 read 文件前,不要断言"SQLite""MySQL""JSON"等具体存储类型**
  - 禁止补写:数据库类型、表结构、字段名、接口函数名、伪代码流程
  - 不确定时用"未在已查文件中证实",不要猜测
  - **如果只搜索了文件名但没 read 内容,不要断言具体实现细节**
- **首轮检查流程 (强制)**:
  - 如果问题涉及"是不是用 SQLite/JSON/某种数据库"、"具体字段/表结构/默认值是什么"、"某文件里写了什么"，第一步必须调用 `read_file`
  - `search_files` 只能用于定位候选文件,不能单独作为具体实现结论的依据
  - 若首轮尚未 `read_file` 成功,最终回复里必须明确写出"未读取到文件内容，不能确认具体实现"

## 回复要求
- 必须使用 tool calling 格式
- ask_clarification 的 question 要自然
- unclear 的 reply 要有引导性
- **收敛规则**: 查到 1-2 个关键文件后立即停止,给出结论并询问是否需要更细节
- **终止条件**:当你已获得足够信息可以回答用户问题时,直接返回回复内容,不要继续调用工具
"""


def format_assets_for_prompt(assets: list[dict[str, Any]]) -> str:
    """Format available assets for prompt section.

    Assets are NOT tools. They are system components visible to LLM
    for discovery, but invoked via call_asset_method.
    """
    if not assets:
        return "【系统资产】暂无可用资产"

    lines = ["【系统资产】"]
    for asset in assets:
        asset_id = asset.get("asset_id", asset.get("name", "unknown"))
        desc = asset.get("description", "")
        capabilities = asset.get("capabilities", [])

        cap_list = []
        for cap in (capabilities[:5] if capabilities else []):
            method = cap.get("method", "unknown")
            cap_list.append(method)

        cap_str = ", ".join(cap_list) if cap_list else "多个方法"
        lines.append(f"  • {asset_id}: {cap_str}")

    if len(assets) > 5:
        lines.append(f"  • ... 还有 {len(assets) - 5} 个资产")

    lines.append("")
    lines.append("调用资产方法: 使用 call_asset_method(asset_id, method, params)")

    return "\n".join(lines)


def build_session_context(
    history: list[dict[str, Any]],
    pending_intent: str | None,
    pending_params: dict[str, Any],
    missing_param: str | None,
    available_apps: list[dict[str, Any]],
    available_assets: list[dict[str, Any]] | None = None,
) -> str:
    """Build readable session context for prompt."""
    lines = []

    if pending_intent:
        lines.append(f"【等待完成】")
        lines.append(f"  - 意图: {pending_intent}")
        if pending_params:
            lines.append(f"  - 已有: {pending_params}")
        if missing_param:
            lines.append(f"  - 等待补充: {missing_param}")
        lines.append(f"  - 用户现在说: \"{{user_input}}\" ← 请将这句话填入缺失参数")

    # Asset visibility section
    if available_assets:
        asset_section = format_assets_for_prompt(available_assets)
        lines.append(asset_section)

    if available_apps:
        names = [a.get("name", a.get("app_id", "")) for a in available_apps[:5]]
        lines.append(f"【已安装 App】{', '.join(names)}")

    if history:
        lines.append("【最近对话】")
        # Phase H+: Cap total context to avoid gateway timeouts
        total_budget = 2000  # chars
        used = 0
        for msg in reversed(history):
            role = msg.get("role", "")
            content = msg.get("content", "")[:120]
            line = f"  {role}: {content}"
            if used + len(line) > total_budget:
                break
            lines.append(line)
            used += len(line)


    return "\n".join(lines) if lines else "新会话,无历史上下文"


def format_tools_for_prompt(registry_tools: list[Any]) -> str:
    """Format tool registry for prompt."""
    lines = []
    for tool in registry_tools:
        if isinstance(tool, dict):
            name = tool.get("name", "")
            desc = tool.get("description", "")
            params = tool.get("parameters", [])

            if isinstance(params, dict):
                props = params.get("properties", {})
                param_strs = [
                    f"{pn}: {pv.get('description', '')}"
                    for pn, pv in props.items()
                ]
            else:
                param_strs = [
                    f"{p.get('name')}: {p.get('description')}"
                    for p in params
                ]
        else:
            name = getattr(tool, "name", "")
            desc = getattr(tool, "description", "")
            params = getattr(tool, "parameters", [])
            param_strs = [
                f"{getattr(p, 'name', '')}: {getattr(p, 'description', '')}"
                for p in params
            ]

        param_line = ", ".join(param_strs) if param_strs else "无参数"
        lines.append(f"  • {name}: {desc}")
        lines.append(f"    参数: {param_line}")
    return "\n".join(lines)


# ─── System Tool Definitions ────────────────────────────────────────────────

ASK_CLARIFICATION_DEF = ToolDef(
    name="ask_clarification",
    description="当缺少必要参数或需要用户确认时,向用户友好地询问更多信息",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "友好自然的问题,引导用户补充信息",
            },
            "pending_intent": {
                "type": "string",
                "description": "当前正在等待完成的意图名称(如 start_app)",
            },
            "missing_param": {
                "type": "string",
                "description": "缺少的参数名称(如 app_name)",
            },
            "suggested_values": {
                "type": "array",
                "items": {"type": "string"},
                "description": "建议的可能值(如可用 App 列表)",
            },
        },
        "required": ["question", "pending_intent", "missing_param"],
    },
)

UNCLEAR_DEF = ToolDef(
    name="unclear",
    description="当完全无法理解用户意图时使用,给出友好引导",
    parameters={
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "友好的回复文本,引导用户重新表达",
            },
        },
        "required": ["reply"],
    },
)


# ─── Tool Calling Interpreter ───────────────────────────────────────────────

class ToolCallingInterpreter:
    """LLM-driven interpreter with unified tool-aware parsing.

    Phase E.2: All non-trivial intents go through ToolCallingEngine.
    Exact matches (greetings/help) bypass LLM for zero cost.
    Multi-turn continuation via session-scoped pending state.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_calling_engine: ToolCallingEngine,
        memory: Any,
        continuation_service: Any = None,
        hot_tool_manager: Any = None,
        runtime_center: Any = None,
        telemetry_service: Any = None,
    ) -> None:
        self._registry = tool_registry
        self._engine = tool_calling_engine
        self._memory = memory
        self._continuation = continuation_service
        self._hot_tool_manager = hot_tool_manager  # Phase E.2: hot tool support
        self._runtime_center = runtime_center  # For asset visibility in prompt
        self._telemetry_service = telemetry_service

    def interpret(
        self,
        message: str,
        user_id: str,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> InterpretedCommand:
        """Interpret user message with tool-aware LLM fallback.

        Two-tier flow:
          1. Exact match → bypass LLM (greetings, help, status)
          2. Everything else → ToolCallingEngine with full context
        """
        # Tier 1: Exact matches (zero cost)
        exact = self._try_exact_match(message)
        if exact:
            return exact

        # Tier 2: Check pending continuation from memory
        pending = self._get_pending(session_id)
        if pending:
            return self._resume_pending(
                message, pending, user_id, session_id, available_apps
            )

        # Tier 3: Full LLM tool calling
        return self._llm_interpret(
            message, user_id, session_id, available_apps
        )

    # ── Tier 1: Exact matches ──────────────────────────────────────────────

    def _try_exact_match(self, message: str) -> InterpretedCommand | None:
        """Check exact match patterns (greetings, help, status)."""
        # Import here to avoid circular dependency
        from app.system.gateway.light_brain_interpreter import LightBrainInterpreter

        for intent, pattern, _ in LightBrainInterpreter.EXACT_MATCH_PATTERNS:
            if pattern.match(message.strip()):
                return InterpretedCommand(
                    intent=intent,
                    raw_input=message,
                    confidence=1.0,
                    parameters={},
                    source="exact_match",
                )
        return None

    # ── Tier 2: Pending continuation ─────────────────────────────────────

    def _get_pending(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve pending state from memory or continuation service."""
        # Try continuation service first (unified layer)
        if self._continuation:
            try:
                cont = self._continuation.get_active(session_id)
                if cont and cont.kind.value.startswith("missing_"):
                    return {
                        "intent": cont.original_intent,
                        "params": dict(cont.original_params or {}),
                        "missing": [p.param_name for p in (cont.missing_params or [])],
                    }
            except Exception:
                pass

        # Fallback: check memory's pending_continuation
        if hasattr(self._memory, "get_pending_continuation"):
            try:
                return self._memory.get_pending_continuation(session_id)
            except Exception:
                pass

        return None

    def _resume_pending(
        self,
        message: str,
        pending: dict[str, Any],
        user_id: str,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> InterpretedCommand:
        """Handle user answering a pending clarification question."""
        pending_intent = pending.get("intent", pending.get("pending_intent"))
        missing_list = pending.get("missing", [])
        first_missing = missing_list[0] if missing_list else "value"

        # Build filled params - user input fills the first missing param
        filled_params = dict(pending.get("params", {}))
        filled_params[first_missing] = message.strip()

        # Clear pending state
        self._clear_pending(session_id)

        # Re-run LLM with the filled params to verify and get full command
        return InterpretedCommand(
            intent=pending_intent,
            raw_input=message,
            confidence=0.85,
            parameters=filled_params,
            source="continuation_resume",
            requires_clarification=False,
        )

    def _clear_pending(self, session_id: str) -> None:
        """Clear pending state after successful resume."""
        if self._continuation:
            try:
                self._continuation.clear(session_id)
            except Exception:
                pass
        if hasattr(self._memory, "clear_pending_continuation"):
            try:
                self._memory.clear_pending_continuation(session_id)
            except Exception:
                pass

    # ── Tier 3: LLM tool calling ─────────────────────────────────────────

    def _llm_interpret(
        self,
        message: str,
        user_id: str,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> InterpretedCommand:
        """Full LLM interpretation with tool registry context."""
        # Get history
        history = self._get_history(session_id)

        # Get available assets from RuntimeCenter (for prompt visibility)
        available_assets = []
        if self._runtime_center:
            try:
                for asset in self._runtime_center.list_assets():
                    available_assets.append({
                        "asset_id": asset.asset_id,
                        "description": getattr(asset, "description", ""),
                        "capabilities": [
                            {"method": cap.name, "description": cap.description or ""}
                            for cap in (asset.capabilities or [])[:5]
                        ],
                    })
            except Exception as e:
                logger.debug("Failed to get assets from RuntimeCenter: %s", e)

        # Build prompt components
        session_ctx = build_session_context(
            history=history,
            pending_intent=None,
            pending_params={},
            missing_param=None,
            available_apps=available_apps,
            available_assets=available_assets if available_assets else None,
        )
        # Phase E.2: Use hot tools instead of full registry
        if self._hot_tool_manager and session_id:
            hot_tools = self._hot_tool_manager.get_tools_for_session(session_id)
            tools_desc = format_tools_for_prompt(hot_tools)
        else:
            tools_desc = format_tools_for_prompt(self._registry.list_all())

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            session_context=session_ctx,
            tools_description=tools_desc,
        )

        # Phase E.2: Use hot tools + find_tool as escape hatch
        # Restore hot_tool_manager usage
        if self._hot_tool_manager and session_id:
            hot_tools = self._hot_tool_manager.get_tools_for_session(session_id)
            registry_tools = self._build_tool_defs_from_hot(hot_tools)
        else:
            registry_tools = self._build_tool_defs()
        all_tools = registry_tools + [ASK_CLARIFICATION_DEF, UNCLEAR_DEF]

        # Execute - 恢复多轮工具调用,但避免回灌 provider 不兼容的 tool_call 历史 shape
        try:
            interaction_id = f"lightbrain:{session_id}:{abs(hash(message))}"
            result = self._engine.execute_turns(
                skill_id="gateway_intent_parser",
                system_prompt=system_prompt,
                user_message=message,
                tools=all_tools,
                max_turns=20,
                asset_id="asset:light_brain_gateway:v1",
                session_id=session_id,
                user_id=user_id,
                interaction_id=interaction_id,
            )
            logger.info(f"ToolCallingEngine result: final_text={result.final_text[:100] if result.final_text else 'empty'}, tool_calls={[t.tool_name for t in result.tool_calls] if result.tool_calls else 'none'}")
        except Exception as e:
            logger.exception("ToolCallingEngine execution failed")
            raise

        return self._process_result(result, message)

    def _build_tool_defs_from_hot(
        self,
        hot_tools: list[dict[str, Any]],
    ) -> list[ToolDef]:
        """Build ToolDef objects from hot tools list (Phase E.2)."""
        tool_defs = []
        for tool in hot_tools:
            # Skip special tools (ask_clarification, unclear) - added separately
            if tool.get("name") in ("ask_clarification", "unclear"):
                continue
            schema = {
                "type": "object",
                "properties": {},
                "required": [],
            }
            params = tool.get("parameters", {})
            if isinstance(params, dict) and "properties" in params:
                # Already structured
                schema = params
            elif isinstance(params, list):
                # Legacy list format
                for p in params:
                    name = p.get("name", "")
                    schema["properties"][name] = {
                        "type": p.get("type", "string"),
                        "description": p.get("description", ""),
                    }
                    if p.get("enum"):
                        schema["properties"][name]["enum"] = p["enum"]
                    if p.get("required", True):
                        schema["required"].append(name)

            tool_defs.append(ToolDef(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                parameters=schema,
            ))
        return tool_defs

    def _build_tool_defs(self) -> list[ToolDef]:
        """Convert registry tools to ToolDef."""
        tool_defs = []
        for tool in self._registry.list_all():
            # ToolDefinition is an object, not a dict
            schema = {
                "type": "object",
                "properties": {},
                "required": [],
            }
            for p in getattr(tool, "parameters", []):
                name = getattr(p, "name", "")
                schema["properties"][name] = {
                    "type": getattr(p, "type", "string"),
                    "description": getattr(p, "description", ""),
                }
                enum_vals = getattr(p, "enum", None)
                if enum_vals:
                    schema["properties"][name]["enum"] = enum_vals
                if getattr(p, "required", True):
                    schema["required"].append(name)

            tool_defs.append(ToolDef(
                name=getattr(tool, "name", ""),
                description=getattr(tool, "description", ""),
                parameters=schema,
            ))
        return tool_defs

    def _process_result(
        self,
        result: Any,
        raw_input: str,
    ) -> InterpretedCommand:
        """Convert ToolCallingEngine result to InterpretedCommand."""
        if not result.tool_calls:
            # LLM responded directly (no tool needed, e.g. "好的,我来...")
            return InterpretedCommand(
                intent="direct_response",
                raw_input=raw_input,
                confidence=0.6,
                parameters={"text": result.final_text},
                source="llm_text",
            )

        call = result.tool_calls[0]
        tool_name = call.tool_name
        tool_args = call.args or {}

        if tool_name == "ask_clarification":
            self._store_pending(
                raw_input=raw_input,
                intent=tool_args.get("pending_intent", "unknown"),
                missing_param=tool_args.get("missing_param", "unknown"),
                suggested=tool_args.get("suggested_values", []),
            )
            return InterpretedCommand(
                intent="clarification_pending",
                raw_input=raw_input,
                confidence=0.8,
                parameters={
                    "question": tool_args.get("question", "需要更多信息"),
                    "pending_intent": tool_args.get("pending_intent"),
                    "missing_param": tool_args.get("missing_param"),
                    "suggested_values": tool_args.get("suggested_values", []),
                },
                source="llm_clarification",
                requires_clarification=True,
                clarification_question=tool_args.get("question"),
            )

        if tool_name == "unclear":
            return InterpretedCommand(
                intent="unclear",
                raw_input=raw_input,
                confidence=0.4,
                parameters={"reply": tool_args.get("reply", "我没理解你的意思,换个说法试试?")},
                source="llm_unclear",
            )

        # Normal tool call → map to direct_response (pass through LLM-generated content)
        # The tool execution result is already in final_text from the last LLM turn
        return InterpretedCommand(
            intent="direct_response",
            raw_input=raw_input,
            confidence=0.9,
            parameters={"text": result.final_text or f"已执行 {tool_name}"},
            source="llm_tool_call",
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Get recent message history for context."""
        try:
            if hasattr(self._memory, "get_recent_messages"):
                return self._memory.get_recent_messages(session_id, limit=6)
            session = self._memory.get_session(session_id)
            if session:
                return getattr(session, "messages", [])[-6:]
        except Exception:
            pass
        return []

    def _store_pending(
        self,
        raw_input: str,
        intent: str,
        missing_param: str,
        suggested: list[str],
    ) -> None:
        """Store pending state for multi-turn continuation."""
        session_id = getattr(self._memory, "_last_session_id", "default")

        # Try continuation service
        if self._continuation:
            try:
                from app.models.continuation import (
                    ContinuationKind,
                    MissingParamSpec,
                    ContinuationResumeRequest,
                )
                self._continuation.create_missing_parameter_continuation(
                    session_id=session_id,
                    original_intent=intent,
                    original_params={},
                    missing_params=[MissingParamSpec(
                        param_name=missing_param,
                        description=f"missing param: {missing_param}",
                    )],
                )
                return
            except Exception as e:
                logger.warning(f"Continuation service store failed: {e}")

        # Fallback: memory
        if hasattr(self._memory, "store_pending_continuation"):
            try:
                self._memory.store_pending_continuation(session_id, {
                    "intent": intent,
                    "missing_param": missing_param,
                    "suggested_values": suggested,
                    "user_input": raw_input,
                })
            except Exception as e:
                logger.warning(f"Memory pending store failed: {e}")
