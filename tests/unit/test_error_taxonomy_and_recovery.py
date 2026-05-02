from __future__ import annotations

from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.invocation_dispatcher import InvocationDispatcher
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationSessionRef
from app.system.invocation.runtime_layer import AssetInvocationRuntimeLayer


def test_safe_dispatch_propagates_error_taxonomy() -> None:
    asset_center = AssetCenterService()
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:test:v1",
            kind="system_asset",
            summary="test",
            detail="test",
            methods=(AssetMethodSpec(name="run", description="run", input_schema={"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}),),
        )
    )
    dispatcher = InvocationDispatcher(asset_center=asset_center, runtime_center=RuntimeCenter())

    result = dispatcher.safe_dispatch(asset_id="asset:test:v1", method="run", params={})

    assert result["error_type"] == "params_schema_mismatch"
    assert result["error_taxonomy"]["category"] == "validation"


def test_runtime_layer_multi_hop_session_propagation_and_history_recovery(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime.json"))
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:test:v1",
            kind="system_asset",
            summary="test",
            detail="test",
            methods=(AssetMethodSpec(name="run", description="run", input_schema={"type": "object"}),),
        )
    )
    runtime_center.register_asset_descriptor = None
    layer = AssetInvocationRuntimeLayer(asset_center=asset_center, historical_session_resolver=lambda envelope: "recovered-local-1")
    runtime_center.register_invocation_runtime_layer(layer)

    envelope = InvocationRequestEnvelope(
        request_id="req-1",
        target_id="asset:test:v1",
        target_type="system_asset",
        method="run",
        session=InvocationSessionRef(upstream_session_id="up-1", root_session_id="root-1", parent_session_id="parent-1"),
    )

    resolution = layer.before_invoke(envelope)

    assert resolution.mode == "recovered_by_history"
    assert resolution.binding.root_session_id == "root-1"
    assert resolution.binding.parent_session_id == "parent-1"

    reloaded_layer = AssetInvocationRuntimeLayer(asset_center=asset_center)
    reloaded_resolution = reloaded_layer.before_invoke(envelope)

    assert reloaded_resolution.mode == "persisted"
    assert reloaded_resolution.binding.local_session_id == "recovered-local-1"
