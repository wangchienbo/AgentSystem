from __future__ import annotations

from typing import Any

from app.models.refinement_loop import RefinementFilter
from app.services.refinement_memory import RefinementMemoryStore
from app.system.chat_observation import build_chat_observation_digest
from app.system.chat_regression import build_multi_run_comparison, list_saved_runs
from app.system.regression_dashboard import build_regression_governance_dashboard, build_regression_triggers


SELF_ITERATION_ASSET_NAMESPACE = "self_iteration"


def _build_asset_summary(
    *,
    asset_id: str,
    asset_type: str,
    title: str,
    summary: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "title": title,
        "summary": summary,
        "detail": detail,
    }


def _build_topic_counts(topic_failure_stage_counts: dict[str, dict[str, int]]) -> dict[str, int]:
    return {
        topic: sum(int(value) for value in (stage_counts or {}).values())
        for topic, stage_counts in (topic_failure_stage_counts or {}).items()
    }


def build_self_iteration_asset_summaries(
    *,
    memory: RefinementMemoryStore | None = None,
    replay_session_id: str | None = None,
    comparison_limit: int = 5,
) -> list[dict[str, Any]]:
    refinement_memory = memory or RefinementMemoryStore()

    runs = list_saved_runs(limit=comparison_limit)
    comparison = build_multi_run_comparison(limit=comparison_limit)
    dashboard = build_regression_governance_dashboard(
        comparison_limit=comparison_limit,
        memory=refinement_memory,
        replay_session_id=replay_session_id,
    )
    triggers = build_regression_triggers(
        comparison_limit=comparison_limit,
        replay_session_id=replay_session_id,
    )
    observation_digest_model = build_chat_observation_digest(session_id=replay_session_id)
    observation_digest = observation_digest_model.model_dump(mode="json")
    observation_topic_counts = _build_topic_counts(observation_digest.get("topic_failure_stage_counts", {}))

    queue_items = refinement_memory.list_queue(app_instance_id="agent_system")
    failed_hypotheses_page = refinement_memory.list_failed_hypothesis_page(
        RefinementFilter(app_instance_id="agent_system", limit=20)
    )

    assets = [
        _build_asset_summary(
            asset_id=f"{SELF_ITERATION_ASSET_NAMESPACE}.regression_runs",
            asset_type="self_iteration_asset",
            title="Regression run history",
            summary=f"{len(runs)} saved runs, avg latency {comparison.get('avg_latency_ms', 0)} ms",
            detail={
                "run_count": len(runs),
                "latest_run_id": None if not runs else runs[0].get("summary", {}).get("run_id"),
                "avg_latency_ms": comparison.get("avg_latency_ms", 0),
                "avg_fallback_count": comparison.get("avg_fallback_count", 0),
                "avg_overreach_risk_count": comparison.get("avg_overreach_risk_count", 0),
            },
        ),
        _build_asset_summary(
            asset_id=f"{SELF_ITERATION_ASSET_NAMESPACE}.live_observation_digest",
            asset_type="self_iteration_asset",
            title="Live chat observation digest",
            summary=f"{observation_digest.get('total_observations', 0)} observations across {len(observation_topic_counts)} topics",
            detail={
                **observation_digest,
                "topic_counts": observation_topic_counts,
            },
        ),
        _build_asset_summary(
            asset_id=f"{SELF_ITERATION_ASSET_NAMESPACE}.governance_dashboard",
            asset_type="self_iteration_asset",
            title="Governance dashboard",
            summary=f"{len((dashboard.get('risk_flags') or []))} risk flags, {dashboard.get('overview', {}).get('queue_count', 0)} queued items",
            detail={
                "risk_flag_count": len(dashboard.get("risk_flags") or []),
                "queue_count": dashboard.get("overview", {}).get("queue_count", 0),
                "failed_verification_count": dashboard.get("overview", {}).get("failed_verification_count", 0),
                "priority_lane": dashboard.get("priority_lane"),
            },
        ),
        _build_asset_summary(
            asset_id=f"{SELF_ITERATION_ASSET_NAMESPACE}.governance_triggers",
            asset_type="self_iteration_asset",
            title="Governance trigger backlog",
            summary=f"{triggers.get('trigger_count', 0)} derived triggers ready for refinement translation",
            detail={
                "trigger_count": triggers.get("trigger_count", 0),
                "top_signals": [item.get("signal") for item in (triggers.get("triggers") or [])[:5]],
                "top_observation_topics": [item.get("observation_topic") for item in (triggers.get("triggers") or [])[:5]],
            },
        ),
        _build_asset_summary(
            asset_id=f"{SELF_ITERATION_ASSET_NAMESPACE}.refinement_backlog",
            asset_type="self_iteration_asset",
            title="Refinement backlog",
            summary=f"{len(queue_items)} queued rollout items, {failed_hypotheses_page.meta.filtered_count} failed hypotheses on page 1",
            detail={
                "queue_count": len(queue_items),
                "top_queue_notes": [item.note for item in queue_items[:5]],
                "failed_hypothesis_count": failed_hypotheses_page.meta.filtered_count,
                "top_failed_hypotheses": [item.hypothesis_id for item in failed_hypotheses_page.items[:5]],
            },
        ),
    ]
    return assets
