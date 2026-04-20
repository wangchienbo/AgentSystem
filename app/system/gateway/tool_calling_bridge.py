"""Tool Calling Gateway Bridge — integrates ToolCallingEngine into Gateway flow.

Phase E.2: Unified tool-aware intent handling.
- Rule-based exact matches still bypass LLM (zero cost for greetings/help)
- Everything else goes through LLM with Tool Registry context
- Multi-turn tool calling with context preservation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallingContext:
    """Context passed to LLM for tool selection."""
    user_message: str
    session_history: list[dict[str, Any]] = field(default_factory=list)
    available_apps: list[dict[str, Any]] = field(default_factory=list)
    pending_intent: str | None = None  # If previous turn requires clarification
    pending_params: dict[str, Any] = field(default_factory=dict)
    tool_registry_snapshot: list[dict[str, Any]] = field(default_factory=list)


TOOL_CALLING_SYSTEM_PROMPT = """你是 AgentSystem 的意图解析助手。

你的任务：根据用户输入和上下文，选择最合适的工具来完成用户请求。

## 当前会话状态
{session_context}

## 可用工具列表
{tools_description}

## 规则
1. 如果用户请求明确且工具匹配，选择对应工具并填写参数
2. 如果缺少必要参数，选择 `ask_clarification` 工具询问用户
3. 如果用户是在回答之前的问题（pending intent 存在），将用户输入填入对应参数
4. 如果完全不理解用户意图，选择 `unclear` 并提供友好回复

## 参数填写规则
- app_name: 从用户输入中提取 App 名称（如"服务器监控"、"日报"）
- app_type: 提取类型（如"监控"、"日报"、"提醒"）
- description: 完整保留用户的原始描述

## 回复格式
必须使用 tool calling 格式回复。"""


ASK_CLARIFICATION_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_clarification",
        "description": "当缺少必要参数或需要用户确认时，向用户询问更多信息",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "询问用户的问题，要友好自然"
                },
                "pending_intent": {
                    "type": "string",
                    "description": "当前等待完成的意图（如 start_app、create_app）"
                },
                "missing_param": {
                    "type": "string",
                    "description": "缺少的参数名称（如 app_name、app_type）"
                },
                "suggested_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "建议的可能值（如可用 App 列表）"
                }
            },
            "required": ["question", "pending_intent", "missing_param"]
        }
    }
}


UNCLEAR_TOOL = {
    "type": "function",
    "function": {
        "name": "unclear",
        "description": "当无法理解用户意图时使用",
        "parameters": {
            "type": "object",
            "properties": {
                "reply": {
                    "type": "string",
                    "description": "友好的回复，引导用户重新表达"
                }
            },
            "required": ["reply"]
        }
    }
}


def build_tool_definitions(registry_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert ToolRegistry tools to OpenAI function format."""
    tools = []
    
    for tool in registry_tools:
        # Build parameters schema
        properties = {}
        required = []
        
        for param in tool.get("parameters", []):
            param_name = param.get("name", "")
            param_type = param.get("type", "string")
            param_desc = param.get("description", "")
            
            properties[param_name] = {
                "type": param_type,
                "description": param_desc
            }
            
            if param.get("required", True):
                required.append(param_name)
            
            # Add enum if exists
            if "enum" in param and param["enum"]:
                properties[param_name]["enum"] = param["enum"]
        
        tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })
    
    # Add system tools
    tools.append(ASK_CLARIFICATION_TOOL)
    tools.append(UNCLEAR_TOOL)
    
    return tools


def format_tools_description(tools: list[dict[str, Any]]) -> str:
    """Format tools for system prompt."""
    lines = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "")
        desc = func.get("description", "")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def format_session_context(
    history: list[dict[str, Any]],
    pending_intent: str | None,
    pending_params: dict[str, Any],
    available_apps: list[dict[str, Any]]
) -> str:
    """Format session context for prompt."""
    lines = []
    
    if pending_intent:
        lines.append(f"【等待完成】意图: {pending_intent}")
        lines.append(f"【已有参数】{pending_params}")
        lines.append(f"【需要补充】用户正在回答之前的问题，请将当前输入填入缺失参数")
    
    if available_apps:
        app_names = [a.get("name", a.get("app_id", "")) for a in available_apps[:5]]
        lines.append(f"【可用 App】{', '.join(app_names)}")
    
    if history:
        lines.append("【最近对话】")
        for msg in history[-3:]:
            role = msg.get("role", "")
            content = msg.get("content", "")[:50]
            lines.append(f"  {role}: {content}...")
    
    return "\n".join(lines) if lines else "新会话，无上下文"
