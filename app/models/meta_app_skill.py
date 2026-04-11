from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MetaAppOperation = Literal["generate_control_skill"]


class MetaAppSkillRequest(BaseModel):
    operation: MetaAppOperation = "generate_control_skill"
    app_name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    app_kind: str = Field(default="service")
    complexity: str = Field(default="moderate")
    scope: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
