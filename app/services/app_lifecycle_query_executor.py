from __future__ import annotations

from typing import Any

from app.models.chat import ActionSuggestion, ChatMessageResponse, InterpretedCommand
from app.services.app_command_service import AppCommandService
from app.services.app_presenter import AppPresenter


class AppLifecycleQueryExecutor:
    def __init__(
        self,
        *,
        command_service: AppCommandService,
        presenter: AppPresenter,
        bus: Any,
        resolve_instance_id,
        resolve_display_name,
    ) -> None:
        self._command_service = command_service
        self._presenter = presenter
        self._bus = bus
        self._resolve_instance_id = resolve_instance_id
        self._resolve_display_name = resolve_display_name

    async def handle_start_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想启动哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                result = await self._bus.rpc(
                    "system.lifecycle",
                    SkillExecutionRequest(
                        skill_id="system.lifecycle",
                        action="start",
                        inputs={"app_id": target, "reason": "user_command"},
                        config={"session_id": session_id},
                    ),
                    timeout=10,
                )
                if result and getattr(result, "status", None) == "completed":
                    display_name = self._resolve_display_name(target, "")
                    return self._command_service.build_success_response(
                        intent="start_app",
                        session_id=session_id,
                        related_app=display_name,
                        response_type="card",
                        content=f"✅ **{display_name}** 已启动。",
                        actions=[
                            ActionSuggestion(
                                id="query_status", label="查看状态", action_type="execute",
                                payload={"intent": "query_app", "target": display_name}, style="secondary",
                            ),
                            ActionSuggestion(
                                id="pause", label="⏸ 暂停", action_type="execute",
                                payload={"intent": "pause_app", "target": display_name}, style="secondary",
                            ),
                            ActionSuggestion(
                                id="stop", label="⏹ 停止", action_type="execute",
                                payload={"intent": "stop_app", "target": display_name}, style="danger",
                            ),
                        ],
                    )
            except Exception as e:
                return self._command_service.build_degraded_response(
                    intent="start_app",
                    session_id=session_id,
                    related_app=target_input,
                    reason="MessageBus RPC 调用失败",
                    detail=f"错误信息：{e}",
                )

        return self._command_service.build_degraded_response(
            intent="start_app",
            session_id=session_id,
            related_app=target_input,
            reason="系统未配置 MessageBus",
            detail="无法通过 RPC 启动 App。",
        )

    async def handle_stop_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想停止哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                result = await self._bus.rpc(
                    "system.lifecycle",
                    SkillExecutionRequest(
                        skill_id="system.lifecycle",
                        action="stop",
                        inputs={"app_id": target, "reason": "user_command"},
                        config={"session_id": session_id},
                    ),
                    timeout=10,
                )
                if result and getattr(result, "status", None) == "completed":
                    display_name = self._resolve_display_name(target, "")
                    return self._command_service.build_success_response(
                        intent="stop_app",
                        session_id=session_id,
                        related_app=display_name,
                        response_type="card",
                        content=f"⏹ **{display_name}** 已停止。",
                        actions=[
                            ActionSuggestion(
                                id="start", label="▶️ 启动", action_type="execute",
                                payload={"intent": "start_app", "target": display_name}, style="primary",
                            ),
                        ],
                    )
            except Exception as e:
                return self._command_service.build_degraded_response(
                    intent="stop_app",
                    session_id=session_id,
                    related_app=target_input,
                    reason="MessageBus RPC 调用失败",
                    detail=f"错误信息：{e}",
                )

        return self._command_service.build_degraded_response(
            intent="stop_app",
            session_id=session_id,
            related_app=target_input,
            reason="系统未配置 MessageBus",
            detail="无法通过 RPC 停止 App。",
        )
