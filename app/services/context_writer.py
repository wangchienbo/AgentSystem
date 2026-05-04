from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.models.context import ContextDetailEvent
from app.services.context_storage_paths import ContextStoragePaths, build_context_storage_paths


@dataclass
class ContextWriter:
    paths: ContextStoragePaths

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = "/root/project/AgentSystem/data/context_center") -> "ContextWriter":
        paths = build_context_storage_paths(base_dir)
        paths.detail_dir.mkdir(parents=True, exist_ok=True)
        paths.summary_dir.mkdir(parents=True, exist_ok=True)
        paths.buffer_dir.mkdir(parents=True, exist_ok=True)
        return cls(paths=paths)

    def append_detail_event(self, *, session_id: str, role: str, message: str, timestamp: datetime | None = None) -> ContextDetailEvent:
        event = ContextDetailEvent(timestamp=timestamp or datetime.now(UTC), role=role, message=message)
        day_file = self.detail_day_file(session_id, event.timestamp)
        self._append_jsonl(day_file, event)
        return event

    def append_summary_event(self, *, session_id: str, role: str, message: str, timestamp: datetime | None = None) -> ContextDetailEvent:
        event = ContextDetailEvent(timestamp=timestamp or datetime.now(UTC), role=role, message=message)
        day_file = self.summary_day_file(session_id, event.timestamp)
        self._append_jsonl(day_file, event)
        return event

    def replace_summary_event(self, *, session_id: str, role: str, message: str, timestamp: datetime | None = None) -> ContextDetailEvent:
        event = ContextDetailEvent(timestamp=timestamp or datetime.now(UTC), role=role, message=message)
        session_dir = self.paths.summary_dir / session_id
        if session_dir.exists():
            for path in session_dir.glob("*.jsonl"):
                path.unlink()
        self._append_jsonl(self.summary_day_file(session_id, event.timestamp), event)
        return event

    def detail_day_file(self, session_id: str, timestamp: datetime) -> Path:
        return self.paths.detail_dir / session_id / f"{timestamp.astimezone(UTC).date().isoformat()}.jsonl"

    def summary_day_file(self, session_id: str, timestamp: datetime) -> Path:
        return self.paths.summary_dir / session_id / f"{timestamp.astimezone(UTC).date().isoformat()}.jsonl"

    def _append_jsonl(self, path: Path, event: ContextDetailEvent) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": event.timestamp.isoformat().replace("+00:00", "Z"),
                "role": event.role,
                "message": event.message,
            }, ensure_ascii=False) + "\n")
