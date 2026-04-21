from __future__ import annotations

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    provider: str = Field(default="OpenAICompatible")
    base_url: str = Field(..., min_length=1)
    wire_api: str = Field(default="openai-responses")
    model: str = Field(default="gpt-4.1")  # Default to gpt-4.1 (widely supported)
    api_key_env: str = Field(default="OPENAI_API_KEY")
    api_key: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
