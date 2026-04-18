from __future__ import annotations

from typing import Any

from app.models.app_command import AppCommand, AppCommandResult
from app.models.chat import InterpretedCommand
from app.services.app_command_presenter import AppCommandPresenter


class AppCommandService:
    def __init__(self, presenter: AppCommandPresenter | None = None) -> None:
        self._presenter = presenter or AppCommandPresenter()

    def build_command(
        self,
        *,
        name: str,
        user_id: str = "",
        session_id: str = "",
        target_app: str | None = None,
        parameters: dict[str, Any] | None = None,
        confirmed: bool = False,
        source: str = "chat",
    ) -> AppCommand:
        return AppCommand(
            name=name,
            user_id=user_id,
            session_id=session_id,
            target_app=target_app,
            parameters=parameters or {},
            confirmed=confirmed,
            source=source,
        )

    def from_interpreted_command(
        self,
        *,
        command: InterpretedCommand,
        session_id: str,
        source: str = "chat",
    ) -> AppCommand:
        return self.build_command(
            name=command.intent,
            user_id=command.user_id or "",
            session_id=session_id,
            target_app=command.target_app,
            parameters=dict(command.parameters or {}),
            confirmed=bool((command.parameters or {}).get("confirmed")),
            source=source,
        )

    def requires_confirmation(self, command: AppCommand) -> bool:
        if command.name in {"create_app", "modify_app", "delete_app"} and not command.confirmed:
            return True
        return False

    def normalize_confirmed_params(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(params or {})
        parameters = dict(normalized.get("parameters") or {})

        if intent == "create_app":
            target_app = normalized.get("target_app") or normalized.get("app_name") or ""
            parameters = parameters or {"app_type": normalized.get("app_type", "unknown")}
            normalized.update({
                "target_app": target_app,
                "parameters": parameters,
                "confirmed": True,
            })
            return normalized

        if intent == "modify_app":
            target_app = normalized.get("target_app") or parameters.get("target_app") or ""
            modification = normalized.get("modification") or parameters.get("modification") or "未指定"
            parameters.update({
                "target_app": target_app,
                "modification": modification,
                "confirmed": True,
            })
            normalized.update({
                "target_app": target_app,
                "modification": modification,
                "parameters": parameters,
                "confirmed": True,
            })
            return normalized

        return normalized

    def rebuild_interpreted_command(
        self,
        *,
        intent: str,
        user_id: str,
        session_id: str,
        params: dict[str, Any],
    ) -> InterpretedCommand | None:
        normalized = self.normalize_confirmed_params(intent, params)
        target_app = normalized.get("target_app")
        if not target_app:
            return None

        app_command = self.build_command(
            name=intent,
            user_id=user_id,
            session_id=session_id,
            target_app=target_app,
            parameters=normalized.get("parameters", {}),
            confirmed=bool(normalized.get("confirmed")),
            source="action",
        )
        return InterpretedCommand(
            intent=app_command.name,
            target_app=app_command.target_app,
            parameters=app_command.parameters,
            requires_clarification=False,
            user_id=app_command.user_id,
        )

    def build_confirmation_actions(
        self,
        *,
        intent: str,
        target_app: str,
        parameters: dict[str, Any] | None = None,
        confirm_label: str,
        cancel_label: str = "❌ 取消",
        confirm_id: str | None = None,
    ) -> list[Any]:
        normalized = self.normalize_confirmed_params(intent, {
            "intent": intent,
            "target_app": target_app,
            "parameters": parameters or {},
            **(parameters or {}),
            "confirmed": True,
        })
        return self._presenter.build_confirmation_actions(
            intent=intent,
            target_app=target_app,
            normalized_payload=normalized,
            confirm_label=confirm_label,
            cancel_label=cancel_label,
            confirm_id=confirm_id,
        )

    def build_confirmation_content(
        self,
        *,
        intent: str,
        related_app: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        return self._presenter.build_confirmation_content(
            intent=intent,
            related_app=related_app,
            parameters=parameters,
        )

    def build_confirmation_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str,
        content: str | None = None,
        target_app: str,
        parameters: dict[str, Any] | None = None,
        confirm_label: str,
        confirm_id: str | None = None,
    ):
        normalized = self.normalize_confirmed_params(intent, {
            "intent": intent,
            "target_app": target_app,
            "parameters": parameters or {},
            **(parameters or {}),
            "confirmed": True,
        })
        return self._presenter.build_confirmation_response(
            intent=intent,
            session_id=session_id,
            related_app=related_app,
            target_app=target_app,
            normalized_payload=normalized,
            confirm_label=confirm_label,
            confirm_id=confirm_id,
            content=content,
        )

    def build_query_detail_response(
        self,
        *,
        session_id: str,
        related_app: str,
        title: str,
        detail: str,
        actions: list[Any] | None = None,
    ):
        return self._presenter.build_query_detail_response(
            session_id=session_id,
            related_app=related_app,
            title=title,
            detail=detail,
            actions=actions,
        )

    def build_permission_denied_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str | None,
        detail: str,
    ):
        return self._presenter.build_permission_denied_response(
            intent=intent,
            session_id=session_id,
            related_app=related_app,
            detail=detail,
        )

    def build_success_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str | None,
        content: str,
        actions: list[Any] | None = None,
        response_type: str = "text",
    ):
        return self._presenter.build_success_response(
            session_id=session_id,
            related_app=related_app,
            content=content,
            actions=actions,
            response_type=response_type,
        )

    def build_degraded_response(
        self,
        *,
        intent: str,
        session_id: str,
        related_app: str | None,
        reason: str,
        detail: str | None = None,
    ):
        return self._presenter.build_degraded_response(
            intent=intent,
            session_id=session_id,
            related_app=related_app,
            reason=reason,
            detail=detail,
        )

    def make_result(
        self,
        *,
        status: str,
        message: str,
        command: AppCommand,
        data: dict[str, Any] | None = None,
        actions: list[dict[str, Any]] | None = None,
        requires_input: bool = False,
        error_code: str | None = None,
    ) -> AppCommandResult:
        return AppCommandResult(
            status=status,
            message=message,
            command_name=command.name,
            target_app=command.target_app,
            data=data or {},
            actions=actions or [],
            requires_input=requires_input,
            error_code=error_code,
        )
