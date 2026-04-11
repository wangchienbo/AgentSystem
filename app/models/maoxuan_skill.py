from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MaoxuanSkillRequest(BaseModel):
    query: str = Field(..., min_length=1)
    context: str = ""
    models: list[str] = Field(default_factory=list)
