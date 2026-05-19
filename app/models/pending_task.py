from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


WORKFLOW_STAGE_INTENT_RECEIVED = "intent_received"
WORKFLOW_STAGE_SOLUTION_DRAFTING = "solution_drafting"
WORKFLOW_STAGE_SOLUTION_REVIEWING = "solution_reviewing"
WORKFLOW_STAGE_TASKLIST_PREPARING = "tasklist_preparing"
WORKFLOW_STAGE_REPO_LOCATING = "repo_locating"
WORKFLOW_STAGE_IMPLEMENTATION_PENDING = "implementation_pending"
WORKFLOW_STAGE_IMPLEMENTATION_RUNNING = "implementation_running"
WORKFLOW_STAGE_UPGRADE_PENDING = "upgrade_pending"
WORKFLOW_STAGE_UPGRADE_RUNNING = "upgrade_running"
WORKFLOW_STAGE_ACCEPTANCE_PENDING = "acceptance_pending"
WORKFLOW_STAGE_ACCEPTANCE_RUNNING = "acceptance_running"
WORKFLOW_STAGE_DONE = "done"
WORKFLOW_STAGE_BLOCKED = "blocked"

WORKFLOW_STAGE_VALUES = (
    WORKFLOW_STAGE_INTENT_RECEIVED,
    WORKFLOW_STAGE_SOLUTION_DRAFTING,
    WORKFLOW_STAGE_SOLUTION_REVIEWING,
    WORKFLOW_STAGE_TASKLIST_PREPARING,
    WORKFLOW_STAGE_REPO_LOCATING,
    WORKFLOW_STAGE_IMPLEMENTATION_PENDING,
    WORKFLOW_STAGE_IMPLEMENTATION_RUNNING,
    WORKFLOW_STAGE_UPGRADE_PENDING,
    WORKFLOW_STAGE_UPGRADE_RUNNING,
    WORKFLOW_STAGE_ACCEPTANCE_PENDING,
    WORKFLOW_STAGE_ACCEPTANCE_RUNNING,
    WORKFLOW_STAGE_DONE,
    WORKFLOW_STAGE_BLOCKED,
)

STAGE_STATUS_PENDING = "pending"
STAGE_STATUS_IN_PROGRESS = "in_progress"
STAGE_STATUS_COMPLETED = "completed"
STAGE_STATUS_BLOCKED = "blocked"

STAGE_STATUS_VALUES = (
    STAGE_STATUS_PENDING,
    STAGE_STATUS_IN_PROGRESS,
    STAGE_STATUS_COMPLETED,
    STAGE_STATUS_BLOCKED,
)

PENDING_TASK_ACTION_APPLY_DRAFT_APP = "apply_draft_app"
PENDING_TASK_ACTION_APPROVE_SOLUTION_DRAFT = "approve_solution_draft"
PENDING_TASK_ACTION_REVISE_SOLUTION_DRAFT = "revise_solution_draft"
PENDING_TASK_ACTION_MATERIALIZE_TASK_LIST = "materialize_task_list"
PENDING_TASK_ACTION_LOCATE_REPO_CONTEXT = "locate_repo_context"
PENDING_TASK_ACTION_IMPLEMENT_APP_CHANGE = "implement_app_change"
PENDING_TASK_ACTION_UPGRADE_APP_RUNTIME = "upgrade_app_runtime"
PENDING_TASK_ACTION_RUN_ACCEPTANCE = "run_acceptance"

PENDING_TASK_ACTION_VALUES = (
    PENDING_TASK_ACTION_APPLY_DRAFT_APP,
    PENDING_TASK_ACTION_APPROVE_SOLUTION_DRAFT,
    PENDING_TASK_ACTION_REVISE_SOLUTION_DRAFT,
    PENDING_TASK_ACTION_MATERIALIZE_TASK_LIST,
    PENDING_TASK_ACTION_LOCATE_REPO_CONTEXT,
    PENDING_TASK_ACTION_IMPLEMENT_APP_CHANGE,
    PENDING_TASK_ACTION_UPGRADE_APP_RUNTIME,
    PENDING_TASK_ACTION_RUN_ACCEPTANCE,
)


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
    current_stage: WorkflowStage = WORKFLOW_STAGE_INTENT_RECEIVED
    stage_status: StageStatus = STAGE_STATUS_PENDING
    solution_draft: dict[str, Any] = Field(default_factory=dict)
    review_result: dict[str, Any] = Field(default_factory=dict)
    task_list: list[dict[str, Any]] = Field(default_factory=list)
    repo_context: dict[str, Any] = Field(
        default_factory=lambda: {
            "active_repo_path": "",
            "repo_valid": False,
            "primary_readme_path": "",
            "primary_readme_exists": False,
            "key_docs": [],
            "target_modules": [],
            "git_branch": "",
            "git_dirty": False,
        }
    )
    implementation_plan: dict[str, Any] = Field(
        default_factory=lambda: {
            "repo_path": "",
            "target_files": [],
            "changed_files_intent": [],
            "work_items": [],
            "validation_map": [],
            "summary": "",
        }
    )
    upgrade_plan: dict[str, Any] = Field(
        default_factory=lambda: {
            "build_install_plan": [],
            "activation_reload_path": [],
            "rollback_hint": "",
        }
    )
    acceptance_plan: dict[str, Any] = Field(
        default_factory=lambda: {
            "test_probe_commands": [],
            "http_runtime_verification_points": [],
            "success_criteria": [],
            "results": [],
            "evidence_summary": {"command_count": 0, "passed_count": 0, "failed_count": 0},
        }
    )
    draft_payload: dict[str, Any] = Field(default_factory=dict)
    target_ref: dict[str, Any] = Field(default_factory=dict)
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_recommended_action: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    last_user_message: str = ""
    error_message: str = ""  # 后台执行时的错误信息
    completed_stages: list[str] = Field(default_factory=list)  # 已完成的阶段列表
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
