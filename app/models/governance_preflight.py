from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


def _format_governance_preflight_badge_payload(payload: dict[str, Any]) -> str:
    status = "AUTO" if payload.get("can_apply") else "HOLD"
    label = str(payload.get("decision_label") or "Unknown preflight decision")
    return f"{status} | {label}"


def _format_governance_preflight_operator_note_payload(payload: dict[str, Any]) -> str:
    parts = [
        _format_governance_preflight_badge_payload(payload),
        f"code={payload.get('decision_code') or 'unknown'}",
        f"stage={payload.get('matched_stage') or 'unknown'}",
        f"scope={payload.get('review_scope') or 'unknown'}",
        f"risk={payload.get('apply_risk') or 'unknown'}",
    ]
    hold_reason = payload.get("hold_reason")
    if hold_reason:
        parts.append(f"hold={hold_reason}")
    queue_id = payload.get("recommended_queue_id")
    if queue_id:
        parts.append(f"queue={queue_id}")
    return " | ".join(parts)


class GovernancePreflightContext(BaseModel):
    recommended_queue_id: str | None = None
    priority_tier: str | None = None
    automation_health: str = "healthy"
    automation_attention_reason: str = ""
    last_tick_outcome: str = "unknown"
    consecutive_failures: int = 0
    retry_pending: bool = False
    priority_lane: str | None = None
    rollout_available: bool = True
    queue_status: str | None = None


class GovernancePreflightDecision(BaseModel):
    recommended_queue_id: str | None = None
    priority_tier: str | None = None
    automation_health: str = "healthy"
    automation_attention_reason: str = ""
    last_tick_outcome: str = "unknown"
    consecutive_failures: int = 0
    queue_status: str | None = None
    priority_lane: str | None = None
    matched_stage: str = "unknown"
    decision_code: str = "unknown"
    decision_label: str = "Unknown preflight decision"
    decision_summary: str = "Unknown preflight decision"
    can_apply: bool
    apply_risk: str
    hold_reason: str = ""
    hold_category: str = "none"
    required_review_scope: str
    review_scope: str
    review_reason: str

    def to_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["render_badge"] = _format_governance_preflight_badge_payload(payload)
        payload["render_operator_note"] = _format_governance_preflight_operator_note_payload(payload)
        return payload
