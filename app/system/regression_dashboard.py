"""
Regression Governance Dashboard
Connects chat regression operational data into a governance-oriented dashboard view,
bridging regression trends, evidence, and comparison into a single refinement-ready surface.
"""
from __future__ import annotations

from typing import Any

from app.models.governance_observation import GovernanceEvidenceDigest
from app.models.refinement_loop import RefinementFilter
from app.services.refinement_memory import RefinementMemoryStore
from app.system.chat_observation import build_chat_observation_digest
from app.system.chat_regression import build_multi_run_comparison, build_topic_trends, read_run_details
from app.system.regression_evidence_bridge import list_regression_evidence_history
from app.system.regression_governance_observation import build_governance_evidence_digest, build_replay_observation_digest
from app.system.regression_governance_policy import (
    build_automation_attention,
    build_automation_risk_flags,
    build_comparison_risk_flags,
    classify_signal_domain,
    classify_signal_family,
    classify_signal_subdomain_candidate,
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


def _merge_observation_digests(*digests: dict[str, Any] | None) -> dict[str, Any]:
    total_observations = 0
    failure_stage_counts: dict[str, int] = {}
    topic_failure_stage_counts: dict[str, dict[str, int]] = {}
    evidence_kind_counts: dict[str, int] = {}
    observation_samples: list[dict[str, Any]] = []

    for digest in digests:
        if not digest:
            continue
        total_observations += int(digest.get("total_observations") or 0)
        for stage, count in (digest.get("failure_stage_counts") or {}).items():
            failure_stage_counts[stage] = failure_stage_counts.get(stage, 0) + int(count)
        for kind, count in (digest.get("evidence_kind_counts") or {}).items():
            evidence_kind_counts[kind] = evidence_kind_counts.get(kind, 0) + int(count)
        for topic, bucket in (digest.get("topic_failure_stage_counts") or {}).items():
            topic_counts = topic_failure_stage_counts.setdefault(topic, {})
            for stage, count in (bucket or {}).items():
                topic_counts[stage] = topic_counts.get(stage, 0) + int(count)
        observation_samples.extend(digest.get("observation_samples") or [])

    dominant_failure_stage = max(failure_stage_counts.items(), key=lambda item: item[1])[0] if failure_stage_counts else None
    dominant_evidence_kind = max(evidence_kind_counts.items(), key=lambda item: item[1])[0] if evidence_kind_counts else None
    merged = GovernanceEvidenceDigest(
        total_observations=total_observations,
        dominant_failure_stage=dominant_failure_stage,
        dominant_evidence_kind=dominant_evidence_kind,
        failure_stage_counts=failure_stage_counts,
        evidence_kind_counts=evidence_kind_counts,
        topic_failure_stage_counts=topic_failure_stage_counts,
        observation_samples=observation_samples,
    )
    return merged.model_dump(mode="json")


def _build_observation_digest_summary(observation_digest: dict[str, Any] | None) -> dict[str, Any]:
    observation_digest = observation_digest or {}
    return {
        "total_observations": int(observation_digest.get("total_observations") or 0),
        "dominant_failure_stage": observation_digest.get("dominant_failure_stage"),
        "dominant_evidence_kind": observation_digest.get("dominant_evidence_kind"),
        "failure_stage_counts": observation_digest.get("failure_stage_counts") or {},
        "evidence_kind_counts": observation_digest.get("evidence_kind_counts") or {},
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
    live_chat_observation_digest = None
    if replay_session_id:
        live_chat_observation_digest = build_chat_observation_digest(session_id=replay_session_id).model_dump(mode="json")
    combined_observation_digest = _merge_observation_digests(
        observation_digest.model_dump(mode="json"),
        live_chat_observation_digest,
    )
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
        "observation_digest": combined_observation_digest,
        "observation_digest_summary": _build_observation_digest_summary(combined_observation_digest),
        "live_chat_observation_digest": live_chat_observation_digest,
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
    subdomain_breakdown = _build_subdomain_breakdown_from_triggers(triggers)
    family_queue_lane_summary = _build_family_queue_lane_summary(triggers)
    live_governance = None
    if memory is not None:
        live_governance = memory.get_governance_dashboard(RefinementFilter(app_instance_id=APP_INSTANCE_ID), recent_limit=5)

    risk_flags = dashboard.get("risk_flags", [])
    primary_contradiction = ""
    recommended_action = ""
    priority_domain = ""
    priority_family = ""
    priority_signal = ""
    priority_subdomain_candidate = ""
    if risk_flags:
        worst = max(risk_flags, key=signal_priority)
        priority_signal = worst.get("signal", "unknown")
        priority_domain = classify_signal_domain(priority_signal)
        priority_family = classify_signal_family(priority_signal)
        priority_subdomain_candidate = classify_signal_subdomain_candidate(priority_signal)
        primary_contradiction = f"{priority_domain}: {priority_signal}"
        recommended_action = recommend_action_for_signal(priority_signal)
    cross_level_summary = _build_cross_level_governance_summary(
        triggers,
        priority_family=priority_family,
        priority_subdomain_candidate=priority_subdomain_candidate,
    )

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
    prioritized_queue_view = _build_governance_prioritized_queue_view(recent_queue)
    rollout_selection = _build_governance_rollout_selection(prioritized_queue_view)
    rollout_review_packet = _build_governance_rollout_review_packet(
        prioritized_queue_view=prioritized_queue_view,
        rollout_selection=rollout_selection,
        cross_level_summary=cross_level_summary,
        automation_attention=dashboard.get("automation_attention"),
        recommended_action=recommended_action,
    )
    rollout_review_card = _build_governance_rollout_review_card(rollout_review_packet)
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
            "priority_subdomain_candidate": priority_subdomain_candidate or None,
            "priority_signal": priority_signal or None,
            "context_summary": "Regression-integrated governance summary",
            "governance": {
                "overview": overview,
                "stats": stats,
                "recent_queue": recent_queue,
                "prioritized_queue_view": prioritized_queue_view,
                "rollout_selection": rollout_selection,
                "rollout_review_packet": rollout_review_packet,
                "rollout_review_card": rollout_review_card,
                "family_breakdown": family_breakdown,
                "subdomain_breakdown": subdomain_breakdown,
                "family_queue_lane_summary": family_queue_lane_summary,
                "cross_level_summary": cross_level_summary,
                "recent_failed_hypotheses": recent_failed_hypotheses,
                "nightly_automation": nightly_status,
                "automation_attention": dashboard.get("automation_attention"),
                "observation_digest_summary": dashboard.get("observation_digest_summary"),
            },
        },
        "regression": dashboard,
        "generated_at": dashboard["generated_at"],
    }




