"""Tool Calling Prompt Builders - pure functions for prompt construction.

Extracted from tool_calling_interpreter to keep the interpreter class focused
on orchestration while prompt-building concerns live here.
"""
from __future__ import annotations

from typing import Any

from app.models.chat import InterpretedCommand
from app.system.runtime_asset_formatter import render_asset_method_catalog
from app.ai.tool_calling_engine import ToolDef

INTROSPECTION_KEYWORDS = (
    "代码", "源码", "仓库", "持久化", "sqlite", "mysql", "json", "字段", "表结构", "默认值", "文件里",
    "接口行为", "接口", "asset", "方法", "调用链"
)

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
    session_id: str | None = None,
    app_system_prompt: str | None = None,
    model_input_view: Any | None = None,
) -> str:
    """Build readable session context for prompt.

    如果提供 model_input_view（ModelInputView），优先使用其 context_text
    代替 history 列表格式化，以支持上下文压缩和窗口控制。
    """
    lines = []

    # App system prompt at the TOP — always visible regardless of history length
    if app_system_prompt:
        lines.append("【App 上下文】")
        lines.append(app_system_prompt)
        lines.append("")

    # 使用 ModelInputView 替代原始 history 格式化
    if model_input_view is not None:
        # Continuation guidance (缩短版，因为 model_input_view 已包含上下文)
        if model_input_view.total_turns > 0:
            lines.append("【对话延续性提示】")
            lines.append("当前消息大概率是上一轮对话的延续。请先判断是否与上轮相关：")
            lines.append("  - 若是延续，基于【对话上下文】中的信息作答")
            lines.append("  - 若是新话题，忽略历史上下文并直接处理当前请求")
            lines.append("")

        # 插入 ModelInputView 构建的上下文
        lines.append("【对话上下文】")
        lines.append(model_input_view.context_text)

        # 如果发生了压缩，添加 expand 提示
        if model_input_view.compressed and model_input_view.expand_hint:
            lines.append("")
            lines.append(model_input_view.expand_hint)

    else:
        # ── 原有逻辑：传统 history 列表格式化 ──
        if history:
            lines.append("【对话延续性提示】")
            lines.append("当前消息大概率是上一轮对话的延续。请先判断是否与上轮相关：")
            lines.append("  - 若是延续，基于【最近对话】中的上下文作答，不要重复问已明确的事实")
            lines.append("  - 若是新话题，忽略历史上下文并直接处理当前请求")
            lines.append("")

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
            recent_history = list(reversed(history[-10:]))
            for msg in recent_history:
                role = msg.get("role", "")
                content = msg.get("content", "") or ""
                lines.append(f"  {role}: {content}")


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
    known_raw = " | ".join(x[:400] for x in recent_user) if recent_user else "(暂无明确既有证据)"
    known = known_raw + (" ...[截断]" if any(len(x) > 400 for x in recent_user) else "")
    recent_reply_raw = recent_assistant[0][:500] if recent_assistant else "(暂无近期回复)"
    recent_reply = recent_reply_raw + ("...[截断]" if recent_assistant and len(recent_assistant[0]) > 300 else "")
    text = (message or "").lower()
    is_script_shape = is_script_like_request(message)
    operator_heavy_keywords = (
        "app",
        "标准安装",
        "安装链路",
        "交付",
        "创建",
        "状态",
        "运行",
        "安装",
        "注册",
        "部署",
    )
    is_operator_heavy = any(keyword in text for keyword in operator_heavy_keywords)
    if any(keyword in text for keyword in INTROSPECTION_KEYWORDS):
        next_action = "优先选择一个最高价值的定位或读取动作，不要同轮规划多个工具"
        stop_condition = "拿到能回答用户当前精度的直接证据后立即用中文给出完整回答"
    elif is_script_shape:
        next_action = "优先判断是否应该转为脚本方案"
        stop_condition = "一旦脚本比碎片工具链更合适，就切换策略"
    elif is_operator_heavy:
        next_action = "优先通过 call_asset_method 查询 App 状态或资产信息；只在资产接口无法直接回答时才走文件系统探索"
        stop_condition = "基于资产查询结果或已有证据直接回答用户问题，用中文输出完整结论后结束"
    else:
        next_action = "选择一个最高价值下一步动作"
        stop_condition = "当前问题已可回答时立即用中文给出回答"
    escalation = ""
    if is_script_shape and any(marker in recent_reply for marker in ("[Reached max turns", "未完成", "继续搜索")):
        escalation = "\n- 升级规则: 近期已出现未收敛信号，本轮优先使用 exec_shell 执行一次性脚本聚合，而不是继续零碎搜索"
    if is_operator_heavy and any(marker in recent_reply for marker in ("[Reached max turns", "未完成", "tool_call", "call_asset_method")):
        escalation = "\n- 收敛提醒: 近期已出现未收敛信号，本轮应优先基于已有证据给出明确结论并用中文输出，不要继续多轮工具探索"
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


def choose_turn_budget(message: str, exec_context: dict | None = None) -> int:
    """Choose turn budget based on execution context or message keywords.

    Priority:
    1. exec_context 中读取 task_mode + authorization → TurnBudgetPolicy
    2. fallback：关键词硬编码
    """
    # 优先从 execution context 读取
    if exec_context:
        try:
            from app.governance.turn_budget_policy import TurnBudgetPolicy, TaskModeBudget
            mode_str = exec_context.get('task_mode', {}).get('mode', 'chat')
            is_auth = exec_context.get('authorization', {}).get('is_authorized', False)
            mode = TaskModeBudget(mode_str)
            return TurnBudgetPolicy.decide(mode, is_auth)
        except (ValueError, ImportError):
            pass  # fallback 到关键词逻辑

    # fallback：原有关键词逻辑
    text = (message or "").lower()
    operator_heavy_keywords = (
        "标准安装",
        "安装链路",
        "交付",
        "创建",
        "状态",
        "运行",
        "接口行为",
        "确认这个接口行为",
        "api handler",
        "request/response",
        "request response",
        "handler 和 request/response 流程",
    )
    if any(keyword in text for keyword in operator_heavy_keywords):
        return 30
    if any(keyword in text for keyword in INTROSPECTION_KEYWORDS):
        return 8
    if is_script_like_request(message):
        return 10
    return 6


def narrow_tools_for_script_route(tools: list[ToolDef]) -> list[ToolDef]:
    allowed = {"exec_shell", "read_file", "write_file", "edit_file", "ask_clarification", "unclear"}
    narrowed = [tool for tool in tools if tool.name in allowed]
    return narrowed or tools

def narrow_tools_for_operator_route(tools: list[ToolDef]) -> list[ToolDef]:
    allowed = {"call_asset_method", "exec_shell", "read_file", "ask_clarification", "unclear",
               "dispatch_app_task", "query_task",
               "list_assets", "query_asset_info"}
    narrowed = [tool for tool in tools if tool.name in allowed]
    return narrowed or tools
