from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ContextOperation = Literal["get", "update", "append", "list_runtime_view"]
ContextSection = Literal["facts", "artifacts", "decisions", "questions", "constraints", "open_loops"]


class ContextSkillRequest(BaseModel):
    operation: ContextOperation
    current_goal: str = ""
    current_stage: str = ""
    status: str = ""
    section: ContextSection | None = None
    key: str = ""
    value: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    tags: list[str] = Field(default_factory=list)
    include_runtime: bool = False
