from __future__ import annotations

from app.system.asset_center.service import AssetCenterService
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope, InvocationSessionRef
from app.system.invocation.runtime_layer import AssetInvocationRuntimeLayer


def _build_envelope() -> InvocationRequestEnvelope:
    return InvocationRequestEnvelope(
        request_id="req-1",
        target_id="asset:demo:v1",
        target_type="system_asset",
        method="run",
        args={"x": 1},
        session=InvocationSessionRef(
            upstream_session_id="upstream-1",
            root_session_id="root-1",
            parent_session_id="parent-1",
        ),
    )


def test_runtime_layer_creates_and_persists_new_binding() -> None:
    service = AssetCenterService()
    layer = AssetInvocationRuntimeLayer(asset_center=service)
    resolution = layer.before_invoke(_build_envelope())

    assert resolution.mode == "new"
    assert resolution.local_session_id.startswith("asset:demo:v1:")
    persisted = service.get_session_binding("asset:demo:v1", "upstream-1")
    assert persisted is not None
    assert persisted.local_session_id == resolution.local_session_id


def test_runtime_layer_hits_memory_cache_after_first_resolution() -> None:
    service = AssetCenterService()
    layer = AssetInvocationRuntimeLayer(asset_center=service)
    envelope = _build_envelope()

    first = layer.before_invoke(envelope)
    second = layer.before_invoke(envelope)

    assert first.local_session_id == second.local_session_id
    assert second.mode == "memory"


def test_runtime_layer_uses_persisted_binding_for_new_instance() -> None:
    service = AssetCenterService()
    first = AssetInvocationRuntimeLayer(asset_center=service)
    second = AssetInvocationRuntimeLayer(asset_center=service)
    envelope = _build_envelope()

    initial = first.before_invoke(envelope)
    restored = second.before_invoke(envelope)

    assert restored.local_session_id == initial.local_session_id
    assert restored.mode == "persisted"


def test_runtime_layer_uses_historical_resolver_when_present() -> None:
    service = AssetCenterService()
    layer = AssetInvocationRuntimeLayer(
        asset_center=service,
        historical_session_resolver=lambda envelope: "recovered-local-1",
    )

    resolution = layer.before_invoke(_build_envelope())

    assert resolution.mode == "recovered_by_history"
    assert resolution.local_session_id == "recovered-local-1"


def test_runtime_layer_after_invoke_attaches_binding_metadata() -> None:
    service = AssetCenterService()
    layer = AssetInvocationRuntimeLayer(asset_center=service)
    envelope = _build_envelope()
    resolution = layer.before_invoke(envelope)
    response = InvocationResponseEnvelope(ok=True, request_id="req-1", data={"ok": True})

    wrapped = layer.after_invoke(envelope, response, resolution)

    assert wrapped.resolved_local_session_id == resolution.local_session_id
    assert wrapped.metadata["binding"]["mode"] in {"new", "memory", "persisted", "recovered_by_history"}
