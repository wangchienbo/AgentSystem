from __future__ import annotations

from collections.abc import Callable
from typing import Any


class AppCommandRouter:
    """Router for app-domain intents.

    Keeps app intent mapping separate from the gateway's broader mixed handler table.
    """

    def __init__(self, handlers: dict[str, Callable[..., Any]] | None = None) -> None:
        self._handlers = handlers or {}

    def register(self, intent: str, handler: Callable[..., Any]) -> None:
        self._handlers[intent] = handler

    def register_many(self, handlers: dict[str, Callable[..., Any]]) -> None:
        self._handlers.update(handlers)

    def resolve(self, intent: str):
        return self._handlers.get(intent)

    def intents(self) -> set[str]:
        return set(self._handlers.keys())

    def handles(self, intent: str) -> bool:
        return intent in self._handlers
