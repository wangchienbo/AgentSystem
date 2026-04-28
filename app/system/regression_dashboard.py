"""
Regression Governance Dashboard
Connects chat regression operational data into a governance-oriented dashboard view,
bridging regression trends, evidence, and comparison into a single refinement-ready surface.
"""
from __future__ import annotations

from typing import Any

from app.models.refinement_loop import RefinementFilter
from app.services.refinement_memory import RefinementMemoryStore
from app.system.chat_regression import build_multi_run_comparison, build_topic_trends, read_run_details
from app.system.regression_evidence_bridge import list_regression_evidence_history
from app.system.regression_governance_observation import build_governance_evidence_digest, build_replay_observation_digest
from app.system.regression_governance_policy import (
    build_automation_attention,
    build_automation_risk_flags,
    build_comparison_risk_flags,
    classify_signal_domain,
    classify_signal_family,
    recommend_action_for_signal,
    signal_priority,
)
from app.system.regression_refinement_translation import persist_trigger_payloads

APP_INSTANCE_ID = "agent_system"


FAILURE_STAGE_SIGNAL_MAP = {
    "elevated_latency": "execution",
    "elevated_fallback": "execution",
    "elevated_overreach": "answer_shaping",
    "conservative_mode_skew": "requirement_understanding",
    "nightly_automation_warning": "execution",
    "nightly_automation_degraded": "execution",
}


def build_regression_governance_dashboard(
    *,
    comparison_limit: int = 5,
    trends_limit: int = 5,
    evidence_limit: int = 10,
    memory: RefinementMemoryStore | None = None,
    nightly_status: dict[str, Any] | None = None,
    replay_session_id: str | None = None,
    replay_history: list[dict[str, Any]] | None = None,
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

    latest_run = None
    comparison_runs = comparison.get("runs") or []
    if comparison_runs:
        latest_run = comparison_runs[0].get("summary", {}).get("run_id")
    observation_digest = build_governance_evidence_digest(read_run_details(latest_run)) if latest_run else build_governance_evidence_digest(None)
    replay_observation_digest = None
    if replay_session_id and replay_history is not None:
        replay_observation_digest = build_replay_observation_digest(replay_session_id, replay_history).model_dump(mode="json")

    # Build risk summary from comparison data
    risk_flags = build_comparison_risk_flags(comparison)

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

    automation_attention = None
    if nightly_status is not None:
        automation_attention = build_automation_attention(nightly_status.get("automation_control") or {})
        risk_flags.extend(build_automation_risk_flags(automation_attention))

    return {
        "comparison": comparison,
        "trends": trends,
        "evidence": evidence,
        "observation_digest": observation_digest.model_dump(mode="json"),
        "replay_observation_digest": replay_observation_digest,
        "risk_flags": risk_flags,
        "rollout_summary": rollout_summary,
        "nightly_automation": nightly_status,
        "automation_attention": automation_attention,
        "dashboard_id": "regression-governance",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def build_regression_operator_summary(
    *,
    comparison_limit: int = 5,
    trends_limit: int = 5,
    evidence_limit: int = 10,
    memory: RefinementMemoryStore | None = None,
    nightly_status: dict[str, Any] | None = None,
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
        nightly_status=nightly_status,
    )
    triggers = build_regression_triggers(comparison_limit=comparison_limit, nightly_status=nightly_status)
    metrics = _build_refinement_metrics_from_regression(dashboard["comparison"], triggers)
    family_breakdown = _build_family_breakdown_from_triggers(triggers)
    live_governance = None
    if memory is not None:
        live_governance = memory.get_governance_dashboard(RefinementFilter(app_instance_id=APP_INSTANCE_ID), recent_limit=5)

    risk_flags = dashboard.get("risk_flags", [])
    primary_contradiction = ""
    recommended_action = ""
    priority_domain = ""
    priority_family = ""
    priority_signal = ""
    if risk_flags:
        worst = max(risk_flags, key=signal_priority)
        priority_signal = worst.get("signal", "unknown")
        priority_domain = classify_signal_domain(priority_signal)
        priority_family = classify_signal_family(priority_signal)
        primary_contradiction = f"{priority_domain}: {priority_signal}"
        recommended_action = recommend_action_for_signal(priority_signal)

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
            "priority_domain": priority_domain or None,
            "priority_family": priority_family or None,
            "priority_signal": priority_signal or None,
            "context_summary": "Regression-integrated governance summary",
            "governance": {
                "overview": overview,
                "stats": stats,
                "recent_queue": recent_queue,
                "family_breakdown": family_breakdown,
                "recent_failed_hypotheses": recent_failed_hypotheses,
                "nightly_automation": nightly_status,
                "automation_attention": dashboard.get("automation_attention"),
            },
        },
        "regression": dashboard,
        "generated_at": dashboard["generated_at"],
    }




