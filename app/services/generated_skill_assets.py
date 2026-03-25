from __future__ import annotations

from typing import Any

from app.models.skill_creation import GeneratedSkillVersionComparison, SkillCreationRequest, SkillSchemaDefinition
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
        existing = self.get_generated_asset(request.skill_id) or {}
        revisions = list(existing.get("revisions", []))
        revisions.append(
            {
                "version": entry.active_version,
                "description": request.description,
                "adapter_kind": request.adapter_kind,
                "generation_operation": request.generation_operation,
                "handler_entry": request.handler_entry,
                "command": list(request.command),
                "tags": list(request.tags),
                "capability_profile": request.capability_profile.model_dump(mode="json"),
                "manifest_risk": request.manifest_risk.model_dump(mode="json"),
                "schema_refs": dict(schema_refs),
                "schemas": {
                    "input": request.schemas.input,
                    "output": request.schemas.output,
                    "error": request.schemas.error,
                },
            }
        )
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
                "manifest_risk": request.manifest_risk.model_dump(mode="json"),
                "schema_refs": dict(schema_refs),
                "schemas": {
                    "input": request.schemas.input,
                    "output": request.schemas.output,
                    "error": request.schemas.error,
                },
                "entry": entry.model_dump(mode="json"),
                "revisions": revisions,
            },
            tags=["generated-skill", request.adapter_kind],
        )

    def get_generated_asset(self, skill_id: str) -> dict[str, Any] | None:
        records = self._data_store.list_records(self._namespace_id)
        key = f"generated-skill:{skill_id}"
        for record in records:
            if record.key == key:
                return record.value
        return None

    def build_request_for_version(self, skill_id: str, version: str) -> SkillCreationRequest:
        asset = self.get_generated_asset(skill_id)
        if asset is None:
            raise ValueError(f"Generated skill asset not found: {skill_id}")
        revisions = list(asset.get("revisions", []))
        target = next((item for item in revisions if item.get("version") == version), None)
        if target is None:
            raise ValueError(f"Generated skill revision not found: {skill_id}@{version}")
        return SkillCreationRequest(
            skill_id=skill_id,
            name=asset.get("name", skill_id),
            description=target.get("description", asset.get("description", "")),
            adapter_kind=target.get("adapter_kind", asset.get("adapter_kind", "script")),
            generation_operation=target.get("generation_operation", ""),
            handler_entry=target.get("handler_entry", ""),
            command=list(target.get("command", [])),
            tags=list(target.get("tags", [])),
            capability_profile=target.get("capability_profile", asset.get("capability_profile", {})),
            manifest_risk=target.get("manifest_risk", asset.get("manifest_risk", {})),
            schemas=SkillSchemaDefinition(**target.get("schemas", asset.get("schemas", {}))),
            smoke_test_inputs={},
        )

    def compare_versions(self, skill_id: str, from_version: str, to_version: str) -> GeneratedSkillVersionComparison:
        asset = self.get_generated_asset(skill_id)
        if asset is None:
            raise ValueError(f"Generated skill asset not found: {skill_id}")
        revisions = list(asset.get("revisions", []))
        from_item = next((item for item in revisions if item.get("version") == from_version), None)
        to_item = next((item for item in revisions if item.get("version") == to_version), None)
        if from_item is None or to_item is None:
            raise ValueError(f"Generated skill comparison versions not found: {skill_id}@{from_version}->{to_version}")
        active_version = asset.get("entry", {}).get("active_version", to_version)
        return GeneratedSkillVersionComparison(
            skill_id=skill_id,
            from_version=from_version,
            to_version=to_version,
            active_version=active_version,
            description_changed=from_item.get("description") != to_item.get("description"),
            adapter_kind_changed=from_item.get("adapter_kind") != to_item.get("adapter_kind"),
            generation_operation_changed=from_item.get("generation_operation") != to_item.get("generation_operation"),
            command_changed=list(from_item.get("command", [])) != list(to_item.get("command", [])),
            tags_changed=list(from_item.get("tags", [])) != list(to_item.get("tags", [])),
            capability_profile_changed=from_item.get("capability_profile", {}) != to_item.get("capability_profile", {}),
            manifest_risk_changed=from_item.get("manifest_risk", {}) != to_item.get("manifest_risk", {}),
            schema_refs_changed=from_item.get("schema_refs", {}) != to_item.get("schema_refs", {}),
        )

    def list_generated_assets(self) -> list[dict[str, Any]]:
        records = self._data_store.list_records(self._namespace_id)
        return [record.value for record in records if record.key.startswith("generated-skill:")]
