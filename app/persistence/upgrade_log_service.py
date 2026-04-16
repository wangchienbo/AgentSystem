from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.models.upgrade_log import UpgradeLogEvent


class UpgradeLogService:
    def __init__(self, base_dir: str = "data/runtime/upgrade_logs") -> None:
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def append_event(self, stream: str, event: UpgradeLogEvent) -> Path:
        stream_path = self.base_path / stream
        stream_path.mkdir(parents=True, exist_ok=True)
        file_path = stream_path / f"{event.ts.date().isoformat()}.jsonl"
        payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        with file_path.open("a", encoding="utf-8") as f:
            f.write(payload + "\n")
        return file_path

    def read_events(self, stream: str, day: str) -> list[UpgradeLogEvent]:
        file_path = self.base_path / stream / f"{day}.jsonl"
        if not file_path.exists():
            return []
        events: list[UpgradeLogEvent] = []
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(UpgradeLogEvent.model_validate(json.loads(line)))
        return events

    def day_path(self, stream: str, ts: datetime) -> Path:
        return self.base_path / stream / f"{ts.date().isoformat()}.jsonl"
