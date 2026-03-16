from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DataNamespaceType = Literal["app_data", "runtime_state", "system_metadata", "skill_assets"]


class DataNamespace(BaseModel):
    namespace_id: str = Field(..., min_length=1)
    app_instance_id: str | None = None
    namespace_type: DataNamespaceType
    owner_user_id: str | None = None
    path: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DataRecord(BaseModel):
    record_id: str = Field(..., min_length=1)
    namespace_id: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    value: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
