from __future__ import annotations

from typing import Any

from app.services.refinement_memory import RefinementMemoryStore
from app.system.self_iteration_assets import build_self_iteration_asset_summaries


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
