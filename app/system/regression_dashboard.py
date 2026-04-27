"""
Regression Governance Dashboard
Connects chat regression operational data into a governance-oriented dashboard view,
bridging regression trends, evidence, and comparison into a single refinement-ready surface.
"""
from __future__ import annotations

from typing import Any

from app.system.chat_regression import build_multi_run_comparison, build_topic_trends
from app.system.regression_evidence_bridge import list_regression_evidence_history


def build_regression_governance_dashboard(
    *,
    comparison_limit: int = 5,
    trends_limit: int = 5,
    evidence_limit: int = 10,
) -> dict[str, Any]:
    """Build a comprehensive governance dashboard from regression data.

    Combines three perspectives into one operator-friendly view:
    - Cross-topic comparison (aggregate trends)
    - Per-topic trend slices
    - Evidence history
    """
    comparison = build_multi_run_comparison(limit=comparison_limit)
    trends = build_topic_trends(limit=trends_limit)
    evidence = list_regression_evidence_history(limit=evidence_limit)

    # Build risk summary from comparison data
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

    return {
        "comparison": comparison,
        "trends": trends,
        "evidence": evidence,
        "risk_flags": risk_flags,
        "dashboard_id": "regression-governance",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def build_regression_operator_summary(
    *,
    comparison_limit: int = 5,
    trends_limit: int = 5,
    evidence_limit: int = 10,
) -> dict[str, Any]:
    """Build a combined operator summary merging regression governance with
    a placeholder refinement summary structure.

    This produces a unified operator-facing summary that embeds the regression
    governance dashboard alongside refinement metrics, ready for consumption
    by the broader governance layer.
    """
    dashboard = build_regression_governance_dashboard(
        comparison_limit=comparison_limit,
        trends_limit=trends_limit,
        evidence_limit=evidence_limit,
    )
    return {
        "app_instance_id": "agent_system",
        "refinement": {
            "proposal_count": 0,
            "proposed_review_count": 0,
            "approved_review_count": 0,
            "rejected_review_count": 0,
            "applied_review_count": 0,
            "latest_priority": None,
            "primary_contradiction": "",
            "recommended_action": "",
            "context_summary": "Regression-integrated governance summary",
            "governance": {
                "overview": {
                    "app_instance_id": "agent_system",
                    "hypothesis_count": 0,
                    "unresolved_hypothesis_count": 0,
                    "verification_count": 0,
                    "passed_verification_count": 0,
                    "failed_verification_count": 0,
                    "decision_count": 0,
                    "promote_count": 0,
                    "hold_count": 0,
                    "queue_count": 0,
                    "queued_count": 0,
                    "applied_count": 0,
                    "failed_hypothesis_count": 0,
                },
                "stats": {
                    "app_instance_id": "agent_system",
                    "total_hypotheses": 0,
                    "repeated_hypotheses": 0,
                    "total_verifications": 0,
                    "passed_verifications": 0,
                    "failed_verifications": 0,
                    "inconclusive_verifications": 0,
                    "total_queue_items": 0,
                    "queued_items": 0,
                    "approved_items": 0,
                    "applied_items": 0,
                    "rejected_items": 0,
                    "rolled_back_items": 0,
                    "failed_hypotheses": 0,
                },
                "recent_queue": {"items": [], "meta": {"total_count": 0, "returned_count": 0, "filtered_count": 0, "has_more": False}},
                "recent_failed_hypotheses": {"items": [], "meta": {"total_count": 0, "returned_count": 0, "filtered_count": 0, "has_more": False}},
            },
        },
        "regression": dashboard,
        "generated_at": dashboard["generated_at"],
    }


def build_regression_triggers(
    *,
    comparison_limit: int = 5,
    threshold: str = "warning",
) -> dict[str, Any]:
    """Generate actionable refinement triggers from regression risk flags.

    Reads the regression governance dashboard, extracts risk flags at or above
    the given threshold, and converts them into structured trigger records ready
    for ingestion by the refinement pipeline.

    Returns a list of triggers each containing:
      - trigger_id: unique identifier
      - signal: risk signal name
      - level: severity level
      - recommended_action: suggested refinement action
      - detail: human-readable description
      - generated_at: timestamp
    """
    dashboard = build_regression_governance_dashboard(
        comparison_limit=comparison_limit,
    )
    risk_flags = dashboard.get("risk_flags", [])
    # Filter by severity
    level_priority = {"info": 0, "warning": 1}
    min_priority = level_priority.get(threshold, 0)
    actionable = [flag for flag in risk_flags if level_priority.get(flag.get("level", ""), 0) >= min_priority]

    from uuid import uuid4
    from datetime import timezone as _tz
    ts = __import__("datetime").datetime.now(_tz.utc).isoformat()

    triggers = []
    for flag in actionable:
        triggers.append({
            "trigger_id": f"regression-trigger-{uuid4().hex[:12]}",
            "signal": flag.get("signal", ""),
            "level": flag.get("level", ""),
            "recommended_action": _recommend_action_for_signal(flag.get("signal", "")),
            "detail": flag.get("detail", ""),
            "generated_at": ts,
        })

    return {
        "triggers": triggers,
        "trigger_count": len(triggers),
        "dashboard_comparison": dashboard["comparison"],
        "generated_at": ts,
    }


def _recommend_action_for_signal(signal: str) -> str:
    """Map regression risk signals to recommended refinement actions."""
    actions = {
        "elevated_latency": "profile_performance_bottlenecks",
        "elevated_fallback": "review_tool_calling_prompt_template",
        "elevated_overreach": "tighten_evidence_boundary_guard",
        "conservative_mode_skew": "audit_verification_policy_thresholds",
    }
    return actions.get(signal, "manual_review_required")
