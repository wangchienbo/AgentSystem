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
            "stability_delta": record.stability_delta,
        }


class CoreArchiveSummarySkill:
    def summarize_evaluation(self, record: CandidateEvaluationRecord) -> dict[str, object]:
        return {
            "candidate_id": record.candidate_id,
            "target": f"{record.target_type}:{record.target_id}",
            "accepted": record.accepted,
            "reason": record.rejection_reason,
        }
