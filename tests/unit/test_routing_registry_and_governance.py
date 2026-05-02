from __future__ import annotations

import pytest

from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.routing_governance_service import RoutingGovernanceService
from app.system.invocation.routing_registry import (
    AssetAliasRecord,
    AssetCapabilityTagRecord,
    AssetIdentityResolutionError,
    EndpointRegistryRecord,
    InvocationRoutingRegistry,
    RuntimeRegistryRecord,
)


def _register_demo_assets(asset_center: AssetCenterService) -> None:
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(AssetMethodSpec(name="get_config", description="Read", input_schema={"type": "object"}),),
        )
    )
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:novel_app:v1",
            kind="app",
            summary="Novel writing app",
            detail="Novel generation",
            methods=(AssetMethodSpec(name="generate", description="Generate", input_schema={"type": "object"}),),
        )
    )


def test_routing_registry_resolves_by_alias_and_tag() -> None:
    asset_center = AssetCenterService()
    _register_demo_assets(asset_center)
    registry = InvocationRoutingRegistry()
    registry.register_alias(AssetAliasRecord(alias="config", asset_id="asset:config_center:v1", priority=10))
    registry.register_capability_tag(AssetCapabilityTagRecord(asset_id="asset:novel_app:v1", tag="novel"))

    descriptors = [asset_center.registry.require_asset("asset:config_center:v1"), asset_center.registry.require_asset("asset:novel_app:v1")]
    assert registry.resolve_target_id("config", descriptors) == "asset:config_center:v1"
    assert registry.resolve_target_id("novel", descriptors) == "asset:novel_app:v1"


def test_routing_registry_detects_ambiguous_alias() -> None:
    asset_center = AssetCenterService()
    _register_demo_assets(asset_center)
    registry = InvocationRoutingRegistry()
    registry.register_alias(AssetAliasRecord(alias="common", asset_id="asset:config_center:v1", priority=10))
    registry.register_alias(AssetAliasRecord(alias="common", asset_id="asset:novel_app:v1", priority=10))
    descriptors = [asset_center.registry.require_asset("asset:config_center:v1"), asset_center.registry.require_asset("asset:novel_app:v1")]

    with pytest.raises(AssetIdentityResolutionError, match="ambiguous alias"):
        registry.resolve_target_id("common", descriptors)


def test_runtime_and_endpoint_registry_lookup() -> None:
    registry = InvocationRoutingRegistry()
    registry.register_runtime(RuntimeRegistryRecord(target_id="asset:config_center:v1", runtime_id="runtime-1", health="healthy"))
    registry.register_endpoint(EndpointRegistryRecord(target_id="asset:config_center:v1", endpoint="http://127.0.0.1:8001", health="healthy"))

    assert registry.get_runtime("asset:config_center:v1").runtime_id == "runtime-1"
    assert registry.get_endpoint("asset:config_center:v1").endpoint.endswith(":8001")


def test_routing_governance_service_resolves_route(tmp_path) -> None:
    asset_center = AssetCenterService()
    _register_demo_assets(asset_center)
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime-center.json"))
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:config_center:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.CORE_RUNTIME,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[AssetCapability(name="get config", description="Read", method="get_config", side_effect_level="read")],
            invoke_contract={"kind": "service"},
            health_contract={"heartbeat": False},
            name="config_center",
            description="Config center",
        )
    )

    service = RoutingGovernanceService(asset_center=asset_center, runtime_center=runtime_center)
    service.register_alias("config", "asset:config_center:v1")
    service.register_runtime_target("asset:config_center:v1", "runtime-1", health="healthy")
    service.register_endpoint_target("asset:config_center:v1", "http://127.0.0.1:8001", health="healthy")

    route = service.resolve_route("config")

    assert route["target_id"] == "asset:config_center:v1"
    assert route["runtime"]["runtime_id"] == "runtime-1"
    assert route["endpoint"]["endpoint"].endswith(":8001")
    assert route["runtime_asset"]["asset_id"] == "asset:config_center:v1"
