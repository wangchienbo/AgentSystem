from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal

from pydantic import BaseModel, Field

SkillStatus = Literal["active", "disabled", "rollback_ready"]


class SkillVersion(BaseModel):
    version: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = Field(default="")


class SkillRegistryEntry(BaseModel):
    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    immutable_interface: bool = False
    status: SkillStatus = "active"
    active_version: str = Field(..., min_length=1)
    versions: list[SkillVersion] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class SkillMutationResult(BaseModel):
    skill_id: str
    action: Literal["replace", "rollback", "disable", "enable"]
    status: SkillStatus
    active_version: str
