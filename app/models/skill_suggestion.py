from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.skill_blueprint import SkillBlueprint


class SkillSuggestionRequest(BaseModel):
    experience_id: str = Field(..., min_length=1)
    persist: bool = False


class SkillSuggestionResult(BaseModel):
    experience_id: str
    suggestion: SkillBlueprint
    persisted: bool = False
    governance_context: dict = Field(default_factory=dict)
