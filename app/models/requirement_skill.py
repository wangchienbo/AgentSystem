from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RequirementSkillOperation = Literal["clarify", "extract", "readiness", "blueprint_draft"]


class RequirementSkillRequest(BaseModel):
    operation: RequirementSkillOperation
    text: str = Field(..., min_length=1)
    include_evidence_ingest: bool = True
    options: dict[str, Any] = Field(default_factory=dict)
