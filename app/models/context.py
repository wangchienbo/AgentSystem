from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

SessionKind = Literal["root", "child", "continuation_child"]
SessionLinkType = Literal["child", "continuation", "related"]
ContextRecordKind = Literal["message", "summary", "system_note", "tool_result"]
SessionStatus = Literal["active", "idle", "resolved", "archived"]
ActorKind = Literal["interaction", "orchestration", "app", "skill", "system"]


class SessionLink(BaseModel):
    parent_session_id: str = Field(..., min_length=1)
    child_session_id: str = Field(..., min_length=1)
    link_type: SessionLinkType = Field(default="child")
    parent_actor: ActorKind = Field(default="system")
    child_actor: ActorKind = Field(default="system")
    topic_key: str = Field(default="")
    status: SessionStatus = Field(default="active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="system", min_length=1)


class SessionContextRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: f"ctx-{uuid.uuid4().hex[:12]}")
    session_id: str = Field(..., min_length=1)
    kind: ContextRecordKind = Field(default="message")
    role: str = Field(default="system")
    content: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SessionContextWindow(BaseModel):
    session_id: str = Field(..., min_length=1)
    records: list[SessionContextRecord] = Field(default_factory=list)


class SessionNode(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    channel: str = Field(..., min_length=1)
    kind: SessionKind = Field(default="root")
    actor: ActorKind = Field(default="interaction")
    topic_key: str = Field(default="")
    root_session_id: str | None = None
    parent_session_id: str | None = None
    status: SessionStatus = Field(default="active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