def _build_governance_prioritized_queue_view(recent_queue: dict[str, Any]) -> dict[str, Any]:
    items = list(recent_queue.get("items", []))

    def _priority_rank(note: str) -> int:
        if "::priority=primary" in note:
            return 0
        if "::priority=secondary" in note:
            return 1
        return 2

    ordered = sorted(
        items,
        key=lambda item: (_priority_rank(item.get("note", "")), item.get("created_at", "")),
        reverse=False,
    )

    counts = {"primary": 0, "secondary": 0, "normal": 0}
    for item in ordered:
        note = item.get("note", "")
        if "::priority=primary" in note:
            counts["primary"] += 1
        elif "::priority=secondary" in note:
            counts["secondary"] += 1
        else:
            counts["normal"] += 1

    return {
        "items": ordered,
        "meta": recent_queue.get("meta", {}),
        "priority_counts": counts,
        "ordering": ["primary", "secondary", "normal"],
    }


def _build_governance_rollout_selection(prioritized_queue_view: dict[str, Any]) -> dict[str, Any]:
    items = prioritized_queue_view.get("items", [])
    if not items:
        return {
            "recommended_queue_id": None,
            "recommended_priority_tier": None,
            "selection_reason": "no_queue_items_available",
            "selection_mode": "governance_priority_ordering",
        }

    top = items[0]
    note = top.get("note", "")
    if "::priority=primary" in note:
        tier = "primary"
    elif "::priority=secondary" in note:
        tier = "secondary"
    else:
        tier = "normal"

    return {
        "recommended_queue_id": top.get("queue_id"),
        "recommended_priority_tier": tier,
        "selection_reason": f"highest_governance_priority:{tier}",
        "selection_mode": "governance_priority_ordering",
    }


