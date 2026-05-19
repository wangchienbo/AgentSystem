"""Intent models — structured output from the intent extraction layer."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class AuthorizationSignal(str, Enum):
    """用户话语中隐含的授权信号等级。"""
    NONE = "none"
    IMPLIED_MODIFY = "implied_modify"           # "你改吧""帮我改"
    IMPLIED_RESTART = "implied_restart"         # "重启吧"
    IMPLIED_BACKGROUND = "implied_background"   # "你继续""后台跑"
    EXPLICIT_FULL = "explicit_full"             # "全部授权给你"


class ExtractedIntent(BaseModel):
    """意图提取层的结构化输出。

    由 IntentExtractor 对用户消息做一次 LLM 调用后产生。
    """
    # ── 核心操作 ──
    action: str = Field(
        description="用户的核心操作意图",
        examples=["create", "modify", "query", "delete", "start", "stop", "chat"],
    )
    target: str | None = Field(
        default=None,
        description="操作目标（app 名、配置名、功能名等）",
    )
    parameters: dict = Field(
        default_factory=dict,
        description="提取的关键参数键值对",
    )

    # ── 任务特征 ──
    task_mode: str = Field(
        default="chat",
        description="匹配的任务模式: chat/execution/engineering/background",
    )
    is_engineering: bool = Field(
        default=False,
        description="是否涉及改机制/改代码/改配置/改自己",
    )
    needs_background: bool = Field(
        default=False,
        description="是否适合后台持续执行",
    )

    # ── 授权信号 ──
    implied_authorization: AuthorizationSignal = Field(
        default=AuthorizationSignal.NONE,
        description="用户话语中隐含的授权信号",
    )

    # ── 元信息 ──
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = Field(default="", description="LLM 的推理过程摘要")
    raw_user_message: str = Field(default="")
