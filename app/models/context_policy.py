from __future__ import annotations

from pydantic import BaseModel, Field


class ContextCompactionPolicy(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    max_context_entries: int = Field(default=20, ge=1)
    compact_on_workflow_complete: bool = True
    compact_on_workflow_failure: bool = True
    compact_on_stage_change: bool = False
