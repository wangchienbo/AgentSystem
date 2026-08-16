from __future__ import annotations

import pytest

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.interaction_runtime.context_assembly import (
    InteractionContextSnapshot,
    build_initial_interaction_context,
)
from app.system.interaction_runtime.decision_protocol import (
    DecisionProtocol,
    InteractionDecisionProtocolError,
)


def test_decision_protocol_accepts_three_branch_envelope() -> None:
    protocol = DecisionProtocol()

    text_result = protocol.normalize(InteractionDecisionEnvelope(decision="text", text="ok"))
    detail_result = protocol.normalize(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1")
    )
    retrieval_result = protocol.normalize(
        InteractionDecisionEnvelope(
            decision="request_context_retrieval",
            needed_context_detail_ids=("detail:sess-1:1",),
            needed_more_context_summary_query="recent implementation work",
            needed_asset_detail_ids=("asset:self_iteration_center:v1",),
            needed_more_asset_summary_query="self iteration assets",
        )
    )
    invoke_result = protocol.normalize(
        InteractionDecisionEnvelope(
            decision="invoke",
            invoke={"asset_id": "asset:self_iteration_center:v1", "method": "list_self_iteration_assets", "params": {}},
        )
    )

    assert text_result.resolved_action == "reply_text"
    assert detail_result.resolved_action == "load_detail"
    assert retrieval_result.resolved_action == "load_context_retrieval"
    assert invoke_result.resolved_action == "invoke_method"


def test_decision_protocol_retrieval_request_requires_payload() -> None:
    with pytest.raises(ValueError):
        InteractionDecisionEnvelope(decision="request_context_retrieval").validate()


    protocol = DecisionProtocol()
    with pytest.raises(InteractionDecisionProtocolError):
        protocol.resolve_against_context(
            InteractionDecisionEnvelope(decision="invoke", invoke={"asset_id": "asset:self_iteration_center:v1"}),
            InteractionContextSnapshot(),
        )


def test_decision_protocol_handles_detail_cache_hit() -> None:
    protocol = DecisionProtocol()
    context = InteractionContextSnapshot(
        details={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1"}
        },
        _summary_index={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1"}
        },
    )

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1"),
        context,
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.metadata["detail_cache_hit"] is True


def test_decision_protocol_handles_stale_detail_request_by_reloading() -> None:
    protocol = DecisionProtocol()
    context = InteractionContextSnapshot(
        summaries=[{"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 3}],
        details={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 2}
        },
        _summary_index={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 3}
        },
    )

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1"),
        context,
    )

    assert result.resolved_action == "load_detail"
    assert result.envelope.metadata["detail_cache_stale"] is True
    assert result.envelope.metadata["detail_epoch"] == 2
    assert result.envelope.metadata["summary_epoch"] == 3


def test_decision_protocol_handles_missing_asset_detail_request() -> None:
    protocol = DecisionProtocol()
    context = InteractionContextSnapshot()

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:not_found:v1"),
        context,
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.metadata["missing_asset_detail"] is True


def test_initial_interaction_context_can_preload_details() -> None:
    context = build_initial_interaction_context(
        asset_summaries=[{"asset_id": "asset:self_iteration_center:v1"}],
        preload_detail_ids=["asset:self_iteration_center:v1"],
        detail_provider=lambda asset_id: {"asset_id": asset_id, "detail_level": "expanded"},
    )

    # build_initial_interaction_context populates details and metadata, but summaries list only
    # (summary_index is built separately when context_assembly.refresh is called)
    assert context.has_detail("asset:self_iteration_center:v1") is True
    assert context.metadata["preloaded_detail_ids"] == ["asset:self_iteration_center:v1"]

