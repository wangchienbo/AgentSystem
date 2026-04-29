from __future__ import annotations

from typing import Any

from app.system.runtime_asset_formatter import (
    append_detail_fallback,
    render_asset_detail_header,
    render_asset_summary_list,
)


def render_self_iteration_strategy_overview(result_payload: dict[str, Any]) -> str:
    recommended = result_payload.get("recommended_next_asset") if isinstance(result_payload.get("recommended_next_asset"), dict) else {}
    recommended_action = result_payload.get("recommended_next_action") if isinstance(result_payload.get("recommended_next_action"), dict) else {}
    follow_up_actions = result_payload.get("follow_up_actions") if isinstance(result_payload.get("follow_up_actions"), list) else []
    route = result_payload.get("route") if isinstance(result_payload.get("route"), list) else []
    pressure = result_payload.get("pressure_snapshot") if isinstance(result_payload.get("pressure_snapshot"), dict) else {}
    system_view = result_payload.get("system_view") if isinstance(result_payload.get("system_view"), dict) else {}

    lines = [
        "self_iteration 策略总览:",
        f"- recommended_next_asset: {recommended.get('asset_id')} ({recommended.get('layer')})",
        f"- reason: {recommended.get('reason')}",
        f"- next_action: {recommended_action.get('method')} params={recommended_action.get('params')}",
        f"- action_target: {recommended_action.get('asset_id')}",
        f"- observe: {', '.join(system_view.get('observe') or [])}",
        f"- summarize: {', '.join(system_view.get('summarize') or [])}",
        f"- act: {', '.join(system_view.get('act') or [])}",
        f"- pressure: risk_flags={pressure.get('risk_flag_count')}; triggers={pressure.get('trigger_count')}; queue={pressure.get('queue_count')}; failed_hypotheses={pressure.get('failed_hypothesis_count')}; observations={pressure.get('total_observations')}; runs={pressure.get('run_count')}",
    ]
    for step in route[:3]:
        if not isinstance(step, dict):
            continue
        lines.append(
            f"- route[{step.get('phase')}]: {step.get('action', {}).get('method')} params={step.get('action', {}).get('params')} | {step.get('goal')}"
        )
    for action in follow_up_actions[:2]:
        if not isinstance(action, dict):
            continue
        lines.append(
            f"- follow_up: {action.get('method')} params={action.get('params')} | {action.get('purpose')}"
        )
    return "\n".join(lines)


def _priority(item: dict[str, Any]) -> tuple[int, int]:
    detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
    target_asset_id = item.get("asset_id")
    if target_asset_id == "self_iteration.governance_dashboard":
        return (0, -int(detail.get("risk_flag_count") or 0))
    if target_asset_id == "self_iteration.governance_triggers":
        return (1, -int(detail.get("trigger_count") or 0))
    if target_asset_id == "self_iteration.refinement_backlog":
        backlog_pressure = int(detail.get("queue_count") or 0) + int(detail.get("failed_hypothesis_count") or 0)
        return (2, -backlog_pressure)
    if target_asset_id == "self_iteration.live_observation_digest":
        return (3, -int(detail.get("total_observations") or 0))
    if target_asset_id == "self_iteration.regression_runs":
        return (4, -int(detail.get("run_count") or 0))
    return (9, 0)


def render_self_iteration_asset_list(result_payload: list[dict[str, Any]]) -> str:
    return render_asset_summary_list(
        result_payload,
        header="self_iteration 资产摘要列表 (按运营优先级排序):",
        sort_key=_priority,
    )


def render_self_iteration_asset_detail(result_payload: dict[str, Any]) -> str:
    detail = result_payload.get("detail") if isinstance(result_payload.get("detail"), dict) else {}
    target_asset_id = result_payload.get("asset_id")
    lines = render_asset_detail_header(result_payload, header="self_iteration 资产")
    if target_asset_id == "self_iteration.regression_runs":
        lines.append(
            f"- metrics: run_count={detail.get('run_count')}; latest_run_id={detail.get('latest_run_id')}; avg_latency_ms={detail.get('avg_latency_ms')}"
        )
    elif target_asset_id == "self_iteration.live_observation_digest":
        lines.append(
            f"- observation: total_observations={detail.get('total_observations')}; topic_counts={detail.get('topic_counts')}"
        )
    elif target_asset_id == "self_iteration.governance_dashboard":
        lines.append(
            f"- governance: risk_flag_count={detail.get('risk_flag_count')}; queue_count={detail.get('queue_count')}; priority_lane={detail.get('priority_lane')}"
        )
    elif target_asset_id == "self_iteration.governance_triggers":
        lines.append(
            f"- triggers: trigger_count={detail.get('trigger_count')}; top_signals={detail.get('top_signals')}; top_observation_topics={detail.get('top_observation_topics')}"
        )
    elif target_asset_id == "self_iteration.refinement_backlog":
        lines.append(
            f"- backlog: queue_count={detail.get('queue_count')}; failed_hypothesis_count={detail.get('failed_hypothesis_count')}; top_failed_hypotheses={detail.get('top_failed_hypotheses')}"
        )
    else:
        append_detail_fallback(lines, detail)
    return "\n".join(lines)
