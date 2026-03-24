from __future__ import annotations

from pydantic import BaseModel, Field


class SkillBlueprint(BaseModel):
    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    related_experience_ids: list[str] = Field(default_factory=list)
    safety_profile: dict = Field(default_factory=dict)
