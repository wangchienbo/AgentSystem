"""PreReplyRouter — 回答前决策层（控制层）。

ContextCenter 体系第三层：把 receive_message 中散落的「回答前短路 / 放行」决策
收敛为统一、有序、可单测的策略列表，并强制架构不变量：

    **非用户主动请求时，任何策略不得吞掉模型主干（取上下文 → 模型回答）。**

与已有两层的关系：
  ContextCenter     = 存储层（append-only 磁盘持久化）
  ModelInputBuilder = 视图层（窗口 + 压缩，纯读取）
  PreReplyRouter    = 控制层（回答前决策：短路 or 放行）  ← 本模块

一期收敛策略：ReplayPolicy（结果回放）。
后续策略（限流 / 任务延续 / 交互路由）按需以 ReplyPolicy 子类并入，
按 priority 升序评估，首个短路即返回，否则一律放行。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.system.gateway.light_brain_gateway import LightBrainGateway

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 核心数据结构
# ---------------------------------------------------------------------------

@dataclass
class ReplyDecision:
    """一次决策的结果：要么短路（带回响应），要么放行给模型主干。"""
    outcome: str  # "short_circuit" | "pass_through"
    response: Any = None          # short_circuit 时携带 ChatMessageResponse
    reason: str = ""              # 可观测性 / 日志


@dataclass
class ReplyContext:
    """回答前决策所需的会话状态快照。

    副作用执行能力通过 ``gateway`` 注入（集成时真实实例，单测时 mock 最小接口）。
    """
    message: str
    session_id: str
    user_id: str
    pending_task: Any = None
    continuation_decision: Any = None
    gateway: "LightBrainGateway | None" = None
    cmd_start_time: float = 0.0


# ---------------------------------------------------------------------------
# 策略基类
# ---------------------------------------------------------------------------

class ReplyPolicy(ABC):
    """单一短路策略：对一种会话状态做「短路 or 放行」决策。

    子类实现 ``evaluate``。决策逻辑（何时短路）应尽量独立于 gateway，
    副作用通过 ``ctx.gateway`` 调用，以便单测。
    """

    #: 评估优先级（升序执行，越小越先）
    priority: int = 100
    #: 策略名，用于日志 / 可观测性
    name: str = "base"

    @abstractmethod
    def evaluate(self, ctx: ReplyContext) -> ReplyDecision:
        """返回短路（带回响应）或放行。"""

    def _pass(self) -> ReplyDecision:
        return ReplyDecision("pass_through", reason=f"{self.name}:pass")

    def _short(self, response: Any, reason: str) -> ReplyDecision:
        return ReplyDecision("short_circuit", response=response, reason=f"{self.name}:{reason}")


# ---------------------------------------------------------------------------
# ReplayPolicy — 结果回放（一期）
# ---------------------------------------------------------------------------

def is_user_asking_task_result(message: str | None) -> bool:
    """判断用户是否在主动询问任务 / 操作结果。

    只有明确询问「上次任务 / 操作怎么样了」时返回 True，才触发结果回放；
    其他任何请求（寒暄、计算、翻译、内容创作等）一律 False，
    保证回放绝不拦截正常对话主干。
    """
    if not message:
        return False
    m = message.strip().lower()
    keywords = (
        "任务", "结果", "进展", "进度", "上次", "之前",
        "完成", "状态", "处理得", "搞完", "做完", "好了吗",
        "完成情况", "办得", "怎么样", "status", "task",
        "result", "progress", "done", "finished",
    )
    return any(k in m for k in keywords)


class ReplayPolicy(ReplyPolicy):
    """结果回放：仅在用户主动询问任务结果时，回放最近一条已关闭任务。

    不变量：非询问（寒暄 / 计算 / 翻译 / 创作等）时一律放行，
    绝不吞掉模型主干 —— 这正是「回放劫持正常对话」bug 的根治点。
    """

    priority: int = 200
    name: str = "replay"

    def evaluate(self, ctx: ReplyContext) -> ReplyDecision:
        # 有进行中任务时不回放（任务延续接管）
        if ctx.pending_task is not None:
            return self._pass()
        # 非用户主动询问任务结果 → 绝不放行给回放，直接放行主干
        if not is_user_asking_task_result(ctx.message):
            return self._pass()

        g = ctx.gateway
        if g is None:
            return self._pass()

        replay_task = g._get_latest_closed_task(ctx.user_id)
        if replay_task is None:
            return self._pass()
        if g.was_replayed(ctx.session_id, replay_task.task_id):
            return self._pass()

        g.mark_replayed(ctx.session_id, replay_task.task_id)
        logger.info(
            "Replaying task result: user=%s task=%s status=%s",
            ctx.user_id, replay_task.task_id, replay_task.status,
        )
        # 直接复用 gateway 的响应构建，避免重复实现
        try:
            from app.system.gateway.light_brain_gateway import ChatMessageResponse
            response = ChatMessageResponse(
                type="replay",
                content=g._format_replay_content(replay_task),
                session_id=ctx.session_id,
                data={"pending_task": replay_task.model_dump(mode="json")},
            )
        except Exception as e:  # pragma: no cover - 防御性
            logger.error("ReplayPolicy response build failed: %s", e)
            return self._pass()
        return self._short(response, "replay")


# ---------------------------------------------------------------------------
# PreReplyRouter — 决策层入口
# ---------------------------------------------------------------------------

#: 默认策略（一期）
DEFAULT_POLICIES: list[ReplyPolicy] = [ReplayPolicy()]


class PreReplyRouter:
    """按优先级评估策略，决定短路 or 放行模型主干。

    全部放行 → 返回 pass_through，receive_message 继续走到模型。
    """

    def __init__(self, policies: list[ReplyPolicy] | None = None) -> None:
        self._policies: list[ReplyPolicy] = sorted(
            policies if policies is not None else list(DEFAULT_POLICIES),
            key=lambda p: p.priority,
        )

    @property
    def policies(self) -> list[ReplyPolicy]:
        return list(self._policies)

    def decide(self, ctx: ReplyContext) -> ReplyDecision:
        for policy in self._policies:
            decision = policy.evaluate(ctx)
            if decision.outcome == "short_circuit":
                logger.debug("PreReplyRouter short-circuit: %s", decision.reason)
                return decision
        return ReplyDecision("pass_through", reason="router:pass")
