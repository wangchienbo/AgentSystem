from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.models.context import ContextDetailEvent
from app.services.context_storage_paths import ContextStoragePaths, DEFAULT_CONTEXT_CENTER_DIR, build_context_storage_paths


@dataclass
class ContextQueryService:
    paths: ContextStoragePaths

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = DEFAULT_CONTEXT_CENTER_DIR) -> "ContextQueryService":
        return cls(paths=build_context_storage_paths(base_dir))

    def read_detail_events(self, *, session_id: str, limit: int = 100) -> list[ContextDetailEvent]:
        return self._read_day_bucketed_events(self.paths.detail_dir / session_id, limit=limit)

    def read_summary_events(self, *, session_id: str, limit: int = 100) -> list[ContextDetailEvent]:
        return self._read_day_bucketed_events(self.paths.summary_dir / session_id, limit=limit)

    def _read_day_bucketed_events(self, session_dir: Path, *, limit: int) -> list[ContextDetailEvent]:
        if not session_dir.exists():
            return []
        events: list[ContextDetailEvent] = []
        for path in sorted(session_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                events.append(ContextDetailEvent.model_validate(payload))
        events.sort(key=lambda item: item.timestamp)
        return events[-limit:]
