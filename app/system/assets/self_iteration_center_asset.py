from __future__ import annotations

from app.system.asset_center.models import AssetMethodSpec
from app.system.assets.base_asset import BaseAsset
from app.system.assets.descriptor_builder import build_asset_descriptor
from app.system.self_iteration_asset_service import SelfIterationAssetService


class SelfIterationCenterAsset(BaseAsset):
    def __init__(self, service: SelfIterationAssetService) -> None:
        self._service = service

    def asset_id(self) -> str:
        return "asset:self_iteration_center:v1"

    def build_descriptor(self):
        methods = [
            AssetMethodSpec(
                name="list_self_iteration_assets",
                description="List self-iteration asset summaries",
                input_schema={
                    "type": "object",
                    "properties": {
                        "replay_session_id": {"type": "string"},
                        "comparison_limit": {"type": "integer", "default": 5},
                    },
                },
            ),
            AssetMethodSpec(
                name="query_self_iteration_asset",
                description="Query one self-iteration asset summary",
                input_schema={
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "replay_session_id": {"type": "string"},
                        "comparison_limit": {"type": "integer", "default": 5},
                    },
                    "required": ["asset_id"],
                },
            ),
            AssetMethodSpec(
                name="get_self_iteration_strategy_overview",
                description="Return the whole-system self-iteration view with recommended next asset",
                input_schema={
                    "type": "object",
                    "properties": {
                        "replay_session_id": {"type": "string"},
                        "comparison_limit": {"type": "integer", "default": 5},
                    },
                },
            ),
        ]
        return build_asset_descriptor(
            descriptor_version=1,
            asset_id=self.asset_id(),
            kind="system_asset",
            summary="Self-iteration governance and system-evolution navigation surface",
            detail=(
                "Standard asset entry for regression history, live observations, governance pressure, "
                "and refinement backlog. Descriptor and methods are generated from one builder source."
            ),
            methods=methods,
            metadata={"asset_family": "self_iteration", "protocol": "v1"},
        )

    def build_method_mappings(self):
        return {
            "list_self_iteration_assets": lambda replay_session_id=None, comparison_limit=5: self._service.list_self_iteration_assets(
                replay_session_id=replay_session_id,
                comparison_limit=comparison_limit,
            ),
            "query_self_iteration_asset": lambda asset_id, replay_session_id=None, comparison_limit=5: self._service.query_self_iteration_asset(
                asset_id=asset_id,
                replay_session_id=replay_session_id,
                comparison_limit=comparison_limit,
            ),
            "get_self_iteration_strategy_overview": lambda replay_session_id=None, comparison_limit=5: self._service.get_self_iteration_strategy_overview(
                replay_session_id=replay_session_id,
                comparison_limit=comparison_limit,
            ),
        }

    def get_service_ref(self) -> SelfIterationAssetService:
        return self._service
