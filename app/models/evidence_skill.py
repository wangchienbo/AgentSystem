from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceSkillOperation = Literal["list_signals", "list_promoted", "list_index", "stats", "context_summary", "search_index"]


class EvidenceSkillRequest(BaseModel):
    operation: EvidenceSkillOperation
    app_instance_id: str = ""
    limit: int | None = Field(default=None, ge=1)
