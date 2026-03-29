from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_creation import AppFromSkillsResult, SkillCreationResult
from app.models.app_blueprint import AppBlueprint


class SuggestedSkillRefinementRequest(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    goal: str = Field(default="refine app from suggested skills")
    experience_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    workflow_id: str = Field(default="wf.suggested.refinement")
    persist_missing_skills: bool = True


class SuggestedSkillRefinementResult(BaseModel):
    blueprint: AppBlueprint
    app_result: AppFromSkillsResult
    created_skills: list[SkillCreationResult] = Field(default_factory=list)
    reused_skill_ids: list[str] = Field(default_factory=list)
    selected_blueprints: list[SkillBlueprint] = Field(default_factory=list)