def _build_governance_rollout_review_packet(
    *,
    prioritized_queue_view: dict[str, Any],
    rollout_selection: dict[str, Any],
    cross_level_summary: dict[str, Any],
    automation_attention: dict[str, Any] | None,
    recommended_action: str,
) -> dict[str, Any]:
    selected_id = rollout_selection.get("recommended_queue_id")
    selected_item = None
    for item in prioritized_queue_view.get("items", []):
        if item.get("queue_id") == selected_id:
            selected_item = item
            break

    return {
        "recommended_queue_id": selected_id,
        "recommended_priority_tier": rollout_selection.get("recommended_priority_tier"),
        "selection_reason": rollout_selection.get("selection_reason"),
        "selection_mode": rollout_selection.get("selection_mode"),
        "priority_lane": cross_level_summary.get("priority_lane"),
        "recommended_action": recommended_action or None,
        "family_warning_density": cross_level_summary.get("family_warning_density", {}),
        "subdomain_warning_density": cross_level_summary.get("subdomain_warning_density", {}),
        "priority_counts": prioritized_queue_view.get("priority_counts", {}),
        "top_queue_note": None if selected_item is None else selected_item.get("note"),
        "top_queue_status": None if selected_item is None else selected_item.get("status"),
        "automation_attention": automation_attention,
    }


def _build_governance_rollout_review_card(rollout_review_packet: dict[str, Any]) -> dict[str, Any]:
    queue_id = rollout_review_packet.get("recommended_queue_id")
    tier = rollout_review_packet.get("recommended_priority_tier") or "none"
    action = rollout_review_packet.get("recommended_action") or "manual_review_required"
    lane = rollout_review_packet.get("priority_lane") or "unclassified"
    attention = rollout_review_packet.get("automation_attention") or {}
    attention_reason = attention.get("reason") or "no_automation_attention"

    if queue_id:
        title = f"Review queue item {queue_id}"
        summary = f"Prioritize {tier} governance item on lane {lane}."
    else:
        title = "No rollout candidate ready"
        summary = "No queued governance candidate is currently available."

    return {
        "title": title,
        "summary": summary,
        "recommended_queue_id": queue_id,
        "priority_tier": tier,
        "recommended_action": action,
        "priority_lane": lane,
        "attention_reason": attention_reason,
        "top_queue_note": rollout_review_packet.get("top_queue_note"),
        "status": rollout_review_packet.get("top_queue_status"),
    }


def _build_cross_level_governance_summary(
    triggers: dict[str, Any],
    *,
    priority_family: str,
    priority_subdomain_candidate: str,
) -> dict[str, Any]:
    trigger_list = triggers.get("triggers", [])
    family_to_subdomains: dict[str, list[str]] = {}
    subdomain_to_latest_lane: dict[str, str] = {}
    family_warning_density: dict[str, float] = {}
    subdomain_warning_density: dict[str, float] = {}
    priority_lane = None

    family_totals: dict[str, int] = {}
    family_warnings: dict[str, int] = {}
    subdomain_totals: dict[str, int] = {}
    subdomain_warnings: dict[str, int] = {}

    for item in trigger_list:
        family = item.get("family") or "unclassified"
        subdomain = item.get("subdomain_candidate") or "unclassified"
        action = item.get("recommended_action") or "manual_review_required"
        lane = f"{family}::{action}"

        family_totals[family] = family_totals.get(family, 0) + 1
        subdomain_totals[subdomain] = subdomain_totals.get(subdomain, 0) + 1
        if item.get("level") == "warning":
            family_warnings[family] = family_warnings.get(family, 0) + 1
            subdomain_warnings[subdomain] = subdomain_warnings.get(subdomain, 0) + 1

        bucket = family_to_subdomains.setdefault(family, [])
        if subdomain not in bucket:
            bucket.append(subdomain)
        subdomain_to_latest_lane[subdomain] = lane

        if priority_lane is None and family == priority_family and subdomain == priority_subdomain_candidate:
            priority_lane = lane

    for family, total in family_totals.items():
        family_warning_density[family] = family_warnings.get(family, 0) / total if total else 0.0
    for subdomain, total in subdomain_totals.items():
        subdomain_warning_density[subdomain] = subdomain_warnings.get(subdomain, 0) / total if total else 0.0

    return {
        "priority_lane": priority_lane,
        "family_to_subdomains": family_to_subdomains,
        "subdomain_to_latest_lane": subdomain_to_latest_lane,
        "family_warning_density": family_warning_density,
        "subdomain_warning_density": subdomain_warning_density,
    }


