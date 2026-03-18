from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SystemStateOperation = Literal["get", "set", "patch", "delete", "list"]
SystemAuditLevel = Literal["info", "warning", "error"]


class SystemStateRequest(BaseModel):
    operation: SystemStateOperation
    key: str = Field(default="")
    value: Any = None


class SystemStateResponse(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    operation: str
    key: str = Field(default="")
    value: Any = None
    values: dict[str, Any] = Field(default_factory=dict)


class SystemAuditRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    level: SystemAuditLevel = "info"


class SystemAuditRecord(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    level: SystemAuditLevel = "info"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
