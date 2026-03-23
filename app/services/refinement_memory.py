from __future__ import annotations

from app.models.refinement_loop import (
    RefinementExperiment,
    RefinementHypothesis,
    RolloutDecision,
    VerificationResult,
)


class RefinementMemoryStore:
    def __init__(self) -> None:
        self._hypotheses: dict[str, RefinementHypothesis] = {}
        self._experiments: dict[str, RefinementExperiment] = {}
        self._verifications: dict[str, VerificationResult] = {}
        self._decisions: dict[str, RolloutDecision] = {}

    def add_hypothesis(self, item: RefinementHypothesis) -> RefinementHypothesis:
        self._hypotheses[item.hypothesis_id] = item
        return item

    def add_experiment(self, item: RefinementExperiment) -> RefinementExperiment:
        self._experiments[item.experiment_id] = item
        return item

    def add_verification(self, item: VerificationResult) -> VerificationResult:
        self._verifications[item.verification_id] = item
        return item

    def add_decision(self, item: RolloutDecision) -> RolloutDecision:
        self._decisions[item.decision_id] = item
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
