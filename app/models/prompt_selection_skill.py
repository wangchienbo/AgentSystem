from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PromptSelectionOperation = Literal["select", "evidence_search"]


class PromptSelectionSkillRequest(BaseModel):
    operation: PromptSelectionOperation
    query: str = ""
    limit: int | None = Field(default=5, ge=1)
    category: str = ""
    app_instance_id: str = ""
