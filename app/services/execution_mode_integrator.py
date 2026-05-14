"""Authorization + Engineering Task Mode — 网关集成层。

将授权态和工程任务模式注入 LightBrain 消息流。
负责：
1. 在消息处理前加载/保存授权态
2. 判断当前模式，注入 command context
3. 根据授权影响 requires_clarification 决策
"""
from __future__ import annotations

import logging
from typing import Any

from app.models.authorization import AuthorizationDecision, AuthorizationLevel, AuthorizationState
from app.models.task_mode import TaskMode, TaskModeClassification, classify_engineering_task
from app.services.authorization_service import AuthorizationService

logger = logging.getLogger(__name__)


class ExecutionModeIntegrator:
    """执行模式集成器。

    作为网关和授权/任务模式之间的桥梁。
    不修改网关本身，而是通过 context 注入 + 决策钩子来影响行为。
    """

    def __init__(self, auth_service: AuthorizationService | None = None) -> None:
        self._auth_service = auth_service or AuthorizationService()

    @property
    def auth_service(self) -> AuthorizationService:
        return self._auth_service

    # ── 消息处理前（receive_message 中调用） ──

    def on_message_received(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> dict[str, Any]:
        """消息到达时处理。返回注入到 session context 的数据。

        1. 确保授权态存在
        2. 分类任务模式
        3. 返回上下文信息
        """
        # 确保会话有授权态
        auth_state = self._auth_service.get_or_create(session_id, user_id)

        # 分类任务模式
        mode_classification = classify_engineering_task(message)

        # 构建注入上下文
        context = {
            "authorization": {
                "level": auth_state.level.value,
                "is_authorized": auth_state.is_authorized(),
                "can_modify": auth_state.can_modify(),
                "can_restart": auth_state.can_restart(),
                "can_background_continue": auth_state.can_background_continue(),
            },
            "task_mode": {
                "mode": mode_classification.mode.value,
                "task_type": mode_classification.task_type.value,
                "signals": mode_classification.signals,
                "confidence": mode_classification.confidence,
            },
        }

        logger.info(
            "ExecutionModeIntegrator: session=%s auth=%s mode=%s signals=%s",
            session_id,
            auth_state.level.value,
            mode_classification.mode.value,
            mode_classification.signals,
        )

        return context

    # ── 授权处理 ──

    def process_authorization_intent(
        self,
        session_id: str,
        user_id: str,
        message: str,
        intent: str,
    ) -> AuthorizationState:
        """处理授权意图。

        从 LLM 识别到的 intent 中解析授权信息，
        转换为正式的 AuthorizationState。

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            message: 原始用户消息
            intent: LLM 识别到的授权意图（由 prompt 驱动）
        """
        level = AuthorizationLevel.AUTHORIZED
        allow_modify = False
        allow_restart = False
        allow_background_continue = False

        intent_lower = intent.lower()

        # 解析授权意图
        if "modify" in intent_lower or "all" in intent_lower or "full" in intent_lower:
            allow_modify = True
            allow_restart = True
            allow_background_continue = True
        else:
            if "background" in intent_lower or "continue" in intent_lower:
                allow_background_continue = True
            if "restart" in intent_lower:
                allow_restart = True
            if "modify" in intent_lower or "change" in intent_lower:
                allow_modify = True

        # 解析用户消息中的授权关键词（辅助）
        msg_lower = message.lower()
        for kw in ["可以改", "可以修改", "允许修改", "可以改你", "你改吧", "改吧", "go ahead", "go ahead and modify"]:
            if kw in msg_lower:
                allow_modify = True
        for kw in ["可以重启", "允许重启", "重启吧", "restart"]:
            if kw in msg_lower:
                allow_restart = True
        for kw in ["可以后台", "后台继续", "你继续", "继续跑", "continue in background", "keep going"]:
            if kw in msg_lower:
                allow_background_continue = True

        # 执行授权
        return self._auth_service.authorize(
            session_id=session_id,
            user_id=user_id,
            level=level,
            allow_modify=allow_modify,
            allow_restart=allow_restart,
            allow_background_continue=allow_background_continue,
            message=message,
            intent=intent,
        )

    # ── 决策 ──

    def should_skip_clarification(
        self,
        session_id: str,
        engineering_mode: bool = False,
    ) -> bool:
        """判断是否可以跳过澄清，直接进入执行模式。

        Args:
            session_id: 会话 ID
            engineering_mode: 当前是否为工程任务模式

        Returns:
            True 表示应跳过澄清，直接执行
        """
        decision = self._auth_service.make_decision(session_id, engineering_task=engineering_mode)
        return decision.can_execute and not decision.requires_clarification

    def get_execution_decision(
        self,
        session_id: str,
        engineering_mode: bool = False,
    ) -> AuthorizationDecision:
        """获取执行决策。"""
        return self._auth_service.make_decision(session_id, engineering_task=engineering_mode)

    # ── Command context 注入 ──

    def inject_into_command_context(
        self,
        context: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        """将授权和任务模式注入 command context。"""
        auth_state = self._auth_service.get(session_id)
        if auth_state:
            context["authorization"] = {
                "level": auth_state.level.value,
                "is_authorized": auth_state.is_authorized(),
                "can_modify": auth_state.can_modify(),
                "can_restart": auth_state.can_restart(),
                "can_background_continue": auth_state.can_background_continue(),
                "authorized_by_intent": auth_state.authorized_by_intent,
            }
        return context

    # ── Prompt 片段生成 ──

    def build_authorization_prompt_block(self, session_id: str) -> str:
        """生成注入到 system prompt 的授权状态块。

        这是关键——通过 prompt 让 LLM 知道当前的授权状态，
        从而做出正确的行为决策。
        """
        auth_state = self._auth_service.get(session_id)
        if not auth_state or not auth_state.is_authorized():
            return ""

        lines = [
            "## 当前授权状态",
            f"- 授权等级: {auth_state.level.value}",
            f"- 允许修改: {'是' if auth_state.allow_modify else '否'}",
            f"- 允许重启: {'是' if auth_state.allow_restart else '否'}",
            f"- 允许后台继续: {'是' if auth_state.allow_background_continue else '否'}",
        ]

        if auth_state.authorized_by_intent:
            lines.append(f"- 授权来源: {auth_state.authorized_by_intent}")

        if auth_state.allow_modify or auth_state.allow_restart:
            lines.append("")
            lines.append("### 执行指引")
            lines.append("用户已授权，优先执行而非澄清。")
            lines.append("如果确认用户意图，直接开始工作，不需要反复确认。")

        if auth_state.allow_background_continue:
            lines.append("用户可以离线，任务应在后台持续推进。")
            lines.append("回来时汇报完成状态和结果摘要。")

        return "\n".join(lines)


# 全局单例（方便网关引用）
_integrator: ExecutionModeIntegrator | None = None


def get_integrator() -> ExecutionModeIntegrator:
    global _integrator
    if _integrator is None:
        _integrator = ExecutionModeIntegrator()
    return _integrator
