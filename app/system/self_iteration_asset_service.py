from __future__ import annotations

from typing import Any

from app.services.refinement_memory import RefinementMemoryStore
from app.system.self_iteration_assets import build_self_iteration_asset_summaries
from app.system.self_iteration_strategy import (
    build_asset_query_action,
    build_follow_up_actions,
    build_strategy_route,
    select_recommended_next_asset,
)


class SelfIterationAssetService:
    def __init__(self, memory: RefinementMemoryStore | None = None) -> None:
        self._memory = memory or RefinementMemoryStore()

    def list_self_iteration_assets(self, replay_session_id: str | None = None, comparison_limit: int = 5) -> list[dict[str, Any]]:
        return build_self_iteration_asset_summaries(
            memory=self._memory,
            replay_session_id=replay_session_id,
            comparison_limit=comparison_limit,
        )

    def query_self_iteration_asset(self, asset_id: str, replay_session_id: str | None = None, comparison_limit: int = 5) -> dict[str, Any] | None:
        for asset in self.list_self_iteration_assets(
            replay_session_id=replay_session_id,
            comparison_limit=comparison_limit,
        ):
            if asset.get("asset_id") == asset_id:
                return asset
        return None

    def get_self_iteration_strategy_overview(self, replay_session_id: str | None = None, comparison_limit: int = 5) -> dict[str, Any]:
        assets = self.list_self_iteration_assets(
            replay_session_id=replay_session_id,
            comparison_limit=comparison_limit,
        )
        by_id = {
            asset.get("asset_id"): asset
            for asset in assets
            if isinstance(asset, dict) and asset.get("asset_id")
        }

        governance_dashboard = by_id.get("self_iteration.governance_dashboard") or {}
        governance_triggers = by_id.get("self_iteration.governance_triggers") or {}
        refinement_backlog = by_id.get("self_iteration.refinement_backlog") or {}
        observation_digest = by_id.get("self_iteration.live_observation_digest") or {}
        regression_runs = by_id.get("self_iteration.regression_runs") or {}

        dashboard_detail = governance_dashboard.get("detail") if isinstance(governance_dashboard.get("detail"), dict) else {}
        trigger_detail = governance_triggers.get("detail") if isinstance(governance_triggers.get("detail"), dict) else {}
        backlog_detail = refinement_backlog.get("detail") if isinstance(refinement_backlog.get("detail"), dict) else {}
        observation_detail = observation_digest.get("detail") if isinstance(observation_digest.get("detail"), dict) else {}
        regression_detail = regression_runs.get("detail") if isinstance(regression_runs.get("detail"), dict) else {}

        pressure_snapshot = {
            "risk_flag_count": int(dashboard_detail.get("risk_flag_count") or 0),
            "trigger_count": int(trigger_detail.get("trigger_count") or 0),
            "queue_count": int(backlog_detail.get("queue_count") or 0),
            "failed_hypothesis_count": int(backlog_detail.get("failed_hypothesis_count") or 0),
            "total_observations": int(observation_detail.get("total_observations") or 0),
            "run_count": int(regression_detail.get("run_count") or 0),
        }

        recommended_next_asset = select_recommended_next_asset(
            pressure_snapshot=pressure_snapshot,
        )
        recommended_next_action = build_asset_query_action(
            recommended_next_asset["asset_id"],
            reason=recommended_next_asset["reason"],
        )
        follow_up_actions = build_follow_up_actions(
            recommended_asset_id=recommended_next_asset["asset_id"],
        )
        route = build_strategy_route(
            recommended_next_asset=recommended_next_asset,
            recommended_next_action=recommended_next_action,
        )

        return {
            "system_view": {
                "observe": [
                    "self_iteration.regression_runs",
                    "self_iteration.live_observation_digest",
                ],
                "summarize": [
                    "self_iteration.governance_dashboard",
                ],
                "act": [
                    "self_iteration.governance_triggers",
                    "self_iteration.refinement_backlog",
                ],
            },
            "recommended_next_asset": recommended_next_asset,
            "recommended_next_action": recommended_next_action,
            "follow_up_actions": follow_up_actions,
            "route": route,
            "pressure_snapshot": pressure_snapshot,
            "assets": assets,
        }
