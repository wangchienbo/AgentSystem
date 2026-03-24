from __future__ import annotations

from datetime import datetime

from app.models.operator_contracts import OperatorPageMeta
from app.models.skill_risk_policy import SkillRiskDashboard, SkillRiskDecision, SkillRiskEventPage, SkillRiskGovernanceEvent, SkillRiskStatsSummary
from app.services.runtime_state_store import RuntimeStateStore


class SkillRiskPolicyService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store
        self._decisions: dict[str, SkillRiskDecision] = {}
        self._events: list[SkillRiskGovernanceEvent] = []
        if self._store is not None:
            self._load()

    def list_decisions(self) -> list[SkillRiskDecision]:
        return sorted(self._decisions.values(), key=lambda item: item.created_at, reverse=True)

    def get_decision(self, skill_id: str) -> SkillRiskDecision | None:
        return self._decisions.get(skill_id)

    def list_events(self, skill_id: str | None = None) -> list[SkillRiskGovernanceEvent]:
        events = self._events if skill_id is None else [item for item in self._events if item.skill_id == skill_id]
        return sorted(events, key=lambda item: item.created_at, reverse=True)

    def get_event_page(self, skill_id: str | None = None, limit: int | None = None) -> SkillRiskEventPage:
        events = self.list_events(skill_id=skill_id)
        filtered_count = len(events)
        has_more = limit is not None and filtered_count > limit
        if limit is not None:
            events = events[:limit]
        return SkillRiskEventPage(
            items=events,
            meta=OperatorPageMeta(
                returned_count=len(events),
                total_count=len(self._events),
                filtered_count=filtered_count,
                has_more=has_more,
            ),
        )

    def get_stats_summary(self) -> SkillRiskStatsSummary:
        decisions = list(self._decisions.values())
        events = list(self._events)
        return SkillRiskStatsSummary(
            total_decisions=len(decisions),
            active_overrides=sum(1 for item in decisions if item.is_active()),
            revoked_overrides=sum(1 for item in decisions if item.decision == "revoked"),
            total_events=len(events),
            blocked_events=sum(1 for item in events if item.event_type == "policy_blocked"),
            approved_events=sum(1 for item in events if item.event_type == "override_approved"),
            revoked_events=sum(1 for item in events if item.event_type == "override_revoked"),
            latest_decision_at=max((item.created_at for item in decisions), default=None),
            latest_event_at=max((item.created_at for item in events), default=None),
        )

    def get_dashboard(self, recent_limit: int = 5) -> SkillRiskDashboard:
        return SkillRiskDashboard(
            overview={
                "active_policy": "default_deny_with_override",
                "decision_store": "skill_risk_policy",
                "event_store": "skill_risk_policy_events",
            },
            stats=self.get_stats_summary(),
            recent_events=self.get_event_page(limit=recent_limit),
        )

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
        self.record_event(
            skill_id=skill_id,
            event_type="override_approved",
            actor=reviewer,
            reason=reason,
            details={"decision": decision.decision, "expires_at": decision.expires_at},
        )
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
        self.record_event(
            skill_id=skill_id,
            event_type="override_revoked",
            actor=reviewer,
            reason=reason,
            details={"decision": decision.decision},
        )
        self._persist()
        return decision

    def record_event(
        self,
        *,
        skill_id: str,
        event_type: str,
        actor: str = "system",
        reason: str = "",
        scope: str = "generated_app_assembly",
        details: dict | None = None,
    ) -> SkillRiskGovernanceEvent:
        event = SkillRiskGovernanceEvent(
            skill_id=skill_id,
            event_type=event_type,
            actor=actor,
            reason=reason,
            scope=scope,
            details=details or {},
        )
        self._events.append(event)
        self._persist()
        return event

    def _persist(self) -> None:
        if self._store is not None:
            self._store.save_mapping("skill_risk_policy", self._decisions)
            self._store.save_collection("skill_risk_policy_events", self._events)

    def _load(self) -> None:
        payload = self._store.load_json("skill_risk_policy", {})
        if isinstance(payload, dict):
            self._decisions = {key: SkillRiskDecision.model_validate(value) for key, value in payload.items()}
        event_payload = self._store.load_json("skill_risk_policy_events", [])
        if isinstance(event_payload, list):
            self._events = [SkillRiskGovernanceEvent.model_validate(item) for item in event_payload]
