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
            "stability_delta": record.stability_delta,
        }

    def build_prompt_invocation_report(self, app_id: str) -> dict[str, object]:
        records = [
            item
            for item in self.evaluation_service.list_records()
            if item.target_type == "app" and item.target_id == app_id and item.candidate_id.startswith("prompt-invoke:")
        ]
        accepted = [item for item in records if item.accepted]
        rejected = [item for item in records if not item.accepted]
        return {
            "app_id": app_id,
            "total_records": len(records),
            "accepted_records": len(accepted),
            "rejected_records": len(rejected),
            "acceptance_rate": 0.0 if not records else len(accepted) / len(records),
        }


class CoreArchiveSummarySkill:
    def summarize_evaluation(self, record: CandidateEvaluationRecord) -> dict[str, object]:
        return {
            "candidate_id": record.candidate_id,
            "target": f"{record.target_type}:{record.target_id}",
            "accepted": record.accepted,
            "reason": record.rejection_reason,
        }

    def summarize_prompt_invocation_regression(self, records: list[CandidateEvaluationRecord]) -> dict[str, object]:
        prompt_records = [item for item in records if item.candidate_id.startswith("prompt-invoke:")]
        return {
            "record_count": len(prompt_records),
            "rejected_count": sum(1 for item in prompt_records if not item.accepted),
            "success_regressions": sum(1 for item in prompt_records if item.success_delta < 0),
            "latency_regressions": sum(1 for item in prompt_records if item.latency_delta > 0),
            "token_regressions": sum(1 for item in prompt_records if item.token_delta > 0),
        }
