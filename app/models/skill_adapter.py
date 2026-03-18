from __future__ import annotations

from pydantic import BaseModel, Field

SkillAdapterType = str


class SkillAdapterSpec(BaseModel):
    kind: str = Field(default="callable", min_length=1)
    entry: str = Field(default="", min_length=0)
    command: list[str] = Field(default_factory=list)
