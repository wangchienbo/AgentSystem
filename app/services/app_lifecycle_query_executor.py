from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.chat import ActionSuggestion, ChatMessageResponse, InterpretedCommand
from app.services.app_command_service import AppCommandService
from app.services.app_presenter import AppPresenter


@dataclass
class AppOperationResolution:
    target: str
    display_name: str
    static_found: bool
    static_status: str
    runtime_found: bool
    runtime_status: str



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

    async def _collect_app_runtime_view(self, target: str) -> dict[str, Any]:
        runtime_view: dict[str, Any] = {"found": False, "status": "unknown"}
        if not self._bus:
            return runtime_view
        try:
            from app.models.skill_runtime import SkillExecutionRequest
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
                lc_output = lc_result.output or {}
                runtime_view["found"] = bool(lc_output.get("found"))
                runtime_view["status"] = lc_output.get("status", "unknown")
                runtime_view["instance"] = lc_output
        except Exception:
            return runtime_view
        return runtime_view

    async def _collect_app_static_view(self, target: str) -> dict[str, Any]:
        static_view: dict[str, Any] = {"found": False, "status": "unknown"}
        if not self._bus:
            return static_view
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
                output = result.output or {}
                static_view["found"] = bool(output.get("found"))
                static_view["status"] = output.get("status", "unknown")
                static_view["entry"] = output
        except Exception:
            return static_view
        return static_view

    async def _collect_app_views(self, target: str) -> tuple[dict[str, Any], dict[str, Any]]:
        static_view = await self._collect_app_static_view(target)
        runtime_view = await self._collect_app_runtime_view(target)
        return static_view, runtime_view

    async def _resolve_app_operation(self, target: str, display_name: str) -> AppOperationResolution:
        static_view, runtime_view = await self._collect_app_views(target)
        return AppOperationResolution(
            target=target,
            display_name=display_name,
            static_found=bool(static_view.get("found")),
            static_status=static_view.get("status", "unknown"),
            runtime_found=bool(runtime_view.get("found")),
            runtime_status=runtime_view.get("status", "not_running") if runtime_view.get("found") else "not_running",
        )


    async def _ensure_static_presence(
        self,
        *,
        target: str,
        session_id: str,
        display_name: str,
        intent: str,
    ) -> ChatMessageResponse | None:
        resolution = await self._resolve_app_operation(target, display_name)
        if resolution.static_found:
            return None
        return self._command_service.build_degraded_response(
            intent=intent,
            session_id=session_id,
            related_app=display_name,
            reason="静态资产不存在",
            detail=f"**{display_name}** 尚未安装或未注册，无法执行该操作。",
        )

    async def _get_runtime_status(self, target: str) -> str:
        resolution = await self._resolve_app_operation(target, target)
        return resolution.runtime_status

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

        precheck = await self._ensure_static_presence(
            target=target,
            session_id=session_id,
            display_name=target_input,
            intent="start_app",
        )
        if precheck is not None:
            return precheck

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                runtime_status = await self._get_runtime_status(target)
                if runtime_status != "not_running":
                    return self._command_service.build_success_response(
                        intent="start_app",
                        session_id=session_id,
                        related_app=target_input,
                        content=f"**{target_input}** 当前已在运行。",
                    )
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

        precheck = await self._ensure_static_presence(
            target=target,
            session_id=session_id,
            display_name=target_input,
            intent="pause_app",
        )
        if precheck is not None:
            return precheck

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

        precheck = await self._ensure_static_presence(
            target=target,
            session_id=session_id,
            display_name=target_input,
            intent="resume_app",
        )
        if precheck is not None:
            return precheck

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
                resolution = await self._resolve_app_operation(target, display_name)
                if resolution.static_found or resolution.runtime_found:
                    detail = (
                        f"ID: {target}\n"
                        f"静态状态: {resolution.static_status}\n"
                        f"运行状态: {resolution.runtime_status}"
                    )
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
