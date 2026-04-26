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
import re
from typing import Any

from app.models.chat import InterpretedCommand
from app.services.tool_registry import ToolRegistry
from app.services.tool_calling_engine import ToolCallingEngine, ToolDef


TOOL_LOOP_GOVERNOR_PATH = "docs/tool-loop-governor.md"
REPO_INTROSPECTION_BRANCH_PATH = "docs/tool-loop-governor-branches/repo-introspection.md"
SCRIPT_FIRST_BRANCH_PATH = "docs/tool-loop-governor-branches/script-first-strategy.md"


INTROSPECTION_KEYWORDS = (
    "代码", "源码", "仓库", "持久化", "sqlite", "mysql", "json", "字段", "表结构", "默认值", "文件里"
)

PATH_PATTERN = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|md|yaml|yml|json|toml|ini))")


logger = logging.getLogger(__name__)


# ─── Prompt Templates ────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """你是 AgentSystem 的智能交互引擎。

你的职责是根据用户输入选择合适工具,并基于工具结果生成友好回复。

## 当前会话状态
{session_context}

## 可用工具
{tools_description}

## 工具循环总控
{tool_loop_governor}

## 当前分支策略
{branch_guidance}

## 最小执行纪律
1. 每一轮优先选择一个最高价值工具,不要在同一轮规划大量工具
2. 候选线索不是结论; 证据足够才回答
3. 如果下一步明显依赖上一步输出,优先考虑脚本方案
4. 每次工具调用后先判断: 还缺什么? 是否已够回答? 是否该转脚本?
5. 对遍历、聚合、批量提取类任务,当普通文件工具连续多轮仍未收敛时,优先改用 `exec_shell` 编写并执行一次性本地脚本
6. 证据已足够时立刻停止调用并回答; 不足时明确未解决问题
7. 缺少必要参数时用 `ask_clarification`; 无法理解时用 `unclear`
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




def build_turn_state_board(message: str, history: list[dict[str, Any]]) -> str:
    recent_user = [m.get("content", "") for m in history if m.get("role") == "user"][-2:]
    recent_assistant = [m.get("content", "") for m in history if m.get("role") == "assistant"][-1:]
    unresolved = message.strip()
    known = " | ".join(x[:80] for x in recent_user) if recent_user else "(暂无明确既有证据)"
    recent_reply = recent_assistant[0][:120] if recent_assistant else "(暂无近期回复)"
    text = (message or "").lower()
    is_script_shape = is_script_like_request(message)
    if any(keyword in text for keyword in INTROSPECTION_KEYWORDS):
        next_action = "优先选择一个最高价值的定位或读取动作，不要同轮规划多个工具"
        stop_condition = "拿到能回答用户当前精度的直接证据后立即停止"
    elif is_script_shape:
        next_action = "优先判断是否应该转为脚本方案"
        stop_condition = "一旦脚本比碎片工具链更合适，就切换策略"
    else:
        next_action = "选择一个最高价值下一步动作"
        stop_condition = "当前问题已可回答时立即停止"
    escalation = ""
    if is_script_shape and any(marker in recent_reply for marker in ("[Reached max turns", "未完成", "继续搜索")):
        escalation = "\n- 升级规则: 近期已出现未收敛信号，本轮优先使用 exec_shell 执行一次性脚本聚合，而不是继续零碎搜索"
    return (
        "[当前状态板]\n"
        f"- 当前未解决问题: {unresolved}\n"
        f"- 最近相关上下文: {known}\n"
        f"- 最近系统回复: {recent_reply}\n"
        f"- 下一步建议: {next_action}\n"
        f"- 停止条件: {stop_condition}"
        f"{escalation}"
    )


def is_script_like_request(message: str) -> bool:
    text = (message or "").lower()
    return any(keyword in text for keyword in ("脚本", "script", "批量", "遍历", "聚合", "解析", "提取", "汇总"))


