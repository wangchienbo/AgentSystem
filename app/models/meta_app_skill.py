from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MetaAppOperation = Literal["bootstrap"]


class MetaAppSkillRequest(BaseModel):
    operation: MetaAppOperation = "bootstrap"
    app_name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    app_kind: str = Field(default="service")
    context: dict[str, Any] = Field(default_factory=dict)
