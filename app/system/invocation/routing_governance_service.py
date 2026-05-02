from __future__ import annotations

from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.routing_registry import (
    AssetAliasRecord,
    AssetCapabilityTagRecord,
    EndpointRegistryRecord,
    InvocationRoutingRegistry,
    RuntimeRegistryRecord,
)


class RoutingGovernanceService:
    def __init__(
        self,
        *,
        asset_center: AssetCenterService,
        runtime_center: RuntimeCenter,
        registry: InvocationRoutingRegistry | None = None,
    ) -> None:
        self._asset_center = asset_center
        self._runtime_center = runtime_center
        self._registry = registry or InvocationRoutingRegistry()

    @property
    def registry(self) -> InvocationRoutingRegistry:
        return self._registry

    def register_alias(self, alias: str, asset_id: str, *, priority: int = 100) -> AssetAliasRecord:
        return self._registry.register_alias(AssetAliasRecord(alias=alias, asset_id=asset_id, priority=priority))

    def register_capability_tag(self, asset_id: str, tag: str) -> AssetCapabilityTagRecord:
        return self._registry.register_capability_tag(AssetCapabilityTagRecord(asset_id=asset_id, tag=tag))

    def register_runtime_target(self, target_id: str, runtime_id: str, *, status: str = "active", health: str = "unknown") -> RuntimeRegistryRecord:
        return self._registry.register_runtime(RuntimeRegistryRecord(target_id=target_id, runtime_id=runtime_id, status=status, health=health))

    def register_endpoint_target(self, target_id: str, endpoint: str, *, status: str = "active", health: str = "unknown") -> EndpointRegistryRecord:
        return self._registry.register_endpoint(EndpointRegistryRecord(target_id=target_id, endpoint=endpoint, status=status, health=health))

    def resolve_target_id(self, query: str) -> str:
        descriptors = [self._asset_center.registry.require_asset(item["asset_id"]) for item in self._asset_center.list_assets()]
        return self._registry.resolve_target_id(query, descriptors)

    def resolve_route(self, query: str) -> dict[str, object]:
        target_id = self.resolve_target_id(query)
        runtime = self._registry.get_runtime(target_id)
        endpoint = self._registry.get_endpoint(target_id)
        runtime_asset = self._runtime_center.get(target_id)
        return {
            "target_id": target_id,
            "runtime": None if runtime is None else runtime.__dict__,
            "endpoint": None if endpoint is None else endpoint.__dict__,
            "runtime_asset": None if runtime_asset is None else runtime_asset.model_dump(mode="json"),
        }
