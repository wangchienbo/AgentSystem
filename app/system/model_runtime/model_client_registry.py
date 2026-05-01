from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.model_client import OpenAIResponsesClient
from app.models.model_config import ModelConfig


@dataclass(frozen=True)
class ModelRuntimeRecord:
    model_id: str
    provider: str
    base_url: str
    api_key_env: str
    wire_api: str
    enabled: bool
    healthy: bool = False
    role: str = "secondary"
    metadata: dict[str, Any] | None = None


class ModelClientRegistry:
    def __init__(self) -> None:
        self._configs: dict[str, ModelConfig] = {}
        self._clients: dict[str, OpenAIResponsesClient] = {}

    def register(self, model_id: str, config: ModelConfig, api_key: str) -> OpenAIResponsesClient:
        client = OpenAIResponsesClient(config=config, api_key=api_key)
        self._configs[model_id] = config
        self._clients[model_id] = client
        return client

    def get_client(self, model_id: str) -> OpenAIResponsesClient:
        try:
            return self._clients[model_id]
        except KeyError as exc:
            raise KeyError(f"Model client not found: {model_id}") from exc

    def get_config(self, model_id: str) -> ModelConfig:
        try:
            return self._configs[model_id]
        except KeyError as exc:
            raise KeyError(f"Model config not found: {model_id}") from exc

    def list_model_ids(self) -> list[str]:
        return list(self._clients.keys())
