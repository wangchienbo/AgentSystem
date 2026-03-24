from __future__ import annotations

from datetime import datetime

from app.models.skill_risk_policy import SkillRiskDecision
from app.services.runtime_state_store import RuntimeStateStore


class SkillRiskPolicyService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store
        self._decisions: dict[str, SkillRiskDecision] = {}
        if self._store is not None:
            self._load()

    def list_decisions(self) -> list[SkillRiskDecision]:
        return sorted(self._decisions.values(), key=lambda item: item.created_at, reverse=True)

    def get_decision(self, skill_id: str) -> SkillRiskDecision | None:
        return self._decisions.get(skill_id)

    def get_active_override(self, skill_id: str, *, scope: str = "generated_app_assembly") -> SkillRiskDecision | None:
        decision = self._decisions.get(skill_id)
        if decision is None or decision.scope != scope or not decision.is_active():
            return None
        return decision

    def approve_override(
        self,
        skill_id: str,
        reviewer: str,
        reason: str = "",
        *,
        scope: str = "generated_app_assembly",
        expires_at: datetime | None = None,
    ) -> SkillRiskDecision:
        decision = SkillRiskDecision(
            skill_id=skill_id,
            decision="approved_override",
            scope=scope,
            reviewer=reviewer,
            reason=reason,
            expires_at=expires_at,
        )
        self._decisions[skill_id] = decision
        self._persist()
        return decision

    def revoke_override(self, skill_id: str, reviewer: str, reason: str = "") -> SkillRiskDecision:
        decision = SkillRiskDecision(
            skill_id=skill_id,
            decision="revoked",
            reviewer=reviewer,
            reason=reason,
        )
        self._decisions[skill_id] = decision
        self._persist()
        return decision

    def _persist(self) -> None:
        if self._store is not None:
            self._store.save_mapping("skill_risk_policy", self._decisions)

    def _load(self) -> None:
        payload = self._store.load_json("skill_risk_policy", {})
        if not isinstance(payload, dict):
            return
        self._decisions = {key: SkillRiskDecision.model_validate(value) for key, value in payload.items()}
