# Context Upload 配置
# Phase H+ 风险护栏：Context upload 白名单和 system note 模板

from dataclasses import dataclass, field
from typing import Literal

ContextRecordKind = Literal["message", "summary", "system_note", "tool_result"]

@dataclass
class ContextUploadConfig:
    """Context upload 白名单配置"""
    
    # 允许上传的内容类型
    allowed_kinds: tuple[ContextRecordKind, ...] = field(
        default_factory=lambda: ("message", "summary", "system_note", "tool_result")
    )
    
    # 禁止上传的内容类型（明确排除）
    forbidden_kinds: tuple[str, ...] = field(
        default_factory=lambda: (
            "scratchpad",
            "chain_of_thought",
            "internal_thought",
            "reasoning_trace",
            "full_tool_trace",
            "failed_attempt",
            "long_summary",
        )
    )
    
    # 允许上传的 role
    allowed_roles: tuple[str, ...] = field(
        default_factory=lambda: ("user", "assistant", "system")
    )
    
    # system note 最大长度（字符数）
    max_system_note_length: int = 500
    
    # 单条 message 最大长度（字符数）
    max_message_length: int = 10000
    
    # 单次 upload 最大记录数
    max_records_per_upload: int = 10


# System Note 模板
SYSTEM_NOTE_TEMPLATES = {
    "dispatch_decision": {
        "type": "dispatch_decision",
        "fields": ["actor", "resolved_session_id", "decision", "outcome"],
        "template": "决策：{decision} | 执行者：{actor} | Session: {resolved_session_id} | 结果：{outcome}",
    },
    "tool_execution": {
        "type": "tool_execution",
        "fields": ["tool_name", "status", "duration_ms"],
        "template": "工具执行：{tool_name} | 状态：{status} | 耗时：{duration_ms}ms",
    },
    "session_lifecycle": {
        "type": "session_lifecycle",
        "fields": ["action", "session_id", "status"],
        "template": "会话生命周期：{action} | Session: {session_id} | 状态：{status}",
    },
    "error_boundary": {
        "type": "error_boundary",
        "fields": ["error_type", "brief_message"],
        "template": "错误边界：{error_type} | 摘要：{brief_message}",
    },
    "context_upload": {
        "type": "context_upload",
        "fields": ["record_count", "session_id"],
        "template": "上下文上传：{record_count} 条记录 | Session: {session_id}",
    },
}

# 风险护栏：禁止上传的内容模式
FORBIDDEN_PATTERNS = [
    "scratchpad",
    "chain-of-thought",
    "chain_of_thought",
    "internal thought",
    "internal_thought",
    "reasoning trace",
    "reasoning_trace",
    "full tool trace",
    "full_tool_trace",
    "failed attempt",
    "failed_attempt",
    "intermediate step",
    "intermediate_step",
]


def is_content_allowed_for_upload(
    content: str,
    kind: str,
    role: str,
    config: ContextUploadConfig | None = None,
) -> tuple[bool, str | None]:
    """
    检查内容是否允许上传到上下文
    
    Returns:
        (allowed, reason): 如果允许返回 (True, None)，否则返回 (False, 原因说明)
    """
    if config is None:
        config = ContextUploadConfig()
    
    # 检查 kind 是否在白名单中
    if kind not in config.allowed_kinds:
        return False, f"Kind '{kind}' 不在允许列表中"
    
    # 检查 kind 是否在黑名单中
    if kind in config.forbidden_kinds:
        return False, f"Kind '{kind}' 被明确禁止"
    
    # 检查 role 是否允许
    if role not in config.allowed_roles:
        return False, f"Role '{role}' 不在允许列表中"
    
    # 检查 system note 长度
    if kind == "system_note" and len(content) > config.max_system_note_length:
        return False, f"System note 超出最大长度限制 ({len(content)} > {config.max_system_note_length})"
    
    # 检查 message 长度
    if kind == "message" and len(content) > config.max_message_length:
        return False, f"Message 超出最大长度限制 ({len(content)} > {config.max_message_length})"
    
    # 检查是否包含禁止的模式
    content_lower = content.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.lower() in content_lower:
            return False, f"内容包含禁止模式：'{pattern}'"
    
    return True, None


def format_system_note(
    template_name: str,
    **kwargs
) -> tuple[bool, str]:
    """
    使用预定义模板格式化 system note
    
    Returns:
        (success, result): 如果成功返回 (True, 格式化后的文本)，否则返回 (False, 错误信息)
    """
    if template_name not in SYSTEM_NOTE_TEMPLATES:
        available = ", ".join(SYSTEM_NOTE_TEMPLATES.keys())
        return False, f"未知模板：'{template_name}'。可用模板：{available}"
    
    template_info = SYSTEM_NOTE_TEMPLATES[template_name]
    required_fields = template_info["fields"]
    
    # 检查必填字段
    missing_fields = [f for f in required_fields if f not in kwargs]
    if missing_fields:
        return False, f"缺少必填字段：{', '.join(missing_fields)}"
    
    try:
        formatted = template_info["template"].format(**kwargs)
        return True, formatted
    except KeyError as e:
        return False, f"模板格式化失败：{e}"
    except ValueError as e:
        return False, f"模板参数错误：{e}"


def validate_context_upload(
    records: list[dict],
    config: ContextUploadConfig | None = None,
) -> tuple[bool, list[str]]:
    """
    批量验证 context upload 记录
    
    Returns:
        (valid, errors): 如果全部有效返回 (True, [])，否则返回 (False, [错误列表])
    """
    if config is None:
        config = ContextUploadConfig()
    
    # 检查记录数量
    if len(records) > config.max_records_per_upload:
        return False, [f"记录数超出限制：{len(records)} > {config.max_records_per_upload}"]
    
    errors = []
    for i, record in enumerate(records):
        kind = record.get("kind", "message")
        role = record.get("role", "system")
        content = record.get("content", "")
        
        allowed, reason = is_content_allowed_for_upload(content, kind, role, config)
        if not allowed:
            errors.append(f"记录 {i}: {reason}")
    
    if errors:
        return False, errors
    
    return True, []
