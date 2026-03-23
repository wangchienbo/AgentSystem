from __future__ import annotations

from app.models.refinement_loop import (
    RefinementExperiment,
    RefinementHypothesis,
    RolloutDecision,
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

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("refinement_hypotheses", self._hypotheses)
        self._store.save_mapping("refinement_experiments", self._experiments)
        self._store.save_mapping("refinement_verifications", self._verifications)
        self._store.save_mapping("refinement_decisions", self._decisions)

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