def _build_family_breakdown_from_triggers(triggers: dict[str, Any]) -> dict[str, Any]:
    trigger_list = triggers.get("triggers", [])
    counts: dict[str, int] = {}
    latest_items: dict[str, dict[str, Any]] = {}
    for item in trigger_list:
        family = item.get("family") or "unclassified"
        counts[family] = counts.get(family, 0) + 1
        latest_items[family] = {
            "signal": item.get("signal"),
            "domain": item.get("domain"),
            "family": family,
            "recommended_action": item.get("recommended_action"),
            "failure_stage": item.get("failure_stage"),
            "generated_at": item.get("generated_at"),
        }
    return {
        "counts": counts,
        "latest_items": latest_items,
        "family_count": len(counts),
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

def _derive_failure_stage_for_signal(signal: str, observation_digest: dict[str, Any]) -> str:
    failure_stage_counts = observation_digest.get("failure_stage_counts") or {}
    mapped = FAILURE_STAGE_SIGNAL_MAP.get(signal)
    if mapped and failure_stage_counts.get(mapped, 0) > 0:
        return mapped
    if failure_stage_counts:
        return max(failure_stage_counts.items(), key=lambda item: item[1])[0]
    return mapped or "unclassified"


def build_regression_triggers(
    *,
    comparison_limit: int = 5,
    threshold: str = "warning",
    nightly_status: dict[str, Any] | None = None,
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
        nightly_status=nightly_status,
    )
    risk_flags = dashboard.get("risk_flags", [])
    observation_digest = dashboard.get("observation_digest") or build_governance_evidence_digest(None).model_dump(mode="json")
    # Filter by severity
    level_priority = {"info": 0, "warning": 1}
    min_priority = level_priority.get(threshold, 0)
    actionable = [flag for flag in risk_flags if level_priority.get(flag.get("level", ""), 0) >= min_priority]

    from uuid import uuid4
    from datetime import timezone as _tz
    ts = __import__("datetime").datetime.now(_tz.utc).isoformat()

    triggers = []
    for flag in actionable:
        signal = flag.get("signal", "")
        triggers.append({
            "trigger_id": f"regression-trigger-{uuid4().hex[:12]}",
            "signal": signal,
            "level": flag.get("level", ""),
            "domain": classify_signal_domain(signal),
            "family": classify_signal_family(signal),
            "recommended_action": recommend_action_for_signal(signal),
            "detail": flag.get("detail", ""),
            "failure_stage": _derive_failure_stage_for_signal(signal, observation_digest),
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
    nightly_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist regression trigger outputs into refinement memory as hypotheses,
    verification records, and rollout queue items.
    """
    trigger_payload = build_regression_triggers(
        comparison_limit=comparison_limit,
        threshold=threshold,
        nightly_status=nightly_status,
    )
    persisted = persist_trigger_payloads(memory, trigger_payload["triggers"])
    persisted["generated_at"] = trigger_payload["generated_at"]
    return persisted

def _recommend_action_for_signal(signal: str) -> str:
    """Map regression risk signals to recommended refinement actions."""
    actions = {
        "elevated_latency": "profile_performance_bottlenecks",
        "elevated_fallback": "review_tool_calling_prompt_template",
        "elevated_overreach": "tighten_evidence_boundary_guard",
        "conservative_mode_skew": "audit_verification_policy_thresholds",
        "nightly_automation_warning": "inspect_nightly_automation_recovery_path",
        "nightly_automation_degraded": "stabilize_nightly_automation_control_plane",
    }
    return actions.get(signal, "manual_review_required")
