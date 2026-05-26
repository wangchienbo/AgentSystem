from __future__ import annotations

from app.models.context_skill import ContextSkillRequest
from app.services.app_context_store import AppContextStore


class ContextSkillError(ValueError):
    pass


class ContextSkillService:
    def __init__(self, context_store: AppContextStore) -> None:
        self._context_store = context_store

    def execute(self, app_instance_id: str, request: ContextSkillRequest) -> dict:
        if request.operation == "get":
            return self._context_store.get_context(app_instance_id).model_dump(mode="json")
        if request.operation == "update":
            updated = self._context_store.update_context(app_instance_id, current_goal=request.current_goal or None, current_stage=request.current_stage or None, status=request.status or None)
            return updated.model_dump(mode="json")
        if request.operation == "append":
            if request.section is None or not request.key:
                raise ContextSkillError("Context append requires section and key")
            entry = self._context_store.append_entry(app_instance_id=app_instance_id, section=request.section, key=request.key, value=request.value, tags=request.tags)
            return entry.model_dump(mode="json")
        if request.operation == "list_runtime_view":
            runtime_view = self._context_store.get_runtime_view(app_instance_id)
            context_obj = runtime_view["context"]
            context_payload = {
                "app_instance_id": context_obj.app_instance_id,
                "app_name": context_obj.app_name,
                "owner_user_id": context_obj.owner_user_id,
                "description": context_obj.description,
                "status": context_obj.status,
                "current_goal": context_obj.current_goal,
                "current_stage": context_obj.current_stage,
                "updated_at": context_obj.updated_at.isoformat(),
                "entries": [{"entry_id": entry.entry_id, "app_instance_id": entry.app_instance_id, "section": entry.section, "key": entry.key, "value": entry.value, "tags": list(entry.tags), "created_at": entry.created_at.isoformat()} for entry in context_obj.entries],
            }
            runtime_obj = runtime_view["runtime"]
            runtime_payload = None
            if runtime_obj is not None:
                runtime_payload = {
                    "app_instance": dict(runtime_obj.app_instance),
                    "pending_tasks": list(runtime_obj.pending_tasks),
                    "lease": None if runtime_obj.lease is None else {"app_instance_id": runtime_obj.lease.app_instance_id, "status": runtime_obj.lease.status, "health": runtime_obj.lease.health, "last_heartbeat_at": runtime_obj.lease.last_heartbeat_at.isoformat(), "restart_count": runtime_obj.lease.restart_count},
                    "latest_checkpoint": None if runtime_obj.latest_checkpoint is None else {"checkpoint_id": runtime_obj.latest_checkpoint.checkpoint_id, "app_instance_id": runtime_obj.latest_checkpoint.app_instance_id, "status": runtime_obj.latest_checkpoint.status, "pending_tasks": list(runtime_obj.latest_checkpoint.pending_tasks), "metadata": dict(runtime_obj.latest_checkpoint.metadata), "created_at": runtime_obj.latest_checkpoint.created_at.isoformat()},
                }
            return {"context": context_payload, "runtime": runtime_payload}
        raise ContextSkillError(f"Unsupported context operation: {request.operation}")
