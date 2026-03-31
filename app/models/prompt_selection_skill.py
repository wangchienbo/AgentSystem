from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PromptSelectionOperation = Literal["select", "evidence_search"]


class PromptSelectionSkillRequest(BaseModel):
    operation: PromptSelectionOperation
    query: str = ""
    limit: int | None = Field(default=5, ge=1)
    category: str = ""
    app_instance_id: str = ""
    max_prompt_tokens: int | None = Field(default=None, ge=1)
    reserved_output_tokens: int = Field(default=256, ge=0)
    working_set_token_estimate: int = Field(default=400, ge=0)
    per_evidence_token_estimate: int = Field(default=120, ge=1)
    strategy: str = "balanced"
    include_prompt_assembly: bool = True
