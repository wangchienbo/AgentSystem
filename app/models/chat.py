"""Chat / LightBrain interaction models.

Request and response schemas for the natural-language interaction layer.
"""

from __future__ import annotations

from typing import Literal

from app.models.cognition import StructuredAnswer

from datetime import UTC, datetime
from typing import Any, Literal as TypingLiteral

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    """User sends a message to the LightBrain."""
    user_id: str = Field(..., min_length=1, description="User identifier")
    channel: str = Field(default="webchat", description="Channel: webchat, qqbot, etc.")
    message: str = Field(..., min_length=1, description="User's natural language message")
    session_id: str | None = Field(default=None, description="Existing session ID; empty/null means create a new session")
    memory_context: str | None = Field(default=None, description="Cross-session memory context summary")

    @field_validator("session_id", mode="before")
    @classmethod
    def normalize_session_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return str(value)


class ChatActionRequest(BaseModel):
    """User clicks a button / selects an action from a previous reply."""
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    action_id: str = Field(..., min_length=1, description="The action ID from ActionSuggestion")
    action_params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core interaction models
# ---------------------------------------------------------------------------

class ActionSuggestion(BaseModel):
    """A clickable button / option the user can select."""
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1, description="Button text")
    icon: str | None = Field(default=None)
    action_type: Literal["confirm", "modify", "cancel", "navigate", "execute"] = Field(default="execute")
    payload: dict[str, Any] = Field(default_factory=dict, description="Params passed back on click")
    style: Literal["primary", "secondary", "danger", "ghost"] = Field(default="primary")


class InlineItem(BaseModel):
    """An embedded list item (e.g. an App card in a list reply)."""
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    subtitle: str | None = None
    status: Literal["running", "paused", "stopped", "error", "draft", "installed"] = Field(default="stopped")
    status_icon: str = Field(default="⚪")
    metadata: dict[str, Any] | None = None
    actions: list[ActionSuggestion] = Field(default_factory=list)


class AppTaskDispatch(BaseModel):
    """交互层识别到 app 任务时返回的 dispatch 指令。

    交互层只识别 + 描述任务，不自己执行；
    HTTP 层收到后异步 dispatch 到 MasterControl。
    """
    type: Literal["app_task"] = "app_task"
    app: str = Field(..., description="目标 App 标识")
    operation: str = Field(..., description="操作名")
    params: dict[str, Any] = Field(default_factory=dict, description="操作参数")
    parent_session: str = Field(default="", description="交互层 session_id")
    task_id: str = Field(default="", description="由 HTTP 层生成，交互层不填")


class TokenUsage(BaseModel):
    """Token usage metadata for a single interaction."""
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    model: str = Field(default="", description="Model used for this interaction")
    cached: bool = Field(default=False, description="Whether this was served from cache (zero cost)")


class ChatMessageResponse(BaseModel):
    """LightBrain's structured reply to a user message."""
    type: Literal["text", "card", "list", "form", "confirm", "progress", "error"] = Field(default="text")
    content: str = Field(..., description="Main text content")
    data: dict[str, Any] | None = Field(default=None, description="Structured data payload")
    actions: list[ActionSuggestion] = Field(default_factory=list, description="Clickable buttons/options")
    inline_items: list[InlineItem] | None = Field(default=None, description="Embedded list items")
    requires_input: bool = Field(default=False, description="Whether the reply expects further user input")
    usage: TokenUsage | None = Field(default=None, description="Token usage for this interaction")
    session_id: str = Field(..., description="Session this reply belongs to")
    structured_answer: StructuredAnswer | None = Field(default=None, description="Structured cognition/action answer contract")
    related_app: str | None = Field(default=None, description="App this reply references")
    app_task_dispatches: list[AppTaskDispatch] = Field(default_factory=list, description="App 任务分发指令（交互层不执行）")


class SessionSummary(BaseModel):
    """Summary of a conversation session."""
    session_id: str
    user_id: str
    channel: str
    created_at: datetime
    last_active_at: datetime
    message_count: int
    related_apps: list[str] = Field(default_factory=list)
    title: str = ""  # Auto-generated from first user message


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int


# ---------------------------------------------------------------------------
# Internal: interpreted command (from LightBrainInterpreter)
# ---------------------------------------------------------------------------

class InterpretedCommand(BaseModel):
    """Structured command parsed from a user's natural language message."""
    intent: str = Field(..., description="Intent: create_app, start_app, stop_app, query_app, query_status, list_apps, modify_app, delete_app, query_help, modify_interactive_app")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    target_app: str | None = Field(default=None, description="Target app name or ID if applicable")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Extracted structured parameters")
    requires_clarification: bool = Field(default=False)
    clarification_question: str | None = Field(default=None)
    suggested_actions: list[ActionSuggestion] = Field(default_factory=list)
    raw_interpretation: str = Field(default="", description="LLM/rule reasoning trace for debugging")
    user_id: str | None = Field(default=None, description="User who issued this command")
    raw_input: str | None = Field(default=None, description="Original user message")
    context: dict[str, Any] = Field(default_factory=dict, description="Runtime context for enrichment")
    structured_answer: StructuredAnswer | None = Field(default=None, description="Structured cognition/action answer contract")


class TaskContinuationDecision(BaseModel):
    """Structured next-step decision for pending task continuation."""
    conversation_mode: Literal["clarify", "draft_create", "continue_task", "execute", "report_status"]
    pending_task_id: str | None = None
    target_ref: dict[str, Any] = Field(default_factory=dict)
    draft_proposal: dict[str, Any] = Field(default_factory=dict)
    next_action: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Internal: workflow plan
# ---------------------------------------------------------------------------

class WorkflowStep(BaseModel):
    step_id: str
    action: str
    target: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    on_failure: Literal["abort", "retry", "skip", "ask_user"] = Field(default="abort")


class RollbackStep(BaseModel):
    step_id: str
    action: str
    target: str | None = None


class WorkflowPlan(BaseModel):
    steps: list[WorkflowStep] = Field(default_factory=list)
    rollback_plan: list[RollbackStep] = Field(default_factory=list)
    estimated_duration: str | None = None
    risk_level: Literal["low", "medium", "high"] = Field(default="low")


class WorkflowResult(BaseModel):
    success: bool
    command: InterpretedCommand
    steps_executed: list[str] = Field(default_factory=list)
    steps_failed: list[str] = Field(default_factory=list)
    result_data: dict[str, Any] | None = None
    error: str | None = None
    reply: ChatMessageResponse
