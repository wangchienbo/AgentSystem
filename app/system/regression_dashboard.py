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
