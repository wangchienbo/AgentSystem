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

    async def handle_pause_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想暂停哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                status_result = await self._bus.rpc(
                    "system.lifecycle",
                    SkillExecutionRequest(
                        skill_id="system.lifecycle",
                        action="get_instance",
                        inputs={"app_id": target},
                        config={},
                    ),
                    timeout=5,
                )
                if status_result and getattr(status_result, "status", None) == "completed":
                    current_status = status_result.output.get("status", "unknown")
                    can_pause, pause_reason = self._command_service.can_pause_from_status(current_status)
                    if not can_pause and pause_reason == "already_paused":
                        return self._command_service.build_success_response(
                            intent="pause_app",
                            session_id=session_id,
                            related_app=display_name,
                            content=f"**{display_name}** 已经处于暂停状态。",
                        )
                result = await self._bus.rpc(
                    "system.lifecycle",
                    SkillExecutionRequest(
                        skill_id="system.lifecycle",
                        action="pause",
                        inputs={"app_id": target, "reason": "user_command"},
                        config={"session_id": session_id},
                    ),
                    timeout=10,
                )
                if result and getattr(result, "status", None) == "completed":
                    return self._command_service.build_success_response(
                        intent="pause_app",
                        session_id=session_id,
                        related_app=display_name,
                        content=f"⏸ **{display_name}** 已暂停。",
                        actions=[
                            ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": display_name}, style="primary"),
                            ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": display_name}, style="secondary"),
                        ],
                    )
            except Exception as e:
                return self._command_service.build_degraded_response(
                    intent="pause_app",
                    session_id=session_id,
                    related_app=target_input,
                    reason="MessageBus RPC 调用失败",
                    detail=f"错误信息：{e}",
                )

        return self._command_service.build_degraded_response(
            intent="pause_app",
            session_id=session_id,
            related_app=target_input,
            reason="系统未配置 MessageBus",
            detail="无法通过 RPC 暂停 App。",
        )

    async def handle_resume_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想恢复哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                status_result = await self._bus.rpc(
                    "system.lifecycle",
                    SkillExecutionRequest(
                        skill_id="system.lifecycle",
                        action="get_instance",
                        inputs={"app_id": target},
                        config={},
                    ),
                    timeout=5,
                )
                if status_result and getattr(status_result, "status", None) == "completed":
                    current_status = status_result.output.get("status", "unknown")
                    can_resume, resume_reason = self._command_service.can_resume_from_status(current_status)
                    if not can_resume and resume_reason == "already_running":
                        return self._command_service.build_success_response(
                            intent="resume_app",
                            session_id=session_id,
                            related_app=display_name,
                            content=f"**{display_name}** 已经在运行中。",
                        )
                    if not can_resume and resume_reason == "invalid_resume_state":
                        return self._command_service.build_degraded_response(
                            intent="resume_app",
                            session_id=session_id,
                            related_app=display_name,
                            reason=f"当前状态为 {current_status}",
                            detail=f"**{display_name}** 当前处于 {current_status} 状态，请先暂停后再恢复。",
                        )
                result = await self._bus.rpc(
                    "system.lifecycle",
                    SkillExecutionRequest(
                        skill_id="system.lifecycle",
                        action="resume",
                        inputs={"app_id": target, "reason": "user_command"},
                        config={"session_id": session_id},
                    ),
                    timeout=10,
                )
                if result and getattr(result, "status", None) == "completed":
                    return self._command_service.build_success_response(
                        intent="resume_app",
                        session_id=session_id,
                        related_app=display_name,
                        content=f"▶️ **{display_name}** 已恢复运行。",
                        actions=[
                            ActionSuggestion(id="pause", label="⏸ 暂停", action_type="execute", payload={"intent": "pause_app", "target": display_name}, style="secondary"),
                            ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": display_name}, style="danger"),
                        ],
                    )
            except Exception as e:
                return self._command_service.build_degraded_response(
                    intent="resume_app",
                    session_id=session_id,
                    related_app=target_input,
                    reason="MessageBus RPC 调用失败",
                    detail=f"错误信息：{e}",
                )

        return self._command_service.build_degraded_response(
            intent="resume_app",
            session_id=session_id,
            related_app=target_input,
            reason="系统未配置 MessageBus",
            detail="无法通过 RPC 恢复 App。",
        )

    async def handle_query_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想查看哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                result = await self._bus.rpc(
                    "system.app_registry",
                    SkillExecutionRequest(
                        skill_id="system.app_registry",
                        action="get",
                        inputs={"app_id": target},
                        config={},
                    ),
                    timeout=5,
                )
                if result and getattr(result, "status", None) == "completed":
                    output = result.output
                    if output.get("found"):
                        status = output.get("status", "unknown")
                        runtime_status = ""
                        try:
                            lc_result = await self._bus.rpc(
                                "system.lifecycle",
                                SkillExecutionRequest(
                                    skill_id="system.lifecycle",
                                    action="get_instance",
                                    inputs={"app_id": target},
                                    config={},
                                ),
                                timeout=5,
                            )
                            if lc_result and getattr(lc_result, "status", None) == "completed":
                                lc_output = lc_result.output
                                if lc_output.get("found"):
                                    runtime_status = f"\n运行状态: {lc_output.get('status', 'unknown')}"
                        except Exception:
                            pass
                        detail = f"ID: {target}\n状态: {status}{runtime_status}"
                        return self._command_service.build_query_detail_response(
                            session_id=session_id,
                            related_app=display_name,
                            title=f"📋 {display_name}",
                            detail=detail,
                            actions=[
                                ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": display_name}, style="primary"),
                                ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": display_name}, style="danger"),
                            ],
                        )
            except Exception:
                pass

        return self._command_service.build_degraded_response(
            intent="query_app",
            session_id=session_id,
            related_app=display_name,
            reason="查询详情失败",
            detail="请稍后重试。",
        )

    async def handle_list_apps(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        user_id = command.user_id or ""
        user_apps = []
        for app in apps:
            owner = app.get("owner_user_id", "")
            if owner == user_id or owner == "system" or not owner:
                user_apps.append(app)

        if not user_apps:
            return self._presenter.build_empty_list_response(session_id=session_id)

        return self._presenter.build_list_response(
            session_id=session_id,
            user_apps=user_apps,
        )

    async def handle_delete_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想删除哪个 App？此操作不可恢复。",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        params = command.parameters or {}
        if params.get("confirmed"):
            if self._bus:
                try:
                    from app.models.skill_runtime import SkillExecutionRequest
                    result = await self._bus.rpc(
                        "system.lifecycle",
                        SkillExecutionRequest(
                            skill_id="system.lifecycle",
                            action="delete",
                            inputs={"app_id": target, "reason": "user_command"},
                            config={"session_id": session_id},
                        ),
                        timeout=10,
                    )
                    if result and getattr(result, "status", None) == "completed":
                        try:
                            await self._bus.rpc(
                                "system.app_registry",
                                SkillExecutionRequest(
                                    skill_id="system.app_registry",
                                    action="unregister",
                                    inputs={"app_id": target},
                                    config={},
                                ),
                                timeout=5,
                            )
                        except Exception:
                            pass
                        return self._command_service.build_success_response(
                            intent="delete_app",
                            session_id=session_id,
                            related_app=display_name,
                            content=f"🗑️ **{display_name}** 已删除。",
                            actions=[
                                ActionSuggestion(
                                    id="list_apps", label="📱 查看 App", action_type="navigate",
                                    payload={"intent": "list_apps"}, style="primary",
                                ),
                            ],
                        )
                except Exception as e:
                    return self._command_service.build_degraded_response(
                        intent="delete_app",
                        session_id=session_id,
                        related_app=display_name,
                        reason="MessageBus RPC 调用失败",
                        detail=f"错误信息：{e}",
                    )
            return self._command_service.build_degraded_response(
                intent="delete_app",
                session_id=session_id,
                related_app=display_name,
                reason="系统未配置 MessageBus",
                detail="无法通过 RPC 删除 App。",
            )

        return ChatMessageResponse(
            type="confirm",
            content=f"⚠️ 确定要删除 **{display_name}** 吗？此操作不可恢复！",
            session_id=session_id,
            related_app=display_name,
            actions=self._command_service.build_confirmation_actions(
                intent="delete_app",
                target_app=target,
                parameters={"target_app": target},
                confirm_label="🗑️ 确认删除",
                confirm_id="confirm_delete",
            ),
            requires_input=True,
        )
