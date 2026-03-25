from __future__ import annotations

from typing import Literal, Any

from pydantic import BaseModel, Field

DiagnosticStage = Literal["create", "register", "smoke_test", "assemble", "materialize", "install", "execute", "reload"]
DiagnosticKind = Literal[
    "invalid_request",
    "adapter_error",
    "callable_generation_error",
    "contract_violation",
    "install_error",
    "execution_error",
    "reload_error",
    "policy_blocked",
]


class SkillDiagnostic(BaseModel):
    stage: DiagnosticStage
    kind: DiagnosticKind
    message: str = Field(..., min_length=1)
    retryable: bool = False
    hint: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)
    suggested_retry_request: dict[str, Any] = Field(default_factory=dict)


class SkillRetryAdviceRequest(BaseModel):
    diagnostic: SkillDiagnostic


class SkillRetryAdviceResponse(BaseModel):
    retryable: bool
    suggested_request: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class SkillDiagnosticError(ValueError):
    def __init__(self, diagnostic: SkillDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic
