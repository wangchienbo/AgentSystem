from __future__ import annotations

from datetime import UTC, datetime

from app.models.evaluation import CandidateEvaluationRecord
from app.models.telemetry import InteractionTelemetryRecord, StepTelemetryRecord
from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader
from app.services.prompt_selection_service import PromptSelectionService


class PromptInvocationService:
    def __init__(
        self,
        prompt_selection: PromptSelectionService,
        model_loader: ModelConfigLoader | None = None,
        client_factory=None,
        telemetry_service=None,
        evaluation_summary_service=None,
        skill_risk_policy_service=None,
    ) -> None:
        self._prompt_selection = prompt_selection
        self._model_loader = model_loader or ModelConfigLoader()
        self._client_factory = client_factory or OpenAIResponsesClient
        self._telemetry_service = telemetry_service
        self._evaluation_summary_service = evaluation_summary_service
        self._skill_risk_policy_service = skill_risk_policy_service

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
        started_at = datetime.now(UTC)
        interaction_id = f"prompt_invoke:{app_instance_id}:{int(started_at.timestamp())}"
        if self._skill_risk_policy_service is not None:
            self._skill_risk_policy_service.record_event(
                skill_id="prompt.invoke",
                event_type="override_approved",
                actor="system",
                reason="prompt invocation executed",
                scope="prompt_invocation",
                details={"app_instance_id": app_instance_id, "query": query, "strategy": strategy},
            )
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
        normalized = self._normalize_model_result(model_result)
        latency_ms = max(int((datetime.now(UTC) - started_at).total_seconds() * 1000), 0)

        if self._telemetry_service is not None:
            self._telemetry_service.record_interaction(
                InteractionTelemetryRecord(
                    interaction_id=interaction_id,
                    app_id=app_instance_id.split(":")[0] if app_instance_id else app_instance_id,
                    request_type="prompt_invocation",
                    success=True,
                    total_input_tokens=selection.get("prompt_budget", {}).get("working_set_token_estimate", 0)
                    + selection.get("selection_summary", {}).get("selected_count", 0)
                    * selection.get("prompt_budget", {}).get("per_evidence_token_estimate", 0),
                    total_output_tokens=normalized.get("estimated_output_tokens", 0),
                    total_tokens=selection.get("prompt_budget", {}).get("working_set_token_estimate", 0)
                    + selection.get("selection_summary", {}).get("selected_count", 0)
                    * selection.get("prompt_budget", {}).get("per_evidence_token_estimate", 0)
                    + normalized.get("estimated_output_tokens", 0),
                    total_latency_ms=latency_ms,
                    strategy_name=f"prompt_invocation:{strategy}",
                )
            )
            self._telemetry_service.record_step(
                StepTelemetryRecord(
                    interaction_id=interaction_id,
                    step_id="prompt_selection",
                    step_type="system",
                    name="prompt_invocation_service",
                    latency_ms=latency_ms,
                    success=True,
                    estimated_cost=float(normalized.get("estimated_output_tokens", 0)) / 1000000,
                    payload_summary={
                        "selected_count": selection.get("selection_summary", {}).get("selected_count", 0),
                        "provider": config.provider,
                        "model": config.model,
                    },
                ),
                app_id=app_instance_id.split(":")[0] if app_instance_id else app_instance_id,
            )

        if self._evaluation_summary_service is not None:
            self._evaluation_summary_service.evaluate(
                CandidateEvaluationRecord(
                    candidate_id=f"prompt-invoke:{interaction_id}",
                    target_type="app",
                    target_id=app_instance_id.split(":")[0] if app_instance_id else app_instance_id,
                    baseline_version="prompt_invocation.v1",
                    candidate_version="prompt_invocation.v2",
                    success_delta=0.01 if normalized.get("text") else -0.01,
                    token_delta=0.0,
                    latency_delta=0.0,
                    stability_delta=0.0,
                )
            )

        return {
            **selection,
            "model_invocation": {
                "provider": config.provider,
                "model": config.model,
                "result": model_result,
            },
            "normalized_response": normalized,
            "invocation_meta": {
                "interaction_id": interaction_id,
                "latency_ms": latency_ms,
            },
        }

    def _normalize_model_result(self, result: dict) -> dict:
        text = ""
        if isinstance(result.get("output_text"), str):
            text = result["output_text"]
        elif isinstance(result.get("output"), list):
            chunks: list[str] = []
            for item in result["output"]:
                if not isinstance(item, dict):
                    continue
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                        chunks.append(content["text"])
            text = "\n".join(chunks).strip()
        elif isinstance(result.get("body_preview"), str):
            text = result["body_preview"]
        elif isinstance(result.get("stream_preview"), str):
            text = result["stream_preview"]
        estimated_output_tokens = max(len(text) // 4, 0)
        return {
            "text": text,
            "finish_status": "completed" if text or result else "empty",
            "estimated_output_tokens": estimated_output_tokens,
            "raw_kind": "responses_api",
        }
