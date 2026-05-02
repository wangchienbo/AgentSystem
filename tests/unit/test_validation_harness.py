from __future__ import annotations

from app.services.context_center import ContextCenter
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.invocation_audit import InvocationAuditStore
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope, InvocationSessionRef
from app.system.invocation.runtime_topology import RuntimeTopologyReadModel
from app.system.invocation.validation_harness import InvocationValidationHarness, ValidationHarnessResult


def _make_envelope(request_id: str = "req-harness-1") -> InvocationRequestEnvelope:
    return InvocationRequestEnvelope(
        request_id=request_id,
        target_id="asset:test:v1",
        target_type="system_asset",
        method="run",
        session=InvocationSessionRef(upstream_session_id="up-h", root_session_id="root-h"),
    )


def _make_response(request_id: str = "req-harness-1") -> InvocationResponseEnvelope:
    return InvocationResponseEnvelope(
        ok=True,
        request_id=request_id,
        data={"result": "ok"},
    )


def test_harness_records_and_returns_topology(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime.json"))
    context_center = ContextCenter()
    audit_store = InvocationAuditStore()

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

    topology = RuntimeTopologyReadModel(
        asset_center=asset_center,
        runtime_center=runtime_center,
        context_center=context_center,
    )
    harness = InvocationValidationHarness(topology=topology, audit_store=audit_store)

    envelope = _make_envelope("req-topo")
    response = _make_response("req-topo")

    result = harness.validate_invocation_chain(
        envelope=envelope,
        response=response,
        binding_resolution_mode="new",
        resolved_local_session_id="local-harness",
    )

    assert isinstance(result, ValidationHarnessResult)
    assert "assets" in result.topology
    assert len(result.topology["assets"]) == 1
    assert result.replay["request_id"] == "req-topo"


def test_harness_downstream_links_in_replay(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime.json"))
    context_center = ContextCenter()
    audit_store = InvocationAuditStore()

    topology = RuntimeTopologyReadModel(
        asset_center=asset_center,
        runtime_center=runtime_center,
        context_center=context_center,
    )
    harness = InvocationValidationHarness(topology=topology, audit_store=audit_store)

    envelope = _make_envelope("req-links")
    response = _make_response("req-links")
    downstream = [{"target": "asset:child:v1", "method": "assist"}]
    vllm = [{"model": "gpt-4", "tokens": 200}]

    result = harness.validate_invocation_chain(
        envelope=envelope,
        response=response,
        binding_resolution_mode="persisted",
        resolved_local_session_id="local-links",
        downstream_call_links=downstream,
        tool_vllm_usage_links=vllm,
    )

    assert len(result.replay["downstream_call_links"]) == 1
    assert len(result.replay["tool_vllm_usage_links"]) == 1
    assert result.replay["binding_resolution_mode"] == "persisted"


def test_harness_topology_contains_runtime_assets(tmp_path) -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime.json"))
    context_center = ContextCenter()
    audit_store = InvocationAuditStore()

    from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:rt:v1",
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
            name="rt",
            description="rt",
        ),
        method_mappings={"run": lambda: {"ok": True}},
    )

    topology = RuntimeTopologyReadModel(
        asset_center=asset_center,
        runtime_center=runtime_center,
        context_center=context_center,
    )
    harness = InvocationValidationHarness(topology=topology, audit_store=audit_store)

    result = harness.validate_invocation_chain(
        envelope=_make_envelope("req-rt"),
        response=_make_response("req-rt"),
        binding_resolution_mode="new",
        resolved_local_session_id="local-rt",
    )

    assert len(result.topology["runtime_assets"]) >= 1


def test_harness_multiple_invocations_accumulate() -> None:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter()
    context_center = ContextCenter()
    audit_store = InvocationAuditStore()

    topology = RuntimeTopologyReadModel(
        asset_center=asset_center,
        runtime_center=runtime_center,
        context_center=context_center,
    )
    harness = InvocationValidationHarness(topology=topology, audit_store=audit_store)

    harness.validate_invocation_chain(
        envelope=_make_envelope("req-1"),
        response=_make_response("req-1"),
        binding_resolution_mode="new",
        resolved_local_session_id="local-1",
    )
    harness.validate_invocation_chain(
        envelope=_make_envelope("req-2"),
        response=_make_response("req-2"),
        binding_resolution_mode="persisted",
        resolved_local_session_id="local-2",
    )

    assert len(audit_store.list_records()) == 2

    replay_1 = audit_store.replay_chain("req-1")
    replay_2 = audit_store.replay_chain("req-2")
    assert replay_1["resolved_local_session_id"] == "local-1"
    assert replay_2["resolved_local_session_id"] == "local-2"
