from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppCreationFromMetaAppRequest(BaseModel):
    """User-facing request to create an app through the meta-app design layer."""
    app_name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    app_kind: str = Field(default="service")
    complexity: str = Field(default="moderate")
    user_id: str = Field(default="")
    trigger: str = Field(default="manual")
    scope: dict[str, Any] = Field(default_factory=dict)
    context: str = Field(default="")
    auto_install: bool = Field(default=False)
    workflow_inputs: dict[str, Any] = Field(default_factory=dict)
