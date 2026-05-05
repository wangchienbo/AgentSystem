from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.context_storage_paths import ContextStoragePaths, DEFAULT_CONTEXT_CENTER_DIR, build_context_storage_paths


@dataclass
class DurableContextBuffer:
    paths: ContextStoragePaths
    max_events_per_session: int = 200

    @classmethod
    def from_base_dir(
        cls,
        base_dir: str | Path = DEFAULT_CONTEXT_CENTER_DIR,
        *,
        max_events_per_session: int = 200,
    ) -> "DurableContextBuffer":
        paths = build_context_storage_paths(base_dir)
        paths.buffer_dir.mkdir(parents=True, exist_ok=True)
        return cls(paths=paths, max_events_per_session=max_events_per_session)

    def append_pending_event(self, *, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        items = self.read_pending_events(session_id=session_id)
        items.append(dict(event))
        trimmed = items[-self.max_events_per_session :]
        self._write_session_events(session_id=session_id, events=trimmed)
        return trimmed[-1]

    def read_pending_events(self, *, session_id: str) -> list[dict[str, Any]]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("events") or [])

    def replace_pending_events(self, *, session_id: str, events: list[dict[str, Any]]) -> None:
        trimmed = list(events)[-self.max_events_per_session :]
        self._write_session_events(session_id=session_id, events=trimmed)

    def clear_session(self, *, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()

    def _write_session_events(self, *, session_id: str, events: list[dict[str, Any]]) -> None:
        path = self._session_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"session_id": session_id, "events": events}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _session_path(self, session_id: str) -> Path:
        return self.paths.buffer_dir / f"{session_id}.json"
