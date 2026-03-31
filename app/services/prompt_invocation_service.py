from __future__ import annotations

from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader
from app.services.prompt_selection_service import PromptSelectionService


class PromptInvocationService:
    def __init__(
        self,
        prompt_selection: PromptSelectionService,
        model_loader: ModelConfigLoader | None = None,
        client_factory=None,
    ) -> None:
        self._prompt_selection = prompt_selection
        self._model_loader = model_loader or ModelConfigLoader()
        self._client_factory = client_factory or OpenAIResponsesClient

    def invoke_with_selection(
        self,
        *,
        app_instance_id: str,
        query: str = "",
        category: str | None = None,
        limit: int = 5,
        max_prompt_tokens: int | None = None,
        reserved_output_tokens: int = 256,
        working_set_token_estimate: int = 400,
        per_evidence_token_estimate: int = 120,
        strategy: str = "balanced",
        include_prompt_assembly: bool = True,
        extra_payload: dict | None = None,
    ) -> dict:
        selection = self._prompt_selection.select_for_prompt(
            app_instance_id=app_instance_id,
            limit=limit,
            query=query,
            category=category,
            max_prompt_tokens=max_prompt_tokens,
            reserved_output_tokens=reserved_output_tokens,
            working_set_token_estimate=working_set_token_estimate,
            per_evidence_token_estimate=per_evidence_token_estimate,
            strategy=strategy,
            include_prompt_assembly=include_prompt_assembly,
        )
        assembled_prompt = selection.get("assembled_prompt", "")
        config = self._model_loader.load()
        api_key = self._model_loader.resolve_api_key(config)
        client = self._client_factory(config=config, api_key=api_key)
        model_result = client.request(assembled_prompt, extra_payload=extra_payload)
        return {
            **selection,
            "model_invocation": {
                "provider": config.provider,
                "model": config.model,
                "result": model_result,
            },
        }