def choose_turn_budget(message: str) -> int:
    text = (message or "").lower()
    if any(keyword in text for keyword in INTROSPECTION_KEYWORDS):
        return 8
    if is_script_like_request(message):
        return 10
    return 20


def narrow_tools_for_script_route(tools: list[ToolDef]) -> list[ToolDef]:
    allowed = {"exec_shell", "read_file", "write_file", "edit_file", "ask_clarification", "unclear"}
    narrowed = [tool for tool in tools if tool.name in allowed]
    return narrowed or tools


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

        # Tier 2.5: explicit file-path introspection fast path
        fast_path = self._try_explicit_file_read_fast_path(
            message=message,
            user_id=user_id,
            session_id=session_id,
            available_apps=available_apps,
        )
        if fast_path:
            return fast_path

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

    def _load_governor_text(self, relative_path: str) -> str:
        try:
            with open(relative_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.warning("Failed to load governor text %s: %s", relative_path, e)
            return ""

    def _select_branch_guidance(self, message: str) -> str:
        text = (message or "").lower()
        if any(keyword in text for keyword in INTROSPECTION_KEYWORDS):
            return self._load_governor_text(REPO_INTROSPECTION_BRANCH_PATH)
        if any(keyword in text for keyword in ("脚本", "script", "批量", "遍历", "聚合", "解析", "提取")):
            return self._load_governor_text(SCRIPT_FIRST_BRANCH_PATH)
        return ""


    def _try_explicit_file_read_fast_path(
        self,
        message: str,
        user_id: str,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> InterpretedCommand | None:
        return None

    def _is_code_introspection_query(self, raw_input: str) -> bool:
        text = (raw_input or "").lower()
        return any(keyword in text for keyword in INTROSPECTION_KEYWORDS)

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

        branch_guidance = self._select_branch_guidance(message)
        turn_state_board = build_turn_state_board(message, history)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            session_context=session_ctx,
            tools_description=tools_desc,
            tool_loop_governor=self._load_governor_text(TOOL_LOOP_GOVERNOR_PATH),
            branch_guidance=(branch_guidance + "\n\n" + turn_state_board) if branch_guidance else turn_state_board,
        )

        # Phase E.2: Use hot tools + find_tool as escape hatch
        # Restore hot_tool_manager usage
        if self._hot_tool_manager and session_id:
            hot_tools = self._hot_tool_manager.get_tools_for_session(session_id)
            registry_tools = self._build_tool_defs_from_hot(hot_tools)
        else:
            registry_tools = self._build_tool_defs()
        all_tools = registry_tools + [ASK_CLARIFICATION_DEF, UNCLEAR_DEF]
        if is_script_like_request(message):
            all_tools = narrow_tools_for_script_route(all_tools)

        # Execute - 恢复多轮工具调用,但避免回灌 provider 不兼容的 tool_call 历史 shape
        try:
            interaction_id = f"lightbrain:{session_id}:{abs(hash(message))}"
            result = self._engine.execute_turns(
                skill_id="gateway_intent_parser",
                system_prompt=system_prompt,
                user_message=message,
                tools=all_tools,
                max_turns=choose_turn_budget(message),
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
            final_text = self._apply_execution_fact_provenance(raw_input=raw_input, result=result)
            return InterpretedCommand(
                intent="direct_response",
                raw_input=raw_input,
                confidence=0.6,
                parameters={"text": final_text},
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

        final_text = self._apply_execution_fact_provenance(raw_input=raw_input, result=result)

        return InterpretedCommand(
            intent="direct_response",
            raw_input=raw_input,
            confidence=0.9,
            parameters={"text": final_text or f"已执行 {tool_name}"},
            source="llm_tool_call",
        )

    def _apply_execution_fact_provenance(self, raw_input: str, result: Any) -> str:
        """Temporary pass-through until a tool-agnostic governance module is introduced."""
        return (getattr(result, "final_text", "") or "").strip()

    def _is_code_introspection_query(self, raw_input: str) -> bool:
        return False

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
