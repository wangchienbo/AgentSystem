from __future__ import annotations

from typing import Any


def build_asset_query_action(asset_id: str, *, reason: str | None = None, purpose: str | None = None) -> dict[str, Any]:
    action: dict[str, Any] = {
        "asset_id": "asset:self_iteration_center:v1",
        "method": "query_self_iteration_asset",
        "params": {"asset_id": asset_id},
    }
    if reason is not None:
        action["reason"] = reason
    if purpose is not None:
        action["purpose"] = purpose
    return action


def select_recommended_next_asset(*, pressure_snapshot: dict[str, int]) -> dict[str, str]:
    if int(pressure_snapshot.get("risk_flag_count") or 0) > 0:
        return {
            "asset_id": "self_iteration.governance_dashboard",
            "layer": "summarize",
            "reason": "Governance risk flags are active, inspect dashboard pressure before lower-priority history.",
        }
    if int(pressure_snapshot.get("trigger_count") or 0) > 0:
        return {
            "asset_id": "self_iteration.governance_triggers",
            "layer": "act",
            "reason": "Derived governance triggers exist, inspect proposed act-stage work before browsing history.",
        }
    if int(pressure_snapshot.get("queue_count") or 0) > 0 or int(pressure_snapshot.get("failed_hypothesis_count") or 0) > 0:
        return {
            "asset_id": "self_iteration.refinement_backlog",
            "layer": "act",
            "reason": "Refinement backlog pressure exists, inspect queued or failed follow-up work next.",
        }
    if int(pressure_snapshot.get("total_observations") or 0) > 0:
        return {
            "asset_id": "self_iteration.live_observation_digest",
            "layer": "observe",
            "reason": "Live observations exist, inspect current user-facing evidence before historic regressions.",
        }
    return {
        "asset_id": "self_iteration.regression_runs",
        "layer": "observe",
        "reason": "No immediate governance or backlog pressure detected, start from recent regression history.",
    }


def build_follow_up_actions(*, recommended_asset_id: str) -> list[dict[str, Any]]:
    candidates = [
        build_asset_query_action(
            "self_iteration.governance_dashboard",
            purpose="Check summarized governance pressure and lane assignment.",
        ),
        build_asset_query_action(
            "self_iteration.governance_triggers",
            purpose="Inspect derived act-stage trigger candidates.",
        ),
        build_asset_query_action(
            "self_iteration.refinement_backlog",
            purpose="Review queued or failed follow-up refinement work.",
        ),
    ]
    return [action for action in candidates if action["params"]["asset_id"] != recommended_asset_id]


def build_strategy_route(*, recommended_next_asset: dict[str, str], recommended_next_action: dict[str, Any]) -> list[dict[str, Any]]:
    recommended_layer = recommended_next_asset["layer"]
    route = [
        {
            "phase": recommended_layer,
            "asset_id": recommended_next_asset["asset_id"],
            "action": recommended_next_action,
            "goal": recommended_next_asset["reason"],
        }
    ]
    if recommended_layer != "summarize":
        route.append(
            {
                "phase": "summarize",
                "asset_id": "self_iteration.governance_dashboard",
                "action": build_asset_query_action("self_iteration.governance_dashboard"),
                "goal": "Normalize current pressure into a governance-level summary before choosing rollout work.",
            }
        )
    if recommended_layer != "act":
        route.append(
            {
                "phase": "act",
                "asset_id": "self_iteration.governance_triggers",
                "action": build_asset_query_action("self_iteration.governance_triggers"),
                "goal": "Inspect act-stage trigger candidates and decide what refinement work should move next.",
            }
        )
    route.append(
        {
            "phase": "validate",
            "asset_id": "self_iteration.live_observation_digest",
            "action": build_asset_query_action("self_iteration.live_observation_digest"),
            "goal": "Return to live observations to validate whether the chosen action improved user-facing behavior.",
        }
    )
    return route
