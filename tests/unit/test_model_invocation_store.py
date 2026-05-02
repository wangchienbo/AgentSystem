from __future__ import annotations

from app.system.invocation.model_invocation_store import ModelInvocationStore
from app.system.invocation.tool_context_contract import ModelInvocationRecord


def _make_record(request_id: str, asset_id: str = "asset:a:v1", local_session_id: str = "sess-1", prompt_tokens: int = 100, completion_tokens: int = 50) -> ModelInvocationRecord:
    return ModelInvocationRecord(
        request_id=request_id,
        asset_id=asset_id,
        local_session_id=local_session_id,
        model_id="gpt-4",
        context_refs=["ref-1"],
        token_usage={"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        output_summary="ok",
    )


def test_record_and_retrieve() -> None:
    store = ModelInvocationStore()
    r = _make_record("req-1")
    store.record(r)
    assert store.get_by_request_id("req-1") is r
    assert store.get_by_request_id("nope") is None


def test_list_by_session() -> None:
    store = ModelInvocationStore()
    store.record(_make_record("req-1"))
    store.record(_make_record("req-2"))
    store.record(_make_record("req-3", asset_id="asset:b:v1"))
    results = store.list_by_session("asset:a:v1", "sess-1")
    assert len(results) == 2


def test_aggregate_token_usage() -> None:
    store = ModelInvocationStore()
    store.record(_make_record("req-1", prompt_tokens=100, completion_tokens=50))
    store.record(_make_record("req-2", prompt_tokens=200, completion_tokens=100))
    agg = store.aggregate_token_usage(asset_id="asset:a:v1")
    assert agg["prompt_tokens"] == 300
    assert agg["completion_tokens"] == 150
    assert agg["total_tokens"] == 450
    assert agg["invocation_count"] == 2


def test_dispatcher_records_invocation_when_store_provided(tmp_path) -> None:
    from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec
    from app.system.asset_center.service import AssetCenterService
    from app.system.catalog.runtime_center import RuntimeCenter
    from app.system.invocation.invocation_dispatcher import InvocationDispatcher
    from app.system.invocation.runtime_layer import AssetInvocationRuntimeLayer

    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime.json"))
    store = ModelInvocationStore()
    runtime_layer = AssetInvocationRuntimeLayer(asset_center=asset_center)
    runtime_center.register_invocation_runtime_layer(runtime_layer)

    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:store_test:v1",
            kind="system_asset",
            summary="test",
            detail="test",
            methods=(AssetMethodSpec(name="run", description="run", input_schema={"type": "object"}),),
        )
    )

    from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:store_test:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.SESSION,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[AssetCapability(name="run", description="run", method="run", side_effect_level="read")],
            invoke_contract={"kind": "service"},
            health_contract={"heartbeat": False},
            name="store_test",
            description="store_test",
        ),
        method_mappings={"run": lambda: {"ok": True, "result": "done"}},
    )

    dispatcher = InvocationDispatcher(
        asset_center=asset_center,
        runtime_center=runtime_center,
        invocation_store=store,
        runtime_layer=runtime_layer,
    )
    result = dispatcher.dispatch(asset_id="asset:store_test:v1", method="run", params={})

    local_session_id = result["response_envelope"].get("resolved_local_session_id", "")
    assert local_session_id, "runtime layer should resolve local_session_id"
    records = store.list_by_session("asset:store_test:v1", local_session_id)
    assert len(records) == 1, "dispatcher should record one invocation"
    assert records[0]["model_id"] == ""
