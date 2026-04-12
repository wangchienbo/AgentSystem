"""Memory Skill request/response models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MemorySkillRequest(BaseModel):
    operation: Literal[
        "get_profile",
        "add_feedback",
        "update_preference",
        "get_recent_feedback",
        "get_context_summary",
        "update_context_summary",
        "record_app_usage",
        "get_full_context",
    ]
    user_id: str = Field(..., min_length=1)
    # Optional fields for specific operations
    feedback: str = ""
    source: str = "chat"
    preference_key: str = ""
    preference_value: Any = None
    summary: str = ""
    app_id: str = ""
    action: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    limit: int = 10


class MemorySkillResponse(BaseModel):
    success: bool = True
    user_id: str = ""
    operation: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
