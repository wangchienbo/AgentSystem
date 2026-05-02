from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GovernanceFailureAttribution:
    failure_stage: str | None
    signal: str
    reason: str


def classify_governance_failure(probe: dict[str, Any]) -> GovernanceFailureAttribution:
    explicit_failure_stage = probe.get("failure_stage")
    if explicit_failure_stage:
        stage = str(explicit_failure_stage)
        return GovernanceFailureAttribution(
            failure_stage=stage,
            signal=_signal_for_stage(stage),
            reason="explicit failure_stage provided by upstream probe",
        )

    answer_mode = str(probe.get("answer_mode") or "")
    verification_mode = str(probe.get("verification_mode") or "")
    response = str(probe.get("response") or "")
    fallback_like = bool(probe.get("fallback_like"))
    overreach_risk = bool(probe.get("overreach_risk"))
    tool_error = bool(probe.get("tool_error"))
    routing_error = bool(probe.get("routing_error"))

    if answer_mode == "clarification_required":
        return GovernanceFailureAttribution(
            failure_stage="requirement_understanding",
            signal="requirement_misunderstanding",
            reason="assistant explicitly asked for clarification",
        )
    if routing_error:
        return GovernanceFailureAttribution(
            failure_stage="routing",
            signal="routing_error",
            reason="routing_error marker present on probe",
        )
    if verification_mode in {"tool_required", "evidence_required", "required"}:
        return GovernanceFailureAttribution(
            failure_stage="evidence",
            signal="missing_evidence",
            reason="verification mode requires additional evidence or tools",
        )
    if tool_error or fallback_like:
        return GovernanceFailureAttribution(
            failure_stage="execution",
            signal="bad_tool_execution",
            reason="tool failure or fallback-like behavior detected",
        )
    if overreach_risk or "不能直接下结论" in response:
        return GovernanceFailureAttribution(
            failure_stage="answer_shaping",
            signal="weak_final_answer_shaping",
            reason="answer shaping risk markers present in response",
        )
    return GovernanceFailureAttribution(
        failure_stage=None,
        signal="healthy_observation",
        reason="no failure attribution markers detected",
    )


def _signal_for_stage(stage: str) -> str:
    mapping = {
        "requirement_understanding": "requirement_misunderstanding",
        "routing": "routing_error",
        "evidence": "missing_evidence",
        "execution": "bad_tool_execution",
        "answer_shaping": "weak_final_answer_shaping",
    }
    return mapping.get(stage, "healthy_observation")