def _build_subdomain_breakdown_from_triggers(triggers: dict[str, Any]) -> dict[str, Any]:
    trigger_list = triggers.get("triggers", [])
    counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    family_map: dict[str, str] = {}
    latest_items: dict[str, dict[str, Any]] = {}

    for item in trigger_list:
        subdomain = item.get("subdomain_candidate") or "unclassified"
        family = item.get("family") or "unclassified"
        counts[subdomain] = counts.get(subdomain, 0) + 1
        family_map[subdomain] = family
        if item.get("level") == "warning":
            warning_counts[subdomain] = warning_counts.get(subdomain, 0) + 1
        latest_items[subdomain] = {
            "signal": item.get("signal"),
            "domain": item.get("domain"),
            "family": family,
            "subdomain_candidate": subdomain,
            "recommended_action": item.get("recommended_action"),
            "failure_stage": item.get("failure_stage"),
            "level": item.get("level"),
            "generated_at": item.get("generated_at"),
        }

    return {
        "counts": counts,
        "warning_counts": warning_counts,
        "family_map": family_map,
        "latest_items": latest_items,
        "subdomain_count": len(counts),
    }


def _build_family_queue_lane_summary(triggers: dict[str, Any]) -> dict[str, Any]:
    trigger_list = triggers.get("triggers", [])
    family_counts: dict[str, int] = {}
    action_counts: dict[str, dict[str, int]] = {}
    warning_counts: dict[str, int] = {}
    latest_lane_items: dict[str, dict[str, Any]] = {}

    for item in trigger_list:
        family = item.get("family") or "unclassified"
        action = item.get("recommended_action") or "manual_review_required"
        lane_key = f"{family}::{action}"
        family_counts[family] = family_counts.get(family, 0) + 1
        action_bucket = action_counts.setdefault(family, {})
        action_bucket[action] = action_bucket.get(action, 0) + 1
        if item.get("level") == "warning":
            warning_counts[family] = warning_counts.get(family, 0) + 1
        latest_lane_items[lane_key] = {
            "domain": item.get("domain"),
            "family": family,
            "subdomain_candidate": item.get("subdomain_candidate"),
            "signal": item.get("signal"),
            "recommended_action": action,
            "failure_stage": item.get("failure_stage"),
            "level": item.get("level"),
            "generated_at": item.get("generated_at"),
        }

    return {
        "family_counts": family_counts,
        "family_warning_counts": warning_counts,
        "action_counts": action_counts,
        "latest_lane_items": latest_lane_items,
        "lane_count": len(latest_lane_items),
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
            "subdomain_candidate": item.get("subdomain_candidate"),
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


def _derive_observation_topic_for_signal(signal: str, observation_digest: dict[str, Any]) -> str | None:
    topic_failure_stage_counts = observation_digest.get("topic_failure_stage_counts") or {}
    if not topic_failure_stage_counts:
        return None

    preferred_topics_by_signal = {
        "elevated_latency": ["api", "storage", "telemetry", "validation", "live_chat"],
        "elevated_fallback": ["validation", "api", "live_chat", "telemetry", "storage"],
        "elevated_overreach": ["validation", "api", "live_chat", "telemetry", "storage"],
        "conservative_mode_skew": ["validation", "live_chat", "api", "telemetry", "storage"],
    }
    preferred = preferred_topics_by_signal.get(signal, [])
    for topic in preferred:
        if topic in topic_failure_stage_counts:
            return topic

    ranked = sorted(
        topic_failure_stage_counts.items(),
        key=lambda item: sum((item[1] or {}).values()),
        reverse=True,
    )
    return ranked[0][0] if ranked else None


def _derive_observation_lane_hint(observation_topic: str | None, failure_stage: str) -> str | None:
    if observation_topic == "api":
        return "execution_semantics::profile_performance_bottlenecks" if failure_stage == "execution" else "execution_semantics::inspect_api_decision_path"
    if observation_topic == "validation":
        return "answer_shaping::tighten_evidence_boundary_guard" if failure_stage in {"evidence", "answer_shaping"} else "requirement_understanding::raise_clarification_threshold"
    if observation_topic == "telemetry":
        return "execution_semantics::improve_observability_signal_quality"
    if observation_topic == "storage":
        return "execution_semantics::inspect_storage_read_write_path"
    if observation_topic == "live_chat":
        if failure_stage == "requirement_understanding":
            return "requirement_understanding::raise_clarification_threshold"
        if failure_stage in {"evidence", "answer_shaping"}:
            return "answer_shaping::tighten_evidence_boundary_guard"
        return "execution_semantics::inspect_live_chat_request_path"
    return None


def _derive_governance_priority_hints(risk_flags: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None]:
    if not risk_flags:
        return None, None, None
    worst = max(risk_flags, key=signal_priority)
    priority_signal = worst.get("signal", "unknown")
    priority_family = classify_signal_family(priority_signal)
    priority_subdomain_candidate = classify_signal_subdomain_candidate(priority_signal)
    priority_lane = f"{priority_family}::{recommend_action_for_signal(priority_signal)}"
    return priority_family, priority_subdomain_candidate, priority_lane



def build_regression_triggers(
    *,
    comparison_limit: int = 5,
    threshold: str = "warning",
    nightly_status: dict[str, Any] | None = None,
    replay_session_id: str | None = None,
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
        replay_session_id=replay_session_id,
    )
    risk_flags = dashboard.get("risk_flags", [])
    priority_family, priority_subdomain_candidate, priority_lane = _derive_governance_priority_hints(risk_flags)
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
        family = classify_signal_family(signal)
        subdomain_candidate = classify_signal_subdomain_candidate(signal)
        action = recommend_action_for_signal(signal)
        suggested_priority_tier = (
            "primary" if f"{family}::{action}" == priority_lane else
            "secondary" if flag.get("level", "") == "warning" else
            "normal"
        )
        failure_stage = _derive_failure_stage_for_signal(signal, observation_digest)
        observation_topic = _derive_observation_topic_for_signal(signal, observation_digest)
        observation_lane_hint = _derive_observation_lane_hint(observation_topic, failure_stage)
        triggers.append({
            "trigger_id": f"regression-trigger-{uuid4().hex[:12]}",
            "signal": signal,
            "level": flag.get("level", ""),
            "domain": classify_signal_domain(signal),
            "family": family,
            "subdomain_candidate": subdomain_candidate,
            "recommended_action": action,
            "detail": flag.get("detail", ""),
            "failure_stage": failure_stage,
            "observation_topic": observation_topic,
            "governance_priority": {
                "is_priority_family": family == priority_family,
                "is_priority_subdomain_candidate": subdomain_candidate == priority_subdomain_candidate,
                "priority_lane": priority_lane,
                "suggested_priority_tier": suggested_priority_tier,
                "observation_lane_hint": observation_lane_hint,
            },
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
    replay_session_id: str | None = None,
) -> dict[str, Any]:
    """Persist regression trigger outputs into refinement memory as hypotheses,
    verification records, and rollout queue items.
    """
    trigger_payload = build_regression_triggers(
        comparison_limit=comparison_limit,
        threshold=threshold,
        nightly_status=nightly_status,
        replay_session_id=replay_session_id,
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
