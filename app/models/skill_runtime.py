from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SkillExecutionRequest(BaseModel):
    skill_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class SkillExecutionResult(BaseModel):
    skill_id: str = Field(..., min_length=1)
    status: str = Field(default="completed")
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    error_detail: dict[str, Any] = Field(default_factory=dict)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
