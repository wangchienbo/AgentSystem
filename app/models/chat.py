"""Chat / LightBrain interaction models.

Request and response schemas for the natural-language interaction layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    """User sends a message to the LightBrain."""
    user_id: str = Field(..., min_length=1, description="User identifier")
    channel: str = Field(default="webchat", description="Channel: webchat, qqbot, etc.")
    message: str = Field(..., min_length=1, description="User's natural language message")
    session_id: str | None = Field(default=None, description="Existing session ID; auto-created if omitted")
    memory_context: str | None = Field(default=None, description="Cross-session memory context summary")


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
    related_app: str | None = Field(default=None, description="App this reply references")
    requires_input: bool = Field(default=False, description="Whether further user input is expected")


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
