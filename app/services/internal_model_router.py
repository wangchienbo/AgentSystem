"""Internal Model Router — the only component that directly calls LLM APIs.

This module is the single exit point for all model API calls in the system.
No other component should import model_client directly. All LLM invocations
must go through this router.

Concurrency rule: ONLY model API calls are serialized here. Everything else
(user requests, tool execution, build/install) runs in parallel.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader


class InternalModelRouter:
    """Central router for all LLM API calls.

    Enforces:
    - Single serialization point for model API calls (semaphore)
    - Consistent error handling and retry
    - Configuration-driven model selection
    - No direct model_client imports elsewhere in the system
    """

    def __init__(
        self,
        config_loader: ModelConfigLoader | None = None,
        max_concurrent: int = 1,
    ) -> None:
        self._config_loader = config_loader or ModelConfigLoader()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client: OpenAIResponsesClient | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Load configuration and create model client."""
        if self._initialized:
            return
        config = self._config_loader.load()
        api_key = self._config_loader.resolve_api_key(config)
        self._client = OpenAIResponsesClient(config=config, api_key=api_key)
        self._initialized = True

    async def call(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model_override: str | None = None,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Make a model API call through the serialization semaphore.

        Args:
            prompt: User/system prompt
            system_prompt: Optional system prompt
            tools: Optional tool definitions for function calling
            model_override: Optional model name override
            timeout: Max wait time in seconds

        Returns:
            Model response dict
        """
        if not self._initialized:
            await self.initialize()

        if not self._client:
            raise RuntimeError("Model client not initialized")

        async with self._semaphore:
            # All model calls go through this single gate
            return await self._client.chat(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=tools,
                model_override=model_override,
                timeout=timeout,
            )

    async def call_with_tools(
        self,
        prompt: str,
        tool_entries: list[Any],
        system_prompt: str | None = None,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Call model with tool definitions converted from ToolEntry objects."""
        tools_schema = [entry.to_llm_context() for entry in tool_entries]
        return await self.call(
            prompt=prompt,
            system_prompt=system_prompt,
            tools=tools_schema,
            timeout=timeout,
        )

    def is_available(self) -> bool:
        """Check if the model router is initialized and ready."""
        return self._initialized and self._client is not None
