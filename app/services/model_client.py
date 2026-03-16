from __future__ import annotations

import httpx

from app.models.model_config import ModelConfig


class ModelClientError(ValueError):
    pass


class OpenAIResponsesClient:
    def __init__(self, config: ModelConfig, api_key: str) -> None:
        self._config = config
        self._api_key = api_key

    def probe(self, prompt: str = "ping") -> dict:
        url = self._config.base_url.rstrip("/") + "/v1/responses"
        payload = {
            "model": self._config.model,
            "input": prompt,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise ModelClientError(f"Model probe failed: {response.status_code} {response.text[:300]}")
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type.lower():
            return response.json()
        return {
            "status_code": response.status_code,
            "content_type": content_type,
            "body_preview": response.text[:500],
        }
