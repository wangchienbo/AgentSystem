from __future__ import annotations

from typing import Any

from app.models.governance_observation import (
    EvidenceEnvelope,
    GovernanceEvidenceDigest,
    ObservationRecord,
)


REPLAY_SAMPLE_LIMIT = 3


def classify_failure_stage(probe: dict[str, Any]) -> str | None:
    explicit = probe.get("failure_stage")
    if explicit:
        return str(explicit)

    answer_mode = str(probe.get("answer_mode") or "")
    verification_mode = str(probe.get("verification_mode") or "")
    response = str(probe.get("response") or "")
    fallback_like = bool(probe.get("fallback_like"))
    overreach_risk = bool(probe.get("overreach_risk"))
    tool_error = bool(probe.get("tool_error"))
    routing_error = bool(probe.get("routing_error"))

    if answer_mode == "clarification_required":
        return "requirement_understanding"
    if routing_error:
        return "routing"
    if verification_mode in {"tool_required", "evidence_required", "required"}:
        return "evidence"
    if tool_error or fallback_like:
        return "execution"
    if overreach_risk or "不能直接下结论" in response:
        return "answer_shaping"
    return None


def classify_signal(probe: dict[str, Any], failure_stage: str | None) -> str:
    if failure_stage == "requirement_understanding":
        return "requirement_misunderstanding"
    if failure_stage == "routing":
        return "routing_error"
    if failure_stage == "evidence":
        return "missing_evidence"
    if failure_stage == "execution":
        return "bad_tool_execution"
    if failure_stage == "answer_shaping":
        return "weak_final_answer_shaping"
    return "healthy_observation"


def _normalize_source(probe: dict[str, Any]) -> str:
    return str(probe.get("source") or "chat_regression_probe")


def _normalize_scope(source: str) -> str:
    if source == "conversation_history_replay":
        return "replay_regression"
    return "fixed_regression"


def build_observation_record(run_id: str, probe: dict[str, Any]) -> ObservationRecord:
    topic = str(probe.get("topic") or "unknown")
    response = str(probe.get("response") or "")
    answer_mode = str(probe.get("answer_mode") or "unknown")
    verification_mode = str(probe.get("verification_mode") or "unknown")
    latency_ms = int(probe.get("latency_ms") or 0)
    prompt_summary = str(probe.get("prompt") or probe.get("request") or f"probe topic={topic}")
    output_summary = response[:240] if response else f"answer_mode={answer_mode}"
    source = _normalize_source(probe)
    scope = _normalize_scope(source)
    failure_stage = classify_failure_stage(probe)
    signal = classify_signal(probe, failure_stage)

    evidence: list[EvidenceEnvelope] = [
        EvidenceEnvelope(
            kind="input",
            summary=prompt_summary,
            source=source if source == "conversation_history_replay" else "fixed_prompt_matrix",
            grade="direct",
            confidence=0.9,
            metadata={"topic": topic, "session_id": probe.get("session_id"), "history_index": probe.get("history_index")},
        )
    ]

    if probe.get("route_selected") or probe.get("routing_error"):
        evidence.append(
            EvidenceEnvelope(
                kind="routing",
                summary=str(probe.get("route_selected") or "routing anomaly detected"),
                source=source,
                grade="derived",
                confidence=0.7,
                metadata={"routing_error": bool(probe.get("routing_error")), "topic": topic},
            )
        )

    if probe.get("tool_name") or probe.get("tool_error"):
        evidence.append(
            EvidenceEnvelope(
                kind="tool_selection",
                summary=str(probe.get("tool_name") or "tool path unresolved"),
                source=source,
                grade="derived",
                confidence=0.7,
                metadata={"tool_error": bool(probe.get("tool_error")), "tool_result": probe.get("tool_result")},
            )
        )

    evidence.extend([
        EvidenceEnvelope(
            kind="output",
            summary=output_summary,
            source=source,
            grade="excerpt",
            confidence=0.8,
            metadata={
                "answer_mode": answer_mode,
                "verification_mode": verification_mode,
            },
        ),
        EvidenceEnvelope(
            kind="execution",
            summary=f"latency_ms={latency_ms}",
            source=source,
            grade="derived",
            confidence=0.8,
            metadata={
                "latency_ms": latency_ms,
                "fallback_like": bool(probe.get("fallback_like")),
                "overreach_risk": bool(probe.get("overreach_risk")),
                "tool_error": bool(probe.get("tool_error")),
            },
        ),
    ])

    if probe.get("user_feedback"):
        evidence.append(
            EvidenceEnvelope(
                kind="user_feedback",
                summary=str(probe.get("user_feedback"))[:240],
                source=source,
                grade="direct",
                confidence=0.9,
            )
        )

    derived_success = bool(probe.get("success")) and failure_stage is None

    return ObservationRecord(
        observation_id=str(probe.get("observation_id") or f"{run_id}:{topic}:{probe.get('session_id') or 'none'}"),
        topic=topic,
        run_id=run_id,
        session_id=probe.get("session_id"),
        source=source,
        scope=scope,
        domain="regression_quality",
        subdomain=str(probe.get("subdomain") or failure_stage or "healthy"),
        signal=signal,
        success=derived_success,
        failure_stage=failure_stage,
        evidence=evidence,
        tags=[topic, scope, signal],
        metadata={"answer_mode": answer_mode, "verification_mode": verification_mode},
    )


def build_governance_evidence_digest(run_detail: dict[str, Any] | None) -> GovernanceEvidenceDigest:
    if not run_detail:
        return GovernanceEvidenceDigest()

    run_id = str((run_detail.get("summary") or {}).get("run_id") or "unknown-run")
    topic_failure_stage_counts: dict[str, dict[str, int]] = {}
    failure_stage_counts: dict[str, int] = {}
    evidence_kind_counts: dict[str, int] = {}
    observations: list[ObservationRecord] = []

    for probe in run_detail.get("probes", []):
        observation = build_observation_record(run_id, probe)
        observations.append(observation)
        for item in observation.evidence:
            evidence_kind_counts[item.kind] = evidence_kind_counts.get(item.kind, 0) + 1
        if observation.failure_stage is None:
            continue
        failure_stage_counts[observation.failure_stage] = failure_stage_counts.get(observation.failure_stage, 0) + 1
        topic_bucket = topic_failure_stage_counts.setdefault(observation.topic, {})
        topic_bucket[observation.failure_stage] = topic_bucket.get(observation.failure_stage, 0) + 1

    dominant_failure_stage = max(failure_stage_counts.items(), key=lambda item: item[1])[0] if failure_stage_counts else None
    dominant_evidence_kind = max(evidence_kind_counts.items(), key=lambda item: item[1])[0] if evidence_kind_counts else None

    return GovernanceEvidenceDigest(
        total_observations=len(observations),
        dominant_failure_stage=dominant_failure_stage,
        dominant_evidence_kind=dominant_evidence_kind,
        failure_stage_counts=failure_stage_counts,
        evidence_kind_counts=evidence_kind_counts,
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
