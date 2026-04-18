from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AppCommandName = Literal[
    "create_app",
    "modify_app",
    "start_app",
    "stop_app",
    "pause_app",
    "resume_app",
    "query_app",
    "list_apps",
    "delete_app",
]

AppCommandStatus = Literal[
    "completed",
    "failed",
    "requires_clarification",
    "requires_confirmation",
    "degraded",
]


class AppCommand(BaseModel):
    """Unified application-layer command for app operations."""

    name: AppCommandName
    user_id: str = Field(default="")
    session_id: str = Field(default="")
    target_app: str | None = Field(default=None)
    parameters: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = Field(default=False)
    source: Literal["chat", "action", "api", "system"] = Field(default="chat")


class AppCommandResult(BaseModel):
    """Normalized result contract produced by the app command layer."""

    status: AppCommandStatus
    message: str
    command_name: AppCommandName
    target_app: str | None = Field(default=None)
    data: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_input: bool = Field(default=False)
    error_code: str | None = Field(default=None)
