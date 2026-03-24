from __future__ import annotations

from pydantic import BaseModel


class OperatorPageMeta(BaseModel):
    returned_count: int = 0
    total_count: int = 0
    filtered_count: int = 0
    has_more: bool = False
    window_since: str | None = None
    next_cursor: str | None = None
