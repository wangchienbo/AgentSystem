from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ModelPoolConfigError(ValueError):
    pass


class ModelPoolLoader:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            raise ModelPoolConfigError(f"Model pool config not found: {self._path}")
        payload = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ModelPoolConfigError("Model pool config must be a mapping")
        self._validate(payload)
        return payload

    def _validate(self, payload: dict[str, Any]) -> None:
        if payload.get("version") != 1:
            raise ModelPoolConfigError("Model pool config version must be 1")
        models = payload.get("models")
        if not isinstance(models, list) or not models:
            raise ModelPoolConfigError("models must be a non-empty list")
        model_ids = []
        for entry in models:
            if not isinstance(entry, dict):
                raise ModelPoolConfigError("each model entry must be a mapping")
            model_id = entry.get("model_id")
            base_url = entry.get("base_url")
            api_key_env = entry.get("api_key_env")
            if not model_id:
                raise ModelPoolConfigError("model_id is required")
            if model_id in model_ids:
                raise ModelPoolConfigError(f"duplicate model_id: {model_id}")
            if not base_url:
                raise ModelPoolConfigError(f"base_url is required for model {model_id}")
            if not api_key_env:
                raise ModelPoolConfigError(f"api_key_env is required for model {model_id}")
            model_ids.append(model_id)
        default_model = payload.get("default_model")
        fallback_model = payload.get("fallback_model")
        if default_model not in model_ids:
            raise ModelPoolConfigError("default_model must reference an existing model_id")
        if fallback_model not in model_ids:
            raise ModelPoolConfigError("fallback_model must reference an existing model_id")
