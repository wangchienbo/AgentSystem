from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.models.chat import InterpretedCommand
from app.services.app_command_router import AppCommandRouter


class AppApplicationService:
    """Unified application-layer entry for app-domain commands.

    This is the first real cut from gateway-owned app flows toward an
    app-domain application layer.
    """

    def __init__(self, router: AppCommandRouter | None = None) -> None:
        self._router = router or AppCommandRouter()

    def register_handler(
        self,
        intent: str,
        handler: Callable[[InterpretedCommand, str, list[dict[str, Any]]], Awaitable[Any]],
    ) -> None:
        self._router.register(intent, handler)

    def register_handlers(
        self,
        handlers: dict[str, Callable[[InterpretedCommand, str, list[dict[str, Any]]], Awaitable[Any]]],
    ) -> None:
        self._router.register_many(handlers)

    def owns(self, intent: str) -> bool:
        return self._router.handles(intent)

    async def handle(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ):
        handler = self._router.resolve(command.intent)
        if not handler:
            return None
        return await handler(command, session_id, available_apps)
