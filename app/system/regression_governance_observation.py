from __future__ import annotations

from typing import Any

from app.models.governance_observation import (
    EvidenceEnvelope,
    GovernanceEvidenceDigest,
    ObservationRecord,
)


REPLAY_SAMPLE_LIMIT = 3


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
    source = str(probe.get("source") or "chat_regression_probe")

    evidence = [
        EvidenceEnvelope(
            kind="input",
            summary=prompt_summary,
            source=source if source == "conversation_history_replay" else "fixed_prompt_matrix",
            metadata={"topic": topic, "session_id": probe.get("session_id"), "history_index": probe.get("history_index")},
        ),
        EvidenceEnvelope(
            kind="output",
            summary=output_summary,
            source=source,
            metadata={
                "answer_mode": answer_mode,
                "verification_mode": verification_mode,
            },
        ),
        EvidenceEnvelope(
            kind="execution",
            summary=f"latency_ms={latency_ms}",
            source=source,
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


def build_replay_probe_from_history_entry(session_id: str, index: int, entry: dict[str, Any]) -> dict[str, Any]:
    role = str(entry.get("role") or "unknown")
    content = str(entry.get("content") or "")
    topic = "validation" if any(token in content for token in ("验证", "check", "确认")) else "replay"

    answer_mode = "direct"
    verification_mode = "none"
    fallback_like = False
    overreach_risk = False

    if role == "assistant":
        if any(token in content for token in ("需要进一步验证", "不能直接下结论", "建议做轻量验证")):
            answer_mode = "verification_required"
            verification_mode = "evidence_required"
            fallback_like = True
            overreach_risk = True
        elif "请先澄清" in content:
            answer_mode = "clarification_required"
    elif role == "user":
        if "为什么" in content or "怎么" in content:
            topic = "api"

    return {
        "topic": topic,
        "prompt": content[:240] or f"history-entry-{index}",
        "success": True,
        "latency_ms": 0,
        "response": content[:240],
        "answer_mode": answer_mode,
        "verification_mode": verification_mode,
        "fallback_like": fallback_like,
        "overreach_risk": overreach_risk,
        "source": "conversation_history_replay",
        "session_id": session_id,
        "history_index": index,
    }


def build_replay_observation_digest(session_id: str, history: list[dict[str, Any]], *, limit: int = REPLAY_SAMPLE_LIMIT) -> GovernanceEvidenceDigest:
    if not history:
        return GovernanceEvidenceDigest()

    trimmed = history[-limit:]
    run_detail = {
        "summary": {"run_id": f"replay-{session_id}"},
        "probes": [
            build_replay_probe_from_history_entry(session_id, idx, entry)
            for idx, entry in enumerate(trimmed)
        ],
    }
    return build_governance_evidence_digest(run_detail)
