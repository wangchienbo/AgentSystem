from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkflowInsightOperation = Literal["overview", "timeline", "stats", "dashboard"]


class WorkflowInsightSkillRequest(BaseModel):
    operation: WorkflowInsightOperation
    workflow_id: str | None = None
    failed_step_id: str | None = None
    limit: int | None = Field(default=None, ge=1)
