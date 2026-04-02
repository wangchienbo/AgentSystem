from __future__ import annotations

from typing import Any

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


class SuggestedSkillRefinementClosureRequest(SuggestedSkillRefinementRequest):
    install: bool = False
    run: bool = False
    user_id: str = Field(default="")
    workflow_inputs: dict[str, Any] = Field(default_factory=dict)
    trigger: str = Field(default="manual")
    reviewer: str = Field(default="")
    version: str = Field(default="candidate-1")
    note: str = Field(default="phase5 refined candidate")


class SuggestedSkillRefinementClosureResult(BaseModel):
    blueprint: AppBlueprint
    app_result: AppFromSkillsResult
    created_skills: list[SkillCreationResult] = Field(default_factory=list)
    reused_skill_ids: list[str] = Field(default_factory=list)
    selected_blueprints: list[SkillBlueprint] = Field(default_factory=list)
    materialized_skill_ids: list[str] = Field(default_factory=list)
    release_entry: dict[str, Any] | None = None
    install_result: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    compare_summary: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
