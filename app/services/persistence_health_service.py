from __future__ import annotations

from pathlib import Path

from app.models.persistence_health import PersistenceHealthSummary
from app.services.runtime_state_store import RuntimeStateStore


class PersistenceHealthService:
    def __init__(self, store: RuntimeStateStore) -> None:
        self._store = store

    def get_summary(self) -> PersistenceHealthSummary:
        base = self._store.base_path
        json_files = sorted(str(path.relative_to(base)) for path in base.rglob("*.json") if path.is_file())
        corrupted_dir = base / "corrupted"
        corrupted_files = []
        if corrupted_dir.exists():
            corrupted_files = sorted(str(path.relative_to(base)) for path in corrupted_dir.rglob("*.json") if path.is_file())
        return PersistenceHealthSummary(
            base_path=str(base),
            file_count=len(json_files),
            corrupted_file_count=len(corrupted_files),
            corrupted_files=corrupted_files,
            json_files=json_files,
            healthy=len(corrupted_files) == 0,
        )
