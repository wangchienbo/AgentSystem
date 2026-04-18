from __future__ import annotations

from typing import Any

from app.models.chat import ActionSuggestion, ChatMessageResponse, InlineItem


class AppPresenter:
    def build_confirmation_actions(
        self,
        *,
        intent: str,
        target_app: str,
        normalized_payload: dict[str, Any],
        confirm_label: str,
        cancel_label: str = "❌ 取消",
        confirm_id: str | None = None,
    ) -> list[ActionSuggestion]:
        return [
            ActionSuggestion(
                id=confirm_id or f"confirm_{intent}",
                label=confirm_label,
                action_type="confirm",
                payload={
                    "intent": intent,
                    "target_app": normalized_payload.get("target_app", target_app),
                    "parameters": normalized_payload.get("parameters", {}),
                    "confirmed": True,
                    **({"modification": normalized_payload.get("modification")} if normalized_payload.get("modification") else {}),
                },
                style="primary",
            ),
            ActionSuggestion(
                id="cancel",
                label=cancel_label,
                action_type="cancel",
                payload={"intent": "cancel"},
                style="ghost",
            ),
        ]

    def build_confirmation_content(
        self,
        *,
        intent: str,
        related_app: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        params = parameters or {}
        if intent == "create_app":
            app_type = params.get("app_type", "unknown")
            schedule_info = params.get("schedule_info", "")
            threshold_info = params.get("threshold_info", "")
            return (
                f"将创建新的 App：**{related_app}**\n\n"
                f"类型: {app_type}"
                f"{schedule_info}{threshold_info}\n\n"
                f"确认后系统会通过统一主链路创建 App，必要时生成或复用相关 skill。"
            )
        if intent == "modify_app":
            modification = params.get("modification", "未指定")
            return (
                f"将 **{related_app}** 修改为：{modification}\n\n"
                f"确认后系统会分析需求，使用已有 skill 或生成新 skill 来完成修改。\n\n"
                f"⚠️ 注意：如果修改需要生成新 skill，仅管理员及以上用户可执行。"
            )
        return f"确认执行 {intent}: {related_app}"

    def build_confirmation_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str,
        target_app: str,
        normalized_payload: dict[str, Any],
        confirm_label: str,
        confirm_id: str | None = None,
        content: str | None = None,
    ) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="confirm",
            content=content or self.build_confirmation_content(
                intent=intent,
                related_app=related_app,
                parameters=normalized_payload.get("parameters", {}),
            ),
            session_id=session_id,
            related_app=related_app,
            actions=self.build_confirmation_actions(
                intent=intent,
                target_app=target_app,
                normalized_payload=normalized_payload,
                confirm_label=confirm_label,
                confirm_id=confirm_id,
            ),
            requires_input=True,
        )

    def build_query_detail_response(
        self,
        *,
        session_id: str,
        related_app: str,
        title: str,
        detail: str,
        actions: list[ActionSuggestion] | None = None,
    ) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="card",
            content=f"{title}\n\n{detail}",
            session_id=session_id,
            related_app=related_app,
            actions=actions or [],
        )

    def build_permission_denied_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str | None,
        detail: str,
    ) -> ChatMessageResponse:
        operation_map = {
            "create_app": "创建 App",
            "modify_app": "修改 App",
        }
        operation = operation_map.get(intent, intent)
        return ChatMessageResponse(
            type="text",
            content=f"⚠️ {operation} 权限不足。\n\n{detail}",
            session_id=session_id,
            related_app=related_app,
        )

    def build_success_response(
        self,
        *,
        session_id: str,
        related_app: str | None,
        content: str,
        actions: list[ActionSuggestion] | None = None,
        response_type: str = "text",
    ) -> ChatMessageResponse:
        return ChatMessageResponse(
            type=response_type,
            content=content,
            session_id=session_id,
            related_app=related_app,
            actions=actions or [],
        )

    def build_degraded_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str | None,
        reason: str,
        detail: str | None = None,
    ) -> ChatMessageResponse:
        operation_map = {
            "create_app": "创建 App",
            "modify_app": "修改 App",
        }
        operation = operation_map.get(intent, intent)
        content = f"⚠️ {operation} 当前无法完成，原因：{reason}。"
        if detail:
            content += f"\n\n{detail}"
        return ChatMessageResponse(
            type="text",
            content=content,
            session_id=session_id,
            related_app=related_app,
        )

    def build_empty_list_response(self, *, session_id: str) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="text",
            content="你还没有任何 App。要我帮你创建一个吗？",
            session_id=session_id,
            actions=[
                ActionSuggestion(id="create_app", label="➕ 创建 App", action_type="navigate", payload={"intent": "create_app"}, style="primary"),
            ],
        )

    def build_list_response(self, *, session_id: str, user_apps: list[dict]) -> ChatMessageResponse:
        groups: dict[str, list[dict]] = {}
        for app in user_apps:
            status = app.get("status", "unknown")
            groups.setdefault(status, []).append(app)

        status_labels = {
            "running": ("🟢", "运行中"),
            "paused": ("🟡", "已暂停"),
            "stopped": ("🔴", "已停止"),
            "draft": ("⚪", "草稿"),
            "installed": ("🔵", "已安装"),
            "error": ("⛔", "故障"),
        }

        items: list[InlineItem] = []
        for status_key in ["running", "paused", "installed", "stopped", "draft", "error"]:
            for app in groups.get(status_key, []):
                icon, _label = status_labels.get(status_key, ("⚪", "未知"))
                app_actions: list[ActionSuggestion] = []
                if status_key == "running":
                    app_actions = [
                        ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": app.get("name")}, style="danger"),
                        ActionSuggestion(id="pause", label="⏸ 暂停", action_type="execute", payload={"intent": "pause_app", "target": app.get("name")}, style="secondary"),
                    ]
                elif status_key in ("stopped", "installed"):
                    app_actions = [
                        ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": app.get("name")}, style="primary"),
                        ActionSuggestion(id="query", label="📋 详情", action_type="execute", payload={"intent": "query_app", "target": app.get("name")}, style="secondary"),
                    ]
                elif status_key == "paused":
                    app_actions = [
                        ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": app.get("name")}, style="primary"),
                    ]

                items.append(InlineItem(
                    id=app.get("app_id", ""),
                    title=app.get("name", ""),
                    subtitle=app.get("description"),
                    status=status_key,
                    status_icon=icon,
                    actions=app_actions,
                ))

        return ChatMessageResponse(
            type="list",
            content=f"你目前有 {len(user_apps)} 个 App",
            session_id=session_id,
            inline_items=items,
            actions=[
                ActionSuggestion(id="create_new", label="➕ 新建 App", action_type="navigate", payload={"intent": "create_app"}, style="primary"),
                ActionSuggestion(id="help", label="❓ 帮助", action_type="navigate", payload={"intent": "query_help"}, style="secondary"),
            ],
        )

    def build_status_card_response(
        self,
        *,
        session_id: str,
        related_app: str,
        icon: str,
        label: str,
        actions: list[ActionSuggestion] | None = None,
    ) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="card",
            content=f"{icon} **{related_app}**\n\n状态: {label}",
            session_id=session_id,
            related_app=related_app,
            actions=actions or [],
        )

    def build_system_status_response(self, *, session_id: str, total: int, running: int) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="card",
            content=f"📊 系统状态\n\nApp 总数: {total}\n运行中: {running}\n已停止: {total - running}\n系统运行正常 ✅",
            session_id=session_id,
            actions=[
                ActionSuggestion(id="list_apps", label="📱 查看 App 列表", action_type="navigate", payload={"intent": "list_apps"}, style="primary"),
            ],
        )
