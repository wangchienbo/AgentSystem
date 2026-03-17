from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.experience import ExperienceRecord


class PracticeReviewRequest(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    max_events: int = Field(default=10, ge=1)
    max_records_per_namespace: int = Field(default=10, ge=1)


class PracticeReviewResult(BaseModel):
    app_instance_id: str
    event_count: int
    record_count: int
    context_entry_count: int = 0
    experience: ExperienceRecord
