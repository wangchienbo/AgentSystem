from __future__ import annotations

from app.models.context_skill import ContextSkillRequest
from app.services.app_context_store import AppContextStore, AppContextStoreError


class ContextSkillError(ValueError):
    pass


class ContextSkillService:
    def __init__(self, context_store: AppContextStore) -> None:
        self._context_store = context_store

    def execute(self, app_instance_id: str, request: ContextSkillRequest) -> dict:
        if request.operation == "get":
            return self._context_store.get_context(app_instance_id).model_dump(mode="json")

        if request.operation == "update":
            updated = self._context_store.update_context(
                app_instance_id,
                current_goal=request.current_goal or None,
                current_stage=request.current_stage or None,
                status=request.status or None,
            )
            return updated.model_dump(mode="json")

        if request.operation == "append":
            if request.section is None or not request.key:
                raise ContextSkillError("Context append requires section and key")
            entry = self._context_store.append_entry(
                app_instance_id=app_instance_id,
                section=request.section,
                key=request.key,
                value=request.value,
                tags=request.tags,
            )
            return entry.model_dump(mode="json")

        if request.operation == "list_runtime_view":
            runtime_view = self._context_store.get_runtime_view(app_instance_id)
            return {
                "context": runtime_view["context"].model_dump(mode="json"),
                "runtime": None if runtime_view["runtime"] is None else runtime_view["runtime"].model_dump(mode="json"),
            }

        raise ContextSkillError(f"Unsupported context operation: {request.operation}")
