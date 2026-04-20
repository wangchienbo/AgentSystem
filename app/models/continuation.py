"""Continuation — 统一的多轮交互契约。

将 clarification / follow-up / pending action 抽象为可复用的跨 intent 基础设施。
Phase H 从 runtime asset 特例收敛为通用模式。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ContinuationKind(str, Enum):
    """Continuation 类型：为什么需要多轮。"""
    MISSING_PARAMETER = "missing_parameter"  # 缺参数
    CONFIRMATION = "confirmation"  # 需要确认（副作用）
    AMBIGUITY = "ambiguity"  # 歧义需要澄清
    REPLAN = "replan"  # 执行失败需要重规划


class MissingParamSpec(BaseModel):
    """缺失参数的具体描述。"""
    param_name: str
    param_type: Literal["string", "number", "boolean", "enum", "asset_id", "method", "json"]
    description: str
    required: bool = True
    enum_values: list[str] | None = None  # 如果是 enum 类型
    example: str | None = None


class ContinuationState(BaseModel):
    """可持久化的 continuation 状态。
    
    替代原来的 _pending_runtime_asset_clarifications 等私有字典。
    """
    continuation_id: str  # 通常就是 session_id
    kind: ContinuationKind
    
    # 原始意图（被暂停的主意图）
    original_intent: str
    original_params: dict[str, Any] = Field(default_factory=dict)
    
    # 缺失什么（用于 MISSING_PARAMETER）
    missing_params: list[MissingParamSpec] = Field(default_factory=list)
    
    # 确认什么（用于 CONFIRMATION）
    confirmation_prompt: str | None = None
    confirmation_action_id: str | None = None  # 对应 action suggestion id
    
    # 歧义选项（用于 AMBIGUITY）
    ambiguity_options: list[dict[str, Any]] = Field(default_factory=list)
    
    # 重规划上下文（用于 REPLAN）
    failed_step_id: str | None = None
    last_error: str | None = None
    
    # 创建时间（用于 TTL 清理）
    created_at: str = Field(default_factory=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
    ttl_seconds: int = 3600  # 1小时过期
    
    # 状态
    status: Literal["pending", "completed", "expired", "cancelled"] = "pending"


class ContinuationResponse(BaseModel):
    """Gateway 返回给用户的 continuation 响应。
    
    统一 clarification 响应格式，替代散落在各 handler 里的字符串拼接。
    """
    requires_input: bool = True  # 总是 True 对于 continuation
    
    # 人类可读的问题
    prompt: str
    
    # 结构化缺失参数（如果有）
    missing_parameters: list[MissingParamSpec] = Field(default_factory=list)
    
    # 建议的快捷操作
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    
    # 原始意图（用于客户端显示上下文）
    original_intent: str | None = None
    partial_params: dict[str, Any] = Field(default_factory=dict)


class ContinuationResumeRequest(BaseModel):
    """用户 follow-up 恢复 continuation 的请求。
    
    可以是自然语言，也可以是结构化参数。
    """
    session_id: str  # 对应 continuation_id
    user_input: str  # 用户的新输入
    
    # 可选：客户端直接填充参数
    filled_params: dict[str, Any] = Field(default_factory=dict)
    
    # 用户选择的 action（如果有）
    selected_action_id: str | None = None


class ContinuationResult(BaseModel):
    """Continuation 恢复后的结果。"""
    status: Literal["completed", "needs_more", "cancelled", "expired"]
    
    # 如果 completed，返回可执行的完整 command
    completed_command: Any | None = None
    
    # 如果 needs_more，返回新的 continuation 状态
    next_continuation: ContinuationState | None = None
    
    # 消息
    message: str | None = None
