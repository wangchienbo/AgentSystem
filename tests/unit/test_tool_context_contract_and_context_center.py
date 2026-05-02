from __future__ import annotations

from app.models.context import SessionContextRecord, SessionNode
from app.services.context_center import ContextCenter
from app.system.invocation.tool_context_contract import ModelInvocationRecord, ToolContextQueryRequest


def test_tool_context_query_request_validation() -> None:
    req = ToolContextQueryRequest(asset_id="asset:demo:v1", local_session_id="local-1", recent_limit=3)
    req.validate()
    assert req.to_dict()["asset_id"] == "asset:demo:v1"


def test_context_center_query_surfaces_by_asset_local_session() -> None:
    center = ContextCenter()
    center.register_session_node(SessionNode(session_id="sess-1", user_id="u1", channel="test"))
    center.register_asset_local_session("asset:demo:v1", "local-1", "sess-1")
    center.append_context(
        SessionContextRecord(session_id="sess-1", kind="message", role="user", content="hello")
    )
    center.append_context(
        SessionContextRecord(session_id="sess-1", kind="summary", role="system", content="summary-1")
    )
    center.append_context(
        SessionContextRecord(session_id="sess-1", kind="system_note", role="system", content="snapshot", metadata={"snapshot": True})
    )
    center.append_context(
        SessionContextRecord(session_id="sess-1", kind="tool_result", role="tool", content="evidence", metadata={"evidence_ref": "ev-1"})
    )

    recent = center.query_recent_window("asset:demo:v1", "local-1", limit=2)
    summaries = center.query_summary_records("asset:demo:v1", "local-1")
    snapshot = center.query_snapshot_record("asset:demo:v1", "local-1")
    evidence = center.query_evidence_refs("asset:demo:v1", "local-1")

    assert len(recent) == 2
    assert summaries[-1]["content"] == "summary-1"
    assert snapshot is not None and snapshot["metadata"]["snapshot"] is True
    assert evidence[-1]["metadata"]["evidence_ref"] == "ev-1"


def test_context_center_assembles_tool_context_bundle() -> None:
    center = ContextCenter()
    center.register_session_node(SessionNode(session_id="sess-1", user_id="u1", channel="test"))
    center.register_asset_local_session("asset:demo:v1", "local-1", "sess-1")
    center.append_context(SessionContextRecord(session_id="sess-1", kind="message", role="user", content="hello"))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="summary", role="system", content="summary-1"))

    bundle = center.assemble_tool_context(
        ToolContextQueryRequest(asset_id="asset:demo:v1", local_session_id="local-1", query="hello", recent_limit=5)
    )

    assert bundle.asset_id == "asset:demo:v1"
    assert bundle.local_session_id == "local-1"
    assert bundle.trace_metadata["recent_count"] >= 1
    assert len(bundle.summary_records) == 1


def test_context_center_records_model_invocation() -> None:
    center = ContextCenter()
    center.record_model_invocation(
        ModelInvocationRecord(
            request_id="req-1",
            asset_id="asset:demo:v1",
            local_session_id="local-1",
            model_id="gpt-5.4",
            context_refs=["ctx-1", "ctx-2"],
            token_usage={"input": 120, "output": 40},
            output_summary="done",
        )
    )

    records = center.list_model_invocations(asset_id="asset:demo:v1", local_session_id="local-1")
    assert len(records) == 1
    assert records[0]["token_usage"]["input"] == 120
