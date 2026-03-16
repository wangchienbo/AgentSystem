from __future__ import annotations

import json
import os
from pathlib import Path

from app.models.model_config import ModelConfig


class ModelConfigError(ValueError):
    pass


class ModelConfigLoader:
    def __init__(self, local_config_path: str = "config/model.local.json") -> None:
        self._local_config_path = Path(local_config_path)

    def load(self) -> ModelConfig:
        if self._local_config_path.exists():
            payload = json.loads(self._local_config_path.read_text(encoding="utf-8"))
            return ModelConfig(**payload)
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("MODEL_BASE_URL")
        model = os.getenv("OPENAI_MODEL") or os.getenv("MODEL_NAME") or "gpt-5.4"
        if not base_url:
            raise ModelConfigError(
                "Model base URL not configured. Provide config/model.local.json or OPENAI_BASE_URL."
            )
        return ModelConfig(base_url=base_url, model=model)

    def resolve_api_key(self, config: ModelConfig) -> str:
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise ModelConfigError(f"Missing API key in env var: {config.api_key_env}")
        return api_key
