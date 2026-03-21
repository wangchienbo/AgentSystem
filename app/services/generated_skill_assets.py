from __future__ import annotations

from typing import Any

from app.models.skill_creation import SkillCreationRequest
from app.models.skill_control import SkillRegistryEntry
from app.services.app_data_store import AppDataStore
from app.services.skill_authoring import SkillAuthoringService


class GeneratedSkillAssetStore:
    def __init__(self, data_store: AppDataStore, authoring: SkillAuthoringService | None = None) -> None:
        self._data_store = data_store
        self._authoring = authoring or SkillAuthoringService()
        self._namespace_id = self._data_store.ensure_skill_asset_namespace().namespace_id

    def persist_generated_skill(
        self,
        *,
        request: SkillCreationRequest,
        schema_refs: dict[str, str],
        entry: SkillRegistryEntry,
    ) -> None:
        self._data_store.put_record(
            namespace_id=self._namespace_id,
            key=f"generated-skill:{request.skill_id}",
            value={
                "skill_id": request.skill_id,
                "name": request.name,
                "description": request.description,
                "adapter_kind": request.adapter_kind,
                "generation_operation": request.generation_operation,
                "handler_entry": request.handler_entry,
                "command": list(request.command),
                "tags": list(request.tags),
                "capability_profile": request.capability_profile.model_dump(mode="json"),
                "schema_refs": dict(schema_refs),
                "schemas": {
                    "input": request.schemas.input,
                    "output": request.schemas.output,
                    "error": request.schemas.error,
                },
                "entry": entry.model_dump(mode="json"),
            },
            tags=["generated-skill", request.adapter_kind],
        )

    def list_generated_assets(self) -> list[dict[str, Any]]:
        records = self._data_store.list_records(self._namespace_id)
        return [record.value for record in records if record.key.startswith("generated-skill:")]
