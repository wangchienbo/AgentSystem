from __future__ import annotations

from app.services.refinement_memory import RefinementMemoryStore
from app.system.asset_center.service import AssetCenterService
from app.system.assets.registration_protocol import AssetRegistrationProtocol
from app.system.assets.self_iteration_center_asset import SelfIterationCenterAsset
from app.system.self_iteration_asset_service import SelfIterationAssetService


def test_self_iteration_asset_descriptor_and_methods_are_same_source() -> None:
    service = SelfIterationAssetService(RefinementMemoryStore())
    asset = SelfIterationCenterAsset(service)

    descriptor = asset.build_descriptor()
    methods = asset.build_method_mappings()

    descriptor_method_names = {method.name for method in descriptor.methods}
    mapping_method_names = set(methods.keys())

    assert descriptor.asset_id == "asset:self_iteration_center:v1"
    assert descriptor.kind == "system_asset"
    assert descriptor_method_names == mapping_method_names
    assert "list_self_iteration_assets" in descriptor_method_names
    assert "query_self_iteration_asset" in descriptor_method_names
    assert "get_self_iteration_strategy_overview" in descriptor_method_names


def test_self_iteration_asset_can_register_through_protocol() -> None:
    service = SelfIterationAssetService(RefinementMemoryStore())
    asset = SelfIterationCenterAsset(service)
    asset_center = AssetCenterService()
    protocol = AssetRegistrationProtocol()

    registered = protocol.register(asset, asset_center)
    detail = asset_center.get_asset_detail("asset:self_iteration_center:v1")

    assert registered.descriptor.asset_id == "asset:self_iteration_center:v1"
    assert detail["asset_id"] == "asset:self_iteration_center:v1"
    assert len(detail["methods"]) == 3
