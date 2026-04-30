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
from datetime import UTC, datetime

from typing import Any

from app.models.chat import InterpretedCommand
from app.models.cognition import SelfModel, StructuredAnswer, StructuredClaim
from app.models.telemetry import StepTelemetryRecord
from app.services.tool_registry import ToolRegistry
from app.services.tool_calling_engine import ToolCallingEngine, ToolDef
from app.system.gateway.scan_profiles import derive_scan_profile
from app.system.runtime_asset_formatter import render_asset_method_catalog
from app.tools.internal_tools import exec_shell


TOOL_LOOP_GOVERNOR_PATH = "docs/tool-loop-governor.md"
REPO_INTROSPECTION_BRANCH_PATH = "docs/tool-loop-governor-branches/repo-introspection.md"
SCRIPT_FIRST_BRANCH_PATH = "docs/tool-loop-governor-branches/script-first-strategy.md"

SELF_ITERATION_BRANCH_GUIDANCE = """你正在处理系统自我迭代 / 治理 / 回归 / 待优化相关问题。

优先策略:
1. 先把这类问题视为运行时资产导航问题,不是仓库代码检索问题
2. 默认优先关注 `asset:self_iteration_center:v1`
3. 第一跳优先选择以下动作之一:
   - `query_asset_info(asset_id=\"asset:self_iteration_center:v1\")`
   - `query_asset_detail(asset_id=\"asset:self_iteration_center:v1\")`
   - `call_asset_method(asset_id=\"asset:self_iteration_center:v1\", method=\"get_self_iteration_strategy_overview\", params={})`
4. 只有当 self_iteration_center 返回的信息仍不足以回答问题时,才考虑扩展到其他资产
5. 不要把这类问题默认降级成文件搜索、仓库搜索或 bash 历史检索
6. 如果用户问的是最近状态、治理风险、回归观察、待优化项,优先从 strategy overview 或 self-iteration asset summary 直接回答

停止条件:
- 一旦 self_iteration_center 已给出足够的摘要或下一步建议,立即停止继续找文件,直接组织回答
"""


INTROSPECTION_KEYWORDS = (
    "代码", "源码", "仓库", "持久化", "sqlite", "mysql", "json", "字段", "表结构", "默认值", "文件里"
)

PATH_PATTERN = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|md|yaml|yml|json|toml|ini))")


logger = logging.getLogger(__name__)


# ─── Prompt Templates ────────────────────────────────────────────────────────

SCRIPT_FIRST_EXECUTION_PROMPT = """你正在执行专用 script-first 子链路。

目标:
- 对遍历、聚合、批量提取类任务，优先用一次性本地脚本完成证据收集
- 不要回到宽泛搜索循环

已知事实:
- 当前分支明确提供 `exec_shell` 工具，可直接调用
- 不要声称没有 `exec_shell` 权限，除非工具调用返回了真实报错
- 默认第一步应调用 `exec_shell`，而不是把脚本交给用户手动执行

硬规则:
1. 第一优先工具是 `exec_shell`
2. 如需补充极少量上下文，可先 `read_file` 读取 1 个关键文件，然后立即回到 `exec_shell`
3. 禁止先做多轮 search/list/read 链式探索
4. 脚本应尽量短、小、可审计，优先使用 python3 - <<'PY' 形式
5. 脚本输出应直接面向用户问题所需的结构化汇总
6. 若无真实工具报错，不要改为让用户手动执行
7. 一旦脚本结果足够回答，立即停止工具调用并直接作答

默认脚本骨架偏好:
- 使用 `python3 - <<'PY'`
- 遍历目标目录
- 过滤目标文件
- 提取与用户问题直接相关的定义
- 打印精简汇总结果
"""

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
    return render_asset_method_catalog(
        assets,
        header="【系统资产】",
        footer="调用资产方法: 使用 call_asset_method(asset_id, method, params)",
        max_items=5,
        overflow_template="  • ... 还有 {extra} 个资产",
    )


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


def is_self_iteration_like_request(message: str) -> bool:
    text = (message or "").lower()
    return any(keyword in text for keyword in ("自我迭代", "治理", "回归", "待优化", "evolution", "governance", "regression", "backlog"))


def choose_turn_budget(message: str) -> int:
    text = (message or "").lower()
    if any(keyword in text for keyword in INTROSPECTION_KEYWORDS):
        return 8
    if is_script_like_request(message):
        return 10
    if is_self_iteration_like_request(message):
        return 4
    return 6


