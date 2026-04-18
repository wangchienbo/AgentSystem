from __future__ import annotations

from typing import Any

from app.models.app_command import AppCommand, AppCommandResult


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
