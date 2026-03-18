from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ConfigMutationAction = Literal["init", "set", "patch", "delete"]


class AppConfigSnapshot(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppConfigMutation(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    action: ConfigMutationAction
    key: str = Field(default="")
    value: Any = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppConfigRequest(BaseModel):
    operation: Literal["get", "set", "patch", "delete", "list"]
    key: str = Field(default="")
    value: Any = None
    config_schema: dict[str, Any] = Field(default_factory=dict)


class AppConfigResponse(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    operation: str
    values: dict[str, Any] = Field(default_factory=dict)
    key: str = Field(default="")
    value: Any = None
    history_count: int = 0