def narrow_tools_for_self_iteration_route(tools: list[ToolDef]) -> list[ToolDef]:
    allowed = {"call_asset_method", "query_asset_detail", "list_assets", "query_asset_info", "ask_clarification", "unclear"}
    narrowed = [tool for tool in tools if tool.name in allowed]
    return narrowed or tools


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

        if is_script_like_request(message):
            return self._run_script_first_route(message, user_id, session_id, available_apps)

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
        if is_self_iteration_like_request(message):
            return SELF_ITERATION_BRANCH_GUIDANCE
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

    def _run_deterministic_script_prestep(
        self,
        message: str,
        user_id: str,
        session_id: str,
    ) -> InterpretedCommand | None:
        profile = derive_scan_profile(message)
        if not profile:
            return None
        scan_roots = profile.get("scan_roots", ["app"])
        file_extensions = profile.get("file_extensions", [".py"])
        max_files = int(profile.get("max_files", 200))
        max_hits_per_file = int(profile.get("max_hits_per_file", 12))
        max_rows = int(profile.get("max_rows", 20))
        regex = profile["regex"]
        summary_focus = profile.get("summary_focus", "仅基于脚本命中结果做汇总")
        output_template = profile.get("output_template", "优先使用简洁小节或表格，最后明确未证实点")
        roots_json = json.dumps(scan_roots, ensure_ascii=False)
        exts_json = json.dumps(file_extensions, ensure_ascii=False)
        command = f"""python3 - <<'PY'
import os, re, json
roots=json.loads(r'''{roots_json}''')
exts=set(json.loads(r'''{exts_json}'''))
max_files={max_files}
max_hits_per_file={max_hits_per_file}
max_rows={max_rows}
pattern=re.compile(r'''{regex}''', re.I)
rows=[]
seen=set()
files_scanned=0
for root in roots:
    if not os.path.exists(root):
        continue
    if os.path.isfile(root):
        candidates=[root]
    else:
        candidates=[]
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith('__')]
            for filename in filenames:
                candidates.append(os.path.join(dirpath, filename))
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if files_scanned >= max_files:
            continue
        if exts and not any(path.endswith(ext) for ext in exts):
            continue
        try:
            with open(path,'r',encoding='utf-8',errors='replace') as f:
                content=f.read()
            files_scanned += 1
        except Exception:
            continue
        if not pattern.search(content):
            continue
        hits=[]
        for i,line in enumerate(content.splitlines(), start=1):
            s=line.strip()
            if pattern.search(s):
                hits.append({{'line': i, 'text': s[:220]}})
            if len(hits) >= max_hits_per_file:
                break
        if hits:
            rows.append({{'file': path, 'hits': hits}})
        if len(rows) >= max_rows:
            break
print(json.dumps(rows[:max_rows], ensure_ascii=False))
PY"""
        script_started = datetime.now(UTC)
        prestep = exec_shell(command=command, workdir="/root/project/AgentSystem", timeout=60)
        script_latency_ms = int((datetime.now(UTC) - script_started).total_seconds() * 1000)
        if not prestep.get("success"):
            self._record_deterministic_prestep_telemetry(
                session_id=session_id,
                profile=profile,
                script_latency_ms=script_latency_ms,
                summarizer_latency_ms=0,
                success=False,
                fallback=True,
                error_code="exec_shell_failed",
            )
            return None
        try:
            parsed_rows = json.loads(prestep.get("stdout", "[]") or "[]")
            row_count = len(parsed_rows) if isinstance(parsed_rows, list) else None
        except Exception:
            row_count = None
        summarizer_started = datetime.now(UTC)
        result = self._engine.execute_turns(
            skill_id="gateway_script_prestep_summarizer",
            system_prompt=(
                "你会收到一个已经执行成功的本地脚本结果(JSON)。"
                "你的任务是仅基于该结果做简洁汇总。"
                "不要声称没有工具权限，不要要求用户手动执行。"
                "若证据不足，要明确说仅基于脚本命中结果汇总。"
                f"本次汇总重点: {summary_focus}。"
                f"输出模板要求: {output_template}。"
                "不要超出命中结果做额外架构推断。"
                "默认输出必须是 JSON 对象，字段至少包含 claim, evidence, unverified_points, confidence。"
                "claim 必须是对象，含 text, evidence_grade, confidence。"
                "evidence 必须是数组，只能复述脚本结果中已有的命中。"
                "unverified_points 必须列出未确认之处。"
                "若无法形成充分结论，也必须返回合法 JSON，而不是普通文本。"
            ),
            user_message=(
                f"用户问题: {message}\n\n"
                f"脚本结果(JSON):\n{prestep.get('stdout','')}"
            ),
            tools=[],
            max_turns=1,
            asset_id="asset:light_brain_gateway:v1",
            session_id=session_id,
            user_id=user_id,
            interaction_id=f"lightbrain-script-prestep:{session_id}:{abs(hash(message))}",
        )
        summarizer_latency_ms = int((datetime.now(UTC) - summarizer_started).total_seconds() * 1000)
        self._record_deterministic_prestep_telemetry(
            session_id=session_id,
            profile=profile,
            script_latency_ms=script_latency_ms,
            summarizer_latency_ms=summarizer_latency_ms,
            success=True,
            fallback=False,
            result_rows=row_count,
        )
        return self._process_result(result, message)

    def _record_deterministic_prestep_telemetry(
        self,
        *,
        session_id: str,
        profile: dict[str, Any],
        script_latency_ms: int,
        summarizer_latency_ms: int,
        success: bool,
        fallback: bool,
        result_rows: int | None = None,
        error_code: str | None = None,
    ) -> None:
        if self._telemetry_service is None:
            return
        self._telemetry_service.record_step(
            StepTelemetryRecord(
                interaction_id=f"lightbrain-script-prestep:{session_id}",
                step_id=f"deterministic-prestep:{profile.get('name', 'unknown')}",
                step_type="system",
                name="deterministic_script_prestep",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                latency_ms=script_latency_ms + summarizer_latency_ms,
                success=success,
                error_code=error_code,
                payload_summary={
                    "profile": profile.get("name"),
                    "profile_hit": True,
                    "script_latency_ms": script_latency_ms,
                    "summarizer_latency_ms": summarizer_latency_ms,
                    "fallback": fallback,
                    "fallback_count": 1 if fallback else 0,
                    "overreach_risk": result_rows is None or result_rows == 0,
                    "verification_outcome": "bounded_summary" if success else "fallback",
                    "result_rows": result_rows,
                    "max_files": profile.get("max_files"),
                    "max_hits_per_file": profile.get("max_hits_per_file"),
                    "max_rows": profile.get("max_rows"),
                },
            ),
            app_id="light_brain_gateway",
        )

    def _run_script_first_route(
        self,
        message: str,
        user_id: str,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> InterpretedCommand:
        deterministic = self._run_deterministic_script_prestep(message, user_id, session_id)
        if deterministic:
            return deterministic

        history = self._get_history(session_id)
        session_ctx = build_session_context(
            history=history,
            pending_intent=None,
            pending_params={},
            missing_param=None,
            available_apps=available_apps,
            available_assets=None,
        )
        script_tools = narrow_tools_for_script_route(self._build_tool_defs() + [ASK_CLARIFICATION_DEF, UNCLEAR_DEF])
        system_prompt = (
            SCRIPT_FIRST_EXECUTION_PROMPT
            + "\n\n## 当前会话状态\n"
            + session_ctx
            + "\n\n## 当前任务\n"
            + message
        )
        result = self._engine.execute_turns(
            skill_id="gateway_script_first_route",
            system_prompt=system_prompt,
            user_message=message,
            tools=script_tools,
            max_turns=4,
            asset_id="asset:light_brain_gateway:v1",
            session_id=session_id,
            user_id=user_id,
            interaction_id=f"lightbrain-script:{session_id}:{abs(hash(message))}",
        )
        return self._process_result(result, message)

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
            prompt_tool_defs = self._build_tool_defs_from_hot(hot_tools)
        else:
            prompt_tool_defs = self._build_tool_defs()

        if is_script_like_request(message):
            prompt_tool_defs = narrow_tools_for_script_route(prompt_tool_defs + [ASK_CLARIFICATION_DEF, UNCLEAR_DEF])
        elif is_self_iteration_like_request(message):
            prompt_tool_defs = narrow_tools_for_self_iteration_route(prompt_tool_defs + [ASK_CLARIFICATION_DEF, UNCLEAR_DEF])
        else:
            prompt_tool_defs = prompt_tool_defs + [ASK_CLARIFICATION_DEF, UNCLEAR_DEF]

        tools_desc = format_tools_for_prompt(prompt_tool_defs)

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
        elif is_self_iteration_like_request(message):
            all_tools = narrow_tools_for_self_iteration_route(all_tools)

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
            structured_answer = self._build_structured_answer(raw_input, result, final_text, 0.6)
            return InterpretedCommand(
                intent="direct_response",
                raw_input=raw_input,
                confidence=0.6,
                parameters={"text": final_text},
                source="llm_text",
                structured_answer=structured_answer,
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

        final_payload = final_text or f"已执行 {tool_name}"
        structured_answer = self._build_structured_answer(raw_input, result, final_payload, 0.9)
        return InterpretedCommand(
            intent="direct_response",
            raw_input=raw_input,
            confidence=0.9,
            parameters={"text": final_payload},
            source="llm_tool_call",
            structured_answer=structured_answer,
        )

    def _apply_execution_fact_provenance(self, raw_input: str, result: Any) -> str:
        """Temporary pass-through until a tool-agnostic governance module is introduced."""
        return (getattr(result, "final_text", "") or "").strip()

    def _build_structured_answer(self, raw_input: str, result: Any, final_text: str, confidence: float) -> StructuredAnswer:
        payload = None
        parsed_claim = final_text
        parsed_confidence = confidence
        parsed_unverified: list[str] = []
        evidence_items = getattr(result, "evidence_items", []) or []
        evidence = []
        grade_rank = {"none": 0, "hint": 1, "excerpt": 2, "verified_fact": 3, "runtime_observation": 4}
        claim_grade = "none"

        def _clamp_conf(value: Any, default: float) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except Exception:
                return default

        def _normalize_evidence_grade(value: Any) -> str:
            val = str(value or "none")
            return val if val in grade_rank else "none"

        def _fallback_text_payload(text: str) -> dict[str, Any]:
            return {
                "claim": {
                    "text": text,
                    "evidence_grade": "none",
                    "confidence": confidence,
                },
                "evidence": [],
                "unverified_points": ["结构化结果缺失或无效，已回退为保守文本结论"],
                "confidence": confidence,
            }

        try:
            maybe = json.loads(final_text) if final_text.strip().startswith("{") else None
            if isinstance(maybe, dict) and any(k in maybe for k in ("claim", "evidence", "unverified_points", "confidence")):
                payload = maybe
        except Exception:
            payload = _fallback_text_payload(final_text)

        if payload is not None:
            claim_payload = payload.get("claim", {}) if isinstance(payload.get("claim"), dict) else {}
            parsed_claim = str(claim_payload.get("text") or payload.get("text") or final_text or "")
            claim_grade = _normalize_evidence_grade(claim_payload.get("evidence_grade") or payload.get("evidence_grade") or "none")
            parsed_confidence = _clamp_conf(claim_payload.get("confidence") or payload.get("confidence") or confidence, confidence)
            parsed_unverified = [str(x) for x in (payload.get("unverified_points") or []) if str(x).strip()][:5]
            for item in (payload.get("evidence") or [])[:5]:
                if isinstance(item, dict):
                    evidence.append({
                        "grade": _normalize_evidence_grade(item.get("grade")),
                        "source_type": str(item.get("source_type", "")),
                        "source_ref": str(item.get("source_ref", "")),
                        "snippet": str(item.get("snippet", "")),
                        "supports_claims": item.get("supports_claims", []),
                    })
            if not parsed_claim.strip():
                parsed_claim = str(final_text or "")
            if claim_grade in ("none", "hint") and not parsed_unverified:
                parsed_unverified.append("当前结论仍受限于现有观测与证据等级")
        else:
            if evidence_items:
                claim_grade = max((_normalize_evidence_grade(getattr(item, "grade", "none")) for item in evidence_items), key=lambda g: grade_rank.get(g, 0))
                for item in evidence_items[:5]:
                    evidence.append({
                        "grade": _normalize_evidence_grade(getattr(item, "grade", "none")),
                        "source_type": getattr(item, "source_type", ""),
                        "source_ref": getattr(item, "source_ref", ""),
                        "snippet": getattr(item, "snippet", ""),
                        "supports_claims": getattr(item, "supports_claims", []),
                    })
            if claim_grade in ("none", "hint"):
                parsed_unverified.append("当前结论仍受限于现有观测与证据等级")

        is_introspection = self._is_code_introspection_query(raw_input)
        answer_mode = "direct"
        verification_mode = "none"
        capability_state = "direct"
        tool_dependence_state = "optional"
        uncertainty_state = ""

        if is_introspection:
            capability_state = "tool_required"
            tool_dependence_state = "required"
            if claim_grade in ("none", "hint"):
                answer_mode = "verification_required"
                verification_mode = "required"
                uncertainty_state = "需先观测或验证"
            else:
                answer_mode = "tool_required"
                verification_mode = "light" if claim_grade == "excerpt" else "none"
        elif parsed_unverified:
            answer_mode = "clarification_required" if parsed_confidence < 0.5 else "verification_required"
            verification_mode = "light"
            capability_state = "verification_required" if answer_mode == "verification_required" else "direct"

        self_model = SelfModel(
            capability_state=capability_state,
            tool_dependence_state=tool_dependence_state,
            confidence_state=parsed_confidence,
            uncertainty_state=uncertainty_state,
            answer_mode=answer_mode,
            verification_mode=verification_mode,
        )
        claim = StructuredClaim(text=parsed_claim, evidence_grade=claim_grade, confidence=parsed_confidence)
        return StructuredAnswer(
            self_model=self_model,
            claim=claim,
            evidence=evidence,
            unverified_points=parsed_unverified,
            text=parsed_claim,
        )

    def _is_code_introspection_query(self, raw_input: str) -> bool:
        text = (raw_input or "").lower()
        return any(keyword in text for keyword in INTROSPECTION_KEYWORDS)

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
