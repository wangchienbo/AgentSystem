from __future__ import annotations

import pytest

from app.system.asset_center.bootstrap import bootstrap_asset_center
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, AssetModelRequirement
from app.system.asset_center.registry import AssetCenterRegistry, AssetDescriptorValidationError
from app.system.asset_center.service import AssetCenterService


def test_bootstrap_asset_center_registers_self_descriptor() -> None:
    service = bootstrap_asset_center()

    assets = service.list_assets()
    assert assets == [
        {
            "asset_id": "asset:asset_center:v1",
            "kind": "system_asset",
            "summary": "Central metadata registry for runtime asset descriptors",
            "descriptor_version": 1,
        }
    ]

    detail = service.get_asset_detail("asset:asset_center:v1")
    assert detail["asset_id"] == "asset:asset_center:v1"
    assert detail["descriptor_version"] == 1


def test_asset_center_registry_registers_descriptor_and_reads_model_requirement() -> None:
    registry = AssetCenterRegistry()
    descriptor = AssetDescriptorRecord(
        descriptor_version=1,
        asset_id="asset:self_iteration_center:v1",
        kind="system_asset",
        summary="Self iteration asset",
        detail="Provides strategy overview and evidence inspection.",
        methods=(
            AssetMethodSpec(
                name="strategy_overview",
                description="Return strategy overview",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
        ),
        model_requirement=AssetModelRequirement(
            preferred_model="gpt-5.4",
            fallback_model="gpt-4.1",
            minimum_requirements={"structured_output": True},
        ),
    )

    registry.register_asset(descriptor)

    assert registry.get_asset_detail("asset:self_iteration_center:v1") == "Provides strategy overview and evidence inspection."
    requirement = registry.get_asset_model_requirement("asset:self_iteration_center:v1")
    assert requirement.preferred_model == "gpt-5.4"
    assert requirement.fallback_model == "gpt-4.1"


def test_asset_center_registry_rejects_invalid_descriptor() -> None:
    registry = AssetCenterRegistry()
    descriptor = AssetDescriptorRecord(
        descriptor_version=0,
        asset_id="asset:bad:v1",
        kind="system_asset",
        summary="bad",
        detail="bad",
    )

    with pytest.raises(AssetDescriptorValidationError):
        registry.register_asset(descriptor)


def test_asset_center_service_returns_detail_payload() -> None:
    registry = AssetCenterRegistry()
    service = AssetCenterService(registry=registry)
    descriptor = AssetDescriptorRecord(
        descriptor_version=1,
        asset_id="asset:demo:v1",
        kind="demo_asset",
        summary="Demo asset",
        detail="Detailed demo description",
    )
    service.register_asset(descriptor)

    detail = service.get_asset_detail("asset:demo:v1")
    assert detail["asset_id"] == "asset:demo:v1"
    assert detail["summary"] == "Demo asset"
    assert detail["detail"] == "Detailed demo description"
