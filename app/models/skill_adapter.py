from __future__ import annotations

from pydantic import BaseModel, Field

SkillAdapterType = str


class SkillAdapterSpec(BaseModel):
    kind: str = Field(default="callable", min_length=1)
    entry: str = Field(default="", min_length=0)
    command: list[str] = Field(default_factory=list)
    invocation_protocol: str = Field(default="", min_length=0)
    timeout_seconds: int = Field(default=15, ge=1)
