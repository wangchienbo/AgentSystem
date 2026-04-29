from __future__ import annotations

from typing import Any


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
