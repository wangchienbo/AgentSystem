from __future__ import annotations

from app.services.context_compaction import ContextCompactionService
from app.services.log_evidence_service import LogEvidenceService


class PromptSelectionService:
    def __init__(
        self,
        context_compaction: ContextCompactionService,
        log_evidence: LogEvidenceService,
    ) -> None:
        self._context_compaction = context_compaction
        self._log_evidence = log_evidence

    def select_for_prompt(self, app_instance_id: str, limit: int = 5) -> dict:
        working_set = self._context_compaction.build_working_set(app_instance_id).model_dump(mode="json")
        evidence = self._log_evidence.list_index_entries(limit=limit, app_instance_id=app_instance_id)
        selected = [
            {
                "source_type": item.source_type,
                "source_id": item.source_id,
                "topic": item.topic,
                "summary": item.short_summary,
                "priority": item.priority,
                "scope_key": item.scope_key,
            }
            for item in evidence.items
        ]
        return {
            "app_instance_id": app_instance_id,
            "working_set": working_set,
            "selected_evidence": selected,
            "selection_policy": {
                "prefer_promoted_index_entries": True,
                "max_evidence_items": limit,
                "avoid_raw_history": True,
            },
        }

    def search_evidence(
        self,
        *,
        query: str = "",
        app_instance_id: str | None = None,
        category: str | None = None,
        limit: int = 5,
    ) -> dict:
        page = self._log_evidence.search_index(
            query=query,
            app_instance_id=app_instance_id,
            category=category,
            limit=limit,
        )
        return page.model_dump(mode="json")
