from __future__ import annotations

from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, AssetModelRequirement
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.invocation_dispatcher import InvocationDispatcher
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationSessionRef
from app.system.invocation.runtime_layer import AssetInvocationRuntimeLayer
from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


def test_runtime_layer_cache_reload_behavior_uses_persisted_binding(tmp_path) -> None:
    asset_center = AssetCenterService()
    first_layer = AssetInvocationRuntimeLayer(asset_center=asset_center)
    envelope = InvocationRequestEnvelope(
        request_id="req-reload",
        target_id="asset:test:v1",
        target_type="system_asset",
        method="run",
        session=InvocationSessionRef(upstream_session_id="up-reload", root_session_id="root-reload"),
    )

    first = first_layer.before_invoke(envelope)
    second_layer = AssetInvocationRuntimeLayer(asset_center=asset_center)
    second = second_layer.before_invoke(envelope)

    assert first.mode == "new"
    assert second.mode == "persisted"
    assert second.binding.local_session_id == first.binding.local_session_id


def test_representative_llm_assisted_chain_selects_model_and_dispatches() -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter()
    asset_center.register_model(
        ModelRuntimeRecord(
            model_id="gpt-primary",
            provider="openai",
            base_url="https://api.openai.test",
            api_key_env="OPENAI_API_KEY",
            wire_api="responses",
            enabled=True,
            healthy=True,
            role="generation",
            metadata={"quality_tier": 3, "max_output_tokens": 16000},
        )
    )
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:llm_app:v1",
            kind="app",
            summary="LLM app",
            detail="Assist",
            methods=(AssetMethodSpec(name="assist", description="assist", input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}),),
            model_requirement=AssetModelRequirement(preferred_model="gpt-primary"),
        )
    )
    from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:llm_app:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.SESSION,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[AssetCapability(name="assist", description="assist", method="assist", side_effect_level="read")],
            invoke_contract={"kind": "service"},
            health_contract={"heartbeat": False},
            name="llm_app",
            description="LLM app",
        ),
        method_mappings={"assist": lambda prompt=None: {"answer": f"ok:{prompt}"}},
    )

    dispatcher = InvocationDispatcher(asset_center=asset_center, runtime_center=runtime_center)
    result = dispatcher.dispatch(asset_id="asset:llm_app:v1", method="assist", params={"prompt": "hello"})

    assert result["ok"] is True
    assert result["resolved_call"]["resolved_model"]["model_id"] == "gpt-primary"
    assert result["execution"]["result"]["answer"] == "ok:hello"


def test_mixed_multi_hop_chain_preserves_session_relationships(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime.json"))
    runtime_layer = AssetInvocationRuntimeLayer(asset_center=asset_center)
    runtime_center.register_invocation_runtime_layer(runtime_layer)

    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:mixed:v1",
            kind="app",
            summary="Mixed",
            detail="Mixed chain",
            methods=(AssetMethodSpec(name="run", description="run", input_schema={"type": "object"}),),
        )
    )
    from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:mixed:v1",
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
            name="mixed",
            description="mixed",
        ),
        method_mappings={"run": lambda local_session_id=None, __invocation_envelope__=None: {"local_session_id": local_session_id, "request_id": __invocation_envelope__.request_id}},
    )

    dispatcher = InvocationDispatcher(asset_center=asset_center, runtime_center=runtime_center, runtime_layer=runtime_layer)
    result = dispatcher.dispatch_from_envelope(
        InvocationRequestEnvelope(
            request_id="req-mixed",
            target_id="asset:mixed:v1",
            target_type="app",
            method="run",
            session=InvocationSessionRef(upstream_session_id="up-mixed", root_session_id="root-mixed", parent_session_id="parent-mixed"),
        )
    )

    binding = result["response_envelope"]["metadata"]["binding"]["binding"]
    assert binding["root_session_id"] == "root-mixed"
    assert binding["parent_session_id"] == "parent-mixed"
    assert result["response_envelope"]["resolved_local_session_id"] == binding["local_session_id"]
