from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RequirementType = Literal["app", "skill", "hybrid", "unclear"]
DemonstrationDecision = Literal["required", "optional", "not_needed", "clarify"]


class RequirementIntent(BaseModel):
    raw_text: str = Field(..., min_length=1)
    normalized_text: str = Field(..., min_length=1)
    requirement_type: RequirementType
    demonstration_decision: DemonstrationDecision
    reason: str = Field(..., min_length=1)
    extracted_keywords: list[str] = Field(default_factory=list)
