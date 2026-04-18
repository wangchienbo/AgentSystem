from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.chat import InterpretedCommand
from app.services.app_command_service import AppCommandService


@dataclass
class AppCommandRecoveryResult:
    command: InterpretedCommand | None
    normalized_params: dict[str, Any]


class AppCommandRecoveryService:
    def __init__(self, command_service: AppCommandService) -> None:
        self._command_service = command_service

    def recover_command(
        self,
        *,
        intent: str,
        user_id: str,
        session_id: str,
        action_params: dict[str, Any] | None,
        last_command: InterpretedCommand | None,
        force_confirmed: bool = True,
    ) -> AppCommandRecoveryResult:
        normalized = self._command_service.normalize_confirmed_params(intent, action_params or {})
        command = self._recover_from_normalized(
            intent=intent,
            user_id=user_id,
            session_id=session_id,
            normalized=normalized,
            last_command=last_command,
            force_confirmed=force_confirmed,
        )
        return AppCommandRecoveryResult(command=command, normalized_params=normalized)

    def recover_from_source(
        self,
        *,
        intent: str,
        user_id: str,
        session_id: str,
        source: str,
        payload: dict[str, Any] | None,
        last_command: InterpretedCommand | None,
        force_confirmed: bool,
    ) -> AppCommandRecoveryResult:
        normalized = dict(payload or {})
        normalized.setdefault("intent", intent)
        normalized.setdefault("recovery_source", source)
        command = self._recover_from_normalized(
            intent=intent,
            user_id=user_id,
            session_id=session_id,
            normalized=normalized,
            last_command=last_command,
            force_confirmed=force_confirmed,
        )
        return AppCommandRecoveryResult(command=command, normalized_params=normalized)

    def _recover_from_normalized(
        self,
        *,
        intent: str,
        user_id: str,
        session_id: str,
        normalized: dict[str, Any],
        last_command: InterpretedCommand | None,
        force_confirmed: bool,
    ) -> InterpretedCommand | None:
        command = last_command
        if not command:
            command = self._command_service.rebuild_interpreted_command(
                intent=intent,
                user_id=user_id,
                session_id=session_id,
                params=normalized,
            )
        if not command:
            target_app = normalized.get("target_app") or normalized.get("target")
            command = InterpretedCommand(
                intent=intent,
                target_app=target_app,
                parameters=dict(normalized.get("parameters") or {}),
                requires_clarification=False,
                user_id=user_id,
            )
        if not command:
            return None

        command.parameters = dict(command.parameters or {})
        command.parameters.update(normalized.get("parameters", {}))

        recovered_target = (
            normalized.get("target_app")
            or normalized.get("target")
            or command.target_app
        )
        if recovered_target:
            command.target_app = recovered_target

        if force_confirmed and normalized.get("confirmed") is not None:
            command.parameters["confirmed"] = normalized.get("confirmed")

        return command
