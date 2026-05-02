from __future__ import annotations

from app.services.context_center import ContextCenter
from app.system.invocation.context_bundle_assembly import ContextBundleAssemblyService
from app.system.invocation.tool_context_contract import ModelInvocationRecord, ToolContextQueryRequest


class ToolContextRuntime:
    """Tool/vLLM-side facade that only consumes resolved local session ids."""

    def __init__(self, context_center: ContextCenter, assembly_service: ContextBundleAssemblyService) -> None:
        self._context_center = context_center
        self._assembly_service = assembly_service

    def assemble_for_model(
        self,
        *,
        asset_id: str,
        local_session_id: str,
        query: str = "",
        token_budget: int = 1600,
        recent_limit: int = 20,
        summary_first: bool = True,
    ) -> dict:
        request = ToolContextQueryRequest(
            asset_id=asset_id,
            local_session_id=local_session_id,
            query=query,
            recent_limit=recent_limit,
        )
        bundle = self._assembly_service.assemble(request, token_budget=token_budget, summary_first=summary_first)
        return bundle.to_dict()

    def record_model_result(
        self,
        *,
        request_id: str,
        asset_id: str,
        local_session_id: str,
        model_id: str,
        context_refs: list[str],
        token_usage: dict,
        output_summary: str,
    ) -> dict:
        record = ModelInvocationRecord(
            request_id=request_id,
            asset_id=asset_id,
            local_session_id=local_session_id,
            model_id=model_id,
            context_refs=context_refs,
            token_usage=token_usage,
            output_summary=output_summary,
            trace_metadata={"source": "tool_context_runtime"},
        )
        self._context_center.record_model_invocation(record)
        return record.to_dict()
