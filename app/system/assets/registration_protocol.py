from __future__ import annotations

from app.system.asset_center.service import AssetCenterService
from app.system.assets.base_asset import BaseAsset, RegisteredAsset


class AssetRegistrationProtocol:
    def materialize(self, asset: BaseAsset) -> RegisteredAsset:
        descriptor = asset.build_descriptor()
        method_mappings = asset.build_method_mappings()
        service_ref = asset.get_service_ref()
        return RegisteredAsset(
            descriptor=descriptor,
            service_ref=service_ref,
            method_mappings=method_mappings,
        )

    def register(self, asset: BaseAsset, asset_center: AssetCenterService) -> RegisteredAsset:
        registered = self.materialize(asset)
        asset_center.register_asset(registered.descriptor)
        return registered
