from __future__ import annotations

from typing import Any

from app.models.app_command import AppCommand, AppCommandResult
from app.models.chat import InterpretedCommand
from app.models.chat import ActionSuggestion


class AppCommandService:
    """Application-layer facade for unified app command execution.

    Phase 1 scope:
    - normalize create_app / modify_app command shape
    - provide one explicit seam between gateway and deeper execution layers
    - allow gradual migration without forcing full behavior rewrite in one step
    """

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
    ) -> list[ActionSuggestion]:
        normalized = self.normalize_confirmed_params(intent, {
            "intent": intent,
            "target_app": target_app,
            "parameters": parameters or {},
            **(parameters or {}),
            "confirmed": True,
        })
        return [
            ActionSuggestion(
                id=confirm_id or f"confirm_{intent}",
                label=confirm_label,
                action_type="confirm",
                payload={
                    "intent": intent,
                    "target_app": normalized.get("target_app", target_app),
                    "parameters": normalized.get("parameters", {}),
                    "confirmed": True,
                    **({"modification": normalized.get("modification")} if normalized.get("modification") else {}),
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
