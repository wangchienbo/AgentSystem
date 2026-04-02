from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


AuthorityScope = Literal[
    "app_install",
    "app_activate",
    "app_rollback",
    "blueprint_materialization",
    "generated_app_assembly",
    "prompt_invocation",
]


class AuthorityPolicyRecord(BaseModel):
    scope: AuthorityScope
    require_reviewer: bool = False
    allowed_reviewers: list[str] = Field(default_factory=list)
    require_reason: bool = False
    allow_automatic: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthorityDecisionResult(BaseModel):
    scope: AuthorityScope
    allowed: bool = True
    reason: str = Field(default="")
    reviewer_required: bool = False
    reviewer: str = Field(default="")


class AuthoritySummary(BaseModel):
    items: list[AuthorityPolicyRecord] = Field(default_factory=list)
    active_scope_count: int = 0
    reviewer_required_scope_count: int = 0
    automatic_scope_count: int = 0
