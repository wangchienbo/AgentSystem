from __future__ import annotations

from typing import Any

from app.models.chat import ActionSuggestion, ChatMessageResponse, InterpretedCommand
from app.services.app_command_service import AppCommandService
from app.services.app_presenter import AppPresenter


class AppCreateModifyExecutor:
    def __init__(
        self,
        *,
        command_service: AppCommandService,
        presenter: AppPresenter,
        bus: Any,
        config_center: Any,
        persistence: Any,
        lifecycle: Any,
        runtime_host: Any,
        app_registry: Any,
        catalog: Any,
        app_refinement_orchestrator: Any,
        resolve_instance_id,
        resolve_display_name,
        check_app_modify_permission,
    ) -> None:
        self._command_service = command_service
        self._presenter = presenter
        self._bus = bus
        self._config_center = config_center
        self._persistence = persistence
        self._lifecycle = lifecycle
        self._runtime_host = runtime_host
        self._app_registry = app_registry
        self._catalog = catalog
        self._app_refinement_orchestrator = app_refinement_orchestrator
        self._resolve_instance_id = resolve_instance_id
        self._resolve_display_name = resolve_display_name
        self._check_app_modify_permission = check_app_modify_permission

    async def handle_create_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        params = command.parameters or {}
        app_name = command.target_app or params.get("target_app") or params.get("app_name") or "未命名 App"
        app_type = params.get("app_type", "通用")
        creative_mode = bool(params.get("creative_mode"))
        schedule_info = ""
        if params.get("schedule"):
            schedule_info = f"\n计划: {params['schedule']}"
        threshold_info = ""
        if params.get("threshold"):
            threshold_info = f"\n告警阈值: {params['threshold']}%"

        app_command = self._command_service.from_interpreted_command(command=command, session_id=session_id)
        if self._command_service.requires_confirmation(app_command):
            return self._command_service.build_confirmation_response(
                intent="create_app",
                session_id=session_id,
                related_app=app_name,
                target_app=app_name,
                parameters={
                    **params,
                    "app_type": app_type,
                    "schedule_info": schedule_info,
                    "threshold_info": threshold_info,
                },
                confirm_label="✅ 确认创建",
                confirm_id="confirm_create",
            )

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                user_id = command.user_id or ""
                features = ["creative_mode", "task_list_execution"] if creative_mode else []
                constraints = [
                    "持续推进，不停在阶段性汇报",
                    "优先复用已有能力，必要时再生成新 skill",
                    "保证稳定性优先，避免频繁切换实现路径",
                ] if creative_mode else []
                result = await self._bus.rpc(
                    "system.meta_app",
                    SkillExecutionRequest(
                        skill_id="system.meta_app",
                        action="create_app",
                        inputs={
                            "app_name": app_name,
                            "app_goal": f"创建一个{app_type}类型的 App：{app_name}",
                            "app_type": app_type,
                            "complexity": "moderate",
                            "user_id": user_id,
                            "features": features,
                            "constraints": constraints,
                        },
                        config={"session_id": session_id, "creative_mode": creative_mode},
                    ),
                    timeout=60,
                )
                if result and getattr(result, "status", None) == "completed":
                    output = result.output
                    app_id = output.get("app_id", app_name)
                    new_skill_ids = output.get("created_skill_ids", [])

                    if new_skill_ids:
                        perm = self._check_app_modify_permission(user_id or "web-user", app_name)
                        can_create_required_skills, policy_reason = self._command_service.can_create_required_skills(
                            perm["can_create_skills"],
                        )
                        if not can_create_required_skills and policy_reason == "skill_creation_forbidden":
                            return self._command_service.build_permission_denied_response(
                                intent="create_app",
                                session_id=session_id,
                                related_app=app_name,
                                detail=(
                                    f"创建 **{app_name}** 需要以下新 skill：\n"
                                    f"`{', '.join(new_skill_ids)}`\n\n"
                                    f"**Skill 是系统共有资产**，只有 **管理员及以上** 用户才能创建。\n\n"
                                    f"请联系管理员来帮你创建这些 skill，或者用已有 skill 重新组合一个 App。"
                                ),
                            )

                    if self._config_center and new_skill_ids:
                        try:
                            for sid in new_skill_ids:
                                self._config_center.resolve_model_preference(app_id, sid)
                        except Exception:
                            pass

                    if self._persistence:
                        try:
                            self._persistence.save_state(
                                lifecycle=self._lifecycle,
                                runtime_host=self._runtime_host,
                                registry=self._app_registry,
                                catalog=self._catalog,
                            )
                        except Exception:
                            pass
                    return self._command_service.build_success_response(
                        intent="create_app",
                        session_id=session_id,
                        related_app=app_name,
                        response_type="card",
                        content=f"✅ App 创建成功！\n\n"
                                f"名称: {app_name}\n"
                                f"类型: {app_type}\n"
                                f"ID: {app_id}\n"
                                f"创作模式: {'已启用持续执行模式' if creative_mode else '标准模式'}\n"
                                f"{schedule_info}{threshold_info}",
                        actions=[
                            ActionSuggestion(
                                id="start_app", label="▶️ 启动", action_type="execute",
                                payload={"intent": "start_app", "target": app_name}, style="primary",
                            ),
                            ActionSuggestion(
                                id="list_apps", label="📱 查看列表", action_type="navigate",
                                payload={"intent": "list_apps"}, style="secondary",
                            ),
                        ],
                    )
            except Exception as e:
                return self._command_service.build_degraded_response(
                    intent="create_app",
                    session_id=session_id,
                    related_app=app_name,
                    reason="MessageBus RPC 调用失败",
                    detail=f"错误信息：{e}\n请重试或联系系统管理员。",
                )

        return self._command_service.build_degraded_response(
            intent="create_app",
            session_id=session_id,
            related_app=app_name,
            reason="系统未配置 MessageBus",
            detail="无法通过 RPC 创建 App。",
        )

    async def handle_modify_app(self, command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想修改哪个 App？想改成什么样？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        params = command.parameters or {}
        app_command = self._command_service.from_interpreted_command(command=command, session_id=session_id)
        if not self._command_service.requires_confirmation(app_command):
            return await self._execute_modify_app(command, session_id)

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        modification = params.get("modification", "未指定")
        return ChatMessageResponse(
            type="confirm",
            session_id=session_id,
            related_app=display_name,
            actions=self._command_service.build_confirmation_actions(
                intent="modify_app",
                target_app=target,
                parameters={
                    "target_app": target,
                    "modification": modification,
                },
                confirm_label="✅ 确认修改",
                confirm_id="confirm_modify",
            ),
            content=self._command_service.build_confirmation_content(
                intent="modify_app",
                related_app=display_name,
                parameters={"modification": modification},
            ),
            requires_input=True,
        )

    async def _execute_modify_app(self, command: InterpretedCommand, session_id: str) -> ChatMessageResponse:
        params = command.parameters or {}
        target_input = params.get("target_app", command.target_app) or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        modification = params.get("modification", "未指定")
        user_id = command.user_id or "web-user"

        perm_result = self._check_app_modify_permission(user_id, target)
        if not perm_result["allowed"]:
            return self._command_service.build_permission_denied_response(
                intent="modify_app",
                session_id=session_id,
                related_app=display_name,
                detail=perm_result["message"],
            )
        can_create_skills = perm_result["can_create_skills"]

        if not self._app_refinement_orchestrator:
            return self._command_service.build_degraded_response(
                intent="modify_app",
                session_id=session_id,
                related_app=display_name,
                reason="refinement orchestrator 未注入",
                detail=f"你的需求已记录：**{display_name}** 需要 **{modification}**\n请在下次系统更新后重试。",
            )

        if self._bus:
            try:
                from app.models.skill_runtime import SkillExecutionRequest
                dry_result = await self._bus.rpc(
                    "system.app_refinement",
                    SkillExecutionRequest(
                        skill_id="system.app_refinement",
                        action="dry_run",
                        inputs={
                            "app_id": target,
                            "description": f"修改 {display_name}：{modification}",
                            "new_features": [modification],
                            "user_id": user_id,
                        },
                        config={},
                    ),
                    timeout=30,
                )
                if dry_result and getattr(dry_result, "status", None) == "completed":
                    dry_output = dry_result.output
                    would_create = dry_output.get("created_skills", [])
                    reused = dry_output.get("modified_skills", [])
                    needs_new_skills = len(would_create) > 0

                    can_create_required_skills, policy_reason = self._command_service.can_create_required_skills(
                        can_create_skills,
                    )
                    if needs_new_skills and not can_create_required_skills and policy_reason == "skill_creation_forbidden":
                        return self._command_service.build_permission_denied_response(
                            intent="modify_app",
                            session_id=session_id,
                            related_app=display_name,
                            detail=(
                                f"**{display_name}** 的修改需要以下新 skill：\n"
                                f"`{', '.join(would_create)}`\n\n"
                                f"**Skill 是系统共有资产**，只有 **管理员及以上** 用户才能创建。\n\n"
                                f"请联系管理员来帮你创建这些 skill，或者使用已有 skill 重新组合一个 App。"
                            ),
                        )

                    result = await self._bus.rpc(
                        "system.app_refinement",
                        SkillExecutionRequest(
                            skill_id="system.app_refinement",
                            action="refine",
                            inputs={
                                "app_id": target,
                                "description": f"修改 {display_name}：{modification}",
                                "new_features": [modification],
                                "user_id": user_id,
                            },
                            config={},
                        ),
                        timeout=60,
                    )
                    if result and getattr(result, "status", None) == "completed":
                        summary_parts = [f"✅ **{display_name}** 修改完成！"]
                        if would_create:
                            summary_parts.append(f"🆕 新生成 skill：{', '.join(would_create)}")
                        if reused:
                            summary_parts.append(f"♻️ 复用已有 skill：{', '.join(reused)}")
                        summary_parts.append(f"\n修改内容：{modification}")
                        return self._command_service.build_success_response(
                            intent="modify_app",
                            session_id=session_id,
                            related_app=display_name,
                            content="\n".join(summary_parts),
                            actions=[
                                ActionSuggestion(
                                    id="list_apps", label="📱 查看 App", action_type="navigate",
                                    payload={"intent": "list_apps"}, style="secondary",
                                ),
                            ],
                        )
            except Exception as e:
                return self._command_service.build_degraded_response(
                    intent="modify_app",
                    session_id=session_id,
                    related_app=display_name,
                    reason="MessageBus RPC 调用失败",
                    detail=f"错误信息：{e}\n请重试或联系系统管理员。",
                )

        return self._command_service.build_degraded_response(
            intent="modify_app",
            session_id=session_id,
            related_app=display_name,
            reason="系统未配置 MessageBus",
            detail="无法通过 RPC 修改 App。",
        )
