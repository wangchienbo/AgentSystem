"""Authorization State — 授权态状态机。

用户在会话中明确授权后，将授权写入持久化状态，
后续轮次不再反复澄清，直接进入执行模式。

授权字段说明：
- allow_modify: 允许修改配置/代码/文件
- allow_restart: 允许重启服务/应用
- allow_background_continue: 允许断线后继续执行
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuthorizationLevel(str, Enum):
    """授权等级，控制执行强度。"""
    NONE = "none"                 # 未授权，默认保守问答态
    CONVERSATIONAL = "chat"       # 仅问答，不可修改
    EXECUTION = "execution"       # 可执行任务，但不修改系统
    AUTHORIZED = "authorized"     # 已授权，可修改/重启/后台执行


class AuthorizationState(BaseModel):
    """会话级授权态。

    用户明确授权后写入，绑定到 session 持续生效。
    后续轮次优先读取此状态，减少澄清。
    """
    session_id: str = Field(..., description="会话 ID，绑定授权")
    user_id: str = Field(..., description="用户 ID")

    # 授权等级
    level: AuthorizationLevel = AuthorizationLevel.NONE

    # 细粒度授权开关
    allow_modify: bool = Field(default=False, description="允许修改配置/代码/文件")
    allow_restart: bool = Field(default=False, description="允许重启服务/应用")
    allow_background_continue: bool = Field(default=False, description="允许后台继续执行")

    # 授权来源（哪条消息触发的授权）
    authorized_by_message: str = Field(default="", description="触发授权的用户消息")
    authorized_by_intent: str = Field(default="", description="识别到的授权意图")

    # 时间戳
    authorized_at: datetime | None = Field(default=None, description="授权时间")
    expires_at: datetime | None = Field(default=None, description="过期时间（默认会话有效）")

    # 是否已在一轮中使用过
    consumed: bool = Field(default=False, description="是否已用于执行决策")

    # 额外元信息
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_authorized(self) -> bool:
        """是否处于可执行状态（授权未过期）。"""
        if self.level == AuthorizationLevel.NONE:
            return False
        if self.expires_at and datetime.now(UTC) > self.expires_at:
            return False
        return True

    def can_modify(self) -> bool:
        """允许修改。"""
        return self.is_authorized() and self.allow_modify

    def can_restart(self) -> bool:
        """允许重启。"""
        return self.is_authorized() and self.allow_restart

    def can_background_continue(self) -> bool:
        """允许后台继续执行。"""
        return self.is_authorized() and self.allow_background_continue

    def authorize(
        self,
        level: AuthorizationLevel,
        *,
        allow_modify: bool = False,
        allow_restart: bool = False,
        allow_background_continue: bool = False,
        message: str = "",
        intent: str = "",
        ttl_seconds: int | None = None,
    ) -> None:
        """执行授权。"""
        self.level = level
        self.allow_modify = allow_modify
        self.allow_restart = allow_restart
        self.allow_background_continue = allow_background_continue
        self.authorized_by_message = message
        self.authorized_by_intent = intent
        self.authorized_at = datetime.now(UTC)
        if ttl_seconds:
            self.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        else:
            self.expires_at = None  # 会话有效
        self.consumed = False

    def revoke(self) -> None:
        """撤销授权。"""
        self.level = AuthorizationLevel.NONE
        self.allow_modify = False
        self.allow_restart = False
        self.allow_background_continue = False
        self.consumed = False


class AuthorizationDecision(BaseModel):
    """授权决策：网关根据授权态和执行类型做出的判断。"""
    can_execute: bool = Field(default=False, description="是否可以直接执行")
    execution_mode: Literal["chat", "execute", "background"] = Field(
        default="chat", description="执行模式"
    )
    reason: str = Field(default="", description="决策原因")
    requires_clarification: bool = Field(default=True, description="是否需要向用户澄清")
    clarification_prompt: str | None = Field(default=None, description="澄清提示文本")


def make_default_auth_state(session_id: str, user_id: str) -> AuthorizationState:
    """创建默认未授权态。"""
    return AuthorizationState(
        session_id=session_id,
        user_id=user_id,
        level=AuthorizationLevel.NONE,
    )
