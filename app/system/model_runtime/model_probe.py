from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from app.ai.model_client import ModelClientError, OpenAIResponsesClient
from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


class ProbeClientProtocol(Protocol):
    def probe(self, prompt: str = "ping") -> dict: ...


class ModelProbe:
    def probe(self, record: ModelRuntimeRecord, client: ProbeClientProtocol) -> ModelRuntimeRecord:
        try:
            client.probe("ping")
            return replace(record, healthy=True)
        except ModelClientError:
            return replace(record, healthy=False)
