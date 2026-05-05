from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.services.context_storage_paths import ContextStoragePaths, DEFAULT_CONTEXT_CENTER_DIR, build_context_storage_paths


@dataclass
class ContextRecoveryManager:
    paths: ContextStoragePaths
    ready: bool = False
    recovering: bool = False

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = DEFAULT_CONTEXT_CENTER_DIR) -> "ContextRecoveryManager":
        return cls(paths=build_context_storage_paths(base_dir))

    def mark_recovering(self) -> None:
        self.recovering = True
        self.ready = False

    def mark_ready(self) -> None:
        self.recovering = False
        self.ready = True

    def recover_pending_sessions(self, *, buffer_dir: Path, flush_session) -> dict[str, int]:
        self.mark_recovering()
        recovered_sessions = 0
        flushed_events = 0
        for path in sorted(buffer_dir.glob("*.json")):
            session_id = path.stem
            result = flush_session(session_id, now=datetime.now(UTC))
            recovered_sessions += 1
            flushed_events += int(result.get("flushed_count") or 0)
        self.mark_ready()
        return {
            "recovered_sessions": recovered_sessions,
            "flushed_events": flushed_events,
        }
