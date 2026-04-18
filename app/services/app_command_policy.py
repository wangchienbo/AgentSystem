from __future__ import annotations

from app.models.app_command import AppCommand


class AppCommandPolicy:
    """Policy layer for app command rules.

    Keeps command semantics separate from response presentation.
    """

    def requires_confirmation(self, command: AppCommand) -> bool:
        return command.name in {"create_app", "modify_app", "delete_app"} and not command.confirmed

    def can_pause_from_status(self, current_status: str) -> tuple[bool, str | None]:
        if current_status == "paused":
            return False, "already_paused"
        return True, None

    def can_resume_from_status(self, current_status: str) -> tuple[bool, str | None]:
        if current_status == "running":
            return False, "already_running"
        if current_status != "paused":
            return False, "invalid_resume_state"
        return True, None
