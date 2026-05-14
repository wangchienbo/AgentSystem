"""Engineering Task Mode — 工程任务模式识别。

将"改自己/改机制/持续执行/自我迭代"从普通问答里分离出来。

设计原则：
- 轻量本地规则做初筛
- 最终判断由 LLM prompt 完成（代码不做语义硬编码）
- 代码只负责：模式切换、流程控制、状态管理
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskMode(str, Enum):
    """任务模式。"""
    CHAT = "chat"                    # 普通问答模式
    EXECUTION = "execution"          # 一般执行模式
    ENGINEERING = "engineering"      # 工程任务模式（改自己/改机制）
    BACKGROUND = "background"        # 后台持续执行模式


class EngineeringTaskType(str, Enum):
    """工程任务子类型。"""
    UNKNOWN = "unknown"
    SELF_MODIFY = "self_modify"             # 改自己（修改 Agent 自身）
    MECHANISM_MODIFY = "mechanism_modify"   # 改机制（修改系统机制）
    BACKGROUND_CONTINUE = "background_continue"  # 后台继续执行
    SELF_ITERATE = "self_iterate"          # 自我迭代
    CODE_CHANGE = "code_change"            # 代码修改
    CONFIG_CHANGE = "config_change"        # 配置修改
    REVIEW = "review"                       # 审查


# 轻量关键词提示（仅辅助，不做主判定）
ENGINEERING_HINTS = [
    # 改自己
    "改自己", "修改自己", "升级自己", "自我改进", "自我升级",
    "改你", "修改你", "升级你",
    "self.modify", "self.upgrade", "self.evolve",
    # 改机制
    "改机制", "修改机制", "改系统", "修改系统",
    "机制改造", "系统改造", "架构改造",
    "modify mechanism", "modify system",
    # 后台执行
    "后台继续", "后台执行", "断线续跑", "离线执行",
    "background", "continue in background",
    # 自我迭代
    "自我迭代", "自迭代", "self.iterate",
    "self iteration", "auto evolve",
    # 工程类
    "任务清单", "checklist", "改造",
    "工程任务", "开发任务", "实施",
]

# 非工程任务关键词（明确走普通问答）
CHAT_ONLY_HINTS = [
    "你好", "hello", "hi",
    "天气", "新闻",
    "闲聊", "聊天",
]


class TaskModeClassification(BaseModel):
    """任务模式分类结果。"""
    mode: TaskMode = TaskMode.CHAT
    task_type: EngineeringTaskType = EngineeringTaskType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    signals: list[str] = Field(default_factory=list, description="触发的信号列表")
    reason: str = Field(default="", description="分类原因")


def classify_engineering_task(text: str) -> TaskModeClassification:
    """轻量本地初筛。返回分类信号供 LLM 最终判断。

    这不是最终判定——只是提取信号。
    真正的语义判断交给 LLM prompt。
    """
    text_lower = text.strip().lower()
    signals: list[str] = []
    task_type = EngineeringTaskType.UNKNOWN
    confidence = 0.0

    # 检查非工程信号
    for hint in CHAT_ONLY_HINTS:
        if hint in text_lower:
            signals.append(f"chat_hint:{hint}")
            confidence = max(confidence, 0.1)

    # 检查工程信号
    if any(kw in text_lower for kw in ["改自", "修改自", "升级自", "self.modif", "self.upgrade", "self.evolv"]):
        signals.append("intent:self_modify")
        task_type = EngineeringTaskType.SELF_MODIFY
        confidence = max(confidence, 0.3)

    if any(kw in text_lower for kw in ["改机制", "修改机制", "机制改造", "系统改造", "架构改造", "modify mechanism"]):
        signals.append("intent:mechanism_modify")
        task_type = EngineeringTaskType.MECHANISM_MODIFY
        confidence = max(confidence, 0.3)

    if any(kw in text_lower for kw in ["后台", "断线续跑", "离线执行", "background", "continue in background"]):
        signals.append("intent:background_continue")
        task_type = EngineeringTaskType.BACKGROUND_CONTINUE
        confidence = max(confidence, 0.3)

    if any(kw in text_lower for kw in ["自我迭代", "自迭代", "self.iterate", "self iteration", "auto evolve"]):
        signals.append("intent:self_iterate")
        task_type = EngineeringTaskType.SELF_ITERATE
        confidence = max(confidence, 0.3)

    if any(kw in text_lower for kw in ["改代码", "修改代码", "改配置", "修改配置", "改文件", "修改文件"]):
        signals.append("intent:code_change")
        task_type = EngineeringTaskType.CODE_CHANGE
        confidence = max(confidence, 0.25)

    # 综合判定
    if not signals:
        return TaskModeClassification(
            mode=TaskMode.CHAT,
            confidence=0.9,
            reason="未匹配到工程任务信号，走普通问答",
        )

    # 有工程信号
    if confidence >= 0.25:
        # 判断是否需要后台执行
        if any("background_continue" in s for s in signals):
            mode = TaskMode.BACKGROUND
        else:
            mode = TaskMode.ENGINEERING

        return TaskModeClassification(
            mode=mode,
            task_type=task_type,
            confidence=confidence,
            signals=signals,
            reason=f"检测到工程信号: {signals}",
        )

    return TaskModeClassification(
        mode=TaskMode.CHAT,
        confidence=0.8,
        signals=signals,
        reason="信号强度不足，走问答模式",
    )
