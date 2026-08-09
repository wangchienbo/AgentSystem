"""Session Context Helpers — 会话上下文构建与增强。

从 http_test_server 抽离的纯逻辑辅助函数：
- 从会话历史构建记忆上下文 / 事实看板
- 用户消息增强（对话约束注入）
- 运行元数据提取

这些函数保持**无状态**：历史通过参数传入，便于测试与复用。
"""
from __future__ import annotations

from typing import Any


def build_memory_context(history: list[dict[str, Any]], limit: int = 12) -> str:
    """从会话历史构建可读的记忆上下文文本。"""
    recent = history[-limit:]
    return "\n".join(
        f"{item.get('role', 'unknown')}: {item.get('content', '')}"
        for item in recent
    )


# 会话事实提取规则（配置驱动，不再硬编码具体场景内容）
# key: 事实字段名；value: {"label": 显示名, "keywords": 触发关键词列表}
SESSION_FACT_RULES: dict[str, dict[str, Any]] = {}


def _extract_session_facts(history: list[dict[str, Any]]) -> dict[str, str]:
    """从会话历史提取已知事实（基于 SESSION_FACT_RULES 规则表）。"""
    facts: dict[str, str] = {}
    for item in history:
        if item.get("role") != "user":
            continue
        content = item.get("content", "")
        for key, rule in SESSION_FACT_RULES.items():
            if key in facts:
                continue
            for kw in rule.get("keywords", []):
                if kw in content:
                    facts[key] = rule.get("value", kw)
                    break
    return facts


def build_session_fact_board(history: list[dict[str, Any]]) -> str:
    """构建会话事实看板文本（基于规则表）。"""
    facts = _extract_session_facts(history)
    if not facts:
        return ""
    lines = ["[当前会话已知事实]"]
    for key, value in facts.items():
        rule = SESSION_FACT_RULES.get(key, {})
        label = rule.get("label", key)
        lines.append(f"- {label}: {value}")
    lines.append("- 对已明确给出的事实，不要重复追问。")
    return "\n".join(lines)


def build_effective_memory_context(history: list[dict[str, Any]]) -> str:
    """构建综合记忆上下文（事实看板 + 最近历史）。"""
    parts = []
    fact_board = build_session_fact_board(history)
    hist_text = build_memory_context(history)
    if fact_board:
        parts.append(fact_board)
    if hist_text:
        parts.append("[最近对话历史]\n" + hist_text)
    return "\n\n".join(parts)


def augment_user_message(raw_message: str, history: list[dict[str, Any]]) -> str:
    """增强用户消息：注入对话约束与自省/检索类请求引导。"""
    style_anchor = "回答时必须先给结论，再给细节。"
    action_first_triggers = ["查看上下文", "看下上下文", "查代码", "源码仓库", "仓库位置", "调用工具查找"]
    if not history:
        return raw_message
    prefix_lines = ["[对话约束]", f"- {style_anchor}"]
    if any(trigger in raw_message for trigger in action_first_triggers):
        prefix_lines.append("- 当前请求属于系统自省/检索类请求，必须优先尝试真实工具动作或真实检索，再根据结果回复；不要直接只做泛化能力解释。")
        prefix_lines.append("- 若无法完成，也要明确说明已尝试了什么、为什么失败、还缺什么权限或信息。")
    return "\n".join(prefix_lines) + f"\n\n[用户当前消息]\n{raw_message}"


def extract_run_metadata(payload: dict[str, Any] | None) -> dict[str, str] | None:
    """从请求 payload 提取运行元数据（run_id / scenario_id）。"""
    if not isinstance(payload, dict):
        return None
    run_id = str(payload.get("run_id") or "").strip()
    scenario_id = str(payload.get("scenario_id") or "").strip()
    metadata: dict[str, str] = {}
    if run_id:
        metadata["run_id"] = run_id
    if scenario_id:
        metadata["scenario_id"] = scenario_id
    return metadata or None
