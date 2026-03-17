from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class WorkflowEventSubscription(BaseModel):
    subscription_id: str = Field(..., min_length=1)
    event_name: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
