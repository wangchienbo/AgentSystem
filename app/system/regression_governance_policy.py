from __future__ import annotations

from typing import Any

PREFLIGHT_HOLD_NONE = ""
PREFLIGHT_HOLD_ROLLOUT_SERVICE_UNAVAILABLE = "rollout_service_unavailable"
PREFLIGHT_HOLD_NO_RECOMMENDED_QUEUE = "no_recommended_queue"
PREFLIGHT_HOLD_RECOMMENDED_QUEUE_MISSING = "recommended_queue_missing"
PREFLIGHT_HOLD_AUTOMATION_DEGRADED_REQUIRES_REVIEW = "automation_degraded_requires_review"
PREFLIGHT_HOLD_AUTOMATION_RETRY_PENDING_REQUIRES_REVIEW = "automation_retry_pending_requires_review"
PREFLIGHT_HOLD_SECONDARY_REQUIRES_REVIEW = "secondary_requires_review"

PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK = "light_auto_apply_ok"
PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED = "operator_review_required"
PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_QUEUE_STATE = "operator_review_required_due_to_queue_state"
PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION = "operator_review_required_due_to_automation"

PREFLIGHT_REVIEW_REASON_PRIMARY_SELECTION_HEALTHY = "primary_selection_healthy"
PREFLIGHT_REVIEW_REASON_SERVICE_UNAVAILABLE = "service_unavailable"
PREFLIGHT_REVIEW_REASON_SELECTION_MISSING = "selection_missing"
PREFLIGHT_REVIEW_REASON_QUEUE_MISSING = "queue_missing"
PREFLIGHT_REVIEW_REASON_QUEUE_STATE_BLOCKED = "queue_state_blocked"
PREFLIGHT_REVIEW_REASON_AUTOMATION_DEGRADED = "automation_degraded"
PREFLIGHT_REVIEW_REASON_AUTOMATION_RETRY_PENDING = "automation_retry_pending"
PREFLIGHT_REVIEW_REASON_PRIORITY_SECONDARY = "priority_secondary"
PREFLIGHT_REVIEW_REASON_PRIORITY_TIER_BLOCKED = "priority_tier_blocked"


def build_governance_preflight_decision(
    *,
    base: dict[str, Any],
    can_apply: bool,
    apply_risk: str,
    hold_reason: str,
    review_scope: str,
    review_reason: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        **base,
        **extra,
        "can_apply": can_apply,
        "apply_risk": apply_risk,
        "hold_reason": hold_reason,
        "hold_category": hold_reason.split(":", 1)[0] if hold_reason else "none",
        "required_review_scope": review_scope,
        "review_scope": review_scope,
        "review_reason": review_reason,
    }

_SIGNAL_PRIORITY = {
    "nightly_automation_degraded": 40,
    "elevated_overreach": 35,
    "elevated_fallback": 30,
    "elevated_latency": 25,
    "conservative_mode_skew": 20,
    "nightly_automation_warning": 10,
}


def signal_priority(flag: dict[str, str]) -> tuple[int, int]:
    return (
        {"info": 0, "warning": 1}.get(flag.get("level", ""), 0),
        _SIGNAL_PRIORITY.get(flag.get("signal", ""), 0),
    )


def classify_signal_domain(signal: str) -> str:
    if signal.startswith("nightly_automation_"):
        return "automation_control_plane"
    return "regression_quality"


def classify_signal_family(signal: str) -> str:
    families = {
        "nightly_automation_degraded": "automation_recovery",
        "nightly_automation_warning": "automation_recovery",
        "elevated_latency": "execution_semantics",
        "elevated_fallback": "execution_semantics",
        "elevated_overreach": "answer_shaping",
        "conservative_mode_skew": "requirement_understanding",
    }
    return families.get(signal, "unclassified")


def classify_signal_subdomain_candidate(signal: str) -> str:
    candidates = {
        "nightly_automation_degraded": "degraded_guard",
        "nightly_automation_warning": "recovery_path",
        "elevated_latency": "latency_path",
        "elevated_fallback": "fallback_path",
        "elevated_overreach": "overreach_boundary",
        "conservative_mode_skew": "clarification_threshold",
    }
    return candidates.get(signal, "unclassified")


def build_automation_attention(automation: dict[str, Any]) -> dict[str, str] | None:
    if automation.get("automation_health") not in {"warning", "degraded"}:
        return None
    return {
        "health": automation.get("automation_health"),
        "reason": automation.get("attention_reason") or automation.get("last_tick_decision") or "",
        "last_tick_outcome": automation.get("last_tick_outcome") or "",
    }


def build_automation_risk_flags(automation_attention: dict[str, str] | None) -> list[dict[str, str]]:
    if automation_attention is None:
        return []
    health = automation_attention.get("health") or "warning"
    reason = automation_attention.get("reason") or "automation_attention"
    outcome = automation_attention.get("last_tick_outcome") or "unknown"
    signal = "nightly_automation_degraded" if health == "degraded" else "nightly_automation_warning"
    detail = f"Nightly automation health {health}; reason={reason}; outcome={outcome}"
    return [{"level": "warning" if health == "degraded" else "info", "signal": signal, "detail": detail}]


def build_comparison_risk_flags(comparison: dict[str, Any]) -> list[dict[str, str]]:
    risk_flags: list[dict[str, str]] = []
    if comparison.get("avg_latency_ms", 0) > 5000:
        risk_flags.append({"level": "warning", "signal": "elevated_latency", "detail": f"Average latency {comparison['avg_latency_ms']:.0f}ms across {comparison['run_count']} runs"})
    if comparison.get("avg_fallback_count", 0) > 1.0:
        risk_flags.append({"level": "warning", "signal": "elevated_fallback", "detail": f"Average fallback count {comparison['avg_fallback_count']:.1f} across {comparison['run_count']} runs"})
    if comparison.get("avg_overreach_risk_count", 0) > 0.5:
        risk_flags.append({"level": "warning", "signal": "elevated_overreach", "detail": f"Average overreach count {comparison['avg_overreach_risk_count']:.1f} across {comparison['run_count']} runs"})

    answer_totals = comparison.get("answer_mode_totals", {})
    conservative = answer_totals.get("verification_required", 0) + answer_totals.get("clarification_required", 0)
    total = sum(answer_totals.values())
    if total > 0 and conservative / total > 0.5:
        risk_flags.append({"level": "warning" if conservative / total > 0.75 else "info", "signal": "conservative_mode_skew", "detail": f"Conservative modes {conservative}/{total} ({conservative / total:.1%})"})
    return risk_flags


def recommend_action_for_signal(signal: str) -> str:
    actions = {
        "elevated_latency": "profile_performance_bottlenecks",
        "elevated_fallback": "review_tool_calling_prompt_template",
        "elevated_overreach": "tighten_evidence_boundary_guard",
        "conservative_mode_skew": "audit_verification_policy_thresholds",
        "nightly_automation_warning": "inspect_nightly_automation_recovery_path",
        "nightly_automation_degraded": "stabilize_nightly_automation_control_plane",
    }
    return actions.get(signal, "manual_review_required")
