from __future__ import annotations

from app.models.evaluation import CandidateEvaluationRecord, EvaluationGatePolicy
from app.models.upgrade_log import UpgradeLogEvent
from app.services.runtime_state_store import RuntimeStateStore
from app.services.upgrade_log_service import UpgradeLogService


class EvaluationSummaryService:
    def __init__(self, store: RuntimeStateStore, upgrade_log_service: UpgradeLogService) -> None:
        self.store = store
        self.upgrade_log_service = upgrade_log_service
        self._records: dict[str, CandidateEvaluationRecord] = {}
        self._load()

    def evaluate(self, record: CandidateEvaluationRecord, policy: EvaluationGatePolicy | None = None) -> CandidateEvaluationRecord:
        gate = policy or EvaluationGatePolicy()
        accepted = True
        rejection_reasons: list[str] = []

        if record.token_delta > gate.max_token_growth:
            accepted = False
            rejection_reasons.append("token_growth_exceeded")
        if record.latency_delta > gate.max_latency_growth:
            accepted = False
            rejection_reasons.append("latency_growth_exceeded")
        if record.success_delta < gate.min_success_delta:
            accepted = False
            rejection_reasons.append("success_regression_exceeded")
        if record.feedback_delta < gate.min_feedback_delta:
            accepted = False
            rejection_reasons.append("feedback_regression_exceeded")
        if record.stability_delta < gate.min_stability_delta:
            accepted = False
            rejection_reasons.append("stability_regression_exceeded")

        evaluated = record.model_copy(
            update={
                "accepted": accepted,
                "rejection_reason": ",".join(rejection_reasons),
            }
        )
        self._records[evaluated.candidate_id] = evaluated
        self._persist()
        try:
            self.upgrade_log_service.append_event(
                "evaluations",
                UpgradeLogEvent(
                    event_id=f"evaluation:{evaluated.candidate_id}",
                    event_type="candidate_evaluated",
                    scope=evaluated.target_type,
                    app_id=evaluated.target_id if evaluated.target_type == "app" else None,
                    skill_id=evaluated.target_id if evaluated.target_type == "skill" else None,
                    payload=evaluated.model_dump(mode="json"),
                ),
            )
        except OSError:
            pass
        return evaluated

    def get(self, candidate_id: str) -> CandidateEvaluationRecord | None:
        return self._records.get(candidate_id)

    def list_records(self) -> list[CandidateEvaluationRecord]:
        return list(self._records.values())

    def _persist(self) -> None:
        self.store.save_mapping("telemetry_candidate_evaluations", self._records)

    def _load(self) -> None:
        self._records = {
            key: CandidateEvaluationRecord.model_validate(value)
            for key, value in self.store.load_json("telemetry_candidate_evaluations", {}).items()
        }
