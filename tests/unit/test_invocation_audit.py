from __future__ import annotations

from app.system.invocation.invocation_audit import InvocationAuditRecord, InvocationAuditStore
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope, InvocationSessionRef


def _make_envelope(request_id: str = "req-audit-1", target_id: str = "asset:test:v1", method: str = "run") -> InvocationRequestEnvelope:
    return InvocationRequestEnvelope(
        request_id=request_id,
        target_id=target_id,
        target_type="system_asset",
        method=method,
        session=InvocationSessionRef(upstream_session_id="up-1", root_session_id="root-1"),
    )


def _make_response(request_id: str = "req-audit-1", ok: bool = True) -> InvocationResponseEnvelope:
    return InvocationResponseEnvelope(
        ok=ok,
        request_id=request_id,
        data={"result": "done"},
    )


def test_audit_record_is_frozen() -> None:
    record = InvocationAuditRecord(
        request_id="req-1",
        target_id="asset:a:v1",
        method="run",
        request_envelope={"request_id": "req-1"},
    )
    assert record.request_id == "req-1"


def test_audit_store_record_and_list() -> None:
    store = InvocationAuditStore()
    envelope = _make_envelope()
    response = _make_response()

    record = store.record(
        envelope=envelope,
        response=response,
        binding_resolution_mode="new",
        resolved_local_session_id="asset:test:v1:local-1",
    )

    assert record.request_id == "req-audit-1"
    assert record.binding_resolution_mode == "new"
    assert record.resolved_local_session_id == "asset:test:v1:local-1"
    assert len(store.list_records()) == 1


def test_audit_store_record_without_response() -> None:
    store = InvocationAuditStore()
    envelope = _make_envelope("req-no-resp")

    record = store.record(
        envelope=envelope,
        binding_resolution_mode="new",
    )

    assert record.response == {}
    assert len(store.list_records()) == 1


def test_audit_store_record_with_downstream_links() -> None:
    store = InvocationAuditStore()
    envelope = _make_envelope("req-links")
    downstream = [{"target": "child-asset", "method": "assist"}]
    vllm_links = [{"model": "gpt-4", "tokens": 100}]

    record = store.record(
        envelope=envelope,
        downstream_call_links=downstream,
        tool_vllm_usage_links=vllm_links,
    )

    assert record.downstream_call_links == downstream
    assert record.tool_vllm_usage_links == vllm_links


def test_audit_store_replay_chain() -> None:
    store = InvocationAuditStore()
    envelope = _make_envelope("req-replay")
    response = _make_response("req-replay")

    store.record(
        envelope=envelope,
        response=response,
        binding_resolution_mode="persisted",
        resolved_local_session_id="local-replay",
        downstream_call_links=[{"target": "child"}],
    )

    replay = store.replay_chain("req-replay")

    assert replay["request_id"] == "req-replay"
    assert replay["binding_resolution_mode"] == "persisted"
    assert replay["resolved_local_session_id"] == "local-replay"
    assert len(replay["downstream_call_links"]) == 1
    assert replay["response"]["ok"] is True


def test_audit_store_replay_chain_not_found() -> None:
    store = InvocationAuditStore()
    try:
        store.replay_chain("nonexistent")
        assert False, "should have raised ValueError"
    except ValueError as exc:
        assert "not found" in str(exc)


def test_audit_store_replay_chain_returns_last_record() -> None:
    store = InvocationAuditStore()
    store.record(envelope=_make_envelope("req-dup"), binding_resolution_mode="first")
    store.record(envelope=_make_envelope("req-dup"), binding_resolution_mode="second")

    replay = store.replay_chain("req-dup")
    assert replay["binding_resolution_mode"] == "second"


def test_audit_record_to_dict_round_trip() -> None:
    record = InvocationAuditRecord(
        request_id="req-round",
        target_id="asset:round:v1",
        method="assist",
        request_envelope={"request_id": "req-round"},
        binding_resolution_mode="new",
        downstream_call_links=[{"step": 1}],
    )
    d = {
        "request_id": record.request_id,
        "target_id": record.target_id,
        "method": record.method,
        "binding_resolution_mode": record.binding_resolution_mode,
        "downstream_call_links": record.downstream_call_links,
    }
    assert d["request_id"] == "req-round"
    assert d["method"] == "assist"
