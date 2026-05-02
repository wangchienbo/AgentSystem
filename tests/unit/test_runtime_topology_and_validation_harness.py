from __future__ import annotations

from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
from app.models.context import SessionNode
from app.services.context_center import ContextCenter
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, AssetSessionBindingRecord
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.invocation_audit import InvocationAuditStore
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope, InvocationSessionRef
from app.system.invocation.routing_governance_service import RoutingGovernanceService
from app.system.invocation.runtime_topology import RuntimeTopologyReadModel
from app.system.invocation.validation_harness import InvocationValidationHarness


def test_runtime_topology_read_model_and_validation_harness(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime-center.json"))
    context_center = ContextCenter()

    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(AssetMethodSpec(name="get_config", description="Read", input_schema={"type": "object"}),),
            metadata={
                "invocation_contract_version": "phase-p-v1",
                "runtime_wrapper_compatibility": True,
                "session_binding_support": "supported",
            },
        )
    )
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
        ),
        method_mappings={"get_config": lambda: {"ok": True}},
    )
    binding = asset_center.upsert_session_binding(
        AssetSessionBindingRecord(
            asset_id="asset:config_center:v1",
            upstream_session_id="up-1",
            local_session_id="local-1",
            metadata={"request_id": "req-1"},
        )
    )
    session = context_center.register_session_node(
        SessionNode(session_id="local-1", kind="child", user_id="tester", channel="unit", topic_key="config session")
    )
    session.status = "active"
    context_center.register_asset_local_session("asset:config_center:v1", "local-1")

    routing = RoutingGovernanceService(asset_center=asset_center, runtime_center=runtime_center)
    routing.register_runtime_target("asset:config_center:v1", "runtime-1", health="healthy")
    routing.register_endpoint_target("asset:config_center:v1", "http://127.0.0.1:28001", health="healthy")

    topology = RuntimeTopologyReadModel(
        asset_center=asset_center,
        runtime_center=runtime_center,
        context_center=context_center,
        routing_governance=routing,
    )
    audit = InvocationAuditStore()
    harness = InvocationValidationHarness(topology=topology, audit_store=audit)

    envelope = InvocationRequestEnvelope(
        request_id="req-1",
        target_id="asset:config_center:v1",
        target_type="system_asset",
        method="get_config",
        session=InvocationSessionRef(upstream_session_id="up-1", root_session_id="root-1"),
    )
    response = InvocationResponseEnvelope(ok=True, request_id="req-1", data={"ok": True}, resolved_local_session_id=binding.local_session_id)

    result = harness.validate_invocation_chain(
        envelope=envelope,
        response=response,
        binding_resolution_mode="persisted",
        resolved_local_session_id="local-1",
        downstream_call_links=[{"from": "asset:config_center:v1", "to": "http://127.0.0.1:28001"}],
        tool_vllm_usage_links=[{"mode": "local_session_only", "asset_id": "asset:config_center:v1"}],
    )

    assert result.topology["assets"][0]["asset_id"] == "asset:config_center:v1"
    assert result.topology["bindings"][0]["local_session_id"] == "local-1"
    assert result.topology["sessions"][0]["session_id"] == session.session_id
    assert result.topology["downstream_edges"][0]["runtime_id"] == "runtime-1"
    assert result.replay["binding_resolution_mode"] == "persisted"
    assert result.replay["downstream_call_links"][0]["to"].endswith(":28001")
    assert result.replay["tool_vllm_usage_links"][0]["mode"] == "local_session_only"
