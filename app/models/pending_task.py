from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PendingTaskStatus = Literal[
    "drafted",
    "pending_input",
    "ready_to_execute",
    "executing",
    "completed",
    "blocked",
    "abandoned",
]

WorkflowStage = Literal[
    "intent_received",
    "solution_drafting",
    "solution_reviewing",
    "tasklist_preparing",
    "repo_locating",
    "implementation_pending",
    "implementation_running",
    "upgrade_pending",
    "upgrade_running",
    "acceptance_pending",
    "acceptance_running",
    "done",
    "blocked",
]

StageStatus = Literal["pending", "in_progress", "completed", "blocked"]


class PendingTaskRecord(BaseModel):
    task_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str | None = None
    intent: str = Field(..., min_length=1)
    status: PendingTaskStatus = "pending_input"
    workflow_type: str = "draft_app_bootstrap"
    current_stage: WorkflowStage = "intent_received"
    stage_status: StageStatus = "pending"
    solution_draft: dict[str, Any] = Field(default_factory=dict)
    review_result: dict[str, Any] = Field(default_factory=dict)
    task_list: list[dict[str, Any]] = Field(default_factory=list)
    repo_context: dict[str, Any] = Field(default_factory=dict)
    implementation_plan: dict[str, Any] = Field(default_factory=dict)
    upgrade_plan: dict[str, Any] = Field(default_factory=dict)
    acceptance_plan: dict[str, Any] = Field(default_factory=dict)
    draft_payload: dict[str, Any] = Field(default_factory=dict)
    target_ref: dict[str, Any] = Field(default_factory=dict)
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_recommended_action: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    last_user_message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
