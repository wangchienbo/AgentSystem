from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from app.models.model_config import ModelConfig

DEFAULT_MODEL_CONFIG_PATH = Path("/root/.config/agentsystem/config.yaml")
LEGACY_MODEL_JSON_PATH = Path("/root/.config/agentsystem/model.local.json")
LEGACY_MODEL_ENV_PATH = Path("/root/.config/agentsystem/model.local.env")


class ModelConfigError(ValueError):
    pass


class ModelConfigLoader:
    def __init__(self, local_config_path: str | None = None) -> None:
        self._local_config_path = Path(local_config_path) if local_config_path else DEFAULT_MODEL_CONFIG_PATH

    def load(self) -> ModelConfig:
        if self._local_config_path.exists():
            payload = yaml.safe_load(self._local_config_path.read_text(encoding="utf-8")) or {}
            model_payload = payload.get("model") if isinstance(payload, dict) else None
            if not isinstance(model_payload, dict):
                raise ModelConfigError(f"Missing 'model' section in {self._local_config_path}")
            config = ModelConfig(**model_payload)
            if getattr(config, "api_key", None):
                os.environ.setdefault(config.api_key_env, config.api_key)
            return config

        self._load_legacy_private_env_file_if_present()
        if LEGACY_MODEL_JSON_PATH.exists():
            payload = json.loads(LEGACY_MODEL_JSON_PATH.read_text(encoding="utf-8"))
            return ModelConfig(**payload)

        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("MODEL_BASE_URL")
        model = os.getenv("OPENAI_MODEL") or os.getenv("MODEL_NAME") or "gpt-5.4"
        if not base_url:
            raise ModelConfigError(
                f"Model base URL not configured. Provide {self._local_config_path} or OPENAI_BASE_URL."
            )
        return ModelConfig(base_url=base_url, model=model)

    def resolve_api_key(self, config: ModelConfig) -> str:
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise ModelConfigError(f"Missing API key in env var: {config.api_key_env}")
        return api_key

    def _load_legacy_private_env_file_if_present(self) -> None:
        if not LEGACY_MODEL_ENV_PATH.exists():
            return
        for line in LEGACY_MODEL_ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
