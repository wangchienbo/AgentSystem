from __future__ import annotations

from app.models.evaluation import CandidateEvaluationRecord
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.telemetry_service import TelemetryService


class CoreReplaySelectorSkill:
    def __init__(self, telemetry_service: TelemetryService) -> None:
        self.telemetry_service = telemetry_service

    def select_failed_interactions(self) -> list[str]:
        return [
            record.interaction_id
            for record in self.telemetry_service._interactions.values()  # noqa: SLF001
            if not record.success
        ]

    def select_prompt_invocation_interactions(self, *, app_id: str | None = None, failed_only: bool = False) -> list[str]:
        interactions = [
            record
            for record in self.telemetry_service._interactions.values()  # noqa: SLF001
            if record.request_type == "prompt_invocation"
        ]
        if app_id is not None:
            interactions = [item for item in interactions if item.app_id == app_id]
        if failed_only:
            interactions = [item for item in interactions if not item.success]
        return [item.interaction_id for item in interactions]

    def select_upgrade_candidates(
        self,
        *,
        app_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        latency_threshold_ms: int = 30000,
        token_threshold: int = 12000,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        interactions = list(self.telemetry_service._interactions.values())  # noqa: SLF001
        if app_id is not None:
            interactions = [item for item in interactions if item.app_id == app_id]
        if user_id is not None:
            interactions = [item for item in interactions if item.user_id == user_id]
        if session_id is not None:
            interactions = [item for item in interactions if item.session_id == session_id]

        candidates: list[dict[str, object]] = []
        for item in interactions:
            reasons: list[str] = []
            priority = 0
            if not item.success:
                reasons.append("failed_interaction")
                priority += 100
            if item.total_latency_ms >= latency_threshold_ms:
                reasons.append("high_latency")
                priority += min(40, item.total_latency_ms // 1000)
            if item.total_tokens >= token_threshold:
                reasons.append("high_token_cost")
                priority += min(30, item.total_tokens // 1000)
            if item.failure_reason == "max_turns_reached":
                reasons.append("convergence_risk")
                priority += 60
            if item.total_tool_calls >= 3:
                reasons.append("high_tool_churn")
                priority += min(20, item.total_tool_calls * 2)
            if not reasons:
                continue
            candidates.append({
                "interaction_id": item.interaction_id,
                "session_id": item.session_id,
                "user_id": item.user_id,
                "app_id": item.app_id,
                "request_type": item.request_type,
                "success": item.success,
                "total_latency_ms": item.total_latency_ms,
                "total_tokens": item.total_tokens,
                "total_tool_calls": item.total_tool_calls,
                "failure_reason": item.failure_reason,
                "priority": priority,
                "reasons": reasons,
            })

        candidates.sort(key=lambda x: (-int(x["priority"]), -int(x["total_latency_ms"]), -int(x["total_tokens"])))
        return candidates[:limit]


class CoreCostAnalyzerSkill:
    def __init__(self, telemetry_service: TelemetryService) -> None:
        self.telemetry_service = telemetry_service

    def summarize_app_cost(self, app_id: str) -> dict[str, int]:
        interactions = [
            item for item in self.telemetry_service._interactions.values()  # noqa: SLF001
            if item.app_id == app_id
        ]
        return {
            "interaction_count": len(interactions),
            "total_tokens": sum(item.total_tokens for item in interactions),
            "total_latency_ms": sum(item.total_latency_ms for item in interactions),
        }

    def summarize_prompt_invocation_cost(self, app_id: str) -> dict[str, int]:
        interactions = [
            item
            for item in self.telemetry_service._interactions.values()  # noqa: SLF001
            if item.app_id == app_id and item.request_type == "prompt_invocation"
        ]
        return {
            "interaction_count": len(interactions),
            "total_tokens": sum(item.total_tokens for item in interactions),
            "total_latency_ms": sum(item.total_latency_ms for item in interactions),
        }


class CoreAcceptanceReportSkill:
    def __init__(self, evaluation_service: EvaluationSummaryService) -> None:
        self.evaluation_service = evaluation_service

    def build_report(self, candidate_id: str) -> dict[str, object]:
        record = self.evaluation_service.get(candidate_id)
        if record is None:
            return {"found": False, "candidate_id": candidate_id}
        return {
            "found": True,
            "candidate_id": record.candidate_id,
            "target_type": record.target_type,
            "target_id": record.target_id,
            "accepted": record.accepted,
            "rejection_reason": record.rejection_reason,
            "token_delta": record.token_delta,
            "latency_delta": record.latency_delta,
            "success_delta": record.success_delta,
            "feedback_delta": record.feedback_delta,
            "stability_delta": record.stability_delta,
            "quality_signals": record.quality_signals,
        }

    def build_prompt_invocation_report(self, app_id: str) -> dict[str, object]:
        records = [
            item
            for item in self.evaluation_service.list_records()
            if item.target_type == "app" and item.target_id == app_id and item.candidate_id.startswith("prompt-invoke:")
        ]
        accepted = [item for item in records if item.accepted]
        rejected = [item for item in records if not item.accepted]
        schema_failures = sum(1 for item in records if item.quality_signals.get("schema_satisfied") is False)
        empty_outputs = sum(1 for item in records if item.quality_signals.get("empty_text") is True)
        return {
            "app_id": app_id,
            "total_records": len(records),
            "accepted_records": len(accepted),
            "rejected_records": len(rejected),
            "acceptance_rate": 0.0 if not records else len(accepted) / len(records),
            "schema_failures": schema_failures,
            "empty_outputs": empty_outputs,
            "recent_quality_signals": [item.quality_signals for item in records[-3:]],
        }


class CoreArchiveSummarySkill:
    def summarize_evaluation(self, record: CandidateEvaluationRecord) -> dict[str, object]:
        return {
            "candidate_id": record.candidate_id,
            "target": f"{record.target_type}:{record.target_id}",
            "accepted": record.accepted,
            "reason": record.rejection_reason,
            "quality_signals": record.quality_signals,
        }

    def summarize_prompt_invocation_regression(self, records: list[CandidateEvaluationRecord]) -> dict[str, object]:
        prompt_records = [item for item in records if item.candidate_id.startswith("prompt-invoke:")]
        return {
            "record_count": len(prompt_records),
            "rejected_count": sum(1 for item in prompt_records if not item.accepted),
            "success_regressions": sum(1 for item in prompt_records if item.success_delta < 0),
            "latency_regressions": sum(1 for item in prompt_records if item.latency_delta > 0),
            "token_regressions": sum(1 for item in prompt_records if item.token_delta > 0),
            "schema_failures": sum(1 for item in prompt_records if item.quality_signals.get("schema_satisfied") is False),
            "empty_outputs": sum(1 for item in prompt_records if item.quality_signals.get("empty_text") is True),
        }
