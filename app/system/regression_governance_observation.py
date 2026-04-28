from __future__ import annotations

from typing import Any

from app.models.governance_observation import (
    EvidenceEnvelope,
    GovernanceEvidenceDigest,
    ObservationRecord,
)


def classify_failure_stage(probe: dict[str, Any]) -> str | None:
    answer_mode = str(probe.get("answer_mode") or "")
    verification_mode = str(probe.get("verification_mode") or "")
    response = str(probe.get("response") or "")
    fallback_like = bool(probe.get("fallback_like"))
    overreach_risk = bool(probe.get("overreach_risk"))

    if answer_mode == "clarification_required":
        return "requirement_understanding"
    if verification_mode in {"tool_required", "evidence_required"}:
        return "evidence"
    if fallback_like:
        return "execution"
    if overreach_risk or "不能直接下结论" in response:
        return "answer_shaping"
    return None


def build_observation_record(run_id: str, probe: dict[str, Any]) -> ObservationRecord:
    topic = str(probe.get("topic") or "unknown")
    response = str(probe.get("response") or "")
    answer_mode = str(probe.get("answer_mode") or "unknown")
    verification_mode = str(probe.get("verification_mode") or "unknown")
    latency_ms = int(probe.get("latency_ms") or 0)
    prompt_summary = str(probe.get("prompt") or f"probe topic={topic}")
    output_summary = response[:240] if response else f"answer_mode={answer_mode}"

    evidence = [
        EvidenceEnvelope(
            kind="input",
            summary=prompt_summary,
            source="fixed_prompt_matrix",
            metadata={"topic": topic},
        ),
        EvidenceEnvelope(
            kind="output",
            summary=output_summary,
            source="chat_regression_probe",
            metadata={
                "answer_mode": answer_mode,
                "verification_mode": verification_mode,
            },
        ),
        EvidenceEnvelope(
            kind="execution",
            summary=f"latency_ms={latency_ms}",
            source="chat_regression_probe",
            metadata={
                "latency_ms": latency_ms,
                "fallback_like": bool(probe.get("fallback_like")),
                "overreach_risk": bool(probe.get("overreach_risk")),
            },
        ),
    ]

    return ObservationRecord(
        topic=topic,
        run_id=run_id,
        success=bool(probe.get("success")),
        failure_stage=classify_failure_stage(probe),
        evidence=evidence,
    )


def build_governance_evidence_digest(run_detail: dict[str, Any] | None) -> GovernanceEvidenceDigest:
    if not run_detail:
        return GovernanceEvidenceDigest()

    run_id = str((run_detail.get("summary") or {}).get("run_id") or "unknown-run")
    topic_failure_stage_counts: dict[str, dict[str, int]] = {}
    failure_stage_counts: dict[str, int] = {}
    observations: list[ObservationRecord] = []

    for probe in run_detail.get("probes", []):
        observation = build_observation_record(run_id, probe)
        observations.append(observation)
        if observation.failure_stage is None:
            continue
        failure_stage_counts[observation.failure_stage] = failure_stage_counts.get(observation.failure_stage, 0) + 1
        topic_bucket = topic_failure_stage_counts.setdefault(observation.topic, {})
        topic_bucket[observation.failure_stage] = topic_bucket.get(observation.failure_stage, 0) + 1

    return GovernanceEvidenceDigest(
        total_observations=len(observations),
        failure_stage_counts=failure_stage_counts,
        topic_failure_stage_counts=topic_failure_stage_counts,
        observation_samples=observations,
    )
