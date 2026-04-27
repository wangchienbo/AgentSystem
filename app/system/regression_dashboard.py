"""
Regression Governance Dashboard
Connects chat regression operational data into a governance-oriented dashboard view,
bridging regression trends, evidence, and comparison into a single refinement-ready surface.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.models.refinement_loop import RefinementFilter, RefinementHypothesis, RolloutQueueItem, VerificationResult
from app.services.refinement_memory import RefinementMemoryStore
from app.system.chat_regression import build_multi_run_comparison, build_topic_trends
from app.system.regression_evidence_bridge import list_regression_evidence_history

APP_INSTANCE_ID = "agent_system"


def build_regression_governance_dashboard(
    *,
    comparison_limit: int = 5,
    trends_limit: int = 5,
    evidence_limit: int = 10,
    memory: RefinementMemoryStore | None = None,
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

    rollout_summary = None
    if memory is not None:
        overview = memory.build_overview(APP_INSTANCE_ID)
        rollout_summary = {
            "queue_count": overview.queue_count,
            "queued_count": overview.queued_count,
            "applied_count": overview.applied_count,
            "failed_hypothesis_count": overview.failed_hypothesis_count,
            "latest_queue_item": None if overview.latest_queue_item is None else overview.latest_queue_item.model_dump(mode="json"),
        }

    return {
        "comparison": comparison,
        "trends": trends,
        "evidence": evidence,
        "risk_flags": risk_flags,
        "rollout_summary": rollout_summary,
        "dashboard_id": "regression-governance",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def build_regression_operator_summary(
    *,
    comparison_limit: int = 5,
    trends_limit: int = 5,
    evidence_limit: int = 10,
    memory: RefinementMemoryStore | None = None,
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
        memory=memory,
    )
    triggers = build_regression_triggers(comparison_limit=comparison_limit)
    metrics = _build_refinement_metrics_from_regression(dashboard["comparison"], triggers)
    live_governance = None
    if memory is not None:
        live_governance = memory.get_governance_dashboard(RefinementFilter(app_instance_id=APP_INSTANCE_ID), recent_limit=5)

    risk_flags = dashboard.get("risk_flags", [])
    primary_contradiction = ""
    recommended_action = ""
    if risk_flags:
        worst = max(risk_flags, key=lambda f: {"info": 0, "warning": 1}.get(f.get("level", ""), 0))
        primary_contradiction = f"Regression signal: {worst.get('signal', 'unknown')}"
        recommended_action = _recommend_action_for_signal(worst.get("signal", ""))

    overview = live_governance.overview.model_dump(mode="json") if live_governance is not None else {
                    "app_instance_id": APP_INSTANCE_ID,
                    "hypothesis_count": metrics["total_hypotheses"],
                    "unresolved_hypothesis_count": metrics["failed_hypotheses"],
                    "verification_count": metrics["total_verifications"],
                    "passed_verification_count": metrics["passed_verifications"],
                    "failed_verification_count": metrics["failed_verifications"],
                    "decision_count": 0,
                    "promote_count": 0,
                    "hold_count": 0,
                    "queue_count": metrics["queued_items"],
                    "queued_count": metrics["queued_items"],
                    "applied_count": metrics["applied_items"],
                    "failed_hypothesis_count": metrics["failed_hypotheses"],
                }
    stats = live_governance.stats.model_dump(mode="json") if live_governance is not None else {
                    "app_instance_id": APP_INSTANCE_ID,
                    "total_hypotheses": metrics["total_hypotheses"],
                    "repeated_hypotheses": metrics["repeated_hypotheses"],
                    "total_verifications": metrics["total_verifications"],
                    "passed_verifications": metrics["passed_verifications"],
                    "failed_verifications": metrics["failed_verifications"],
                    "inconclusive_verifications": metrics["inconclusive_verifications"],
                    "total_queue_items": metrics["total_queue_items"],
                    "queued_items": metrics["queued_items"],
                    "approved_items": metrics["approved_items"],
                    "applied_items": metrics["applied_items"],
                    "rejected_items": metrics["rejected_items"],
                    "rolled_back_items": metrics["rolled_back_items"],
                    "failed_hypotheses": metrics["failed_hypotheses"],
                    "latest_hypothesis_at": None,
                    "latest_verification_at": metrics["latest_verification_at"],
                    "latest_queue_item_at": metrics["latest_queue_item_at"],
                    "latest_failed_hypothesis_at": metrics["latest_failed_hypothesis_at"],
                }
    recent_queue = live_governance.recent_queue.model_dump(mode="json") if live_governance is not None else {"items": [], "meta": {"total_count": metrics["queued_items"], "returned_count": 0, "filtered_count": 0, "has_more": False}}
    recent_failed_hypotheses = live_governance.recent_failed_hypotheses.model_dump(mode="json") if live_governance is not None else {"items": [], "meta": {"total_count": metrics["failed_hypotheses"], "returned_count": 0, "filtered_count": 0, "has_more": False}}

    return {
        "app_instance_id": APP_INSTANCE_ID,
        "refinement": {
            "proposal_count": 0,
            "proposed_review_count": 0,
            "approved_review_count": 0,
            "rejected_review_count": 0,
            "applied_review_count": 0,
            "latest_priority": None,
            "primary_contradiction": primary_contradiction,
            "recommended_action": recommended_action,
            "context_summary": "Regression-integrated governance summary",
            "governance": {
                "overview": overview,
                "stats": stats,
                "recent_queue": recent_queue,
                "recent_failed_hypotheses": recent_failed_hypotheses,
            },
        },
        "regression": dashboard,
        "generated_at": dashboard["generated_at"],
    }




def _build_refinement_metrics_from_regression(comparison: dict[str, Any], triggers: dict[str, Any]) -> dict[str, Any]:
    """Derive refinement metrics from regression comparison and trigger data."""
    answer_totals = comparison.get("answer_mode_totals", {})
    verification_totals = comparison.get("verification_mode_totals", {})
    trigger_list = triggers.get("triggers", [])

    # Total verifications = total responses across runs
    total_verifications = comparison.get("run_count", 0) * 4  # 4 topics
    passed_verifications = answer_totals.get("direct", 0) + answer_totals.get("balanced", 0)
    failed_verifications = answer_totals.get("verification_required", 0) + answer_totals.get("clarification_required", 0)
    inconclusive_verifications = 0  # derived from evidence later if needed

    # Hypotheses from trigger signals
    total_hypotheses = len(trigger_list)
    failed_hypotheses = sum(1 for t in trigger_list if t.get("level") == "warning")
    repeated_hypotheses = 0  # placeholder for future dedup

    # Queue items = triggers that are actionable
    total_queue_items = len(trigger_list)
    queued_items = len(trigger_list)
    approved_items = 0  # requires integration with queue approval
    applied_items = 0   # requires integration with apply tracking
    rejected_items = 0
    rolled_back_items = 0

    ts = comparison.get("timestamp") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    return {
        "total_hypotheses": total_hypotheses,
        "repeated_hypotheses": repeated_hypotheses,
        "total_verifications": total_verifications,
        "passed_verifications": passed_verifications,
        "failed_verifications": failed_verifications,
        "inconclusive_verifications": inconclusive_verifications,
        "total_queue_items": total_queue_items,
        "queued_items": queued_items,
        "approved_items": approved_items,
        "applied_items": applied_items,
        "rejected_items": rejected_items,
        "rolled_back_items": rolled_back_items,
        "failed_hypotheses": failed_hypotheses,
        "latest_verification_at": ts,
        "latest_queue_item_at": ts,
        "latest_failed_hypothesis_at": ts if failed_hypotheses > 0 else None,
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



def apply_regression_triggers_to_refinement(
    memory: RefinementMemoryStore,
    *,
    comparison_limit: int = 5,
    threshold: str = "warning",
) -> dict[str, Any]:
    """Persist regression trigger outputs into refinement memory as hypotheses,
    verification records, and rollout queue items.
    """
    trigger_payload = build_regression_triggers(
        comparison_limit=comparison_limit,
        threshold=threshold,
    )
    created_hypotheses = []
    created_queue_items = []
    created_verifications = []

    for trigger in trigger_payload["triggers"]:
        signal = trigger["signal"]
        contradiction = f"Regression signal: {signal}"
        hypothesis = memory.add_hypothesis(
            RefinementHypothesis(
                hypothesis_id=f"reg-hyp-{uuid4().hex[:12]}",
                app_instance_id=APP_INSTANCE_ID,
                proposal_id=trigger["trigger_id"],
                experience_id=trigger["trigger_id"],
                contradiction=contradiction,
                hypothesis=f"Address {signal} through {trigger['recommended_action']}",
                expected_change=trigger["detail"],
                evidence=[trigger["detail"]],
                repeat_risk="medium" if trigger["level"] == "warning" else "low",
            )
        )
        verification = memory.add_verification(
            VerificationResult(
                verification_id=f"reg-ver-{uuid4().hex[:12]}",
                hypothesis_id=hypothesis.hypothesis_id,
                app_instance_id=APP_INSTANCE_ID,
                outcome="failed" if trigger["level"] == "warning" else "inconclusive",
                summary=trigger["detail"],
                failed_checks=[signal] if trigger["level"] == "warning" else [],
                execution_reference=trigger["trigger_id"],
                failure_aware=True,
                gating_reason=trigger["recommended_action"],
            )
        )
        queue_item = memory.add_queue_item(
            RolloutQueueItem(
                queue_id=f"reg-queue-{uuid4().hex[:12]}",
                hypothesis_id=hypothesis.hypothesis_id,
                proposal_id=trigger["trigger_id"],
                app_instance_id=APP_INSTANCE_ID,
                status="queued",
                note=trigger["recommended_action"],
            )
        )
        created_hypotheses.append(hypothesis.model_dump(mode="json"))
        created_verifications.append(verification.model_dump(mode="json"))
        created_queue_items.append(queue_item.model_dump(mode="json"))

    return {
        "trigger_count": trigger_payload["trigger_count"],
        "created_hypotheses": created_hypotheses,
        "created_verifications": created_verifications,
        "created_queue_items": created_queue_items,
        "generated_at": trigger_payload["generated_at"],
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
