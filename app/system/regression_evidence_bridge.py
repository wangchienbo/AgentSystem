from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.governance.log_evidence_service import LogEvidenceService
from app.models.log_evidence import PromotedEvidence, SuspiciousSignal

from pathlib import Path as _Path

from app.system.chat_regression import REGRESSION_LOG_DIR, build_multi_run_comparison


REGRESSION_EVIDENCE_LOG_DIR = REGRESSION_LOG_DIR

def build_regression_evidence_from_comparison(
    comparison: dict[str, Any],
    *,
    app_instance_id: str = "chat_regression",
) -> list[PromotedEvidence]:
    """Generate promoted evidence records from a multi-run regression comparison.

    This bridges the regression subsystem's operational outputs into the
    evidence ledger so the system can self-monitor and detect regressions
    that warrant refinement.
    """
    evidence_list: list[PromotedEvidence] = []

    if not comparison or comparison.get("run_count", 0) < 2:
        return evidence_list

    avg_latency_ms = comparison.get("avg_latency_ms", 0)
    avg_fallback = comparison.get("avg_fallback_count", 0)
    avg_overreach = comparison.get("avg_overreach_risk_count", 0)

    service = LogEvidenceService()

    def _make_signal(
        scope_suffix: str,
        category: str,
        reason: str,
        severity: str = "medium",
        **kwargs: Any,
    ) -> SuspiciousSignal:
        scope_key = f"chat_regression:{scope_suffix}"
        return SuspiciousSignal(
            signal_id=f"regression-signal-{uuid4().hex[:12]}",
            category=category,
            severity=severity,
            scope_key=scope_key,
            app_instance_id=app_instance_id,
            reason=reason,
            frequency=1,
            metadata=kwargs,
        )

    # Rule 1: High latency regression signal
    if avg_latency_ms > 5000:
        signal = _make_signal(
            scope_suffix="latency",
            category="workflow_failure",
            reason=f"Average chat response latency ({avg_latency_ms:.0f}ms) is elevated across {comparison['run_count']} recent runs",
            severity="high" if avg_latency_ms > 10000 else "medium",
        )
        evidence_list.append(service._promote_signal(signal, recommended_action="inspect_latency_trend"))

    # Rule 2: Elevated fallback rate signal
    if avg_fallback > 1.0:
        signal = _make_signal(
            scope_suffix="fallback",
            category="policy_pressure",
            reason=f"Average fallback count ({avg_fallback:.1f}) suggests the system is frequently answering with uncertainty markers",
            severity="high" if avg_fallback > 2.0 else "medium",
            avg_fallback=avg_fallback,
        )
        evidence_list.append(service._promote_signal(signal, recommended_action="audit_fallback_patterns"))

    # Rule 3: Overreach risk signal
    if avg_overreach > 0.5:
        signal = _make_signal(
            scope_suffix="overreach",
            category="clarify_unresolved",
            reason=f"Average overreach-risk count ({avg_overreach:.1f}) suggests the system may be answering beyond its evidence boundaries",
            severity="high" if avg_overreach > 2.0 else "medium",
            avg_overreach=avg_overreach,
        )
        evidence_list.append(service._promote_signal(signal, recommended_action="tighten_boundary_guard"))

    # Rule 4: Answer mode distribution skew
    answer_mode_totals = comparison.get("answer_mode_totals", {})
    verification_required_count = answer_mode_totals.get("verification_required", 0)
    clarification_required_count = answer_mode_totals.get("clarification_required", 0)
    direct_count = answer_mode_totals.get("direct", 0)

    conservative_count = verification_required_count + clarification_required_count
    total_mode_count = sum(answer_mode_totals.values())
    if total_mode_count > 0 and conservative_count / total_mode_count > 0.5:
        signal = _make_signal(
            scope_suffix="conservative_mode",
            category="policy_pressure",
            reason=f"Conservative answer modes dominate: {conservative_count}/{total_mode_count} prompts suggest system is overly cautious",
            severity="high" if conservative_count / total_mode_count > 0.75 else "medium",
            answer_mode_totals=answer_mode_totals,
        )
        evidence_list.append(service._promote_signal(signal, recommended_action="review_prompt_guard_or_tool_policy"))

    # Rule 5: Very high direct rate with high overreach is a conflict
    if direct_count > 0 and avg_overreach > 1.0:
        signal = _make_signal(
            scope_suffix="conflicting_signal",
            category="policy_pressure",
            reason=f"High direct answer count ({direct_count}) with elevated overreach ({avg_overreach:.1f})",
            severity="high",
            direct_count=direct_count,
            avg_overreach=avg_overreach,
        )
        evidence_list.append(service._promote_signal(signal, recommended_action="strengthen_verification_for_direct_answers"))

    return evidence_list


def promote_regression_evidence(
    *,
    app_instance_id: str = "chat_regression",
    comparison: dict[str, Any] | None = None,
    limit: int = 5,
    log_dir: _Path | None = None,
) -> dict[str, Any]:
    """Convenience: compute comparison, promote evidence, persist to file, and return summary."""
    if comparison is None:
        comparison = build_multi_run_comparison(limit=limit)
    evidence_list = build_regression_evidence_from_comparison(
        comparison,
        app_instance_id=app_instance_id,
    )
    result = {
        "comparison": comparison,
        "promoted_evidence": [e.model_dump(mode="json") for e in evidence_list],
        "promoted_count": len(evidence_list),
    }
    # Persist to evidence log
    target_dir = log_dir or REGRESSION_EVIDENCE_LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    import json
    ev_path = target_dir / "evidence.jsonl"
    with ev_path.open("a", encoding="utf-8") as f:
        for e in result["promoted_evidence"]:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return result


def list_regression_evidence_history(
    *,
    log_dir: _Path | None = None,
    limit: int = 20,
    topic: str | None = None,
) -> list[dict[str, Any]]:
    """Read previously generated regression evidence from the persistence file.
    
    Optionally filter by topic name (api, validation, telemetry, storage).
    """
    target_dir = log_dir or REGRESSION_EVIDENCE_LOG_DIR
    ev_path = target_dir / "evidence.jsonl"
    if not ev_path.exists():
        return []
    lines = ev_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    parsed = [json.loads(line) for line in lines]
    idx = {"api": 0, "validation": 1, "telemetry": 2, "storage": 3}
    if topic is not None and topic in idx:
        needIdx = idx[topic]
        parsed = [e for e in parsed if (e.get("summary","")[needIdx:needIdx+len(topic)] == topic if len(e.get("summary","")) > needIdx else False)]
    # Return most recent first
    return list(reversed(parsed))[:limit]
