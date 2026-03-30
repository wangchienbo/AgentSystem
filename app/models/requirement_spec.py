from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.requirement_intent import DemonstrationDecision, RequirementType

RequirementReadiness = Literal["ready", "needs_clarification", "needs_demo", "conflicting_constraints"]


class RequirementSpec(BaseModel):
    raw_text: str = Field(..., min_length=1)
    requirement_type: RequirementType
    demonstration_decision: DemonstrationDecision
    goal: str = Field(default="")
    roles: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    failure_strategy: str | None = None
    needs_demo: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    readiness: RequirementReadiness = "needs_clarification"
    recommended_questions: list[str] = Field(default_factory=list)
    extracted_keywords: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
