from __future__ import annotations

from app.models.chat import ActionSuggestion, ChatMessageResponse, InlineItem


class AppListPresenter:
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

    def build_empty_response(self, *, session_id: str) -> ChatMessageResponse:
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
