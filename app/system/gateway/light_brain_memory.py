"""LightBrain Memory — persistent session and state management.

Handles conversation session lifecycle, message history storage,
and system state persistence across restarts.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.chat import (
    ChatMessageResponse,
    InterpretedCommand,
    SessionSummary,
)


def _sanitize_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                key = str(key)
            sanitized[key] = _sanitize_jsonable(item)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_jsonable(item) for item in value]
    return repr(value)


def _command_snapshot(command: InterpretedCommand) -> dict[str, Any]:
    data = command.model_dump(mode="python")
    data["parameters"] = _sanitize_jsonable(data.get("parameters", {}))
    data["context"] = _sanitize_jsonable(data.get("context", {}))
    data["suggested_actions"] = _sanitize_jsonable(data.get("suggested_actions", []))
    return data


# ---------------------------------------------------------------------------
# Internal models
# ---------------------------------------------------------------------------

class _SessionRecord:
    """In-memory session record, persisted to disk."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        channel: str,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.channel = channel
        self.created_at = datetime.now(UTC)
        self.last_active_at = self.created_at
        self.messages: list[dict[str, Any]] = []  # {role, content, timestamp}
        self.last_command: InterpretedCommand | None = None
        self.last_reply: ChatMessageResponse | None = None
        self.related_apps: set[str] = set()
        self.compact_threshold: int = 50  # messages before compaction

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        self.last_active_at = datetime.now(UTC)

    def to_summary(self) -> SessionSummary:
        # Auto-generate title from first user message
        title = ""
        for msg in self.messages:
            if msg.get("role") == "user":
                title = msg.get("content", "")[:40]
                break
        if not title:
            title = "空对话"
        return SessionSummary(
            session_id=self.session_id,
            user_id=self.user_id,
            channel=self.channel,
            created_at=self.created_at,
            last_active_at=self.last_active_at,
            message_count=len(self.messages),
            related_apps=sorted(self.related_apps),
            title=title,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel": self.channel,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "messages": self.messages,
            "last_command": _command_snapshot(self.last_command) if self.last_command else None,
            "last_reply": self.last_reply.model_dump() if self.last_reply else None,
            "related_apps": sorted(self.related_apps),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_SessionRecord":
        record = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            channel=data["channel"],
        )
        record.created_at = datetime.fromisoformat(data["created_at"])
        record.last_active_at = datetime.fromisoformat(data["last_active_at"])
        record.messages = data.get("messages", [])
        if data.get("last_command"):
            record.last_command = InterpretedCommand(**data["last_command"])
        if data.get("last_reply"):
            record.last_reply = ChatMessageResponse(**data["last_reply"])
        record.related_apps = set(data.get("related_apps", []))
        return record

    def needs_compaction(self) -> bool:
        return len(self.messages) > self.compact_threshold

    def compact(self) -> None:
        """Simple compaction: drop oldest messages beyond threshold."""
        if len(self.messages) > self.compact_threshold:
            self.messages = self.messages[-self.compact_threshold:]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class LightBrainMemoryError(Exception):
    """Error raised by LightBrainMemory operations."""


# ---------------------------------------------------------------------------
# LightBrainMemory service
# ---------------------------------------------------------------------------

