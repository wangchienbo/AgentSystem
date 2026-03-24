from __future__ import annotations

from pydantic import BaseModel, Field


class OperatorFilterParams(BaseModel):
    app_instance_id: str | None = None
    limit: int | None = Field(default=None, ge=1)
    since: str | None = None
    cursor: str | None = None
