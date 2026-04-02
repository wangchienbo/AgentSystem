from __future__ import annotations

from pydantic import BaseModel, Field


class PersistenceHealthSummary(BaseModel):
    base_path: str
    file_count: int = 0
    corrupted_file_count: int = 0
    corrupted_files: list[str] = Field(default_factory=list)
    json_files: list[str] = Field(default_factory=list)
    healthy: bool = True
