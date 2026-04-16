from __future__ import annotations

from app.services.app_context_store import AppContextStore
from app.services.context_compaction import ContextCompactionService


class ContextRetrievalService:
    def __init__(self, app_context_store: AppContextStore, context_compaction: ContextCompactionService) -> None:
        self._app_context_store = app_context_store
        self._context_compaction = context_compaction

    def get_prompt_ready_context(self, app_instance_id: str) -> dict:
        context = self._app_context_store.get_context(app_instance_id)
        layers = self._context_compaction.list_layers(app_instance_id)
        working_set = layers["layers"]["working_set"]
        summary = layers["layers"].get("summary")
        return {
            "app_instance_id": app_instance_id,
            "current_goal": context.current_goal,
            "current_stage": context.current_stage,
            "working_set": working_set,
            "summary": summary,
            "selection_policy": {
                "prefer_layers": ["working_set", "summary"],
                "avoid_raw_history": True,
            },
        }

    def retrieve_detail_refs(self, app_instance_id: str) -> dict:
        layers = self._context_compaction.list_layers(app_instance_id)
        working_set = layers["layers"]["working_set"]
        summary = layers["layers"].get("summary") or {}
        return {
            "app_instance_id": app_instance_id,
            "working_set_refs": working_set.get("detail_refs", []),
            "summary_refs": summary.get("detail_refs", []),
            "detail": layers["layers"]["detail"],
        }