class LightBrainMemory:
    """In-memory session store with optional disk persistence.

    Phase 5.1: session lifecycle management + persistence layer.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._sessions: dict[str, _SessionRecord] = {}
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".lightbrain" / "sessions"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_dir = self._data_dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._identity_path = self._data_dir / "identity.json"
        self._identity: dict[str, Any] = {}
        self._load_existing_sessions()

    # -- session lifecycle --------------------------------------------------

    def create_session(self, user_id: str, channel: str, session_id: str | None = None) -> _SessionRecord:
        """Create a new conversation session."""
        import uuid
        sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        if sid in self._sessions:
            return self._sessions[sid]
        record = _SessionRecord(session_id=sid, user_id=user_id, channel=channel)
        self._sessions[sid] = record
        self._persist_session(record)
        return record

    def get_session(self, session_id: str) -> _SessionRecord | None:
        return self._sessions.get(session_id)

    def list_sessions(self, user_id: str | None = None) -> list[SessionSummary]:
        sessions = list(self._sessions.values())
        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]
        return [s.to_summary() for s in sessions]

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        path = self._sessions_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
        return True

    def record_user_message(self, session_id: str, message: str) -> None:
        record = self._sessions.get(session_id)
        if not record:
            raise LightBrainMemoryError(f"Session not found: {session_id}")
        record.add_message("user", message)
        self._persist_session(record)

    def record_command(self, session_id: str, command: InterpretedCommand) -> None:
        record = self._sessions.get(session_id)
        if not record:
            raise LightBrainMemoryError(f"Session not found: {session_id}")
        record.last_command = command
        if command.target_app:
            record.related_apps.add(command.target_app)
        self._persist_session(record)

    def record_reply(self, session_id: str, reply: ChatMessageResponse) -> None:
        record = self._sessions.get(session_id)
        if not record:
            raise LightBrainMemoryError(f"Session not found: {session_id}")
        record.last_reply = reply
        # Include token usage in the stored message if available
        msg_data: dict[str, Any] = {
            "role": "assistant",
            "content": reply.content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if reply.usage:
            msg_data["usage"] = reply.usage.model_dump(mode="json")
        record.messages.append(msg_data)
        if reply.related_app:
            record.related_apps.add(reply.related_app)
        if record.needs_compaction():
            record.compact()
        self._persist_session(record)

    def get_recent_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        record = self._sessions.get(session_id)
        if not record:
            raise LightBrainMemoryError(f"Session not found: {session_id}")
        return record.messages[-limit:]

    def get_user_recent_messages(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """Get recent messages across ALL sessions for a user, ordered by time."""
        all_msgs: list[tuple[str, dict[str, Any]]] = []
        for record in self._sessions.values():
            if record.user_id == user_id:
                for msg in record.messages:
                    all_msgs.append((msg.get("timestamp", ""), msg))
        all_msgs.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in all_msgs[:limit]]

    def find_similar(self, raw_input: str | None, limit: int = 3) -> list[dict[str, Any]]:
        """Find similar past interactions (placeholder for Phase 5.1)."""
        # Phase 5.1: currently no-op, returns empty list
        # Future: semantic similarity search over message history
        return []

    # -- identity -----------------------------------------------------------

    def save_identity(self, identity: dict[str, Any]) -> None:
        """Save gateway identity metadata."""
        self._identity = identity
        try:
            self._identity_path.write_text(json.dumps(identity, indent=2, ensure_ascii=False))
        except OSError as e:
            raise LightBrainMemoryError(f"Failed to persist identity: {e}")

    def load_identity(self) -> dict[str, Any] | None:
        """Load gateway identity metadata."""
        if self._identity:
            return self._identity
        if self._identity_path.exists():
            try:
                self._identity = json.loads(self._identity_path.read_text())
                return self._identity
            except Exception:
                return None
        return None

    def export_state(self) -> dict[str, Any]:
        """Export full memory state for snapshot persistence."""
        return {
            "sessions": {sid: s.to_dict() for sid, s in self._sessions.items()},
            "identity": self._identity,
            "exported_at": datetime.now(UTC).isoformat(),
        }

    def restore_from(self, snapshot: dict[str, Any] | None) -> None:
        """Restore memory state from a snapshot."""
        if not snapshot:
            return
        sessions = snapshot.get("sessions", {})
        for sid, data in sessions.items():
            try:
                self._sessions[sid] = _SessionRecord.from_dict(data)
            except Exception:
                continue
        self._identity = snapshot.get("identity", {})

    # -- persistence --------------------------------------------------------

    def _persist_session(self, record: _SessionRecord) -> None:
        path = self._sessions_dir / f"{record.session_id}.json"
        try:
            path.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
        except OSError as e:
            raise LightBrainMemoryError(f"Failed to persist session {record.session_id}: {e}")

    def _load_existing_sessions(self) -> None:
        """Load sessions from disk on startup."""
        for path in self._sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                record = _SessionRecord.from_dict(data)
                self._sessions[record.session_id] = record
            except Exception:
                # Corrupted session file — skip
                continue
