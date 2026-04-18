from __future__ import annotations

from app.models.app_command import AppCommand


class AppCommandPolicy:
    """Policy layer for app command rules.

    Keeps command semantics separate from response presentation.
    """

    def requires_confirmation(self, command: AppCommand) -> bool:
        return command.name in {"create_app", "modify_app", "delete_app"} and not command.confirmed
