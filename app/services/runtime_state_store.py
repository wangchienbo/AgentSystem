from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class RuntimeStateStore:
    def __init__(self, base_dir: str = "data/runtime") -> None:
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_collection(self, name: str, items: list[BaseModel]) -> None:
        payload = [item.model_dump(mode="json") for item in items]
        self._write_json(name, payload)

    def save_mapping(self, name: str, mapping: dict[str, BaseModel]) -> None:
        payload = {key: value.model_dump(mode="json") for key, value in mapping.items()}
        self._write_json(name, payload)

    def save_nested_mapping(self, name: str, mapping: dict[str, list[BaseModel]]) -> None:
        payload = {
            key: [item.model_dump(mode="json") for item in values]
            for key, values in mapping.items()
        }
        self._write_json(name, payload)

    def load_json(self, name: str, default: Any) -> Any:
        path = self.base_path / f"{name}.json"
        if not path.exists():
            return default
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return default
        if not raw.strip():
            self._quarantine_invalid_file(path, reason="empty")
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self._quarantine_invalid_file(path, reason="invalid")
            return default

    def _write_json(self, name: str, payload: Any) -> None:
        path = self.base_path / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _quarantine_invalid_file(self, path: Path, *, reason: str) -> None:
        try:
            quarantine_dir = self.base_path / "corrupted"
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            target = quarantine_dir / f"{path.stem}.{reason}.json"
            if target.exists():
                target = quarantine_dir / f"{path.stem}.{reason}.{path.stat().st_mtime_ns}.json"
            shutil.move(str(path), str(target))
        except OSError:
            return
