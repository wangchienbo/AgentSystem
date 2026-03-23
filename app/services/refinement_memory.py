from __future__ import annotations

from app.models.refinement_loop import (
    FailedHypothesisRecord,
    RefinementDashboard,
    RefinementExperiment,
    RefinementHypothesis,
    RefinementOverview,
    RolloutDecision,
    RolloutQueueItem,
    VerificationResult,
)
from app.services.runtime_state_store import RuntimeStateStore


class RefinementMemoryStore:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store
        self._hypotheses: dict[str, RefinementHypothesis] = {}
        self._experiments: dict[str, RefinementExperiment] = {}
        self._verifications: dict[str, VerificationResult] = {}
        self._decisions: dict[str, RolloutDecision] = {}
        self._queue: dict[str, RolloutQueueItem] = {}
        self._failed_hypotheses: dict[str, FailedHypothesisRecord] = {}
        self._load()

    def add_hypothesis(self, item: RefinementHypothesis) -> RefinementHypothesis:
        self._hypotheses[item.hypothesis_id] = item
        self._persist()
        return item

    def add_experiment(self, item: RefinementExperiment) -> RefinementExperiment:
        self._experiments[item.experiment_id] = item
        self._persist()
        return item

    def add_verification(self, item: VerificationResult) -> VerificationResult:
        self._verifications[item.verification_id] = item
        self._persist()
        return item

    def add_decision(self, item: RolloutDecision) -> RolloutDecision:
        self._decisions[item.decision_id] = item
        self._persist()
        return item

    def add_queue_item(self, item: RolloutQueueItem) -> RolloutQueueItem:
        self._queue[item.queue_id] = item
        self._persist()
        return item

    def add_failed_hypothesis(self, item: FailedHypothesisRecord) -> FailedHypothesisRecord:
        self._failed_hypotheses[item.record_id] = item
        self._persist()
        return item

    def list_hypotheses(self, app_instance_id: str | None = None) -> list[RefinementHypothesis]:
        items = list(self._hypotheses.values())
        if app_instance_id is not None:
            items = [item for item in items if item.app_instance_id == app_instance_id]
        return items

    def list_experiments(self, hypothesis_id: str | None = None) -> list[RefinementExperiment]:
        items = list(self._experiments.values())
        if hypothesis_id is not None:
            items = [item for item in items if item.hypothesis_id == hypothesis_id]
        return items

    def list_verifications(self, hypothesis_id: str | None = None) -> list[VerificationResult]:
        items = list(self._verifications.values())
        if hypothesis_id is not None:
            items = [item for item in items if item.hypothesis_id == hypothesis_id]
        return items

    def list_decisions(self, hypothesis_id: str | None = None) -> list[RolloutDecision]:
        items = list(self._decisions.values())
        if hypothesis_id is not None:
            items = [item for item in items if item.hypothesis_id == hypothesis_id]
        return items

    def list_queue(self, app_instance_id: str | None = None, hypothesis_id: str | None = None) -> list[RolloutQueueItem]:
        items = list(self._queue.values())
        if app_instance_id is not None:
            items = [item for item in items if item.app_instance_id == app_instance_id]
        if hypothesis_id is not None:
            items = [item for item in items if item.hypothesis_id == hypothesis_id]
        return items

    def list_failed_hypotheses(self, app_instance_id: str | None = None, hypothesis_id: str | None = None) -> list[FailedHypothesisRecord]:
        items = list(self._failed_hypotheses.values())
        if app_instance_id is not None:
            items = [item for item in items if item.app_instance_id == app_instance_id]
        if hypothesis_id is not None:
            items = [item for item in items if item.hypothesis_id == hypothesis_id]
        return items

    def build_overview(self, app_instance_id: str) -> RefinementOverview:
        hypotheses = self.list_hypotheses(app_instance_id)
        hypothesis_ids = {item.hypothesis_id for item in hypotheses}
        verifications = [item for item in self._verifications.values() if item.hypothesis_id in hypothesis_ids]
        decisions = [item for item in self._decisions.values() if item.hypothesis_id in hypothesis_ids]
        queue_items = self.list_queue(app_instance_id=app_instance_id)
        failed_hypotheses = self.list_failed_hypotheses(app_instance_id=app_instance_id)
        latest_hypothesis = max(hypotheses, key=lambda item: item.created_at) if hypotheses else None
        latest_verification = max(verifications, key=lambda item: item.created_at) if verifications else None
        latest_decision = max(decisions, key=lambda item: item.created_at) if decisions else None
        latest_queue_item = max(queue_items, key=lambda item: item.created_at) if queue_items else None
        latest_failed_hypothesis = max(failed_hypotheses, key=lambda item: item.created_at) if failed_hypotheses else None
        return RefinementOverview(
            app_instance_id=app_instance_id,
            hypothesis_count=len(hypotheses),
            unresolved_hypothesis_count=sum(1 for item in hypotheses if item.status in {"proposed", "approved"}),
            verification_count=len(verifications),
            passed_verification_count=sum(1 for item in verifications if item.outcome == "passed"),
            failed_verification_count=sum(1 for item in verifications if item.outcome == "failed"),
            decision_count=len(decisions),
            promote_count=sum(1 for item in decisions if item.status == "promote"),
            hold_count=sum(1 for item in decisions if item.status == "hold"),
            queue_count=len(queue_items),
            queued_count=sum(1 for item in queue_items if item.status == "queued"),
            applied_count=sum(1 for item in queue_items if item.status == "applied"),
            failed_hypothesis_count=len(failed_hypotheses),
            latest_hypothesis=latest_hypothesis,
            latest_verification=latest_verification,
            latest_decision=latest_decision,
            latest_queue_item=latest_queue_item,
            latest_failed_hypothesis=latest_failed_hypothesis,
        )

    def build_dashboard(self, app_instance_id: str, limit: int = 5) -> RefinementDashboard:
        overview = self.build_overview(app_instance_id)
        recent_hypotheses = sorted(self.list_hypotheses(app_instance_id), key=lambda item: item.created_at, reverse=True)[:limit]
        hypothesis_ids = {item.hypothesis_id for item in recent_hypotheses}
        recent_verifications = sorted(
            [item for item in self._verifications.values() if item.app_instance_id == app_instance_id],
            key=lambda item: item.created_at,
            reverse=True,
        )[:limit]
        recent_decisions = sorted(
            [item for item in self._decisions.values() if item.app_instance_id == app_instance_id],
            key=lambda item: item.created_at,
            reverse=True,
        )[:limit]
        recent_queue_items = sorted(self.list_queue(app_instance_id=app_instance_id), key=lambda item: item.created_at, reverse=True)[:limit]
        recent_failed_hypotheses = sorted(
            self.list_failed_hypotheses(app_instance_id=app_instance_id), key=lambda item: item.created_at, reverse=True
        )[:limit]
        return RefinementDashboard(
            overview=overview,
            recent_hypotheses=recent_hypotheses,
            recent_verifications=recent_verifications,
            recent_decisions=recent_decisions,
            recent_queue_items=recent_queue_items,
            recent_failed_hypotheses=recent_failed_hypotheses,
        )

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("refinement_hypotheses", self._hypotheses)
        self._store.save_mapping("refinement_experiments", self._experiments)
        self._store.save_mapping("refinement_verifications", self._verifications)
        self._store.save_mapping("refinement_decisions", self._decisions)
        self._store.save_mapping("refinement_queue", self._queue)
        self._store.save_mapping("refinement_failed_hypotheses", self._failed_hypotheses)

    def _load(self) -> None:
        if self._store is None:
            return
        self._hypotheses = {
            key: RefinementHypothesis.model_validate(value)
            for key, value in self._store.load_json("refinement_hypotheses", {}).items()
        }
        self._experiments = {
            key: RefinementExperiment.model_validate(value)
            for key, value in self._store.load_json("refinement_experiments", {}).items()
        }
        self._verifications = {
            key: VerificationResult.model_validate(value)
            for key, value in self._store.load_json("refinement_verifications", {}).items()
        }
        self._decisions = {
            key: RolloutDecision.model_validate(value)
            for key, value in self._store.load_json("refinement_decisions", {}).items()
        }
        self._queue = {
            key: RolloutQueueItem.model_validate(value)
            for key, value in self._store.load_json("refinement_queue", {}).items()
        }
        self._failed_hypotheses = {
            key: FailedHypothesisRecord.model_validate(value)
            for key, value in self._store.load_json("refinement_failed_hypotheses", {}).items()
        }
