from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ContextCompactionSkillOperation = Literal["compact", "working_set", "layers", "select_for_prompt"]


class ContextCompactionSkillRequest(BaseModel):
    operation: ContextCompactionSkillOperation
    reason: str = "manual"
