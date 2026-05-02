from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.context_center import ContextCenter
from app.system.invocation.tool_context_contract import ToolContextQueryRequest


@dataclass(frozen=True)
class ContextBundle:
    asset_id: str
    local_session_id: str
    summary: list[dict[str, Any]] = field(default_factory=list)
    recent: list[dict[str, Any]] = field(default_factory=list)
    snapshot: dict[str, Any] | None = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    token_budget: int = 0
    token_estimate: int = 0
    dropped_sections: list[str] = field(default_factory=list)
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "local_session_id": self.local_session_id,
            "summary": self.summary,
            "recent": self.recent,
            "snapshot": self.snapshot,
            "evidence_refs": self.evidence_refs,
            "token_budget": self.token_budget,
            "token_estimate": self.token_estimate,
            "dropped_sections": self.dropped_sections,
            "trace_metadata": self.trace_metadata,
        }


class ContextBundleAssemblyService:
    def __init__(self, context_center: ContextCenter, *, per_record_token_estimate: int = 80) -> None:
        self._context_center = context_center
        self._per_record_token_estimate = per_record_token_estimate

    def assemble(
        self,
        request: ToolContextQueryRequest,
        *,
        token_budget: int,
        summary_first: bool = True,
    ) -> ContextBundle:
        request.validate()
        response = self._context_center.assemble_tool_context(request)
        sections: list[tuple[str, list[dict[str, Any]]]] = []
        dropped: list[str] = []

        summary_records = list(response.summary_records)
        recent_records = list(response.recent_records)
        evidence_records = list(response.evidence_refs)
        snapshot_records = [] if response.snapshot_record is None else [response.snapshot_record]

        if summary_first:
            sections.extend([
                ("summary", summary_records),
                ("snapshot", snapshot_records),
                ("evidence_refs", evidence_records),
                ("recent", recent_records),
            ])
        else:
            sections.extend([
                ("recent", recent_records),
                ("summary", summary_records),
                ("snapshot", snapshot_records),
                ("evidence_refs", evidence_records),
            ])

        budget_left = max(token_budget, 0)
        selected: dict[str, list[dict[str, Any]]] = {"summary": [], "recent": [], "snapshot": [], "evidence_refs": []}
        for section_name, items in sections:
            kept: list[dict[str, Any]] = []
            for item in items:
                if budget_left < self._per_record_token_estimate:
                    dropped.append(section_name)
                    break
                kept.append(item)
                budget_left -= self._per_record_token_estimate
            selected[section_name] = kept
            if len(kept) < len(items) and section_name not in dropped:
                dropped.append(section_name)

        token_estimate = (sum(len(items) for items in selected.values())) * self._per_record_token_estimate
        return ContextBundle(
            asset_id=request.asset_id,
            local_session_id=request.local_session_id,
            summary=selected["summary"],
            recent=selected["recent"],
            snapshot=selected["snapshot"][0] if selected["snapshot"] else None,
            evidence_refs=selected["evidence_refs"],
            token_budget=token_budget,
            token_estimate=token_estimate,
            dropped_sections=dropped,
            trace_metadata={
                **response.trace_metadata,
                "summary_first": summary_first,
                "per_record_token_estimate": self._per_record_token_estimate,
            },
        )
