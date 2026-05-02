from __future__ import annotations

from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationSessionRef
from app.system.invocation.runtime_layer import AssetInvocationRuntimeLayer


def test_runtime_center_invoke_asset_envelope_uses_runtime_layer(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime-center.json"))
    runtime_layer = AssetInvocationRuntimeLayer(asset_center=asset_center)
    runtime_center.register_invocation_runtime_layer(runtime_layer)

    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:demo:v1",
            kind="system_asset",
            summary="Demo",
            detail="Demo asset",
            methods=(
                AssetMethodSpec(
                    name="run",
                    description="Run",
                    input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
                ),
            ),
        )
    )
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:demo:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.CORE_RUNTIME,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[AssetCapability(name="run", description="Run", method="run", side_effect_level="read")],
            invoke_contract={"kind": "service"},
            health_contract={"heartbeat": False},
            name="demo",
            description="Demo",
        ),
        method_mappings={
            "run": lambda x=None, local_session_id=None, __invocation_envelope__=None: {
                "x": x,
                "local_session_id": local_session_id,
                "request_id": None if __invocation_envelope__ is None else __invocation_envelope__.request_id,
            }
        },
    )

    envelope = InvocationRequestEnvelope(
        request_id="req-1",
        target_id="asset:demo:v1",
        target_type="system_asset",
        method="run",
        args={"x": 3},
        session=InvocationSessionRef(upstream_session_id="up-1", root_session_id="root-1"),
    )

    response = runtime_center.invoke_asset_envelope(envelope)

    assert response.ok is True
    assert response.resolved_local_session_id is not None
    assert response.data["local_session_id"] == response.resolved_local_session_id
    assert response.data["request_id"] == "req-1"
    assert response.metadata["binding"]["mode"] == "new"
