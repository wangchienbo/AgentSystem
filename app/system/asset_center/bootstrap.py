from __future__ import annotations

from app.system.asset_center.models import AssetDescriptorRecord
from app.system.asset_center.service import AssetCenterService

ASSET_CENTER_DESCRIPTOR = AssetDescriptorRecord(
    descriptor_version=1,
    asset_id="asset:asset_center:v1",
    kind="system_asset",
    summary="Central metadata registry for runtime asset descriptors",
    detail=(
        "Provides the authoritative runtime metadata entry for asset summaries, details, "
        "method specs, and model requirements. Does not execute business logic."
    ),
    methods=(),
)


def bootstrap_asset_center() -> AssetCenterService:
    service = AssetCenterService()
    service.register_asset(ASSET_CENTER_DESCRIPTOR)
    return service
