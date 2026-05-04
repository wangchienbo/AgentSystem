from __future__ import annotations

from app.models.context import SessionContextRecord, SessionNode
from app.services.context_center import ContextCenter
from app.system.invocation.context_bundle_assembly import ContextBundleAssemblyService
from app.system.invocation.tool_context_contract import ToolContextQueryRequest
from app.system.invocation.tool_context_runtime import ToolContextRuntime


def _seed_center() -> ContextCenter:
    center = ContextCenter()
    center.register_session_node(SessionNode(session_id="sess-1", user_id="u1", channel="test"))
    center.register_asset_local_session("asset:demo:v1", "local-1", "sess-1")
    center.append_context(SessionContextRecord(session_id="sess-1", kind="summary", role="system", content="summary-1"))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="message", role="user", content="msg-1"))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="message", role="assistant", content="msg-2"))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="system_note", role="system", content="snapshot", metadata={"snapshot": True}))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="tool_result", role="tool", content="evidence", metadata={"evidence_ref": "ev-1"}))
    return center


def test_context_bundle_assembly_prefers_summary_under_budget() -> None:
    center = _seed_center()
    service = ContextBundleAssemblyService(center, per_record_token_estimate=50)

    bundle = service.assemble(
        request=ToolContextQueryRequest(
            asset_id="asset:demo:v1",
            local_session_id="local-1",
            recent_limit=5,
        ),
        token_budget=100,
        summary_first=True,
    )

    assert len(bundle.summary) == 1
    assert bundle.recent == [] or bundle.dropped_sections
    assert bundle.token_estimate <= 100


def test_context_bundle_assembly_can_prioritize_recent_when_requested() -> None:
    center = _seed_center()
    service = ContextBundleAssemblyService(center, per_record_token_estimate=50)

    bundle = service.assemble(
        request=ToolContextQueryRequest(
            asset_id="asset:demo:v1",
            local_session_id="local-1",
            recent_limit=2,
        ),
        token_budget=100,
        summary_first=False,
    )

    assert len(bundle.recent) >= 1
    assert bundle.trace_metadata["summary_first"] is False


def test_tool_context_runtime_only_uses_resolved_local_session_inputs() -> None:
    center = _seed_center()
    assembly = ContextBundleAssemblyService(center, per_record_token_estimate=50)
    runtime = ToolContextRuntime(center, assembly)

    bundle = runtime.assemble_for_model(
        asset_id="asset:demo:v1",
        local_session_id="local-1",
        query="hello",
        token_budget=150,
        recent_limit=3,
    )
    record = runtime.record_model_result(
        request_id="req-1",
        asset_id="asset:demo:v1",
        local_session_id="local-1",
        model_id="gpt-5.4",
        context_refs=[item.get("record_id", f"summary:{index}") for index, item in enumerate(bundle["summary"], start=1)] + [item["record_id"] for item in bundle["recent"]],
        token_usage={"input": 100, "output": 20},
        output_summary="done",
    )

    assert bundle["local_session_id"] == "local-1"
    assert bundle["asset_id"] == "asset:demo:v1"
    assert record["local_session_id"] == "local-1"
    assert center.list_model_invocations(asset_id="asset:demo:v1", local_session_id="local-1")[0]["request_id"] == "req-1"
