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

        quality_signals = self._derive_quality_signals(normalized, extra_payload)
        if self._evaluation_summary_service is not None:
            feedback_delta = self._derive_feedback_delta(extra_payload)
            success_delta = self._derive_success_delta(normalized, extra_payload, quality_signals)
            stability_delta = self._derive_stability_delta(normalized, extra_payload, quality_signals)
            self._evaluation_summary_service.evaluate(
                CandidateEvaluationRecord(
                    candidate_id=f"prompt-invoke:{interaction_id}",
                    target_type="app",
                    target_id=app_instance_id.split(":")[0] if app_instance_id else app_instance_id,
                    baseline_version="prompt_invocation.v1",
                    candidate_version="prompt_invocation.v2",
                    success_delta=success_delta,
                    token_delta=0.0,
                    latency_delta=0.0,
                    feedback_delta=feedback_delta,
                    stability_delta=stability_delta,
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
            "quality_signals": quality_signals,
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
            "text_length": len(text),
        }

    def _derive_feedback_delta(self, extra_payload: dict | None) -> float:
        if not isinstance(extra_payload, dict):
            return 0.0
        feedback = extra_payload.get("feedback")
        if isinstance(feedback, dict):
            score = feedback.get("score")
            if isinstance(score, (int, float)):
                return max(min((float(score) - 3.0) / 2.0, 1.0), -1.0)
        return 0.0

    def _derive_quality_signals(self, normalized: dict, extra_payload: dict | None) -> dict:
        text = normalized.get("text", "") or ""
        text_length = normalized.get("text_length", 0)
        empty_text = text_length == 0
        very_short_text = 0 < text_length < 8
        schema_expectation = None
        schema_satisfied = None
        workflow_success_hint = None
        if isinstance(extra_payload, dict):
            schema_expectation = extra_payload.get("expected_output")
            workflow_success_hint = extra_payload.get("workflow_outcome")
            if schema_expectation == "json_object":
                stripped = text.strip()
                schema_satisfied = stripped.startswith("{") and stripped.endswith("}")
            elif schema_expectation == "slug_text":
                schema_satisfied = bool(text) and (text == text.lower()) and (" " not in text)
        score = 0.0
        if not empty_text:
            score += 0.03
        if very_short_text:
            score -= 0.02
        if schema_satisfied is True:
            score += 0.03
        if schema_satisfied is False:
            score -= 0.04
        if workflow_success_hint == "success":
            score += 0.02
        elif workflow_success_hint == "failure":
            score -= 0.05
        return {
            "empty_text": empty_text,
            "very_short_text": very_short_text,
            "schema_expectation": schema_expectation,
            "schema_satisfied": schema_satisfied,
            "workflow_success_hint": workflow_success_hint,
            "quality_score": score,
        }

    def _derive_success_delta(self, normalized: dict, extra_payload: dict | None, quality_signals: dict) -> float:
        if isinstance(extra_payload, dict):
            outcome = extra_payload.get("workflow_outcome")
            if outcome == "success":
                return max(0.05 + quality_signals.get("quality_score", 0.0), -0.20)
            if outcome == "failure":
                return min(-0.10 + quality_signals.get("quality_score", 0.0), 0.05)
        return (0.01 if normalized.get("text") else -0.05) + quality_signals.get("quality_score", 0.0)

    def _derive_stability_delta(self, normalized: dict, extra_payload: dict | None, quality_signals: dict) -> float:
        delta = 0.0
        if normalized.get("finish_status") != "completed":
            delta -= 0.05
        if quality_signals.get("very_short_text"):
            delta -= 0.02
        if quality_signals.get("schema_satisfied") is False:
            delta -= 0.02
        if isinstance(extra_payload, dict) and extra_payload.get("retry_count", 0) not in (0, None):
            delta -= 0.01
        return delta
