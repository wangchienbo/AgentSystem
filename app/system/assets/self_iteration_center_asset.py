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
            AssetMethodSpec(
                name="strategy_overview",
                description="Alias for get_self_iteration_strategy_overview",
                input_schema={
                    "type": "object",
                    "properties": {
                        "replay_session_id": {"type": "string"},
                        "comparison_limit": {"type": "integer", "default": 5},
                    },
                },
            ),
            AssetMethodSpec(
                name="diagnose_codebase",
                description=(
                    "运行只读代码健康诊断：扫描导入缺陷（from-import 目标缺失）和 "
                    "God Object（超大模块/超长函数）。返回结构化诊断报告。"
                    "用于自治开发闭环的观察层，让系统看见自己代码的问题。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_god_objects": {"type": "boolean", "default": True},
                    },
                },
            ),
            AssetMethodSpec(
                name="propose_code_improvements",
                description=(
                    "自治开发闭环的分析→方案层：基于 diagnose_codebase 的诊断结果，"
                    "对 God Object / 超长函数生成结构化代码重构方案（拆分建议、风险、验证清单、回滚）。"
                    "方案仅供审批参考，不自动应用任何代码变更。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_god_objects": {"type": "boolean", "default": True},
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
            "strategy_overview": lambda replay_session_id=None, comparison_limit=5: self._service.get_self_iteration_strategy_overview(
                replay_session_id=replay_session_id,
                comparison_limit=comparison_limit,
            ),
            "diagnose_codebase": lambda include_god_objects=True: self._service.diagnose_codebase(
                include_god_objects=include_god_objects,
            ),
            "propose_code_improvements": lambda include_god_objects=True: self._service.propose_code_improvements(
                include_god_objects=include_god_objects,
            ),
        }

    def get_service_ref(self) -> SelfIterationAssetService:
        return self._service
