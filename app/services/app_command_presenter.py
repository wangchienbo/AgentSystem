from __future__ import annotations

from typing import Any

from app.models.chat import ActionSuggestion, ChatMessageResponse


class AppCommandPresenter:
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
